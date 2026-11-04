"""Fallas de cotización, conservación de caché y control de unidades."""

import copy
import csv
import datetime as dt
import fcntl
import json
import multiprocessing
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from zoneinfo import ZoneInfo

from cartera.precios import ClientePrecios, Cotizacion, advertencias_precio, capturar_historial
from cartera.punto_partida import Lote, Posicion


AR = ZoneInfo("America/Argentina/Buenos_Aires")
T1 = dt.datetime(2026, 11, 4, 12, tzinfo=AR)
T2 = T1 + dt.timedelta(minutes=5)
AAA = Posicion("AAA", "Demo", "cedear", 100, 1)
BOND = Posicion("BOND1", "Bono Demo", "bono", 1000, 100)


def fila(ticker="AAA", ultimo=1000, **valores):
    return dict(symbol=ticker, c=ultimo, px_bid=990, px_ask=1010, pct_change=-1.5, **valores)


def cot(ticker="AAA", precio=1000, estado="vivo"):
    return Cotizacion(ticker, precio, precio, precio, 0.0, estado, T1)


def _guardar_panel_concurrente(ruta_cache, iniciado, terminado):
    def fetch(url):
        iniciado.set()
        return [fila("BOND1", 160000)]
    cliente = ClientePrecios(fetch, ruta_cache, ahora=lambda: T2)
    cliente.obtener([BOND])
    terminado.set()


