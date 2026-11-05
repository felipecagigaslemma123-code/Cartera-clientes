import datetime as dt
import io
import json
import plistlib
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import patch
from zoneinfo import ZoneInfo

from cartera import notificar
from cartera.__main__ import main
from cartera.alertas_comando import correr_alertas
from cartera.almacenamiento import cargar_cartera, importar_cartera

RAIZ = Path(__file__).resolve().parents[1]
DEMO = RAIZ / "fixtures" / "punto_partida_demo.xlsx"
AR = ZoneInfo("America/Argentina/Buenos_Aires")
ABIERTO = dt.datetime(2026, 11, 4, 12, 0, tzinfo=AR)
CERRADO = dt.datetime(2026, 11, 4, 20, 0, tzinfo=AR)
SECRETO = "123456:TOKEN-SECRETO"


def fila(ticker, precio):
    return {"symbol": ticker, "c": precio, "px_bid": precio, "px_ask": precio, "pct_change": 0.0}


class Base(unittest.TestCase):
    def setUp(self):
        temporal = tempfile.TemporaryDirectory()
        self.addCleanup(temporal.cleanup)
        self.datos = Path(temporal.name) / "datos"
        importar_cartera(self.datos, "demo", DEMO)
        self.carpeta = self.datos / "clientes" / "demo"
        self.punto, _ = cargar_cartera(self.datos, "demo")
        self.recibidos = []
        self.llamadas = []
        self.precio = 1600.0

    def canal(self, titulo, mensaje):
        self.recibidos.append(titulo + " " + mensaje)

    def fetch(self, url):
        self.llamadas.append(url)
        return [fila("AAA", self.precio), fila("BBB", 1100.0)]

    def niveles(self, contenido=None):
        contenido = contenido if contenido is not None else {"AAA": {"take_profit": 1500.0, "stop_loss": 900.0}}
        texto = contenido if isinstance(contenido, str) else json.dumps(contenido)
        (self.carpeta / "niveles.json").write_text(texto, encoding="utf-8")

    def correr(self, ahora=ABIERTO, canales=None, fetch=None):
        return correr_alertas(self.carpeta, self.punto, "demo", fetch or self.fetch,
                              canales if canales is not None else [self.canal], ahora)

    def tipos(self, resultado):
        return [e.tipo for e in resultado["eventos"]]

    def estado(self):
        return json.loads((self.carpeta / "estado_alertas.json").read_text(encoding="utf-8"))


class Corrida(Base):
    def test_dispara_y_avisa_en_un_solo_mensaje(self):
        self.niveles()
        r = self.correr()
        self.assertEqual(sorted(self.tipos(r)), ["control", "take_profit"])
        self.assertTrue(r["entregado"])
        self.assertTrue(r["evaluo_niveles"])
        self.assertEqual(len(self.recibidos), 1)
        self.assertIn("demo", self.recibidos[0])
        self.assertIn("AAA", self.recibidos[0])

    def test_no_repite_en_la_corrida_siguiente(self):
        self.niveles()
        self.correr()
        self.recibidos.clear()
        r = self.correr(ABIERTO + dt.timedelta(minutes=5))
        self.assertEqual(r["eventos"], [])
        self.assertEqual(self.recibidos, [])

    def test_consulta_solo_los_paneles_necesarios(self):
        self.niveles()
        self.correr()
        self.assertEqual(self.llamadas, ["https://data912.com/live/arg_cedears"])

    def test_sin_niveles_no_consulta_la_red(self):
        self.correr()
        self.assertEqual(self.llamadas, [])

    def test_fuera_de_horario_solo_vencimientos(self):
        self.niveles()
        (self.carpeta / "instrumentos.json").write_text('{"BOND1": {"vencimiento": "2026-11-10"}}', encoding="utf-8")
        r = self.correr(CERRADO)
        self.assertEqual(self.tipos(r), ["vencimiento"])
        self.assertFalse(r["evaluo_niveles"])
        self.assertEqual(self.llamadas, [])

    def test_fuente_caida_avisa_que_no_se_chequeo(self):
        self.niveles()

        def caida(url):
            raise OSError("sin red")

        r = self.correr(fetch=caida)
        self.assertIn("sin_chequeo", self.tipos(r))
        self.assertNotIn("take_profit", self.tipos(r))


class AvisoDeControl(Base):
    def test_una_vez_por_dia(self):
        self.correr()
        self.assertIn("no hay niveles", self.recibidos[0])
        self.recibidos.clear()
        self.correr(ABIERTO + dt.timedelta(hours=1))
        self.assertEqual(self.recibidos, [])
        self.correr(ABIERTO + dt.timedelta(days=1))
        self.assertEqual(len(self.recibidos), 1)

    def test_informa_cuantas_especies_tienen_niveles(self):
        self.niveles({"AAA": {"take_profit": 5000.0, "stop_loss": 100.0}, "BBB": {"take_profit": None, "stop_loss": 100.0}})
        self.correr()
        self.assertIn("2", self.recibidos[0])

    def test_no_se_envia_fuera_de_horario(self):
        self.correr(CERRADO)
        self.assertEqual(self.recibidos, [])


