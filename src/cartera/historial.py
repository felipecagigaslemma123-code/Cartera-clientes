"""Rendimiento vendido y cobrado desde los extractos, separado del día cero."""

import csv
import fcntl
import io
import json
import math
import os
import tempfile
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

from ._historial_lectura import (
    ErrorHistorial, clasificar, consolidar, leer_ajustes, leer_extracto, leer_mep,
)
from ._historial_calculos import (
    Historial, RealizadoHistorico, conciliar_tenencias, construir_historial,
)


_COLUMNAS_REALIZADO = ("ticker", "fecha", "cantidad", "cantidad_sin_lote", "importe_ars",
                        "costo_ars", "resultado_ars", "origen_costo", "clase")


def _ruta(carpeta, nombre, directorio=False):
    ruta = carpeta / nombre
    if ruta.is_symlink() or ruta.resolve().parent != carpeta.resolve():
        raise ErrorHistorial("{} debe permanecer en la carpeta del cliente y no ser un enlace.".format(nombre))
    if ruta.exists() and not (ruta.is_dir() if directorio else ruta.is_file()):
        raise ErrorHistorial("{} debe ser {}.".format(nombre, "una carpeta" if directorio else "un archivo"))
    return ruta


def _leer_cierres(ruta):
    if not ruta.exists():
        return []
    try:
        contenido = json.loads(ruta.read_text(encoding="utf-8"))
    except (ValueError, UnicodeError):
        raise ErrorHistorial("cierres.json no es un JSON válido.") from None
    if not isinstance(contenido, list) or any(not isinstance(t, str) or not t.strip() for t in contenido):
        raise ErrorHistorial("cierres.json debe contener una lista de tickers no vacíos.")
    return [ticker.strip() for ticker in contenido]


def _cierres_diarios(contenido, ticker):
    if not isinstance(contenido, list):
        raise ErrorHistorial("El histórico de {} no contiene una lista de precios.".format(ticker))
    precios = {}
    for indice, fila in enumerate(contenido, 1):
        contexto = "Histórico {} fila {}".format(ticker, indice)
        if not isinstance(fila, dict):
            raise ErrorHistorial(contexto + ": se esperaba un objeto con date y c.")
        fecha = fila.get("date")
        if isinstance(fecha, datetime):
            fecha = fecha.date()
        elif isinstance(fecha, str):
            try:
                fecha = date.fromisoformat(fecha)
            except ValueError:
                raise ErrorHistorial(contexto + ": date debe tener formato AAAA-MM-DD.") from None
        if not isinstance(fecha, date):
            raise ErrorHistorial(contexto + ": falta una fecha válida.")
        precio = fila.get("c")
        try:
            valido = (not isinstance(precio, bool) and isinstance(precio, (int, float))
                      and math.isfinite(float(precio)) and precio > 0)
        except (ValueError, OverflowError):
            valido = False
        if not valido:
            raise ErrorHistorial(contexto + ": c debe ser un número positivo y finito.")
        if fecha in precios and precios[fecha] != float(precio):
            raise ErrorHistorial(contexto + ": hay cierres diferentes para la misma fecha.")
        precios[fecha] = float(precio)
    return precios


def _actualizar_mep(mep, fetch):
    if fetch is None:
        from .transporte import consultar_json
        fetch = consultar_json
    respuestas = []
    for ticker in ("AL30", "AL30D"):
        try:
            contenido = fetch("https://data912.com/historical/bonds/" + ticker)
        except Exception:
            raise ErrorHistorial("No se pudo consultar el histórico de {} para actualizar el MEP.".format(ticker)) from None
        respuestas.append(_cierres_diarios(contenido, ticker))
    pesos, dolares = respuestas
    comunes = pesos.keys() & dolares.keys()
    if not comunes:
        raise ErrorHistorial("No hay fechas con cierres de AL30 y AL30D para actualizar el MEP.")
    actualizado = dict(mep)
    for fecha in sorted(comunes):
        valor = pesos[fecha] / dolares[fecha]
        if not math.isfinite(valor) or valor <= 0:
            raise ErrorHistorial("El MEP calculado para {} está fuera de rango.".format(fecha.isoformat()))
        actualizado[fecha] = valor
    return actualizado


