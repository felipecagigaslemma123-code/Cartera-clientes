"""Corrida de alertas con exclusión por cliente y confirmación de entrega."""

import copy
import fcntl
import json
import math
import os
import tempfile
import uuid
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from .alertas import (
    Evento, _validar_estado_niveles, _validar_estado_vencimientos,
    en_horario_mercado, evaluar_niveles, evaluar_vencimientos,
)
from .notificar import Notificador
from .dia_cero import _leer_dia_cero
from .movimientos import cartera_actual, leer_movimientos, validar_movimientos
from .precios import ClientePrecios


_ARGENTINA = ZoneInfo("America/Argentina/Buenos_Aires")


def ahora_argentina():
    return datetime.now(_ARGENTINA)


def _ruta(carpeta, nombre):
    ruta = carpeta / nombre
    if ruta.is_symlink() or ruta.resolve().parent != carpeta.resolve():
        raise ValueError("{} debe estar en la carpeta del cliente y no ser un enlace.".format(nombre))
    if ruta.exists() and not ruta.is_file():
        raise ValueError("{} debe ser un archivo.".format(nombre))
    return ruta


def _constante_invalida(texto):
    raise ValueError("Número no finito")


def _leer_json(ruta, defecto):
    if not ruta.exists():
        return copy.deepcopy(defecto)
    try:
        return json.loads(ruta.read_text(encoding="utf-8"), parse_constant=_constante_invalida)
    except (ValueError, UnicodeError):
        raise ValueError("{} no contiene un JSON válido.".format(ruta.name)) from None


def _estado_vacio():
    return {"esquema_version": 1, "niveles": {}, "vencimientos": {}, "control": None,
            "error_niveles": None, "error_instrumentos": None, "error_movimientos": None}


def _validar_estado(estado):
    if not isinstance(estado, dict) or type(estado.get("esquema_version")) is not int or estado["esquema_version"] != 1:
        raise ValueError("El estado no tiene una versión válida.")
    _validar_estado_niveles(estado.get("niveles"))
    _validar_estado_vencimientos(estado.get("vencimientos"))
    for campo in ("control", "error_niveles", "error_instrumentos", "error_movimientos"):
        valor = estado.get(campo)
        if valor is not None:
            if not isinstance(valor, str):
                raise ValueError("La fecha de estado no es válida.")
            date.fromisoformat(valor)
    return dict(_estado_vacio(), **estado)


def _escribir_temporal(carpeta, contenido, prefijo):
    temporal = None
    try:
        with tempfile.NamedTemporaryFile(mode="wb", dir=carpeta, prefix=prefijo,
                                         suffix=".tmp", delete=False) as salida:
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


def _respaldar_corrupto(carpeta, contenido, ahora):
    ruta = _ruta(carpeta, "estado_alertas.corrupto.json")
    if ruta.exists():
        if ruta.read_bytes() == contenido:
            return
        nombre = "estado_alertas.corrupto.{}_{}.json".format(ahora.strftime("%Y%m%dT%H%M%S_%f"), uuid.uuid4().hex)
        ruta = _ruta(carpeta, nombre)
    temporal = _escribir_temporal(carpeta, contenido, ".estado-corrupto-")
    try:
        os.link(str(temporal), str(ruta))
    finally:
        temporal.unlink(missing_ok=True)


def _cargar_estado(ruta, ahora):
    if not ruta.exists():
        return _estado_vacio(), False
    contenido = ruta.read_bytes()
    try:
        return _validar_estado(json.loads(contenido.decode("utf-8"), parse_constant=_constante_invalida)), False
    except (ValueError, TypeError, UnicodeError, OverflowError):
        _respaldar_corrupto(ruta.parent, contenido, ahora)
        return _estado_vacio(), True


def _niveles_validos(contenido, punto, conocidas=None, avisos=None):
    if not isinstance(contenido, dict):
        raise ValueError("niveles.json debe contener un objeto.")
    activos = {posicion.ticker for posicion in punto.posiciones}
    conocidas = activos if conocidas is None else conocidas
    niveles = {}
    for ticker, valores in contenido.items():
        if ticker in conocidas and ticker not in activos:
            if avisos is not None:
                avisos.append("{}: nivel ignorado porque la especie ya no tiene tenencia.".format(ticker))
            continue
        if ticker not in activos or not isinstance(valores, dict):
            raise ValueError("niveles.json contiene una especie desconocida o un objeto inválido.")
        # Una clave mal escrita dejaría la especie sin control y sin que se note.
        if set(valores) - {"take_profit", "stop_loss"}:
            raise ValueError("niveles.json contiene una clave desconocida.")
        valores = {lado: valores.get(lado) for lado in ("take_profit", "stop_loss")}
        for valor in valores.values():
            if valor is None:
                continue
            try:
                valido = (not isinstance(valor, bool) and isinstance(valor, (int, float))
                          and math.isfinite(float(valor)) and valor > 0)
            except (ValueError, OverflowError):
                valido = False
            if not valido:
                raise ValueError("niveles.json contiene un nivel que no es positivo y finito o null.")
        if valores["take_profit"] is not None and valores["stop_loss"] is not None:
            if valores["take_profit"] <= valores["stop_loss"]:
                raise ValueError("niveles.json requiere take_profit mayor que stop_loss.")
        if any(valor is not None for valor in valores.values()):
            niveles[ticker] = valores
    return niveles


