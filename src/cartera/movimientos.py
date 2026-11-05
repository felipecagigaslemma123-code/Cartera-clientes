"""Historial manual de movimientos y reconstrucción de tenencias por FIFO.

La base importada es inmutable. Las fechas se controlan al validar un historial;
las funciones de cálculo no dependen de la fecha del reloj.
"""

import csv
import fcntl
import io
import math
import os
import re
import tempfile
from dataclasses import dataclass, replace
from datetime import date, datetime
from decimal import Decimal
from numbers import Number
from pathlib import Path
from typing import List, Optional

from .punto_partida import Lote, Posicion, PuntoPartida


_COLUMNAS = ("fecha", "tipo", "ticker", "cantidad", "importe", "moneda", "tc", "tipo_activo", "nota")
_TIPOS = {"compra", "venta", "renta", "dividendo", "deposito", "retiro", "gasto", "compra_usd", "venta_usd"}
_UNIDADES = {"cedear": 1, "accion": 1, "bono": 100, "on": 100, "letra": 100}


class ErrorMovimiento(ValueError):
    """Conserva todos los problemas del movimiento o del historial recibido."""

    def __init__(self, errores):
        self.errores = [errores] if isinstance(errores, str) else list(errores)
        super().__init__("\n".join(self.errores))


@dataclass
class Realizado:
    ticker: str
    fecha: date
    cantidad: float
    importe: float
    costo: Optional[float]
    resultado: Optional[float]
    origen_costo: str


def _vacio(valor):
    return valor is None or isinstance(valor, str) and not valor.strip()


def _fecha(valor, campo, errores):
    if isinstance(valor, datetime):
        return valor.date()
    if isinstance(valor, date):
        return valor
    if isinstance(valor, str) and re.fullmatch(r"\d{4}-\d{2}-\d{2}", valor.strip()):
        try:
            return date.fromisoformat(valor.strip())
        except ValueError:
            pass
    errores.append("{} inválida; usá AAAA-MM-DD.".format(campo))
    return None


def _texto(valor, campo, errores, conservar=False):
    if valor is None:
        return ""
    if not isinstance(valor, str):
        errores.append("{} debe ser texto.".format(campo))
        return ""
    return valor if conservar else valor.strip()


def _numero(valor, campo, errores, vacio=None, positivo=False):
    if _vacio(valor):
        if vacio is not None:
            return vacio
        errores.append("{} es obligatorio y debe ser un número positivo y finito.".format(campo))
        return None
    if isinstance(valor, bool) or not isinstance(valor, (str, Number)):
        errores.append("{} debe ser un número finito.".format(campo))
        return None
    try:
        numero = float(valor)
    except (ValueError, TypeError, OverflowError):
        errores.append("{} debe ser un número finito, con punto decimal y sin separadores de miles.".format(campo))
        return None
    if not math.isfinite(numero) or numero < 0 or positivo and numero <= 0:
        errores.append("{} debe ser un número {}y finito.".format(campo, "positivo " if positivo else "no negativo "))
        return None
    return numero


