import csv
import datetime as dt
import json
import tempfile
import unittest
from pathlib import Path
from zoneinfo import ZoneInfo

from cartera.precios import ClientePrecios, Cotizacion, ErrorDiaCero, capturar_historial, fijar_dia_cero
from cartera.punto_partida import Posicion

AR = ZoneInfo("America/Argentina/Buenos_Aires")
T1 = dt.datetime(2026, 11, 4, 12, 0, tzinfo=AR)
T2 = dt.datetime(2026, 11, 4, 12, 5, tzinfo=AR)

AAA = Posicion(ticker="AAA", especie="A", tipo="cedear", cantidad=100, cotiza_cada=1)
BBB = Posicion(ticker="BBB", especie="B", tipo="cedear", cantidad=50, cotiza_cada=1)
BOND = Posicion(ticker="BOND1", especie="C", tipo="bono", cantidad=1000, cotiza_cada=100)


def fila(simbolo, c=1200.0, bid=1190.0, ask=1210.0, pct=1.5):
    return {"symbol": simbolo, "q_bid": 1.0, "px_bid": bid, "px_ask": ask, "q_ask": 1.0,
            "v": 1.0, "q_op": 1.0, "c": c, "pct_change": pct}


class FetchFalso:
    def __init__(self, respuestas):
        self.respuestas = respuestas
        self.llamadas = []

    def __call__(self, url):
        self.llamadas.append(url)
        respuesta = self.respuestas.get(url.rsplit("/", 1)[-1])
        if respuesta is None:
            raise IOError("caida")
        return respuesta


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.cache = Path(self.tmp.name) / "cache.json"

    def cliente(self, respuestas, ahora=T1):
        fetch = FetchFalso(respuestas)
        return ClientePrecios(fetch, self.cache, ahora=lambda: ahora), fetch


class Obtener(Base):
    def test_una_sola_llamada_por_endpoint(self):
        cliente, fetch = self.cliente(
            {"arg_cedears": [fila("AAA"), fila("BBB")], "arg_bonds": [fila("BOND1", 160000.0)]}
        )
        cliente.obtener([AAA, BBB, BOND])
        self.assertEqual(
            sorted(fetch.llamadas),
            ["https://data912.com/live/arg_bonds", "https://data912.com/live/arg_cedears"],
        )

    def test_dato_vivo(self):
        cliente, _ = self.cliente({"arg_cedears": [fila("AAA")]})
        c = cliente.obtener([AAA])["AAA"]
        self.assertEqual(c.estado, "vivo")
        self.assertEqual((c.ultimo, c.bid, c.ask, c.pct_dia), (1200.0, 1190.0, 1210.0, 1.5))
        self.assertEqual(c.consultado_en, T1)

    def test_sin_cache_y_caido_es_sin_dato_nunca_cero(self):
        cliente, _ = self.cliente({})
        c = cliente.obtener([AAA])["AAA"]
        self.assertEqual(c.estado, "sin_dato")
        self.assertIsNone(c.ultimo)
        self.assertIsNone(c.bid)

    def test_cero_no_es_un_precio(self):
        cliente, _ = self.cliente({"arg_cedears": [fila("AAA", c=0.0)]})
        c = cliente.obtener([AAA])["AAA"]
        self.assertEqual(c.estado, "sin_dato")
        self.assertIsNone(c.ultimo)

    def test_bid_cero_se_vuelve_nulo(self):
        cliente, _ = self.cliente({"arg_cedears": [fila("AAA", bid=0.0, ask=0.0)]})
        c = cliente.obtener([AAA])["AAA"]
        self.assertEqual(c.estado, "vivo")
        self.assertIsNone(c.bid)
        self.assertIsNone(c.ask)

    def test_caida_devuelve_el_ultimo_dato_con_su_fecha(self):
        cliente, _ = self.cliente({"arg_cedears": [fila("AAA")]}, ahora=T1)
        cliente.obtener([AAA])
        cliente, _ = self.cliente({}, ahora=T2)
        c = cliente.obtener([AAA])["AAA"]
        self.assertEqual(c.estado, "cache")
        self.assertEqual(c.ultimo, 1200.0)
        self.assertEqual(c.consultado_en, T1)

    def test_especie_que_falta_en_el_panel_usa_cache(self):
        cliente, _ = self.cliente({"arg_cedears": [fila("AAA")]}, ahora=T1)
        cliente.obtener([AAA])
        cliente, _ = self.cliente({"arg_cedears": [fila("BBB")]}, ahora=T2)
        resultado = cliente.obtener([AAA, BBB])
        self.assertEqual(resultado["AAA"].estado, "cache")
        self.assertEqual(resultado["BBB"].estado, "vivo")

    def test_falla_de_un_endpoint_no_afecta_a_otro(self):
        cliente, _ = self.cliente({"arg_bonds": [fila("BOND1", 160000.0)]})
        resultado = cliente.obtener([AAA, BOND])
        self.assertEqual(resultado["AAA"].estado, "sin_dato")
        self.assertEqual(resultado["BOND1"].estado, "vivo")

    def test_cache_ilegible_se_trata_como_vacia(self):
        self.cache.write_text("{no es json", encoding="utf-8")
        cliente, _ = self.cliente({})
        self.assertEqual(cliente.obtener([AAA])["AAA"].estado, "sin_dato")

    def test_dolar_mep_usa_mark_de_al30(self):
        cliente, fetch = self.cliente(
            {"mep": [{"ticker": "GD30", "mark": 1.0}, {"ticker": "AL30", "bid": 1500.0, "ask": 1502.0, "close": 1500.0, "mark": 1501.0}]}
        )
        mep = cliente.dolar_mep()
        self.assertEqual(mep.ultimo, 1501.0)
        self.assertEqual(fetch.llamadas, ["https://data912.com/live/mep"])

    def test_dolar_mep_caido_no_inventa(self):
        cliente, _ = self.cliente({})
        mep = cliente.dolar_mep()
        self.assertTrue(mep is None or mep.ultimo is None)


