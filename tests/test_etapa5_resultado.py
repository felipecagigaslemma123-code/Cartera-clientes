import datetime as dt
import unittest

from cartera.movimientos import (
    ErrorMovimiento, cartera_actual, conciliar_efectivo, flujos, resultado_integral,
    saldos_efectivo, validar_movimientos,
)
from cartera.punto_partida import Lote, Posicion, PuntoPartida


def mov(fecha, tipo, importe, ticker="", cantidad=0, moneda="ARS", tc=None, tipo_activo=""):
    return {"fecha": fecha, "tipo": tipo, "ticker": ticker, "cantidad": cantidad, "importe": importe,
            "moneda": moneda, "tc": tc, "tipo_activo": tipo_activo, "nota": ""}


CERO = dt.date(2026, 10, 1)
D = dt.date(2026, 10, 10)
HOY = dt.date(2026, 10, 20)
BASE = [Posicion("AAA", "Demo A", "cedear", 100.0, 1), Posicion("BOND1", "Bono", "bono", 1000.0, 100)]
LOTES = [Lote("AAA", 100.0, "extracto", dt.date(2026, 1, 1), None, 100000.0, ""),
         Lote("BOND1", 1000.0, "estimado", dt.date(2026, 1, 1), 1400.0, 1400000.0, "")]
PUNTO = PuntoPartida(BASE, LOTES)
DIA_CERO = {
    "esquema_version": 2, "fecha": "2026-10-01", "fijado_en": "2026-10-01T17:05:00-03:00",
    "cantidades": {"AAA": 100.0, "BOND1": 1000.0}, "precios": {"AAA": 1000.0, "BOND1": 150000.0},
    "mep": 1500.0, "efectivo": {"fecha": "2026-10-01", "ARS": 10000.0, "USD": 10.0},
}
# Las cuentas de este ejemplo están hechas a mano:
# inicial: 100.000 + 1.500.000 + 10.000 + 15.000 = 1.625.000
# ARS: 10.000 + 50.000 - 12.000 + 800.000 + 5.000 - 300 - 20.000 - 155.000 = 677.700
# USD: 10 + 100 + 2 + 100 = 212
# final con AAA 1.300, BOND1 160.000 y MEP 1.600:
# 143.000 + 800.000 + 677.700 + 339.200 = 1.959.900
# total: 1.959.900 - 1.625.000 - 200.000 + 20.000 = 154.900
MOVIMIENTOS = [
    mov(D, "deposito", 50000.0),
    mov(D, "deposito", 100.0, moneda="USD", tc=1500.0),
    mov(D, "compra", 12000.0, "AAA", 10.0),
    mov(D, "venta", 800000.0, "BOND1", 500.0),
    mov(D, "renta", 5000.0, "BOND1"),
    mov(D, "dividendo", 2.0, "AAA", moneda="USD", tc=1500.0),
    mov(D, "gasto", 300.0),
    mov(D, "retiro", 20000.0),
    mov(D, "compra_usd", 100.0, moneda="USD", tc=1550.0),
]
PRECIOS = {"AAA": 1300.0, "BOND1": 160000.0}


def integral(movimientos=MOVIMIENTOS, dia_cero=DIA_CERO, precios=PRECIOS, mep=1600.0):
    actual, _ = cartera_actual(PUNTO, movimientos)
    return resultado_integral(BASE, dia_cero, actual.posiciones, movimientos, precios, mep)


