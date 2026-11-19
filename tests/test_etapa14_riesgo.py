"""Etapa 14: riesgo de la cartera (docs/RIESGO.md).

El esperado sale de una implementación de referencia de Claude con las funciones comprobadas de
tools/riesgo/riesgo_ref.py, y reproduce el análisis de carteras reales del 18/11/2026.
"""

import copy
import datetime as dt
import io
import json
import math
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest import mock

from cartera import riesgo
from cartera.__main__ import main
from cartera.riesgo import (EVENTOS_CONOCIDOS, PARAMETROS, ErrorRiesgo, armar_riesgo, descargar_historicos,
                            historicos_necesarios, riesgo_html, segmento_historico)

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "riesgo"
TOL = 1e-9


def cargar():
    datos = json.loads((FIXTURES / "datos.json").read_text(encoding="utf-8"))
    historicos = {}
    for ruta in (FIXTURES / "historicos").glob("*.json"):
        segmento, ticker = ruta.stem.split("_", 1)
        historicos[segmento + "/" + ticker] = json.loads(ruta.read_text(encoding="utf-8"))
    cierre = json.loads((FIXTURES / "cierre_iamc.json").read_text(encoding="utf-8"))
    return datos, historicos, cierre


ESPERADO = json.loads((FIXTURES / "esperado.json").read_text(encoding="utf-8"))


class Comparar(unittest.TestCase):
    def igual(self, real, esperado, ruta="modelo"):
        if isinstance(esperado, float) and not isinstance(real, bool):
            self.assertIsInstance(real, (int, float), ruta)
            self.assertTrue(math.isclose(real, esperado, rel_tol=TOL, abs_tol=1e-12),
                            "{}: {} != {}".format(ruta, real, esperado))
        elif isinstance(esperado, dict):
            self.assertIsInstance(real, dict, ruta)
            self.assertEqual(set(real), set(esperado), ruta)
            for clave in esperado:
                self.igual(real[clave], esperado[clave], ruta + "." + str(clave))
        elif isinstance(esperado, list):
            self.assertIsInstance(real, (list, tuple), ruta)
            self.assertEqual(len(real), len(esperado), ruta)
            for i, (a, b) in enumerate(zip(real, esperado)):
                self.igual(a, b, "{}[{}]".format(ruta, i))
        else:
            self.assertEqual(real, esperado, ruta)


class Basicos(unittest.TestCase):
    def test_segmentos(self):
        self.assertEqual(segmento_historico("arg_cedears"), "cedears")
        self.assertEqual(segmento_historico("arg_stocks"), "stocks")
        self.assertEqual(segmento_historico("arg_bonds"), "bonds")
        self.assertIsNone(segmento_historico("arg_notes"))
        self.assertIsNone(segmento_historico("arg_corp"))
        self.assertIsNone(segmento_historico(None))

    def test_historicos_necesarios(self):
        datos, _, _ = cargar()
        self.assertEqual(historicos_necesarios(datos), [
            "bonds/AL30", "bonds/AL30C", "cedears/SPY", "cedears/AAA", "cedears/BBB", "stocks/CCC",
            "cedears/DDD", "bonds/BON", "cedears/NOV"])

    def test_parametros_y_eventos(self):
        self.assertEqual(PARAMETROS["ventana"], 252)
        self.assertEqual(PARAMETROS["minimo"], 126)
        self.assertEqual(PARAMETROS["confianza"], 0.95)
        self.assertEqual(PARAMETROS["lambda_ewma"], 0.94)
        self.assertEqual(PARAMETROS["escenarios_pb"], [-200, -100, 100, 200])
        self.assertIn(("SPY", "2026-05-29"), EVENTOS_CONOCIDOS)


