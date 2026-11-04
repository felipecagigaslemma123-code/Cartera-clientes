import datetime as dt
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from openpyxl import load_workbook

from cartera.calculos import costo_total, estado_costo, resultado_posicion, resumen_cartera, valuacion
from cartera.punto_partida import ErrorPuntoPartida, cargar_punto_partida

RAIZ = Path(__file__).resolve().parents[1]
DEMO = RAIZ / "fixtures" / "punto_partida_demo.xlsx"


def lotes_de(punto, ticker):
    return [l for l in punto.lotes if l.ticker == ticker]


def posicion_de(punto, ticker):
    return next(p for p in punto.posiciones if p.ticker == ticker)


class Carga(unittest.TestCase):
    def setUp(self):
        self.punto = cargar_punto_partida(DEMO)

    def test_lee_posiciones_sin_la_fila_total(self):
        self.assertEqual(
            [p.ticker for p in self.punto.posiciones],
            ["AAA", "BBB", "CCC", "BOND1", "NOTE1", "ONX"],
        )

    def test_lee_datos_de_posicion(self):
        bono = posicion_de(self.punto, "BOND1")
        self.assertEqual(bono.tipo, "bono")
        self.assertEqual(bono.cantidad, 1000)
        self.assertEqual(bono.cotiza_cada, 100)

    def test_lote_de_extracto_usa_el_costo_real(self):
        lote = lotes_de(self.punto, "AAA")[0]
        self.assertEqual(lote.origen, "extracto")
        self.assertAlmostEqual(lote.costo, 60600.00, places=2)
        self.assertAlmostEqual(lote.precio, 1010.00, places=2)
        self.assertEqual(lote.fecha, dt.date(2026, 3, 10))

    def test_precio_de_extracto_respeta_cotizacion_cada_100(self):
        lote = lotes_de(self.punto, "NOTE1")[0]
        self.assertAlmostEqual(lote.precio, 105.0, places=2)

    def test_lote_estimado_calcula_el_costo_sin_depender_de_la_formula(self):
        lote = lotes_de(self.punto, "BBB")[1]
        self.assertEqual(lote.origen, "estimado")
        self.assertAlmostEqual(lote.precio, 900.0)
        self.assertAlmostEqual(lote.costo, 18000.0)

    def test_lote_sin_precio_queda_pendiente(self):
        lote = lotes_de(self.punto, "BOND1")[0]
        self.assertEqual(lote.origen, "pendiente")
        self.assertIsNone(lote.precio)
        self.assertIsNone(lote.costo)

    def test_fecha_sin_precio_sigue_pendiente_y_no_es_error(self):
        with tempfile.TemporaryDirectory() as carpeta:
            ruta = Path(carpeta) / "x.xlsx"
            libro = load_workbook(DEMO)
            libro["Lotes"]["D10"] = dt.datetime(2025, 1, 1)
            libro.save(ruta)
            punto = cargar_punto_partida(ruta)
        self.assertEqual(lotes_de(punto, "BOND1")[0].origen, "pendiente")


class Validaciones(unittest.TestCase):
    def errores_al_cambiar(self, cambio):
        with tempfile.TemporaryDirectory() as carpeta:
            ruta = Path(carpeta) / "x.xlsx"
            libro = load_workbook(DEMO)
            cambio(libro)
            libro.save(ruta)
            with self.assertRaises(ErrorPuntoPartida) as contexto:
                cargar_punto_partida(ruta)
        return contexto.exception.errores

    def test_cantidad_de_lotes_que_no_cierra(self):
        def cambio(libro):
            libro["Lotes"]["B5"] = 61

        errores = self.errores_al_cambiar(cambio)
        self.assertTrue(any("AAA" in e for e in errores))

    def test_cotiza_cada_que_no_coincide_con_el_tipo(self):
        def cambio(libro):
            libro["Cartera"]["E8"] = 1

        errores = self.errores_al_cambiar(cambio)
        self.assertTrue(any("BOND1" in e for e in errores))

    def test_tipo_desconocido(self):
        def cambio(libro):
            libro["Cartera"]["C5"] = "fondo"

        self.assertTrue(self.errores_al_cambiar(cambio))

    def test_extracto_sin_costo(self):
        def cambio(libro):
            libro["Lotes"]["G5"] = None

        self.assertTrue(self.errores_al_cambiar(cambio))

    def test_estimado_con_precio_y_sin_fecha(self):
        def cambio(libro):
            libro["Lotes"]["F10"] = 150000

        errores = self.errores_al_cambiar(cambio)
        self.assertTrue(any("BOND1" in e for e in errores))

    def test_origen_desconocido(self):
        def cambio(libro):
            libro["Lotes"]["C5"] = "Otro"

        self.assertTrue(self.errores_al_cambiar(cambio))

    def test_ticker_repetido(self):
        def cambio(libro):
            libro["Cartera"]["A6"] = "AAA"

        self.assertTrue(self.errores_al_cambiar(cambio))

    def test_informa_todos_los_errores_juntos(self):
        def cambio(libro):
            libro["Lotes"]["B5"] = 61
            libro["Cartera"]["E8"] = 1

        errores = self.errores_al_cambiar(cambio)
        self.assertGreaterEqual(len(errores), 2)


