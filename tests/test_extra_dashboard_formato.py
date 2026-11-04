"""Fechas legibles y columna fija del dashboard."""

import datetime as dt
import unittest
from pathlib import Path
from zoneinfo import ZoneInfo

from cartera.calculos import resultado_posicion, resumen_cartera
from cartera.dashboard import generar_html
from cartera.precios import Cotizacion
from cartera.punto_partida import cargar_punto_partida

DEMO = Path(__file__).resolve().parents[1] / "fixtures" / "punto_partida_demo.xlsx"
T = dt.datetime(2026, 11, 4, 15, 42, 51, tzinfo=ZoneInfo("America/Argentina/Buenos_Aires"))


def generar(instrumentos, generado_en=T):
    punto = cargar_punto_partida(DEMO)
    resultados = [resultado_posicion(p, [l for l in punto.lotes if l.ticker == p.ticker], 1000.0)
                  for p in punto.posiciones]
    cotizaciones = {p.ticker: Cotizacion(ticker=p.ticker, ultimo=1000.0, bid=999.0, ask=1001.0, pct_dia=0.0,
                                         estado="vivo", consultado_en=generado_en)
                    for p in punto.posiciones}
    return generar_html(
        cliente={"slug": "demo", "nombre": "Demo"}, resultados=resultados, resumen=resumen_cartera(resultados),
        cotizaciones=cotizaciones, niveles={}, instrumentos=instrumentos,
        efectivo={"fecha": "2026-11-04", "ARS": 1.0, "USD": 0.0}, historial={}, generado_en=generado_en,
        posiciones=punto.posiciones)


class Formato(unittest.TestCase):
    def test_muestra_fecha_y_hora_legibles(self):
        html = generar({})
        self.assertIn("Generado: 04/11/2026 15:42", html)
        self.assertIn("consulta 04/11/2026 15:42", html)

    def test_usa_hora_de_argentina_aunque_venga_en_otra_zona(self):
        html = generar({}, T.astimezone(dt.timezone.utc))
        self.assertIn("Generado: 04/11/2026 15:42", html)

    def test_vencimiento_con_fecha_argentina_y_plural(self):
        html = generar({"AAA": {"vencimiento": "2026-11-05"}, "BBB": {"vencimiento": "2026-11-22"},
                        "CCC": {"vencimiento": "2026-11-03"}})
        self.assertIn("AAA · 05/11/2026 · falta 1 día", html)
        self.assertIn("BBB · 22/11/2026 · faltan 18 días", html)
        self.assertIn("CCC · 03/11/2026 · vencida hace 1 día", html)

    def test_los_datos_embebidos_conservan_el_formato_iso(self):
        self.assertIn('"vencimiento": "2026-11-22"', generar({"BBB": {"vencimiento": "2026-11-22"}}))

    def test_la_primera_columna_queda_fija(self):
        html = generar({})
        self.assertIn('class="tabla-posiciones"', html)
        self.assertIn(".tabla-posiciones td:first-child", html)
        self.assertIn("position:sticky;left:0", html)


if __name__ == "__main__":
    unittest.main()
