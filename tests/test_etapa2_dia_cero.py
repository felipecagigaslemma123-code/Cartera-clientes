import datetime as dt
import json
import tempfile
import unittest
from pathlib import Path
from zoneinfo import ZoneInfo

from openpyxl import load_workbook

from cartera.almacenamiento import actualizar_costos, importar_cartera
from cartera.precios import (
    ClientePrecios,
    Cotizacion,
    ErrorDiaCero,
    advertencias_precio,
    cargar_efectivo_dia_cero,
    fijar_dia_cero,
    patrimonio_inicial,
)
from cartera.punto_partida import Lote, Posicion

RAIZ = Path(__file__).resolve().parents[1]
DEMO = RAIZ / "fixtures" / "punto_partida_demo.xlsx"
T = dt.datetime(2026, 11, 4, 17, 5, tzinfo=ZoneInfo("America/Argentina/Buenos_Aires"))
FECHA = dt.date(2026, 11, 4)

AAA = Posicion(ticker="AAA", especie="A", tipo="cedear", cantidad=100, cotiza_cada=1)
BOND = Posicion(ticker="BOND1", especie="B", tipo="bono", cantidad=1000, cotiza_cada=100)
POSICIONES = [AAA, BOND]


def cot(ticker, ultimo, estado="vivo"):
    return Cotizacion(ticker=ticker, ultimo=ultimo, bid=ultimo, ask=ultimo, pct_dia=0.0, estado=estado, consultado_en=T)


COTIZACIONES = {"AAA": cot("AAA", 1200.0), "BOND1": cot("BOND1", 160000.0)}
VALUACION = 100 * 1200.0 + 1000 * 160000.0 / 100


