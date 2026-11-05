"""Canales de avisos: sin efectos al importar y sin secretos en los errores."""

import json
import os
import subprocess
from urllib.parse import quote
from urllib.request import Request, urlopen


_SCRIPT_MACOS = """on run argv
    display notification (item 2 of argv) with title (item 1 of argv)
end run"""
_LIMITE_TELEGRAM = 4000
_AVISO_RECORTE = "\n[Mensaje recortado]"


class ErrorNotificacion(RuntimeError):
    """Falla de entrega con un mensaje que no contiene datos del transporte."""


def _nombre_canal(canal, indice):
    if canal is canal_macos:
        return "canal_macos"
    if canal is canal_telegram:
        return "canal_telegram"
    # No usar __name__, repr ni texto de excepciones: podrían incluir secretos.
    return "canal_{}".format(indice)


class Notificador:
    def __init__(self, canales):
        self.canales = list(canales)

    def enviar(self, eventos, slug):
        eventos = list(eventos)
        if not eventos:
            return []
        titulo = "Alertas · {}".format(slug)
        lineas = ["Cliente: {}".format(slug)]
        for evento in eventos:
            lineas.append(str(evento.mensaje))
        mensaje = "\n".join(lineas)
        errores = []
        for indice, canal in enumerate(self.canales, 1):
            try:
                canal(titulo, mensaje)
            except Exception:
                errores.append("No se pudo entregar por {}.".format(_nombre_canal(canal, indice)))
        return errores


def canal_macos(titulo, mensaje):
    """Pasa contenido como argumentos; nunca como parte del AppleScript."""
    try:
        subprocess.run(
            ["osascript", "-e", _SCRIPT_MACOS, "--", titulo, mensaje],
            shell=False, check=True, capture_output=True, text=True, timeout=10,
        )
    except Exception:
        raise ErrorNotificacion("No se pudo entregar la notificación de macOS.") from None


def _leer_llavero(servicio):
    try:
        salida = subprocess.run(
            ["security", "find-generic-password", "-s", servicio, "-w"],
            shell=False, check=False, capture_output=True, text=True, timeout=5,
        )
        if salida.returncode != 0 or not isinstance(salida.stdout, str):
            return None
        return salida.stdout.strip() or None
    except Exception:
        return None


def credencial_telegram():
    """Devuelve un par completo del entorno o, en su defecto, del Llavero."""
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    chat = os.environ.get("TELEGRAM_CHAT_ID", "").strip()
    if token and chat:
        return token, chat
    token = _leer_llavero("cartera-telegram-token")
    chat = _leer_llavero("cartera-telegram-chat")
    return (token, chat) if token and chat else None


def canal_telegram(titulo, mensaje):
    """Entrega por Bot API y oculta URL, credenciales y detalles de cualquier falla."""
    try:
        credenciales = credencial_telegram()
        if credenciales is None:
            raise ErrorNotificacion("Telegram no tiene credenciales completas.")
        token, chat = credenciales
        texto = "{}\n{}".format(titulo, mensaje)
        if len(texto) > _LIMITE_TELEGRAM:
            texto = texto[:_LIMITE_TELEGRAM - len(_AVISO_RECORTE)] + _AVISO_RECORTE
        datos = json.dumps({"chat_id": chat, "text": texto}, ensure_ascii=False).encode("utf-8")
        solicitud = Request(
            "https://api.telegram.org/bot{}/sendMessage".format(quote(token, safe=":")),
            data=datos, headers={"Content-Type": "application/json"}, method="POST",
        )
        with urlopen(solicitud, timeout=10) as respuesta:
            cuerpo = respuesta.read(1024 * 1024 + 1)
        if len(cuerpo) > 1024 * 1024:
            raise ErrorNotificacion("Respuesta de Telegram demasiado grande.")
        resultado = json.loads(cuerpo.decode("utf-8"))
        if not isinstance(resultado, dict) or resultado.get("ok") is not True:
            raise ErrorNotificacion("Telegram no confirmó la entrega.")
    except Exception:
        raise ErrorNotificacion("No se pudo entregar el mensaje de Telegram.") from None


def canales_disponibles():
    canales = [canal_macos]
    if credencial_telegram() is not None:
        canales.append(canal_telegram)
    return canales
