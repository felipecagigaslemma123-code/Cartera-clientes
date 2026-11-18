"""Etapa 13: qué parte de lo que se cobra devuelve lo invertido y qué parte es ganancia."""

import json
import re
import unittest
from datetime import date
from decimal import Decimal
from pathlib import Path

from cartera.flujo_fondos import Pago, _separar_capital
from cartera.informe import armar_informe, informe_html, leer_datos_dashboard

D = Decimal
FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "informe"


def separar(seleccion, pagos, liquidacion, precio, nominales=D(1000)):
    fila = {"pagos": [{} for _ in pagos]}
    _separar_capital(fila, seleccion, pagos, liquidacion, precio * nominales / 100, nominales)
    return fila


class Separacion(unittest.TestCase):
    # Bono con cupón semestral de 5 por 100 VN y dos amortizaciones de 50.
    PAGOS = [Pago(date(2027, 1, 1), D(0), D(5), "iamc"), Pago(date(2027, 7, 1), D(50), D(5), "iamc"),
             Pago(date(2028, 1, 1), D(50), D(2.5), "iamc")]
    ANTERIOR = date(2026, 7, 1)

    def test_bajo_la_par_con_intereses_corridos(self):
        seleccion = {self.ANTERIOR: None, **{p.fecha: p for p in self.PAGOS}}
        liquidacion = date(2026, 10, 1)  # 92 de 184 días del cupón: 2,5 de corrido
        fila = separar(seleccion, self.PAGOS, liquidacion, D(92.5))
        corrido = D(5) * 92 / 184 * 10
        self.assertEqual(D(fila["intereses_corridos"]), corrido)
        self.assertEqual(D(fila["ganancia_precio"]), D(1000) - (D(925) - corrido))
        self.assertEqual(D(fila["intereses"]), D(125) - corrido)
        self.assertNotIn("intereses_corridos_estimados", fila)
        capital = [D(p["capital"]) for p in fila["pagos"]]
        self.assertEqual(sum(capital), D(925))  # vuelve exactamente lo invertido
        self.assertEqual(capital[0], corrido)  # el primer cupón devuelve solo el corrido
        self.assertEqual(capital[1], capital[2])  # el resto, en proporción a lo que amortiza
        total = D(1125)
        self.assertEqual(sum(D(p["ganancia"]) for p in fila["pagos"]), total - D(925))

    def test_sobre_la_par_la_ganancia_por_precio_es_negativa(self):
        seleccion = {self.ANTERIOR: None, **{p.fecha: p for p in self.PAGOS}}
        fila = separar(seleccion, self.PAGOS, self.ANTERIOR, D(104))
        self.assertEqual(D(fila["intereses_corridos"]), 0)
        self.assertEqual(D(fila["ganancia_precio"]), D(-40))
        self.assertEqual(D(fila["intereses"]), D(125))

    def test_inicio_del_cupon_estimado_con_el_periodo_siguiente(self):
        seleccion = {p.fecha: p for p in self.PAGOS}
        fila = separar(seleccion, self.PAGOS, date(2026, 10, 2), D(92.5))
        # 2027-01-01 menos el período siguiente (181 días) = 2026-07-04; 90 días transcurridos.
        self.assertEqual(D(fila["intereses_corridos"]), D(5) * 90 / 181 * 10)
        self.assertTrue(fila["intereses_corridos_estimados"])

    def test_cero_cupon(self):
        pagos = [Pago(date(2027, 6, 30), D(180), D(0), "estimado · REM 2026-10")]
        fila = separar({pagos[0].fecha: pagos[0]}, pagos, date(2026, 8, 7), D(127))
        self.assertEqual(D(fila["intereses_corridos"]), 0)
        self.assertEqual(D(fila["ganancia_precio"]), D(1800) - D(1270))
        self.assertEqual(D(fila["intereses"]), 0)
        self.assertEqual(D(fila["pagos"][0]["capital"]), D(1270))

    def test_sin_amortizacion_no_se_separa(self):
        pagos = [Pago(date(2027, 1, 1), D(0), D(5), "iamc")]
        fila = separar({self.ANTERIOR: None, pagos[0].fecha: pagos[0]}, pagos, date(2026, 10, 1), D(90))
        self.assertIn("motivo_capital", fila)
        self.assertNotIn("capital", fila["pagos"][0])

    def test_sin_pago_anterior_ni_siguiente(self):
        pagos = [Pago(date(2027, 1, 1), D(100), D(5), "iamc")]
        fila = separar({pagos[0].fecha: pagos[0]}, pagos, date(2026, 10, 1), D(98))
        self.assertIn("inicio del cupón", fila["motivo_capital"])