def _normalizar(movimiento):
    """Normaliza el formato sin consultar el reloj ni decidir sobre las tenencias.

    La aplicabilidad de ticker y cantidad se controla en validar_movimientos;
    aplicar_movimientos ignora esos campos para tipos que no modifican lotes.
    """
    if not isinstance(movimiento, dict):
        raise ErrorMovimiento("El movimiento debe ser un diccionario.")
    errores = []
    fecha = _fecha(movimiento.get("fecha"), "Fecha", errores)
    tipo = _texto(movimiento.get("tipo"), "tipo", errores)
    if tipo not in _TIPOS:
        errores.append("Tipo de movimiento desconocido: {!r}.".format(tipo))
    ticker = _texto(movimiento.get("ticker"), "ticker", errores)
    cantidad = _numero(movimiento.get("cantidad"), "cantidad", errores, vacio=0.0)
    importe = _numero(movimiento.get("importe"), "importe", errores, positivo=True)
    moneda = _texto(movimiento.get("moneda"), "moneda", errores).upper() or "ARS"
    if moneda not in ("ARS", "USD"):
        errores.append("Moneda desconocida: {!r}; usá ARS o USD.".format(moneda))
    tc_bruto = movimiento.get("tc")
    tc = None
    if moneda == "USD":
        tc = _numero(tc_bruto, "tc en USD", errores, positivo=True)
    elif not _vacio(tc_bruto):
        errores.append("En ARS no se admite tc.")
    if tipo in ("compra_usd", "venta_usd") and moneda != "USD":
        errores.append("{} debe cargarse en USD con su tc.".format(tipo))
    tipo_activo = _texto(movimiento.get("tipo_activo"), "tipo_activo", errores)
    if tipo_activo and tipo_activo not in _UNIDADES:
        errores.append("Tipo de activo desconocido: {!r}.".format(tipo_activo))
    nota = _texto(movimiento.get("nota"), "nota", errores, conservar=True)
    if importe is not None and tc is not None and not math.isfinite(importe * tc):
        errores.append("El valor en pesos debe ser finito; revisá importe y tc.")
    if errores:
        raise ErrorMovimiento(errores)
    return dict(fecha=fecha, tipo=tipo, ticker=ticker, cantidad=cantidad, importe=importe,
                moneda=moneda, tc=tc, tipo_activo=tipo_activo, nota=nota)


def _decimal(numero):
    return Decimal(str(numero))


def _en_rango(valor):
    try:
        return math.isfinite(float(valor))
    except (OverflowError, ValueError):
        return False


def _importe_ars(movimiento):
    return movimiento["importe"] * movimiento["tc"] if movimiento["moneda"] == "USD" else movimiento["importe"]


def _normalizados(movimientos):
    normalizados = []
    errores = []
    for indice, movimiento in enumerate(movimientos, 1):
        try:
            normalizados.append((indice, _normalizar(movimiento)))
        except ErrorMovimiento as error:
            errores.extend("Movimiento {} (fila {}): {}".format(indice, indice + 1, problema)
                           for problema in error.errores)
    return normalizados, errores


def aplicar_movimientos(lotes, movimientos):
    """Devuelve copias de los lotes restantes y las ventas, en orden estable."""
    pendientes = [replace(lote) for lote in lotes]
    ordenados, errores = _normalizados(movimientos)
    if errores:
        raise ErrorMovimiento(errores)
    realizados = []
    for indice, movimiento in sorted(ordenados, key=lambda entrada: entrada[1]["fecha"]):
        tipo = movimiento["tipo"]
        if tipo not in ("compra", "venta"):
            continue
        ticker, cantidad = movimiento["ticker"], movimiento["cantidad"]
        if not ticker or cantidad <= 0:
            raise ErrorMovimiento("Movimiento {}: {} requiere ticker y cantidad positiva.".format(indice, tipo))
        importe = _importe_ars(movimiento)
        if tipo == "compra":
            cantidad_total = sum((_decimal(lote.cantidad) for lote in pendientes if lote.ticker == ticker), Decimal(0)) + _decimal(cantidad)
            costo_total = sum((_decimal(lote.costo) for lote in pendientes
                               if lote.ticker == ticker and lote.costo is not None), Decimal(0)) + _decimal(importe)
            if not _en_rango(cantidad_total) or not _en_rango(costo_total):
                raise ErrorMovimiento("Movimiento {} ({}): la cantidad o el costo acumulado excede el rango finito admitido.".format(indice, ticker))
            pendientes.append(Lote(ticker, cantidad, "extracto", movimiento["fecha"], None, importe, movimiento["nota"]))
            continue
        disponibles = sum((_decimal(lote.cantidad) for lote in pendientes if lote.ticker == ticker), Decimal(0))
        if _decimal(cantidad) > disponibles:
            raise ErrorMovimiento("Movimiento {} ({}): venta de {} supera los {} disponibles en lotes.".format(
                indice, ticker, cantidad, disponibles))
        por_consumir = _decimal(cantidad)
        costo = Decimal(0)
        incompleto = False
        origenes = set()
        # sorted conserva el orden original ante fechas iguales, incluyendo compras.
        for lote in sorted(pendientes, key=lambda actual: actual.fecha or date.min):
            if lote.ticker != ticker or por_consumir <= 0:
                continue
            cantidad_lote = _decimal(lote.cantidad)
            consumido = min(por_consumir, cantidad_lote)
            proporcion = consumido / cantidad_lote
            if lote.costo is None or lote.origen == "pendiente":
                incompleto = True
            else:
                costo_consumido = _decimal(lote.costo) * proporcion
                costo += costo_consumido
                lote.costo = float(_decimal(lote.costo) - costo_consumido)
                origenes.add(lote.origen)
            lote.cantidad = float(cantidad_lote - consumido)
            por_consumir -= consumido
        pendientes = [lote for lote in pendientes if lote.cantidad > 0]
        if not incompleto and not _en_rango(costo):
            raise ErrorMovimiento("Movimiento {} ({}): el costo realizado excede el rango finito admitido.".format(indice, ticker))
        costo = float(costo) if not incompleto else None
        origen = "incompleto" if incompleto else next(iter(origenes)) if len(origenes) == 1 else "mixto"
        realizados.append(Realizado(ticker, movimiento["fecha"], cantidad, importe,
                                    None if incompleto else costo,
                                    None if incompleto else importe - costo, origen))
    return pendientes, realizados


