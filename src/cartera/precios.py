"""Cotizaciones por panel, caché local y captura de consultas observadas."""

import csv
import fcntl
import io
import json
import math
import os
import tempfile
from dataclasses import asdict, dataclass
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Optional
from zoneinfo import ZoneInfo


ENDPOINTS = {"cedear": "arg_cedears", "accion": "arg_stocks", "bono": "arg_bonds",
             "letra": "arg_notes", "on": "arg_corp"}
_BASE = "https://data912.com/live/"
_COLUMNAS = ["consultado_en", "ticker", "ultimo", "bid", "ask"]


@dataclass
class Cotizacion:
    ticker: str
    ultimo: Optional[float]
    bid: Optional[float]
    ask: Optional[float]
    pct_dia: Optional[float]
    estado: str
    consultado_en: datetime


def _numero(valor, positivo=False):
    if isinstance(valor, bool) or not isinstance(valor, (int, float)):
        return None
    try:
        numero = float(valor)
    except (OverflowError, ValueError):
        return None
    if not math.isfinite(numero) or (positivo and numero <= 0):
        return None
    return numero


def _instante(valor):
    if not isinstance(valor, datetime) or valor.utcoffset() is None:
        raise ValueError("La hora de consulta debe incluir zona horaria.")
    return valor


def _constante_invalida(texto):
    raise ValueError("Número no finito en caché: " + texto)


def _leer_cache(ruta):
    try:
        contenido = json.loads(ruta.read_text(encoding="utf-8"), parse_constant=_constante_invalida)
    except (OSError, ValueError, UnicodeError):
        return {}
    if not isinstance(contenido, dict):
        return {}
    cache = {}
    for ticker, registro in contenido.items():
        try:
            if not isinstance(ticker, str) or not ticker or not isinstance(registro, dict):
                continue
            if registro.get("ticker", ticker) != ticker:
                continue
            ultimo = _numero(registro.get("ultimo"), positivo=True)
            if ultimo is None:
                continue
            consultado = _instante(datetime.fromisoformat(registro["consultado_en"]))
            cache[ticker] = Cotizacion(
                ticker=ticker, ultimo=ultimo,
                bid=_numero(registro.get("bid"), positivo=True),
                ask=_numero(registro.get("ask"), positivo=True),
                pct_dia=_numero(registro.get("pct_dia")),
                estado="cache", consultado_en=consultado,
            )
        except (KeyError, TypeError, ValueError, OverflowError):
            continue
    return cache


def _guardar_cache(ruta, vivos):
    ruta.parent.mkdir(parents=True, exist_ok=True)
    descriptor = os.open(str(ruta.parent), os.O_RDONLY)
    try:
        # Bloquear la carpeta mantiene la exclusión aunque se reemplace el JSON.
        fcntl.flock(descriptor, fcntl.LOCK_EX)
        _publicar_cache(ruta, vivos)
    finally:
        os.close(descriptor)


def _publicar_cache(ruta, vivos):
    # Volver a leer evita perder paneles guardados por otra instancia anterior.
    cache = _leer_cache(ruta)
    cache.update(vivos)
    contenido = {}
    for ticker, cotizacion in cache.items():
        registro = asdict(cotizacion)
        registro["consultado_en"] = cotizacion.consultado_en.isoformat()
        registro["estado"] = "vivo"  # Describe la consulta que originó el dato guardado.
        contenido[ticker] = registro
    serializado = json.dumps(contenido, ensure_ascii=False, allow_nan=False, indent=2) + "\n"
    temporal = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=ruta.parent,
                                         prefix=".cache-precios-", suffix=".tmp", delete=False) as archivo:
            temporal = Path(archivo.name)
            archivo.write(serializado)
            archivo.flush()
            os.fsync(archivo.fileno())
        os.replace(str(temporal), str(ruta))
        temporal = None
    finally:
        if temporal is not None:
            temporal.unlink(missing_ok=True)


class ClientePrecios:
    def __init__(self, fetch, ruta_cache, ahora=None, persistir_cache=True):
        self.fetch = fetch
        self.ruta_cache = Path(ruta_cache)
        self.ahora = ahora or (lambda: datetime.now(ZoneInfo("America/Argentina/Buenos_Aires")))
        self.persistir_cache = persistir_cache
        self._vivos_pendientes = {}

    def guardar_cache(self):
        """Publica las consultas nuevas, opcionalmente diferidas por el comando."""
        if not self._vivos_pendientes:
            return 0
        _guardar_cache(self.ruta_cache, self._vivos_pendientes)
        cantidad = len(self._vivos_pendientes)
        self._vivos_pendientes.clear()
        return cantidad

    def _panel(self, endpoint):
        try:
            respuesta = self.fetch(_BASE + endpoint)
        except Exception:
            return []
        return respuesta if isinstance(respuesta, list) else []

    def obtener(self, posiciones):
        posiciones = list(posiciones)
        ahora = _instante(self.ahora())
        cache = _leer_cache(self.ruta_cache)
        grupos = {}
        for posicion in posiciones:
            endpoint = ENDPOINTS.get(posicion.tipo)
            if endpoint is not None:
                grupos.setdefault(endpoint, []).append(posicion)
        cotizaciones, vivos = {}, {}
        for endpoint, panel_posiciones in grupos.items():
            filas = {}
            repetidos = set()
            for fila in self._panel(endpoint):
                if not isinstance(fila, dict) or not isinstance(fila.get("symbol"), str):
                    continue
                ticker = fila["symbol"]
                if ticker in filas:
                    repetidos.add(ticker)
                filas[ticker] = fila
            for posicion in panel_posiciones:
                ticker = posicion.ticker
                fila = filas.get(ticker, {}) if ticker not in repetidos else {}
                ultimo = _numero(fila.get("c"), positivo=True)
                if ultimo is not None:
                    cotizacion = Cotizacion(
                        ticker=ticker, ultimo=ultimo,
                        bid=_numero(fila.get("px_bid"), positivo=True),
                        ask=_numero(fila.get("px_ask"), positivo=True),
                        pct_dia=_numero(fila.get("pct_change")),
                        estado="vivo", consultado_en=ahora,
                    )
                    cotizaciones[ticker] = vivos[ticker] = cotizacion
        for posicion in posiciones:
            if posicion.ticker not in cotizaciones:
                cotizaciones[posicion.ticker] = cache.get(posicion.ticker) or Cotizacion(
                    ticker=posicion.ticker, ultimo=None, bid=None, ask=None,
                    pct_dia=None, estado="sin_dato", consultado_en=ahora,
                )
        if vivos:
            self._vivos_pendientes.update(vivos)
            if self.persistir_cache:
                self.guardar_cache()
        return cotizaciones

    def dolar_mep(self):
        ahora = _instante(self.ahora())
        filas = [fila for fila in self._panel("mep")
                 if isinstance(fila, dict) and fila.get("ticker") == "AL30"]
        if len(filas) != 1:
            return None
        fila = filas[0]
        ultimo = _numero(fila.get("mark"), positivo=True)
        if ultimo is None:
            return None
        cotizacion = Cotizacion(
            ticker="MEP", ultimo=ultimo,
            bid=_numero(fila.get("bid"), positivo=True),
            ask=_numero(fila.get("ask"), positivo=True),
            pct_dia=None, estado="vivo", consultado_en=ahora,
        )
        self._vivos_pendientes["MEP"] = cotizacion
        if self.persistir_cache:
            self.guardar_cache()
        return cotizacion