def _suma_costos(lotes):
    lotes = list(lotes)
    if any(lote.costo is None for lote in lotes):
        return None
    valor = float(sum((Decimal(str(lote.costo)) for lote in lotes), Decimal(0)))
    if not math.isfinite(valor):
        raise ErrorHistorial("El costo acumulado de los lotes excede el rango finito.")
    return valor


def _diferencias_costos(lotes, punto):
    tickers = {l.ticker for l in lotes} | {p.ticker for p in punto.posiciones}
    diferencias = {}
    for ticker in sorted(tickers):
        derivada = _suma_costos(l for l in lotes if l.ticker == ticker)
        base = _suma_costos(l for l in punto.lotes if l.ticker == ticker)
        if (derivada is None) != (base is None) or (derivada is not None and abs(derivada - base) > 1):
            diferencia = None if derivada is None or base is None else derivada - base
            if diferencia is not None and not math.isfinite(diferencia):
                raise ErrorHistorial("La diferencia de costo de {} excede el rango finito.".format(ticker))
            diferencias[ticker] = {"derivada": derivada, "base": base, "diferencia": diferencia}
    return diferencias


def _texto_costo(valor):
    return "sin dato" if valor is None else format(valor, ",.2f").translate(str.maketrans({",": ".", ".": ","}))


def _preparar_historial(carpeta, punto, fetch=None, actualizar_mep=False):
    carpeta = Path(carpeta)
    if not carpeta.is_dir():
        raise ErrorHistorial("La carpeta del cliente no existe.")
    extractos = _ruta(carpeta, "extractos", directorio=True)
    if not extractos.exists():
        raise ErrorHistorial("No existe extractos/: agregá los extractos antes de calcular el historial.")
    archivos = sorted((p for p in extractos.iterdir() if p.suffix.lower() == ".xlsx"), key=lambda p: p.name)
    if not archivos:
        raise ErrorHistorial("extractos/ no contiene archivos .xlsx.")
    filas = []
    for archivo in archivos:
        if archivo.is_symlink() or archivo.resolve().parent != extractos.resolve() or not archivo.is_file():
            raise ErrorHistorial("extractos/{} debe ser un archivo y no un enlace.".format(archivo.name))
        filas.extend(leer_extracto(archivo))
    ajustes = leer_ajustes(_ruta(carpeta, "ajustes_historial.csv"))
    cierres = _leer_cierres(_ruta(carpeta, "cierres.json"))
    mep = leer_mep(_ruta(carpeta, "mep_diario.csv"))
    # Validar también la semántica antes de consultar la fuente o publicar salidas.
    # Al actualizar no convertir con un MEP viejo que está por reemplazarse.
    historial = construir_historial(filas, ajustes=ajustes, cierres=cierres,
                                    mep={} if actualizar_mep else mep)
    if actualizar_mep:
        mep = _actualizar_mep(mep, fetch)
        historial = construir_historial(filas, ajustes=ajustes, cierres=cierres, mep=mep)
    historial.diferencias_tenencias = conciliar_tenencias(historial.lotes, punto.posiciones)
    historial.diferencias_costos = _diferencias_costos(historial.lotes, punto)
    for ticker, valores in historial.diferencias_tenencias.items():
        historial.avisos.append("{}: cantidad derivada {}, base {}, diferencia {}; la base se conserva.".format(
            ticker, valores["derivada"], valores["base"], valores["diferencia"]))
    for ticker, valores in historial.diferencias_costos.items():
        historial.avisos.append("{}: costo derivado ARS {}, base ARS {}; no se modifica la base.".format(
            ticker, _texto_costo(valores["derivada"]), _texto_costo(valores["base"])))
    return historial, mep


