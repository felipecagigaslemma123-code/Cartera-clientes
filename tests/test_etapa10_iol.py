"""Extractos de InvertirOnline: lectura del HTML y tratamiento en el historial."""

import datetime as dt
import tempfile
import unittest
from pathlib import Path

from cartera.historial import ErrorHistorial, clasificar, construir_historial, leer_extracto_iol

ENCABEZADO_IOL = ["Nro. de Mov.", "Nro. de Boleto", "Tipo Mov.", "Concert.", "Liquid.", "Est", "Cant. titulos", "Precio",
                  "Comis.", "Iva Com.", "Otros Imp.", "Monto", "Observaciones", "Tipo Cuenta"]
D1, D2, D3 = dt.date(2026, 1, 10), dt.date(2026, 2, 10), dt.date(2026, 3, 10)
F1, F2, F3 = "10/01/26", "10/02/26", "10/03/26"
DEPOSITO = "Depósito de Fondos - Transferencia electrónica - BANCO DEMO S.A."
EXTRACCION = "Extracción de Fondos - Transferencia Electrónica - Billetera Demo"


def mov(numero, tipo, fecha, monto, cantidad="0", cuenta="Pesos", estado="Terminada", precio="0", boleto="0"):
    return [str(numero), boleto, tipo, fecha, fecha, estado, str(cantidad), precio, "0,00", "0,00", "0,00", monto, "",
            "Inversion Argentina " + cuenta]


def _celda(texto):
    return texto.encode("ascii", "xmlcharrefreplace").decode("ascii")


def escribir_iol(ruta, filas, encabezado=None):
    """Imita el archivo real: HTML con entidades, celdas con <span> y una fila suelta antes de la tabla."""
    partes = ['\r\n<link href="/Content/Estilos" rel="stylesheet"/>\r\n<html>\r\n<head>\r\n'
              '<title>Operaciones Finalizadas</title>\r\n</head>\r\n<body>\r\n    <tr>\r\n'
              '        <td colspan="15">Operaciones Historicas del periodo 1/1/2026 hasta 31/3/2026</td>\r\n    </tr>\r\n'
              '<table border="1" cellpadding="0" cellspacing="0">\r\n    <tr>\r\n']
    for titulo in encabezado or ENCABEZADO_IOL:
        partes.append('        <th style="width: 60px;">' + _celda(titulo) + '</th>\r\n')
    partes.append('    </tr>\r\n')
    for fila in filas:
        partes.append('            <tr>\r\n')
        for indice, valor in enumerate(fila):
            interior = ('\r\n                        <span>' + _celda(valor) + '</span>\r\n                '
                        if indice in (4, 8, 9, 10, 11) else _celda(valor))
            partes.append('                <td style="width: 60px;">' + interior + '</td>\r\n')
        partes.append('            </tr>\r\n')
    partes.append('</table>\r\n</body>\r\n</html>')
    Path(ruta).write_bytes("".join(partes).encode("ascii"))


class Base(unittest.TestCase):
    def setUp(self):
        temporal = tempfile.TemporaryDirectory()
        self.addCleanup(temporal.cleanup)
        self.dir = Path(temporal.name)

    def leer(self, filas, encabezado=None, nombre="mov.xls"):
        ruta = self.dir / nombre
        escribir_iol(ruta, filas, encabezado)
        return leer_extracto_iol(ruta)

    def historial(self, filas, mep=None):
        return construir_historial(self.leer(filas), mep=mep)


