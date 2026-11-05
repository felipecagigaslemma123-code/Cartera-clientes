"""Resultado histórico realizado: lotes y cobros, separado del día cero."""

import copy
import math
from collections import defaultdict, deque
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from numbers import Real
from typing import Dict, List, Optional

from ._historial_lectura import ErrorHistorial, _normalizar_ajuste, clasificar, consolidar
from .punto_partida import Lote


_CLASES_INGRESOS = ("dividendo", "retencion", "renta", "caucion_colocada", "caucion_tomada", "fci", "gastos", "compensacion")
_PATAS = {
    "caucion_colocada": {"COMPRA CAUCION CONTADO", "VENTA CAUCION TERMINO"},
    "caucion_tomada": {"VENTA CAUCION CONTADO", "COMPRA CAUCION TERMINO"},
}


def _bolsa():
    return {"ARS": 0.0, "USD": 0.0, "equivalente_ars": 0.0}


@dataclass
class RealizadoHistorico:
    ticker: str
    fecha: date
    cantidad: float
    cantidad_sin_lote: float
    importe_ars: Optional[float]
    costo_ars: Optional[float]
    resultado_ars: Optional[float]
    origen_costo: str
    clase: str


@dataclass
class Historial:
    realizados: List[RealizadoHistorico] = field(default_factory=list)
    ingresos: Dict[str, dict] = field(default_factory=lambda: {clase: _bolsa() for clase in _CLASES_INGRESOS})
    aportes: dict = field(default_factory=_bolsa)
    retiros: dict = field(default_factory=_bolsa)
    lotes: List[Lote] = field(default_factory=list)
    total_conocido: float = 0.0
    realizado_extracto: float = 0.0
    realizado_estimado: float = 0.0
    ventas_sin_dato: int = 0
    valores_sin_dato: int = 0
    sin_clasificar: List[dict] = field(default_factory=list)
    avisos: List[str] = field(default_factory=list)
    diferencias_tenencias: dict = field(default_factory=dict)
    diferencias_costos: dict = field(default_factory=dict)


def _numero(valor, nombre, positivo=False):
    if isinstance(valor, bool) or not isinstance(valor, (Real, Decimal)):
        raise ErrorHistorial(nombre + " debe ser un número finito.")
    try:
        numero = float(valor)
    except (ValueError, OverflowError):
        raise ErrorHistorial(nombre + " excede el rango numérico.") from None
    if not math.isfinite(numero) or positivo and numero <= 0:
        raise ErrorHistorial(nombre + " debe ser un número finito" + (" positivo." if positivo else "."))
    return numero


def _decimal(valor):
    return Decimal(str(valor))


def _suma(valores):
    return _numero(sum((_decimal(v) for v in valores), Decimal(0)), "El acumulado histórico")


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
    raise ErrorHistorial("La fecha operada debe tener formato AAAA-MM-DD.")


def _contexto(fila):
    return "{} fila {} (comprobante {}): ".format(
        fila.get("archivo", "historial"), fila.get("fila", "sin número"), fila.get("numero", "sin número"))


def _fila_normalizada(fila):
    if not isinstance(fila, dict):
        raise ErrorHistorial("Cada renglón de historial debe ser un diccionario.")
    nueva = copy.deepcopy(fila)
    contexto = _contexto(nueva)
    try:
        nueva["operado"] = _fecha(nueva.get("operado"))
        for campo in ("importe", "cantidad"):
            nueva[campo] = _numero(nueva.get(campo, 0), campo)
        if nueva.get("saldo") is not None:
            nueva["saldo"] = _numero(nueva["saldo"], "saldo")
        for campo in ("comprobante", "especie", "referencia"):
            valor = nueva.get(campo, "")
            if valor is None:
                valor = ""
            if not isinstance(valor, str):
                raise ErrorHistorial(campo + " debe ser texto.")
            nueva[campo] = valor.strip()
        if nueva.get("moneda") not in ("ARS", "USD"):
            raise ErrorHistorial("La moneda debe ser ARS o USD.")
        if nueva.get("cuenta") not in ("PESOS", "DOLARES", "CABLE"):
            raise ErrorHistorial("La cuenta debe ser PESOS, DOLARES o CABLE.")
    except ErrorHistorial as error:
        raise ErrorHistorial(contexto + str(error)) from None
    return nueva


