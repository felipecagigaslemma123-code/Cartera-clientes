import datetime as dt
import re
import unittest
from pathlib import Path
from zoneinfo import ZoneInfo

from cartera.calculos import resultado_posicion, resumen_cartera
from cartera.dashboard import generar_html
from cartera.precios import Cotizacion
from cartera.punto_partida import cargar_punto_partida

DEMO = Path(__file__).resolve().parents[1] / "fixtures" / "punto_partida_demo.xlsx"
T = dt.datetime(2026, 11, 4, 12, 0, tzinfo=ZoneInfo("America/Argentina/Buenos_Aires"))
PRECIOS = {"AAA": 1200.0, "BBB": 1100.0, "CCC": 2500.0, "BOND1": 160000.0, "NOTE1": 110.0}


class Dashboard(unittest.TestCase):
    def setUp(self):
        punto = cargar_punto_partida(DEMO)
        self.resultados = [
            resultado_posicion(p, [l for l in punto.lotes if l.ticker == p.ticker], PRECIOS.get(p.ticker))
            for p in punto.posiciones
        ]
        self.cotizaciones = {
            ticker: Cotizacion(ticker=ticker, ultimo=precio, bid=precio, ask=precio, pct_dia=1.5, estado="vivo", consultado_en=T)
            for ticker, precio in PRECIOS.items()
        }
        self.cotizaciones["ONX"] = Cotizacion(ticker="ONX", ultimo=None, bid=None, ask=None, pct_dia=None, estado="sin_dato", consultado_en=T)
        self.html = self.generar()

    def generar(self, nombre="Cliente Demo"):
        return generar_html(
            cliente={"slug": "demo", "nombre": nombre},
            resultados=self.resultados,
            resumen=resumen_cartera(self.resultados),
            cotizaciones=self.cotizaciones,
            niveles={"AAA": {"take_profit": 1500.0, "stop_loss": 900.0}},
            instrumentos={"BOND1": {"vencimiento": "2026-11-22"}},
            efectivo={"fecha": "2026-11-04", "ARS": 1000.0, "USD": 10.0, "nota": ""},
            historial={},
            generado_en=T,
        )

    def test_muestra_todas_las_posiciones(self):
        for ticker in ("AAA", "BBB", "CCC", "BOND1", "NOTE1", "ONX"):
            self.assertIn(ticker, self.html)

    def test_es_autocontenido(self):
        externos = re.findall(r'<(?:script|link|img)[^>]+(?:src|href)=["\']?https?:', self.html, flags=re.I)
        self.assertEqual(externos, [])
        self.assertNotIn("@import", self.html)
        self.assertNotIn("fonts.googleapis", self.html)

    def test_consulta_precios_de_data912(self):
        self.assertIn("data912.com/live/", self.html)

    def test_distingue_faltantes_y_estimados(self):
        minusculas = self.html.lower()
        self.assertIn("falta estimar", minusculas)
        self.assertIn("estimado", minusculas)
        self.assertIn("sin dato", minusculas)

    def test_muestra_efectivo_aparte(self):
        self.assertIn("efectivo", self.html.lower())

    def test_muestra_la_hora_de_consulta_sin_llamarla_ultimo_precio(self):
        minusculas = self.html.lower()
        self.assertIn("consulta", minusculas)
        self.assertNotIn("hora del último precio", minusculas)

    def test_escapa_los_textos(self):
        html = self.generar(nombre="<b>A&B</b>")
        self.assertNotIn("<b>A&B</b>", html)


if __name__ == "__main__":
    unittest.main()
