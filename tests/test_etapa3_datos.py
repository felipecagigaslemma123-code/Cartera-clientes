import csv
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
from zoneinfo import ZoneInfo

from cartera.__main__ import main
from cartera.almacenamiento import importar_cartera
from cartera.calculos import resultado_posicion, resumen_cartera
from cartera.dashboard import generar_html
from cartera.precios import Cotizacion
from cartera.punto_partida import cargar_punto_partida

DEMO = Path(__file__).resolve().parents[1] / "fixtures" / "punto_partida_demo.xlsx"
T = dt.datetime(2026, 11, 4, 17, 5, tzinfo=ZoneInfo("America/Argentina/Buenos_Aires"))
PRECIOS = {"AAA": 1200.0, "BBB": 1100.0, "CCC": 2500.0, "BOND1": 160000.0, "NOTE1": 110.0}
DIA_CERO = {
    "esquema_version": 2, "fecha": "2026-11-04", "fijado_en": "2026-11-04T17:05:00-03:00",
    "cantidades": {"AAA": 100.0, "BBB": 50.0, "CCC": 10.0, "BOND1": 1000.0, "NOTE1": 200000.0, "ONX": 500.0},
    "precios": {"AAA": 1000.0, "BBB": 1000.0, "CCC": 2000.0, "BOND1": 150000.0, "NOTE1": 100.0, "ONX": 140000.0},
    "mep": 1500.0, "efectivo": {"fecha": "2026-11-04", "ARS": -1000.0, "USD": 10.0},
}


def datos_de(html):
    coincidencia = re.search(r'<script id="datos-cartera" type="application/json">(.*?)</script>', html, re.S)
    if coincidencia is None:
        raise AssertionError("No se encontró el bloque de datos")
    return json.loads(coincidencia.group(1))


def cot(ticker, precio, estado="vivo"):
    return Cotizacion(ticker=ticker, ultimo=precio, bid=None if precio is None else precio - 1,
                      ask=None if precio is None else precio + 1,
                      pct_dia=None if precio is None else 1.5, estado=estado, consultado_en=T)


