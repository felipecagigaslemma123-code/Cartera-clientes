import datetime as dt
import io
import json
import re
import stat
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import patch

from openpyxl import Workbook

from cartera.__main__ import main
from cartera.almacenamiento import importar_cartera
from cartera.historial import (
    ErrorHistorial, clasificar, conciliar_tenencias, consolidar, construir_historial,
    leer_ajustes, leer_extracto, leer_mep,
)
from cartera.punto_partida import Posicion

DEMO = Path(__file__).resolve().parents[1] / "fixtures" / "punto_partida_demo.xlsx"
ENCABEZADO = ["Liquida", "Operado", "Comprobante", "Numero", "Cantidad", "Especie", "Precio", "Importe", "Saldo", "Referencia"]
D1, D2, D3 = dt.date(2026, 1, 10), dt.date(2026, 2, 10), dt.date(2026, 3, 10)


def f(fecha, comprobante, importe, especie="", cantidad=0, numero=1, moneda="ARS", cuenta="PESOS", referencia=""):
    return {"operado": fecha, "comprobante": comprobante, "numero": numero, "cantidad": cantidad, "especie": especie,
            "importe": importe, "saldo": None, "referencia": referencia, "moneda": moneda, "cuenta": cuenta,
            "archivo": "x.xlsx", "fila": 2}


def compra(fecha, especie, cantidad, importe, numero=1, **k):
    return f(fecha, "COMPRA NORMAL", -importe, especie, cantidad, numero, **k)


def venta(fecha, especie, cantidad, importe, numero=2, **k):
    return f(fecha, "VENTA", importe, especie, -cantidad, numero, **k)


def ajuste(fecha, tipo, ticker, cantidad, importe, moneda="ARS", tc=None, tipo_activo=""):
    return {"fecha": fecha, "tipo": tipo, "ticker": ticker, "cantidad": cantidad, "importe": importe, "moneda": moneda,
            "tc": tc, "tipo_activo": tipo_activo, "nota": ""}


class Clasificacion(unittest.TestCase):
    def test_tabla(self):
        casos = {"COMPRA NORMAL": "compra", "COMPRA TRADING": "compra", "COMPRA PARIDAD": "compra", "VENTA": "venta",
                 "VENTA TRADING": "venta", "DIVIDENDOS": "dividendo", "RETENCION": "retencion",
                 "SUSCRIPCION FCI": "fci", "LIQUIDACION RESCATE FCI": "fci", "CREDITO DERMERC-": "gastos",
                 "N C ARANCELES": "gastos", "RECIBO DE COBRO": "aporte", "ORDEN DE PAGO": "retiro",
                 "ALGO NUEVO": "sin_clasificar", "NOTA DE CREDITO EO": "compensacion"}
        for comprobante, clase in casos.items():
            self.assertEqual(clasificar(f(D1, comprobante, 1.0), []), clase, comprobante)

    def test_renta_o_cierre(self):
        fila = f(D1, "RENTA Y AMORTIZ", 10.0, "AAA")
        self.assertEqual(clasificar(fila, []), "renta")
        self.assertEqual(clasificar(fila, ["AAA"]), "cierre")

    def test_conversion_solo_con_su_referencia(self):
        self.assertEqual(clasificar(f(D1, "NOTA DE CREDITO U$S", 1.0, referencia="CONV CABLE A ME"), []), "conversion")
        self.assertEqual(clasificar(f(D1, "NOTA DE DEBITOS U$S", -1.0, referencia="CONV CABLE A ME "), []), "conversion")
        self.assertEqual(clasificar(f(D1, "NOTA DE CREDITO U$S", 1.0, referencia="OTRA"), []), "sin_clasificar")