class ResultadoIntegral(unittest.TestCase):
    def test_ejemplo_completo(self):
        r = integral()
        self.assertAlmostEqual(r.patrimonio_inicial, 1625000.0)
        self.assertAlmostEqual(r.valuacion_final, 943000.0)
        self.assertAlmostEqual(r.efectivo_ars, 677700.0)
        self.assertAlmostEqual(r.efectivo_usd, 212.0)
        self.assertAlmostEqual(r.patrimonio_final, 1959900.0)
        self.assertAlmostEqual(r.total, 154900.0)
        self.assertEqual(r.faltantes, [])

    def test_desglose_en_pesos(self):
        f = integral().flujos
        self.assertAlmostEqual(f.aportes, 200000.0)
        self.assertAlmostEqual(f.retiros, 20000.0)
        self.assertAlmostEqual(f.rentas, 5000.0)
        self.assertAlmostEqual(f.dividendos, 3000.0)
        self.assertAlmostEqual(f.gastos, 300.0)

    def base_sin_cambios(self, movimientos):
        return integral(movimientos, precios={"AAA": 1000.0, "BOND1": 150000.0}, mep=1500.0).total

    def test_sin_movimientos_ni_cambios_da_cero(self):
        self.assertAlmostEqual(self.base_sin_cambios([]), 0.0)

    def test_deposito_y_retiro_no_son_ganancia(self):
        self.assertAlmostEqual(self.base_sin_cambios([mov(D, "deposito", 5000.0), mov(D, "retiro", 2000.0)]), 0.0)

    def test_deposito_en_dolares_usa_su_tipo_de_cambio(self):
        self.assertAlmostEqual(self.base_sin_cambios([mov(D, "deposito", 100.0, moneda="USD", tc=1500.0)]), 0.0)

    def test_compra_y_venta_a_valor_de_mercado_no_son_ganancia(self):
        self.assertAlmostEqual(self.base_sin_cambios([mov(D, "compra", 10000.0, "AAA", 10.0)]), 0.0)
        self.assertAlmostEqual(self.base_sin_cambios([mov(D, "venta", 10000.0, "AAA", 10.0)]), 0.0)

    def test_renta_y_gasto_se_cuentan_una_sola_vez(self):
        self.assertAlmostEqual(self.base_sin_cambios([mov(D, "renta", 700.0, "BOND1")]), 700.0)
        self.assertAlmostEqual(self.base_sin_cambios([mov(D, "gasto", 300.0)]), -300.0)

    def test_comprar_dolares_al_mep_no_es_ganancia(self):
        self.assertAlmostEqual(self.base_sin_cambios([mov(D, "compra_usd", 10.0, moneda="USD", tc=1500.0)]), 0.0)
        self.assertAlmostEqual(self.base_sin_cambios([mov(D, "venta_usd", 10.0, moneda="USD", tc=1500.0)]), 0.0)

    def test_el_costo_no_interviene(self):
        otros = PuntoPartida(BASE, [Lote("AAA", 100.0, "extracto", dt.date(2026, 1, 1), None, 1.0, ""), LOTES[1]])
        actual, _ = cartera_actual(otros, MOVIMIENTOS)
        r = resultado_integral(BASE, DIA_CERO, actual.posiciones, MOVIMIENTOS, PRECIOS, 1600.0)
        self.assertAlmostEqual(r.total, 154900.0)


class SinDato(unittest.TestCase):
    def assertSinDato(self, resultado, texto):
        self.assertIsNone(resultado.total)
        self.assertTrue(any(texto in faltante for faltante in resultado.faltantes), resultado.faltantes)

    def test_sin_dia_cero(self):
        self.assertSinDato(integral(dia_cero=None), "día cero")

    def test_sin_efectivo_inicial_no_se_asume_cero(self):
        cero = dict(DIA_CERO, efectivo={"fecha": None, "ARS": None, "USD": 10.0})
        r = integral(dia_cero=cero)
        self.assertSinDato(r, "efectivo ARS")
        self.assertIsNone(r.efectivo_ars)

    def test_sin_precio_de_una_posicion_actual(self):
        self.assertSinDato(integral(precios={"AAA": 1300.0, "BOND1": None}), "BOND1")

    def test_sin_mep_con_dolares(self):
        self.assertSinDato(integral(mep=None), "MEP")

    def test_sin_dolares_no_hace_falta_el_mep(self):
        cero = dict(DIA_CERO, efectivo={"fecha": "2026-10-01", "ARS": 10000.0, "USD": 0.0})
        r = integral([], dia_cero=cero, mep=None, precios={"AAA": 1000.0, "BOND1": 150000.0})
        self.assertAlmostEqual(r.total, 0.0)

    def test_no_necesita_precio_de_lo_vendido(self):
        movimientos = [mov(D, "venta", 1500000.0, "BOND1", 1000.0)]
        r = integral(movimientos, precios={"AAA": 1000.0}, mep=1500.0)
        self.assertAlmostEqual(r.total, 0.0)


