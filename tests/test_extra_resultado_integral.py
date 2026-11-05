"""Casos adicionales de efectivo y resultado, exclusivamente ficticios."""

import copy
import datetime as dt
import unittest

from cartera.movimientos import (
    ErrorMovimiento, conciliar_efectivo, resultado_integral, saldos_efectivo,
)
from cartera.punto_partida import Posicion


D = dt.date(2026, 10, 2)
BASE = [Posicion("DEMO", "Demo", "cedear", 10.0, 1)]
CERO = {
    "esquema_version": 2, "fecha": "2026-10-01", "fijado_en": "2026-10-01T17:00:00-03:00",
    "cantidades": {"DEMO": 10.0}, "precios": {"DEMO": 100.0}, "mep": 1000.0,
    "efectivo": {"fecha": "2026-10-01", "ARS": 1000.0, "USD": 0.0},
}


def mov(tipo, importe, moneda="ARS", tc=None, **campos):
    movimiento = {"fecha": D, "tipo": tipo, "importe": importe, "moneda": moneda,
                  "tc": tc, "ticker": "", "cantidad": 0, "tipo_activo": "", "nota": ""}
    movimiento.update(campos)
    return movimiento


class ResultadoAdicional(unittest.TestCase):
    def test_vender_todo_conserva_el_patrimonio_inicial_y_no_necesita_precios(self):
        movimientos = [mov("venta", 1200, ticker="DEMO", cantidad=10)]
        resultado = resultado_integral(BASE, CERO, [], movimientos, {}, None)
        self.assertEqual(resultado.patrimonio_inicial, 2000)
        self.assertEqual(resultado.valuacion_final, 0)
        self.assertEqual(resultado.patrimonio_final, 2200)
        self.assertEqual(resultado.total, 200)

    def test_faltantes_del_precio_actual_no_quedan_fijos(self):
        resultado = resultado_integral(BASE, CERO, BASE, [], {"DEMO": None}, None)
        self.assertIsNone(resultado.total)
        self.assertIsNone(resultado.valuacion_final)
        self.assertEqual(resultado.faltantes_fijos, [])
        self.assertTrue(any("DEMO" in dato for dato in resultado.faltantes))

    def test_mep_inicial_faltante_no_se_resuelve_con_mep_actual(self):
        cero = copy.deepcopy(CERO)
        cero["mep"] = None
        cero["efectivo"]["USD"] = 1
        resultado = resultado_integral(BASE, cero, BASE, [], {"DEMO": 100}, 1000)
        self.assertIsNone(resultado.total)
        self.assertEqual(resultado.patrimonio_final, 3000)
        self.assertTrue(any("MEP" in dato for dato in resultado.faltantes_fijos))

    def test_saldo_usd_negativo_tambien_necesita_mep_actual(self):
        resultado = resultado_integral(BASE, CERO, BASE, [mov("retiro", 1, "USD", 1000)],
                                      {"DEMO": 100}, None)
        self.assertEqual(resultado.efectivo_usd, -1)
        self.assertIsNone(resultado.total)
        self.assertEqual(resultado.faltantes_fijos, [])
        self.assertTrue(any("MEP" in dato for dato in resultado.faltantes))

    def test_compras_y_ventas_en_dolares_afectan_solo_su_moneda(self):
        saldos = saldos_efectivo({"ARS": 7, "USD": 10}, [
            mov("compra", 3, "USD", 1000, ticker="DEMO", cantidad=1),
            mov("venta", 2, "USD", 1000, ticker="DEMO", cantidad=1),
        ])
        self.assertEqual(saldos, {"ARS": 7, "USD": 9})

    def test_cambio_de_moneda_con_saldo_inicial_nulo_no_lo_completa(self):
        saldos = saldos_efectivo({"ARS": None, "USD": 2}, [mov("compra_usd", 3, "USD", 1000)])
        self.assertEqual(saldos, {"ARS": None, "USD": 5})

    def test_conciliacion_puede_hacerse_el_dia_cero(self):
        control = {"fecha": "2026-10-01", "ARS": 1001, "USD": 0.01}
        self.assertEqual(conciliar_efectivo(CERO, [mov("deposito", 10)], control).estado, "concilia")

    def test_superar_la_tolerancia_no_concilia(self):
        control = {"fecha": "2026-10-01", "ARS": 1001.0001, "USD": 0}
        self.assertEqual(conciliar_efectivo(CERO, [], control).estado, "no_concilia")

    def test_no_modifica_entradas(self):
        movimientos = [mov("deposito", 5)]
        cero_original = copy.deepcopy(CERO)
        movimientos_originales = copy.deepcopy(movimientos)
        resultado_integral(BASE, CERO, BASE, movimientos, {"DEMO": 100}, 1000)
        conciliar_efectivo(CERO, movimientos, {"fecha": "2026-10-02", "ARS": 1005, "USD": 0})
        self.assertEqual(CERO, cero_original)
        self.assertEqual(movimientos, movimientos_originales)

    def test_desbordamiento_no_publica_un_infinito(self):
        with self.assertRaises(ErrorMovimiento):
            saldos_efectivo({"ARS": 1e308, "USD": 0}, [mov("deposito", 1e308)])


if __name__ == "__main__":
    unittest.main()
