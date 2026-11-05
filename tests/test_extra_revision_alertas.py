"""Casos agregados en la revisión de la etapa 4."""

import datetime as dt
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from zoneinfo import ZoneInfo

from cartera.alertas import evaluar_niveles, evaluar_vencimientos
from cartera.alertas_comando import correr_alertas
from cartera.almacenamiento import importar_cartera


DEMO = Path(__file__).resolve().parents[1] / "fixtures" / "punto_partida_demo.xlsx"
AR = ZoneInfo("America/Argentina/Buenos_Aires")
ABIERTO = dt.datetime(2026, 11, 4, 12, tzinfo=AR)
CERRADO = dt.datetime(2026, 11, 4, 20, tzinfo=AR)


class Base(unittest.TestCase):
    def setUp(self):
        temporal = tempfile.TemporaryDirectory()
        self.addCleanup(temporal.cleanup)
        self.datos = Path(temporal.name) / "datos"
        self.punto, _ = importar_cartera(self.datos, "demo", DEMO)
        self.carpeta = self.datos / "clientes" / "demo"
        self.recibidos = []
        self.escribir("niveles.json", {"AAA": {"take_profit": 1500, "stop_loss": 900}})

    def escribir(self, nombre, contenido):
        (self.carpeta / nombre).write_text(json.dumps(contenido), encoding="utf-8")

    def fetch(self, url):
        return [{"symbol": "AAA", "c": 800, "px_bid": 800, "px_ask": 800}]

    def canal(self, titulo, mensaje):
        self.recibidos.append(titulo + "\n" + mensaje)

    def correr(self, ahora=ABIERTO):
        return correr_alertas(self.carpeta, self.punto, "demo", self.fetch, [self.canal], ahora)


class InstrumentosInvalidos(Base):
    def setUp(self):
        super().setUp()
        self.escribir("instrumentos.json", {"BOND1": {"vencimiento": "30/11/2026"}})

    def globales(self, resultado):
        return [e for e in resultado["eventos"] if e.tipo == "sin_chequeo" and e.ticker is None]

    def test_no_frena_los_niveles_y_lo_avisa(self):
        resultado = self.correr()
        self.assertTrue(resultado["evaluo_niveles"])
        self.assertIn("stop_loss", [e.tipo for e in resultado["eventos"]])
        self.assertEqual(len(self.globales(resultado)), 1)
        self.assertIn("instrumentos.json", self.recibidos[0])

    def test_avisa_una_vez_por_dia(self):
        self.correr()
        self.assertEqual(self.globales(self.correr(ABIERTO + dt.timedelta(minutes=5))), [])
        self.assertEqual(len(self.globales(self.correr(ABIERTO + dt.timedelta(days=1)))), 1)

    def test_tambien_avisa_fuera_de_horario(self):
        self.assertEqual(len(self.globales(self.correr(CERRADO))), 1)

    def test_json_roto_equivale_a_invalido(self):
        (self.carpeta / "instrumentos.json").write_text("{roto", encoding="utf-8")
        self.assertEqual(len(self.globales(self.correr(CERRADO))), 1)

    def test_conserva_lo_ya_avisado(self):
        self.escribir("instrumentos.json", {"BOND1": {"vencimiento": "2026-11-10"}})
        self.correr(CERRADO)
        (self.carpeta / "instrumentos.json").write_text("{roto", encoding="utf-8")
        self.correr(CERRADO + dt.timedelta(minutes=5))
        estado = json.loads((self.carpeta / "estado_alertas.json").read_text(encoding="utf-8"))
        self.assertEqual(estado["vencimientos"]["BOND1"]["avisados"], [7])
        self.escribir("instrumentos.json", {"BOND1": {"vencimiento": "2026-11-10"}})
        repetidos = [e for e in self.correr(CERRADO + dt.timedelta(minutes=10))["eventos"] if e.tipo == "vencimiento"]
        self.assertEqual(repetidos, [])


class ClaveDesconocida(Base):
    def test_clave_mal_escrita_invalida_el_archivo(self):
        self.escribir("niveles.json", {"AAA": {"takeprofit": 1500}})
        resultado = self.correr()
        self.assertFalse(resultado["evaluo_niveles"])
        tipos = [(e.tipo, e.ticker) for e in resultado["eventos"]]
        self.assertIn(("sin_chequeo", None), tipos)
        self.assertNotIn("no hay niveles definidos", self.recibidos[0])


class Mensajes(Base):
    def test_nivel_muestra_precio_y_nivel_sin_repetir(self):
        self.correr()
        self.assertIn("AAA stop loss: precio 800, nivel 900.", self.recibidos[0])
        self.assertNotIn("stop_loss ·", self.recibidos[0])

    def test_precio_pequeno_no_se_redondea_a_cero(self):
        cotizacion = SimpleNamespace(ticker="X", estado="vivo", bid=0.00001, ultimo=None)
        eventos, _ = evaluar_niveles({"X": cotizacion}, {"X": {"stop_loss": 0.00002}}, {}, ABIERTO)
        self.assertEqual(eventos[0].mensaje, "X stop loss: precio 0,00001, nivel 0,00002.")

    def test_vencimiento_con_fecha_argentina(self):
        hoy = dt.date(2026, 11, 4)
        casos = [("2026-11-22", "X vence el 22/11/2026: faltan 18 días."),
                 ("2026-11-05", "X vence el 05/11/2026: falta 1 día."),
                 ("2026-11-04", "X vence hoy (04/11/2026).")]
        for fecha, esperado in casos:
            eventos, _ = evaluar_vencimientos({"X": {"vencimiento": fecha}}, {}, hoy)
            self.assertEqual(eventos[0].mensaje, esperado)


if __name__ == "__main__":
    unittest.main()