class EntregaFallida(Base):
    def roto(self, titulo, mensaje):
        raise IOError("sin red")

    def test_sin_ningun_canal_no_marca_como_avisado(self):
        self.niveles()
        r = self.correr(canales=[self.roto])
        self.assertFalse(r["entregado"])
        self.assertEqual(len(r["errores"]), 1)
        r = self.correr(ABIERTO + dt.timedelta(minutes=5))
        self.assertIn("take_profit", self.tipos(r))
        self.assertEqual(len(self.recibidos), 1)

    def test_con_un_canal_alcanza(self):
        self.niveles()
        r = self.correr(canales=[self.roto, self.canal])
        self.assertTrue(r["entregado"])
        self.assertEqual(len(r["errores"]), 1)
        self.assertEqual(self.correr(ABIERTO + dt.timedelta(minutes=5))["eventos"], [])

    def test_el_fallo_queda_en_el_log(self):
        self.niveles()
        self.correr(canales=[self.roto, self.canal])
        self.assertIn("take_profit", (self.carpeta / "alertas.log").read_text(encoding="utf-8"))


class NivelesInvalidos(Base):
    def casos(self):
        return (
            "{roto",
            {"ZZZ": {"take_profit": 10.0, "stop_loss": None}},
            {"AAA": {"take_profit": "mil", "stop_loss": None}},
            {"AAA": {"take_profit": -1.0, "stop_loss": None}},
            {"AAA": {"take_profit": 900.0, "stop_loss": 900.0}},
        )

    def test_avisa_y_no_evalua(self):
        for numero, caso in enumerate(self.casos()):
            estado = self.carpeta / "estado_alertas.json"
            if estado.exists():
                estado.unlink()
            self.llamadas.clear()
            self.niveles(caso)
            r = self.correr()
            self.assertFalse(r["evaluo_niveles"], numero)
            self.assertEqual(self.llamadas, [], numero)
            sin_chequeo = [e for e in r["eventos"] if e.tipo == "sin_chequeo"]
            self.assertEqual(len(sin_chequeo), 1, numero)
            self.assertIsNone(sin_chequeo[0].ticker, numero)

    def test_una_vez_por_dia(self):
        self.niveles("{roto")
        self.correr()
        self.assertEqual(self.correr(ABIERTO + dt.timedelta(minutes=5))["eventos"], [])


class Estado(Base):
    def test_guarda_el_formato_previsto(self):
        self.niveles()
        self.correr()
        estado = self.estado()
        self.assertEqual(estado["esquema_version"], 1)
        self.assertEqual(estado["control"], "2026-11-04")
        self.assertIn("AAA", estado["niveles"])

    def test_estado_ilegible_conserva_copia_y_sigue(self):
        self.niveles()
        (self.carpeta / "estado_alertas.json").write_text("{roto", encoding="utf-8")
        r = self.correr()
        self.assertIn("take_profit", self.tipos(r))
        self.assertEqual((self.carpeta / "estado_alertas.corrupto.json").read_text(encoding="utf-8"), "{roto")


class Canales(unittest.TestCase):
    def test_macos_pasa_el_texto_como_argumento_y_sin_shell(self):
        peligroso = '"; do shell script "rm -rf ~'
        with patch("cartera.notificar.subprocess.run") as correr:
            notificar.canal_macos("titulo", peligroso)
        argumentos, opciones = correr.call_args
        self.assertFalse(opciones.get("shell", False))
        self.assertEqual(argumentos[0][0], "osascript")
        self.assertIn(peligroso, argumentos[0])
        self.assertTrue(all(peligroso not in a for a in argumentos[0] if a.startswith("on run")))

    def respuesta(self, cuerpo):
        class Respuesta:
            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

            def read(self, *a):
                return cuerpo

        return Respuesta()

def notificar_evento():
    from cartera.alertas import Evento
    return Evento(tipo="stop_loss", ticker="AAA", precio=900.0, nivel=900.0, mensaje="AAA toco stop loss")


class Notificacion(unittest.TestCase):
    def test_varios_eventos_en_un_mensaje(self):
        recibidos = []
        notificar.Notificador([lambda t, m: recibidos.append(m)]).enviar(
            [notificar_evento(), notificar_evento()], "demo")
        self.assertEqual(len(recibidos), 1)
        self.assertEqual(recibidos[0].count("AAA toco stop loss"), 2)


class Comando(Base):
    def correr_cli(self):
        salida, errores = io.StringIO(), io.StringIO()
        with patch("cartera.__main__.consultar_json", side_effect=self.fetch):
            with redirect_stdout(salida), redirect_stderr(errores):
                return main(["--datos", str(self.datos), "alertas", "--cliente", "demo"])

    def test_termina_bien_si_se_entrega(self):
        with patch("cartera.notificar.canales_disponibles", return_value=[self.canal]):
            with patch("cartera.alertas_comando.ahora_argentina", return_value=ABIERTO):
                self.assertEqual(self.correr_cli(), 0)
        self.assertEqual(len(self.recibidos), 1)

    def test_termina_con_error_si_no_llega(self):
        def roto(titulo, mensaje):
            raise IOError("sin red")

        with patch("cartera.notificar.canales_disponibles", return_value=[roto]):
            with patch("cartera.alertas_comando.ahora_argentina", return_value=ABIERTO):
                codigo = self.correr_cli()
        self.assertNotEqual(codigo, 0)


if __name__ == "__main__":
    unittest.main()
