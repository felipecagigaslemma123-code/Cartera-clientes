"""Efectivo por moneda y resultado monetario de la cartera con movimientos.

Los costos de lotes no intervienen: los cobros y las ventas ya están incluidos
una sola vez en el efectivo reconstruido desde la referencia inicial.
"""

from dataclasses import dataclass, field
from datetime import date, datetime
import math
from typing import Dict, List, Optional

from .calculos import valuacion
from .dia_cero import ErrorDiaCero, patrimonio_inicial


@dataclass
class Flujos:
    aportes: float = 0.0
    retiros: float = 0.0
    rentas: float = 0.0
    dividendos: float = 0.0
    gastos: float = 0.0


@dataclass
class Conciliacion:
    estado: str
    fecha: Optional[str]
    diferencias: Dict[str, float]


@dataclass
class ResultadoIntegral:
    patrimonio_inicial: Optional[float]
    valuacion_final: Optional[float]
    efectivo_ars: Optional[float]
    efectivo_usd: Optional[float]
    patrimonio_final: Optional[float]
    flujos: Flujos
    total: Optional[float]
    faltantes: List[str]
    faltantes_fijos: List[str] = field(default_factory=list)


def _error(texto):
    # Importación diferida: movimientos expone esta API pública al final del módulo.
    from .movimientos import ErrorMovimiento
    return ErrorMovimiento(texto)


def _numero(valor, nombre, positivo=False):
    if isinstance(valor, bool) or not isinstance(valor, (int, float)):
        raise _error(nombre + " debe ser un número finito.")
    try:
        numero = float(valor)
    except (OverflowError, ValueError):
        raise _error(nombre + " está fuera del rango numérico.") from None
    if not math.isfinite(numero) or (positivo and numero <= 0):
        raise _error(nombre + " debe ser un número finito" + (" positivo." if positivo else "."))
    return numero


def _suma(valores):
    try:
        numero = math.fsum(valores)
    except OverflowError:
        raise _error("El cálculo de movimientos excede el rango numérico.") from None
    return _numero(numero, "El cálculo de movimientos")


def _fecha(valor):
    if isinstance(valor, datetime):
        return valor.date()
    if isinstance(valor, date):
        return valor
    if isinstance(valor, str):
        try:
            return date.fromisoformat(valor)
        except ValueError:
            pass
    raise _error("La fecha debe tener formato AAAA-MM-DD.")


def _normalizados(movimientos):
    from .movimientos import _normalizar
    return [_normalizar(movimiento) for movimiento in movimientos]


def _pesos(movimiento):
    importe = movimiento["importe"]
    if movimiento["moneda"] == "USD":
        importe *= movimiento["tc"]
    return _numero(importe, "El importe en pesos", positivo=True)


def saldos_efectivo(efectivo, movimientos, hasta=None):
    """Reconstruye saldos; una moneda inicialmente desconocida sigue desconocida."""
    if efectivo is None:
        efectivo = {}
    if not isinstance(efectivo, dict):
        raise _error("El efectivo debe contener saldos ARS y USD.")
    iniciales = {moneda: None if efectivo.get(moneda) is None else
                 _numero(efectivo[moneda], "El efectivo " + moneda)
                 for moneda in ("ARS", "USD")}
    componentes = {moneda: [] if saldo is None else [saldo]
                   for moneda, saldo in iniciales.items()}
    limite = None if hasta is None else _fecha(hasta)
    for movimiento in _normalizados(movimientos):
        if limite is not None and movimiento["fecha"] > limite:
            continue
        tipo, moneda, importe = movimiento["tipo"], movimiento["moneda"], movimiento["importe"]
        if tipo in ("compra_usd", "venta_usd"):
            pesos = _pesos(movimiento)
            signo = 1 if tipo == "compra_usd" else -1
            componentes["USD"].append(signo * importe)
            componentes["ARS"].append(-signo * pesos)
        else:
            signo = -1 if tipo in ("compra", "retiro", "gasto") else 1
            componentes[moneda].append(signo * importe)
    return {moneda: None if iniciales[moneda] is None else _suma(componentes[moneda])
            for moneda in ("ARS", "USD")}


