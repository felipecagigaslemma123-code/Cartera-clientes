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
from cartera.alertas_comando import correr_alertas
from cartera.almacenamiento import importar_cartera
from cartera.movimientos import ErrorMovimiento, leer_movimientos

DEMO = Path(__file__).resolve().parents[1] / "fixtures" / "punto_partida_demo.xlsx"
AR = ZoneInfo("America/Argentina/Buenos_Aires")
ABIERTO = dt.datetime(2026, 11, 4, 12, tzinfo=AR)
ENCABEZADO = "fecha,tipo,ticker,cantidad,importe,moneda,tc,tipo_activo,nota"
DIA_CERO = {
    "esquema_version": 2, "fecha": "2026-10-01", "fijado_en": "2026-10-01T17:05:00-03:00",
    "cantidades": {"AAA": 100.0, "BBB": 50.0, "CCC": 10.0, "BOND1": 1000.0, "NOTE1": 200000.0, "ONX": 500.0},
    "precios": {"AAA": 1000.0, "BBB": 1000.0, "CCC": 2000.0, "BOND1": 150000.0, "NOTE1": 100.0, "ONX": 140000.0},
    "mep": 1500.0, "efectivo": {"fecha": "2026-10-01", "ARS": 10000.0, "USD": 0.0},
}
PANELES = {
    "arg_cedears": [{"symbol": "AAA", "c": 1200.0, "px_bid": 1199.0, "px_ask": 1201.0},
                    {"symbol": "BBB", "c": 1100.0}, {"symbol": "NUE", "c": 500.0}],
    "arg_stocks": [{"symbol": "CCC", "c": 2500.0}],
    "arg_bonds": [{"symbol": "BOND1", "c": 160000.0}],
    "arg_notes": [{"symbol": "NOTE1", "c": 110.0}],
    "arg_corp": [{"symbol": "ONX", "c": 150000.0}],
    "mep": [{"ticker": "AL30", "mark": 1500.0}],
}
# Patrimonio inicial: 100.000 + 50.000 + 20.000 + 1.500.000 + 200.000 + 700.000 + 10.000 = 2.580.000
# Sin movimientos, final: 120.000 + 55.000 + 25.000 + 1.600.000 + 220.000 + 750.000 + 10.000 = 2.780.000
TOTAL_SIN_MOVIMIENTOS = 200000.0


def datos_de(html):
    return json.loads(re.search(r'<script id="datos-cartera" type="application/json">(.*?)</script>', html, re.S).group(1))


class Base(unittest.TestCase):
    def setUp(self):
        temporal = tempfile.TemporaryDirectory()
        self.addCleanup(temporal.cleanup)
        self.datos = Path(temporal.name) / "datos"
        self.punto, _ = importar_cartera(self.datos, "demo", DEMO)
        self.carpeta = self.datos / "clientes" / "demo"
        self.csv = self.carpeta / "movimientos.csv"
        (self.carpeta / "dia_cero.json").write_text(json.dumps(DIA_CERO), encoding="utf-8")

    def cli(self, *argumentos):
        salida, errores = io.StringIO(), io.StringIO()
        fetch = lambda url: PANELES[url.rsplit("/", 1)[-1]]
        with patch("cartera.__main__.consultar_json", side_effect=fetch):
            with redirect_stdout(salida), redirect_stderr(errores):
                codigo = main(["--datos", str(self.datos), argumentos[0], "--cliente", "demo"] + list(argumentos[1:]))
        return codigo, salida.getvalue(), errores.getvalue()

    def cargar(self, *argumentos):
        return self.cli("movimiento", *argumentos)

    def venta_total_aaa(self):
        codigo, _, errores = self.cargar("--fecha", "2026-10-10", "--tipo", "venta", "--ticker", "AAA",
                                         "--cantidad", "100", "--importe", "120000")
        self.assertEqual(codigo, 0, errores)


