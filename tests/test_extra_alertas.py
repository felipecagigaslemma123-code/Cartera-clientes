"""Fronteras, conservación de estado y datos inválidos de los evaluadores."""

import copy
import datetime as dt
import json
import unittest
from zoneinfo import ZoneInfo

from cartera.alertas import en_horario_mercado, evaluar_niveles, evaluar_vencimientos
from cartera.precios import Cotizacion


AR = ZoneInfo("America/Argentina/Buenos_Aires")
AHORA = dt.datetime(2026, 11, 4, 12, tzinfo=AR)
NIVELES = {"AAA": {"take_profit": 100.0, "stop_loss": 50.0}}


def cot(precio, bid=None, estado="vivo", ticker="AAA"):
    return Cotizacion(ticker, precio, bid, None, None, estado, AHORA)


def evaluar(precio, estado=None, niveles=NIVELES, ahora=AHORA):
    return evaluar_niveles({"AAA": cot(precio)}, niveles, estado or {}, ahora)


class FronterasNiveles(unittest.TestCase):
    def test_rearme_take_profit_es_estricto_en_uno_por_ciento(self):
        _, estado = evaluar(100)
        _, estado = evaluar(99, estado)
        eventos, _ = evaluar(101, estado)
        self.assertEqual(eventos, [])
        _, estado = evaluar(98.9999, estado)
        eventos, _ = evaluar(100, estado)
        self.assertEqual([e.tipo for e in eventos], ["take_profit"])

    def test_rearme_stop_loss_es_estricto_en_uno_por_ciento(self):
        _, estado = evaluar(50)
        _, estado = evaluar(50.5, estado)
        eventos, _ = evaluar(49, estado)
        self.assertEqual(eventos, [])
        _, estado = evaluar(50.5001, estado)
        eventos, _ = evaluar(50, estado)
        self.assertEqual([e.tipo for e in eventos], ["stop_loss"])

    def test_precio_invalido_no_dispara_y_punta_valida_prevalece(self):
        for precio in (None, 0, -1, True, float("inf"), float("nan"), 10 ** 400):
            with self.subTest(precio=precio):
                eventos, _ = evaluar(precio)
                self.assertEqual([e.tipo for e in eventos], ["sin_chequeo"])
                eventos, _ = evaluar_niveles({"AAA": cot(precio, bid=120)}, NIVELES, {}, AHORA)
                self.assertEqual([e.tipo for e in eventos], ["take_profit"])

    def test_bid_invalido_usa_el_ultimo(self):
        for bid in (0, -1, True, float("inf"), float("nan")):
            with self.subTest(bid=bid):
                eventos, _ = evaluar_niveles({"AAA": cot(120, bid=bid)}, NIVELES, {}, AHORA)
                self.assertEqual([e.tipo for e in eventos], ["take_profit"])

    def test_cache_no_rearma_un_nivel_avisado(self):
        _, estado = evaluar(100)
        eventos, estado = evaluar_niveles({"AAA": cot(90, estado="cache")}, NIVELES, estado, AHORA)
        self.assertEqual([e.tipo for e in eventos], ["sin_chequeo"])
        eventos, _ = evaluar(100, estado)
        self.assertEqual(eventos, [])

    def test_eliminar_nivel_lo_rearma_al_reaparecer(self):
        _, estado = evaluar(100)
        _, estado = evaluar(100, estado, {"AAA": {"take_profit": None, "stop_loss": 50}})
        eventos, _ = evaluar(100, estado)
        self.assertEqual([e.tipo for e in eventos], ["take_profit"])
        _, estado = evaluar(100, estado, {})
        self.assertEqual(estado, {})

    def test_sin_chequeo_por_dia_de_argentina_no_por_utc(self):
        instante = dt.datetime(2026, 11, 5, 1, tzinfo=dt.timezone.utc)
        _, estado = evaluar(None, ahora=AHORA)
        eventos, _ = evaluar(None, estado, ahora=instante)
        self.assertEqual(eventos, [])
        eventos, _ = evaluar(None, estado, ahora=dt.datetime(2026, 11, 5, 3, tzinfo=dt.timezone.utc))
        self.assertEqual([e.tipo for e in eventos], ["sin_chequeo"])

    def test_estado_y_configuracion_no_se_mutan(self):
        _, estado = evaluar(100)
        copias = copy.deepcopy((estado, NIVELES))
        _, nuevo = evaluar(90, estado)
        self.assertEqual((estado, NIVELES), copias)
        nuevo["AAA"]["take_profit"]["nivel"] = 1
        self.assertEqual(estado["AAA"]["take_profit"]["nivel"], 100)
        json.dumps(nuevo, allow_nan=False)

    def test_estado_malformado_y_nivel_no_finito_se_rechazan(self):
        with self.assertRaises(ValueError):
            evaluar(100, {"AAA": {"take_profit": {"nivel": 100, "avisado": "si"}}})
        for nivel in (True, 0, float("nan"), 10 ** 400):
            with self.subTest(nivel=nivel), self.assertRaises(ValueError):
                evaluar(100, niveles={"AAA": {"take_profit": nivel}})

    def test_hora_sin_zona_se_rechaza(self):
        with self.assertRaises(ValueError):
            en_horario_mercado(dt.datetime(2026, 11, 4, 12))


