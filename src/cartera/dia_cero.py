"""Foto inicial de cantidades, precios y efectivo, sin depender de los costos."""

import fcntl
import json
import math
import os
import tempfile
import uuid
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import List, Optional
from zoneinfo import ZoneInfo


class ErrorDiaCero(ValueError):
    """No se puede fijar, completar o interpretar una referencia inicial."""


@dataclass
class PatrimonioInicial:
    valuacion_posiciones: float
    efectivo_ars: Optional[float]
    efectivo_usd: Optional[float]
    total: Optional[float]
    faltantes: List[str]


def _ahora():
    return datetime.now(ZoneInfo("America/Argentina/Buenos_Aires"))


def _numero(valor, nombre, positivo=False):
    if isinstance(valor, bool) or not isinstance(valor, (int, float)):
        raise ErrorDiaCero("{} debe ser un número finito{}.".format(nombre, " positivo" if positivo else ""))
    try:
        numero = float(valor)
    except (OverflowError, ValueError):
        raise ErrorDiaCero("{} está fuera del rango numérico.".format(nombre)) from None
    if not math.isfinite(numero) or (positivo and numero <= 0):
        raise ErrorDiaCero("{} debe ser un número finito{}.".format(nombre, " positivo" if positivo else ""))
    return numero


def _fecha_iso(valor, nombre, admite_nulo=False):
    if valor is None and admite_nulo:
        return None
    if isinstance(valor, datetime):
        return valor.date().isoformat()
    if isinstance(valor, date):
        return valor.isoformat()
    if isinstance(valor, str):
        try:
            return date.fromisoformat(valor).isoformat()
        except ValueError:
            pass
    raise ErrorDiaCero("{} debe ser una fecha AAAA-MM-DD{}.".format(nombre, " o null" if admite_nulo else ""))


def _validar_efectivo(efectivo):
    if efectivo is None:
        efectivo = {}
    if not isinstance(efectivo, dict):
        raise ErrorDiaCero("El efectivo debe ser un objeto con fecha, ARS y USD.")
    normalizado = {"fecha": _fecha_iso(efectivo.get("fecha"), "La fecha del efectivo", admite_nulo=True)}
    for moneda in ("ARS", "USD"):
        valor = efectivo.get(moneda)
        normalizado[moneda] = None if valor is None else _numero(valor, "El efectivo " + moneda)
    return normalizado


def _timestamp(valor, nombre):
    try:
        instante = datetime.fromisoformat(valor)
        if instante.utcoffset() is not None:
            return
    except (ValueError, TypeError):
        pass
    raise ErrorDiaCero("{} debe incluir fecha, hora y zona horaria.".format(nombre))


def _validar_dia_cero(contenido):
    if not isinstance(contenido, dict) or type(contenido.get("esquema_version")) is not int:
        raise ErrorDiaCero("El día cero no contiene una versión de esquema válida.")
    if contenido["esquema_version"] != 2:
        raise ErrorDiaCero("Versión de día cero no compatible; se necesita la foto con cantidades guardadas.")
    _fecha_iso(contenido.get("fecha"), "La fecha del día cero")
    _timestamp(contenido.get("fijado_en"), "fijado_en")
    cantidades = contenido.get("cantidades")
    precios = contenido.get("precios")
    if not isinstance(cantidades, dict) or not cantidades or not isinstance(precios, dict):
        raise ErrorDiaCero("El día cero debe contener cantidades y precios por especie.")
    if set(cantidades) != set(precios):
        raise ErrorDiaCero("Las especies de cantidades y precios del día cero no coinciden.")
    for ticker, cantidad in cantidades.items():
        if not isinstance(ticker, str) or not ticker.strip():
            raise ErrorDiaCero("El día cero contiene un ticker inválido.")
        _numero(cantidad, "La cantidad de " + ticker, positivo=True)
        _numero(precios[ticker], "El precio de " + ticker, positivo=True)
    if "mep" not in contenido or "efectivo" not in contenido:
        raise ErrorDiaCero("El día cero debe informar MEP y efectivo, aunque sean datos faltantes.")
    if contenido["mep"] is not None:
        _numero(contenido["mep"], "El dólar MEP", positivo=True)
    if not isinstance(contenido["efectivo"], dict):
        raise ErrorDiaCero("El efectivo guardado debe ser un objeto con fecha, ARS y USD.")
    _validar_efectivo(contenido["efectivo"])
    if "efectivo_cargado_en" in contenido:
        _timestamp(contenido["efectivo_cargado_en"], "efectivo_cargado_en")
    return contenido


def _sin_constantes(valor):
    raise ErrorDiaCero("El día cero contiene un número no finito: " + valor)


