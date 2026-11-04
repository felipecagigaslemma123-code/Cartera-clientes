"""Casos de integridad de la base inicial y del uso por comandos."""

import datetime as dt
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from openpyxl import load_workbook

from cartera.almacenamiento import ErrorCartera, cargar_cartera, importar_cartera


RAIZ = Path(__file__).resolve().parents[1]
DEMO = RAIZ / "fixtures" / "punto_partida_demo.xlsx"


class PersistenciaComandos(unittest.TestCase):
    def setUp(self):
        self.temporal = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporal.cleanup)
        self.raiz = Path(self.temporal.name)
        self.datos = self.raiz / "datos"
        self.archivo = self.datos / "clientes" / "demo" / "cartera.json"

    def comando(self, *argumentos, variables=None):
        entorno = dict(os.environ, PYTHONPATH=str(RAIZ / "src"), PYTHONDONTWRITEBYTECODE="1")
        entorno.pop("CARTERA_DATOS", None)
        if variables:
            entorno.update(variables)
        return subprocess.run([sys.executable, "-m", "cartera", *map(str, argumentos)],
                              text=True, capture_output=True, env=entorno, timeout=15)

    def importar(self):
        return importar_cartera(self.datos, "demo", DEMO)

    def test_base_conserva_lotes_fechas_origen_y_huella_exacta(self):
        punto, contenido = self.importar()
        leido, guardado = cargar_cartera(self.datos, "demo")
        self.assertEqual(punto, leido)
        self.assertEqual(contenido, guardado)
        self.assertEqual(guardado["esquema_version"], 1)
        self.assertEqual(guardado["origen"]["sha256"], hashlib.sha256(DEMO.read_bytes()).hexdigest())
        self.assertEqual(guardado["origen"]["archivo"], DEMO.name)
        self.assertEqual(dt.datetime.fromisoformat(guardado["importado_en"]).utcoffset(), dt.timedelta(hours=-3))
        self.assertEqual(set(self.archivo.parent.iterdir()), {self.archivo})

    def test_reimportacion_no_cambia_base_ni_registros_existentes(self):
        self.importar()
        previo = self.archivo.read_bytes()
        movimientos = self.archivo.parent / "movimientos.csv"
        movimientos.write_text("registro de demostración", encoding="utf-8")
        salida = self.comando("--datos", self.datos, "importar", "--cliente", "demo", "--archivo", DEMO)
        self.assertNotEqual(salida.returncode, 0)
        self.assertIn("ya existe", salida.stderr)
        self.assertEqual(self.archivo.read_bytes(), previo)
        self.assertEqual(movimientos.read_text(encoding="utf-8"), "registro de demostración")
        self.assertEqual(set(self.archivo.parent.iterdir()), {self.archivo, movimientos})

    def test_validacion_invalida_no_crea_carpeta_de_datos(self):
        malo = self.raiz / "invalido.xlsx"
        libro = load_workbook(DEMO)
        libro["Cartera"]["E8"] = 1
        libro["Lotes"]["B5"] = 61
        libro.save(malo)
        libro.close()
        salida = self.comando("--datos", self.datos, "importar", "--cliente", "demo", "--archivo", malo)
        self.assertNotEqual(salida.returncode, 0)
        self.assertIn("AAA", salida.stderr)
        self.assertIn("BOND1", salida.stderr)
        self.assertFalse(self.datos.exists())

    def test_archivo_corrupto_da_error_claro_sin_salida(self):
        malo = self.raiz / "corrupto.xlsx"
        malo.write_text("no es un Excel", encoding="utf-8")
        salida = self.comando("--datos", self.datos, "importar", "--cliente", "demo", "--archivo", malo)
        self.assertNotEqual(salida.returncode, 0)
        self.assertNotIn("Traceback", salida.stderr)
        self.assertFalse(self.datos.exists())

    def test_base_corrupta_no_se_reescribe(self):
        self.importar()
        self.archivo.write_text("{mal", encoding="utf-8")
        salida = self.comando("--datos", self.datos, "estado", "--cliente", "demo")
        self.assertNotEqual(salida.returncode, 0)
        self.assertNotIn("Traceback", salida.stderr)
        self.assertEqual(self.archivo.read_text(encoding="utf-8"), "{mal")

    def test_base_con_costo_o_cantidades_inconsistentes_se_rechaza(self):
        _, original = self.importar()
        for campo, valor in (("costo", None), ("costo", 1.0), ("cantidad", 1000), ("origen", "inventado")):
            with self.subTest(campo=campo, valor=valor):
                contenido = json.loads(json.dumps(original))
                contenido["lotes"][0][campo] = valor
                self.archivo.write_text(json.dumps(contenido), encoding="utf-8")
                with self.assertRaises(ErrorCartera):
                    cargar_cartera(self.datos, "demo")

    def test_version_desconocida_o_nan_no_se_aceptan(self):
        _, contenido = self.importar()
        contenido["esquema_version"] = 2
        self.archivo.write_text(json.dumps(contenido), encoding="utf-8")
        with self.assertRaises(ErrorCartera):
            cargar_cartera(self.datos, "demo")
        self.archivo.write_text('{"esquema_version": NaN}', encoding="utf-8")
        with self.assertRaises(ErrorCartera):
            cargar_cartera(self.datos, "demo")

    def test_variable_datos_y_precedencia_de_argumento(self):
        salida = self.comando("importar", "--cliente", "demo", "--archivo", DEMO,
                              variables={"CARTERA_DATOS": str(self.datos)})
        self.assertEqual(salida.returncode, 0, salida.stderr)
        salida = self.comando("--datos", self.datos, "estado", "--cliente", "demo",
                              variables={"CARTERA_DATOS": str(self.raiz / "otra")})
        self.assertEqual(salida.returncode, 0, salida.stderr)
        self.assertFalse((self.raiz / "otra").exists())

    def test_falta_ruta_datos_no_usa_directorio_actual(self):
        salida = self.comando("estado", "--cliente", "demo")
        self.assertNotEqual(salida.returncode, 0)
        self.assertIn("CARTERA_DATOS", salida.stderr)
        self.assertNotIn("Traceback", salida.stderr)

    def test_cliente_inexistente_no_crea_datos(self):
        salida = self.comando("--datos", self.datos, "estado", "--cliente", "demo")
        self.assertNotEqual(salida.returncode, 0)
        self.assertIn("No existe", salida.stderr)
        self.assertFalse(self.datos.exists())

    def test_slug_no_puede_escapar_de_la_ruta_de_datos(self):
        for slug in ("../otro", "/tmp/otro", ".", "..", "cliente/otro"):
            with self.subTest(slug=slug):
                with self.assertRaises(ErrorCartera):
                    importar_cartera(self.datos, slug, DEMO)
        self.assertFalse(self.datos.exists())

    def test_enlace_de_cliente_no_puede_escribir_fuera_de_datos(self):
        otro = self.raiz / "otro"
        otro.mkdir()
        clientes = self.datos / "clientes"
        clientes.mkdir(parents=True)
        (clientes / "demo").symlink_to(otro, target_is_directory=True)
        with self.assertRaises(ErrorCartera):
            self.importar()
        self.assertEqual(list(otro.iterdir()), [])

    def test_no_escribe_dentro_del_proyecto(self):
        with self.assertRaises(ErrorCartera):
            importar_cartera(RAIZ, "demo", DEMO)
        self.assertFalse((RAIZ / "clientes").exists())

    def test_estado_muestra_origen_y_faltantes_sin_fabricar_precio(self):
        self.importar()
        previo = self.archivo.read_bytes()
        salida = self.comando("--datos", self.datos, "estado", "--cliente", "demo")
        self.assertEqual(salida.returncode, 0, salida.stderr)
        self.assertIn("104.600,00", salida.stdout)
        self.assertIn("mixto (incluye estimado)", salida.stdout)
        self.assertIn("falta estimar", salida.stdout)
        self.assertEqual(salida.stdout.count("Precio: sin dato"), 6)
        self.assertEqual(salida.stdout.count("resultado: sin dato"), 6)
        self.assertEqual(self.archivo.read_bytes(), previo)

    def test_suma_fuera_de_rango_no_imprime_estado_parcial_ni_traceback(self):
        _, contenido = self.importar()
        contenido["lotes"][0].update(costo=1e308, precio=1e308 / 60)
        contenido["lotes"][1].update(costo=1e308, precio=1e308 / 40)
        self.archivo.write_text(json.dumps(contenido), encoding="utf-8")
        salida = self.comando("--datos", self.datos, "estado", "--cliente", "demo")
        self.assertNotEqual(salida.returncode, 0)
        self.assertIn("rango", salida.stderr)
        self.assertNotIn("Traceback", salida.stderr)
        self.assertEqual(salida.stdout, "")

    def test_base_con_decimales_en_limite_de_tolerancia_se_puede_releer(self):
        excel = self.raiz / "decimales.xlsx"
        libro = load_workbook(DEMO)
        libro["Cartera"]["D5"] = 1000.5
        libro["Lotes"]["B5"] = 100.1
        libro["Lotes"]["B6"] = 100.1
        for _ in range(8):
            libro["Lotes"].append(["AAA", 100.1, "Extracto", None, 1, None, 1000, ""])
        libro.save(excel)
        libro.close()
        importar_cartera(self.datos, "demo", excel)
        salida = self.comando("--datos", self.datos, "estado", "--cliente", "demo")
        self.assertEqual(salida.returncode, 0, salida.stderr)
        self.assertIn("cantidad 1.000,5", salida.stdout)


if __name__ == "__main__":
    unittest.main()