def _orden_numero(valor):
    # Los números de comprobante suelen ser enteros; los alfanuméricos conservan
    # un orden determinista sin tratarlos como una clasificación financiera.
    if valor is None:
        return (2, "")
    if isinstance(valor, bool):
        return (1, str(valor))
    try:
        numero = Decimal(str(valor))
        if numero.is_finite():
            return (0, numero)
    except Exception:
        pass
    return (1, str(valor))


def _filas_ajustes(ajustes):
    filas = []
    for indice, ajuste in enumerate(ajustes, 1):
        normalizado = _normalizar_ajuste(ajuste)
        fila = copy.deepcopy(normalizado)
        tipo = normalizado["tipo"]
        signo = -1 if tipo in ("compra", "gasto") else 1
        fila.update(operado=normalizado["fecha"], comprobante="AJUSTE " + tipo.upper(),
                    numero=None, cantidad=normalizado["cantidad"], especie=normalizado["ticker"],
                    importe=signo * normalizado["importe"], saldo=None,
                    referencia=normalizado["nota"], cuenta="PESOS" if normalizado["moneda"] == "ARS" else "DOLARES",
                    archivo=normalizado.get("archivo", "ajustes_historial.csv"),
                    fila=normalizado.get("fila", indice + 1),
                    _clase="gastos" if tipo == "gasto" else tipo, _origen="estimado")
        filas.append(fila)
    return filas


