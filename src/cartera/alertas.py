"""Evaluación pura de niveles y vencimientos, sin red ni canales de aviso."""

import copy
import math
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import Optional
from zoneinfo import ZoneInfo


@dataclass
class Evento:
    tipo: str
    ticker: Optional[str]
    precio: Optional[float]
    nivel: Optional[float]
    mensaje: str


_LADOS = ("take_profit", "stop_loss")
_ARGENTINA = ZoneInfo("America/Argentina/Buenos_Aires")


def _hora_argentina(ahora):
    if not isinstance(ahora, datetime) or ahora.utcoffset() is None:
        raise ValueError("La hora de evaluación debe incluir zona horaria.")
    return ahora.astimezone(_ARGENTINA)


def en_horario_mercado(ahora):
    hora = _hora_argentina(ahora)
    return hora.weekday() < 5 and 11 <= hora.hour < 17


def _positivo(valor):
    if isinstance(valor, bool) or not isinstance(valor, (int, float)):
        return None
    try:
        numero = float(valor)
    except (OverflowError, ValueError):
        return None
    return numero if math.isfinite(numero) and numero > 0 else None


def _nivel(valor):
    if valor is None:
        return None
    numero = _positivo(valor)
    if numero is None:
        raise ValueError("Los niveles deben ser números positivos y finitos o null.")
    return numero


def _fecha_iso(valor):
    if not isinstance(valor, str):
        raise ValueError("La fecha debe tener formato AAAA-MM-DD.")
    try:
        return date.fromisoformat(valor).isoformat()
    except ValueError:
        raise ValueError("La fecha debe tener formato AAAA-MM-DD.") from None


def _validar_estado_niveles(estado):
    if not isinstance(estado, dict):
        raise ValueError("El estado de niveles debe ser un objeto.")
    for ticker, registro in estado.items():
        if not isinstance(ticker, str) or not ticker or not isinstance(registro, dict):
            raise ValueError("El estado contiene una especie inválida.")
        if set(registro) - set(_LADOS) - {"sin_chequeo"}:
            raise ValueError("El estado de niveles tiene campos desconocidos.")
        for lado in _LADOS:
            if lado not in registro:
                continue
            guardado = registro[lado]
            if not isinstance(guardado, dict) or set(guardado) != {"nivel", "avisado"}:
                raise ValueError("El estado de un nivel es inválido.")
            _nivel(guardado["nivel"])
            if type(guardado["avisado"]) is not bool:
                raise ValueError("La marca de aviso debe ser booleana.")
        if registro.get("sin_chequeo") is not None:
            _fecha_iso(registro["sin_chequeo"])


def _precio_texto(precio):
    texto = format(Decimal(str(precio)), ",f")
    if "." in texto:
        texto = texto.rstrip("0").rstrip(".")
    return texto.translate(str.maketrans({",": ".", ".": ","}))


def evaluar_niveles(cotizaciones, niveles, estado, ahora):
    """Devuelve eventos y un estado nuevo; nunca modifica el estado recibido.

    Cada especie guarda take_profit/stop_loss con nivel y avisado, y la fecha
    del último sin_chequeo. Los niveles eliminados se desarman y las especies
    retiradas se purgan para no ocultar una alerta al volver a configurarlas.
    """
    hoy = _hora_argentina(ahora).date().isoformat()
    if not isinstance(cotizaciones, dict) or not isinstance(niveles, dict):
        raise ValueError("Cotizaciones y niveles deben ser objetos por especie.")
    _validar_estado_niveles(estado)
    anterior = copy.deepcopy(estado)
    eventos, nuevo = [], {}
    for ticker, configuracion in niveles.items():
        if not isinstance(ticker, str) or not ticker or not isinstance(configuracion, dict):
            raise ValueError("La configuración de niveles contiene una especie inválida.")
        valores = {lado: _nivel(configuracion.get(lado)) for lado in _LADOS}
        if valores["take_profit"] is not None and valores["stop_loss"] is not None:
            if valores["take_profit"] <= valores["stop_loss"]:
                raise ValueError("Take profit debe ser mayor que stop loss.")
        if all(nivel is None for nivel in valores.values()):
            continue
        previo = anterior.get(ticker, {})
        actual = {"sin_chequeo": previo.get("sin_chequeo")}
        for lado, nivel in valores.items():
            guardado = previo.get(lado, {})
            avisado = guardado.get("avisado", False) if guardado.get("nivel") == nivel and nivel is not None else False
            actual[lado] = {"nivel": nivel, "avisado": avisado}
        nuevo[ticker] = actual
        cotizacion = cotizaciones.get(ticker)
        referencia = None
        if (cotizacion is not None and getattr(cotizacion, "estado", None) == "vivo"
                and getattr(cotizacion, "ticker", ticker) == ticker):
            referencia = _positivo(getattr(cotizacion, "bid", None))
            if referencia is None:
                referencia = _positivo(getattr(cotizacion, "ultimo", None))
        if referencia is None:
            if actual["sin_chequeo"] != hoy:
                eventos.append(Evento("sin_chequeo", ticker, None, None,
                                      "{}: no se pudo chequear, no hay cotización en vivo.".format(ticker)))
                actual["sin_chequeo"] = hoy
            continue
        precio_decimal = Decimal(str(referencia))
        for lado, nivel in valores.items():
            if nivel is None:
                continue
            objetivo = Decimal(str(nivel))
            registro = actual[lado]
            if registro["avisado"]:
                dentro = (precio_decimal < objetivo * Decimal("0.99") if lado == "take_profit"
                          else precio_decimal > objetivo * Decimal("1.01"))
                if dentro:
                    registro["avisado"] = False
            disparado = precio_decimal >= objetivo if lado == "take_profit" else precio_decimal <= objetivo
            if disparado and not registro["avisado"]:
                eventos.append(Evento(lado, ticker, referencia, nivel,
                                      "{} {}: precio {}, nivel {}.".format(
                                          ticker, lado.replace("_", " "), _precio_texto(referencia), _precio_texto(nivel))))
                registro["avisado"] = True
    return eventos, nuevo