class ComandoMovimiento(Base):
    def test_guarda_y_se_puede_leer(self):
        codigo, salida, errores = self.cargar("--fecha", "2026-10-10", "--tipo", "deposito", "--importe", "5000.5",
                                              "--nota", "aporte, inicial")
        self.assertEqual(codigo, 0, errores)
        self.assertTrue(salida.strip())
        self.assertEqual(self.csv.read_text(encoding="utf-8").splitlines()[0], ENCABEZADO)
        movimiento = leer_movimientos(self.csv)[0]
        self.assertEqual(movimiento["fecha"], dt.date(2026, 10, 10))
        self.assertEqual(movimiento["importe"], 5000.5)
        self.assertEqual(movimiento["moneda"], "ARS")
        self.assertIsNone(movimiento["tc"])
        self.assertEqual(movimiento["nota"], "aporte, inicial")

    def test_solo_lo_lee_el_usuario(self):
        self.cargar("--fecha", "2026-10-10", "--tipo", "deposito", "--importe", "5000")
        self.assertEqual(stat.S_IMODE(self.csv.stat().st_mode) & 0o077, 0)

    def test_dolares_con_tipo_de_cambio(self):
        codigo, _, errores = self.cargar("--fecha", "2026-10-10", "--tipo", "dividendo", "--ticker", "AAA",
                                         "--importe", "2", "--moneda", "USD", "--tc", "1500")
        self.assertEqual(codigo, 0, errores)
        self.assertEqual(leer_movimientos(self.csv)[0]["tc"], 1500.0)

    def test_rechaza_sin_escribir(self):
        casos = [("--fecha", "2026-10-01", "--tipo", "deposito", "--importe", "1"),
                 ("--fecha", "2099-01-01", "--tipo", "deposito", "--importe", "1"),
                 ("--fecha", "10/10/2026", "--tipo", "deposito", "--importe", "1"),
                 ("--fecha", "2026-10-10", "--tipo", "deposito", "--importe", "1.234,56"),
                 ("--fecha", "2026-10-10", "--tipo", "venta", "--ticker", "AAA", "--cantidad", "101", "--importe", "1")]
        for caso in casos:
            codigo, _, errores = self.cargar(*caso)
            self.assertNotEqual(codigo, 0, caso)
            self.assertTrue(errores.strip(), caso)
            self.assertFalse(self.csv.exists(), caso)

    def test_rechaza_si_vuelve_invalido_un_movimiento_anterior(self):
        self.venta_total_aaa()
        antes = self.csv.read_bytes()
        codigo, _, _ = self.cargar("--fecha", "2026-10-05", "--tipo", "venta", "--ticker", "AAA",
                                   "--cantidad", "1", "--importe", "1")
        self.assertNotEqual(codigo, 0)
        self.assertEqual(self.csv.read_bytes(), antes)

    def test_necesita_el_dia_cero(self):
        (self.carpeta / "dia_cero.json").unlink()
        codigo, _, errores = self.cargar("--fecha", "2026-10-10", "--tipo", "deposito", "--importe", "1")
        self.assertNotEqual(codigo, 0)
        self.assertIn("día cero", errores.lower())
        self.assertFalse(self.csv.exists())

    def test_archivo_invalido_informa_la_fila(self):
        self.csv.write_text(ENCABEZADO + "\n2026-10-10,deposito,,,abc,ARS,,,\n", encoding="utf-8")
        with self.assertRaises(ErrorMovimiento) as error:
            leer_movimientos(self.csv)
        self.assertIn("2", str(error.exception))

    def test_encabezado_invalido(self):
        self.csv.write_text("a,b\n1,2\n", encoding="utf-8")
        with self.assertRaises(ErrorMovimiento):
            leer_movimientos(self.csv)

    def test_sin_archivo_no_hay_movimientos(self):
        self.assertEqual(leer_movimientos(self.csv), [])

    def test_fijar_dia_cero_no_puede_pasar_por_encima_de_los_movimientos(self):
        self.cargar("--fecha", "2026-10-10", "--tipo", "deposito", "--importe", "1")
        antes = (self.carpeta / "dia_cero.json").read_bytes()
        codigo, _, _ = self.cli("fijar-dia-cero", "--fecha", "2026-10-10", "--forzar")
        self.assertNotEqual(codigo, 0)
        self.assertEqual((self.carpeta / "dia_cero.json").read_bytes(), antes)


