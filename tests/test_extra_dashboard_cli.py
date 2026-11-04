"""Integridad del comando dashboard con datos y fuentes completamente ficticios."""

import csv
import datetime as dt
import inspect
import io
import json
import os
from pathlib import Path
import re
import stat
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from unittest.mock import patch
from zoneinfo import ZoneInfo

from cartera.__main__ import main
from cartera.almacenamiento import importar_cartera


RAIZ = Path(__file__).resolve().parents[1]
DEMO = RAIZ / "fixtures" / "punto_partida_demo.xlsx"
T = dt.datetime(2026, 11, 3, 12, tzinfo=ZoneInfo("America/Argentina/Buenos_Aires"))
PANELES = {
    "arg_cedears": [{"symbol": "AAA", "c": 1200.0}, {"symbol": "BBB", "c": 1100.0}],
    "arg_stocks": [{"symbol": "CCC", "c": 2500.0}],
    "arg_bonds": [{"symbol": "BOND1", "c": 160000.0}],
    "arg_notes": [{"symbol": "NOTE1", "c": 110.0}],
    "arg_corp": [{"symbol": "ONX", "c": 150000.0}],
    "mep": [{"ticker": "AL30", "mark": 1500.0}],
}


def datos_de(html):
    encontrado = re.search(r'<script id="datos-cartera" type="application/json">(.*?)</script>', html, re.S)
    if encontrado is None:
        raise AssertionError("No se encontró el bloque de datos del dashboard")
    return json.loads(encontrado.group(1))