def construir_historial(filas, ajustes=(), cierres=(), mep=None):
    """Calcula lotes abiertos y resultado observado sin tocar la base ni el día cero."""
    cierres = set(cierres)
    if any(not isinstance(ticker, str) or not ticker for ticker in cierres):
        raise ErrorHistorial("Los cierres deben identificar especies con texto no vacío.")
    mapa_mep = {}
    for fecha, cambio in (mep or {}).items():
        mapa_mep[_fecha(fecha)] = _numero(cambio, "MEP", positivo=True)
    fechas_mep = sorted(mapa_mep)
    origenes, avisos = consolidar([_fila_normalizada(fila) for fila in filas])
    historial = Historial(avisos=list(avisos))
    procesables = []
    cierres_agrupados, cauciones = {}, defaultdict(list)
    entradas = [(fila, False) for fila in origenes] + [(fila, True) for fila in _filas_ajustes(ajustes)]
    for indice, (original, es_ajuste) in enumerate(entradas):
        # Los metadatos que agregue un llamador a un renglón de extracto nunca
        # pueden reemplazar su clasificación ni la procedencia observada.
        clase = original["_clase"] if es_ajuste else clasificar(original, cierres)
        if clase == "sin_clasificar":
            historial.sin_clasificar.append(copy.deepcopy(original))
            continue
        fila = dict(original)
        fila["_clase"] = clase
        fila["_indice"] = indice
        fila["_origen"] = "estimado" if es_ajuste else "extracto"
        if clase == "conversion":
            continue
        if clase in ("compra", "venta", "cierre"):
            if not fila["especie"]:
                raise ErrorHistorial(_contexto(fila) + "Una compra, venta o cierre necesita especie.")
            if clase != "cierre" and fila["cantidad"] == 0:
                raise ErrorHistorial(_contexto(fila) + "Una compra o venta necesita cantidad distinta de cero.")
        if clase.startswith("caucion_"):
            cauciones[(fila["moneda"], clase, fila["operado"])].append(fila)
        elif clase == "cierre":
            clave = (fila["especie"], fila["operado"])
            cierres_agrupados.setdefault(clave, []).append(fila)
        else:
            procesables.append(fila)
    # Un cierre reúne todos los pagos de la especie en el día, incluso cuentas
    # o monedas distintas; su lugar en el orden es el primer comprobante.
    for grupo in cierres_agrupados.values():
        primera = min(grupo, key=lambda fila: (_orden_numero(fila.get("numero")), fila["_indice"]))
        evento = dict(primera)
        evento["_pagos"] = grupo
        procesables.append(evento)

    def valor_ars(fila, importe=None):
        valor = fila["importe"] if importe is None else importe
        if fila["moneda"] == "ARS" or valor == 0:
            return valor
        cambio = fila.get("tc")
        if cambio is None:
            anteriores = [fecha for fecha in fechas_mep if fecha <= fila["operado"]]
            fecha = anteriores[-1] if anteriores else None
            if fecha is not None and (fila["operado"] - fecha).days <= 5:
                cambio = mapa_mep[fecha]
        if cambio is None:
            historial.valores_sin_dato += 1
            historial.avisos.append(_contexto(fila) + "Sin MEP del día o anterior de hasta cinco días para {} USD.".format(valor))
            return None
        return _numero(valor * cambio, "El valor histórico en pesos")

    conocidos = []
    componentes = {clase: {"ARS": [], "USD": [], "equivalente_ars": [], "incompleto": False}
                   for clase in _CLASES_INGRESOS + ("aporte", "retiro")}

    def agregar_ingreso(clase, fila, importe=None):
        importe = fila["importe"] if importe is None else importe
        if clase in ("aporte", "retiro"):
            importe = abs(importe)
        equivalente = valor_ars(fila, importe)
        grupo = componentes[clase]
        grupo[fila["moneda"]].append(importe)
        if equivalente is None:
            grupo["incompleto"] = True
        else:
            grupo["equivalente_ars"].append(equivalente)
            if clase not in ("aporte", "retiro"):
                conocidos.append(equivalente)

    for (_, clase, _), grupo in cauciones.items():
        presentes = {fila["comprobante"] for fila in grupo}
        if not _PATAS[clase].issubset(presentes):
            numeros = ", ".join(str(fila.get("numero", "sin número")) for fila in grupo)
            historial.avisos.append("Caución {} en {} {} sin ambas patas; no se suma capital. Comprobantes: {}.".format(
                clase, grupo[0]["operado"].isoformat(), grupo[0]["moneda"], numeros))
            continue
        agregar_ingreso(clase, grupo[0], _suma(fila["importe"] for fila in grupo))

    creados, abiertos = [], defaultdict(deque)
    importes_extracto, importes_estimados = [], []

    def consumir(ticker, cantidad):
        restante, costo = _decimal(cantidad), Decimal(0)
        origenes_consumidos, costo_incompleto = set(), False
        while restante > 0 and abiertos[ticker]:
            lote = abiertos[ticker][0]
            disponible = _decimal(lote.cantidad)
            tomado = min(restante, disponible)
            origenes_consumidos.add(lote.origen)
            if lote.costo is None:
                costo_incompleto = True
            else:
                costo_tomado = _decimal(lote.costo) * tomado / disponible
                costo += costo_tomado
                lote.costo = _numero(_decimal(lote.costo) - costo_tomado, "El costo restante")
            lote.cantidad = _numero(disponible - tomado, "La cantidad restante")
            restante -= tomado
            if lote.cantidad == 0:
                abiertos[ticker].popleft()
        falta = _numero(restante, "La cantidad sin lote")
        incompleto = costo_incompleto or falta > 0 or not origenes_consumidos
        origen = ("incompleto" if incompleto else next(iter(origenes_consumidos))
                  if len(origenes_consumidos) == 1 else "mixto")
        return (None if incompleto else _numero(costo, "El costo realizado")), falta, origen

    for fila in sorted(procesables, key=lambda actual: (actual["operado"], 0 if actual["_clase"] == "compra" else 1,
                                                        _orden_numero(actual.get("numero")), actual["_indice"])):
        clase = fila["_clase"]
        if clase == "compra":
            costo = valor_ars(fila, abs(fila["importe"]))
            lote = Lote(fila["especie"], abs(fila["cantidad"]), fila.get("_origen", "extracto"),
                        fila["operado"], None, costo, fila.get("referencia", ""))
            creados.append(lote)
            abiertos[lote.ticker].append(lote)
        elif clase in ("venta", "cierre"):
            ticker = fila["especie"]
            if clase == "cierre":
                cantidad = _suma(lote.cantidad for lote in abiertos[ticker])
                importes = [valor_ars(pago) for pago in fila["_pagos"]]
                importe = None if any(valor is None for valor in importes) else _suma(importes)
            else:
                cantidad = abs(fila["cantidad"])
                importe = valor_ars(fila)
            costo, falta, origen = consumir(ticker, cantidad)
            # Una venta por ajuste no sale de un extracto: su importe no es un dato observado.
            if fila.get("_origen") == "estimado" and origen == "extracto":
                origen = "mixto"
            resultado = None if costo is None or importe is None else _suma((importe, -costo))
            historial.realizados.append(RealizadoHistorico(ticker, fila["operado"], cantidad, falta,
                                                         importe, costo, resultado, origen, clase))
            if resultado is None:
                historial.ventas_sin_dato += 1
                if falta > 0:
                    historial.avisos.append(_contexto(fila) + "Venta de {} sin lotes para {} unidades; resultado sin dato.".format(ticker, falta))
                elif clase == "cierre" and cantidad == 0:
                    historial.avisos.append(_contexto(fila) + "Cierre de {} sin lotes abiertos; resultado sin dato.".format(ticker))
            else:
                conocidos.append(resultado)
                (importes_extracto if origen == "extracto" else importes_estimados).append(resultado)
        elif clase in componentes:
            agregar_ingreso(clase, fila)
        else:
            # Solo se llega aquí si se agregó una clase sin tratamiento explícito.
            # Tampoco ese caso puede convertirse en ganancia o desaparecer.
            desconocida = {clave: copy.deepcopy(valor) for clave, valor in fila.items() if not clave.startswith("_")}
            historial.sin_clasificar.append(desconocida)

    for clase, grupo in componentes.items():
        bolsa = {moneda: _suma(grupo[moneda]) for moneda in ("ARS", "USD")}
        bolsa["equivalente_ars"] = None if grupo["incompleto"] else _suma(grupo["equivalente_ars"])
        if clase == "aporte":
            historial.aportes = bolsa
        elif clase == "retiro":
            historial.retiros = bolsa
        else:
            historial.ingresos[clase] = bolsa
    historial.lotes = [lote for lote in creados if lote.cantidad > 0]
    historial.total_conocido = _suma(conocidos)
    historial.realizado_extracto = _suma(importes_extracto)
    historial.realizado_estimado = _suma(importes_estimados)
    return historial


def conciliar_tenencias(lotes, posiciones):
    """Informa diferencias nominales mayores a 0,5 sin modificar las entradas."""
    derivadas, base = defaultdict(Decimal), defaultdict(Decimal)
    for lote in lotes:
        derivadas[lote.ticker] += _decimal(_numero(lote.cantidad, "La cantidad del lote"))
    for posicion in posiciones:
        base[posicion.ticker] += _decimal(_numero(posicion.cantidad, "La cantidad base"))
    diferencias = {}
    for ticker in sorted(set(derivadas) | set(base)):
        diferencia = derivadas[ticker] - base[ticker]
        if abs(diferencia) > Decimal("0.5"):
            diferencias[ticker] = {"derivada": _numero(derivadas[ticker], "La cantidad derivada"),
                                   "base": _numero(base[ticker], "La cantidad base"),
                                   "diferencia": _numero(diferencia, "La diferencia de cantidad")}
    return diferencias