def _cargar_historial(carpeta, punto):
    """Carga para el dashboard sin publicar CSV ni actualizar datos de mercado."""
    return _preparar_historial(carpeta, punto)[0]


def _csv_realizados(historial):
    salida = io.StringIO(newline="")
    escritor = csv.writer(salida, lineterminator="\n")
    escritor.writerow(_COLUMNAS_REALIZADO)
    for realizado in historial.realizados:
        escritor.writerow([realizado.fecha.isoformat() if campo == "fecha" else
                           "" if getattr(realizado, campo) is None else getattr(realizado, campo)
                           for campo in _COLUMNAS_REALIZADO])
    return salida.getvalue().encode("utf-8")


def _csv_mep(mep):
    salida = io.StringIO(newline="")
    escritor = csv.writer(salida, lineterminator="\n")
    escritor.writerow(("fecha", "mep"))
    escritor.writerows((fecha.isoformat(), valor) for fecha, valor in sorted(mep.items()))
    return salida.getvalue().encode("utf-8")


def _temporal(ruta, contenido):
    temporal = None
    try:
        with tempfile.NamedTemporaryFile(mode="wb", dir=ruta.parent, prefix=".historial-", suffix=".tmp", delete=False) as salida:
            temporal = Path(salida.name)
            os.fchmod(salida.fileno(), 0o600)
            salida.write(contenido)
            salida.flush()
            os.fsync(salida.fileno())
        return temporal
    except BaseException:
        if temporal is not None:
            temporal.unlink(missing_ok=True)
        raise


def _publicar(salidas):
    """Prepara archivos completos y revierte los publicados si falla otro reemplazo."""
    temporales, respaldos = {}, {}
    publicados, conservar = [], set()
    try:
        for ruta, contenido in salidas.items():
            _ruta(ruta.parent, ruta.name)
            temporales[ruta] = _temporal(ruta, contenido)
            respaldos[ruta] = _temporal(ruta, ruta.read_bytes()) if ruta.exists() else None
        try:
            for ruta, temporal in temporales.items():
                _ruta(ruta.parent, ruta.name)
                os.replace(str(temporal), str(ruta))
                publicados.append(ruta)
        except BaseException:
            errores = []
            for ruta in reversed(publicados):
                respaldo = respaldos[ruta]
                try:
                    if respaldo is None:
                        ruta.unlink(missing_ok=True)
                    else:
                        os.replace(str(respaldo), str(ruta))
                except OSError:
                    if respaldo is not None:
                        conservar.add(respaldo)
                    errores.append(str(respaldo or ruta))
            if errores:
                raise ErrorHistorial("Falló la publicación y no se pudo completar la restauración. "
                                     "Revisá los archivos o respaldos privados: " + ", ".join(errores)) from None
            raise
    finally:
        for temporal in list(temporales.values()) + list(respaldos.values()):
            if temporal is not None and temporal not in conservar:
                temporal.unlink(missing_ok=True)


def correr_historial(carpeta, punto, fetch=None, actualizar_mep=False):
    """Calcula el historial independiente y publica solo sus salidas privadas."""
    carpeta = Path(carpeta)
    if not carpeta.is_dir():
        raise ErrorHistorial("La carpeta del cliente no existe.")
    # Evita intercalar dos cálculos sin crear archivos de bloqueo ni alterar entradas.
    descriptor = os.open(str(carpeta), os.O_RDONLY)
    try:
        fcntl.flock(descriptor, fcntl.LOCK_EX)
        ruta_realizado = _ruta(carpeta, "realizado.csv")
        ruta_mep = _ruta(carpeta, "mep_diario.csv") if actualizar_mep else None
        historial, mep = _preparar_historial(carpeta, punto, fetch, actualizar_mep)
        salidas = {ruta_realizado: _csv_realizados(historial)}
        if actualizar_mep:
            salidas[ruta_mep] = _csv_mep(mep)
        _publicar(salidas)
        return historial
    finally:
        os.close(descriptor)