class Calculos(unittest.TestCase):
    def setUp(self):
        self.punto = cargar_punto_partida(DEMO)

    def resultado(self, ticker, precio, dia_cero=None):
        return resultado_posicion(
            posicion_de(self.punto, ticker), lotes_de(self.punto, ticker), precio, dia_cero
        )

    def test_valuacion_por_unidad(self):
        self.assertAlmostEqual(valuacion(100, 1200, 1), 120000)

    def test_valuacion_cada_100_nominales(self):
        self.assertAlmostEqual(valuacion(1000, 160000, 100), 1600000)

    def test_estados_de_costo(self):
        esperados = {
            "AAA": "extracto",
            "BBB": "mixto",
            "CCC": "estimado",
            "BOND1": "incompleto",
            "ONX": "incompleto",
        }
        for ticker, estado in esperados.items():
            self.assertEqual(estado_costo(lotes_de(self.punto, ticker)), estado, ticker)

    def test_costo_total(self):
        self.assertAlmostEqual(costo_total(lotes_de(self.punto, "BBB")), 51000)

    def test_costo_parcial_no_se_usa(self):
        self.assertIsNone(costo_total(lotes_de(self.punto, "ONX")))

    def test_resultado_con_costo_completo(self):
        r = self.resultado("AAA", 1200)
        self.assertAlmostEqual(r.valuacion, 120000)
        self.assertAlmostEqual(r.costo, 104600)
        self.assertAlmostEqual(r.resultado, 15400)
        self.assertAlmostEqual(r.resultado_pct, 15400 / 104600)
        self.assertEqual(r.estado_costo, "extracto")

    def test_sin_costo_no_informa_resultado_pero_si_valuacion(self):
        r = self.resultado("BOND1", 160000)
        self.assertAlmostEqual(r.valuacion, 1600000)
        self.assertIsNone(r.costo)
        self.assertIsNone(r.resultado)
        self.assertIsNone(r.resultado_pct)

    def test_sin_precio_no_informa_un_cero(self):
        r = self.resultado("AAA", None)
        self.assertIsNone(r.valuacion)
        self.assertIsNone(r.resultado)
        self.assertIsNone(r.resultado_dia_cero)

    def test_resultado_desde_el_dia_cero_no_necesita_costo(self):
        r = self.resultado("BOND1", 160000, dia_cero=150000)
        self.assertAlmostEqual(r.resultado_dia_cero, 100000)
        self.assertAlmostEqual(r.resultado_dia_cero_pct, 160000 / 150000 - 1)

    def test_sin_dia_cero(self):
        r = self.resultado("AAA", 1200)
        self.assertIsNone(r.resultado_dia_cero)
        self.assertIsNone(r.resultado_dia_cero_pct)

    def test_resumen_no_mezcla_posiciones_sin_costo(self):
        resultados = [self.resultado("AAA", 1200), self.resultado("BOND1", 160000), self.resultado("CCC", None)]
        resumen = resumen_cartera(resultados)
        self.assertAlmostEqual(resumen.valuacion_total, 1720000)
        self.assertAlmostEqual(resumen.valuacion_comparable, 120000)
        self.assertAlmostEqual(resumen.costo_comparable, 104600)
        self.assertAlmostEqual(resumen.resultado_comparable, 15400)
        self.assertEqual(resumen.posiciones_sin_costo, ["BOND1"])
        self.assertEqual(resumen.posiciones_sin_precio, ["CCC"])


class LineaDeComandos(unittest.TestCase):
    def correr(self, datos, *argumentos):
        entorno = dict(os.environ, PYTHONPATH=str(RAIZ / "src"))
        return subprocess.run(
            [sys.executable, "-m", "cartera", "--datos", str(datos), *argumentos],
            capture_output=True,
            text=True,
            env=entorno,
            timeout=30,
        )

    def test_importar_y_ver_estado(self):
        with tempfile.TemporaryDirectory() as carpeta:
            salida = self.correr(carpeta, "importar", "--cliente", "demo", "--archivo", str(DEMO))
            self.assertEqual(salida.returncode, 0, salida.stderr)
            cartera = Path(carpeta) / "clientes" / "demo" / "cartera.json"
            json.loads(cartera.read_text(encoding="utf-8"))

            estado = self.correr(carpeta, "estado", "--cliente", "demo")
            self.assertEqual(estado.returncode, 0, estado.stderr)
            self.assertIn("BOND1", estado.stdout)
            self.assertIn("falta estimar", estado.stdout.lower())
            self.assertIn("estimado", estado.stdout.lower())

    def test_error_de_validacion_no_escribe_nada(self):
        with tempfile.TemporaryDirectory() as carpeta:
            malo = Path(carpeta) / "malo.xlsx"
            libro = load_workbook(DEMO)
            libro["Lotes"]["B5"] = 61
            libro.save(malo)
            datos = Path(carpeta) / "datos"
            salida = self.correr(datos, "importar", "--cliente", "demo", "--archivo", str(malo))
            self.assertNotEqual(salida.returncode, 0)
            self.assertIn("AAA", salida.stdout + salida.stderr)
            self.assertFalse((datos / "clientes" / "demo" / "cartera.json").exists())


if __name__ == "__main__":
    unittest.main()