class Base(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.tmp = Path(tmp.name)
        self.ruta = self.tmp / "dia_cero.json"

    def fijar(self, **argumentos):
        return fijar_dia_cero(POSICIONES, COTIZACIONES, self.ruta, FECHA, **argumentos)

    def guardado(self):
        return json.loads(self.ruta.read_text(encoding="utf-8"))


class FijarDiaCero(Base):
    def test_guarda_una_foto_completa(self):
        self.fijar(mep=1500.0, efectivo={"fecha": "2026-11-04", "ARS": 1000.0, "USD": 10.0})
        d = self.guardado()
        self.assertEqual(d["esquema_version"], 2)
        self.assertEqual(d["fecha"], "2026-11-04")
        self.assertEqual(d["cantidades"], {"AAA": 100, "BOND1": 1000})
        self.assertEqual(d["precios"], {"AAA": 1200.0, "BOND1": 160000.0})
        self.assertEqual(d["mep"], 1500.0)
        self.assertEqual(d["efectivo"], {"fecha": "2026-11-04", "ARS": 1000.0, "USD": 10.0})

    def test_sin_efectivo_queda_en_null_y_no_en_cero(self):
        self.fijar()
        self.assertEqual(self.guardado()["efectivo"], {"fecha": None, "ARS": None, "USD": None})

    def test_acepta_saldo_deudor(self):
        self.fijar(efectivo={"fecha": "2026-11-04", "ARS": -44656.61, "USD": 0.0})
        self.assertEqual(self.guardado()["efectivo"]["ARS"], -44656.61)

    def test_efectivo_invalido_no_escribe(self):
        for malo in ("mil", True, float("nan")):
            with self.assertRaises(ErrorDiaCero):
                self.fijar(efectivo={"fecha": "2026-11-04", "ARS": malo, "USD": 0.0})
            self.assertFalse(self.ruta.exists())


class CargarEfectivo(Base):
    NUEVO = {"fecha": "2026-11-05", "ARS": 5000.0, "USD": 0.0}

    def test_no_toca_precios_ni_cantidades(self):
        self.fijar(mep=1500.0)
        antes = self.guardado()
        cargar_efectivo_dia_cero(self.ruta, self.NUEVO)
        despues = self.guardado()
        self.assertEqual(despues["efectivo"], self.NUEVO)
        self.assertIn("efectivo_cargado_en", despues)
        for clave in ("fecha", "fijado_en", "cantidades", "precios", "mep"):
            self.assertEqual(despues[clave], antes[clave], clave)

    def test_sin_dia_cero_es_error(self):
        with self.assertRaises(ErrorDiaCero):
            cargar_efectivo_dia_cero(self.ruta, self.NUEVO)

    def test_no_pisa_sin_forzar(self):
        self.fijar(efectivo={"fecha": "2026-11-04", "ARS": 1.0, "USD": None})
        with self.assertRaises(ErrorDiaCero):
            cargar_efectivo_dia_cero(self.ruta, self.NUEVO)
        self.assertEqual(self.guardado()["efectivo"]["ARS"], 1.0)
        cargar_efectivo_dia_cero(self.ruta, self.NUEVO, forzar=True)
        self.assertEqual(self.guardado()["efectivo"]["ARS"], 5000.0)

    def test_invalido_no_modifica_el_archivo(self):
        self.fijar()
        antes = self.ruta.read_bytes()
        with self.assertRaises(ErrorDiaCero):
            cargar_efectivo_dia_cero(self.ruta, {"fecha": "2026-11-05", "ARS": "mil", "USD": 0.0})
        self.assertEqual(self.ruta.read_bytes(), antes)


class Patrimonio(Base):
    def calcular(self, **argumentos):
        return patrimonio_inicial(POSICIONES, self.fijar(**argumentos))

    def test_suma_posiciones_y_efectivo(self):
        p = self.calcular(mep=1500.0, efectivo={"fecha": "2026-11-04", "ARS": 1000.0, "USD": 10.0})
        self.assertAlmostEqual(p.valuacion_posiciones, VALUACION)
        self.assertAlmostEqual(p.total, VALUACION + 1000.0 + 10.0 * 1500.0)
        self.assertEqual(p.faltantes, [])

    def test_saldo_deudor_resta(self):
        p = self.calcular(mep=1500.0, efectivo={"fecha": "2026-11-04", "ARS": -1000.0, "USD": 0.0})
        self.assertAlmostEqual(p.total, VALUACION - 1000.0)

    def test_sin_efectivo_no_informa_total(self):
        p = self.calcular(mep=1500.0)
        self.assertIsNone(p.total)
        self.assertAlmostEqual(p.valuacion_posiciones, VALUACION)
        self.assertIn("efectivo ARS", p.faltantes)
        self.assertIn("efectivo USD", p.faltantes)

    def test_usd_sin_mep_no_informa_total(self):
        p = self.calcular(mep=None, efectivo={"fecha": "2026-11-04", "ARS": 0.0, "USD": 10.0})
        self.assertIsNone(p.total)
        self.assertEqual(p.faltantes, ["dólar MEP"])

    def test_usd_en_cero_no_necesita_mep(self):
        p = self.calcular(mep=None, efectivo={"fecha": "2026-11-04", "ARS": 0.0, "USD": 0.0})
        self.assertAlmostEqual(p.total, VALUACION)
        self.assertEqual(p.faltantes, [])

    def test_usa_lo_guardado_y_no_la_cantidad_actual(self):
        dia_cero = self.fijar(mep=1500.0, efectivo={"fecha": "2026-11-04", "ARS": 0.0, "USD": 0.0})
        cambiada = Posicion(ticker="AAA", especie="A", tipo="cedear", cantidad=1, cotiza_cada=1)
        p = patrimonio_inicial([cambiada, BOND], dia_cero)
        self.assertAlmostEqual(p.valuacion_posiciones, VALUACION)


class ControlDePrecios(unittest.TestCase):
    def lote(self, ticker, precio):
        costo = None if precio is None else precio
        origen = "pendiente" if precio is None else "estimado"
        return Lote(ticker=ticker, cantidad=1, origen=origen, fecha=FECHA, precio=precio, costo=costo, nota="")

    def avisos(self, ticker, precio, actual):
        return advertencias_precio([self.lote(ticker, precio)], POSICIONES, {ticker: cot(ticker, actual)})

    def test_precio_en_otra_unidad_avisa_con_ticker_y_precios(self):
        avisos = self.avisos("BOND1", 68.5, 108000.0)
        self.assertEqual(len(avisos), 1)
        self.assertIn("BOND1", avisos[0])
        self.assertRegex(avisos[0], r"68[.,]5")
        self.assertRegex(avisos[0], r"108[.,]?000")

    def test_mas_de_cinco_veces_mayor_avisa(self):
        self.assertEqual(len(self.avisos("AAA", 5001.0, 1000.0)), 1)

    def test_limites_exactos_no_avisan(self):
        self.assertEqual(self.avisos("AAA", 5000.0, 1000.0), [])
        self.assertEqual(self.avisos("AAA", 200.0, 1000.0), [])

    def test_sin_alguno_de_los_precios_no_compara(self):
        self.assertEqual(self.avisos("AAA", None, 1000.0), [])
        self.assertEqual(self.avisos("AAA", 1000.0, None), [])


class RespuestaDeError(unittest.TestCase):
    def test_http_200_con_objeto_de_error_es_una_falla(self):
        with tempfile.TemporaryDirectory() as carpeta:
            cliente = ClientePrecios(lambda url: {"Error": "sin datos"}, Path(carpeta) / "c.json", ahora=lambda: T)
            self.assertEqual(cliente.obtener([AAA])["AAA"].estado, "sin_dato")
            mep = cliente.dolar_mep()
            self.assertTrue(mep is None or mep.ultimo is None)


class EstimacionPerdida(unittest.TestCase):
    def test_avisa_si_un_lote_estimado_vuelve_a_pendiente(self):
        with tempfile.TemporaryDirectory() as carpeta:
            carpeta = Path(carpeta)
            importar_cartera(carpeta / "datos", "demo", DEMO)
            viejo = carpeta / "viejo.xlsx"
            libro = load_workbook(DEMO)
            libro["Lotes"]["F9"] = None  # CCC, estimado en la base
            libro.save(viejo)
            resultado = actualizar_costos(carpeta / "datos", "demo", viejo)
        self.assertTrue(any("CCC" in a for a in resultado["advertencias"]), resultado["advertencias"])


if __name__ == "__main__":
    unittest.main()
