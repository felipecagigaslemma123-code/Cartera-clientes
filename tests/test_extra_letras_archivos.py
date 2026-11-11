"""Precios de compra y dashboard integrado, con datos ficticios y red reemplazada."""

import copy
import io
import json
import os
import re
import stat
import tempfile
import unittest
from contextlib import redirect_stdout, redirect_stderr
from datetime import date, datetime, timedelta
from pathlib import Path
from unittest.mock import patch
from zoneinfo import ZoneInfo

from cartera.__main__ import main
from cartera.almacenamiento import importar_cartera
from cartera.letras import ErrorLetra, referencias_compras
from cartera.letras_archivos import guardar_compra, leer_compras
from cartera.precios import ClientePrecios

DEMO = Path(__file__).resolve().parents[1] / "fixtures" / "punto_partida_demo.xlsx"


class PreciosLetrasArchivos(unittest.TestCase):
    def setUp(self):
        self.temporal = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporal.cleanup)
        self.datos = Path(self.temporal.name)
        self.base, _ = importar_cartera(self.datos, "demo", DEMO)
        self.carpeta = self.datos / "clientes" / "demo"
        self.compra = referencias_compras(self.base, [])[0]
        self.ruta = self.carpeta / "compras_letras.json"
        instante = datetime.now(ZoneInfo("America/Argentina/Buenos_Aires"))
        self.hoy = instante.date()
        reloj = patch("cartera.dashboard_archivos.ClientePrecios", side_effect=lambda fetch, ruta, persistir_cache:
                      ClientePrecios(fetch, ruta, ahora=lambda: instante, persistir_cache=persistir_cache))
        reloj.start()
        self.addCleanup(reloj.stop)
        self.instrumentos = {self.compra["ticker"]: {
            "vencimiento": (self.hoy + timedelta(days=90)).isoformat(),
            "letra": {"familia": "LECAP", "moneda_pago": "ARS", "fecha_emision": "2025-01-01",
                      "tem_emision": "0.02", "base_nominal": "100", "fuente": "Contrato ficticio"}}}
        (self.carpeta / "instrumentos.json").write_text(json.dumps(self.instrumentos))

    def ejecutar(self, argumentos):
        salida, errores = io.StringIO(), io.StringIO()
        with redirect_stdout(salida), redirect_stderr(errores):
            codigo = main(["--datos", str(self.datos)] + argumentos)
        return codigo, salida.getvalue(), errores.getvalue()

    def argumentos(self, **cambios):
        campos = {"referencia": self.compra["referencia"], "precio": "110.25", "moneda": "ARS", "liquidacion": self.hoy.isoformat()}
        campos.update(cambios)
        return ["precio-letra", "--cliente", "demo"] + [valor for campo, dato in campos.items() for valor in ("--" + campo, dato)]

    def archivos(self):
        return {str(p.relative_to(self.carpeta)): p.read_bytes() for p in self.carpeta.rglob("*") if p.is_file()}

    def test_listar_referencias_no_modifica_archivos_ni_consulta_red(self):
        antes = self.archivos()
        with patch("cartera.__main__.consultar_json") as fetch:
            codigo, salida, error = self.ejecutar(["letras", "--cliente", "demo"])
        self.assertEqual((codigo, error), (0, ""))
        self.assertIn(self.compra["referencia"], salida)
        self.assertIn("sin dato", salida)
        self.assertEqual(self.archivos(), antes)
        fetch.assert_not_called()

    def test_guardar_y_corregir_precio_no_modifica_base(self):
        antes = self.archivos()
        for precio in ("110.25", "111.75"):
            with patch("cartera.__main__.consultar_json") as fetch:
                codigo, salida, error = self.ejecutar(self.argumentos(precio=precio))
            self.assertEqual((codigo, error), (0, ""))
            self.assertIn("guardado", salida)
            self.assertEqual(leer_compras(self.ruta)["compras"][0]["precio"], precio)
            self.assertEqual(leer_compras(self.ruta)["compras"][0]["huella"], self.compra["huella"])
            fetch.assert_not_called()
        self.assertEqual(stat.S_IMODE(self.ruta.stat().st_mode), 0o600)
        self.assertTrue(all((self.carpeta / ruta).read_bytes() == datos for ruta, datos in antes.items()))

    def test_mismo_precio_no_escribe(self):
        self.assertEqual(self.ejecutar(self.argumentos())[0], 0)
        antes, instante = self.archivos(), self.ruta.stat().st_mtime_ns
        codigo, salida, error = self.ejecutar(self.argumentos())
        self.assertEqual((codigo, error), (0, ""))
        self.assertIn("Sin cambios", salida)
        self.assertEqual(self.archivos(), antes)
        self.assertEqual(self.ruta.stat().st_mtime_ns, instante)

    def test_validacion_rechaza_sin_escribir(self):
        for cambios in ({"precio": "NaN"}, {"precio": "0"}, {"precio": "1.234,56"},
                        {"referencia": "base:999"}, {"liquidacion": "1900-01-01"},
                        {"liquidacion": (self.hoy + timedelta(days=1)).isoformat()}):
            with self.subTest(cambios=cambios):
                antes = self.archivos()
                codigo, _, error = self.ejecutar(self.argumentos(**cambios))
                self.assertEqual(codigo, 1)
                self.assertTrue(error)
                self.assertNotIn("Traceback", error)
                self.assertEqual(self.archivos(), antes)

    def test_liquidacion_desde_vencimiento_se_rechaza(self):
        self.instrumentos[self.compra["ticker"]]["vencimiento"] = self.hoy.isoformat()
        (self.carpeta / "instrumentos.json").write_text(json.dumps(self.instrumentos))
        antes = self.archivos()
        codigo, _, error = self.ejecutar(self.argumentos())
        self.assertEqual(codigo, 1)
        self.assertIn("anterior al vencimiento", error)
        self.assertEqual(self.archivos(), antes)

    def test_base_inexistente(self):
        codigo, _, error = self.ejecutar(["letras", "--cliente", "ausente"])
        self.assertEqual(codigo, 1)
        self.assertIn("No existe", error)
        self.assertFalse((self.datos / "clientes" / "ausente").exists())

    def test_json_corrupto_o_enlace_no_se_pisa(self):
        self.ruta.write_text("{roto")
        antes = self.ruta.read_bytes()
        self.assertEqual(self.ejecutar(self.argumentos())[0], 1)
        self.assertEqual(self.ruta.read_bytes(), antes)
        self.ruta.unlink()
        destino = self.datos / "ajeno.json"
        destino.write_text("privado ficticio")
        self.ruta.symlink_to(destino)
        self.assertEqual(self.ejecutar(self.argumentos())[0], 1)
        self.assertEqual(destino.read_text(), "privado ficticio")

    def test_falla_publicacion_conserva_version_y_limpia_temporal(self):
        self.assertEqual(self.ejecutar(self.argumentos())[0], 0)
        antes = self.archivos()
        with patch("cartera.letras_archivos.os.replace", side_effect=OSError("falla ficticia")):
            codigo, _, error = self.ejecutar(self.argumentos(precio="112"))
        self.assertEqual(codigo, 1)
        self.assertIn("falla ficticia", error)
        self.assertEqual(self.archivos(), antes)

    def test_archivo_con_clave_repetida_se_rechaza(self):
        self.ruta.write_text('{"esquema_version":1,"compras":[],"compras":[]}')
        with self.assertRaisesRegex(ErrorLetra, "repetida"):
            leer_compras(self.ruta)

    def fetch(self, url):
        if url.endswith("/mep"):
            return [{"ticker": "AL30", "mark": 1500}]
        return [{"symbol": posicion.ticker, "c": 120} for posicion in self.base.posiciones]

    def test_dashboard_integra_precio_sin_alterar_resultado_completo(self):
        with patch("cartera.__main__.consultar_json", side_effect=self.fetch):
            codigo, _, error = self.ejecutar(["dashboard", "--cliente", "demo"])
        self.assertEqual((codigo, error), (0, ""))
        def datos():
            html = (self.carpeta / "dashboard.html").read_text()
            return json.loads(re.search(r'<script id="datos-cartera" type="application/json">(.*?)</script>', html, re.S).group(1))
        antes = datos()
        self.assertEqual(self.ejecutar(self.argumentos())[0], 0)
        with patch("cartera.__main__.consultar_json", side_effect=self.fetch):
            codigo, _, error = self.ejecutar(["dashboard", "--cliente", "demo"])
        self.assertEqual((codigo, error), (0, ""))
        despues = datos()
        self.assertEqual(antes["integral"], despues["integral"])
        self.assertEqual(antes["posiciones"], despues["posiciones"])
        self.assertIsNotNone(despues["letras"]["posiciones"][0]["pago_vencimiento"])
        self.assertEqual(despues["letras"]["posiciones"][0]["lotes"][0]["precio"], "110.25")

    def test_dashboard_archivo_de_precios_invalido_informa_sin_usarlo(self):
        self.ruta.write_text('{"esquema_version": 99, "compras": []}')
        with patch("cartera.__main__.consultar_json", side_effect=self.fetch):
            codigo, salida, error = self.ejecutar(["dashboard", "--cliente", "demo"])
        self.assertEqual((codigo, error), (0, ""))
        self.assertIn("No se pudieron leer", salida)
        html = (self.carpeta / "dashboard.html").read_text()
        self.assertIn("No se pudieron leer", html)
        self.assertEqual(self.ruta.read_text(), '{"esquema_version": 99, "compras": []}')


if __name__ == "__main__":
    unittest.main()