def validar_movimientos(punto, movimientos, fecha_dia_cero, hoy):
    """Valida cada fila y simula el historial entero, sin modificar la base."""
    normalizados, errores = _normalizados(movimientos)
    limites = []
    cero = None if fecha_dia_cero is None else _fecha(fecha_dia_cero, "Fecha del día cero", limites)
    fecha_hoy = _fecha(hoy, "Fecha de hoy", limites)
    if limites:
        raise ErrorMovimiento(limites + errores)
    tipos = {posicion.ticker: posicion.tipo for posicion in punto.posiciones}
    cantidades_nominales = {posicion.ticker: _decimal(posicion.cantidad) for posicion in punto.posiciones}
    cantidades = {}
    for lote in punto.lotes:
        cantidades[lote.ticker] = cantidades.get(lote.ticker, Decimal(0)) + _decimal(lote.cantidad)
    for indice, movimiento in sorted(normalizados, key=lambda entrada: entrada[1]["fecha"]):
        problemas = []
        tipo, ticker, cantidad = movimiento["tipo"], movimiento["ticker"], movimiento["cantidad"]
        fecha = movimiento["fecha"]
        if cero is not None and fecha <= cero:
            errores.append("Movimiento {} (fila {}): fecha {} debe ser posterior al día cero {}.".format(
                indice, indice + 1, fecha.isoformat(), cero.isoformat()))
        if fecha > fecha_hoy:
            errores.append("Movimiento {} (fila {}): fecha futura {}; hoy en Argentina es {}.".format(
                indice, indice + 1, fecha.isoformat(), fecha_hoy.isoformat()))
        if tipo in ("compra", "venta"):
            if not ticker:
                problemas.append("{} requiere ticker.".format(tipo))
            if cantidad <= 0:
                problemas.append("{} requiere cantidad positiva.".format(tipo))
        elif cantidad != 0:
            problemas.append("{} no admite cantidad; dejala vacía o en 0.".format(tipo))
        if tipo in ("deposito", "retiro", "compra_usd", "venta_usd") and ticker:
            problemas.append("{} no admite ticker.".format(tipo))
        elif tipo in ("renta", "dividendo") and not ticker:
            problemas.append("{} requiere ticker de una especie conocida.".format(tipo))
        if tipo in ("venta", "renta", "dividendo", "gasto") and ticker and ticker not in tipos:
            problemas.append("La especie {} no es conocida en esa fecha.".format(ticker))
        activo = movimiento["tipo_activo"]
        if tipo == "compra" and ticker:
            if ticker not in tipos and not activo:
                problemas.append("La primera compra de {} requiere tipo_activo.".format(ticker))
            elif ticker in tipos and activo and activo != tipos[ticker]:
                problemas.append("tipo_activo de {} no coincide con {}.".format(ticker, tipos[ticker]))
        elif activo:
            problemas.append("tipo_activo solo corresponde a una compra.")
        if tipo == "venta" and ticker in tipos and cantidad > 0:
            disponible = cantidades.get(ticker, Decimal(0))
            if _decimal(cantidad) > disponible:
                problemas.append("Venta de {} supera los {} disponibles en lotes de {}.".format(cantidad, disponible, ticker))
            nominal = cantidades_nominales.get(ticker, Decimal(0))
            if _decimal(cantidad) > nominal:
                problemas.append("Venta de {} supera la tenencia nominal de {} en {}.".format(cantidad, nominal, ticker))
        if tipo == "compra" and cantidad > 0:
            nominal_nuevo = cantidades_nominales.get(ticker, Decimal(0)) + _decimal(cantidad)
            lotes_nuevos = cantidades.get(ticker, Decimal(0)) + _decimal(cantidad)
            if not _en_rango(nominal_nuevo) or not _en_rango(lotes_nuevos):
                problemas.append("La cantidad acumulada de {} excede el rango finito admitido.".format(ticker))
        if problemas:
            errores.extend("Movimiento {} (fila {}, {}): {}".format(indice, indice + 1, ticker or "sin ticker", problema)
                           for problema in problemas)
            continue
        if tipo == "compra":
            tipos.setdefault(ticker, activo)
            cantidades[ticker] = cantidades.get(ticker, Decimal(0)) + _decimal(cantidad)
            cantidades_nominales[ticker] = cantidades_nominales.get(ticker, Decimal(0)) + _decimal(cantidad)
        elif tipo == "venta":
            cantidades[ticker] -= _decimal(cantidad)
            cantidades_nominales[ticker] -= _decimal(cantidad)
    if not errores:
        # La simulación de costos detecta también desbordes antes de persistir.
        try:
            aplicar_movimientos(punto.lotes, [movimiento for _, movimiento in normalizados])
        except ErrorMovimiento as error:
            errores.extend(error.errores)
    if errores:
        raise ErrorMovimiento(errores)