class Realizado(unittest.TestCase):
    def test_ganancia_por_fifo(self):
        h = construir_historial([compra(D1, "AAA", 10, 1000.0, 1), compra(D2, "AAA", 10, 2000.0, 2), venta(D3, "AAA", 15, 3500.0, 3)])
        r = h.realizados[0]
        self.assertAlmostEqual(r.costo_ars, 2000.0)
        self.assertAlmostEqual(r.resultado_ars, 1500.0)
        self.assertEqual(r.clase, "venta")
        self.assertEqual(r.origen_costo, "extracto")
        self.assertAlmostEqual(h.lotes[0].cantidad, 5)
        self.assertAlmostEqual(h.lotes[0].costo, 1000.0)

    def test_perdida(self):
        h = construir_historial([compra(D1, "AAA", 10, 1000.0), venta(D2, "AAA", 10, 800.0)])
        self.assertAlmostEqual(h.realizados[0].resultado_ars, -200.0)
        self.assertAlmostEqual(h.total_conocido, -200.0)
        self.assertEqual(h.lotes, [])

    def test_venta_sin_lotes_no_inventa(self):
        h = construir_historial([compra(D1, "AAA", 4, 400.0), venta(D2, "AAA", 10, 1000.0)])
        r = h.realizados[0]
        self.assertIsNone(r.resultado_ars)
        self.assertIsNone(r.costo_ars)
        self.assertAlmostEqual(r.cantidad_sin_lote, 6)
        self.assertEqual(h.ventas_sin_dato, 1)
        self.assertEqual(h.total_conocido, 0)

    def test_mismo_dia_compra_antes_que_venta(self):
        h = construir_historial([venta(D1, "AAA", 10, 1100.0, 1), compra(D1, "AAA", 10, 1000.0, 2)])
        self.assertAlmostEqual(h.realizados[0].resultado_ars, 100.0)

    def test_ventas_del_mismo_dia_por_numero(self):
        h = construir_historial([compra(D1, "AAA", 10, 1000.0, 1), venta(D2, "AAA", 5, 900.0, 9), venta(D2, "AAA", 5, 600.0, 8)])
        self.assertEqual([r.importe_ars for r in h.realizados], [600.0, 900.0])

    def test_cierre_por_toda_la_cantidad_y_pagos_del_dia(self):
        filas = [compra(D1, "LET", 1000, 1000.0), f(D2, "RENTA Y AMORTIZ", 300.0, "LET", numero=5),
                 f(D2, "RENTA Y AMORTIZ", 750.0, "LET", numero=6)]
        h = construir_historial(filas, cierres=["LET"])
        self.assertEqual(len(h.realizados), 1)
        self.assertEqual(h.realizados[0].clase, "cierre")
        self.assertAlmostEqual(h.realizados[0].resultado_ars, 50.0)
        self.assertEqual(h.lotes, [])
        self.assertEqual(h.ingresos["renta"]["ARS"], 0)

    def test_cierre_sin_lotes_es_sin_dato(self):
        h = construir_historial([f(D2, "RENTA Y AMORTIZ", 300.0, "LET")], cierres=["LET"])
        self.assertIsNone(h.realizados[0].resultado_ars)
        self.assertEqual(h.ventas_sin_dato, 1)

    def test_entrada_por_ajuste_es_estimada_y_no_es_ganancia(self):
        h = construir_historial([venta(D2, "GLD", 10, 1200.0)], ajustes=[ajuste(D1, "compra", "GLD", 10, 1000.0, tipo_activo="cedear")])
        self.assertAlmostEqual(h.realizados[0].resultado_ars, 200.0)
        self.assertEqual(h.realizados[0].origen_costo, "estimado")
        self.assertAlmostEqual(h.realizado_estimado, 200.0)
        self.assertEqual(h.realizado_extracto, 0)

    def test_origen_mixto_va_con_lo_estimado(self):
        h = construir_historial([compra(D2, "AAA", 10, 1000.0), venta(D3, "AAA", 20, 2500.0)],
                                ajustes=[ajuste(D1, "compra", "AAA", 10, 1000.0)])
        self.assertEqual(h.realizados[0].origen_costo, "mixto")
        self.assertAlmostEqual(h.realizado_estimado, 500.0)

    def test_ajuste_de_venta(self):
        h = construir_historial([compra(D1, "AAA", 10, 1000.0)], ajustes=[ajuste(D2, "venta", "AAA", 3, 450.0)])
        self.assertAlmostEqual(h.realizados[0].resultado_ars, 150.0)
        self.assertAlmostEqual(h.lotes[0].cantidad, 7)
        self.assertEqual(h.realizados[0].origen_costo, "mixto")
        self.assertEqual(h.realizado_extracto, 0)
        self.assertAlmostEqual(h.realizado_estimado, 150.0)


