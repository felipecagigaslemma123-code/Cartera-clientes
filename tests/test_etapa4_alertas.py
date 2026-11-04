import copy
import datetime as dt
import json
import unittest
from zoneinfo import ZoneInfo

from cartera.alertas import Evento, en_horario_mercado, evaluar_niveles, evaluar_vencimientos
from cartera.notificar import Notificador
from cartera.precios import Cotizacion

AR = ZoneInfo("America/Argentina/Buenos_Aires")
T = dt.datetime(2026, 11, 4, 12, 0, tzinfo=AR)
NIVELES = {"AAA": {"take_profit": 1500.0, "stop_loss": 900.0}}


def cot(bid=None, ultimo=1200.0, estado="vivo", ticker="AAA"):
    return Cotizacion(ticker=ticker, ultimo=ultimo, bid=bid, ask=None, pct_dia=None, estado=estado, consultado_en=T)


def tipos(eventos):
    return [e.tipo for e in eventos]


class Horario(unittest.TestCase):
    def test_limites(self):
        self.assertTrue(en_horario_mercado(dt.datetime(2026, 11, 4, 11, 0, tzinfo=AR)))
        self.assertTrue(en_horario_mercado(dt.datetime(2026, 11, 4, 16, 59, tzinfo=AR)))
        self.assertFalse(en_horario_mercado(dt.datetime(2026, 11, 4, 10, 59, tzinfo=AR)))
        self.assertFalse(en_horario_mercado(dt.datetime(2026, 11, 4, 17, 0, tzinfo=AR)))

    def test_fin_de_semana(self):
        self.assertFalse(en_horario_mercado(dt.datetime(2026, 11, 7, 12, 0, tzinfo=AR)))

    def test_convierte_a_hora_argentina(self):
        self.assertTrue(en_horario_mercado(dt.datetime(2026, 11, 4, 15, 0, tzinfo=dt.timezone.utc)))


class Niveles(unittest.TestCase):
    def evaluar(self, cotizacion, estado=None, niveles=NIVELES, ahora=T):
        return evaluar_niveles({"AAA": cotizacion}, niveles, estado or {}, ahora)

    def test_dentro_de_la_banda_no_avisa(self):
        eventos, _ = self.evaluar(cot(bid=1200.0))
        self.assertEqual(eventos, [])

    def test_take_profit_incluye_el_limite(self):
        eventos, _ = self.evaluar(cot(bid=1500.0))
        self.assertEqual(tipos(eventos), ["take_profit"])
        self.assertEqual(eventos[0].ticker, "AAA")
        self.assertEqual(eventos[0].nivel, 1500.0)
        self.assertEqual(eventos[0].precio, 1500.0)

    def test_stop_loss_incluye_el_limite(self):
        eventos, _ = self.evaluar(cot(bid=900.0))
        self.assertEqual(tipos(eventos), ["stop_loss"])

    def test_usa_bid_y_no_el_ultimo(self):
        eventos, _ = self.evaluar(cot(bid=1400.0, ultimo=1600.0))
        self.assertEqual(eventos, [])

    def test_sin_bid_usa_el_ultimo(self):
        eventos, _ = self.evaluar(cot(bid=None, ultimo=1600.0))
        self.assertEqual(tipos(eventos), ["take_profit"])

    def test_nivel_nulo_no_alerta(self):
        eventos, _ = self.evaluar(cot(bid=1.0), niveles={"AAA": {"take_profit": 1500.0, "stop_loss": None}})
        self.assertEqual(eventos, [])

    def test_avisa_una_sola_vez(self):
        _, estado = self.evaluar(cot(bid=1600.0))
        eventos, _ = self.evaluar(cot(bid=1700.0), estado)
        self.assertEqual(eventos, [])

    def test_no_se_rearma_sin_alejarse_mas_de_1_por_ciento(self):
        _, estado = self.evaluar(cot(bid=1600.0))
        _, estado = self.evaluar(cot(bid=1490.0), estado)
        eventos, _ = self.evaluar(cot(bid=1510.0), estado)
        self.assertEqual(eventos, [])

    def test_se_rearma_al_alejarse_mas_de_1_por_ciento(self):
        _, estado = self.evaluar(cot(bid=1600.0))
        _, estado = self.evaluar(cot(bid=1480.0), estado)
        eventos, _ = self.evaluar(cot(bid=1510.0), estado)
        self.assertEqual(tipos(eventos), ["take_profit"])

    def test_cambiar_el_nivel_rearma(self):
        _, estado = self.evaluar(cot(bid=1600.0))
        eventos, _ = self.evaluar(cot(bid=1600.0), estado, {"AAA": {"take_profit": 1550.0, "stop_loss": 900.0}})
        self.assertEqual(tipos(eventos), ["take_profit"])

    def test_dato_viejo_no_dispara_y_avisa_que_no_se_chequeo(self):
        eventos, _ = self.evaluar(cot(bid=1600.0, estado="cache"))
        self.assertEqual(tipos(eventos), ["sin_chequeo"])

    def test_sin_chequeo_una_vez_por_dia(self):
        _, estado = self.evaluar(cot(ultimo=None, estado="sin_dato"))
        eventos, estado = self.evaluar(cot(ultimo=None, estado="sin_dato"), estado, ahora=T + dt.timedelta(hours=1))
        self.assertEqual(eventos, [])
        eventos, _ = self.evaluar(cot(ultimo=None, estado="sin_dato"), estado, ahora=T + dt.timedelta(days=1))
        self.assertEqual(tipos(eventos), ["sin_chequeo"])

    def test_especie_con_nivel_ausente_de_las_cotizaciones(self):
        eventos, _ = evaluar_niveles({}, NIVELES, {}, T)
        self.assertEqual(tipos(eventos), ["sin_chequeo"])

    def test_especie_sin_niveles_no_genera_sin_chequeo(self):
        eventos, _ = evaluar_niveles({"ZZZ": cot(ultimo=None, estado="sin_dato", ticker="ZZZ")}, {}, {}, T)
        self.assertEqual(eventos, [])

    def test_no_muta_el_estado_y_es_serializable(self):
        _, estado = self.evaluar(cot(bid=1600.0))
        anterior = copy.deepcopy(estado)
        _, nuevo = self.evaluar(cot(bid=1480.0), estado)
        self.assertEqual(estado, anterior)
        json.dumps(nuevo)