def leer_movimientos(ruta):
    """Lee un CSV completo, con encabezado exacto; ausencia significa historial vacío."""
    ruta = Path(ruta)
    try:
        archivo = ruta.open("r", encoding="utf-8-sig", newline="")
    except FileNotFoundError:
        return []
    errores, movimientos = [], []
    lector = None
    try:
        with archivo:
            lector = csv.reader(archivo, strict=True)
            if next(lector, None) != list(_COLUMNAS):
                raise ErrorMovimiento("Fila 1: encabezado de movimientos.csv inválido; se espera {}.".format(",".join(_COLUMNAS)))
            for fila in lector:
                numero = lector.line_num
                # Editar a mano suele dejar líneas en blanco; no son movimientos.
                if not any(campo.strip() for campo in fila):
                    continue
                if len(fila) != len(_COLUMNAS):
                    errores.append("Fila {}: se esperan exactamente {} columnas.".format(numero, len(_COLUMNAS)))
                    continue
                try:
                    movimientos.append(_normalizar(dict(zip(_COLUMNAS, fila))))
                except ErrorMovimiento as error:
                    errores.extend("Fila {}: {}".format(numero, problema) for problema in error.errores)
    except (csv.Error, UnicodeError) as error:
        errores.append("Fila {}: CSV inválido ({}).".format(lector.line_num if lector is not None else 1, error))
    if errores:
        raise ErrorMovimiento(errores)
    return movimientos


def _fila_csv(movimiento):
    return [movimiento["fecha"].isoformat(), movimiento["tipo"], movimiento["ticker"],
            movimiento["cantidad"], movimiento["importe"], movimiento["moneda"],
            "" if movimiento["tc"] is None else movimiento["tc"], movimiento["tipo_activo"], movimiento["nota"]]


