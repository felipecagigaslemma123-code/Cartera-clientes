"""Respaldo del día cero al forzar y control de las fechas del efectivo."""

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
from cartera.precios import Cotizacion, cargar_efectivo_dia_cero, fijar_dia_cero
from cartera.punto_partida import Posicion

DEMO = Path(__file__).resolve().parents[1] / "fixtures" / "punto_partida_demo.xlsx"
AR = ZoneInfo("America/Argentina/Buenos_Aires")
HOY = dt.datetime.now(AR).date()
AYER = (HOY - dt.timedelta(days=1)).isoformat()
MANANA = (HOY + dt.timedelta(days=1)).isoformat()
AAA = Posicion(ticker="AAA", especie="A", tipo="cedear", cantidad=100, cotiza_cada=1)
EFECTIVO = {"fecha": HOY.isoformat(), "ARS": -500.0, "USD": 0.0}


def cotizaciones(precio):
    return {"AAA": Cotizacion(ticker="AAA", ultimo=precio, bid=precio, ask=precio, pct_dia=0.0,
                              estado="vivo", consultado_en=dt.datetime.now(AR))}


class Respaldo(unittest.TestCase):
    def setUp(self):
        temporal = tempfile.TemporaryDirectory()
        self.addCleanup(temporal.cleanup)
        self.ruta = Path(temporal.name) / "dia_cero.json"
        self.historial = self.ruta.parent / "historial_dia_cero"

    def leer(self):
        return json.loads(self.ruta.read_text(encoding="utf-8"))

    def fijar(self, precio=1000.0, **argumentos):
        return fijar_dia_cero([AAA], cotizaciones(precio), self.ruta, HOY, **argumentos)

    def test_primera_fijacion_no_crea_historial(self):
        self.fijar()
        self.assertFalse(self.historial.exists())

    def test_forzar_guarda_la_version_anterior_exacta(self):
        self.fijar()
        anterior = self.ruta.read_bytes()
        self.fijar(precio=2000.0, forzar=True)
        versiones = list(self.historial.iterdir())
        self.assertEqual(len(versiones), 1)
        self.assertEqual(versiones[0].read_bytes(), anterior)
        self.assertEqual(self.leer()["precios"]["AAA"], 2000.0)

    def test_varias_veces_no_pisa_versiones(self):
        self.fijar()
        for precio in (2000.0, 3000.0, 4000.0):
            self.fijar(precio=precio, forzar=True)
        self.assertEqual(len(list(self.historial.iterdir())), 3)

    def test_forzar_sin_efectivo_conserva_el_cargado(self):
        self.fijar()
        cargar_efectivo_dia_cero(self.ruta, EFECTIVO)
        cargado_en = self.leer()["efectivo_cargado_en"]
        self.fijar(precio=2000.0, forzar=True)
        self.assertEqual(self.leer()["efectivo"], EFECTIVO)
        self.assertEqual(self.leer()["efectivo_cargado_en"], cargado_en)

    def test_forzar_con_efectivo_lo_reemplaza(self):
        self.fijar(efectivo=EFECTIVO)
        nuevo = {"fecha": HOY.isoformat(), "ARS": 7.0, "USD": 0.0}
        self.fijar(forzar=True, efectivo=nuevo)
        self.assertEqual(self.leer()["efectivo"], nuevo)

    def test_error_al_forzar_no_toca_nada(self):
        self.fijar()
        anterior = self.ruta.read_bytes()
        with self.assertRaises(ValueError):
            fijar_dia_cero([AAA], {}, self.ruta, HOY, forzar=True)
        self.assertEqual(self.ruta.read_bytes(), anterior)
        self.assertFalse(self.historial.exists())

    def test_si_falla_el_respaldo_no_reemplaza(self):
        self.fijar()
        anterior = self.ruta.read_bytes()
        with patch("cartera.dia_cero.os.link", side_effect=OSError("disco lleno")):
            with self.assertRaises(OSError):
                self.fijar(precio=2000.0, forzar=True)
        self.assertEqual(self.ruta.read_bytes(), anterior)

    def test_version_anterior_ilegible_se_respalda_igual(self):
        self.ruta.write_text("{roto", encoding="utf-8")
        self.fijar(forzar=True)
        versiones = list(self.historial.iterdir())
        self.assertEqual(versiones[0].read_text(encoding="utf-8"), "{roto")
        self.assertIsNone(self.leer()["efectivo"]["ARS"])

    def test_reemplazar_efectivo_lo_respalda(self):
        self.fijar(efectivo=EFECTIVO)
        anterior = self.ruta.read_bytes()
        cargar_efectivo_dia_cero(self.ruta, {"fecha": HOY.isoformat(), "ARS": 7.0, "USD": 0.0}, forzar=True)
        self.assertEqual(list(self.historial.iterdir())[0].read_bytes(), anterior)

    def test_primera_carga_de_efectivo_no_respalda(self):
        self.fijar()
        cargar_efectivo_dia_cero(self.ruta, EFECTIVO)
        self.assertFalse(self.historial.exists())