def _leer_dia_cero(ruta):
    try:
        contenido = json.loads(Path(ruta).read_text(encoding="utf-8"), parse_constant=_sin_constantes)
    except FileNotFoundError:
        raise ErrorDiaCero("No existe un día cero fijado.") from None
    except (json.JSONDecodeError, UnicodeError):
        raise ErrorDiaCero("dia_cero.json no es un JSON válido; no se modificó el archivo.") from None
    return _validar_dia_cero(contenido)


def _guardar_atomico(ruta, contenido, forzar=False):
    ruta = Path(ruta)
    if ruta.is_symlink():
        raise ErrorDiaCero("El archivo de día cero no puede ser un enlace.")
    if ruta.exists() and not forzar:
        raise ErrorDiaCero("El día cero ya existe; usá forzar para reemplazarlo.")
    serializado = (json.dumps(contenido, ensure_ascii=False, indent=2, allow_nan=False) + "\n").encode("utf-8")
    ruta.parent.mkdir(parents=True, exist_ok=True)
    temporal = None
    try:
        with tempfile.NamedTemporaryFile(mode="wb", dir=ruta.parent, prefix=".dia-cero-", suffix=".tmp", delete=False) as salida:
            temporal = Path(salida.name)
            salida.write(serializado)
            salida.flush()
            os.fsync(salida.fileno())
        if forzar:
            os.replace(str(temporal), str(ruta))
            temporal = None
        else:
            try:
                os.link(str(temporal), str(ruta))
            except FileExistsError:
                raise ErrorDiaCero("El día cero ya existe; no se reemplazó.") from None
    finally:
        if temporal is not None:
            temporal.unlink(missing_ok=True)


def _respaldar(ruta, contenido):
    """Guarda una versión anterior completa sin pisar respaldos previos."""
    carpeta = Path(ruta).parent / "historial_dia_cero"
    if carpeta.is_symlink():
        raise ErrorDiaCero("historial_dia_cero no puede ser un enlace a otra carpeta.")
    carpeta.mkdir(exist_ok=True)
    nombre = "dia_cero_{}_{}.json".format(_ahora().strftime("%Y%m%dT%H%M%S_%f"), uuid.uuid4().hex)
    temporal = None
    try:
        with tempfile.NamedTemporaryFile(mode="wb", dir=carpeta, prefix=".dia-cero-", suffix=".tmp", delete=False) as salida:
            temporal = Path(salida.name)
            salida.write(contenido)
            salida.flush()
            os.fsync(salida.fileno())
        os.link(str(temporal), str(carpeta / nombre))
    finally:
        if temporal is not None:
            temporal.unlink(missing_ok=True)
    return carpeta / nombre


def _efectivo_vacio(efectivo):
    return efectivo["ARS"] is None and efectivo["USD"] is None


def _efectivo_a_conservar(anteriores):
    """Devuelve el efectivo ya cargado en una versión anterior legible, o None."""
    try:
        contenido = _validar_dia_cero(json.loads(anteriores.decode("utf-8"), parse_constant=_sin_constantes))
    except (ValueError, UnicodeError):
        return None
    efectivo = _validar_efectivo(contenido["efectivo"])
    if _efectivo_vacio(efectivo):
        return None
    return efectivo, contenido.get("efectivo_cargado_en")


def fijar_dia_cero(posiciones, cotizaciones, ruta, fecha, forzar=False, mep=None, efectivo=None):
    """Fija precios observados y cantidades; los costos no intervienen.

    Al forzar, respalda la versión anterior y, si no se recibe efectivo, conserva el
    ya cargado: volver a tomar precios no debe borrar un saldo.
    """
    if not isinstance(cotizaciones, dict):
        raise ErrorDiaCero("Las cotizaciones deben estar identificadas por ticker.")
    posiciones = list(posiciones)
    cantidades, precios = {}, {}
    for posicion in posiciones:
        ticker = posicion.ticker
        if not isinstance(ticker, str) or not ticker.strip() or ticker in cantidades:
            raise ErrorDiaCero("Las posiciones contienen un ticker inválido o repetido.")
        cantidades[ticker] = _numero(posicion.cantidad, "La cantidad de " + ticker, positivo=True)
        cotizacion = cotizaciones.get(ticker)
        if cotizacion is None or cotizacion.estado != "vivo":
            raise ErrorDiaCero("{}: falta una cotización viva para fijar el día cero.".format(ticker))
        if cotizacion.ticker != ticker:
            raise ErrorDiaCero("{}: la cotización corresponde a otra especie.".format(ticker))
        precios[ticker] = _numero(cotizacion.ultimo, "El precio de " + ticker, positivo=True)
    contenido = {
        "esquema_version": 2,
        "fecha": _fecha_iso(fecha, "La fecha del día cero"),
        "fijado_en": _ahora().isoformat(),
        "cantidades": cantidades,
        "precios": precios,
        "mep": None if mep is None else _numero(mep, "El dólar MEP", positivo=True),
        "efectivo": _validar_efectivo(efectivo),
    }
    anteriores = None
    if forzar and Path(ruta).is_file() and not Path(ruta).is_symlink():
        anteriores = Path(ruta).read_bytes()
        conservado = _efectivo_a_conservar(anteriores)
        if conservado is not None and _efectivo_vacio(contenido["efectivo"]):
            contenido["efectivo"] = conservado[0]
            if conservado[1] is not None:
                contenido["efectivo_cargado_en"] = conservado[1]
    _validar_dia_cero(contenido)
    # Verificar la unidad de cada especie y el rango numérico antes de escribir.
    patrimonio_inicial(posiciones, contenido)
    if anteriores is not None:
        _respaldar(ruta, anteriores)
    _guardar_atomico(ruta, contenido, forzar=forzar)
    return contenido


