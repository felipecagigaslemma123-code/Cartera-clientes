"""Controles de huecos, casos degenerados, privacidad y publicación del riesgo."""

import copy
import io
import json
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from datetime import date
from pathlib import Path
from unittest import mock

from cartera import riesgo
from cartera.__main__ import main
from test_etapa14_riesgo import armar_datos, cargar


class Integridad(unittest.TestCase):
    def test_un_precio_ausente_invalida_ambos_retornos(self):
        datos, historicos, cierre = cargar()
        original = riesgo.armar_riesgo(datos, historicos, cierre)
        # Un hueco de precio no se puede saltar para unir dos ruedas distantes.
        historicos["cedears/AAA"] = [f for f in historicos["cedears/AAA"] if f["date"] != "2026-11-02"]
        modelo = riesgo.armar_riesgo(datos, historicos, cierre)
        aaa = next(a for a in modelo["activos"] if a["ticker"] == "AAA")
        anterior = next(a for a in original["activos"] if a["ticker"] == "AAA")
        self.assertEqual(aaa["historia"]["n"], anterior["historia"]["n"] - 2)
        self.assertIsNone(aaa["ewma_anual"])

    def test_sin_negocio_no_hay_precio_para_riesgo(self):
        datos, historicos, cierre = cargar()
        for fila in historicos["cedears/AAA"]:
            if fila["date"] == "2026-11-02":
                fila["v"] = 0
        modelo = riesgo.armar_riesgo(datos, historicos, cierre)
        aaa = next(a for a in modelo["activos"] if a["ticker"] == "AAA")
        self.assertEqual(aaa["historia"]["n"], 250)
        self.assertEqual(aaa["excluidos"], [])

    def test_no_usa_datos_posteriores_al_tablero(self):
        datos, historicos, cierre = cargar()
        original = riesgo.armar_riesgo(datos, historicos, cierre)
        for clave in ("bonds/AL30", "bonds/AL30C", "cedears/AAA", "cedears/SPY"):
            historicos[clave].append({"date": "2026-11-19", "c": 1.0, "v": 100})
        self.assertEqual(riesgo.armar_riesgo(datos, historicos, cierre), original)

    def test_duplicados_identicos_y_conflictivos(self):
        datos, historicos, cierre = cargar()
        original = riesgo.armar_riesgo(datos, historicos, cierre)
        fila = next(f for f in historicos["cedears/AAA"] if f["date"] == "2026-11-02")
        historicos["cedears/AAA"].append(copy.deepcopy(fila))
        self.assertEqual(riesgo.armar_riesgo(datos, historicos, cierre), original)
        historicos["cedears/AAA"].append(dict(fila, c=fila["c"] * 1.1))
        modelo = riesgo.armar_riesgo(datos, historicos, cierre)
        aaa = next(a for a in modelo["activos"] if a["ticker"] == "AAA")
        self.assertEqual(aaa["historia"]["n"], 250)

    def test_historias_suficientes_sin_interseccion_suficiente(self):
        datos, historicos, cierre = cargar()
        datos["posiciones"] = datos["posiciones"][:2]
        historicos["cedears/BBB"] = copy.deepcopy(historicos["cedears/AAA"])
        historicos["cedears/AAA"] = [f for f in historicos["cedears/AAA"] if f["date"] != "2026-11-02"]
        historicos["cedears/BBB"] = [f for f in historicos["cedears/BBB"] if f["date"] != "2026-11-10"]
        modelo = riesgo.armar_riesgo(datos, historicos, cierre, {"minimo": 250})
        self.assertTrue(all(a["historia"]["estado"] == "suficiente" for a in modelo["activos"]))
        self.assertEqual(modelo["cartera"]["filas"], 248)
        self.assertEqual(modelo["cartera"]["estado"], "sin_dato")
        self.assertIsNone(modelo["cartera"]["var95_usd"])

    def test_sin_mercado_conserva_volatilidad_y_explica_beta_ausente(self):
        datos, historicos, cierre = cargar()
        historicos["cedears/SPY"] = None
        modelo = riesgo.armar_riesgo(datos, historicos, cierre)
        self.assertIsNone(modelo["cartera"]["beta"])
        self.assertIsNotNone(modelo["cartera"]["vol_anual"])
        self.assertTrue(any("SPY" in a and "beta" in a for a in modelo["avisos"]))

    def test_sin_convexidad_no_inventa_escenarios(self):
        datos, historicos, cierre = cargar()
        cierre["informes"]["titulos_publicos"]["rows"][0]["cx"] = None
        modelo = riesgo.armar_riesgo(datos, historicos, cierre)
        familia = next(f for f in modelo["renta_fija"] if f["familia"] == "USD")
        self.assertIsNone(familia["cx"])
        self.assertTrue(all(v is None for v in familia["escenarios"].values()))
        self.assertAlmostEqual(familia["dv01_ars"], 55.5)
        self.assertTrue(any("convexidad" in a for a in modelo["avisos"]))

    def test_sin_valor_total_no_publica_pesos_inventados(self):
        datos, historicos, cierre = cargar()
        for posicion in datos["posiciones"]:
            posicion["valuacion"] = 0.0
        modelo = riesgo.armar_riesgo(datos, historicos, cierre)
        self.assertTrue(all(a["peso"] is None for a in modelo["activos"]))
        self.assertIsNone(modelo["concentracion"]["herfindahl"])
        self.assertEqual(modelo["cartera"]["estado"], "sin_dato")
        json.dumps(modelo, allow_nan=False)
        self.assertNotIn("None", riesgo.riesgo_html(modelo))

    def test_parametros_no_modifican_los_defaults(self):
        datos, historicos, cierre = cargar()
        modelo = riesgo.armar_riesgo(datos, historicos, cierre, {"escenarios_pb": [-50, 50]})
        modelo["parametros"]["escenarios_pb"].append(500)
        self.assertEqual(riesgo.PARAMETROS["escenarios_pb"], [-200, -100, 100, 200])
        for parametros in ({"lambda_ewma": 1.0}, {"minimo": 1}, {"ventana": True}, {"confianza": float("nan")}):
            with self.subTest(parametros=parametros), self.assertRaises(riesgo.ErrorRiesgo):
                riesgo.armar_riesgo(datos, historicos, cierre, parametros)

    def test_html_escapa_textos_y_no_confunde_faltantes_con_cero(self):
        datos, historicos, cierre = cargar()
        datos["cliente"]["nombre"] = '<script>alert("hola")</script>'
        html = riesgo.riesgo_html(riesgo.armar_riesgo(datos, historicos, cierre))
        self.assertNotIn("<script>", html)
        self.assertIn("&lt;script&gt;", html)
        for titulo in ("Cómo leerlo", "Cartera", "Quién explica el riesgo", "Por especie", "Renta fija", "Fuera del cálculo"):
            self.assertIn(titulo, html)
        self.assertIn("sin dato", html)