class Ingresos(unittest.TestCase):
    def test_desglose(self):
        filas = [f(D1, "DIVIDENDOS", 100.0, "AAA"), f(D1, "RETENCION", -7.0, referencia="RET AAA"),
                 f(D1, "RENTA Y AMORTIZ", 50.0, "BON"), f(D1, "CREDITO DERMERC-", 5.0), f(D1, "DIVIDENDOS", -2.0, "SPY"),
                 f(D1, "SUSCRIPCION FCI", -100.0, "FCI"), f(D1, "LIQUIDACION RESCATE FCI", 103.0, "FCI")]
        h = construir_historial(filas)
        self.assertAlmostEqual(h.ingresos["dividendo"]["ARS"], 98.0)
        self.assertAlmostEqual(h.ingresos["retencion"]["ARS"], -7.0)
        self.assertAlmostEqual(h.ingresos["renta"]["ARS"], 50.0)
        self.assertAlmostEqual(h.ingresos["gastos"]["ARS"], 5.0)
        self.assertAlmostEqual(h.ingresos["fci"]["ARS"], 3.0)
        self.assertAlmostEqual(h.total_conocido, 149.0)

    def test_aportes_y_retiros_no_son_ganancia(self):
        h = construir_historial([f(D1, "RECIBO DE COBRO", 1000.0), f(D2, "ORDEN DE PAGO", -300.0)])
        self.assertAlmostEqual(h.aportes["ARS"], 1000.0)
        self.assertAlmostEqual(h.retiros["ARS"], 300.0)
        self.assertEqual(h.total_conocido, 0)

    def test_sin_clasificar_no_suma_y_se_lista(self):
        h = construir_historial([f(D1, "NOTA NUEVA", 500.0)])
        self.assertEqual(h.total_conocido, 0)
        self.assertEqual(len(h.sin_clasificar), 1)

    def test_compensacion_por_error_operativo_es_ingreso(self):
        h = construir_historial([f(D1, "NOTA DE CREDITO EO", 500.0, referencia="ERROR OP")])
        self.assertAlmostEqual(h.ingresos["compensacion"]["ARS"], 500.0)
        self.assertAlmostEqual(h.total_conocido, 500.0)
        self.assertEqual(h.sin_clasificar, [])

    def test_conversion_no_cuenta(self):
        h = construir_historial([f(D1, "NOTA DE CREDITO U$S", 10.0, moneda="USD", cuenta="DOLARES", referencia="CONV CABLE A ME"),
                                 f(D1, "NOTA DE DEBITOS U$S", -10.0, moneda="USD", cuenta="CABLE", referencia="CONV CABLE A ME")])
        self.assertEqual(h.total_conocido, 0)
        self.assertEqual(h.sin_clasificar, [])

    def test_caucion_colocada(self):
        h = construir_historial([f(D1, "COMPRA CAUCION CONTADO", -1000.0, "VARIAS", 100, 10),
                                 f(D1, "VENTA CAUCION TERMINO", 1010.0, "VARIAS", -100, 11)])
        self.assertAlmostEqual(h.ingresos["caucion_colocada"]["ARS"], 10.0)
        self.assertAlmostEqual(h.total_conocido, 10.0)

    def test_caucion_tomada(self):
        h = construir_historial([f(D1, "VENTA CAUCION CONTADO", 1000.0, "VARIAS", -100, 20),
                                 f(D1, "COMPRA CAUCION TERMINO", -1030.0, "VARIAS", 100, 21)])
        self.assertAlmostEqual(h.ingresos["caucion_tomada"]["ARS"], -30.0)

    def test_una_pata_de_contado_con_dos_de_termino(self):
        h = construir_historial([f(D1, "VENTA CAUCION CONTADO", 2000.0, "VARIAS", -100, 20),
                                 f(D1, "COMPRA CAUCION TERMINO", -1010.0, "VARIAS", 100, 21),
                                 f(D1, "COMPRA CAUCION TERMINO", -1020.0, "VARIAS", 100, 35)])
        self.assertAlmostEqual(h.ingresos["caucion_tomada"]["ARS"], -30.0)
        self.assertEqual(h.avisos, [])

    def test_cauciones_de_distinta_clase_el_mismo_dia(self):
        h = construir_historial([f(D1, "VENTA CAUCION CONTADO", 1000.0, "VARIAS", -100, 20),
                                 f(D1, "COMPRA CAUCION TERMINO", -1030.0, "VARIAS", 100, 21),
                                 f(D1, "COMPRA CAUCION CONTADO", -500.0, "VARIAS", 100, 30),
                                 f(D1, "VENTA CAUCION TERMINO", 505.0, "VARIAS", -100, 31)])
        self.assertAlmostEqual(h.ingresos["caucion_tomada"]["ARS"], -30.0)
        self.assertAlmostEqual(h.ingresos["caucion_colocada"]["ARS"], 5.0)

    def test_pata_sin_pareja_no_suma_el_capital(self):
        h = construir_historial([f(D1, "COMPRA CAUCION TERMINO", -1000000.0, "VARIAS", 100, 21)])
        self.assertEqual(h.total_conocido, 0)
        self.assertTrue(any("21" in aviso for aviso in h.avisos))


