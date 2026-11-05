"""Avisos con transportes simulados; nunca se usa el Llavero ni la red real."""

import json
import subprocess
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from cartera import notificar


TOKEN = "123456:TOKEN-FICTICIO"
CHAT = "42"


def evento(tipo="stop_loss", precio=900.0, mensaje="AAA tocó stop loss"):
    return SimpleNamespace(tipo=tipo, ticker="AAA", precio=precio, nivel=900.0, mensaje=mensaje)


def respuesta(cuerpo):
    class Respuesta:
        def __enter__(self):
            return self
        def __exit__(self, *argumentos):
            return False
        def read(self, *argumentos):
            return cuerpo
    return Respuesta()


class NotificadorSeguro(unittest.TestCase):
    def test_un_solo_mensaje_por_canal_contiene_todos_los_eventos(self):
        recibidos = []
        canales = [lambda titulo, mensaje: recibidos.append((titulo, mensaje))]
        errores = notificar.Notificador(canales).enviar([evento(), evento("take_profit", 1500, "AAA tocó take profit")], "demo")
        self.assertEqual(errores, [])
        self.assertEqual(len(recibidos), 1)
        self.assertIn("demo", recibidos[0][0])
        self.assertIn("demo", recibidos[0][1])
        self.assertIn("AAA tocó stop loss", recibidos[0][1])
        self.assertIn("AAA tocó take profit", recibidos[0][1])

    def test_todos_los_canales_se_intentan_y_sus_errores_no_revelan_textos(self):
        recibidos = []
        def roto(titulo, mensaje):
            raise OSError("TOKEN-FICTICIO https://api.telegram.org secreto")
        roto.__name__ = TOKEN
        def sano(titulo, mensaje):
            recibidos.append(mensaje)
        errores = notificar.Notificador([roto, sano, roto]).enviar([evento()], "demo")
        self.assertEqual(len(errores), 2)
        self.assertEqual(len(recibidos), 1)
        self.assertIn("canal_1", errores[0])
        self.assertIn("canal_3", errores[1])
        self.assertNotIn("TOKEN", str(errores))
        self.assertNotIn("https", str(errores))

    def test_sin_eventos_no_invoca_ningun_canal(self):
        def prohibido(titulo, mensaje):
            self.fail("No debía invocarse un canal")
        self.assertEqual(notificar.Notificador([prohibido]).enviar([], "demo"), [])


class CanalesSimulados(unittest.TestCase):
    def test_macos_contenido_es_argumento_y_errores_se_sanitizan(self):
        peligroso = '\"; do shell script \"texto ficticio'
        with patch("cartera.notificar.subprocess.run") as ejecutar:
            notificar.canal_macos("demo", peligroso)
        argumentos = ejecutar.call_args.args[0]
        opciones = ejecutar.call_args.kwargs
        self.assertEqual(argumentos[-2:], ["demo", peligroso])
        self.assertNotIn(peligroso, argumentos[2])
        self.assertIs(opciones["shell"], False)
        self.assertIs(opciones["check"], True)
        self.assertEqual(opciones["timeout"], 10)
        with patch("cartera.notificar.subprocess.run", side_effect=subprocess.CalledProcessError(1, TOKEN)):
            with self.assertRaises(notificar.ErrorNotificacion) as contexto:
                notificar.canal_macos("demo", "texto ficticio")
        self.assertNotIn(TOKEN, str(contexto.exception))

    def test_telegram_json_sin_interpretar_formato_y_tiempo_limitado(self):
        with patch.dict("os.environ", {"TELEGRAM_BOT_TOKEN": TOKEN, "TELEGRAM_CHAT_ID": CHAT}, clear=True), patch(
            "cartera.notificar.urlopen", return_value=respuesta(b'{"ok":true}')
        ) as abrir, patch("cartera.notificar.subprocess.run") as llavero:
            notificar.canal_telegram("demo", "<b>texto ficticio</b>")
        solicitud = abrir.call_args.args[0]
        self.assertEqual(solicitud.get_method(), "POST")
        self.assertEqual(abrir.call_args.kwargs["timeout"], 10)
        datos = json.loads(solicitud.data)
        self.assertEqual(datos["chat_id"], CHAT)
        self.assertNotIn("parse_mode", datos)
        self.assertIn("<b>texto ficticio</b>", datos["text"])
        llavero.assert_not_called()

    def test_recorte_incluye_aviso_y_cuenta_titulo(self):
        with patch.dict("os.environ", {"TELEGRAM_BOT_TOKEN": TOKEN, "TELEGRAM_CHAT_ID": CHAT}, clear=True), patch(
            "cartera.notificar.urlopen", return_value=respuesta(b'{"ok":true}')
        ) as abrir:
            notificar.canal_telegram("título demo", "x" * 9000)
        texto = json.loads(abrir.call_args.args[0].data)["text"]
        self.assertLessEqual(len(texto), 4000)
        self.assertIn("recortado", texto)

    def test_telegram_rechaza_respuestas_sin_confirmacion_exacta(self):
        for cuerpo in (b'{"ok":false}', b'{"ok":1}', b'[]', b'{roto', b'{"description":"TOKEN-FICTICIO"}'):
            with self.subTest(cuerpo=cuerpo), patch.dict(
                "os.environ", {"TELEGRAM_BOT_TOKEN": TOKEN, "TELEGRAM_CHAT_ID": CHAT}, clear=True
            ), patch("cartera.notificar.urlopen", return_value=respuesta(cuerpo)):
                with self.assertRaises(notificar.ErrorNotificacion) as contexto:
                    notificar.canal_telegram("demo", "texto ficticio")
                self.assertNotIn("TOKEN", str(contexto.exception))
                self.assertNotIn("https", str(contexto.exception))

    def test_telegram_no_expone_error_de_red(self):
        with patch.dict("os.environ", {"TELEGRAM_BOT_TOKEN": TOKEN, "TELEGRAM_CHAT_ID": CHAT}, clear=True), patch(
            "cartera.notificar.urlopen", side_effect=OSError("https://api.telegram.org/bot" + TOKEN)
        ):
            with self.assertRaises(notificar.ErrorNotificacion) as contexto:
                notificar.canal_telegram("demo", "texto ficticio")
            errores = notificar.Notificador([notificar.canal_telegram]).enviar([evento()], "demo")
        self.assertNotIn(TOKEN, str(contexto.exception))
        self.assertEqual(errores, ["No se pudo entregar por canal_telegram."])


