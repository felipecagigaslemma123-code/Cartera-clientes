"""Valuaciones y comparación de costos de las posiciones.

La comparación con un precio del día cero mide la variación de precio aplicada
a la cantidad recibida. El resultado económico con flujos corresponde a una
etapa posterior y no se calcula a partir de esta diferencia.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from numbers import Real
from typing import Iterable, List, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from .punto_partida import Lote, Posicion


@dataclass
class ResultadoPosicion:
    ticker: str
    tipo: str
    valuacion: Optional[float]
    costo: Optional[float]
    estado_costo: str
    resultado: Optional[float]
    resultado_pct: Optional[float]
    resultado_dia_cero: Optional[float]
    resultado_dia_cero_pct: Optional[float]


@dataclass
class ResumenCartera:
    valuacion_total: float
    costo_comparable: float
    valuacion_comparable: float
    resultado_comparable: float
    posiciones_sin_costo: List[str]
    posiciones_sin_precio: List[str]


def _numero(valor: Real, nombre: str, permite_cero: bool = False) -> float:
    if isinstance(valor, bool) or not isinstance(valor, Real):
        raise ValueError(f"{nombre} debe ser un número finito")
    try:
        numero = float(valor)
    except (OverflowError, ValueError):
        raise ValueError(f"{nombre} debe ser un número finito") from None
    if not math.isfinite(numero):
        raise ValueError(f"{nombre} debe ser un número finito")
    if numero < 0 or (numero == 0 and not permite_cero):
        condicion = "no negativo" if permite_cero else "positivo"
        raise ValueError(f"{nombre} debe ser {condicion}")
    return numero


def _finito(valor: float) -> float:
    if not math.isfinite(valor):
        raise ValueError("El cálculo excede el rango numérico permitido")
    return valor


def _suma(valores: Iterable[float]) -> float:
    try:
        return _finito(math.fsum(valores))
    except OverflowError:
        raise ValueError("La suma excede el rango numérico permitido") from None


def valuacion(cantidad: float, precio: float, cotiza_cada: int) -> float:
    """Valúa unidades o nominales; un precio ausente debe tratarse antes."""
    cantidad = _numero(cantidad, "La cantidad", permite_cero=True)
    precio = _numero(precio, "El precio")
    unidad = _numero(cotiza_cada, "La unidad de cotización")
    if unidad not in (1, 100):
        raise ValueError("La unidad de cotización debe ser 1 o 100")
    return _finito(cantidad / unidad * precio)


def estado_costo(lotes: Iterable[Lote]) -> str:
    """Clasifica la procedencia del costo sin completar datos ausentes."""
    origenes = {lote.origen for lote in lotes}
    if origenes - {"extracto", "estimado", "pendiente"}:
        raise ValueError("El origen de un lote es desconocido")
    if not origenes or "pendiente" in origenes:
        return "incompleto"
    if origenes == {"extracto"}:
        return "extracto"
    if origenes == {"estimado"}:
        return "estimado"
    return "mixto"


def costo_total(lotes: Iterable[Lote]) -> Optional[float]:
    lotes = list(lotes)
    if estado_costo(lotes) == "incompleto":
        return None
    return _suma(_numero(lote.costo, "El costo del lote") for lote in lotes)


def resultado_posicion(
    posicion: Posicion,
    lotes: Iterable[Lote],
    precio: Optional[float],
    precio_dia_cero: Optional[float] = None,
) -> ResultadoPosicion:
    lotes = list(lotes)
    if any(lote.ticker != posicion.ticker for lote in lotes):
        raise ValueError("Los lotes deben corresponder a la posición")
    estado = estado_costo(lotes)
    costo = costo_total(lotes)
    valor = resultado = porcentaje = diferencia = porcentaje_cero = None
    if precio is not None:
        valor = valuacion(posicion.cantidad, precio, posicion.cotiza_cada)
        if costo is not None:
            resultado = _finito(valor - costo)
            porcentaje = _finito(resultado / costo)
        if precio_dia_cero is not None:
            base = valuacion(
                posicion.cantidad, precio_dia_cero, posicion.cotiza_cada
            )
            diferencia = _finito(valor - base)
            if base > 0:
                porcentaje_cero = _finito(diferencia / base)
    return ResultadoPosicion(
        ticker=posicion.ticker,
        tipo=posicion.tipo,
        valuacion=valor,
        costo=costo,
        estado_costo=estado,
        resultado=resultado,
        resultado_pct=porcentaje,
        resultado_dia_cero=diferencia,
        resultado_dia_cero_pct=porcentaje_cero,
    )


def resumen_cartera(resultados: Iterable[ResultadoPosicion]) -> ResumenCartera:
    resultados = list(resultados)
    con_precio = [r for r in resultados if r.valuacion is not None]
    comparables = [
        r for r in con_precio
        if r.costo is not None and r.estado_costo != "incompleto"
    ]
    costo = _suma(r.costo for r in comparables)
    valor = _suma(r.valuacion for r in comparables)
    return ResumenCartera(
        valuacion_total=_suma(r.valuacion for r in con_precio),
        costo_comparable=costo,
        valuacion_comparable=valor,
        resultado_comparable=_finito(valor - costo),
        posiciones_sin_costo=[
            r.ticker for r in resultados
            if r.costo is None or r.estado_costo == "incompleto"
        ],
        posiciones_sin_precio=[
            r.ticker for r in resultados if r.valuacion is None
        ],
    )