def _instrumentos_validos(contenido, punto):
    if not isinstance(contenido, dict):
        raise ValueError("instrumentos.json debe contener un objeto.")
    activos = {posicion.ticker for posicion in punto.posiciones}
    instrumentos = {}
    for ticker, instrumento in contenido.items():
        if not isinstance(instrumento, dict):
            raise ValueError("instrumentos.json contiene un objeto inválido.")
        vencimiento = instrumento.get("vencimiento")
        if vencimiento is not None:
            try:
                date.fromisoformat(vencimiento)
            except (TypeError, ValueError):
                raise ValueError("instrumentos.json contiene un vencimiento inválido; no se pudieron chequear vencimientos.") from None
        if ticker in activos:
            instrumentos[ticker] = {"vencimiento": vencimiento}
    return instrumentos


def _guardar_estado(ruta, estado):
    contenido = (json.dumps(estado, ensure_ascii=False, allow_nan=False, indent=2) + "\n").encode("utf-8")
    temporal = _escribir_temporal(ruta.parent, contenido, ".estado-alertas-")
    try:
        os.replace(str(temporal), str(ruta))
        temporal = None
    finally:
        if temporal is not None:
            temporal.unlink(missing_ok=True)


def _agregar_log(ruta, eventos, errores, ahora, corrupto):
    registros = []
    if corrupto:
        registros.append({"hora": ahora.isoformat(), "tipo": "estado_corrupto", "ticker": None, "precio": None})
    for evento in eventos:
        registros.append({"hora": ahora.isoformat(), "tipo": evento.tipo, "ticker": evento.ticker, "precio": evento.precio})
    for error in errores:
        registros.append({"hora": ahora.isoformat(), "tipo": "error_canal", "canal": error})
    if not registros:
        return
    contenido = "".join(json.dumps(registro, ensure_ascii=False, allow_nan=False) + "\n" for registro in registros).encode("utf-8")
    descriptor = os.open(str(ruta), os.O_WRONLY | os.O_CREAT | os.O_APPEND | getattr(os, "O_NOFOLLOW", 0), 0o600)
    with os.fdopen(descriptor, "ab", buffering=0) as salida:
        os.fchmod(salida.fileno(), 0o600)
        pendiente = contenido
        while pendiente:
            escritos = salida.write(pendiente)
            if not escritos:
                raise OSError("No se pudo completar el registro de alertas.")
            pendiente = pendiente[escritos:]
        os.fsync(salida.fileno())