class CredencialesSimuladas(unittest.TestCase):
    def test_entorno_completo_tiene_prioridad_y_se_recorta_espacio(self):
        with patch.dict("os.environ", {"TELEGRAM_BOT_TOKEN": " " + TOKEN + "\n", "TELEGRAM_CHAT_ID": " 42 "}, clear=True), patch(
            "cartera.notificar.subprocess.run"
        ) as llavero:
            self.assertEqual(notificar.credencial_telegram(), (TOKEN, CHAT))
        llavero.assert_not_called()

    def test_entorno_incompleto_recurre_a_par_completo_del_llavero_simulado(self):
        def ejecutar(argumentos, **opciones):
            self.assertEqual(argumentos[:3], ["security", "find-generic-password", "-s"])
            self.assertEqual(argumentos[-1], "-w")
            self.assertIs(opciones["shell"], False)
            self.assertEqual(opciones["timeout"], 5)
            return SimpleNamespace(returncode=0, stdout="token del llavero\n" if argumentos[3].endswith("token") else "chat del llavero\n")
        with patch.dict("os.environ", {"TELEGRAM_BOT_TOKEN": TOKEN}, clear=True), patch(
            "cartera.notificar.subprocess.run", side_effect=ejecutar
        ) as llavero:
            self.assertEqual(notificar.credencial_telegram(), ("token del llavero", "chat del llavero"))
        self.assertEqual(llavero.call_count, 2)

    def test_llavero_ausente_vacio_o_con_timeout_devuelve_none(self):
        for salida in (SimpleNamespace(returncode=44, stdout=""), SimpleNamespace(returncode=0, stdout=" \n"), OSError(TOKEN)):
            with self.subTest(salida=type(salida).__name__), patch.dict("os.environ", {}, clear=True):
                contexto = patch("cartera.notificar.subprocess.run", side_effect=salida) if isinstance(salida, Exception) else patch(
                    "cartera.notificar.subprocess.run", return_value=salida)
                with contexto:
                    self.assertIsNone(notificar.credencial_telegram())

    def test_canales_disponibles_no_prueba_sus_transportes(self):
        with patch("cartera.notificar.credencial_telegram", return_value=(TOKEN, CHAT)), patch(
            "cartera.notificar.urlopen"
        ) as abrir, patch("cartera.notificar.subprocess.run") as ejecutar:
            self.assertEqual(notificar.canales_disponibles(), [notificar.canal_macos, notificar.canal_telegram])
        abrir.assert_not_called()
        ejecutar.assert_not_called()
        with patch("cartera.notificar.credencial_telegram", return_value=None):
            self.assertEqual(notificar.canales_disponibles(), [notificar.canal_macos])

    def test_sin_credenciales_no_intenta_red(self):
        with patch("cartera.notificar.credencial_telegram", return_value=None), patch("cartera.notificar.urlopen") as abrir:
            with self.assertRaises(notificar.ErrorNotificacion):
                notificar.canal_telegram("demo", "texto ficticio")
        abrir.assert_not_called()


if __name__ == "__main__":
    unittest.main()
