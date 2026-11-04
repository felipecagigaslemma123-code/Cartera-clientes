"""Lectura y validación del Excel que define la cartera inicial."""

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
import math
from numbers import Real
from pathlib import Path
from typing import List, Optional
from xml.etree.ElementTree import ParseError
from zipfile import BadZipFile
from zoneinfo import ZoneInfo

from openpyxl import load_workbook
from openpyxl.utils.exceptions import InvalidFileException


@dataclass
class Posicion:
    ticker: str
    especie: str
    tipo: str
    cantidad: float
    cotiza_cada: int


@dataclass
class Lote:
    ticker: str
    cantidad: float
    origen: str
    fecha: Optional[date]
    precio: Optional[float]
    costo: Optional[float]
    nota: str


@dataclass
class PuntoPartida:
    posiciones: List[Posicion]
    lotes: List[Lote]


class ErrorPuntoPartida(Exception):
    """Contiene todos los problemas de entrada detectados en el libro."""

    def __init__(self, errores: List[str]):
        self.errores = list(errores)
        super().__init__("\n".join(self.errores))


_COTIZA_POR_TIPO = {"cedear": 1, "accion": 1, "bono": 100, "on": 100, "letra": 100}


def _vacio(valor):
    return valor is None or (isinstance(valor, str) and not valor.strip())


def _texto(valor):
    if not isinstance(valor, str) or valor.strip().startswith("="):
        return None
    return valor.strip()


def _numero_positivo(valor, campo, contexto, errores):
    if isinstance(valor, bool) or not isinstance(valor, Real):
        errores.append(f"{contexto}: {campo} debe ser un número positivo.")
        return None
    try:
        numero = float(valor)
    except (OverflowError, ValueError):
        errores.append(f"{contexto}: {campo} debe ser un número positivo y finito.")
        return None
    if not math.isfinite(numero) or numero <= 0:
        errores.append(f"{contexto}: {campo} debe ser un número positivo y finito.")
        return None
    return numero


def _hoy_argentina():
    return datetime.now(ZoneInfo("America/Argentina/Buenos_Aires")).date()


def _fecha(valor, contexto, errores, hoy):
    if _vacio(valor):
        return None
    fecha = None
    if isinstance(valor, datetime):
        fecha = valor.date()
    elif isinstance(valor, date):
        fecha = valor
    elif isinstance(valor, str):
        try:
            fecha = date.fromisoformat(valor.strip())
        except ValueError:
            pass
    if fecha is None:
        errores.append(f"{contexto}: fecha de compra inválida; usá una fecha o AAAA-MM-DD.")
    elif fecha > hoy:
        errores.append(f"{contexto}: fecha de compra futura ({fecha.isoformat()}); hoy en Argentina es {hoy.isoformat()}.")
    return fecha


def _leer_posiciones(hoja, errores):
    posiciones = []
    vistos = set()
    for fila, valores in enumerate(
        hoja.iter_rows(min_row=5, max_col=5, values_only=True), 5
    ):
        ticker_bruto, especie_bruta, tipo_bruto, cantidad_bruta, cotiza_bruta = valores
        if _vacio(ticker_bruto) or _texto(ticker_bruto) == "Total":
            break
        ticker = _texto(ticker_bruto)
        contexto = f"Cartera fila {fila} ({ticker or 'ticker inválido'})"
        inicio = len(errores)
        if not ticker:
            errores.append(f"{contexto}: el ticker debe ser texto no vacío.")
        elif ticker in vistos:
            errores.append(f"{contexto}: ticker repetido en Cartera.")
        if ticker:
            vistos.add(ticker)
        especie = _texto(especie_bruta)
        if not especie:
            errores.append(f"{contexto}: falta el nombre de la especie.")
        tipo = _texto(tipo_bruto)
        if tipo not in _COTIZA_POR_TIPO:
            errores.append(f"{contexto}: tipo de activo desconocido: {tipo_bruto!r}.")
        cantidad = _numero_positivo(cantidad_bruta, "cantidad", contexto, errores)
        cotiza = _numero_positivo(cotiza_bruta, "cotiza cada", contexto, errores)
        if cotiza is not None and cotiza not in (1, 100):
            errores.append(f"{contexto}: cotiza cada debe ser 1 o 100.")
        elif tipo in _COTIZA_POR_TIPO and cotiza is not None:
            if cotiza != _COTIZA_POR_TIPO[tipo]:
                errores.append(f"{contexto}: cotiza cada no coincide con el tipo {tipo}.")
        if len(errores) == inicio:
            posiciones.append(Posicion(ticker, especie, tipo, cantidad, int(cotiza)))
    if not vistos:
        errores.append("Cartera: no contiene posiciones desde la fila 5.")
    return posiciones, vistos