class Dolares(unittest.TestCase):
    MEP = {D1: 1500.0, D2: 1600.0}

    def test_dividendo_en_dolares(self):
        h = construir_historial([f(D1, "DIVIDENDOS", 10.0, "AAA", moneda="USD", cuenta="CABLE")], mep=self.MEP)
        self.assertAlmostEqual(h.ingresos["dividendo"]["USD"], 10.0)
        self.assertAlmostEqual(h.ingresos["dividendo"]["equivalente_ars"], 15000.0)
        self.assertAlmostEqual(h.total_conocido, 15000.0)

    def test_compra_en_dolares_venta_en_pesos(self):
        h = construir_historial([compra(D1, "AAA", 10, 100.0, moneda="USD", cuenta="DOLARES"), venta(D2, "AAA", 10, 170000.0)], mep=self.MEP)
        self.assertAlmostEqual(h.realizados[0].costo_ars, 150000.0)
        self.assertAlmostEqual(h.realizados[0].resultado_ars, 20000.0)

    def test_usa_el_mep_anterior_hasta_cinco_dias(self):
        fila = f(D1 + dt.timedelta(days=5), "DIVIDENDOS", 1.0, "AAA", moneda="USD", cuenta="CABLE")
        self.assertAlmostEqual(construir_historial([fila], mep={D1: 1500.0}).total_conocido, 1500.0)

    def test_sin_mep_es_sin_dato(self):
        fila = f(D1 + dt.timedelta(days=6), "DIVIDENDOS", 1.0, "AAA", moneda="USD", cuenta="CABLE")
        h = construir_historial([fila], mep={D1: 1500.0})
        self.assertEqual(h.valores_sin_dato, 1)
        self.assertEqual(h.total_conocido, 0)
        self.assertAlmostEqual(h.ingresos["dividendo"]["USD"], 1.0)
        self.assertIsNone(h.ingresos["dividendo"]["equivalente_ars"])

    def test_compra_sin_mep_vuelve_sin_dato_la_venta(self):
        h = construir_historial([compra(D1, "AAA", 10, 100.0, moneda="USD", cuenta="DOLARES"), venta(D2, "AAA", 10, 170000.0)], mep={})
        self.assertIsNone(h.realizados[0].resultado_ars)
        self.assertEqual(h.ventas_sin_dato, 1)

    def test_ajuste_en_dolares_usa_su_tc(self):
        h = construir_historial([venta(D2, "AAA", 10, 170000.0)], ajustes=[ajuste(D1, "compra", "AAA", 10, 100.0, "USD", 1400.0)], mep=self.MEP)
        self.assertAlmostEqual(h.realizados[0].costo_ars, 140000.0)


