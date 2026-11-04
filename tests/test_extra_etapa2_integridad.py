"""Guardados, avisos y transporte público de la segunda etapa."""

import contextlib
import datetime as dt
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from zoneinfo import ZoneInfo

from cartera.__main__ import main
from cartera.almacenamiento import importar_cartera
from cartera.precios import Cotizacion, fijar_dia_cero
from cartera.transporte import consultar_json


DEMO = Path(__file__).resolve().parents[1] / "fixtures" / "punto_partida_demo.xlsx"
AHORA = dt.datetime.now(ZoneInfo("America/Argentina/Buenos_Aires"))


class IntegridadComandos(unittest.TestCase):
    def setUp(self):
        self.temporal = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporal.cleanup)
        self.datos = Path(self.temporal.name) / "datos"
        self.punto, _ = importar_cartera(self.datos, "demo", DEMO)
        self.carpeta = self.datos / "clientes" / "demo"

    def ejecutar(self, *argumentos):
        salida, errores = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(salida), contextlib.redirect_stderr(errores):
            codigo = main(["--datos", str(self.datos), *argumentos, "--cliente", "demo"])
        return codigo, salida.getvalue(), errores.getvalue()

    def fetch(self, url):
        if url.endswith("/mep"):
            return [{"ticker": "AL30", "mark": 1500}]
        return [{"symbol": p.ticker, "c": 1200, "px_bid": 1190, "px_ask": 1210}
                for p in self.punto.posiciones]

    def archivos(self):
        return {str(p.relative_to(self.carpeta)): p.read_bytes() for p in self.carpeta.rglob("*") if p.is_file()}

    def test_captura_informa_historial_guardado_si_falla_la_cache(self):
        with patch("cartera.__main__.consultar_json", side_effect=self.fetch), patch(
            "cartera.precios.os.replace", side_effect=OSError("caché no disponible")
        ):
            codigo, salida, errores = self.ejecutar("capturar")
        self.assertNotEqual(codigo, 0)
        self.assertIn("7 filas", salida)
        self.assertIn("historial guardó 7 filas", errores)
        self.assertIn("caché", errores)
        self.assertTrue((self.carpeta / "historial.csv").exists())

    def test_fijacion_incompleta_no_actualiza_cache_ni_guarda_dia_cero(self):
        previo = self.archivos()
        def parcial(url):
            return [{"symbol": "AAA", "c": 1200}] if url.endswith("arg_cedears") else []
        with patch("cartera.__main__.consultar_json", side_effect=parcial):
            codigo, _, errores = self.ejecutar("fijar-dia-cero")
        self.assertNotEqual(codigo, 0)
        self.assertIn("viva", errores)
        self.assertEqual(self.archivos(), previo)

    def test_cache_falla_despues_de_fijar_avisa_foto_guardada(self):
        # Fijar día cero usa os.link; esta falla afecta solo la publicación de caché.
        with patch("cartera.__main__.consultar_json", side_effect=self.fetch), patch(
            "cartera.precios.os.replace", side_effect=OSError("caché no disponible")
        ):
            codigo, salida, errores = self.ejecutar("fijar-dia-cero")
        self.assertEqual(codigo, 0)
        self.assertIn("Día cero fijado", salida)
        self.assertIn("el día cero se guardó", errores)
        self.assertTrue((self.carpeta / "dia_cero.json").exists())

    def test_efectivo_que_desborda_patrimonio_no_modifica_foto(self):
        cotizaciones = {p.ticker: Cotizacion(p.ticker, 1, 1, 1, 0, "vivo", AHORA) for p in self.punto.posiciones}
        ruta = self.carpeta / "dia_cero.json"
        fijar_dia_cero(self.punto.posiciones, cotizaciones, ruta, AHORA.date(), mep=1e308)
        previo = self.archivos()
        with patch("cartera.__main__.consultar_json") as fetch:
            codigo, salida, errores = self.ejecutar("efectivo-dia-cero", "--ars", "0", "--usd", "2")
        self.assertNotEqual(codigo, 0)
        self.assertIn("rango", errores)
        self.assertEqual(self.archivos(), previo)
        fetch.assert_not_called()

    def test_fecha_pasada_advierte_que_precio_no_es_historico(self):
        ayer = (AHORA.date() - dt.timedelta(days=1)).isoformat()
        with patch("cartera.__main__.consultar_json", side_effect=self.fetch):
            codigo, salida, errores = self.ejecutar("fijar-dia-cero", "--fecha", ayer)
        self.assertEqual(codigo, 0, errores)
        self.assertIn("no cotizaciones históricas", salida)


class TransportePublico(unittest.TestCase):
    def test_consulta_tiene_timeout_y_encabezados_genericos(self):
        with patch("cartera.transporte.urlopen", return_value=io.BytesIO(b"[]")) as abrir:
            self.assertEqual(consultar_json("https://data912.com/live/arg_bonds"), [])
        solicitud = abrir.call_args.args[0]
        self.assertEqual(abrir.call_args.kwargs["timeout"], 10)
        self.assertEqual(solicitud.get_header("User-agent"), "cartera/0.2")
        self.assertEqual(solicitud.get_header("Accept"), "application/json")

    def test_json_no_finito_o_invalido_es_un_error(self):
        for cuerpo in (b"[NaN]", b"[Infinity]", b"{roto"):
            with self.subTest(cuerpo=cuerpo), patch("cartera.transporte.urlopen", return_value=io.BytesIO(cuerpo)):
                with self.assertRaises(ValueError):
                    consultar_json("https://data912.com/live/arg_bonds")

    def test_respuesta_demasiado_grande_se_rechaza(self):
        cuerpo = b" " * (5 * 1024 * 1024 + 1)
        with patch("cartera.transporte.urlopen", return_value=io.BytesIO(cuerpo)):
            with self.assertRaises(ValueError):
                consultar_json("https://data912.com/live/arg_bonds")


if __name__ == "__main__":
    unittest.main()