class ClienteAdicional(unittest.TestCase):
    def setUp(self):
        self.temporal = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporal.cleanup)
        self.raiz = Path(self.temporal.name)
        self.cache = self.raiz / "cache.json"

    def cliente(self, datos, ahora=T1, **opciones):
        llamadas = []
        def fetch(url):
            llamadas.append(url)
            respuesta = datos.get(url.rsplit("/", 1)[-1])
            if isinstance(respuesta, Exception):
                raise respuesta
            return respuesta
        return ClientePrecios(fetch, self.cache, ahora=lambda: ahora, **opciones), llamadas

    def test_rechaza_no_finitos_booleanos_textos_y_no_positivos(self):
        for ultimo in (True, float("nan"), float("inf"), -1, 0, "1000", None):
            with self.subTest(ultimo=ultimo):
                cliente, _ = self.cliente({"arg_cedears": [fila(ultimo=ultimo)]})
                resultado = cliente.obtener([AAA])["AAA"]
                self.assertEqual(resultado.estado, "sin_dato")
                self.assertIsNone(resultado.ultimo)
                self.assertFalse(self.cache.exists())

    def test_puntas_invalidas_no_anulan_ultimo_valido(self):
        registro = fila()
        registro.update(px_bid=True, px_ask=float("inf"), pct_change=float("nan"))
        cliente, _ = self.cliente({"arg_cedears": [registro]})
        resultado = cliente.obtener([AAA])["AAA"]
        self.assertEqual(resultado.estado, "vivo")
        self.assertIsNone(resultado.bid)
        self.assertIsNone(resultado.ask)
        self.assertIsNone(resultado.pct_dia)

    def test_objetos_de_error_y_listas_rotas_recurren_a_cache_sin_rejuvenecer(self):
        cliente, _ = self.cliente({"arg_cedears": [fila()]})
        cliente.obtener([AAA])
        anterior = self.cache.read_bytes()
        for respuesta in ({"Error": "sin datos"}, [None, 5, {}], OSError("sin red")):
            with self.subTest(respuesta=respuesta):
                cliente, _ = self.cliente({"arg_cedears": respuesta}, ahora=T2)
                resultado = cliente.obtener([AAA])["AAA"]
                self.assertEqual(resultado.estado, "cache")
                self.assertEqual(resultado.consultado_en, T1)
                self.assertEqual(resultado.pct_dia, -1.5)
                self.assertEqual(self.cache.read_bytes(), anterior)

    def test_panel_con_ticker_duplicado_no_elige_un_precio_arbitrario(self):
        cliente, _ = self.cliente({"arg_cedears": [fila()]})
        cliente.obtener([AAA])
        cliente, _ = self.cliente({"arg_cedears": [fila(ultimo=2000), fila(ultimo=3000)]}, ahora=T2)
        resultado = cliente.obtener([AAA])["AAA"]
        self.assertEqual(resultado.estado, "cache")
        self.assertEqual(resultado.ultimo, 1000)

    def test_guardar_un_panel_conserva_los_datos_y_hora_de_otro(self):
        cliente, _ = self.cliente({"arg_cedears": [fila()]})
        cliente.obtener([AAA])
        primero = json.loads(self.cache.read_text())["AAA"]
        cliente, _ = self.cliente({"arg_bonds": [fila("BOND1", 160000)]}, ahora=T2)
        cliente.obtener([BOND])
        cache = json.loads(self.cache.read_text())
        self.assertEqual(cache["AAA"], primero)
        self.assertEqual(cache["BOND1"]["ultimo"], 160000)

    def test_registro_cache_sin_zona_horaria_no_se_usa(self):
        cliente, _ = self.cliente({"arg_cedears": [fila()]})
        cliente.obtener([AAA])
        contenido = json.loads(self.cache.read_text())
        contenido["AAA"]["consultado_en"] = "2026-11-04T12:00:00"
        self.cache.write_text(json.dumps(contenido))
        cliente, _ = self.cliente({}, ahora=T2)
        self.assertEqual(cliente.obtener([AAA])["AAA"].estado, "sin_dato")

    def test_error_al_publicar_cache_no_destruye_archivo_anterior(self):
        cliente, _ = self.cliente({"arg_cedears": [fila()]})
        cliente.obtener([AAA])
        anterior = self.cache.read_bytes()
        cliente, _ = self.cliente({"arg_cedears": [fila(ultimo=2000)]}, ahora=T2)
        with patch("cartera.precios.os.replace", side_effect=OSError("sin disco")):
            with self.assertRaises(OSError):
                cliente.obtener([AAA])
        self.assertEqual(self.cache.read_bytes(), anterior)
        self.assertEqual(list(self.raiz.glob("*.tmp")), [])

    def test_consulta_diferida_no_crea_cache_hasta_confirmar(self):
        cliente, _ = self.cliente({"arg_cedears": [fila()]}, persistir_cache=False)
        self.assertEqual(cliente.obtener([AAA])["AAA"].estado, "vivo")
        self.assertFalse(self.cache.exists())
        self.assertEqual(cliente.guardar_cache(), 1)
        anterior = self.cache.read_bytes()
        modificado = self.cache.stat().st_mtime_ns
        self.assertEqual(cliente.guardar_cache(), 0)
        self.assertEqual(self.cache.read_bytes(), anterior)
        self.assertEqual(self.cache.stat().st_mtime_ns, modificado)

    def test_guardado_concurrente_espera_y_fusiona_la_version_mas_reciente(self):
        cliente, _ = self.cliente({"arg_cedears": [fila()]})
        cliente.obtener([AAA])
        contexto = multiprocessing.get_context("spawn")
        iniciado, terminado = contexto.Event(), contexto.Event()
        proceso = contexto.Process(target=_guardar_panel_concurrente,
                                   args=(str(self.cache), iniciado, terminado))
        descriptor = os.open(str(self.raiz), os.O_RDONLY)
        try:
            fcntl.flock(descriptor, fcntl.LOCK_EX)
            proceso.start()
            self.assertTrue(iniciado.wait(5), "El proceso no llegó a consultar su panel.")
            self.assertFalse(terminado.wait(0.1), "La caché se publicó mientras otra instancia tenía el bloqueo.")
            nueva_version = json.loads(self.cache.read_text())
            nueva_version["AAA"]["ultimo"] = 2000.0
            nueva_version["AAA"]["consultado_en"] = T2.isoformat()
            self.cache.write_text(json.dumps(nueva_version))
        finally:
            fcntl.flock(descriptor, fcntl.LOCK_UN)
            os.close(descriptor)
            if proceso.pid is not None:
                proceso.join(5)
                if proceso.is_alive():
                    proceso.terminate()
                    proceso.join(2)
        self.assertEqual(proceso.exitcode, 0)
        contenido = json.loads(self.cache.read_text())
        self.assertEqual(contenido["AAA"]["ultimo"], 2000.0)
        self.assertEqual(contenido["AAA"]["consultado_en"], T2.isoformat())
        self.assertEqual(contenido["BOND1"]["ultimo"], 160000.0)

    def test_mep_usa_mark_y_no_reutiliza_cache_si_cae(self):
        cliente, llamadas = self.cliente({"mep": [{"ticker": "AL30", "mark": 1500, "bid": 1490, "ask": 1510}]})
        resultado = cliente.dolar_mep()
        self.assertEqual(resultado.ticker, "MEP")
        self.assertEqual(resultado.ultimo, 1500)
        self.assertEqual(llamadas, ["https://data912.com/live/mep"])
        cliente, _ = self.cliente({"mep": OSError("sin red")}, ahora=T2)
        self.assertIsNone(cliente.dolar_mep())

    def test_mep_invalido_o_duplicado_no_devuelve_otro_bono(self):
        for respuesta in ([{"ticker": "GD30", "mark": 1500}],
                          [{"ticker": "AL30", "mark": True}],
                          [{"ticker": "AL30", "mark": 1}] * 2,
                          {"Error": "sin datos"}):
            with self.subTest(respuesta=respuesta):
                cliente, _ = self.cliente({"mep": respuesta})
                self.assertIsNone(cliente.dolar_mep())