class Modelo(Comparar):
    def test_coincide_con_el_esperado(self):
        datos, historicos, cierre = cargar()
        self.igual(armar_riesgo(datos, historicos, cierre), ESPERADO)

    def test_es_serializable_y_puro(self):
        datos, historicos, cierre = cargar()
        copia = copy.deepcopy((datos, historicos, cierre))
        modelo = armar_riesgo(datos, historicos, cierre)
        json.dumps(modelo, ensure_ascii=False)
        self.assertEqual((datos, historicos, cierre), copia)

    def test_reglas_visibles_en_el_esperado(self):
        m = ESPERADO
        estados = {a["ticker"]: a["historia"]["estado"] for a in m["activos"]}
        self.assertEqual(estados, {"AAA": "suficiente", "BBB": "suficiente", "SPY": "suficiente",
                                   "BON": "suficiente", "CCC": "insuficiente", "DDD": "sin_serie",
                                   "ONX": "sin_fuente", "LCR": "sin_fuente"})
        self.assertNotIn("NOV", estados)
        self.assertIn("NOV: sin valuación; queda fuera de pesos y cálculos.", m["avisos"])
        spy = next(a for a in m["activos"] if a["ticker"] == "SPY")
        self.assertEqual(spy["excluidos"], [{"fecha": "2026-05-29", "motivo": "cambio de ratio 3:1"}])
        bbb = next(a for a in m["activos"] if a["ticker"] == "BBB")
        self.assertEqual(bbb["excluidos"][0]["fecha"], "2026-09-15")
        self.assertTrue(bbb["excluidos"][0]["motivo"].startswith("salto de +"))
        bon = next(a for a in m["activos"] if a["ticker"] == "BON")
        self.assertTrue(all("pago del" in e["motivo"] for e in bon["excluidos"]))
        self.assertIn("2026-07-06", [e["fecha"] for e in bon["excluidos"]])
        self.assertEqual(m["cartera"]["incluidos"], ["AAA", "BBB", "BON", "SPY"])
        self.assertAlmostEqual(m["cartera"]["cobertura_patrimonial"], 0.67)
        self.assertEqual({e["ticker"] for e in m["cartera"]["excluidos"]}, {"CCC", "DDD", "ONX", "LCR"})
        self.assertAlmostEqual(sum(c["fraccion"] for c in m["cartera"]["contribuciones"]), 1.0)
        self.assertEqual([r["familia"] for r in m["renta_fija"]], ["USD", "CER"])
        self.assertAlmostEqual(m["renta_fija"][0]["dv01_ars"], 120000 * 3.2e-4 + 90000 * 1.9e-4)

    def test_dato_faltante_nunca_es_cero(self):
        ddd = next(a for a in ESPERADO["activos"] if a["ticker"] == "DDD")
        for clave in ("vol_anual", "ewma_anual", "beta", "var95_usd", "es95_usd"):
            self.assertIsNone(ddd[clave])

    def test_sin_respuesta_de_data912(self):
        datos, historicos, cierre = cargar()
        historicos["cedears/AAA"] = None
        m = armar_riesgo(datos, historicos, cierre)
        aaa = next(a for a in m["activos"] if a["ticker"] == "AAA")
        self.assertEqual(aaa["historia"]["estado"], "sin_serie")
        self.assertEqual(aaa["historia"]["motivo"], "no se pudo consultar data912")
        self.assertNotIn("AAA", m["cartera"]["incluidos"])

    def test_sin_ccl_es_error(self):
        datos, historicos, cierre = cargar()
        historicos["bonds/AL30C"] = {"Error": "Nahh no tengo ese ticker loko"}
        with self.assertRaises(ErrorRiesgo):
            armar_riesgo(datos, historicos, cierre)

    def test_sin_cierre_iamc(self):
        datos, historicos, _ = cargar()
        m = armar_riesgo(datos, historicos, None)
        self.assertEqual(m["renta_fija"], [])
        self.assertTrue(all(a["renta_fija"] is None for a in m["activos"]))
        self.assertTrue(any("IAMC" in aviso for aviso in m["avisos"]))
        # Sin cierre no se conocen los pagos del bono: no se excluyen esas ruedas, pero sí el resto.
        self.assertEqual(m["cartera"]["estado"], "calculada")
        bon = next(a for a in m["activos"] if a["ticker"] == "BON")
        self.assertEqual(bon["excluidos"], [])
        spy = next(a for a in m["activos"] if a["ticker"] == "SPY")
        self.assertEqual(spy["excluidos"], [{"fecha": "2026-05-29", "motivo": "cambio de ratio 3:1"}])

    def test_minimos_configurables(self):
        datos, historicos, cierre = cargar()
        m = armar_riesgo(datos, historicos, cierre, {"minimo_cola": 400})
        self.assertEqual(m["var_historico"]["estado"], "sin_dato")
        self.assertEqual(m["var_historico"]["motivo"], "314 ruedas comunes; el mínimo es 400")
        self.assertEqual(m["parametros"]["minimo_cola"], 400)
        m = armar_riesgo(datos, historicos, cierre, {"minimo": 300})
        self.assertEqual(m["cartera"]["estado"], "sin_dato")
        self.assertEqual(m["cartera"]["incluidos"], [])
        self.assertEqual(m["cartera"]["motivo"], "ninguna posición tiene historia suficiente")


