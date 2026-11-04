"""Integridad de la foto inicial, saldos tardíos y patrimonio guardado."""

import copy
import datetime as dt
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from zoneinfo import ZoneInfo

from cartera.dia_cero import (
    ErrorDiaCero,
    _leer_dia_cero,
    _validar_efectivo,
    cargar_efectivo_dia_cero,
    fijar_dia_cero,
    patrimonio_inicial,
)
from cartera.punto_partida import Posicion


FECHA = dt.date(2026, 11, 4)
AR = ZoneInfo("America/Argentina/Buenos_Aires")
POSICION = Posicion("AAA", "Demo", "cedear", 10, 1)


def cotizacion(precio=100.0, ticker="AAA", estado="vivo"):
    return SimpleNamespace(ticker=ticker, ultimo=precio, estado=estado)


class IntegridadDiaCero(unittest.TestCase):
    def setUp(self):
        self.temporal = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporal.cleanup)
        self.raiz = Path(self.temporal.name)
        self.ruta = self.raiz / "datos" / "dia_cero.json"

    def fijar(self, **extras):
        return fijar_dia_cero([POSICION], {"AAA": cotizacion()}, self.ruta, FECHA, **extras)

    def test_efectivo_ausente_y_claves_ausentes_no_son_ceros(self):
        self.assertEqual(_validar_efectivo(None), {"fecha": None, "ARS": None, "USD": None})
        d = self.fijar(efectivo={"ARS": 0})
        p = patrimonio_inicial([POSICION], d)
        self.assertEqual(p.efectivo_ars, 0)
        self.assertIsNone(p.efectivo_usd)
        self.assertIsNone(p.total)
        self.assertEqual(p.faltantes, ["efectivo USD"])

    def test_precio_invalido_no_crea_carpeta(self):
        for precio in (None, True, 0, -1, float("nan"), float("inf")):
            with self.subTest(precio=precio), self.assertRaises(ErrorDiaCero):
                fijar_dia_cero([POSICION], {"AAA": cotizacion(precio)}, self.ruta, FECHA)
            self.assertFalse(self.ruta.parent.exists())

    def test_mep_invalido_o_efectivo_booleano_no_reemplazan_base(self):
        self.fijar()
        antes = self.ruta.read_bytes()
        for mep in (True, 0, -100, float("nan"), float("inf")):
            with self.subTest(mep=mep), self.assertRaises(ErrorDiaCero):
                self.fijar(forzar=True, mep=mep)
        for saldo in (True, "mil", float("nan"), float("inf")):
            with self.subTest(saldo=saldo), self.assertRaises(ErrorDiaCero):
                self.fijar(forzar=True, efectivo={"ARS": saldo})
        self.assertEqual(self.ruta.read_bytes(), antes)

    def test_cotizacion_de_otro_ticker_y_posicion_repetida_se_rechazan(self):
        with self.assertRaises(ErrorDiaCero):
            fijar_dia_cero([POSICION], {"AAA": cotizacion(ticker="OTRA")}, self.ruta, FECHA)
        with self.assertRaises(ErrorDiaCero):
            fijar_dia_cero([POSICION, POSICION], {"AAA": cotizacion()}, self.ruta, FECHA)
        self.assertFalse(self.ruta.exists())

    def test_error_al_reemplazar_foto_conserva_base_completa(self):
        self.fijar()
        antes = self.ruta.read_bytes()
        with patch("cartera.dia_cero.os.replace", side_effect=OSError("disco no disponible")):
            with self.assertRaises(OSError):
                self.fijar(forzar=True, mep=1500.0)
        self.assertEqual(self.ruta.read_bytes(), antes)
        self.assertEqual(list(self.ruta.parent.glob("*.tmp")), [])

    def test_error_al_publicar_foto_inicial_no_deja_archivo_parcial(self):
        with patch("cartera.dia_cero.os.link", side_effect=OSError("disco no disponible")):
            with self.assertRaises(OSError):
                self.fijar()
        self.assertFalse(self.ruta.exists())
        self.assertEqual(list(self.ruta.parent.glob("*.tmp")), [])

    def test_error_al_completar_efectivo_conserva_la_foto(self):
        self.fijar()
        antes = self.ruta.read_bytes()
        with patch("cartera.dia_cero.os.replace", side_effect=OSError("disco no disponible")):
            with self.assertRaises(OSError):
                cargar_efectivo_dia_cero(self.ruta, {"ARS": -1, "USD": 0})
        self.assertEqual(self.ruta.read_bytes(), antes)
        self.assertEqual(list(self.ruta.parent.glob("*.tmp")), [])

    def test_efectivo_en_cero_ya_es_un_saldo_cargado(self):
        self.fijar(efectivo={"ARS": 0, "USD": None})
        with self.assertRaises(ErrorDiaCero):
            cargar_efectivo_dia_cero(self.ruta, {"ARS": 10, "USD": 0})
        cargar_efectivo_dia_cero(self.ruta, {"ARS": 10, "USD": 0}, forzar=True)
        self.assertEqual(_leer_dia_cero(self.ruta)["efectivo"]["ARS"], 10)

    def test_completar_no_muta_la_entrada_y_preserva_campos_adicionales(self):
        d = self.fijar(mep=1500)
        d["referencia"] = {"nota": "foto ficticia"}
        self.ruta.write_text(json.dumps(d), encoding="utf-8")
        efectivo = {"fecha": "2026-11-05", "ARS": -100, "USD": -2}
        antes = copy.deepcopy(efectivo)
        nuevo = cargar_efectivo_dia_cero(self.ruta, efectivo)
        self.assertEqual(efectivo, antes)
        self.assertEqual(nuevo["referencia"], d["referencia"])
        for clave in ("fecha", "fijado_en", "cantidades", "precios", "mep"):
            self.assertEqual(nuevo[clave], d[clave], clave)
        self.assertIsNotNone(dt.datetime.fromisoformat(nuevo["efectivo_cargado_en"]).utcoffset())

    def test_saldo_usd_deudor_necesita_mep_y_resta_del_total(self):
        d = self.fijar(efectivo={"ARS": 10, "USD": -2})
        p = patrimonio_inicial([POSICION], d)
        self.assertIsNone(p.total)
        self.assertEqual(p.faltantes, ["dólar MEP"])
        d["mep"] = 1500
        p = patrimonio_inicial([POSICION], d)
        self.assertEqual(p.total, 1000 + 10 - 3000)

    def test_sin_cantidades_guardadas_no_usa_las_actuales(self):
        d = self.fijar(efectivo={"ARS": 0, "USD": 0})
        del d["cantidades"]
        with self.assertRaises(ErrorDiaCero):
            patrimonio_inicial([POSICION], d)

    def test_no_omite_especie_sin_unidad_y_rechaza_unidad_invalida(self):
        d = self.fijar()
        with self.assertRaises(ErrorDiaCero):
            patrimonio_inicial([], d)
        mala = Posicion("AAA", "Demo", "cedear", 10, 10)
        with self.assertRaises(ErrorDiaCero):
            patrimonio_inicial([mala], d)

    def test_unidad_invalida_no_permite_fijar_una_foto_inutilizable(self):
        mala = Posicion("AAA", "Demo", "cedear", 10, 10)
        with self.assertRaises(ErrorDiaCero):
            fijar_dia_cero([mala], {"AAA": cotizacion()}, self.ruta, FECHA)
        self.assertFalse(self.ruta.exists())

    def test_archivo_corrupto_y_snapshot_incompleto_no_se_modifican(self):
        self.ruta.parent.mkdir()
        for texto in ("{roto", '{"esquema_version":2}', '{"esquema_version":NaN}'):
            with self.subTest(texto=texto):
                self.ruta.write_text(texto, encoding="utf-8")
                with self.assertRaises(ErrorDiaCero):
                    cargar_efectivo_dia_cero(self.ruta, {"ARS": 10, "USD": 0})
                self.assertEqual(self.ruta.read_text(encoding="utf-8"), texto)

    def test_foto_y_patrimonio_no_publican_infinito_por_desbordamiento(self):
        d = self.fijar(efectivo={"ARS": 0, "USD": 0})
        d["cantidades"]["AAA"] = 1e308
        d["precios"]["AAA"] = 1e308
        with self.assertRaises(ErrorDiaCero):
            patrimonio_inicial([POSICION], d)


if __name__ == "__main__":
    unittest.main()