def agregar_movimiento(ruta, punto, movimiento, fecha_dia_cero, hoy):
    """Agrega una fila solo tras validar el historial, publicando un archivo completo."""
    ruta = Path(ruta)
    # Un intento inválido no crea ni siquiera la carpeta o un archivo de bloqueo.
    normalizado = _normalizar(movimiento)
    if not ruta.parent.exists():
        validar_movimientos(punto, [normalizado], fecha_dia_cero, hoy)
        ruta.parent.mkdir(parents=True, exist_ok=True)
    descriptor = os.open(str(ruta.parent), os.O_RDONLY)
    temporal = None
    try:
        # El directorio mantiene el bloqueo estable aunque se reemplace el CSV.
        fcntl.flock(descriptor, fcntl.LOCK_EX)
        if ruta.is_symlink():
            raise ErrorMovimiento("movimientos.csv no puede ser un enlace.")
        existia = ruta.exists()
        anteriores = ruta.read_bytes() if existia else b""
        historial = leer_movimientos(ruta)
        validar_movimientos(punto, historial + [normalizado], fecha_dia_cero, hoy)
        salida = io.StringIO(newline="")
        escritor = csv.writer(salida, lineterminator="\n")
        if not existia:
            escritor.writerow(_COLUMNAS)
        elif anteriores and not anteriores.endswith((b"\n", b"\r")):
            salida.write("\n")
        escritor.writerow(_fila_csv(normalizado))
        contenido = anteriores + salida.getvalue().encode("utf-8")
        with tempfile.NamedTemporaryFile(mode="wb", dir=str(ruta.parent), prefix=".movimientos-", suffix=".tmp", delete=False) as archivo:
            temporal = Path(archivo.name)
            os.fchmod(archivo.fileno(), 0o600)
            archivo.write(contenido)
            archivo.flush()
            os.fsync(archivo.fileno())
        if existia:
            if ruta.is_symlink() or ruta.read_bytes() != anteriores:
                raise ErrorMovimiento("movimientos.csv cambió durante la carga; volvé a intentar.")
            os.replace(str(temporal), str(ruta))
        else:
            # También evita pisar un archivo creado por un editor que no use el bloqueo.
            os.link(str(temporal), str(ruta))
        return normalizado
    finally:
        if temporal is not None:
            temporal.unlink(missing_ok=True)
        os.close(descriptor)


def cartera_actual(punto, movimientos):
    """Reconstruye cantidades desde las posiciones base y costos desde sus lotes."""
    normalizados, errores = _normalizados(movimientos)
    if errores:
        raise ErrorMovimiento(errores)
    historial = [movimiento for _, movimiento in normalizados]
    validar_movimientos(punto, historial, None, date.max)
    lotes, realizados = aplicar_movimientos(punto.lotes, historial)
    metadatos = {posicion.ticker: replace(posicion) for posicion in punto.posiciones}
    cantidades = {posicion.ticker: _decimal(posicion.cantidad) for posicion in punto.posiciones}
    for _, movimiento in sorted(normalizados, key=lambda entrada: entrada[1]["fecha"]):
        tipo, ticker = movimiento["tipo"], movimiento["ticker"]
        if tipo == "compra":
            if ticker not in metadatos:
                activo = movimiento["tipo_activo"]
                metadatos[ticker] = Posicion(ticker, ticker, activo, 0.0, _UNIDADES[activo])
            cantidades[ticker] = cantidades.get(ticker, Decimal(0)) + _decimal(movimiento["cantidad"])
        elif tipo == "venta":
            cantidades[ticker] -= _decimal(movimiento["cantidad"])
    posiciones = [replace(posicion, cantidad=float(cantidades[ticker]))
                  for ticker, posicion in metadatos.items() if cantidades[ticker] != 0]
    return PuntoPartida(posiciones, lotes), realizados


# Las funciones monetarias importan _normalizar dentro de su cuerpo para evitar
# un ciclo al reexportar toda la API pública de la etapa desde este módulo.
from .movimientos_resultados import (  # noqa: E402
    Conciliacion, Flujos, ResultadoIntegral, conciliar_efectivo, flujos,
    resultado_integral, saldos_efectivo,
)
