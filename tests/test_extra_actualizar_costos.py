"""Correcciones auditadas de costos con archivos exclusivamente ficticios."""

import datetime as dt
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock
from zoneinfo import ZoneInfo

from openpyxl import load_workbook

from cartera import almacenamiento


RAIZ = Path(__file__).resolve().parents[1]
DEMO = RAIZ / "fixtures" / "punto_partida_demo.xlsx"
AR = ZoneInfo("America/Argentina/Buenos_Aires")


class ActualizarCostos(unittest.TestCase):
    def setUp(self):
        self.temporal = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporal.cleanup)
        self.raiz = Path(self.temporal.name)
        self.datos = self.raiz / "datos"
        self.base = self.datos / "clientes" / "demo" / "cartera.json"
        self.historial = self.base.parent / "historial_cartera"

    def importar(self):
        return almacenamiento.importar_cartera(self.datos, "demo", DEMO)

    def excel(self, cambio=None, nombre="corregido.xlsx"):
        ruta = self.raiz / nombre
        libro = load_workbook(DEMO)
        try:
            if cambio:
                cambio(libro)
            libro.save(ruta)
        finally:
            libro.close()
        return ruta

    def comando(self, archivo):
        entorno = dict(os.environ, PYTHONPATH=str(RAIZ / "src"), PYTHONDONTWRITEBYTECODE="1")
        entorno.pop("CARTERA_DATOS", None)
        return subprocess.run(
            [sys.executable, "-m", "cartera", "--datos", str(self.datos),
             "actualizar-costos", "--cliente", "demo", "--archivo", str(archivo)],
            text=True, capture_output=True, env=entorno, timeout=15,
        )

    def instantanea(self):
        if not self.datos.exists():
            return None
        return {
            str(ruta.relative_to(self.datos)): (ruta.read_bytes() if ruta.is_file() else None,
                                               ruta.stat().st_mtime_ns)
            for ruta in self.datos.rglob("*")
        }

    def test_actualizacion_correcta_guarda_historia_completa_y_nueva_procedencia(self):
        self.importar()
        anterior = self.base.read_bytes()
        previo = json.loads(anterior)

        def cambio(libro):
            libro["Lotes"]["F9"] = 2100
            libro["Lotes"]["H9"] = "Estimación revisada"

        archivo = self.excel(cambio)
        salida = self.comando(archivo)
        self.assertEqual(salida.returncode, 0, salida.stderr)
        actual = json.loads(self.base.read_text(encoding="utf-8"))
        self.assertEqual(actual["esquema_version"], previo["esquema_version"])
        self.assertNotEqual(actual["importado_en"], previo["importado_en"])
        self.assertEqual(dt.datetime.fromisoformat(actual["importado_en"]).utcoffset(), dt.timedelta(hours=-3))
        self.assertEqual(actual["origen"]["archivo"], archivo.name)
        self.assertEqual(actual["origen"]["sha256"], hashlib.sha256(archivo.read_bytes()).hexdigest())
        self.assertEqual(actual["posiciones"], previo["posiciones"])
        self.assertEqual(actual["lotes"][4]["costo"], 21000)
        self.assertEqual(actual["lotes"][4]["nota"], "Estimación revisada")
        versiones = list(self.historial.glob("*.json"))
        self.assertEqual(len(versiones), 1)
        self.assertEqual(versiones[0].read_bytes(), anterior)
        self.assertRegex(versiones[0].name, r"\d{4}-?\d{2}-?\d{2}[T_ -]\d{2}[-_:]?\d{2}[-_:]?\d{2}")
        self.assertIn("CCC", salida.stdout)
        self.assertIn("20.000,00", salida.stdout)
        self.assertIn("21.000,00", salida.stdout)
        self.assertIn("estimado", salida.stdout.lower())

    def test_cantidad_total_distinta_aunque_excel_cierre_falla_sin_escribir(self):
        self.importar()

        def cambio(libro):
            libro["Cartera"]["D5"] = 100.1
            libro["Lotes"]["B5"] = 60.1

        archivo = self.excel(cambio)
        antes = self.instantanea()
        salida = self.comando(archivo)
        self.assertNotEqual(salida.returncode, 0)
        self.assertIn("AAA", salida.stderr)
        self.assertEqual(self.instantanea(), antes)

    def test_base_inexistente_falla_sin_crear_carpeta(self):
        salida = self.comando(DEMO)
        self.assertNotEqual(salida.returncode, 0)
        self.assertFalse(self.datos.exists())
        self.assertNotIn("Traceback", salida.stderr)

    def test_mismo_excel_no_modifica_base_metadata_ni_crea_historial(self):
        self.importar()
        antes = self.instantanea()
        salida = self.comando(DEMO)
        self.assertEqual(salida.returncode, 0, salida.stderr)
        self.assertIn("no hay cambios", salida.stdout.lower())
        self.assertEqual(self.instantanea(), antes)
        self.assertFalse(self.historial.exists())

    def test_excel_regrabado_y_lotes_reordenados_no_son_cambios(self):
        self.importar()

        def reordenar(libro):
            hoja = libro["Lotes"]
            primera = [hoja.cell(5, columna).value for columna in range(1, 9)]
            segunda = [hoja.cell(6, columna).value for columna in range(1, 9)]
            for columna, valor in enumerate(segunda, 1):
                hoja.cell(5, columna, valor)
            for columna, valor in enumerate(primera, 1):
                hoja.cell(6, columna, valor)

        antes = self.instantanea()
        for archivo in (self.excel(nombre="regrabado.xlsx"), self.excel(reordenar, "reordenado.xlsx")):
            with self.subTest(archivo=archivo.name):
                salida = self.comando(archivo)
                self.assertEqual(salida.returncode, 0, salida.stderr)
                self.assertIn("no hay cambios", salida.stdout.lower())
                self.assertEqual(self.instantanea(), antes)

    def test_dos_actualizaciones_seguidas_no_pisan_historial(self):
        self.importar()
        estados = [self.base.read_bytes()]
        nombres = []
        with mock.patch.object(almacenamiento, "datetime", wraps=dt.datetime) as reloj:
            reloj.now.return_value = dt.datetime(2026, 11, 4, 14, 0, tzinfo=AR)
            for precio in (2100, 2200):
                archivo = self.excel(lambda libro: setattr(libro["Lotes"]["F9"], "value", precio))
                resultado = almacenamiento.actualizar_costos(self.datos, "demo", archivo)
                self.assertTrue(resultado["cambios"])
                estados.append(self.base.read_bytes())
                nombres.append({ruta.name for ruta in self.historial.glob("*.json")})
        self.assertEqual(len(nombres[0]), 1)
        self.assertEqual(len(nombres[1]), 2)
        self.assertTrue(nombres[0] < nombres[1])
        self.assertEqual({ruta.read_bytes() for ruta in self.historial.glob("*.json")}, set(estados[:2]))

    def test_completar_costo_pendiente_muestra_costo_y_origen_nuevos(self):
        self.importar()

        def cambio(libro):
            libro["Lotes"]["D10"] = dt.datetime.now(AR).date()
            libro["Lotes"]["F10"] = 150000

        salida = self.comando(self.excel(cambio))
        self.assertEqual(salida.returncode, 0, salida.stderr)
        self.assertIn("BOND1", salida.stdout)
        self.assertIn("falta estimar", salida.stdout.lower())
        self.assertIn("1.500.000,00", salida.stdout)
        self.assertIn("estimado", salida.stdout.lower())
        self.assertNotIn("advertencia", (salida.stdout + salida.stderr).lower())
        nuevo = json.loads(self.base.read_text(encoding="utf-8"))
        self.assertEqual(nuevo["lotes"][5]["origen"], "estimado")
        self.assertEqual(nuevo["lotes"][5]["costo"], 1500000)

    def test_dividir_lote_estimado_conservando_cantidad_total_se_acepta(self):
        self.importar()

        def cambio(libro):
            libro["Lotes"]["B9"] = 6
            libro["Lotes"].append(["CCC", 4, "A estimar", dt.date(2025, 1, 15), 1, 2000, None, "Lote separado"])

        salida = self.comando(self.excel(cambio))
        self.assertEqual(salida.returncode, 0, salida.stderr)
        nuevo = json.loads(self.base.read_text(encoding="utf-8"))
        lotes = [lote for lote in nuevo["lotes"] if lote["ticker"] == "CCC"]
        self.assertEqual(len(lotes), 2)
        self.assertEqual(sum(lote["cantidad"] for lote in lotes), 10)
        self.assertEqual(sum(lote["costo"] for lote in lotes), 20000)
        self.assertEqual(len(list(self.historial.glob("*.json"))), 1)

    def test_cambio_de_ticker_especie_tipo_o_unidad_es_rechazado_sin_escritura(self):
        self.importar()

        def ticker(libro):
            libro["Cartera"]["A5"] = "AAD"
            libro["Lotes"]["A5"] = "AAD"
            libro["Lotes"]["A6"] = "AAD"

        def especie(libro):
            libro["Cartera"]["B5"] = "Nombre distinto"

        def tipo(libro):
            libro["Cartera"]["C5"] = "accion"

        def unidad(libro):
            libro["Cartera"]["C5"] = "bono"
            libro["Cartera"]["E5"] = 100
            libro["Lotes"]["E5"] = 100
            libro["Lotes"]["E6"] = 100

        antes = self.instantanea()
        for cambio in (ticker, especie, tipo, unidad):
            with self.subTest(cambio=cambio.__name__):
                salida = self.comando(self.excel(cambio))
                self.assertNotEqual(salida.returncode, 0)
                self.assertEqual(self.instantanea(), antes)

    def test_excel_invalido_acumula_errores_sin_escribir(self):
        self.importar()

        def cambio(libro):
            libro["Lotes"]["B5"] = 61
            libro["Lotes"]["F8"] = -900

        antes = self.instantanea()
        salida = self.comando(self.excel(cambio))
        self.assertNotEqual(salida.returncode, 0)
        self.assertIn("AAA", salida.stderr)
        self.assertIn("BBB", salida.stderr)
        self.assertEqual(self.instantanea(), antes)

    def test_extracto_a_estimado_advierte_sin_bloquear(self):
        self.importar()

        def cambio(libro):
            libro["Lotes"]["C5"] = "A estimar"
            libro["Lotes"]["F5"] = 1010

        salida = self.comando(self.excel(cambio))
        self.assertEqual(salida.returncode, 0, salida.stderr)
        self.assertIn("advertencia", (salida.stdout + salida.stderr).lower())
        self.assertIn("AAA", salida.stdout + salida.stderr)
        self.assertIn("extracto", (salida.stdout + salida.stderr).lower())
        self.assertEqual(json.loads(self.base.read_text())["lotes"][0]["origen"], "estimado")

    def test_extracto_a_pendiente_advierte_y_no_muestra_cero(self):
        self.importar()

        def cambio(libro):
            libro["Lotes"]["C5"] = "A estimar"
            libro["Lotes"]["F5"] = None

        salida = self.comando(self.excel(cambio))
        self.assertEqual(salida.returncode, 0, salida.stderr)
        self.assertIn("advertencia", (salida.stdout + salida.stderr).lower())
        self.assertIn("falta estimar", salida.stdout.lower())
        self.assertIsNone(json.loads(self.base.read_text())["lotes"][0]["costo"])

    def test_cambio_de_costo_extracto_advierte_aunque_total_no_cambie(self):
        self.importar()

        def cambio(libro):
            libro["Lotes"]["G5"] = 60700
            libro["Lotes"]["G6"] = 43900

        archivo = self.excel(cambio)
        resultado = almacenamiento.actualizar_costos(self.datos, "demo", archivo)
        self.assertTrue(resultado["advertencias"])
        self.assertTrue(any("AAA" in aviso and "extracto" in aviso.lower() for aviso in resultado["advertencias"]))
        cambio_aaa = next(c for c in resultado["cambios"] if c["ticker"] == "AAA")
        self.assertEqual(cambio_aaa["costo_anterior"], cambio_aaa["costo_nuevo"])
        self.assertEqual(cambio_aaa["origen_nuevo"], "extracto")

    def test_cambiar_solo_notas_se_audita_sin_advertencia_de_extracto(self):
        self.importar()
        archivo = self.excel(lambda libro: setattr(libro["Lotes"]["H5"], "value", "Nota corregida"))
        resultado = almacenamiento.actualizar_costos(self.datos, "demo", archivo)
        self.assertTrue(resultado["cambios"])
        self.assertEqual(resultado["advertencias"], [])
        self.assertTrue(resultado["historial"].is_file())

    def test_campos_opcionales_existentes_siguen_compatibles_en_version_uno(self):
        self.importar()
        contenido = json.loads(self.base.read_text(encoding="utf-8"))
        contenido["revision_externa_demo"] = {"validado": True, "nota": "Dato ficticio"}
        self.base.write_text(json.dumps(contenido), encoding="utf-8")
        archivo = self.excel(lambda libro: setattr(libro["Lotes"]["F9"], "value", 2100))
        salida = self.comando(archivo)
        self.assertEqual(salida.returncode, 0, salida.stderr)
        nuevo = json.loads(self.base.read_text(encoding="utf-8"))
        self.assertEqual(nuevo["esquema_version"], 1)
        self.assertEqual(nuevo["revision_externa_demo"], contenido["revision_externa_demo"])

    def test_actualizar_con_fecha_futura_falla_sin_escribir(self):
        self.importar()
        manana = dt.datetime.now(AR).date() + dt.timedelta(days=1)
        archivo = self.excel(lambda libro: setattr(libro["Lotes"]["D9"], "value", manana))
        antes = self.instantanea()
        salida = self.comando(archivo)
        self.assertNotEqual(salida.returncode, 0)
        for texto in ("Lotes", "9", "CCC"):
            self.assertIn(texto, salida.stderr)
        self.assertEqual(self.instantanea(), antes)

    def test_actualizar_con_fecha_de_hoy_se_acepta(self):
        self.importar()
        hoy = dt.datetime.now(AR).date()
        archivo = self.excel(lambda libro: setattr(libro["Lotes"]["D9"], "value", hoy))
        salida = self.comando(archivo)
        self.assertEqual(salida.returncode, 0, salida.stderr)
        self.assertEqual(json.loads(self.base.read_text())["lotes"][4]["fecha"], hoy.isoformat())

    def test_falla_al_guardar_historial_conserva_base_completa(self):
        self.importar()
        antes = self.base.read_bytes()
        archivo = self.excel(lambda libro: setattr(libro["Lotes"]["F9"], "value", 2100))
        with mock.patch.object(almacenamiento.os, "link", side_effect=OSError("falló historial")):
            with self.assertRaises((OSError, almacenamiento.ErrorCartera)):
                almacenamiento.actualizar_costos(self.datos, "demo", archivo)
        self.assertEqual(self.base.read_bytes(), antes)
        self.assertEqual(list(self.base.parent.glob("*.tmp")), [])

    def test_falla_al_reemplazar_conserva_base_y_version_anterior(self):
        self.importar()
        antes = self.base.read_bytes()
        archivo = self.excel(lambda libro: setattr(libro["Lotes"]["F9"], "value", 2100))
        with mock.patch.object(almacenamiento.os, "replace", side_effect=OSError("falló reemplazo")):
            with self.assertRaises((OSError, almacenamiento.ErrorCartera)):
                almacenamiento.actualizar_costos(self.datos, "demo", archivo)
        self.assertEqual(self.base.read_bytes(), antes)
        for version in self.historial.glob("*.json"):
            self.assertEqual(version.read_bytes(), antes)
        self.assertEqual(list(self.base.parent.glob("*.tmp")), [])


if __name__ == "__main__":
    unittest.main()