class Estado(Base):
    def test_muestra_la_cartera_actual_y_el_efectivo(self):
        self.venta_total_aaa()
        codigo, salida, errores = self.cli("estado")
        self.assertEqual(codigo, 0, errores)
        self.assertNotIn("AAA ·", salida)
        self.assertIn("BBB ·", salida)
        self.assertIn("130.000", salida)
        self.assertIn("Patrimonio inicial", salida)

    def test_archivo_invalido_es_un_error(self):
        self.csv.write_text("a,b\n", encoding="utf-8")
        codigo, _, errores = self.cli("estado")
        self.assertNotEqual(codigo, 0)
        self.assertTrue(errores.strip())


class Dashboard(Base):
    def generar(self):
        codigo, _, errores = self.cli("dashboard")
        self.assertEqual(codigo, 0, errores)
        return (self.carpeta / "dashboard.html").read_text(encoding="utf-8")

    def test_sin_movimientos_calcula_el_resultado(self):
        html = self.generar()
        integral = datos_de(html)["integral"]
        self.assertAlmostEqual(integral["total"], TOTAL_SIN_MOVIMIENTOS)
        self.assertIn('id="resultado-completo"', html)
        self.assertNotIn("Se calcula cuando estén los movimientos", html)
        self.assertNotIn("resultado de la cartera", html.lower())

    def test_con_movimientos(self):
        self.cargar("--fecha", "2026-10-10", "--tipo", "deposito", "--importe", "1000")
        self.cargar("--fecha", "2026-10-10", "--tipo", "renta", "--ticker", "BOND1", "--importe", "700")
        integral = datos_de(self.generar())["integral"]
        self.assertAlmostEqual(integral["total"], TOTAL_SIN_MOVIMIENTOS + 700.0)
        self.assertAlmostEqual(integral["aportes"], 1000.0)
        self.assertAlmostEqual(integral["rentas"], 700.0)
        self.assertAlmostEqual(integral["efectivo"]["ARS"], 11700.0)

    def test_posiciones_actuales_y_patrimonio_inicial_con_lo_vendido(self):
        self.venta_total_aaa()
        datos = datos_de(self.generar())
        self.assertNotIn("AAA", [p["ticker"] for p in datos["posiciones"]])
        self.assertAlmostEqual(datos["dia_cero"]["patrimonio_inicial"], 2580000.0)
        self.assertAlmostEqual(datos["integral"]["total"], TOTAL_SIN_MOVIMIENTOS)

    def test_especie_nueva_se_cotiza(self):
        self.cargar("--fecha", "2026-10-10", "--tipo", "compra", "--ticker", "NUE", "--cantidad", "10",
                    "--importe", "4000", "--tipo-activo", "cedear")
        datos = datos_de(self.generar())
        nueva = next(p for p in datos["posiciones"] if p["ticker"] == "NUE")
        self.assertEqual(nueva["ultimo"], 500.0)
        self.assertEqual(nueva["estado_costo"], "extracto")
        self.assertAlmostEqual(datos["integral"]["total"], TOTAL_SIN_MOVIMIENTOS + 1000.0)

    def test_realizado_con_origen(self):
        self.venta_total_aaa()
        html = self.generar()
        realizado = datos_de(html)["realizados"][0]
        self.assertEqual(realizado["ticker"], "AAA")
        self.assertAlmostEqual(realizado["resultado"], 15400.0)
        self.assertEqual(realizado["origen_costo"], "extracto")
        self.assertIn('id="resultado-realizado"', html)

    def test_realizado_sin_costo_no_inventa(self):
        self.cargar("--fecha", "2026-10-10", "--tipo", "venta", "--ticker", "BOND1", "--cantidad", "10", "--importe", "16000")
        realizado = datos_de(self.generar())["realizados"][0]
        self.assertIsNone(realizado["resultado"])
        self.assertEqual(realizado["origen_costo"], "incompleto")

    def test_sin_dia_cero_es_sin_dato(self):
        (self.carpeta / "dia_cero.json").unlink()
        html = self.generar()
        integral = datos_de(html)["integral"]
        self.assertIsNone(integral["total"])
        self.assertTrue(any("día cero" in f for f in integral["faltantes"]))
        self.assertIn("sin dato", html.lower())

    def test_no_publica_porcentaje_integral(self):
        self.assertNotIn("porcentaje", datos_de(self.generar())["integral"])

    def test_conciliacion_visible(self):
        self.cargar("--fecha", "2026-10-10", "--tipo", "deposito", "--importe", "1000")
        (self.carpeta / "efectivo.json").write_text(
            json.dumps({"fecha": "2026-10-15", "ARS": 5000.0, "USD": 0.0, "nota": ""}), encoding="utf-8")
        html = self.generar()
        conciliacion = datos_de(html)["conciliacion"]
        self.assertEqual(conciliacion["estado"], "no_concilia")
        self.assertAlmostEqual(conciliacion["diferencias"]["ARS"], -6000.0)
        self.assertIn("no concilia", html.lower())

    def test_archivo_invalido_no_genera_nada(self):
        self.csv.write_text("a,b\n", encoding="utf-8")
        codigo, _, errores = self.cli("dashboard")
        self.assertNotEqual(codigo, 0)
        self.assertTrue(errores.strip())
        self.assertFalse((self.carpeta / "dashboard.html").exists())