class IntegridadDashboard(unittest.TestCase):
    def setUp(self):
        self.temporal = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporal.cleanup)
        self.raiz = Path(self.temporal.name)
        self.datos = self.raiz / "datos"
        importar_cartera(self.datos, "demo", DEMO)
        self.carpeta = self.datos / "clientes" / "demo"
        self.salida = self.carpeta / "dashboard.html"

    def ejecutar(self):
        salida, errores = io.StringIO(), io.StringIO()
        with redirect_stdout(salida), redirect_stderr(errores):
            codigo = main(["--datos", str(self.datos), "dashboard", "--cliente", "demo"])
        return codigo, salida.getvalue(), errores.getvalue()

    def fetch(self, url):
        return PANELES[url.rsplit("/", 1)[-1]]

    def archivos(self):
        return {str(ruta.relative_to(self.carpeta)): ruta.read_bytes()
                for ruta in self.carpeta.rglob("*") if ruta.is_file()}

    def previa(self):
        self.salida.write_text("Versión anterior ficticia", encoding="utf-8")
        self.salida.chmod(0o600)

    def test_json_opcional_malformado_no_consulta_ni_modifica_archivos(self):
        self.previa()
        for nombre in ("perfil.json", "niveles.json", "instrumentos.json", "efectivo.json", "dia_cero.json"):
            with self.subTest(nombre=nombre):
                ruta = self.carpeta / nombre
                ruta.write_text("{json roto", encoding="utf-8")
                antes = self.archivos()
                with patch("cartera.__main__.consultar_json") as consultar:
                    codigo, salida, errores = self.ejecutar()
                self.assertNotEqual(codigo, 0)
                self.assertIn(nombre, errores)
                self.assertNotIn("Traceback", errores)
                self.assertEqual(self.archivos(), antes)
                consultar.assert_not_called()
                ruta.unlink()

    def test_nivel_no_numerico_no_consulta_ni_modifica_base_o_dashboard(self):
        self.previa()
        ruta = self.carpeta / "niveles.json"
        ruta.write_text('{"AAA": {"take_profit": "alto", "stop_loss": null}}', encoding="utf-8")
        antes = self.archivos()
        with patch("cartera.__main__.consultar_json") as consultar:
            codigo, _, errores = self.ejecutar()
        self.assertNotEqual(codigo, 0)
        self.assertIn("niveles", errores.lower())
        self.assertIn("AAA", errores)
        self.assertEqual(self.archivos(), antes)
        consultar.assert_not_called()

    def test_vencimiento_invalido_no_consulta_ni_modifica_archivos(self):
        self.previa()
        (self.carpeta / "instrumentos.json").write_text(
            '{"BOND1": {"vencimiento": "2026-02-30"}}', encoding="utf-8")
        antes = self.archivos()
        with patch("cartera.__main__.consultar_json") as consultar:
            codigo, _, errores = self.ejecutar()
        self.assertNotEqual(codigo, 0)
        self.assertIn("BOND1", errores)
        self.assertIn("instrumentos", errores.lower())
        self.assertEqual(self.archivos(), antes)
        consultar.assert_not_called()

    def test_objeto_opcional_con_tipo_incorrecto_no_consulta(self):
        self.previa()
        (self.carpeta / "perfil.json").write_text('["no es un perfil"]', encoding="utf-8")
        antes = self.archivos()
        with patch("cartera.__main__.consultar_json") as consultar:
            codigo, _, errores = self.ejecutar()
        self.assertNotEqual(codigo, 0)
        self.assertIn("perfil", errores.lower())
        self.assertEqual(self.archivos(), antes)
        consultar.assert_not_called()

    def test_sin_opcionales_genera_con_slug_y_saldos_faltantes(self):
        with patch("cartera.__main__.consultar_json", side_effect=self.fetch):
            codigo, salida, errores = self.ejecutar()
        self.assertEqual(codigo, 0, errores)
        html = self.salida.read_text(encoding="utf-8")
        datos = datos_de(html)
        self.assertIn("demo", html)
        self.assertIsNone(datos["dia_cero"])
        self.assertIsNone(datos["efectivo"]["ARS"])
        self.assertIsNone(datos["efectivo"]["USD"])
        self.assertEqual(len(datos["posiciones"]), 6)
        self.assertIn(str(self.salida), salida)

    def test_historial_limita_500_por_especie_y_no_se_reescribe(self):
        from cartera.dashboard import generar_html

        historial_csv = self.carpeta / "historial.csv"
        with historial_csv.open("w", encoding="utf-8", newline="") as archivo:
            escritor = csv.writer(archivo)
            escritor.writerow(["consultado_en", "ticker", "ultimo", "bid", "ask"])
            for indice in range(605):
                escritor.writerow([(T + dt.timedelta(seconds=indice)).isoformat(), "AAA", 1000 + indice, "", ""])
            for indice in range(7):
                escritor.writerow([(T + dt.timedelta(seconds=indice)).isoformat(), "BOND1", 150000 + indice, "", ""])
            escritor.writerow([T.isoformat(), "MEP", 1500, "", ""])
        antes = historial_csv.read_bytes()
        with patch("cartera.__main__.consultar_json", side_effect=self.fetch), patch(
            "cartera.dashboard_archivos.generar_html", wraps=generar_html
        ) as generar:
            codigo, _, errores = self.ejecutar()
        self.assertEqual(codigo, 0, errores)
        self.assertEqual(generar.call_count, 1)
        argumentos = inspect.signature(generar_html).bind(*generar.call_args.args, **generar.call_args.kwargs)
        historial = argumentos.arguments["historial"]
        self.assertEqual(len(historial["AAA"]), 500)
        self.assertEqual(historial["AAA"][0], (T + dt.timedelta(seconds=105), 1105.0))
        self.assertEqual(historial["AAA"][-1], (T + dt.timedelta(seconds=604), 1604.0))
        self.assertEqual(len(historial["BOND1"]), 7)
        self.assertEqual(historial_csv.read_bytes(), antes)
        posiciones = datos_de(self.salida.read_text(encoding="utf-8"))["posiciones"]
        self.assertNotIn("MEP", [p["ticker"] for p in posiciones])

    def test_error_al_reemplazar_html_conserva_version_y_permisos(self):
        self.previa()
        previo = self.salida.read_bytes()
        reemplazar = os.replace

        def fallar_solo_dashboard(origen, destino):
            if Path(destino).resolve() == self.salida.resolve():
                raise OSError("no se pudo reemplazar dashboard de prueba")
            return reemplazar(origen, destino)

        with patch("cartera.__main__.consultar_json", side_effect=self.fetch), patch(
            "cartera.dashboard_archivos.os.replace", side_effect=fallar_solo_dashboard
        ):
            codigo, _, errores = self.ejecutar()
        self.assertNotEqual(codigo, 0)
        self.assertIn("dashboard", errores.lower())
        self.assertNotIn("Traceback", errores)
        self.assertEqual(self.salida.read_bytes(), previo)
        self.assertEqual(stat.S_IMODE(self.salida.stat().st_mode), 0o600)
        self.assertEqual(list(self.carpeta.glob("*.tmp")), [])

    def test_reemplaza_salida_legible_por_otros_con_archivo_privado(self):
        self.previa()
        self.salida.chmod(0o644)
        with patch("cartera.__main__.consultar_json", side_effect=self.fetch):
            codigo, _, errores = self.ejecutar()
        self.assertEqual(codigo, 0, errores)
        self.assertEqual(stat.S_IMODE(self.salida.stat().st_mode) & 0o077, 0)
        self.assertNotEqual(self.salida.read_text(encoding="utf-8"), "Versión anterior ficticia")

    def test_salida_enlace_no_se_sigue_ni_se_consulta(self):
        victima = self.raiz / "otro_archivo_ficticio.html"
        victima.write_text("no modificar", encoding="utf-8")
        self.salida.symlink_to(victima)
        antes = self.archivos()
        with patch("cartera.__main__.consultar_json") as consultar:
            codigo, _, errores = self.ejecutar()
        self.assertNotEqual(codigo, 0)
        self.assertEqual(victima.read_text(encoding="utf-8"), "no modificar")
        self.assertEqual(self.archivos(), antes)
        consultar.assert_not_called()

    def test_falla_de_cache_no_puede_parecer_exito_silencioso(self):
        with patch("cartera.__main__.consultar_json", side_effect=self.fetch), patch(
            "cartera.dashboard_archivos.ClientePrecios.guardar_cache",
            side_effect=OSError("falló caché de prueba")
        ):
            codigo, salida, errores = self.ejecutar()
        self.assertIn("caché", salida + errores)
        self.assertIn("prueba", salida + errores)
        self.assertNotIn("Traceback", errores)
        if codigo == 0:
            self.assertTrue(self.salida.exists(), "Un éxito debe dejar el archivo generado.")


if __name__ == "__main__":
    unittest.main()