class Informe(unittest.TestCase):
    def setUp(self):
        datos = leer_datos_dashboard(FIXTURES / "dashboard.html")
        self.instrumentos = json.loads((FIXTURES / "instrumentos.json").read_text(encoding="utf-8"))
        self.datos = datos
        self.m = armar_informe(datos, self.instrumentos)

    def test_por_titulo(self):
        r = {x["ticker"]: x for x in self.m["rendimientos"]}
        self.assertEqual((r["AL30"]["capital"], r["AL30"]["ganancia"]), (D("80.00"), D("9.00")))
        self.assertEqual((r["S30N6"]["capital"], r["S30N6"]["ganancia"]), (D(610000), D("40000.00")))
        self.assertEqual((r["TZV28"]["capital"], r["TZV28"]["ganancia"]), (None, None))

    def test_por_moneda_sin_mezclar_y_sin_inventar(self):
        self.assertEqual(self.m["a_cobrar_capital"], {"USD MEP": D("80.00"), "USD cable": D("0.00"), "ARS": None})

    def test_proximos_cobros(self):
        capital = {(c["ticker"], c["fecha"]): c["capital"] for c in self.m["proximos_cobros"]}
        self.assertEqual(capital[("AL30", date(2027, 1, 9))], D(40))
        self.assertEqual(capital[("S30N6", date(2026, 11, 30))], D(610000))
        self.assertIsNone(capital[("TZV28", date(2028, 6, 30))])

    def test_html(self):
        h = informe_html(self.m)
        self.assertIn("US$ 80,00 devuelve lo invertido · <b>US$ 9,00</b> de ganancia", h)
        self.assertIn("Devuelve lo invertido", h)
        self.assertIn("Vencimiento ($ 40.000 de ganancia)", h)
        self.assertIn("Renta y amortización (US$ 5,00 de ganancia)", h)
        self.assertNotIn("Renta · US$", h)  # una renta sola no se detalla
        self.assertEqual(h.count('class="parte"'), 2)  # el total en pesos no tiene separación

    def test_cobros_por_anio(self):
        self.assertEqual(self.m["cobros_por_anio_capital"], {
            "2026": {"ARS": D(610000)}, "2027": {"USD MEP": D(80), "USD cable": D("0.00")}, "2028": {"ARS": None}})

    def test_barra_anual_con_capital_abajo_y_ganancia_arriba(self):
        h = informe_html(self.m)
        grafico = h.split('aria-label="Cobros en dólares por año"')[1].split("</svg>")[0]
        rects = re.findall(r'<rect x="[\d.]+" y="([\d.]+)" width="[\d.]+" height="([\d.]+)"[^>]*fill="(#[0-9a-f]+)"', grafico)
        # Dólar MEP 2027: US$ 89, de los cuales US$ 80 devuelven lo invertido.
        verde, azul = rects[0], rects[1]
        self.assertEqual((verde[2], azul[2]), ("#3d8b8b", "#1f3a5f"))
        self.assertAlmostEqual(float(azul[1]) / float(verde[1]), 80 / 89, places=2)
        self.assertIn(">Ganancia</span>", h)

    def test_sin_separacion_la_barra_es_de_un_solo_color(self):
        self.m["cobros_por_anio_capital"] = {}
        h = informe_html(self.m)
        grafico = h.split('aria-label="Cobros en dólares por año"')[1].split("</svg>")[0]
        self.assertNotIn("#3d8b8b", grafico)
        self.assertNotIn(">Ganancia</span>", h)

    def test_una_compra_sin_separacion_deja_sin_dato_la_posicion(self):
        self.datos["flujo_fondos"]["posiciones"][0]["compras"][1]["pagos"][0].pop("capital")
        m = armar_informe(self.datos, self.instrumentos)
        capital = {(c["ticker"], c["fecha"]): c["capital"] for c in m["proximos_cobros"]}
        self.assertIsNone(capital[("AL30", date(2027, 1, 9))])


if __name__ == "__main__":
    unittest.main()
