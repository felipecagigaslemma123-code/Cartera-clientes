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

if __name__ == "__main__":
    unittest.main()