class Generar(unittest.TestCase):
    def setUp(self):
        self.punto = cargar_punto_partida(DEMO)

    def generar(self, dia_cero=DIA_CERO, mep=True, instrumentos=None, especie=None):
        if especie:
            self.punto.posiciones[0].especie = especie
        resultados = [
            resultado_posicion(p, [l for l in self.punto.lotes if l.ticker == p.ticker], PRECIOS.get(p.ticker),
                               dia_cero["precios"][p.ticker] if dia_cero else None)
            for p in self.punto.posiciones
        ]
        cotizaciones = {t: cot(t, p) for t, p in PRECIOS.items()}
        cotizaciones["ONX"] = cot("ONX", None, "sin_dato")
        return generar_html(
            cliente={"slug": "demo", "nombre": "Cliente Demo"},
            resultados=resultados,
            resumen=resumen_cartera(resultados),
            cotizaciones=cotizaciones,
            niveles={"AAA": {"take_profit": 1500.0, "stop_loss": None}},
            instrumentos=instrumentos if instrumentos is not None else {},
            efectivo={"fecha": "2026-11-04", "ARS": None, "USD": 10.0, "nota": ""},
            historial={"AAA": [(T - dt.timedelta(days=1), 1100.0), (T, 1200.0)]},
            generado_en=T,
            posiciones=self.punto.posiciones,
            dia_cero=dia_cero,
            mep=cot("MEP", 1500.0) if mep else None,
        )

    def posicion(self, html, ticker):
        return next(p for p in datos_de(html)["posiciones"] if p["ticker"] == ticker)

    def test_incluye_lo_necesario_para_recalcular(self):
        p = self.posicion(self.generar(), "BOND1")
        self.assertEqual(p["cantidad"], 1000)
        self.assertEqual(p["cotiza_cada"], 100)
        self.assertEqual(p["endpoint"], "arg_bonds")
        self.assertEqual(p["precio_dia_cero"], 150000.0)
        self.assertAlmostEqual(p["valuacion"], 1600000.0)

    def test_faltantes_son_null_y_nunca_cero(self):
        html = self.generar()
        onx = self.posicion(html, "ONX")
        self.assertIsNone(onx["ultimo"])
        self.assertIsNone(onx["valuacion"])
        self.assertIsNone(onx["costo"])
        self.assertEqual(onx["estado"], "sin_dato")
        self.assertIsNone(datos_de(html)["efectivo"]["ARS"])

    def test_costo_y_su_origen(self):
        html = self.generar()
        self.assertEqual(self.posicion(html, "AAA")["estado_costo"], "extracto")
        self.assertAlmostEqual(self.posicion(html, "AAA")["costo"], 104600.0)
        self.assertEqual(self.posicion(html, "BBB")["estado_costo"], "mixto")
        self.assertEqual(self.posicion(html, "BOND1")["estado_costo"], "incompleto")

    def test_niveles_nulos_se_conservan(self):
        aaa = self.posicion(self.generar(), "AAA")
        self.assertEqual(aaa["take_profit"], 1500.0)
        self.assertIsNone(aaa["stop_loss"])
        self.assertIsNone(self.posicion(self.generar(), "BBB")["take_profit"])

    def test_dia_cero_y_patrimonio(self):
        d = datos_de(self.generar())["dia_cero"]
        valuacion = 100000 + 50000 + 20000 + 1500000 + 200000 + 700000
        self.assertAlmostEqual(d["valuacion_posiciones"], valuacion)
        self.assertAlmostEqual(d["patrimonio_inicial"], valuacion - 1000 + 15000)
        self.assertEqual(d["faltantes"], [])

    def test_sin_dia_cero(self):
        html = self.generar(dia_cero=None)
        self.assertIsNone(datos_de(html)["dia_cero"])
        self.assertIsNone(self.posicion(html, "AAA")["precio_dia_cero"])

    def test_patrimonio_con_faltantes_no_informa_total(self):
        incompleto = dict(DIA_CERO, efectivo={"fecha": None, "ARS": None, "USD": None})
        d = datos_de(self.generar(dia_cero=incompleto))["dia_cero"]
        self.assertIsNone(d["patrimonio_inicial"])
        self.assertIn("efectivo ARS", d["faltantes"])

    def test_sin_mep(self):
        self.assertIsNone(datos_de(self.generar(mep=False))["mep"])

    def test_vencimientos_de_60_dias_y_vencidos(self):
        html = self.generar(instrumentos={
            "AAA": {"vencimiento": "2026-11-22"},
            "BBB": {"vencimiento": "2027-01-03"},
            "CCC": {"vencimiento": "2027-01-04"},
            "NOTE1": {"vencimiento": "2026-11-01"},
        })
        v = datos_de(html)["vencimientos"]
        self.assertEqual([x["ticker"] for x in v], ["NOTE1", "AAA", "BBB"])
        self.assertEqual(v[0]["dias"], -3)
        self.assertTrue(v[0]["vencida"])
        self.assertEqual(v[1]["dias"], 18)
        self.assertFalse(v[1]["vencida"])
        self.assertEqual(v[2]["dias"], 60)

    def test_un_texto_no_rompe_la_pagina(self):
        html = self.generar(especie="</script><script>alert(1)</script>")
        self.assertEqual(self.posicion(html, "AAA")["especie"], "</script><script>alert(1)</script>")
        self.assertNotIn("<script>alert(1)", html)

    def test_incluye_la_politica_de_seguridad(self):
        html = self.generar()
        self.assertIn("Content-Security-Policy", html)
        self.assertIn("connect-src https://data912.com", html)

    def test_pide_paneles_y_no_especie_por_especie(self):
        html = self.generar()
        self.assertIn("/live/mep", html)
        self.assertNotRegex(html, r"data912\.com/live/[a-z_]+/[A-Za-z]")

    def test_no_usa_inner_html_ni_almacenamiento(self):
        html = self.generar()
        self.assertNotIn("innerHTML", html)
        self.assertNotIn("localStorage", html)

    def test_formato_argentino(self):
        self.assertIn("1.600.000", self.generar())

    def test_incluye_gráfico_y_aviso_de_historial(self):
        html = self.generar()
        self.assertIn("<svg", html)
        self.assertIn("sin historial suficiente", html.lower())

    def test_no_presenta_un_resultado_completo(self):
        minusculas = self.generar().lower()
        self.assertIn("se calcula cuando estén los movimientos", minusculas)
        self.assertNotIn("resultado de la cartera", minusculas)