class CacheYComando(unittest.TestCase):
    def test_copia_de_hoy_se_evalua_en_hora_argentina(self):
        with tempfile.TemporaryDirectory() as temporal:
            cache = Path(temporal)
            (cache / "cedears_AAA.json").write_text(json.dumps({
                "consultado_en": "2026-11-19T01:00:00+00:00", "respuesta": []}), encoding="utf-8")
            fetch = mock.Mock()
            historicos, avisos = riesgo.descargar_historicos(
                ["cedears/AAA"], cache, fetch=fetch, hoy=date(2026, 11, 18))
            fetch.assert_not_called()
            self.assertEqual(historicos["cedears/AAA"], [])
            self.assertEqual(avisos, [])

    def test_pausa_solo_entre_consultas_y_sin_duplicados(self):
        with tempfile.TemporaryDirectory() as temporal:
            fetch = mock.Mock(return_value={"Error": "no hay historia"})
            with mock.patch.object(riesgo.time, "sleep") as pausa:
                riesgo.descargar_historicos(["cedears/AAA", "cedears/AAA", "cedears/BBB", "stocks/CCC"],
                                            temporal, fetch=fetch, hoy=date(2026, 11, 18))
            self.assertEqual(fetch.call_count, 3)
            self.assertEqual(pausa.call_args_list, [mock.call(0.5), mock.call(0.5)])

    def test_claves_no_permiten_salir_de_la_cache(self):
        with tempfile.TemporaryDirectory() as temporal:
            fetch = mock.Mock()
            with self.assertRaises(riesgo.ErrorRiesgo):
                riesgo.descargar_historicos(["bonds/../../otro"], temporal, fetch=fetch)
            fetch.assert_not_called()

    def correr(self, base, *argumentos):
        salida, errores = io.StringIO(), io.StringIO()
        with redirect_stdout(salida), redirect_stderr(errores):
            codigo = main(["--datos", str(base), "riesgo", "--cliente", "demo"] + list(argumentos))
        return codigo, salida.getvalue(), errores.getvalue()

    def test_bloque_invalido_no_escribe_ni_consulta(self):
        with tempfile.TemporaryDirectory() as temporal:
            base = Path(temporal)
            armar_datos(base)
            tablero = base / "clientes" / "demo" / "dashboard.html"
            tablero.write_text('<script id="datos-cartera">{"posiciones": []}</script>', encoding="utf-8")
            with mock.patch.object(riesgo, "consultar_json") as fetch:
                codigo, _, errores = self.correr(base)
            self.assertEqual(codigo, 1)
            self.assertIn("generado_en", errores)
            fetch.assert_not_called()
            self.assertFalse((tablero.parent / "riesgo").exists())

    def test_sin_ccl_no_modifica_tampoco_la_cache(self):
        with tempfile.TemporaryDirectory() as temporal:
            base = Path(temporal)
            cache = armar_datos(base)
            (cache / "bonds_AL30C.json").unlink()
            anteriores = {r: r.read_bytes() for r in base.rglob("*") if r.is_file()}
            _, historicos, _ = cargar()

            def fetch(url):
                clave = url.split("historical/")[1]
                if clave == "bonds/AL30C":
                    raise OSError("sin red")
                return historicos.get(clave, {"Error": "no hay historia"})

            with mock.patch.object(riesgo, "_hoy", return_value=date(2026, 11, 20)), \
                    mock.patch.object(riesgo, "consultar_json", side_effect=fetch), \
                    mock.patch.object(riesgo.time, "sleep"):
                codigo, _, errores = self.correr(base)
            self.assertEqual(codigo, 1)
            self.assertIn("AL30", errores)
            self.assertEqual({r: r.read_bytes() for r in base.rglob("*") if r.is_file()}, anteriores)

    def test_reemplaza_salidas_de_la_misma_fecha_y_no_requiere_base(self):
        with tempfile.TemporaryDirectory() as temporal:
            base = Path(temporal)
            armar_datos(base)
            destino = base / "clientes" / "demo" / "riesgo"
            destino.mkdir()
            (destino / "riesgo-2026-11-18.html").write_text("anterior", encoding="utf-8")
            with mock.patch.object(riesgo, "_hoy", return_value=date(2026, 11, 18)):
                codigo, salida, errores = self.correr(base, "--sin-red")
            self.assertEqual(codigo, 0, errores)
            self.assertIn("67,0 %", salida)
            self.assertIn("<!doctype html>", (destino / "riesgo-2026-11-18.html").read_text(encoding="utf-8"))
            self.assertEqual(len(list(destino.iterdir())), 2)
            self.assertFalse((destino.parent / "cartera.json").exists())


if __name__ == "__main__":
    unittest.main()
