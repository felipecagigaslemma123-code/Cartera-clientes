"""Comandos de precios y día cero, con datos ficticios y sin consultas de red."""

import copy
import csv
import datetime as dt
import io
import json
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import patch
from zoneinfo import ZoneInfo

from cartera.__main__ import main
from cartera.almacenamiento import importar_cartera


DEMO = Path(__file__).resolve().parents[1] / "fixtures" / "punto_partida_demo.xlsx"
AR = ZoneInfo("America/Argentina/Buenos_Aires")


def fila(ticker, precio):
    return {"symbol": ticker, "c": precio, "px_bid": precio - 1,
            "px_ask": precio + 1, "pct_change": 1.5}


PANELES = {
    "arg_cedears": [fila("AAA", 1200.0), fila("BBB", 1100.0)],
    "arg_stocks": [fila("CCC", 2500.0)],
    "arg_bonds": [fila("BOND1", 160000.0)],
    "arg_notes": [fila("NOTE1", 110.0)],
    "arg_corp": [fila("ONX", 150000.0)],
    "mep": [{"ticker": "AL30", "mark": 1500.0, "bid": 1499.0, "ask": 1501.0}],
}


class ComandosPrecios(unittest.TestCase):
    def setUp(self):
        self.temporal = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporal.cleanup)
        self.raiz = Path(self.temporal.name)
        self.datos = self.raiz / "datos"
        self.cliente = self.datos / "clientes" / "demo"
        self.dia_cero = self.cliente / "dia_cero.json"
        self.hoy = dt.datetime.now(AR).date()

    def importar(self):
        importar_cartera(self.datos, "demo", DEMO)

    def ejecutar(self, comando, *argumentos, paneles=None):
        respuestas = copy.deepcopy(PANELES if paneles is None else paneles)
        llamadas = []

        def consultar(url):
            llamadas.append(url)
            endpoint = url.rsplit("/", 1)[-1]
            if endpoint not in respuestas:
                raise OSError("Servicio de demostración no disponible")
            return respuestas[endpoint]

        salida, errores = io.StringIO(), io.StringIO()
        with patch("cartera.__main__.consultar_json", side_effect=consultar), \
                redirect_stdout(salida), redirect_stderr(errores):
            try:
                codigo = main(["--datos", str(self.datos), comando, "--cliente", "demo", *argumentos])
            except SystemExit as error:
                codigo = error.code
        return codigo, salida.getvalue(), errores.getvalue(), llamadas

    def arbol(self):
        if not self.datos.exists():
            return {}
        return {str(ruta.relative_to(self.datos)): (ruta.read_bytes(), ruta.stat().st_mtime_ns)
                for ruta in self.datos.rglob("*") if ruta.is_file()}

    def leer_dia_cero(self):
        return json.loads(self.dia_cero.read_text(encoding="utf-8"))

    def efectivo(self, contenido):
        (self.cliente / "efectivo.json").write_text(json.dumps(contenido), encoding="utf-8")

    def test_tres_comandos_exigen_base_sin_consultar_ni_crear_datos(self):
        for comando, argumentos in (("capturar", ()), ("fijar-dia-cero", ()),
                                    ("efectivo-dia-cero", ("--ars=0", "--usd=0"))):
            with self.subTest(comando=comando):
                codigo, _, errores, llamadas = self.ejecutar(comando, *argumentos)
                self.assertNotEqual(codigo, 0)
                self.assertTrue(errores)
                self.assertEqual(llamadas, [])
                self.assertFalse(self.datos.exists())

    def test_capturar_agrega_seis_especies_y_mep_con_urls_genericas(self):
        self.importar()
        codigo, salida, errores, llamadas = self.ejecutar("capturar")
        self.assertEqual(codigo, 0, errores)
        with (self.cliente / "historial.csv").open(encoding="utf-8", newline="") as archivo:
            filas = list(csv.DictReader(archivo))
        self.assertEqual(len(filas), 7)
        self.assertEqual({fila["ticker"] for fila in filas}, {"AAA", "BBB", "CCC", "BOND1", "NOTE1", "ONX", "MEP"})
        self.assertRegex(salida, r"\b7\b")
        self.assertEqual(set(llamadas), {"https://data912.com/live/" + endpoint for endpoint in PANELES})
        self.assertEqual(len(llamadas), len(set(llamadas)))
        for registro in filas:
            self.assertIsNotNone(dt.datetime.fromisoformat(registro["consultado_en"]).utcoffset())
        self.assertEqual(float(next(fila for fila in filas if fila["ticker"] == "MEP")["ultimo"]), 1500.0)

    def test_capturar_lista_cache_y_no_la_agrega_como_observacion_nueva(self):
        self.importar()
        self.assertEqual(self.ejecutar("capturar")[0], 0)
        paneles = copy.deepcopy(PANELES)
        paneles["arg_cedears"] = {"Error": "panel caído"}
        codigo, salida, errores, _ = self.ejecutar("capturar", paneles=paneles)
        self.assertEqual(codigo, 0, errores)
        self.assertIn("AAA", salida)
        self.assertIn("BBB", salida)
        self.assertIn("cache", salida.lower())
        with (self.cliente / "historial.csv").open(encoding="utf-8", newline="") as archivo:
            filas = list(csv.DictReader(archivo))
        self.assertEqual(len(filas), 12)  # Siete iniciales y cinco nuevas, sin AAA/BBB.
        self.assertEqual(sum(fila["ticker"] == "AAA" for fila in filas), 1)

    def test_capturar_sin_cotizaciones_vivas_falla_e_identifica_faltantes(self):
        self.importar()
        codigo, salida, errores, _ = self.ejecutar("capturar", paneles={})
        self.assertNotEqual(codigo, 0)
        texto = salida + errores
        for ticker in ("AAA", "BBB", "CCC", "BOND1", "NOTE1", "ONX"):
            self.assertIn(ticker, texto)
        if (self.cliente / "historial.csv").exists():
            with (self.cliente / "historial.csv").open(encoding="utf-8", newline="") as archivo:
                self.assertEqual(list(csv.DictReader(archivo)), [])

    def test_capturar_advierte_posible_unidad_sin_modificar_costos(self):
        self.importar()
        base = (self.cliente / "cartera.json").read_bytes()
        paneles = copy.deepcopy(PANELES)
        paneles["arg_cedears"][0] = fila("AAA", 100000.0)
        codigo, salida, errores, _ = self.ejecutar("capturar", paneles=paneles)
        self.assertEqual(codigo, 0, errores)
        self.assertIn("AAA", salida)
        self.assertIn("advertencia", salida.lower())
        self.assertTrue("unidad" in salida.lower() or "moneda" in salida.lower())
        self.assertEqual((self.cliente / "cartera.json").read_bytes(), base)

    def test_fijar_guarda_cantidades_efectivo_y_fecha_argentina_sin_costos_completos(self):
        self.importar()
        self.efectivo({"fecha": self.hoy.isoformat(), "ARS": 1000.0, "USD": 10.0})
        codigo, salida, errores, _ = self.ejecutar("fijar-dia-cero")
        self.assertEqual(codigo, 0, errores)
        foto = self.leer_dia_cero()
        self.assertEqual(foto["fecha"], self.hoy.isoformat())
        self.assertEqual(foto["esquema_version"], 2)
        self.assertEqual(foto["cantidades"], {"AAA": 100, "BBB": 50, "CCC": 10, "BOND1": 1000, "NOTE1": 200000, "ONX": 500})
        self.assertEqual(foto["efectivo"], {"fecha": self.hoy.isoformat(), "ARS": 1000.0, "USD": 10.0})
        self.assertEqual(foto["mep"], 1500.0)
        self.assertIn("patrimonio", salida.lower())
        self.assertIn("2.786.000,00", salida)

    def test_fecha_futura_falla_antes_de_consultar_o_escribir(self):
        self.importar()
        antes = self.arbol()
        futura = (self.hoy + dt.timedelta(days=1)).isoformat()
        codigo, _, errores, llamadas = self.ejecutar("fijar-dia-cero", "--fecha", futura)
        self.assertNotEqual(codigo, 0)
        self.assertTrue(errores)
        self.assertEqual(llamadas, [])
        self.assertEqual(self.arbol(), antes)

    def test_efectivo_json_invalido_falla_antes_de_consultar_o_escribir(self):
        self.importar()
        for contenido in ("{roto", json.dumps({"ARS": "mil", "USD": 0}),
                          json.dumps({"ARS": True, "USD": 0}), json.dumps({"ARS": 0, "USD": float("nan")})):
            with self.subTest(contenido=contenido):
                (self.cliente / "efectivo.json").write_text(contenido, encoding="utf-8")
                antes = self.arbol()
                codigo, _, errores, llamadas = self.ejecutar("fijar-dia-cero")
                self.assertNotEqual(codigo, 0)
                self.assertTrue(errores)
                self.assertEqual(llamadas, [])
                self.assertEqual(self.arbol(), antes)

    def test_dia_cero_existente_no_consulta_ni_modifica_sin_forzar(self):
        self.importar()
        self.assertEqual(self.ejecutar("fijar-dia-cero")[0], 0)
        antes = self.arbol()
        codigo, _, errores, llamadas = self.ejecutar("fijar-dia-cero")
        self.assertNotEqual(codigo, 0)
        self.assertTrue(errores)
        self.assertEqual(llamadas, [])
        self.assertEqual(self.arbol(), antes)
        paneles = copy.deepcopy(PANELES)
        paneles["arg_cedears"][0] = fila("AAA", 1300.0)
        codigo, _, errores, llamadas = self.ejecutar("fijar-dia-cero", "--forzar", paneles=paneles)
        self.assertEqual(codigo, 0, errores)
        self.assertTrue(llamadas)
        self.assertEqual(self.leer_dia_cero()["precios"]["AAA"], 1300.0)

    def test_mep_caido_no_impide_fijar_y_avisa_sin_dato(self):
        self.importar()
        paneles = copy.deepcopy(PANELES)
        del paneles["mep"]
        codigo, salida, errores, _ = self.ejecutar("fijar-dia-cero", paneles=paneles)
        self.assertEqual(codigo, 0, errores)
        self.assertIsNone(self.leer_dia_cero()["mep"])
        self.assertIn("mep", salida.lower())
        self.assertIn("sin dato", salida.lower())

    def test_efectivo_tardio_acepta_deuda_y_cero_sin_red_ni_retomar_precios(self):
        self.importar()
        fecha = (self.hoy - dt.timedelta(days=1)).isoformat()
        self.assertEqual(self.ejecutar("fijar-dia-cero", "--fecha", fecha)[0], 0)
        antes = self.leer_dia_cero()
        codigo, salida, errores, llamadas = self.ejecutar("efectivo-dia-cero", "--ars=-1000", "--usd=0")
        self.assertEqual(codigo, 0, errores)
        self.assertEqual(llamadas, [])
        despues = self.leer_dia_cero()
        self.assertEqual(despues["efectivo"], {"fecha": fecha, "ARS": -1000.0, "USD": 0.0})
        self.assertIn("efectivo_cargado_en", despues)
        for clave in ("fecha", "fijado_en", "cantidades", "precios", "mep"):
            self.assertEqual(despues[clave], antes[clave], clave)
        self.assertIn("patrimonio", salida.lower())

    def test_efectivo_sin_dia_cero_no_crea_archivos_ni_consulta(self):
        self.importar()
        antes = self.arbol()
        codigo, _, errores, llamadas = self.ejecutar("efectivo-dia-cero", "--ars=0", "--usd=0")
        self.assertNotEqual(codigo, 0)
        self.assertTrue(errores)
        self.assertEqual(llamadas, [])
        self.assertEqual(self.arbol(), antes)

    def test_efectivo_no_finito_no_toca_dia_cero(self):
        self.importar()
        self.assertEqual(self.ejecutar("fijar-dia-cero")[0], 0)
        antes = self.arbol()
        codigo, _, errores, llamadas = self.ejecutar("efectivo-dia-cero", "--ars=nan", "--usd=0")
        self.assertNotEqual(codigo, 0)
        self.assertTrue(errores)
        self.assertEqual(llamadas, [])
        self.assertEqual(self.arbol(), antes)

    def test_estado_con_dia_cero_muestra_faltantes_sin_red_ni_escritura(self):
        self.importar()
        self.assertEqual(self.ejecutar("fijar-dia-cero")[0], 0)
        antes = self.arbol()
        codigo, salida, errores, llamadas = self.ejecutar("estado")
        self.assertEqual(codigo, 0, errores)
        self.assertEqual(llamadas, [])
        self.assertIn(self.hoy.isoformat(), salida)
        self.assertIn("patrimonio", salida.lower())
        self.assertIn("sin dato", salida.lower())
        self.assertIn("efectivo ARS", salida)
        self.assertIn("efectivo USD", salida)
        self.assertEqual(self.arbol(), antes)


if __name__ == "__main__":
    unittest.main()