def _leer_lotes(hoja, posiciones, tickers, errores, hoy):
    lotes = []
    presentes = set()
    cantidades = {}
    unidades = {p.ticker: p.cotiza_cada for p in posiciones}
    for fila, valores in enumerate(
        hoja.iter_rows(min_row=5, max_col=8, values_only=True), 5
    ):
        if all(_vacio(valor) for valor in valores):
            continue
        ticker_bruto, cantidad_bruta, origen_bruto, fecha_bruta, cotiza_bruta, precio_bruto, costo_bruto, nota_bruta = valores
        ticker = _texto(ticker_bruto)
        contexto = f"Lotes fila {fila} ({ticker or 'sin ticker'})"
        inicio = len(errores)
        if not ticker:
            errores.append(f"{contexto}: el ticker debe ser texto no vacío.")
        elif ticker not in tickers:
            errores.append(f"{contexto}: el ticker no está en Cartera.")
        if ticker:
            presentes.add(ticker)
        cantidad = _numero_positivo(cantidad_bruta, "cantidad", contexto, errores)
        if ticker and cantidad is not None:
            cantidades[ticker] = cantidades.get(ticker, Decimal("0")) + Decimal(str(cantidad))
        cotiza = _numero_positivo(cotiza_bruta, "cotiza cada", contexto, errores)
        if cotiza is not None and cotiza not in (1, 100):
            errores.append(f"{contexto}: cotiza cada debe ser 1 o 100.")
        elif ticker in unidades and cotiza is not None and cotiza != unidades[ticker]:
            errores.append(f"{contexto}: cotiza cada no coincide con Cartera.")
        fecha = _fecha(fecha_bruta, contexto, errores, hoy)
        origen_excel = _texto(origen_bruto)
        origen = "pendiente"
        precio = costo = None
        if origen_excel == "Extracto":
            origen = "extracto"
            costo = _numero_positivo(costo_bruto, "costo total de extracto", contexto, errores)
            if costo is not None and cantidad is not None and cotiza is not None:
                precio = costo / cantidad * cotiza
        elif origen_excel == "A estimar":
            if not _vacio(precio_bruto):
                origen = "estimado"
                precio = _numero_positivo(precio_bruto, "precio de compra estimado", contexto, errores)
                if _vacio(fecha_bruta):
                    errores.append(f"{contexto}: un precio estimado requiere fecha de compra.")
                if precio is not None and cantidad is not None and cotiza is not None:
                    costo = cantidad * precio / cotiza
        else:
            errores.append(f"{contexto}: origen desconocido: {origen_bruto!r}.")
        if ((precio is not None and (not math.isfinite(precio) or precio <= 0)) or
                (costo is not None and (not math.isfinite(costo) or costo <= 0))):
            errores.append(f"{contexto}: el cálculo de precio o costo no da un número positivo y finito.")
        if len(errores) == inicio:
            nota = "" if nota_bruta is None else str(nota_bruta)
            lotes.append(Lote(ticker, cantidad, origen, fecha, precio, costo, nota))
    for posicion in posiciones:
        if posicion.ticker not in presentes:
            errores.append(f"{posicion.ticker}: especie sin lotes.")
        elif abs(cantidades.get(posicion.ticker, Decimal("0")) - Decimal(str(posicion.cantidad))) > Decimal("0.5"):
            errores.append(f"{posicion.ticker}: la suma de cantidades de lotes no coincide con Cartera (tolerancia 0,5).")
    return lotes


def cargar_punto_partida(ruta) -> PuntoPartida:
    """Lee entradas sin evaluar fórmulas y rechaza el libro si hay algún error."""
    hoy = _hoy_argentina()
    try:
        entrada = ruta if hasattr(ruta, "read") else Path(ruta)
        libro = load_workbook(entrada, data_only=False, read_only=True)
    except (OSError, ValueError, BadZipFile, InvalidFileException, KeyError, IndexError, ParseError) as error:
        raise ErrorPuntoPartida([f"No se pudo abrir el Excel: {error}"]) from error
    try:
        errores = []
        for nombre in ("Cartera", "Lotes"):
            if nombre not in libro.sheetnames:
                errores.append(f"Falta la hoja obligatoria {nombre}.")
        posiciones, tickers = ([], set())
        if "Cartera" in libro.sheetnames:
            posiciones, tickers = _leer_posiciones(libro["Cartera"], errores)
        lotes = []
        if "Lotes" in libro.sheetnames:
            lotes = _leer_lotes(libro["Lotes"], posiciones, tickers, errores, hoy)
        if errores:
            raise ErrorPuntoPartida(errores)
        return PuntoPartida(posiciones, lotes)
    except (OSError, ValueError, BadZipFile, KeyError, IndexError, ParseError) as error:
        raise ErrorPuntoPartida([f"No se pudo leer el contenido del Excel: {error}"]) from error
    finally:
        libro.close()