class Consolidacion(unittest.TestCase):
    def test_quita_duplicados(self):
        filas, _ = consolidar([compra(D1, "AAA", 10, 1000.0, 1), compra(D1, "AAA", 10, 1000.0, 1), compra(D1, "AAA", 10, 1000.0, 2)])
        self.assertEqual(len(filas), 2)

    def test_mismo_numero_otro_importe_no_es_duplicado(self):
        filas, _ = consolidar([compra(D1, "AAA", 10, 1000.0, 1), compra(D1, "AAA", 10, 1001.0, 1)])
        self.assertEqual(len(filas), 2)

    def test_otra_cuenta_no_es_duplicado(self):
        filas, _ = consolidar([f(D1, "DIVIDENDOS", 1.0, "A", moneda="USD", cuenta="CABLE"), f(D1, "DIVIDENDOS", 1.0, "A", moneda="USD", cuenta="DOLARES")])
        self.assertEqual(len(filas), 2)

    def test_avisa_saldo_que_no_cierra(self):
        a = dict(compra(D1, "AAA", 1, 100.0, 1), saldo=900.0, fila=2)
        b = dict(compra(D1, "BBB", 1, 100.0, 2), saldo=500.0, fila=3)
        _, avisos = consolidar([a, b])
        self.assertTrue(any("x.xlsx" in aviso and "3" in aviso for aviso in avisos))

    def test_saldo_correcto_sin_aviso(self):
        a = dict(compra(D1, "AAA", 1, 100.0, 1), saldo=900.0, fila=2)
        b = dict(compra(D1, "BBB", 1, 100.0, 2), saldo=800.0, fila=3)
        self.assertEqual(consolidar([a, b])[1], [])


class Tenencias(unittest.TestCase):
    def test_informa_solo_diferencias(self):
        h = construir_historial([compra(D1, "AAA", 10, 100.0), compra(D1, "BBB", 5, 100.0), compra(D1, "NUE", 1, 100.0)])
        base = [Posicion("AAA", "A", "cedear", 10.0, 1), Posicion("BBB", "B", "cedear", 7.0, 1), Posicion("CCC", "C", "cedear", 3.0, 1)]
        d = conciliar_tenencias(h.lotes, base)
        self.assertEqual(set(d), {"BBB", "CCC", "NUE"})
        self.assertEqual(d["BBB"], {"derivada": 5.0, "base": 7.0, "diferencia": -2.0})

    def test_tolerancia(self):
        h = construir_historial([compra(D1, "AAA", 10, 100.0)])
        self.assertEqual(conciliar_tenencias(h.lotes, [Posicion("AAA", "A", "cedear", 10.5, 1)]), {})


def escribir_extracto(ruta, titulo, filas):
    libro = Workbook()
    hoja = libro.active
    hoja.title = titulo
    hoja.append(ENCABEZADO)
    for fila in filas:
        hoja.append(fila)
    libro.save(ruta)


def fila_xlsx(fecha, comprobante, numero, cantidad, especie, importe, saldo, referencia=None):
    momento = dt.datetime(fecha.year, fecha.month, fecha.day)
    return [momento, momento, comprobante, numero, cantidad, especie, 0, importe, saldo, referencia]


