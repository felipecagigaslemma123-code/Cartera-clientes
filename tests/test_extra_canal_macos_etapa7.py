"""El canal manual solo usa macOS; todas las entregas están reemplazadas."""

import subprocess
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from cartera import notificar


def evento(mensaje):
    return SimpleNamespace(mensaje=mensaje)


class CanalManualEtapa7(unittest.TestCase):
    def test_descubrir_canales_no_ejecuta_procesos_y_no_comparte_la_lista(self):
        with patch("cartera.notificar.subprocess.run") as ejecutar:
            primera = notificar.canales_disponibles()
            primera.clear()
            segunda = notificar.canales_disponibles()
        self.assertEqual(segunda, [notificar.canal_macos])
        ejecutar.assert_not_called()

    def test_una_corrida_con_varios_eventos_invoca_macos_una_sola_vez(self):
        with patch("cartera.notificar.subprocess.run") as ejecutar:
            errores = notificar.Notificador(notificar.canales_disponibles()).enviar(
                [evento("AAA take profit"), evento("BBB stop loss")], "demo-ficticio")
        self.assertEqual(errores, [])
        ejecutar.assert_called_once()
        argumentos = ejecutar.call_args.args[0]
        self.assertEqual(argumentos[0], "osascript")
        self.assertEqual(argumentos[-2], "Alertas · demo-ficticio")
        self.assertIn("AAA take profit", argumentos[-1])
        self.assertIn("BBB stop loss", argumentos[-1])
        self.assertIs(ejecutar.call_args.kwargs["shell"], False)

    def test_fallo_del_canal_se_identifica_sin_publicar_detalles_del_sistema(self):
        secreto = "detalle-ficticio-que-no-debe-salir"
        with patch("cartera.notificar.subprocess.run", side_effect=OSError(secreto)):
            errores = notificar.Notificador(notificar.canales_disponibles()).enviar(
                [evento("AAA take profit")], "demo-ficticio")
        self.assertEqual(errores, ["No se pudo entregar por canal_macos."])
        self.assertNotIn(secreto, str(errores))

    def test_timeout_del_sistema_es_error_controlado_y_no_se_reintenta_en_el_canal(self):
        agotado = subprocess.TimeoutExpired(["osascript", "argumento-ficticio"], 10,
                                            output="salida-ficticia", stderr="error-ficticio")
        with patch("cartera.notificar.subprocess.run", side_effect=agotado) as ejecutar:
            with self.assertRaises(notificar.ErrorNotificacion) as contexto:
                notificar.canal_macos("demo-ficticio", "AAA take profit")
        ejecutar.assert_called_once()
        self.assertEqual(str(contexto.exception), "No se pudo entregar la notificación de macOS.")
        self.assertNotIn("fictici", str(contexto.exception))


if __name__ == "__main__":
    unittest.main()