def cotizacion(ticker, ultimo=1200.0, estado="vivo"):
    return Cotizacion(ticker=ticker, ultimo=ultimo, bid=ultimo, ask=ultimo, pct_dia=0.0, estado=estado, consultado_en=T1)


class DiaCero(Base):
    def setUp(self):
        super().setUp()
        self.ruta = Path(self.tmp.name) / "dia_cero.json"

    def test_fija_precios(self):
        contenido = fijar_dia_cero([AAA], {"AAA": cotizacion("AAA")}, self.ruta, dt.date(2026, 11, 4))
        guardado = json.loads(self.ruta.read_text(encoding="utf-8"))
        self.assertEqual(guardado["fecha"], "2026-11-04")
        self.assertEqual(guardado["precios"], {"AAA": 1200.0})
        self.assertEqual(contenido["precios"], {"AAA": 1200.0})

    def test_no_fija_si_falta_un_precio(self):
        with self.assertRaises(ErrorDiaCero):
            fijar_dia_cero([AAA, BBB], {"AAA": cotizacion("AAA")}, self.ruta, dt.date(2026, 11, 4))
        self.assertFalse(self.ruta.exists())

    def test_no_fija_con_datos_de_cache(self):
        with self.assertRaises(ErrorDiaCero):
            fijar_dia_cero([AAA], {"AAA": cotizacion("AAA", estado="cache")}, self.ruta, dt.date(2026, 11, 4))

    def test_no_pisa_sin_forzar(self):
        fijar_dia_cero([AAA], {"AAA": cotizacion("AAA")}, self.ruta, dt.date(2026, 11, 4))
        with self.assertRaises(ErrorDiaCero):
            fijar_dia_cero([AAA], {"AAA": cotizacion("AAA", 1300.0)}, self.ruta, dt.date(2026, 11, 5))
        self.assertEqual(json.loads(self.ruta.read_text(encoding="utf-8"))["precios"]["AAA"], 1200.0)
        fijar_dia_cero([AAA], {"AAA": cotizacion("AAA", 1300.0)}, self.ruta, dt.date(2026, 11, 5), forzar=True)
        self.assertEqual(json.loads(self.ruta.read_text(encoding="utf-8"))["precios"]["AAA"], 1300.0)


class Historial(Base):
    def test_agrega_solo_datos_vivos(self):
        ruta = Path(self.tmp.name) / "h.csv"
        datos = {"AAA": cotizacion("AAA"), "BBB": cotizacion("BBB", estado="cache")}
        self.assertEqual(capturar_historial(datos, ruta), 1)
        self.assertEqual(capturar_historial(datos, ruta), 1)
        with ruta.open(encoding="utf-8", newline="") as archivo:
            filas = list(csv.DictReader(archivo))
        self.assertEqual(len(filas), 2)
        self.assertEqual(set(filas[0]), {"consultado_en", "ticker", "ultimo", "bid", "ask"})
        self.assertEqual(filas[0]["ticker"], "AAA")


if __name__ == "__main__":
    unittest.main()