class Vencimientos(unittest.TestCase):
    INSTRUMENTOS = {"BOND1": {"vencimiento": "2026-12-31"}}

    def evaluar(self, hoy, estado=None):
        return evaluar_vencimientos(self.INSTRUMENTOS, estado or {}, hoy)

    def test_lejos_no_avisa(self):
        eventos, _ = self.evaluar(dt.date(2026, 11, 30))
        self.assertEqual(eventos, [])

    def test_avisa_al_llegar_a_un_umbral_y_no_repite(self):
        eventos, estado = self.evaluar(dt.date(2026, 12, 1))
        self.assertEqual(tipos(eventos), ["vencimiento"])
        eventos, estado = self.evaluar(dt.date(2026, 12, 2), estado)
        self.assertEqual(eventos, [])
        eventos, _ = self.evaluar(dt.date(2026, 12, 16), estado)
        self.assertEqual(tipos(eventos), ["vencimiento"])

    def test_varios_umbrales_alcanzados_generan_un_solo_aviso(self):
        eventos, estado = self.evaluar(dt.date(2026, 12, 21))
        self.assertEqual(len(eventos), 1)
        eventos, _ = self.evaluar(dt.date(2026, 12, 22), estado)
        self.assertEqual(eventos, [])

    def test_ya_vencida_no_avisa(self):
        eventos, _ = self.evaluar(dt.date(2027, 1, 1))
        self.assertEqual(eventos, [])

    def test_estado_serializable(self):
        _, estado = self.evaluar(dt.date(2026, 12, 1))
        json.dumps(estado)


class Notificaciones(unittest.TestCase):
    EVENTO = Evento(tipo="stop_loss", ticker="AAA", precio=900.0, nivel=900.0, mensaje="AAA toco stop loss")

    def test_un_canal_caido_no_frena_a_los_demas(self):
        recibidos = []

        def roto(titulo, mensaje):
            raise IOError("sin red")

        def sano(titulo, mensaje):
            recibidos.append((titulo, mensaje))

        errores = Notificador([roto, sano]).enviar([self.EVENTO], "cliente-demo")
        self.assertEqual(len(recibidos), 1)
        self.assertEqual(len(errores), 1)

    def test_identifica_al_cliente_por_slug(self):
        recibidos = []
        Notificador([lambda t, m: recibidos.append(t + " " + m)]).enviar([self.EVENTO], "cliente-demo")
        self.assertIn("cliente-demo", recibidos[0])
        self.assertIn("AAA", recibidos[0])

    def test_sin_eventos_no_envia(self):
        recibidos = []
        Notificador([lambda t, m: recibidos.append(m)]).enviar([], "cliente-demo")
        self.assertEqual(recibidos, [])


if __name__ == "__main__":
    unittest.main()