def flujos(movimientos):
    """Desglosa flujos en pesos al cambio propio de cada movimiento."""
    campos = {"deposito": "aportes", "retiro": "retiros", "renta": "rentas",
              "dividendo": "dividendos", "gasto": "gastos"}
    componentes = {campo: [] for campo in campos.values()}
    for movimiento in _normalizados(movimientos):
        campo = campos.get(movimiento["tipo"])
        if campo is not None:
            componentes[campo].append(_pesos(movimiento))
    return Flujos(**{campo: _suma(valores) for campo, valores in componentes.items()})


def conciliar_efectivo(dia_cero, movimientos, efectivo):
    """Contrasta solo monedas comparables, a la fecha del saldo informado."""
    efectivo = efectivo or {}
    fecha = efectivo.get("fecha")
    try:
        fecha = None if fecha is None else _fecha(fecha)
    except ValueError:
        fecha = None
    sin_control = Conciliacion("sin_control", None if fecha is None else fecha.isoformat(), {})
    if not dia_cero or fecha is None:
        return sin_control
    try:
        fecha_inicial = _fecha(dia_cero.get("fecha"))
    except ValueError:
        return sin_control
    if fecha < fecha_inicial:
        return sin_control
    calculado = saldos_efectivo(dia_cero.get("efectivo"), movimientos, hasta=fecha)
    diferencias = {}
    supera = False
    for moneda, tolerancia in (("ARS", 1.0), ("USD", 0.01)):
        informado = efectivo.get(moneda)
        if informado is None or calculado[moneda] is None:
            continue
        diferencia = _suma((_numero(informado, "El efectivo informado " + moneda), -calculado[moneda]))
        diferencias[moneda] = diferencia
        # La tolerancia es inclusiva; no confundir el redondeo binario con un desvío.
        if abs(diferencia) > tolerancia and not math.isclose(abs(diferencia), tolerancia,
                                                            rel_tol=0.0, abs_tol=1e-9):
            supera = True
    if not diferencias:
        return sin_control
    return Conciliacion("no_concilia" if supera else "concilia", fecha.isoformat(), diferencias)


def resultado_integral(posiciones_base, dia_cero, posiciones_actuales, movimientos, precios, mep):
    """Patrimonio final menos inicial y aportes, más retiros, sin porcentaje.

    La referencia inicial recibe siempre la base importada: una especie vendida
    por completo aún conserva su unidad y su valor en el patrimonio inicial.
    """
    movimientos = list(movimientos)
    desgloses = flujos(movimientos)
    fijos = []
    inicial = None
    if dia_cero is None:
        fijos.append("día cero")
        saldos = {"ARS": None, "USD": None}
    else:
        try:
            referencia = patrimonio_inicial(posiciones_base, dia_cero)
        except ErrorDiaCero as error:
            fijos.append("patrimonio inicial: " + str(error))
        else:
            inicial = referencia.total
            fijos.extend("patrimonio inicial: " + nombre for nombre in referencia.faltantes)
        saldos = saldos_efectivo(dia_cero.get("efectivo"), movimientos)
        for moneda in ("ARS", "USD"):
            if saldos[moneda] is None:
                fijos.append("efectivo " + moneda + " calculado")
    faltantes = list(fijos)
    valores = []
    sin_precio = False
    for posicion in posiciones_actuales:
        precio = precios.get(posicion.ticker)
        if precio is None:
            faltantes.append("precio actual de " + posicion.ticker)
            sin_precio = True
        else:
            valores.append(valuacion(posicion.cantidad, precio, posicion.cotiza_cada))
    valor_final = None if sin_precio else _suma(valores)
    conversion = None
    if saldos["USD"] == 0:
        conversion = 0.0
    elif saldos["USD"] is not None:
        if mep is None:
            faltantes.append("dólar MEP actual")
        else:
            conversion = _numero(saldos["USD"] * _numero(mep, "El dólar MEP actual", positivo=True),
                                 "El efectivo USD convertido")
    final = None
    if valor_final is not None and saldos["ARS"] is not None and conversion is not None:
        final = _suma((valor_final, saldos["ARS"], conversion))
    total = None
    if not faltantes and inicial is not None and final is not None:
        total = _suma((final, -inicial, -desgloses.aportes, desgloses.retiros))
    return ResultadoIntegral(inicial, valor_final, saldos["ARS"], saldos["USD"], final,
                             desgloses, total, faltantes, fijos)
