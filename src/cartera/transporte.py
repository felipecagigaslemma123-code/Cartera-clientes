"""Consultas públicas de precios, sin datos ni credenciales del cliente."""

import json
from urllib.request import Request, urlopen


def _constante_invalida(texto):
    raise ValueError("La respuesta de precios contiene un número no finito: " + texto)


def consultar_json(url):
    solicitud = Request(url, headers={"User-Agent": "cartera/0.2", "Accept": "application/json"})
    with urlopen(solicitud, timeout=10) as respuesta:
        contenido = respuesta.read(5 * 1024 * 1024 + 1)
    if len(contenido) > 5 * 1024 * 1024:
        raise ValueError("La respuesta de precios supera el tamaño permitido.")
    return json.loads(contenido.decode("utf-8"), parse_constant=_constante_invalida)