class Capturar(Base):
    def test_captura_la_cartera_actual(self):
        self.venta_total_aaa()
        self.cargar("--fecha", "2026-10-10", "--tipo", "compra", "--ticker", "NUE", "--cantidad", "1",
                    "--importe", "500", "--tipo-activo", "cedear")
        codigo, _, errores = self.cli("capturar")
        self.assertEqual(codigo, 0, errores)
        historial = (self.carpeta / "historial.csv").read_text(encoding="utf-8")
        self.assertIn(",NUE,", historial)
        self.assertNotIn(",AAA,", historial)


class Alertas(Base):
    def setUp(self):
        super().setUp()
        self.recibidos = []

    def canal(self, titulo, mensaje):
        self.recibidos.append(mensaje)

    def fetch(self, url):
        return PANELES[url.rsplit("/", 1)[-1]]

    def correr(self):
        return correr_alertas(self.carpeta, self.punto, "demo", self.fetch, [self.canal], ABIERTO)

    def niveles(self, contenido):
        (self.carpeta / "niveles.json").write_text(json.dumps(contenido), encoding="utf-8")

    def test_nivel_de_especie_vendida_no_apaga_las_demas(self):
        self.venta_total_aaa()
        self.niveles({"AAA": {"stop_loss": 5000.0}, "BBB": {"stop_loss": 5000.0}})
        resultado = self.correr()
        self.assertTrue(resultado["evaluo_niveles"])
        tipos = [(e.tipo, e.ticker) for e in resultado["eventos"]]
        self.assertIn(("stop_loss", "BBB"), tipos)
        self.assertNotIn(("stop_loss", "AAA"), tipos)
        self.assertTrue(any("AAA" in aviso for aviso in resultado["avisos"]))

    def test_nivel_de_especie_nueva(self):
        self.cargar("--fecha", "2026-10-10", "--tipo", "compra", "--ticker", "NUE", "--cantidad", "1",
                    "--importe", "500", "--tipo-activo", "cedear")
        self.niveles({"NUE": {"stop_loss": 5000.0}})
        tipos = [(e.tipo, e.ticker) for e in self.correr()["eventos"]]
        self.assertIn(("stop_loss", "NUE"), tipos)

    def test_especie_desconocida_sigue_siendo_invalida(self):
        self.niveles({"ZZZ": {"stop_loss": 5000.0}})
        self.assertFalse(self.correr()["evaluo_niveles"])

    def test_archivo_invalido_no_frena_y_avisa_una_vez_por_dia(self):
        self.csv.write_text("a,b\n", encoding="utf-8")
        self.niveles({"AAA": {"stop_loss": 5000.0}})
        primera = self.correr()
        self.assertTrue(primera["evaluo_niveles"])
        tipos = [(e.tipo, e.ticker) for e in primera["eventos"]]
        self.assertIn(("stop_loss", "AAA"), tipos)
        self.assertIn(("sin_chequeo", None), tipos)
        self.assertIn("movimientos.csv", self.recibidos[0])
        segunda = correr_alertas(self.carpeta, self.punto, "demo", self.fetch, [self.canal],
                                 ABIERTO + dt.timedelta(minutes=5))
        self.assertNotIn(("sin_chequeo", None), [(e.tipo, e.ticker) for e in segunda["eventos"]])


if __name__ == "__main__":
    unittest.main()