class Comando(unittest.TestCase):
    PANELES = {
        "arg_cedears": [{"symbol": "AAA", "c": 1200.0, "px_bid": 1199.0, "px_ask": 1201.0, "pct_change": 1.0},
                        {"symbol": "BBB", "c": 1100.0}],
        "arg_stocks": [{"symbol": "CCC", "c": 2500.0}],
        "arg_bonds": [{"symbol": "BOND1", "c": 160000.0}],
        "arg_notes": [{"symbol": "NOTE1", "c": 110.0}],
        "arg_corp": [{"symbol": "ONX", "c": 150000.0}],
        "mep": [{"ticker": "AL30", "mark": 1500.0}],
    }

    def setUp(self):
        temporal = tempfile.TemporaryDirectory()
        self.addCleanup(temporal.cleanup)
        self.datos = Path(temporal.name) / "datos"
        importar_cartera(self.datos, "demo", DEMO)
        self.carpeta = self.datos / "clientes" / "demo"
        self.salida = self.carpeta / "dashboard.html"

    def correr(self, fetch=None):
        fetch = fetch or (lambda url: self.PANELES[url.rsplit("/", 1)[-1]])
        salida, errores = io.StringIO(), io.StringIO()
        with patch("cartera.__main__.consultar_json", side_effect=fetch):
            with redirect_stdout(salida), redirect_stderr(errores):
                codigo = main(["--datos", str(self.datos), "dashboard", "--cliente", "demo"])
        return codigo, salida.getvalue(), errores.getvalue()

    def test_genera_el_archivo_y_muestra_la_ruta(self):
        codigo, salida, errores = self.correr()
        self.assertEqual(codigo, 0, errores)
        self.assertIn("dashboard.html", salida)
        posiciones = datos_de(self.salida.read_text(encoding="utf-8"))["posiciones"]
        self.assertEqual(len(posiciones), 6)
        self.assertEqual(next(p for p in posiciones if p["ticker"] == "AAA")["estado"], "vivo")

    def test_solo_lo_lee_el_usuario(self):
        self.correr()
        self.assertEqual(stat.S_IMODE(self.salida.stat().st_mode) & 0o077, 0)

    def test_fuente_caida_genera_igual_y_marca(self):
        def caida(url):
            raise OSError("sin red")

        codigo, salida, _ = self.correr(caida)
        self.assertEqual(codigo, 0)
        self.assertIn("AAA", salida)
        posiciones = datos_de(self.salida.read_text(encoding="utf-8"))["posiciones"]
        self.assertTrue(all(p["estado"] == "sin_dato" and p["valuacion"] is None for p in posiciones))

    def test_usa_lo_guardado_si_hay_caida_despues(self):
        self.correr()

        def caida(url):
            raise OSError("sin red")

        self.correr(caida)
        posiciones = datos_de(self.salida.read_text(encoding="utf-8"))["posiciones"]
        aaa = next(p for p in posiciones if p["ticker"] == "AAA")
        self.assertEqual(aaa["estado"], "cache")
        self.assertEqual(aaa["ultimo"], 1200.0)

    def test_no_agrega_filas_al_historial(self):
        self.correr()
        self.assertFalse((self.carpeta / "historial.csv").exists())

    def test_lee_los_archivos_del_cliente(self):
        (self.carpeta / "perfil.json").write_text('{"slug": "demo", "nombre": "Nombre Visible"}', encoding="utf-8")
        (self.carpeta / "niveles.json").write_text('{"AAA": {"take_profit": 1500.0, "stop_loss": 900.0}}', encoding="utf-8")
        (self.carpeta / "instrumentos.json").write_text('{"BOND1": {"vencimiento": "2099-01-01"}}', encoding="utf-8")
        (self.carpeta / "efectivo.json").write_text('{"fecha": "2026-11-04", "ARS": 7.0, "USD": null}', encoding="utf-8")
        (self.carpeta / "dia_cero.json").write_text(json.dumps(DIA_CERO), encoding="utf-8")
        with (self.carpeta / "historial.csv").open("w", encoding="utf-8", newline="") as archivo:
            escritor = csv.writer(archivo)
            escritor.writerow(["consultado_en", "ticker", "ultimo", "bid", "ask"])
            escritor.writerow([T.isoformat(), "MEP", 1500.0, "", ""])
        self.correr()
        html = self.salida.read_text(encoding="utf-8")
        datos = datos_de(html)
        self.assertIn("Nombre Visible", html)
        aaa = next(p for p in datos["posiciones"] if p["ticker"] == "AAA")
        self.assertEqual((aaa["take_profit"], aaa["stop_loss"], aaa["precio_dia_cero"]), (1500.0, 900.0, 1000.0))
        self.assertEqual(next(p for p in datos["posiciones"] if p["ticker"] == "BOND1")["vencimiento"], "2099-01-01")
        self.assertEqual(datos["efectivo"]["ARS"], 7.0)
        self.assertEqual(datos["dia_cero"]["fecha"], "2026-11-04")
        self.assertEqual(datos["mep"]["ultimo"], 1500.0)
        self.assertNotIn("MEP", [p["ticker"] for p in datos["posiciones"]])

    def test_sin_base_falla_sin_escribir(self):
        salida, errores = io.StringIO(), io.StringIO()
        with redirect_stdout(salida), redirect_stderr(errores):
            codigo = main(["--datos", str(self.datos), "dashboard", "--cliente", "otro"])
        self.assertNotEqual(codigo, 0)
        self.assertFalse((self.datos / "clientes" / "otro" / "dashboard.html").exists())


if __name__ == "__main__":
    unittest.main()
