"""Canales de avisos: sin efectos al importar y sin secretos en los errores."""

import subprocess


_SCRIPT_MACOS = """on run argv
    display notification (item 2 of argv) with title (item 1 of argv)
end run"""


class ErrorNotificacion(RuntimeError):
    """Falla de entrega con un mensaje que no contiene datos del transporte."""


def _nombre_canal(canal, indice):
    if canal is canal_macos:
        return "canal_macos"
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


def canales_disponibles():
    """El comando manual entrega únicamente mediante notificaciones de macOS."""
    return [canal_macos]
