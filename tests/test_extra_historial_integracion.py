"""Ejecución histórica independiente, sin red, datos ni avisos reales."""

import copy
import csv
import io
import json
import os
import stat
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import patch

from cartera.__main__ import main
from cartera.almacenamiento import importar_cartera
from cartera.historial import ErrorHistorial, correr_historial, leer_mep
from test_etapa6_historial import D1, D2, D3, escribir_extracto, fila_xlsx

DEMO = Path(__file__).resolve().parents[1] / "fixtures" / "punto_partida_demo.xlsx"


class PublicacionHistorial(unittest.TestCase):
    def setUp(self):
        temporal = tempfile.TemporaryDirectory()
        self.addCleanup(temporal.cleanup)
        self.raiz = Path(temporal.name)
        self.datos = self.raiz / "datos"
        self.punto, _ = importar_cartera(self.datos, "demo", DEMO)
        self.carpeta = self.datos / "clientes" / "demo"
        self.extractos = self.carpeta / "extractos"
        self.extractos.mkdir()
        self.realizado = self.carpeta / "realizado.csv"
        self.mep = self.carpeta / "mep_diario.csv"
        self.consultas = []
        self.escribir()

    def escribir(self, filas=None, titulo="PESOS"):
        escribir_extracto(self.extractos / "ficticio.xlsx", titulo, filas if filas is not None else [
            fila_xlsx(D1, "RECIBO DE COBRO", 1, 0, None, 5000, 5000),
            fila_xlsx(D1, "COMPRA NORMAL", 2, 100, "AAA", -1000, 4000),
            fila_xlsx(D2, "VENTA", 3, -40, "AAA", 600, 4600),
            fila_xlsx(D3, "DIVIDENDOS", 4, 0, "BBB", 70, 4670)])

    def fetch(self, url):
        self.consultas.append(url)
        if url.endswith("/AL30D"):
            return [{"date": D1.isoformat(), "c": 100}]
        return [{"date": D1.isoformat(), "c": 150000}, {"date": D2.isoformat(), "c": 160000}]

    def cli(self, *argumentos):
        salida, errores = io.StringIO(), io.StringIO()
        with patch("cartera.__main__.consultar_json", side_effect=self.fetch), redirect_stdout(salida), redirect_stderr(errores):
            codigo = main(["--datos", str(self.datos), "historial", "--cliente", "demo", *argumentos])
        return codigo, salida.getvalue(), errores.getvalue()

    def arbol(self):
        return {str(p.relative_to(self.carpeta)): (p.read_bytes(), p.stat().st_mtime_ns)
                for p in self.carpeta.rglob("*") if p.is_file()}

    def anteriores(self):
        self.realizado.write_bytes(b"salida previa ficticia\n")
        self.mep.write_text("fecha,mep\n2025-12-01,1400\n", encoding="utf-8")

    def temporales(self):
        return list(self.carpeta.glob(".historial-*.tmp"))

    def test_no_depende_del_dia_cero_ni_de_movimientos_manuales(self):
        (self.carpeta / "dia_cero.json").write_text("JSON ficticio deliberadamente inválido")
        (self.carpeta / "movimientos.csv").write_text("CSV ficticio deliberadamente inválido")
        antes = self.arbol()
        codigo, salida, errores = self.cli()
        self.assertEqual(codigo, 0, errores)
        self.assertIn("270,00", salida)
        self.assertEqual(self.consultas, [])
        despues = self.arbol()
        self.assertEqual({n: v for n, v in despues.items() if n in antes}, antes)
        self.assertEqual(set(despues) - set(antes), {"realizado.csv"})

    def test_unknown_se_lista_completo_y_no_suma_su_importe(self):
        self.escribir([fila_xlsx(D1, "OPERACION DESCONOCIDA", "AB-12", 3, "FICT", 900000, 900000, "Revisar íntegro"),
                       fila_xlsx(D2, "DIVIDENDOS", 2, 0, "AAA", 7, 900007)])
        codigo, salida, errores = self.cli()
        self.assertEqual(codigo, 0, errores)
        self.assertIn("Total conocido: ARS 7,00", salida)
        linea = next(l for l in salida.splitlines() if l.startswith("SIN CLASIFICAR"))
        fila = json.loads(linea.split(": ", 1)[1])
        self.assertEqual(fila["numero"], "AB-12")
        self.assertEqual(fila["importe"], 900000)
        self.assertEqual(fila["referencia"], "Revisar íntegro")
        self.assertTrue({"operado", "liquida", "precio", "saldo", "moneda", "cuenta", "cantidad", "especie", "archivo", "fila"} <= set(fila))

    def test_comprobante_vacio_se_lista_sin_silenciar_ni_sumar(self):
        self.escribir([fila_xlsx(D1, None, "", 0, None, 999, 999)])
        codigo, salida, errores = self.cli()
        self.assertEqual(codigo, 0, errores)
        self.assertIn("Total conocido: ARS 0,00", salida)
        self.assertIn("SIN CLASIFICAR", salida)
        self.assertIn('"importe": 999.0', salida)

    def test_costo_derivado_diferente_se_informa_sin_corregir_base(self):
        self.escribir([fila_xlsx(D1, "COMPRA NORMAL", 1, 100, "AAA", -1000, -1000)])
        base = (self.carpeta / "cartera.json").read_bytes()
        h = correr_historial(self.carpeta, self.punto)
        self.assertNotIn("AAA", h.diferencias_tenencias)
        self.assertEqual(h.diferencias_costos["AAA"]["derivada"], 1000)
        self.assertTrue(any("AAA" in a and "costo" in a for a in h.avisos))
        self.assertEqual((self.carpeta / "cartera.json").read_bytes(), base)

    def test_actualizar_usa_solo_cierres_comunes_y_preserva_otros_dias(self):
        self.mep.write_text("fecha,mep\n2025-12-01,1400\n2026-01-10,1450\n", encoding="utf-8")
        h = correr_historial(self.carpeta, self.punto, fetch=self.fetch, actualizar_mep=True)
        self.assertEqual(h.total_conocido, 270)
        valores = leer_mep(self.mep)
        self.assertEqual(valores[D1], 1500)
        self.assertNotIn(D2, valores)
        self.assertEqual(len(valores), 2)
        self.assertEqual(self.consultas, ["https://data912.com/historical/bonds/AL30", "https://data912.com/historical/bonds/AL30D"])
        for ruta in (self.mep, self.realizado):
            self.assertEqual(stat.S_IMODE(ruta.stat().st_mode), 0o600)

    def test_meps_actualizados_se_usan_antes_de_generar_realizado(self):
        self.escribir([fila_xlsx(D1, "COMPRA NORMAL", 1, 10, "AAA", -100, -100)], titulo="DOLARES")
        escribir_extracto(self.extractos / "venta.xlsx", "PESOS", [fila_xlsx(D2, "VENTA", 2, -10, "AAA", 170000, 170000)])
        h = correr_historial(self.carpeta, self.punto, fetch=self.fetch, actualizar_mep=True)
        self.assertEqual(h.realizados[0].costo_ars, 150000)
        self.assertEqual(h.realizados[0].resultado_ars, 20000)
        with self.realizado.open(newline="") as entrada:
            fila = list(csv.DictReader(entrada))[0]
        self.assertEqual(float(fila["costo_ars"]), 150000)
        self.assertEqual(float(fila["resultado_ars"]), 20000)

    def test_actualizar_no_calcula_con_un_mep_previo_que_va_a_reemplazar(self):
        self.escribir([fila_xlsx(D1, "COMPRA NORMAL", 1, 10, "AAA", -100, -100)], titulo="DOLARES")
        escribir_extracto(self.extractos / "venta.xlsx", "PESOS", [fila_xlsx(D2, "VENTA", 2, -10, "AAA", 170000, 170000)])
        self.mep.write_text("fecha,mep\n2026-01-10,1e308\n", encoding="utf-8")
        h = correr_historial(self.carpeta, self.punto, fetch=self.fetch, actualizar_mep=True)
        self.assertEqual(h.realizados[0].resultado_ars, 20000)
        self.assertEqual(leer_mep(self.mep)[D1], 1500)

    def test_archivo_invalido_preserva_salidas_y_no_consulta(self):
        self.anteriores()
        escribir_extracto(self.extractos / "invalido.xlsx", "Hoja1", [])
        antes = self.arbol()
        codigo, _, errores = self.cli("--actualizar-mep")
        self.assertEqual(codigo, 1)
        self.assertTrue(errores)
        self.assertEqual(self.consultas, [])
        self.assertEqual(self.arbol(), antes)
        self.assertEqual(self.temporales(), [])

    def test_movimiento_conocido_invalido_falla_antes_de_consultar_mep(self):
        self.escribir([fila_xlsx(D1, "COMPRA NORMAL", 1, 0, "AAA", -100, -100)])
        antes = self.arbol()
        codigo, _, errores = self.cli("--actualizar-mep")
        self.assertEqual(codigo, 1)
        self.assertTrue(errores)
        self.assertEqual(self.consultas, [])
        self.assertEqual(self.arbol(), antes)

    def test_cierres_o_ajustes_o_mep_invalidos_no_publican(self):
        self.anteriores()
        casos = (("cierres.json", '{"AAA": true}'),
                 ("ajustes_historial.csv", "fecha,tipo\n2026-01-10,deposito\n"),
                 ("mep_diario.csv", "fecha,mep\n2026-01-10,nan\n"))
        for nombre, texto in casos:
            with self.subTest(archivo=nombre):
                self.anteriores()
                ruta = self.carpeta / nombre
                ruta.write_text(texto)
                antes = self.arbol()
                with self.assertRaises(ErrorHistorial):
                    correr_historial(self.carpeta, self.punto, fetch=self.fetch, actualizar_mep=True)
                self.assertEqual(self.arbol(), antes)
                self.assertEqual(self.consultas, [])
                if nombre != "mep_diario.csv":
                    ruta.unlink()

    def test_fuente_historica_invalida_preserva_ambas_salidas(self):
        self.anteriores()
        for respuesta in ({"Error": "ficticio"}, [], [{"date": "inválida", "c": 1}], [{"date": D1.isoformat(), "c": 0}]):
            with self.subTest(respuesta=respuesta):
                antes = self.arbol()
                with self.assertRaises(ErrorHistorial):
                    correr_historial(self.carpeta, self.punto, fetch=lambda u: copy.deepcopy(respuesta), actualizar_mep=True)
                self.assertEqual(self.arbol(), antes)
                self.assertEqual(self.temporales(), [])

    def test_carpeta_sin_xlsx_es_error_sin_publicar(self):
        (self.extractos / "ficticio.xlsx").unlink()
        self.anteriores()
        antes = self.arbol()
        with self.assertRaises(ErrorHistorial):
            correr_historial(self.carpeta, self.punto)
        self.assertEqual(self.arbol(), antes)

    def test_enlace_de_salida_se_rechaza_sin_tocar_destino(self):
        destino = self.raiz / "salida_ficticia.csv"
        destino.write_text("original")
        self.realizado.symlink_to(destino)
        with self.assertRaises(ErrorHistorial):
            correr_historial(self.carpeta, self.punto, fetch=self.fetch, actualizar_mep=True)
        self.assertEqual(destino.read_text(), "original")
        self.assertEqual(self.consultas, [])
        self.assertEqual(self.temporales(), [])

    def test_fallo_preparando_temporal_preserva_ambas_salidas(self):
        self.anteriores()
        antes = self.arbol()
        with patch("cartera.historial.os.fsync", side_effect=OSError("fallo ficticio")):
            with self.assertRaises(OSError):
                correr_historial(self.carpeta, self.punto, fetch=self.fetch, actualizar_mep=True)
        self.assertEqual(self.arbol(), antes)
        self.assertEqual(self.temporales(), [])

    def test_fallo_segundo_replace_restaura_ambas_versiones_anteriores(self):
        self.anteriores()
        anterior_realizado, anterior_mep = self.realizado.read_bytes(), self.mep.read_bytes()
        reemplazar = os.replace
        def fallar_mep(origen, destino):
            if Path(destino) == self.mep:
                raise OSError("fallo ficticio de publicación MEP")
            return reemplazar(origen, destino)
        with patch("cartera.historial.os.replace", side_effect=fallar_mep):
            with self.assertRaises(OSError):
                correr_historial(self.carpeta, self.punto, fetch=self.fetch, actualizar_mep=True)
        self.assertEqual(self.realizado.read_bytes(), anterior_realizado)
        self.assertEqual(self.mep.read_bytes(), anterior_mep)
        self.assertEqual(self.temporales(), [])

    def test_fallo_segundo_replace_sin_salidas_previas_restaura_ausencia(self):
        reemplazar = os.replace
        def fallar_mep(origen, destino):
            if Path(destino) == self.mep:
                raise OSError("fallo ficticio")
            return reemplazar(origen, destino)
        with patch("cartera.historial.os.replace", side_effect=fallar_mep):
            with self.assertRaises(OSError):
                correr_historial(self.carpeta, self.punto, fetch=self.fetch, actualizar_mep=True)
        self.assertFalse(self.realizado.exists())
        self.assertFalse(self.mep.exists())
        self.assertEqual(self.temporales(), [])

    def test_dos_corridas_concurrentes_dejan_csv_y_mep_coherentes(self):
        self.escribir([fila_xlsx(D1, "COMPRA NORMAL", 1, 10, "AAA", -100, -100)], titulo="DOLARES")
        escribir_extracto(self.extractos / "venta.xlsx", "PESOS", [fila_xlsx(D2, "VENTA", 2, -10, "AAA", 170000, 170000)])
        def correr(cambio):
            def fetch(url):
                return [{"date": D1.isoformat(), "c": 100 if url.endswith("/AL30D") else cambio * 100}]
            return correr_historial(self.carpeta, self.punto, fetch=fetch, actualizar_mep=True)
        with ThreadPoolExecutor(max_workers=2) as ejecutor:
            list(ejecutor.map(correr, (1500, 1600)))
        cambio_final = leer_mep(self.mep)[D1]
        with self.realizado.open(newline="") as entrada:
            fila = list(csv.DictReader(entrada))[0]
        self.assertEqual(float(fila["costo_ars"]), cambio_final * 100)
        self.assertEqual(float(fila["resultado_ars"]), 170000 - cambio_final * 100)
        self.assertEqual(self.temporales(), [])


if __name__ == "__main__":
    unittest.main()