class Efectivo(unittest.TestCase):
    INICIAL = {"ARS": 10000.0, "USD": 10.0}

    def test_saldos_por_moneda(self):
        saldos = saldos_efectivo(self.INICIAL, MOVIMIENTOS)
        self.assertAlmostEqual(saldos["ARS"], 677700.0)
        self.assertAlmostEqual(saldos["USD"], 212.0)

    def test_hasta_una_fecha(self):
        saldos = saldos_efectivo(self.INICIAL, [mov(D, "deposito", 5.0), mov(HOY, "deposito", 7.0)], hasta=D)
        self.assertAlmostEqual(saldos["ARS"], 10005.0)

    def test_puede_ser_negativo(self):
        self.assertAlmostEqual(saldos_efectivo(self.INICIAL, [mov(D, "retiro", 20000.0)])["ARS"], -10000.0)

    def test_inicial_nulo_sigue_sin_dato(self):
        saldos = saldos_efectivo({"ARS": None, "USD": 1.0}, [mov(D, "deposito", 5.0)])
        self.assertIsNone(saldos["ARS"])

    def test_flujos_sin_movimientos(self):
        self.assertEqual(flujos([]).aportes, 0)


class Conciliacion(unittest.TestCase):
    MOV = [mov(D, "deposito", 5000.0)]

    def conciliar(self, fecha="2026-10-15", ars=15000.0, usd=10.0, movimientos=None):
        return conciliar_efectivo(DIA_CERO, self.MOV if movimientos is None else movimientos,
                                  {"fecha": fecha, "ARS": ars, "USD": usd})

    def test_concilia(self):
        self.assertEqual(self.conciliar().estado, "concilia")

    def test_dentro_de_la_tolerancia(self):
        self.assertEqual(self.conciliar(ars=15000.99, usd=10.01).estado, "concilia")

    def test_no_concilia_e_informa_la_diferencia(self):
        c = self.conciliar(ars=14000.0)
        self.assertEqual(c.estado, "no_concilia")
        self.assertAlmostEqual(c.diferencias["ARS"], -1000.0)

    def test_compara_contra_el_saldo_de_su_fecha(self):
        movimientos = self.MOV + [mov(dt.date(2026, 10, 18), "retiro", 3000.0)]
        self.assertEqual(self.conciliar(movimientos=movimientos).estado, "concilia")

    def test_sin_fecha_no_hay_control(self):
        self.assertEqual(self.conciliar(fecha=None).estado, "sin_control")

    def test_fecha_anterior_al_dia_cero_no_hay_control(self):
        self.assertEqual(self.conciliar(fecha="2026-09-01").estado, "sin_control")

    def test_sin_saldos_no_hay_control(self):
        self.assertEqual(self.conciliar(ars=None, usd=None).estado, "sin_control")

    def test_compara_solo_la_moneda_disponible(self):
        c = self.conciliar(usd=None)
        self.assertEqual(c.estado, "concilia")
        self.assertEqual(set(c.diferencias), {"ARS"})

    def test_sin_dia_cero_no_hay_control(self):
        c = conciliar_efectivo(None, [], {"fecha": "2026-10-15", "ARS": 1.0, "USD": 1.0})
        self.assertEqual(c.estado, "sin_control")