class Archivos(unittest.TestCase):
    def setUp(self):
        temporal = tempfile.TemporaryDirectory()
        self.addCleanup(temporal.cleanup)
        self.dir = Path(temporal.name)

    def test_pesos(self):
        ruta = self.dir / "a.xlsx"
        escribir_extracto(ruta, "Cuenta Corriente PESOS 06-10-26", [fila_xlsx(D1, "COMPRA NORMAL", 5, 10.0, "AAA", -1000.0, -1000.0)])
        fila = leer_extracto(ruta)[0]
        self.assertEqual((fila["moneda"], fila["cuenta"], fila["operado"], fila["numero"]), ("ARS", "PESOS", D1, 5))
        self.assertEqual(fila["fila"], 2)
        self.assertEqual(fila["archivo"], "a.xlsx")

    def test_dolares_y_cable(self):
        for titulo, cuenta in (("Cuenta Corriente DOLARES 06-03-26", "DOLARES"), ("Cuenta Corriente DOLARES CABLE 06-03", "CABLE")):
            ruta = self.dir / (cuenta + ".xlsx")
            escribir_extracto(ruta, titulo, [fila_xlsx(D1, "DIVIDENDOS", 5, 0, "AAA", 1.0, 1.0)])
            fila = leer_extracto(ruta)[0]
            self.assertEqual((fila["moneda"], fila["cuenta"]), ("USD", cuenta))

    def test_especie_vacia(self):
        ruta = self.dir / "a.xlsx"
        escribir_extracto(ruta, "PESOS", [fila_xlsx(D1, "RECIBO DE COBRO", 5, 0, None, 1.0, 1.0)])
        self.assertEqual(leer_extracto(ruta)[0]["especie"], "")

    def test_titulo_sin_moneda(self):
        ruta = self.dir / "a.xlsx"
        escribir_extracto(ruta, "Hoja1", [])
        with self.assertRaises(ErrorHistorial):
            leer_extracto(ruta)

    def test_encabezado_invalido(self):
        ruta = self.dir / "a.xlsx"
        libro = Workbook()
        libro.active.title = "PESOS"
        libro.active.append(["a", "b"])
        libro.save(ruta)
        with self.assertRaises(ErrorHistorial):
            leer_extracto(ruta)

    def test_ajustes(self):
        ruta = self.dir / "ajustes_historial.csv"
        ruta.write_text("fecha,tipo,ticker,cantidad,importe,moneda,tc,tipo_activo,nota\n2026-01-10,compra,AAA,10,1000,,,cedear,entrada\n", encoding="utf-8")
        ajuste_leido = leer_ajustes(ruta)[0]
        self.assertEqual((ajuste_leido["fecha"], ajuste_leido["cantidad"], ajuste_leido["moneda"]), (D1, 10.0, "ARS"))
        self.assertEqual(leer_ajustes(self.dir / "no.csv"), [])

    def test_ajuste_de_tipo_no_admitido(self):
        ruta = self.dir / "ajustes_historial.csv"
        ruta.write_text("fecha,tipo,ticker,cantidad,importe,moneda,tc,tipo_activo,nota\n2026-01-10,deposito,,,1000,,,,\n", encoding="utf-8")
        with self.assertRaises(ErrorHistorial):
            leer_ajustes(ruta)

    def test_mep(self):
        ruta = self.dir / "mep_diario.csv"
        ruta.write_text("fecha,mep\n2026-01-10,1500.5\n", encoding="utf-8")
        self.assertEqual(leer_mep(ruta), {D1: 1500.5})
        self.assertEqual(leer_mep(self.dir / "no.csv"), {})


PANELES = {"arg_cedears": [{"symbol": "AAA", "c": 1200.0}, {"symbol": "BBB", "c": 1100.0}], "arg_stocks": [{"symbol": "CCC", "c": 2500.0}],
           "arg_bonds": [{"symbol": "BOND1", "c": 160000.0}], "arg_notes": [{"symbol": "NOTE1", "c": 110.0}],
           "arg_corp": [{"symbol": "ONX", "c": 150000.0}], "mep": [{"ticker": "AL30", "mark": 1500.0}]}


def consultar(url):
    if "/historical/bonds/AL30D" in url:
        return [{"date": "2026-01-10", "c": 100.0}]
    if "/historical/bonds/AL30" in url:
        return [{"date": "2026-01-10", "c": 150000.0}, {"date": "2026-01-11", "c": 151000.0}]
    return PANELES[url.rsplit("/", 1)[-1]]