class FechasDelEfectivo(unittest.TestCase):
    PANELES = {
        "arg_cedears": [{"symbol": "AAA", "c": 1200.0}, {"symbol": "BBB", "c": 1100.0}],
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

    def correr(self, *argumentos):
        salida, errores = io.StringIO(), io.StringIO()
        with patch("cartera.__main__.consultar_json", side_effect=lambda url: self.PANELES[url.rsplit("/", 1)[-1]]):
            with redirect_stdout(salida), redirect_stderr(errores):
                codigo = main(["--datos", str(self.datos), *argumentos])
        return codigo, salida.getvalue(), errores.getvalue()

    def efectivo_json(self, fecha, ars=5.0):
        contenido = {"fecha": fecha, "ARS": ars, "USD": 0.0}
        (self.carpeta / "efectivo.json").write_text(json.dumps(contenido), encoding="utf-8")

    def test_efectivo_viejo_avisa(self):
        self.efectivo_json(AYER)
        codigo, salida, _ = self.correr("fijar-dia-cero", "--cliente", "demo")
        self.assertEqual(codigo, 0)
        self.assertIn("ADVERTENCIA", salida)
        self.assertIn(AYER, salida)

    def test_efectivo_de_la_misma_fecha_no_avisa(self):
        self.efectivo_json(HOY.isoformat())
        _, salida, _ = self.correr("fijar-dia-cero", "--cliente", "demo")
        self.assertNotIn("ADVERTENCIA", salida)

    def test_efectivo_sin_fecha_avisa(self):
        self.efectivo_json(None)
        _, salida, _ = self.correr("fijar-dia-cero", "--cliente", "demo")
        self.assertIn("no tiene fecha", salida)

    def test_sin_efectivo_no_avisa(self):
        self.efectivo_json(None, ars=None)
        (self.carpeta / "efectivo.json").write_text('{"fecha": null, "ARS": null, "USD": null}', encoding="utf-8")
        _, salida, _ = self.correr("fijar-dia-cero", "--cliente", "demo")
        self.assertNotIn("ADVERTENCIA", salida)

    def test_efectivo_json_futuro_no_fija(self):
        self.efectivo_json(MANANA)
        codigo, _, errores = self.correr("fijar-dia-cero", "--cliente", "demo")
        self.assertNotEqual(codigo, 0)
        self.assertIn("futura", errores)
        self.assertFalse((self.carpeta / "dia_cero.json").exists())

    def test_cargar_con_fecha_futura_no_escribe(self):
        self.correr("fijar-dia-cero", "--cliente", "demo")
        anterior = (self.carpeta / "dia_cero.json").read_bytes()
        codigo, _, errores = self.correr(
            "efectivo-dia-cero", "--cliente", "demo", "--ars", "1", "--usd", "0", "--fecha", MANANA)
        self.assertNotEqual(codigo, 0)
        self.assertIn("futura", errores)
        self.assertEqual((self.carpeta / "dia_cero.json").read_bytes(), anterior)

    def test_cargar_con_fecha_distinta_avisa(self):
        self.correr("fijar-dia-cero", "--cliente", "demo")
        codigo, salida, _ = self.correr(
            "efectivo-dia-cero", "--cliente", "demo", "--ars", "1", "--usd", "0", "--fecha", AYER)
        self.assertEqual(codigo, 0)
        self.assertIn("ADVERTENCIA", salida)

    def test_estado_muestra_el_aviso(self):
        self.efectivo_json(AYER)
        self.correr("fijar-dia-cero", "--cliente", "demo")
        _, salida, _ = self.correr("estado", "--cliente", "demo")
        self.assertIn("ADVERTENCIA", salida)

    def test_forzar_avisa_donde_quedo_la_version_anterior(self):
        self.correr("fijar-dia-cero", "--cliente", "demo")
        _, salida, _ = self.correr("fijar-dia-cero", "--cliente", "demo", "--forzar")
        self.assertIn("historial_dia_cero", salida)


if __name__ == "__main__":
    unittest.main()
