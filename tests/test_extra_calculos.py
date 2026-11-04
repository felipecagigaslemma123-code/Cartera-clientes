"""Casos de cálculo que complementan la aceptación de la primera etapa."""

import datetime as dt
import unittest

from cartera.calculos import (
    costo_total,
    estado_costo,
    resultado_posicion,
    resumen_cartera,
    valuacion,
)
from cartera.punto_partida import Lote, Posicion


def lote(origen="extracto", costo=1000.0, cantidad=10):
    return Lote(
        ticker="AAA", cantidad=cantidad, origen=origen,
        fecha=dt.date(2026, 1, 1), precio=None, costo=costo, nota="",
    )


class CalculosAdicionales(unittest.TestCase):
    def test_costo_se_conserva_si_no_hay_precio(self):
        r = resultado_posicion(Posicion("AAA", "Demo", "cedear", 10, 1), [lote()], None, 100)
        self.assertEqual(r.costo, 1000)
        self.assertEqual(r.estado_costo, "extracto")
        for campo in ("valuacion", "resultado", "resultado_pct", "resultado_dia_cero", "resultado_dia_cero_pct"):
            self.assertIsNone(getattr(r, campo), campo)

    def test_resultado_negativo_y_estimado_por_cada_cien(self):
        r = resultado_posicion(
            Posicion("AAA", "Demo", "bono", 1000, 100),
            [lote(origen="estimado", costo=1200, cantidad=1000)], 100, 110,
        )
        self.assertEqual(r.valuacion, 1000)
        self.assertEqual(r.resultado, -200)
        self.assertAlmostEqual(r.resultado_pct, -1 / 6)
        self.assertEqual(r.resultado_dia_cero, -100)
        self.assertAlmostEqual(r.resultado_dia_cero_pct, -1 / 11)
        self.assertEqual(r.estado_costo, "estimado")

    def test_costo_incompleto_no_produce_total_parcial(self):
        lotes = [lote(), lote(origen="pendiente", costo=None)]
        self.assertEqual(estado_costo(lotes), "incompleto")
        self.assertIsNone(costo_total(lotes))

    def test_sin_lotes_no_inventa_costo_cero(self):
        self.assertEqual(estado_costo([]), "incompleto")
        self.assertIsNone(costo_total([]))

    def test_generadores_de_lotes_no_pierden_el_costo(self):
        self.assertEqual(costo_total(iter([lote(), lote(costo=2000)])), 3000)

    def test_suma_no_redondea_cada_lote(self):
        self.assertAlmostEqual(costo_total([lote(costo=0.004)] * 3), 0.012)

    def test_resumen_total_conocido_y_comparables_no_confunden_faltantes(self):
        posicion = Posicion("AAA", "Demo", "cedear", 10, 1)
        sin_precio = resultado_posicion(posicion, [lote(origen="pendiente", costo=None)], None)
        sin_costo = resultado_posicion(posicion, [lote(origen="pendiente", costo=None)], 150)
        sin_precio.ticker = "SIN_PRECIO"
        sin_costo.ticker = "SIN_COSTO"
        estimado = resultado_posicion(posicion, [lote(origen="estimado")], 120)
        resumen = resumen_cartera(iter([sin_precio, sin_costo, estimado]))
        self.assertEqual(resumen.valuacion_total, 2700)
        self.assertEqual(resumen.valuacion_comparable, 1200)
        self.assertEqual(resumen.costo_comparable, 1000)
        self.assertEqual(resumen.resultado_comparable, 200)
        self.assertEqual(resumen.posiciones_sin_costo, ["SIN_PRECIO", "SIN_COSTO"])
        self.assertEqual(resumen.posiciones_sin_precio, ["SIN_PRECIO"])

    def test_valores_no_finitos_booleanos_y_precio_cero_son_invalidos(self):
        for precio in (float("inf"), float("nan"), True, 0, -1):
            with self.subTest(precio=precio), self.assertRaises(ValueError):
                valuacion(10, precio, 1)
        with self.assertRaises(ValueError):
            valuacion(10, 100, 0)
        with self.assertRaises(ValueError):
            valuacion(10, 100, 10)
        with self.assertRaises(ValueError):
            valuacion(1e308, 1e308, 1)

    def test_precio_base_invalido_no_produce_porcentajes(self):
        with self.assertRaises(ValueError):
            resultado_posicion(Posicion("AAA", "Demo", "cedear", 10, 1), [lote()], 120, 0)


if __name__ == "__main__":
    unittest.main()