class Comando(unittest.TestCase):
    def setUp(self):
        temporal = tempfile.TemporaryDirectory()
        self.addCleanup(temporal.cleanup)
        self.datos = Path(temporal.name) / "datos"
        importar_cartera(self.datos, "demo", DEMO)
        self.carpeta = self.datos / "clientes" / "demo"

    def extractos(self):
        carpeta = self.carpeta / "extractos"
        carpeta.mkdir()
        escribir_extracto(carpeta / "p.xlsx", "Cuenta Corriente PESOS", [
            fila_xlsx(D1, "RECIBO DE COBRO", 1, 0, None, 5000.0, 5000.0),
            fila_xlsx(D1, "COMPRA NORMAL", 2, 10.0, "AAA", -1000.0, 4000.0),
            fila_xlsx(D2, "VENTA", 3, -10.0, "AAA", 1500.0, 5500.0),
            fila_xlsx(D3, "DIVIDENDOS", 4, 0, "BBB", 70.0, 5570.0)])

    def correr(self, *argumentos, comando="historial"):
        salida, errores = io.StringIO(), io.StringIO()
        with patch("cartera.__main__.consultar_json", side_effect=consultar):
            with redirect_stdout(salida), redirect_stderr(errores):
                codigo = main(["--datos", str(self.datos), comando, "--cliente", "demo"] + list(argumentos))
        return codigo, salida.getvalue(), errores.getvalue()

    def test_informa_y_escribe(self):
        self.extractos()
        codigo, salida, errores = self.correr()
        self.assertEqual(codigo, 0, errores)
        self.assertIn("570,00", salida)
        self.assertIn("5.000,00", salida)
        csv = self.carpeta / "realizado.csv"
        self.assertIn("AAA", csv.read_text(encoding="utf-8"))
        self.assertEqual(stat.S_IMODE(csv.stat().st_mode) & 0o077, 0)

    def test_duplicados_entre_archivos(self):
        self.extractos()
        carpeta = self.carpeta / "extractos"
        escribir_extracto(carpeta / "q.xlsx", "Cuenta Corriente PESOS", [fila_xlsx(D2, "VENTA", 3, -10.0, "AAA", 1500.0, 5500.0)])
        _, salida, errores = self.correr()
        self.assertIn("570,00", salida, errores)

    def test_sin_extractos_es_error(self):
        codigo, _, errores = self.correr()
        self.assertNotEqual(codigo, 0)
        self.assertTrue(errores.strip())
        self.assertFalse((self.carpeta / "realizado.csv").exists())

    def test_archivo_invalido_no_escribe(self):
        self.extractos()
        escribir_extracto(self.carpeta / "extractos" / "mal.xlsx", "Hoja1", [])
        codigo, _, _ = self.correr()
        self.assertNotEqual(codigo, 0)
        self.assertFalse((self.carpeta / "realizado.csv").exists())

    def test_actualizar_mep(self):
        self.extractos()
        codigo, _, errores = self.correr("--actualizar-mep")
        self.assertEqual(codigo, 0, errores)
        self.assertEqual(leer_mep(self.carpeta / "mep_diario.csv"), {D1: 1500.0})

    def generar(self):
        codigo, _, errores = self.correr(comando="dashboard")
        self.assertEqual(codigo, 0, errores)
        html = (self.carpeta / "dashboard.html").read_text(encoding="utf-8")
        datos = json.loads(re.search(r'<script id="datos-cartera" type="application/json">(.*?)</script>', html, re.S).group(1))
        return html, datos

    def test_dashboard_con_seccion(self):
        self.extractos()
        html, datos = self.generar()
        self.assertIn('id="rendimiento-realizado"', html)
        self.assertAlmostEqual(datos["historial"]["total_conocido"], 570.0)
        self.assertAlmostEqual(datos["historial"]["aportes"]["ARS"], 5000.0)
        self.assertEqual(datos["historial"]["realizados"][0]["ticker"], "AAA")

    def test_dashboard_sin_extractos(self):
        html, datos = self.generar()
        self.assertNotIn('id="rendimiento-realizado"', html)
        self.assertNotIn("historial", datos)

    def test_dashboard_con_error_se_genera_igual(self):
        self.extractos()
        escribir_extracto(self.carpeta / "extractos" / "mal.xlsx", "Hoja1", [])
        html, datos = self.generar()
        self.assertNotIn('id="rendimiento-realizado"', html)
        self.assertTrue(datos["avisos_datos"])


if __name__ == "__main__":
    unittest.main()
