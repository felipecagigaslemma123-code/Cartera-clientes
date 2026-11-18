"""Informe 1.1: resultado acumulado como suma de resultados (docs/INFORME.md, sección 8). Datos ficticios."""

import copy
import json
import unittest
from decimal import Decimal
from pathlib import Path

from cartera.informe import armar_informe, informe_html, leer_datos_dashboard

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "informe"
D = Decimal


def cargar():
    datos = leer_datos_dashboard(FIXTURES / "dashboard.html")
    instrumentos = json.loads((FIXTURES / "instrumentos.json").read_text(encoding="utf-8"))
    return datos, instrumentos


def nota_de_resultados(html):
    return html.split("Resultado de cada venta o vencimiento")[1].split("</p>")[0]


class TenenciaAnteriorAlPrimerExtracto(unittest.TestCase):
    """El caso que motivó el cambio: una tenencia previa entra sin aporte registrado."""

    def datos(self):
        datos, instrumentos = cargar()
        # Tenía un título comprado antes del primer extracto, con costo de entrada 100 y valor actual 150.
        # Aportó 1.000 en efectivo, compró otro título por 1.000 y lo vendió en 1.200. Hoy tiene 1.200 en efectivo.
        datos["posiciones"] = [{"ticker": "PREV", "tipo": "cedear", "cantidad": 1.0, "ultimo": 150.0,
                                "valuacion": 150.0, "costo": 100.0, "resultado": 50.0}]
        datos["integral"].update(patrimonio_final=1350.0, valuacion_final=150.0, efectivo={"ARS": 1200.0, "USD": 0.0})
        historial = datos["historial"]
        historial.update(total_conocido=200.0, realizado_extracto=200.0,
                         aportes={"ARS": 1000.0, "USD": 0.0, "equivalente_ars": 1000.0},
                         retiros={"ARS": 0.0, "USD": 0.0, "equivalente_ars": 0.0},
                         realizados=[{"ticker": "OTRO", "fecha": "2026-05-04", "resultado_ars": 200.0, "clase": "venta"}])
        for bloque in historial["ingresos"].values():
            bloque.update(ARS=0.0, USD=0.0, equivalente_ars=0.0)
        return datos, instrumentos

    def test_no_cuenta_la_tenencia_previa_como_ganancia(self):
        datos, instrumentos = self.datos()
        r = armar_informe(datos, instrumentos)["resultados"]
        # Patrimonio 1.350 − capital puesto (100 en títulos + 1.000 en efectivo) = 250. Antes daba 350.
        self.assertEqual(r["acumulado"], D("250"))
        self.assertEqual((r["tenencia"], r["desde_dia_cero"]), (D("50"), D("0")))

    def test_no_depende_del_patrimonio_ni_de_los_aportes(self):
        datos, instrumentos = self.datos()
        datos["integral"]["patrimonio_final"] = None
        datos["historial"]["aportes"]["equivalente_ars"] = 999999.0
        self.assertEqual(armar_informe(datos, instrumentos)["resultados"]["acumulado"], D("250"))

    def test_la_nota_lo_explica_con_palabras(self):
        datos, instrumentos = self.datos()
        nota = nota_de_resultados(informe_html(armar_informe(datos, instrumentos)))
        self.assertIn("la ganancia realizada más una ganancia de $\u00a050 en lo que hoy está en cartera", nota)
        self.assertIn("No incluye la variación del dólar sobre el efectivo", nota)
        self.assertNotIn("aportes", nota)


class SinDato(unittest.TestCase):
    def test_posicion_sin_resultado(self):
        datos, instrumentos = cargar()
        datos["posiciones"][0]["resultado"] = None
        m = armar_informe(datos, instrumentos)
        self.assertIsNone(m["resultados"]["acumulado"])
        self.assertIsNone(m["resultados"]["tenencia"])
        h = informe_html(m)
        self.assertIn("Resultado acumulado: sin dato; falta el costo o el precio de AL30.", nota_de_resultados(h))

    def test_historial_incompleto(self):
        datos, instrumentos = cargar()
        datos["historial"]["ventas_sin_dato"] = 1
        r = armar_informe(datos, instrumentos)["resultados"]
        self.assertIsNone(r["acumulado"])
        self.assertEqual(r["incompletos"], 1)
        self.assertEqual(r["faltantes"], ["1 operación del historial sin resultado"])
        h = informe_html(armar_informe(datos, instrumentos))
        self.assertIn("suma lo conocido · 1 sin dato", h)
        self.assertIn("$ 300.000", h)

    def test_sin_ganancia_realizada(self):
        datos, instrumentos = cargar()
        datos["historial"]["total_conocido"] = None
        self.assertIsNone(armar_informe(datos, instrumentos)["resultados"]["acumulado"])

    def test_escapa_el_ticker_del_motivo(self):
        datos, instrumentos = cargar()
        datos["posiciones"][0].update(ticker="<X&Y>", resultado=None)
        h = informe_html(armar_informe(datos, instrumentos))
        self.assertIn("falta el costo o el precio de &lt;X&amp;Y&gt;.", h)


class DesdeElDiaCero(unittest.TestCase):
    def test_suma_ventas_y_cobros_registrados(self):
        datos, instrumentos = cargar()
        datos["realizados"] = [{"ticker": "SPY", "fecha": "2026-11-20", "cantidad": 1.0, "importe": 17000.0,
                                "costo": 10000.0, "resultado": 7000.0, "origen_costo": "extracto"}]
        datos["integral"].update(rentas=3000.0, dividendos=500.0, amortizaciones=1000.0, gastos=200.0)
        r = armar_informe(datos, instrumentos)["resultados"]
        self.assertEqual(r["desde_dia_cero"], D("11300"))
        self.assertEqual(r["acumulado"], D("300000") + D("11300") + D("95000"))
        nota = nota_de_resultados(informe_html(armar_informe(datos, instrumentos)))
        self.assertIn("y una ganancia de $\u00a011.300 en ventas y cobros desde el día cero", nota)

    def test_venta_sin_costo(self):
        datos, instrumentos = cargar()
        datos["realizados"] = [{"ticker": "SPY", "fecha": "2026-11-20", "resultado": None}]
        r = armar_informe(datos, instrumentos)["resultados"]
        self.assertIsNone(r["acumulado"])
        self.assertEqual(r["faltantes"], ["el costo de 1 venta desde el día cero"])

    def test_perdida_en_palabras(self):
        datos, instrumentos = cargar()
        for posicion in datos["posiciones"]:
            posicion["resultado"] = -1000.0
        nota = nota_de_resultados(informe_html(armar_informe(datos, instrumentos)))
        self.assertIn("una pérdida de $\u00a05.000 en lo que hoy está en cartera", nota)
        self.assertNotIn("$\u00a0-", nota)
        self.assertNotIn("$ ", nota, "en la nota el signo pesos no se separa del número")


if __name__ == "__main__":
    unittest.main()
