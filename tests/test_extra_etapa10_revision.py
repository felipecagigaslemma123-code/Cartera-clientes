"""Revisión de la Etapa 10 con extractos reales: operaciones en dólares de la cuenta corriente."""

import datetime as dt
import unittest

from cartera.historial import clasificar, construir_historial
from test_etapa6_historial import compra, f

D1, D2 = dt.date(2026, 1, 10), dt.date(2026, 2, 10)


class OperacionesEnDolares(unittest.TestCase):
    def test_paridad_y_cable_son_compras_y_ventas(self):
        for comprobante, clase in {"COMPRA CABLE": "compra", "VENTA PARIDAD": "venta", "VENTA CABLE": "venta"}.items():
            self.assertEqual(clasificar(f(D1, comprobante, 1.0), []), clase, comprobante)

    def test_venta_paridad_consume_lotes_y_convierte_con_mep(self):
        venta = f(D2, "VENTA PARIDAD", 40.0, "AAA", -2, 2, moneda="USD", cuenta="DOLARES")
        h = construir_historial([compra(D1, "AAA", 2, 30000.0), venta], mep={D2: 1000.0})
        self.assertEqual(h.sin_clasificar, [])
        self.assertAlmostEqual(h.realizados[0].importe_ars, 40000.0)
        self.assertAlmostEqual(h.realizados[0].resultado_ars, 10000.0)
        self.assertEqual(h.lotes, [])


if __name__ == "__main__":
    unittest.main()