class Html(unittest.TestCase):
    def test_reporte(self):
        html = riesgo_html(ESPERADO)
        self.assertTrue(html.lower().lstrip().startswith("<!doctype html>"))
        self.assertIn('charset="utf-8"', html.lower())
        self.assertNotIn("http", html.lower())
        self.assertIn("Cliente Demo Riesgo", html)
        self.assertIn("USD CCL", html)
        for ticker in ("AAA", "BBB", "BON", "SPY", "CCC", "DDD", "ONX", "LCR"):
            self.assertIn(ticker, html)
        self.assertIn("sin dato", html)
        self.assertIn("data912 no tiene su historia", html)
        self.assertIn("cambio de ratio 3:1", html)
        self.assertIn("67,0 %", html)                 # patrimonio medido
        self.assertIn("NOV: sin valuación", html)
        self.assertRegex(html, r"CER")
        self.assertNotRegex(html, r"\d,\d{3}\.\d")     # nada de formato inglés
        self.assertNotIn("None", html)
        self.assertNotIn("NaN", html)


def armar_datos(base):
    datos, historicos, cierre = cargar()
    carpeta = base / "clientes" / "demo"
    carpeta.mkdir(parents=True)
    (carpeta / "dashboard.html").write_text(
        '<!doctype html><html><body><script id="datos-cartera" type="application/json">{}</script>'
        "</body></html>".format(json.dumps(datos, ensure_ascii=False)), encoding="utf-8")
    cierres = base / "iamc" / "cierres"
    cierres.mkdir(parents=True)
    (cierres / "2026-11-17.json").write_text(json.dumps(cierre), encoding="utf-8")
    posterior = {"fecha_cierre": "2026-11-19", "informes": {}}   # posterior al dashboard: no se usa
    (cierres / "2026-11-19.json").write_text(json.dumps(posterior), encoding="utf-8")
    cache = base / "cache" / "data912" / "historicos"
    cache.mkdir(parents=True)
    for clave, respuesta in historicos.items():
        (cache / (clave.replace("/", "_") + ".json")).write_text(
            json.dumps({"consultado_en": "2026-11-18T10:00:00-03:00", "respuesta": respuesta}), encoding="utf-8")
    return cache