class HistorialAdicional(unittest.TestCase):
    def setUp(self):
        self.temporal = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporal.cleanup)
        self.ruta = Path(self.temporal.name) / "historial.csv"

    def test_sin_vivos_no_crea_archivo(self):
        self.assertEqual(capturar_historial({"AAA": cot(estado="cache")}, self.ruta), 0)
        self.assertFalse(self.ruta.exists())

    def test_mep_se_captura_con_ticker_propio_y_puntas_vacias(self):
        mep = cot("MEP", 1500)
        mep.bid = mep.ask = None
        self.assertEqual(capturar_historial({"MEP": mep}, self.ruta), 1)
        with self.ruta.open(newline="") as archivo:
            fila = next(csv.DictReader(archivo))
        self.assertEqual(fila["ticker"], "MEP")
        self.assertEqual(fila["bid"], "")
        self.assertEqual(fila["ask"], "")

    def test_error_de_escritura_no_deja_una_captura_parcial(self):
        capturar_historial({"AAA": cot()}, self.ruta)
        anterior = self.ruta.read_bytes()
        with patch("cartera.precios.os.fsync", side_effect=OSError("sin disco")):
            with self.assertRaises(OSError):
                capturar_historial({"AAA": cot(precio=2000)}, self.ruta)
        self.assertEqual(self.ruta.read_bytes(), anterior)

    def test_encabezado_incompatible_no_se_trunca(self):
        self.ruta.write_text("otro,formato\n1,2\n")
        anterior = self.ruta.read_bytes()
        with self.assertRaises(ValueError):
            capturar_historial({"AAA": cot()}, self.ruta)
        self.assertEqual(self.ruta.read_bytes(), anterior)

    def test_captura_no_relee_las_filas_del_historial(self):
        capturar_historial({"AAA": cot()}, self.ruta)
        with self.ruta.open("ab") as archivo:
            archivo.write(b"2026-11-04T12:00:00-03:00,AAA,1000,1000,1000\r\n" * 1000)
        pruebas = self
        original = self.ruta.open("a+b", buffering=0)
        lecturas = []

        class ArchivoVigilado:
            def __getattr__(self, nombre):
                return getattr(original, nombre)

            def __enter__(self):
                return self

            def __exit__(self, *argumentos):
                return original.__exit__(*argumentos)

            def readline(self, limite=-1):
                pruebas.assertGreater(limite, 0)
                return original.readline(limite)

            def read(self, cantidad=-1):
                lecturas.append(cantidad)
                pruebas.assertEqual(cantidad, 1, "Solo debe leer el último byte después del encabezado.")
                return original.read(cantidad)

        with patch("cartera.precios.Path.open", return_value=ArchivoVigilado()):
            self.assertEqual(capturar_historial({"AAA": cot(precio=2000)}, self.ruta), 1)
        self.assertEqual(lecturas, [1])
        with self.ruta.open(newline="") as archivo:
            filas = list(csv.DictReader(archivo))
        self.assertEqual(len(filas), 1002)
        self.assertEqual(float(filas[-1]["ultimo"]), 2000)

    def test_historial_sin_salto_final_se_completa_sin_unir_filas(self):
        capturar_historial({"AAA": cot()}, self.ruta)
        anterior = self.ruta.read_bytes().rstrip(b"\r\n")
        self.ruta.write_bytes(anterior)
        capturar_historial({"AAA": cot(precio=2000)}, self.ruta)
        self.assertTrue(self.ruta.read_bytes().startswith(anterior))
        with self.ruta.open(newline="") as archivo:
            filas = list(csv.DictReader(archivo))
        self.assertEqual(len(filas), 2)
        self.assertEqual(float(filas[-1]["ultimo"]), 2000)


class AdvertenciasAdicionales(unittest.TestCase):
    def test_limites_decimales_y_origen_se_conservan(self):
        for precio, cantidad in ((5000, 0), (200, 0), (5000.01, 1), (199.99, 1)):
            with self.subTest(precio=precio):
                lote = Lote("AAA", 1, "estimado", T1.date(), precio, precio, "Demo")
                anterior = copy.deepcopy(lote)
                avisos = advertencias_precio([lote], [AAA], {"AAA": cot()})
                self.assertEqual(len(avisos), cantidad)
                self.assertEqual(lote, anterior)
                if avisos:
                    self.assertIn("unidad o moneda", avisos[0])
                    self.assertIn("estimado", avisos[0])

    def test_bono_se_compara_en_su_unidad_de_cotizacion_sin_recalcular(self):
        lote = Lote("BOND1", 1000, "extracto", T1.date(), 68.5, 685, "Demo")
        aviso = advertencias_precio([lote], [BOND], {"BOND1": cot("BOND1", 108000)})[0]
        self.assertIn("68,5", aviso)
        self.assertIn("108.000", aviso)
        self.assertEqual(lote.costo, 685)


if __name__ == "__main__":
    unittest.main()