class FronterasVencimientos(unittest.TestCase):
    INSTRUMENTOS = {"BOND1": {"vencimiento": "2026-12-31"}}

    def test_saltar_umbrales_no_enciende_uno_mas_lejano_despues(self):
        eventos, estado = evaluar_vencimientos(self.INSTRUMENTOS, {}, dt.date(2026, 12, 21))
        self.assertEqual(len(eventos), 1)
        self.assertEqual(estado["BOND1"]["avisados"], [15])
        eventos, estado = evaluar_vencimientos(self.INSTRUMENTOS, estado, dt.date(2026, 12, 22))
        self.assertEqual(eventos, [])
        eventos, _ = evaluar_vencimientos(self.INSTRUMENTOS, estado, dt.date(2026, 12, 24))
        self.assertEqual(len(eventos), 1)

    def test_cambiar_vencimiento_reinicia_avisos(self):
        _, estado = evaluar_vencimientos(self.INSTRUMENTOS, {}, dt.date(2026, 12, 21))
        cambiado = {"BOND1": {"vencimiento": "2027-01-01"}}
        eventos, nuevo = evaluar_vencimientos(cambiado, estado, dt.date(2026, 12, 22))
        self.assertEqual(len(eventos), 1)
        self.assertEqual(nuevo["BOND1"]["vencimiento"], "2027-01-01")

    def test_hoy_avisa_y_ayer_vencida_no(self):
        eventos, _ = evaluar_vencimientos(self.INSTRUMENTOS, {}, dt.date(2026, 12, 31))
        self.assertEqual(len(eventos), 1)
        eventos, _ = evaluar_vencimientos(self.INSTRUMENTOS, {}, dt.date(2027, 1, 1))
        self.assertEqual(eventos, [])

    def test_no_fecha_y_especies_retiradas_no_conservan_avisos(self):
        estado = {"BOND1": {"vencimiento": "2026-12-31", "avisados": [30]}}
        eventos, nuevo = evaluar_vencimientos({"BOND1": {"vencimiento": None}}, estado, dt.date(2026, 12, 1))
        self.assertEqual(eventos, [])
        self.assertEqual(nuevo, {})

    def test_no_mutacion_y_salida_json(self):
        _, estado = evaluar_vencimientos(self.INSTRUMENTOS, {}, dt.date(2026, 12, 1))
        antes = copy.deepcopy(estado)
        _, nuevo = evaluar_vencimientos(self.INSTRUMENTOS, estado, dt.date(2026, 12, 24))
        self.assertEqual(estado, antes)
        self.assertNotEqual(nuevo, estado)
        json.dumps(nuevo, allow_nan=False)

    def test_fecha_invalida_y_umbrales_invalidos_se_rechazan(self):
        with self.assertRaises(ValueError):
            evaluar_vencimientos({"BOND1": {"vencimiento": "sin fecha"}}, {}, dt.date(2026, 12, 1))
        with self.assertRaises(ValueError):
            evaluar_vencimientos(self.INSTRUMENTOS, {}, dt.date(2026, 12, 1), umbrales=(True,))


if __name__ == "__main__":
    unittest.main()