def correr_alertas(carpeta, punto, slug, fetch, canales, ahora):
    """Notifica una sola vez por corrida y confirma el estado solo tras entregar."""
    if not isinstance(ahora, datetime) or ahora.utcoffset() is None:
        raise ValueError("La hora de la corrida debe incluir zona horaria.")
    ahora = ahora.astimezone(_ARGENTINA)
    carpeta = Path(carpeta)
    if not carpeta.is_dir():
        raise ValueError("La carpeta del cliente no existe.")
    bloqueo = _ruta(carpeta, ".alertas.lock")
    descriptor = os.open(str(bloqueo), os.O_CREAT | os.O_RDWR | getattr(os, "O_NOFOLLOW", 0), 0o600)
    try:
        try:
            fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return {"eventos": [], "errores": [], "entregado": True, "evaluo_niveles": False, "omitida": True, "avisos": []}
        os.fchmod(descriptor, 0o600)
        rutas = {nombre: _ruta(carpeta, nombre) for nombre in
                 ("niveles.json", "instrumentos.json", "estado_alertas.json", "cache_precios.json", "alertas.log")}
        estado, corrupto = _cargar_estado(rutas["estado_alertas.json"], ahora)
        nuevo = copy.deepcopy(estado)
        eventos, avisos, evaluo_niveles = [], [], False
        hoy = ahora.date().isoformat()
        conocidas = {p.ticker for p in punto.posiciones}
        try:
            movimientos = leer_movimientos(_ruta(carpeta, "movimientos.csv"))
            ruta_cero = _ruta(carpeta, "dia_cero.json")
            dia_cero = _leer_dia_cero(ruta_cero) if ruta_cero.exists() else None
            validar_movimientos(punto, movimientos, date.fromisoformat(dia_cero["fecha"]) if dia_cero else None,
                                ahora.date())
            actual, _ = cartera_actual(punto, movimientos)
            conocidas.update(m["ticker"] for m in movimientos if m["tipo"] == "compra")
        except (ValueError, OSError):
            actual = punto
            avisos.append("movimientos.csv inválido o no se pudo validar: se usa la base importada; revisá el archivo y el día cero.")
            if nuevo.get("error_movimientos") != hoy:
                eventos.append(Evento("sin_chequeo", None, None, None,
                                      "No se pudo reconstruir la cartera actual: movimientos.csv es inválido o no se puede validar. "
                                      "Se chequea con la base importada; revisá el archivo y el día cero."))
                nuevo["error_movimientos"] = hoy
        punto = actual
        if en_horario_mercado(ahora):
            try:
                niveles = _niveles_validos(_leer_json(rutas["niveles.json"], {}), punto, conocidas, avisos)
            except (ValueError, OSError):
                niveles = None
                avisos.append("niveles.json inválido: no se pudieron chequear los niveles.")
                if nuevo.get("error_niveles") != hoy:
                    eventos.append(Evento("sin_chequeo", None, None, None,
                                          "No se pudieron chequear los niveles: niveles.json es inválido o no se puede leer. Revisá el archivo."))
                    nuevo["error_niveles"] = hoy
            if niveles is not None:
                cotizaciones = {}
                if niveles:
                    seleccionadas = [p for p in punto.posiciones if p.ticker in niveles]
                    cliente = ClientePrecios(fetch, rutas["cache_precios.json"], ahora=lambda: ahora, persistir_cache=False)
                    cotizaciones = cliente.obtener(seleccionadas)
                    try:
                        cliente.guardar_cache()
                    except OSError:
                        avisos.append("No se pudo guardar la caché de precios; se evalúan los datos consultados.")
                    for ticker, cotizacion in cotizaciones.items():
                        if cotizacion.estado != "vivo":
                            avisos.append("{}: sin cotización viva; no se pudo chequear.".format(ticker))
                de_niveles, nuevo["niveles"] = evaluar_niveles(cotizaciones, niveles, estado["niveles"], ahora)
                eventos.extend(de_niveles)
                evaluo_niveles = True
            if nuevo.get("control") != hoy:
                mensaje = ("Alertas activas: no se pudieron validar los niveles." if niveles is None else
                           "Alertas activas: {} especies con niveles.".format(len(niveles)) if niveles else
                           "Alertas activas, pero no hay niveles definidos.")
                eventos.append(Evento("control", None, None, None, mensaje))
                nuevo["control"] = hoy
        try:
            instrumentos = _instrumentos_validos(_leer_json(rutas["instrumentos.json"], {}), punto)
        except (ValueError, OSError):
            # No debe frenar los niveles ni pasar como "sin vencimientos".
            avisos.append("instrumentos.json inválido: no se pudieron chequear los vencimientos.")
            if nuevo.get("error_instrumentos") != hoy:
                eventos.append(Evento("sin_chequeo", None, None, None,
                                      "No se pudieron chequear los vencimientos: instrumentos.json es inválido o no se puede leer. Revisá el archivo."))
                nuevo["error_instrumentos"] = hoy
        else:
            de_vencimientos, nuevo["vencimientos"] = evaluar_vencimientos(instrumentos, estado["vencimientos"], ahora.date())
            eventos.extend(de_vencimientos)
        # Descubrir canales solo cuando hay avisos evita lecturas de credenciales
        # en corridas simultáneas, fuera de horario o sin eventos nuevos.
        canales = list(canales) if eventos else []
        errores = Notificador(canales).enviar(eventos, slug)
        entregado = not eventos or bool(canales) and len(errores) < len(canales)
        if eventos and not canales:
            errores = ["No hay canales de notificación disponibles."]
        _agregar_log(rutas["alertas.log"], eventos, errores, ahora, corrupto)
        if entregado:
            _guardar_estado(rutas["estado_alertas.json"], nuevo)
        return {"eventos": eventos, "errores": errores, "entregado": entregado,
                "evaluo_niveles": evaluo_niveles, "omitida": False, "avisos": avisos}
    finally:
        os.close(descriptor)