class CarteraActual(unittest.TestCase):
    def test_actualiza_cantidades_sin_tocar_la_base(self):
        actual, _ = cartera_actual(PUNTO, MOVIMIENTOS)
        cantidades = {p.ticker: p.cantidad for p in actual.posiciones}
        self.assertEqual(cantidades, {"AAA": 110.0, "BOND1": 500.0})
        self.assertEqual(BASE[0].cantidad, 100.0)
        self.assertEqual(len(PUNTO.lotes), 2)

    def test_venta_total_quita_la_posicion(self):
        actual, realizados = cartera_actual(PUNTO, [mov(D, "venta", 200000.0, "AAA", 100.0)])
        self.assertEqual([p.ticker for p in actual.posiciones], ["BOND1"])
        self.assertAlmostEqual(realizados[0].resultado, 100000.0)

    def test_especie_nueva_toma_la_unidad_de_su_tipo(self):
        actual, _ = cartera_actual(PUNTO, [mov(D, "compra", 150000.0, "ONY", 100.0, tipo_activo="on")])
        nueva = next(p for p in actual.posiciones if p.ticker == "ONY")
        self.assertEqual((nueva.tipo, nueva.cotiza_cada, nueva.especie), ("on", 100, "ONY"))

    def test_recompra_de_lo_vendido_conserva_el_tipo(self):
        movimientos = [mov(D, "venta", 1.0, "BOND1", 1000.0), mov(HOY, "compra", 2.0, "BOND1", 5.0)]
        actual, _ = cartera_actual(PUNTO, movimientos)
        self.assertEqual(next(p for p in actual.posiciones if p.ticker == "BOND1").cotiza_cada, 100)


class Validacion(unittest.TestCase):
    def rechaza(self, *movimientos):
        with self.assertRaises(ErrorMovimiento):
            validar_movimientos(PUNTO, list(movimientos), CERO, HOY)

    def test_acepta_el_ejemplo(self):
        validar_movimientos(PUNTO, MOVIMIENTOS, CERO, HOY)

    def test_fecha_igual_o_anterior_al_dia_cero(self):
        self.rechaza(mov(CERO, "deposito", 1.0))

    def test_fecha_futura(self):
        self.rechaza(mov(HOY + dt.timedelta(days=1), "deposito", 1.0))

    def test_hoy_se_acepta(self):
        validar_movimientos(PUNTO, [mov(HOY, "deposito", 1.0)], CERO, HOY)

    def test_tipo_desconocido(self):
        self.rechaza(mov(D, "regalo", 1.0))

    def test_importe_no_positivo(self):
        self.rechaza(mov(D, "deposito", 0.0))
        self.rechaza(mov(D, "deposito", -5.0))
        self.rechaza(mov(D, "deposito", float("nan")))

    def test_compra_sin_cantidad_o_sin_especie(self):
        self.rechaza(mov(D, "compra", 1.0, "AAA", 0))
        self.rechaza(mov(D, "compra", 1.0, "", 5.0))

    def test_cantidad_donde_no_aplica(self):
        self.rechaza(mov(D, "renta", 1.0, "AAA", 5.0))

    def test_especie_donde_no_aplica(self):
        self.rechaza(mov(D, "deposito", 1.0, "AAA"))

    def test_especie_nueva_sin_tipo_de_activo(self):
        self.rechaza(mov(D, "compra", 1.0, "ONY", 1.0))

    def test_tipo_de_activo_invalido_o_distinto(self):
        self.rechaza(mov(D, "compra", 1.0, "ONY", 1.0, tipo_activo="fondo"))
        self.rechaza(mov(D, "compra", 1.0, "AAA", 1.0, tipo_activo="bono"))

    def test_renta_de_especie_desconocida(self):
        self.rechaza(mov(D, "renta", 1.0, "ZZZ"))

    def test_dolares_sin_tipo_de_cambio(self):
        self.rechaza(mov(D, "deposito", 1.0, moneda="USD"))

    def test_pesos_con_tipo_de_cambio(self):
        self.rechaza(mov(D, "deposito", 1.0, tc=1500.0))

    def test_cambio_debe_ser_en_dolares(self):
        self.rechaza(mov(D, "compra_usd", 1.0))

    def test_moneda_desconocida(self):
        self.rechaza(mov(D, "deposito", 1.0, moneda="EUR", tc=1.0))

    def test_vender_de_mas(self):
        self.rechaza(mov(D, "venta", 1.0, "AAA", 101.0))

    def test_informa_todos_los_problemas(self):
        with self.assertRaises(ErrorMovimiento) as error:
            validar_movimientos(PUNTO, [mov(CERO, "deposito", 1.0), mov(D, "regalo", 1.0)], CERO, HOY)
        self.assertIn("1", str(error.exception))
        self.assertIn("2", str(error.exception))


if __name__ == "__main__":
    unittest.main()
