import copy
import datetime as dt
import unittest

from cartera.movimientos import ErrorMovimiento, aplicar_movimientos
from cartera.punto_partida import Lote


def lote(cantidad, costo, fecha, origen="extracto", ticker="AAA"):
    precio = None if costo is None else costo / cantidad
    return Lote(ticker=ticker, cantidad=cantidad, origen=origen, fecha=fecha, precio=precio, costo=costo, nota="")


def mov(fecha, tipo, cantidad=0, importe=0.0, ticker="AAA"):
    return {"fecha": fecha, "tipo": tipo, "ticker": ticker, "cantidad": cantidad, "importe": importe, "nota": ""}


VIEJO = dt.date(2026, 1, 1)
NUEVO = dt.date(2026, 2, 1)
D1 = dt.date(2026, 11, 10)
D2 = dt.date(2026, 11, 11)


class Movimientos(unittest.TestCase):
    def test_compra_agrega_un_lote_de_extracto(self):
        lotes, realizados = aplicar_movimientos([], [mov(D1, "compra", 10, 1000.0)])
        self.assertEqual(len(lotes), 1)
        self.assertEqual(lotes[0].origen, "extracto")
        self.assertEqual(lotes[0].cantidad, 10)
        self.assertAlmostEqual(lotes[0].costo, 1000.0)
        self.assertEqual(lotes[0].fecha, D1)
        self.assertEqual(realizados, [])

    def test_venta_consume_primero_el_lote_mas_viejo(self):
        lotes, _ = aplicar_movimientos(
            [lote(10, 2000.0, NUEVO), lote(10, 1000.0, VIEJO)],
            [mov(D1, "venta", 10, 3000.0)],
        )
        self.assertEqual(len(lotes), 1)
        self.assertEqual(lotes[0].fecha, NUEVO)

    def test_venta_parcial_prorratea_el_costo(self):
        lotes, realizados = aplicar_movimientos([lote(10, 1000.0, VIEJO)], [mov(D1, "venta", 4, 600.0)])
        self.assertEqual(lotes[0].cantidad, 6)
        self.assertAlmostEqual(lotes[0].costo, 600.0)
        self.assertAlmostEqual(realizados[0].costo, 400.0)
        self.assertAlmostEqual(realizados[0].resultado, 200.0)
        self.assertEqual(realizados[0].ticker, "AAA")

    def test_venta_que_cruza_dos_lotes(self):
        lotes, realizados = aplicar_movimientos(
            [lote(10, 1000.0, VIEJO), lote(10, 2000.0, NUEVO)],
            [mov(D1, "venta", 15, 3000.0)],
        )
        self.assertEqual(lotes[0].cantidad, 5)
        self.assertAlmostEqual(lotes[0].costo, 1000.0)
        self.assertEqual(len(realizados), 1)
        self.assertAlmostEqual(realizados[0].costo, 2000.0)
        self.assertAlmostEqual(realizados[0].resultado, 1000.0)

    def test_lote_sin_fecha_es_el_mas_viejo(self):
        lotes, _ = aplicar_movimientos(
            [lote(10, 1000.0, VIEJO), lote(10, None, None, origen="pendiente")],
            [mov(D1, "venta", 10, 3000.0)],
        )
        self.assertEqual(lotes[0].fecha, VIEJO)

    def test_venta_de_lote_pendiente_no_inventa_resultado(self):
        _, realizados = aplicar_movimientos(
            [lote(10, None, None, origen="pendiente")], [mov(D1, "venta", 4, 600.0)]
        )
        self.assertIsNone(realizados[0].costo)
        self.assertIsNone(realizados[0].resultado)

    def test_aplica_por_fecha_aunque_vengan_desordenados(self):
        lotes, _ = aplicar_movimientos(
            [], [mov(D2, "venta", 5, 800.0), mov(D1, "compra", 10, 1000.0)]
        )
        self.assertEqual(lotes[0].cantidad, 5)

    def test_vender_de_mas_es_error(self):
        with self.assertRaises(ErrorMovimiento):
            aplicar_movimientos([lote(10, 1000.0, VIEJO)], [mov(D1, "venta", 11, 1.0)])

    def test_otros_tipos_no_tocan_los_lotes(self):
        for tipo in ("renta", "dividendo", "deposito", "retiro"):
            lotes, realizados = aplicar_movimientos([lote(10, 1000.0, VIEJO)], [mov(D1, tipo, 0, 50.0)])
            self.assertEqual(lotes[0].cantidad, 10, tipo)
            self.assertEqual(realizados, [], tipo)

    def test_no_muta_los_lotes_recibidos(self):
        originales = [lote(10, 1000.0, VIEJO)]
        copia = copy.deepcopy(originales)
        aplicar_movimientos(originales, [mov(D1, "venta", 4, 600.0)])
        self.assertEqual(originales[0].cantidad, copia[0].cantidad)
        self.assertEqual(originales[0].costo, copia[0].costo)

    def test_lotes_de_otra_especie_no_se_consumen(self):
        lotes, _ = aplicar_movimientos(
            [lote(10, 1000.0, VIEJO, ticker="BBB"), lote(10, 2000.0, NUEVO)],
            [mov(D1, "venta", 10, 3000.0)],
        )
        self.assertEqual([l.ticker for l in lotes], ["BBB"])

    def test_compra_en_dolares_guarda_el_costo_en_pesos(self):
        movimiento = dict(mov(D1, "compra", 10, 100.0), moneda="USD", tc=1500.0)
        lotes, _ = aplicar_movimientos([], [movimiento])
        self.assertAlmostEqual(lotes[0].costo, 150000.0)
        self.assertIsNone(lotes[0].precio)

    def test_venta_en_dolares_informa_el_importe_en_pesos(self):
        movimiento = dict(mov(D1, "venta", 10, 100.0), moneda="USD", tc=1500.0)
        _, realizados = aplicar_movimientos([lote(10, 100000.0, VIEJO)], [movimiento])
        self.assertAlmostEqual(realizados[0].importe, 150000.0)
        self.assertAlmostEqual(realizados[0].resultado, 50000.0)

    def test_gasto_y_cambios_no_tocan_los_lotes(self):
        for tipo in ("gasto", "compra_usd", "venta_usd"):
            movimiento = dict(mov(D1, tipo, 0, 50.0, ticker=""), moneda="USD" if tipo != "gasto" else "ARS",
                              tc=1500.0 if tipo != "gasto" else None)
            lotes, realizados = aplicar_movimientos([lote(10, 1000.0, VIEJO)], [movimiento])
            self.assertEqual(lotes[0].cantidad, 10, tipo)
            self.assertEqual(realizados, [], tipo)

    def test_misma_fecha_respeta_el_orden_de_carga(self):
        lotes, _ = aplicar_movimientos(
            [lote(10, 1000.0, VIEJO)],
            [mov(D1, "venta", 10, 1500.0), mov(D1, "compra", 10, 1600.0)],
        )
        self.assertEqual(len(lotes), 1)
        self.assertAlmostEqual(lotes[0].costo, 1600.0)

    def test_venta_total_no_deja_un_lote_vacio(self):
        lotes, _ = aplicar_movimientos([lote(10, 1000.0, VIEJO)], [mov(D1, "venta", 10, 1500.0)])
        self.assertEqual(lotes, [])


class OrigenDelCosto(unittest.TestCase):
    def origen(self, lotes):
        cantidad = sum(l.cantidad for l in lotes)
        return aplicar_movimientos(lotes, [mov(D1, "venta", cantidad, 9000.0)])[1][0]

    def test_extracto(self):
        self.assertEqual(self.origen([lote(10, 1000.0, VIEJO)]).origen_costo, "extracto")

    def test_estimado(self):
        self.assertEqual(self.origen([lote(10, 1000.0, VIEJO, origen="estimado")]).origen_costo, "estimado")

    def test_mixto(self):
        realizado = self.origen([lote(10, 1000.0, VIEJO, origen="estimado"), lote(10, 2000.0, NUEVO)])
        self.assertEqual(realizado.origen_costo, "mixto")
        self.assertAlmostEqual(realizado.costo, 3000.0)

    def test_un_lote_pendiente_vuelve_incompleta_toda_la_venta(self):
        realizado = self.origen([lote(10, None, None, origen="pendiente"), lote(10, 2000.0, NUEVO)])
        self.assertEqual(realizado.origen_costo, "incompleto")
        self.assertIsNone(realizado.costo)
        self.assertIsNone(realizado.resultado)


if __name__ == "__main__":
    unittest.main()