class Lectura(Base):
    def test_compra_en_pesos(self):
        filas = self.leer([mov(195751555, "Compra(AAA)", F1, "-413.228,38", 305, precio="1354,13", boleto="77")])
        self.assertEqual(len(filas), 1)
        fila = filas[0]
        self.assertEqual(set(fila), {"moneda", "cuenta", "operado", "comprobante", "numero", "cantidad", "especie", "importe",
                                     "saldo", "referencia", "archivo", "fila"})
        self.assertEqual((fila["moneda"], fila["cuenta"], fila["operado"]), ("ARS", "PESOS", D1))
        self.assertEqual((fila["comprobante"], fila["numero"], fila["especie"]), ("IOL COMPRA", 195751555, "AAA"))
        self.assertEqual(fila["cantidad"], 305)
        self.assertAlmostEqual(fila["importe"], -413228.38)
        self.assertIsNone(fila["saldo"])
        self.assertEqual(fila["referencia"], "Compra(AAA)")
        self.assertEqual(fila["archivo"], "mov.xls")

    def test_venta_con_cantidad_negativa(self):
        fila = self.leer([mov(2, "Venta(AAA)", F1, "15.411,67", 1)])[0]
        self.assertEqual((fila["comprobante"], fila["cantidad"]), ("IOL VENTA", -1))
        self.assertAlmostEqual(fila["importe"], 15411.67)

    def test_operacion_en_dolares_cuenta_la_cantidad_una_vez(self):
        filas = self.leer([mov(7, "Compra(AAAD)", F1, "-49,33", 385, precio="84,85"),
                           mov(7, "Compra(AAAD)", F1, "-329,94", 385, "Dolares", precio="84,85")])
        por = {fila["comprobante"]: fila for fila in filas}
        self.assertEqual(set(por), {"IOL COMPRA", "IOL IMPUESTO"})
        self.assertEqual((por["IOL COMPRA"]["moneda"], por["IOL COMPRA"]["cuenta"]), ("USD", "DOLARES"))
        self.assertEqual((por["IOL COMPRA"]["especie"], por["IOL COMPRA"]["cantidad"]), ("AAA", 385))
        self.assertAlmostEqual(por["IOL COMPRA"]["importe"], -329.94)
        self.assertEqual((por["IOL IMPUESTO"]["moneda"], por["IOL IMPUESTO"]["especie"]), ("ARS", "AAA"))
        self.assertEqual(por["IOL IMPUESTO"]["cantidad"], 0)
        self.assertAlmostEqual(por["IOL IMPUESTO"]["importe"], -49.33)

    def test_la_d_final_solo_se_quita_en_dolares(self):
        fila = self.leer([mov(3, "Compra(YPFD)", F1, "-1.000,00", 1)])[0]
        self.assertEqual(fila["especie"], "YPFD")

    def test_renta_en_dolares_y_su_gasto_en_pesos(self):
        filas = self.leer([mov(10, "Pago de Renta(BOND1)", F1, "-30,05"),
                           mov(11, "Pago de Renta(BOND1 US$)", F1, "12,84", cuenta="Dolares")])
        por = {fila["comprobante"]: fila for fila in filas}
        self.assertEqual((por["IOL RENTA"]["moneda"], por["IOL RENTA"]["especie"]), ("USD", "BOND1"))
        self.assertAlmostEqual(por["IOL RENTA"]["importe"], 12.84)
        self.assertEqual(por["IOL GASTO DE COBRO"]["especie"], "BOND1")
        self.assertAlmostEqual(por["IOL GASTO DE COBRO"]["importe"], -30.05)

    def test_dividendo_y_su_gasto(self):
        filas = self.leer([mov(12, "Pago de Dividendos(AAA)", F1, "-1,69"),
                           mov(13, "Pago de Dividendos(AAA US$)", F1, "0,15", cuenta="Dolares"),
                           mov(14, "Pago de Dividendos(BBB)", F1, "7.313,45")])
        self.assertEqual(sorted(fila["comprobante"] for fila in filas), ["IOL DIVIDENDO", "IOL DIVIDENDO", "IOL GASTO DE COBRO"])

    def test_amortizacion_en_dos_filas(self):
        filas = self.leer([mov(20, "Pago de Amortización(ON1 US$)", F1, "325,00", cuenta="Dolares"),
                           mov(21, "Pago de Amortización(ON1)", F1, "0,00", -325)])
        self.assertEqual({fila["comprobante"] for fila in filas}, {"IOL AMORTIZACION"})
        self.assertEqual({fila["especie"] for fila in filas}, {"ON1"})
        self.assertEqual(sorted(fila["cantidad"] for fila in filas), [-325, 0])

    def test_fondos_fci_caucion_y_credito(self):
        filas = self.leer([mov(30, DEPOSITO, F1, "800.000,00"), mov(31, EXTRACCION, F1, "-9.847,11"),
                           mov(32, "Suscripción FCI(FONDO)", F1, "-1.001,75", 19), mov(33, "Rescate FCI(FONDO)", F2, "1.034,01", 19),
                           mov(34, "Caución(Caución en Pesos Arg.)", F1, "-2.645.366,00", 2645366),
                           mov(34, "Liquidación de Caución", F3, "2.649.214,72", 2649736), mov(35, "Crédito", F1, "0,04", cuenta="Dolares")])
        self.assertEqual([fila["comprobante"] for fila in sorted(filas, key=lambda f: (f["numero"], f["operado"]))],
                         ["IOL DEPOSITO", "IOL EXTRACCION", "IOL SUSCRIPCION FCI", "IOL RESCATE FCI", "IOL CAUCION",
                          "IOL LIQUIDACION CAUCION", "IOL CREDITO"])
        deposito = next(fila for fila in filas if fila["comprobante"] == "IOL DEPOSITO")
        self.assertEqual(deposito["referencia"], DEPOSITO)
        self.assertEqual(deposito["especie"], "")

    def test_ignora_lo_no_terminado(self):
        filas = self.leer([mov(1, "Compra(AAA)", F1, "-100,00", 1), mov(2, "Compra(AAA)", F1, "-100,00", 1, estado="Cancelada")])
        self.assertEqual([fila["numero"] for fila in filas], [1])

    def test_tipo_desconocido_queda_sin_clasificar(self):
        fila = self.leer([mov(1, "Canje(AAA)", F1, "0,00", 5)])[0]
        self.assertEqual(fila["comprobante"], "Canje(AAA)")
        self.assertEqual(clasificar(fila, []), "sin_clasificar")

    def test_archivos_invalidos(self):
        casos = {
            "encabezado": dict(filas=[mov(1, "Compra(AAA)", F1, "-1,00", 1)], encabezado=ENCABEZADO_IOL[:-1] + ["Otra"]),
            "cuenta": dict(filas=[mov(1, "Compra(AAA)", F1, "-1,00", 1, cuenta="Estados Unidos")]),
            "fecha": dict(filas=[mov(1, "Compra(AAA)", "31/02/26", "-1,00", 1)]),
            "monto": dict(filas=[mov(1, "Compra(AAA)", F1, "abc", 1)]),
            "numero repetido": dict(filas=[mov(1, "Compra(AAA)", F1, "-1,00", 1), mov(1, "Compra(AAA)", F1, "-2,00", 1)]),
        }
        for nombre, caso in casos.items():
            with self.assertRaises(ErrorHistorial, msg=nombre):
                self.leer(caso["filas"], caso.get("encabezado"))

    def test_un_xls_sin_la_tabla_es_invalido(self):
        ruta = self.dir / "otro.xls"
        ruta.write_bytes(b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1" + b"\x00" * 64)
        with self.assertRaises(ErrorHistorial):
            leer_extracto_iol(ruta)
        ruta.write_text("<html><body><p>Sin movimientos</p></body></html>", encoding="utf-8")
        with self.assertRaises(ErrorHistorial):
            leer_extracto_iol(ruta)


class Clasificacion(unittest.TestCase):
    def test_tabla(self):
        casos = {"IOL COMPRA": "compra", "IOL VENTA": "venta", "IOL IMPUESTO": "gastos", "IOL RENTA": "renta",
                 "IOL DIVIDENDO": "dividendo", "IOL GASTO DE COBRO": "gastos", "IOL AMORTIZACION": "amortizacion",
                 "IOL DEPOSITO": "aporte", "IOL EXTRACCION": "retiro", "IOL SUSCRIPCION FCI": "fci",
                 "IOL RESCATE FCI": "fci", "IOL CREDITO": "gastos"}
        for comprobante, clase in casos.items():
            fila = {"comprobante": comprobante, "especie": "AAA", "importe": 1.0, "referencia": ""}
            self.assertEqual(clasificar(fila, []), clase, comprobante)


class EnElHistorial(Base):
    def test_compra_en_dolares_usa_el_mep_y_separa_el_impuesto(self):
        h = self.historial([mov(7, "Compra(AAAD)", F1, "-5,00", 10), mov(7, "Compra(AAAD)", F1, "-100,00", 10, "Dolares")],
                           mep={D1: 1000.0})
        self.assertEqual(len(h.lotes), 1)
        self.assertEqual((h.lotes[0].ticker, h.lotes[0].cantidad), ("AAA", 10))
        self.assertAlmostEqual(h.lotes[0].costo, 100000.0)
        self.assertAlmostEqual(h.ingresos["gastos"]["ARS"], -5.0)
        self.assertEqual(h.sin_clasificar, [])

    def test_amortizacion_con_baja_cierra_la_posicion(self):
        h = self.historial([mov(1, "Compra(LET1)", F1, "-900.000,00", 1000), mov(2, "Pago de Amortización(LET1)", F2, "1.000.000,00"),
                            mov(3, "Pago de Amortización(LET1)", F2, "0,00", -1000)])
        self.assertEqual(len(h.realizados), 1)
        r = h.realizados[0]
        self.assertEqual((r.ticker, r.fecha, r.clase, r.origen_costo), ("LET1", D2, "cierre", "extracto"))
        self.assertAlmostEqual(r.cantidad, 1000)
        self.assertAlmostEqual(r.importe_ars, 1000000.0)
        self.assertAlmostEqual(r.costo_ars, 900000.0)
        self.assertAlmostEqual(r.resultado_ars, 100000.0)
        self.assertEqual(h.lotes, [])
        self.assertAlmostEqual(h.ingresos["renta"]["ARS"], 0.0)
        self.assertAlmostEqual(h.total_conocido, 100000.0)

    def test_la_baja_parcial_cierra_solo_esa_cantidad(self):
        h = self.historial([mov(1, "Compra(LET1)", F1, "-900.000,00", 1000), mov(2, "Pago de Amortización(LET1)", F2, "400.000,00"),
                            mov(3, "Pago de Amortización(LET1)", F2, "0,00", -400)])
        self.assertAlmostEqual(h.realizados[0].cantidad, 400)
        self.assertAlmostEqual(h.realizados[0].costo_ars, 360000.0)
        self.assertAlmostEqual(h.realizados[0].resultado_ars, 40000.0)
        self.assertAlmostEqual(h.lotes[0].cantidad, 600)
        self.assertAlmostEqual(h.lotes[0].costo, 540000.0)

    def test_amortizacion_sin_baja_es_renta(self):
        h = self.historial([mov(1, "Compra(BOND1)", F1, "-790.152,89", 45493), mov(2, "Pago de Amortización(BOND1)", F2, "114.200,62")])
        self.assertEqual(h.realizados, [])
        self.assertAlmostEqual(h.ingresos["renta"]["ARS"], 114200.62)
        self.assertAlmostEqual(h.lotes[0].cantidad, 45493)
        self.assertAlmostEqual(h.lotes[0].costo, 790152.89)

    def test_cierre_en_dolares_con_la_baja_en_la_cuenta_en_pesos(self):
        h = self.historial([mov(1, "Compra(ON1)", F1, "-400.000,00", 325), mov(2, "Pago de Renta(ON1 US$)", F2, "10,00", cuenta="Dolares"),
                            mov(3, "Pago de Amortización(ON1 US$)", F2, "325,00", cuenta="Dolares"),
                            mov(4, "Pago de Amortización(ON1)", F2, "0,00", -325)], mep={D2: 1500.0})
        r = h.realizados[0]
        self.assertEqual(r.clase, "cierre")
        self.assertAlmostEqual(r.importe_ars, 487500.0)
        self.assertAlmostEqual(r.resultado_ars, 87500.0)
        self.assertAlmostEqual(h.ingresos["renta"]["USD"], 10.0)
        self.assertEqual(h.lotes, [])

    def test_cierre_sin_lotes_suficientes_no_inventa(self):
        h = self.historial([mov(1, "Compra(LET1)", F1, "-90,00", 100), mov(2, "Pago de Amortización(LET1)", F2, "1.000,00"),
                            mov(3, "Pago de Amortización(LET1)", F2, "0,00", -1000)])
        r = h.realizados[0]
        self.assertIsNone(r.resultado_ars)
        self.assertAlmostEqual(r.cantidad_sin_lote, 900)
        self.assertEqual(h.ventas_sin_dato, 1)

    def test_caucion_colocada_con_fechas_distintas(self):
        h = self.historial([mov(34, "Caución(Caución en Pesos Arg.)", F1, "-2.645.366,00", 2645366),
                            mov(34, "Liquidación de Caución", F3, "2.649.214,72", 2649736)])
        self.assertAlmostEqual(h.ingresos["caucion_colocada"]["ARS"], 3848.72)
        self.assertAlmostEqual(h.ingresos["caucion_tomada"]["ARS"], 0.0)
        self.assertAlmostEqual(h.total_conocido, 3848.72)
        self.assertEqual(h.sin_clasificar, [])

    def test_caucion_tomada(self):
        h = self.historial([mov(40, "Caución(Caución en Pesos Arg.)", F1, "1.000,00"), mov(40, "Liquidación de Caución", F2, "-1.010,00")])
        self.assertAlmostEqual(h.ingresos["caucion_tomada"]["ARS"], -10.0)

    def test_caucion_sin_liquidacion_no_suma_capital(self):
        h = self.historial([mov(34, "Caución(Caución en Pesos Arg.)", F1, "-2.645.366,00")])
        self.assertAlmostEqual(h.total_conocido, 0.0)
        self.assertTrue(any("34" in aviso for aviso in h.avisos))

    def test_fondos_fci_y_credito(self):
        h = self.historial([mov(30, DEPOSITO, F1, "800.000,00"), mov(31, EXTRACCION, F1, "-9.847,11"),
                            mov(32, "Suscripción FCI(FONDO)", F1, "-1.001,75", 19), mov(33, "Rescate FCI(FONDO)", F2, "1.034,01", 19),
                            mov(35, "Crédito", F1, "0,04", cuenta="Dolares")], mep={D1: 1000.0})
        self.assertAlmostEqual(h.aportes["ARS"], 800000.0)
        self.assertAlmostEqual(h.retiros["ARS"], 9847.11)
        self.assertAlmostEqual(h.ingresos["fci"]["ARS"], 32.26)
        self.assertAlmostEqual(h.ingresos["gastos"]["USD"], 0.04)
        self.assertAlmostEqual(h.total_conocido, 32.26 + 40.0)
        self.assertEqual(h.lotes, [])

    def test_los_cobros_no_incluyen_el_gasto(self):
        h = self.historial([mov(1, "Compra(BOND1)", F1, "-1.000,00", 100), mov(10, "Pago de Renta(BOND1)", F2, "-30,05"),
                            mov(11, "Pago de Renta(BOND1 US$)", F2, "12,84", cuenta="Dolares"),
                            mov(12, "Pago de Amortización(BOND1 US$)", F2, "5,00", cuenta="Dolares")], mep={D2: 1000.0})
        self.assertEqual(sorted((c["ticker"], c["moneda"], c["importe"]) for c in h.cobros),
                         [("BOND1", "USD", 5.0), ("BOND1", "USD", 12.84)])
        self.assertAlmostEqual(h.ingresos["gastos"]["ARS"], -30.05)
        self.assertAlmostEqual(h.ingresos["renta"]["USD"], 17.84)

    def test_dos_archivos_superpuestos_no_duplican(self):
        filas = [mov(1, "Compra(AAA)", F1, "-100,00", 10), mov(2, "Pago de Amortización(AAA)", F2, "0,00", -4),
                 mov(3, "Pago de Amortización(AAA)", F2, "50,00")]
        escribir_iol(self.dir / "a.xls", filas)
        escribir_iol(self.dir / "b.xls", filas[:2])
        h = construir_historial(leer_extracto_iol(self.dir / "a.xls") + leer_extracto_iol(self.dir / "b.xls"))
        self.assertAlmostEqual(h.lotes[0].cantidad, 6)
        self.assertEqual(len(h.realizados), 1)


if __name__ == "__main__":
    unittest.main()