def cargar_efectivo_dia_cero(ruta, efectivo, forzar=False):
    """Completa saldos sin consultar ni volver a tomar precios."""
    ruta = Path(ruta)
    nuevo_efectivo = _validar_efectivo(efectivo)
    if ruta.is_symlink():
        raise ErrorDiaCero("El archivo de día cero no puede ser un enlace.")
    try:
        entrada = ruta.open("rb")
    except FileNotFoundError:
        raise ErrorDiaCero("No existe un día cero fijado.") from None
    with entrada:
        fcntl.flock(entrada.fileno(), fcntl.LOCK_EX)
        anteriores = entrada.read()
        try:
            contenido = json.loads(anteriores.decode("utf-8"), parse_constant=_sin_constantes)
        except (json.JSONDecodeError, UnicodeError):
            raise ErrorDiaCero("dia_cero.json no es un JSON válido; no se modificó el archivo.") from None
        _validar_dia_cero(contenido)
        habia_efectivo = any(contenido["efectivo"].get(moneda) is not None for moneda in ("ARS", "USD"))
        if not forzar and habia_efectivo:
            raise ErrorDiaCero("El día cero ya tiene efectivo cargado; usá forzar para reemplazarlo.")
        contenido["efectivo"] = nuevo_efectivo
        contenido["efectivo_cargado_en"] = _ahora().isoformat()
        actual = ruta.stat()
        abierta = os.fstat(entrada.fileno())
        if (actual.st_dev, actual.st_ino) != (abierta.st_dev, abierta.st_ino) or ruta.read_bytes() != anteriores:
            raise ErrorDiaCero("El día cero cambió durante la carga; volvé a intentar con la versión actual.")
        if habia_efectivo:
            _respaldar(ruta, anteriores)
        _guardar_atomico(ruta, contenido, forzar=True)
    return contenido


def _suma_finita(valores):
    try:
        total = math.fsum(valores)
    except OverflowError:
        raise ErrorDiaCero("El patrimonio inicial está fuera del rango numérico.") from None
    if not math.isfinite(total):
        raise ErrorDiaCero("El patrimonio inicial está fuera del rango numérico.")
    return total


def patrimonio_inicial(posiciones, dia_cero):
    """Valúa la foto guardada; las posiciones actuales solo aportan su unidad."""
    _validar_dia_cero(dia_cero)
    unidades = {}
    for posicion in posiciones:
        if posicion.ticker in unidades:
            raise ErrorDiaCero("Las posiciones contienen tickers repetidos.")
        unidad = _numero(posicion.cotiza_cada, "La unidad de " + posicion.ticker, positivo=True)
        if unidad not in (1, 100):
            raise ErrorDiaCero("{}: la unidad debe ser 1 o 100.".format(posicion.ticker))
        unidades[posicion.ticker] = unidad
    valores = []
    for ticker, cantidad in dia_cero["cantidades"].items():
        if ticker not in unidades:
            raise ErrorDiaCero("{}: falta la unidad de cotización para valuar el día cero.".format(ticker))
        valor = float(cantidad) / unidades[ticker] * float(dia_cero["precios"][ticker])
        if not math.isfinite(valor):
            raise ErrorDiaCero("{}: la valuación inicial está fuera del rango numérico.".format(ticker))
        valores.append(valor)
    valuacion = _suma_finita(valores)
    efectivo = _validar_efectivo(dia_cero["efectivo"])
    ars, usd, mep = efectivo["ARS"], efectivo["USD"], dia_cero["mep"]
    faltantes = []
    if ars is None:
        faltantes.append("efectivo ARS")
    if usd is None:
        faltantes.append("efectivo USD")
    elif usd != 0 and mep is None:
        faltantes.append("dólar MEP")
    total = None
    if not faltantes:
        conversion = 0.0 if usd == 0 else usd * mep
        total = _suma_finita((valuacion, ars, conversion))
    return PatrimonioInicial(valuacion, ars, usd, total, faltantes)