class Descarga(unittest.TestCase):
    def test_usa_la_copia_de_hoy_y_consulta_la_vieja(self):
        with tempfile.TemporaryDirectory() as t:
            cache = armar_datos(Path(t))
            pedidos = []

            def fetch(url):
                pedidos.append(url)
                return {"Error": "Nahh no tengo ese ticker loko"}

            with mock.patch.object(riesgo.time, "sleep"):
                hist, avisos = descargar_historicos(["cedears/AAA", "cedears/NOV"], cache, fetch=fetch,
                                                    hoy=dt.date(2026, 11, 18))
            self.assertEqual(pedidos, ["https://data912.com/historical/cedears/NOV"])
            self.assertIsInstance(hist["cedears/AAA"], list)
            self.assertEqual(hist["cedears/NOV"], {"Error": "Nahh no tengo ese ticker loko"})
            guardado = json.loads((cache / "cedears_NOV.json").read_text(encoding="utf-8"))
            self.assertEqual(guardado["respuesta"], {"Error": "Nahh no tengo ese ticker loko"})

            pedidos.clear()
            with mock.patch.object(riesgo.time, "sleep"):
                hist, _ = descargar_historicos(["cedears/AAA"], cache, fetch=fetch, hoy=dt.date(2026, 11, 19))
            self.assertEqual(pedidos, ["https://data912.com/historical/cedears/AAA"])

    def test_falla_de_red(self):
        with tempfile.TemporaryDirectory() as t:
            cache = armar_datos(Path(t))

            def fetch(url):
                raise OSError("sin red")

            with mock.patch.object(riesgo.time, "sleep"):
                hist, avisos = descargar_historicos(["cedears/AAA", "cedears/ZZZ"], cache, fetch=fetch,
                                                    hoy=dt.date(2026, 11, 20))
            self.assertIsInstance(hist["cedears/AAA"], list)       # copia vieja con aviso
            self.assertIsNone(hist["cedears/ZZZ"])
            self.assertTrue(any("AAA" in a for a in avisos))
            self.assertTrue(any("ZZZ" in a for a in avisos))

    def test_sin_red(self):
        with tempfile.TemporaryDirectory() as t:
            cache = armar_datos(Path(t))
            fetch = mock.Mock()
            hist, _ = descargar_historicos(["cedears/AAA", "cedears/ZZZ"], cache, fetch=fetch,
                                           hoy=dt.date(2026, 12, 1), sin_red=True)
            fetch.assert_not_called()
            self.assertIsInstance(hist["cedears/AAA"], list)
            self.assertIsNone(hist["cedears/ZZZ"])


class Comando(Comparar):
    def correr(self, base, *extra):
        salida, errores = io.StringIO(), io.StringIO()
        with redirect_stdout(salida), redirect_stderr(errores):
            codigo = main(["--datos", str(base), "riesgo", "--cliente", "demo"] + list(extra))
        return codigo, salida.getvalue(), errores.getvalue()

    def test_escribe_json_y_html(self):
        with tempfile.TemporaryDirectory() as t:
            base = Path(t)
            armar_datos(base)
            with mock.patch.object(riesgo, "_hoy", return_value=dt.date(2026, 11, 18)):
                codigo, salida, errores = self.correr(base, "--sin-red")
            self.assertEqual(codigo, 0, errores)
            carpeta = base / "clientes" / "demo" / "riesgo"
            modelo = json.loads((carpeta / "riesgo-2026-11-18.json").read_text(encoding="utf-8"))
            esperado = copy.deepcopy(ESPERADO)
            # NOV no tiene copia guardada: el aviso de descarga se suma a los del modelo.
            self.assertTrue(set(esperado["avisos"]) <= set(modelo["avisos"]))
            modelo["avisos"] = esperado["avisos"]
            self.igual(modelo, esperado)
            html = (carpeta / "riesgo-2026-11-18.html").read_text(encoding="utf-8")
            self.assertIn("Cliente Demo Riesgo", html)
            self.assertIn("riesgo-2026-11-18.json", salida)
            self.assertIn("riesgo-2026-11-18.html", salida)

    def test_sin_dashboard_no_escribe(self):
        with tempfile.TemporaryDirectory() as t:
            base = Path(t)
            armar_datos(base)
            (base / "clientes" / "demo" / "dashboard.html").unlink()
            codigo, _, errores = self.correr(base, "--sin-red")
            self.assertNotEqual(codigo, 0)
            self.assertTrue(errores.strip())
            self.assertFalse((base / "clientes" / "demo" / "riesgo").exists())

    def test_sin_ccl_no_escribe(self):
        with tempfile.TemporaryDirectory() as t:
            base = Path(t)
            cache = armar_datos(base)
            (cache / "bonds_AL30C.json").unlink()
            codigo, _, errores = self.correr(base, "--sin-red")
            self.assertNotEqual(codigo, 0)
            self.assertIn("AL30", errores)
            self.assertFalse((base / "clientes" / "demo" / "riesgo").exists())


if __name__ == "__main__":
    unittest.main()
