"""Etapa 12: casos que aparecieron al probar el informe con carteras reales (16/11/2026)."""

import copy
import json
import unittest
from datetime import date
from decimal import Decimal
from pathlib import Path

from cartera.informe import _n, armar_informe, informe_html, leer_datos_dashboard

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "informe"


def cargar():
    datos = leer_datos_dashboard(FIXTURES / "dashboard.html")
    instrumentos = json.loads((FIXTURES / "instrumentos.json").read_text(encoding="utf-8"))
    return datos, instrumentos


class LetraAjustableEnLosDosBloques(unittest.TestCase):
    """Una LECER figura en `letras` (sin pago) y en el flujo (con pago proyectado): va una sola vez."""

    def test_gana_el_flujo(self):
        datos, instrumentos = cargar()
        datos["letras"]["posiciones"].append({"ticker": "TZV28", "moneda_pago": "ARS", "familia": "LECER",
                                              "vencimiento": "2028-06-30", "pago_vencimiento": None, "lotes": []})
        m = armar_informe(datos, instrumentos)
        self.assertEqual([r["ticker"] for r in m["rendimientos"]].count("TZV28"), 1)
        self.assertEqual([c["ticker"] for c in m["proximos_cobros"]].count("TZV28"), 1)
        self.assertEqual(m["a_cobrar"]["ARS"], Decimal("720000.00"))


class EfectivoSinDato(unittest.TestCase):
    def test_no_muestra_signo_de_moneda(self):
        datos, instrumentos = cargar()
        datos["integral"]["efectivo"] = {"ARS": None, "USD": None}
        h = informe_html(armar_informe(datos, instrumentos))
        self.assertNotIn("$ sin dato", h)
        self.assertNotIn("US$ sin dato", h)


class MuchasOperaciones(unittest.TestCase):
    def test_agrupa_por_mes(self):
        datos, instrumentos = cargar()
        datos["historial"]["realizados"] = [
            {"ticker": "T{}".format(i), "fecha": "2026-0{}-1{}".format(1 + i % 3, i % 9), "resultado_ars": 1000.0 * (i - 7)}
            for i in range(20)]
        h = informe_html(armar_informe(datos, instrumentos))
        grafico = h.split('aria-label="Resultados realizados"')[1].split("</svg>")[0]
        self.assertEqual(grafico.count("<rect"), 3)
        self.assertNotIn(">T1<", grafico)
        self.assertIn("20 operaciones, agrupadas por mes", h)

    def test_pocas_operaciones_van_una_por_una(self):
        datos, instrumentos = cargar()
        h = informe_html(armar_informe(datos, instrumentos))
        grafico = h.split('aria-label="Resultados realizados"')[1].split("</svg>")[0]
        self.assertEqual(grafico.count("<rect"), 2)
        self.assertIn(">TX26<", grafico)


class Redondeo(unittest.TestCase):
    def test_mitad_hacia_arriba(self):
        self.assertEqual(_n(Decimal("14.365"), 2), "14,37")
        self.assertEqual(_n(Decimal("2.5")), "3")
        self.assertEqual(_n(Decimal("-1234567.891"), 2), "-1.234.567,89")


if __name__ == "__main__":
    unittest.main()