def capturar_historial(cotizaciones, ruta_csv):
    """Agrega consultas vivas, conservando el archivo anterior ante fallas de escritura."""
    filas = []
    for cotizacion in cotizaciones.values():
        if cotizacion.estado != "vivo":
            continue
        if not isinstance(cotizacion.ticker, str) or not cotizacion.ticker:
            raise ValueError("La cotización no tiene ticker.")
        ultimo = _numero(cotizacion.ultimo, positivo=True)
        if ultimo is None:
            raise ValueError("El historial requiere un último precio positivo y finito.")
        filas.append([
            _instante(cotizacion.consultado_en).isoformat(), cotizacion.ticker, ultimo,
            _numero(cotizacion.bid, positivo=True), _numero(cotizacion.ask, positivo=True),
        ])
    if not filas:
        return 0
    ruta = Path(ruta_csv)
    ruta.parent.mkdir(parents=True, exist_ok=True)
    with ruta.open("a+b", buffering=0) as archivo:
        fcntl.flock(archivo.fileno(), fcntl.LOCK_EX)
        longitud = os.fstat(archivo.fileno()).st_size
        ultimo_byte = None
        if longitud:
            archivo.seek(0)
            encabezado = archivo.readline(4096).decode("utf-8")
            if next(csv.reader([encabezado]), None) != _COLUMNAS:
                raise ValueError("El encabezado de historial.csv no coincide con el formato esperado.")
            archivo.seek(-1, os.SEEK_END)
            ultimo_byte = archivo.read(1)
        salida = io.StringIO(newline="")
        escritor = csv.writer(salida)
        if not longitud:
            escritor.writerow(_COLUMNAS)
        elif ultimo_byte not in (b"\n", b"\r"):
            salida.write("\n")
        escritor.writerows(filas)
        archivo.seek(0, os.SEEK_END)
        try:
            pendiente = salida.getvalue().encode("utf-8")
            while pendiente:
                escritos = archivo.write(pendiente)
                if not escritos:
                    raise OSError("No se pudo completar la escritura del historial.")
                pendiente = pendiente[escritos:]
            os.fsync(archivo.fileno())
        except BaseException:
            # El bloqueo impide quitar filas agregadas por otro capturador.
            os.ftruncate(archivo.fileno(), longitud)
            raise
    return len(filas)


def _precio_formateado(valor):
    texto = format(Decimal(str(valor)), ",f")
    if "." in texto:
        texto = texto.rstrip("0").rstrip(".")
    return texto.translate(str.maketrans({",": ".", ".": ","}))


def advertencias_precio(lotes, posiciones, cotizaciones):
    """Advierte por unidades o monedas posibles sin alterar el costo de los lotes."""
    tickers = {posicion.ticker for posicion in posiciones}
    advertencias = []
    for numero_lote, lote in enumerate(lotes, 1):
        cotizacion = cotizaciones.get(lote.ticker)
        compra = _numero(lote.precio, positivo=True)
        actual = _numero(cotizacion.ultimo, positivo=True) if cotizacion is not None else None
        if lote.ticker not in tickers or compra is None or actual is None:
            continue
        compra_decimal, actual_decimal = Decimal(str(compra)), Decimal(str(actual))
        if compra_decimal > actual_decimal * 5 or compra_decimal < actual_decimal / 5:
            procedencia = "último dato guardado" if cotizacion.estado == "cache" else "cotización consultada"
            advertencias.append(
                "ADVERTENCIA {} (lote {}): precio de compra {} y precio actual {} ({}); "
                "posible error de unidad o moneda. El lote conserva su origen {}.".format(
                    lote.ticker, numero_lote, _precio_formateado(compra),
                    _precio_formateado(actual), procedencia, lote.origen)
            )
    return advertencias


# La API pública conserva las funciones del día cero en cartera.precios.
from .dia_cero import (  # noqa: E402
    ErrorDiaCero, PatrimonioInicial, cargar_efectivo_dia_cero,
    fijar_dia_cero, patrimonio_inicial,
)