def _validar_estado_vencimientos(estado):
    if not isinstance(estado, dict):
        raise ValueError("El estado de vencimientos debe ser un objeto.")
    for ticker, registro in estado.items():
        if not isinstance(ticker, str) or not ticker or not isinstance(registro, dict):
            raise ValueError("El estado de vencimientos contiene una especie inválida.")
        if set(registro) != {"vencimiento", "avisados"}:
            raise ValueError("El estado de vencimientos tiene campos inválidos.")
        _fecha_iso(registro["vencimiento"])
        if not isinstance(registro["avisados"], list) or any(type(u) is not int or u < 0 for u in registro["avisados"]):
            raise ValueError("Los umbrales avisados deben ser enteros no negativos.")


def _mensaje_vencimiento(ticker, fecha, dias):
    fecha_local = date.fromisoformat(fecha).strftime("%d/%m/%Y")
    if dias == 0:
        return "{} vence hoy ({}).".format(ticker, fecha_local)
    plazo = "falta 1 día" if dias == 1 else "faltan {} días".format(dias)
    return "{} vence el {}: {}.".format(ticker, fecha_local, plazo)


def evaluar_vencimientos(instrumentos, estado, hoy, umbrales=(30, 15, 7, 1)):
    """Avisa solo el umbral más cercano alcanzado, sin repetirlo ni mutar entradas."""
    if not isinstance(instrumentos, dict) or not isinstance(hoy, date) or isinstance(hoy, datetime):
        raise ValueError("Instrumentos debe ser un objeto y hoy una fecha sin hora.")
    _validar_estado_vencimientos(estado)
    anterior = copy.deepcopy(estado)
    umbrales = list(umbrales)
    if any(type(umbral) is not int or umbral < 0 for umbral in umbrales):
        raise ValueError("Los umbrales deben ser enteros no negativos.")
    eventos, nuevo = [], {}
    for ticker, instrumento in instrumentos.items():
        if not isinstance(ticker, str) or not ticker or not isinstance(instrumento, dict):
            raise ValueError("Los instrumentos contienen una especie inválida.")
        fecha = instrumento.get("vencimiento")
        if fecha is None:
            continue
        fecha = _fecha_iso(fecha)
        previo = anterior.get(ticker, {})
        avisados = list(previo.get("avisados", [])) if previo.get("vencimiento") == fecha else []
        nuevo[ticker] = {"vencimiento": fecha, "avisados": avisados}
        dias = (date.fromisoformat(fecha) - hoy).days
        if dias < 0:
            continue
        alcanzados = [umbral for umbral in umbrales if dias <= umbral]
        if not alcanzados:
            continue
        umbral = min(alcanzados)
        if umbral in avisados:
            continue
        eventos.append(Evento("vencimiento", ticker, None, None,
                              _mensaje_vencimiento(ticker, fecha, dias)))
        avisados.append(umbral)
        avisados.sort(reverse=True)
    return eventos, nuevo
