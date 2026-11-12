"""Base inicial y correcciones de costos con conservación de versiones completas."""

import fcntl
import hashlib
import io
import json
import math
import os
import re
import tempfile
import uuid
from collections import Counter
from dataclasses import asdict
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from zoneinfo import ZoneInfo

from .calculos import costo_total, estado_costo
from .punto_partida import Lote, Posicion, PuntoPartida, cargar_punto_partida


class ErrorCartera(ValueError):
    """La base guardada o el destino de datos no son válidos."""


def _ruta_cartera(datos, slug):
    if not isinstance(slug, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]*", slug):
        raise ErrorCartera("Cliente inválido: usá letras, números, guiones o guiones bajos.")
    raiz = Path(datos).expanduser().resolve()
    ruta = raiz / "clientes" / slug / "cartera.json"
    destino = ruta.resolve()
    if raiz not in destino.parents:
        raise ErrorCartera("La carpeta del cliente debe permanecer dentro de la ruta de datos.")
    proyecto = Path(__file__).resolve().parents[2]
    if proyecto == destino or proyecto in destino.parents:
        raise ErrorCartera("Elegí una ruta de datos fuera de la carpeta del proyecto.")
    return ruta


def _leer_excel(archivo):
    archivo = Path(archivo).expanduser()
    contenido_excel = archivo.read_bytes()
    punto = cargar_punto_partida(io.BytesIO(contenido_excel))
    origen = {"archivo": archivo.name, "sha256": hashlib.sha256(contenido_excel).hexdigest()}
    return punto, origen


def _contenido_base(punto, origen, ahora, anterior=None):
    contenido = dict(anterior or {})
    contenido.update(
        esquema_version=1,
        importado_en=ahora.isoformat(),
        origen=dict(contenido.get("origen", {}), **origen),
        posiciones=[asdict(posicion) for posicion in punto.posiciones],
        lotes=[dict(asdict(lote), fecha=lote.fecha.isoformat() if lote.fecha else None) for lote in punto.lotes],
    )
    return contenido


def _serializar(contenido):
    return (json.dumps(contenido, ensure_ascii=False, indent=2, allow_nan=False) + "\n").encode("utf-8")


def _escribir_temporal(carpeta, contenido):
    temporal = None
    try:
        with tempfile.NamedTemporaryFile(mode="wb", dir=carpeta, prefix=".cartera-",
                                         suffix=".tmp", delete=False) as salida:
            temporal = Path(salida.name)
            salida.write(contenido)
            salida.flush()
            os.fsync(salida.fileno())
        return temporal
    except BaseException:
        if temporal is not None:
            temporal.unlink(missing_ok=True)
        raise


def importar_cartera(datos, slug, archivo):
    """Valida antes de escribir y publica un JSON completo sin sobrescribir."""
    ruta = _ruta_cartera(datos, slug)
    if ruta.exists() or ruta.is_symlink():
        raise ErrorCartera("La cartera de {} ya existe; la base inicial no se reemplaza.".format(slug))
    punto, origen = _leer_excel(archivo)
    contenido = _contenido_base(punto, origen, datetime.now(ZoneInfo("America/Argentina/Buenos_Aires")))
    serializado = _serializar(contenido)
    ruta.parent.mkdir(parents=True, exist_ok=True)
    temporal = None
    try:
        temporal = _escribir_temporal(ruta.parent, serializado)
        # El enlace publica el archivo completo y falla si otra importación ganó.
        try:
            os.link(str(temporal), str(ruta))
        except FileExistsError:
            raise ErrorCartera("La cartera de {} ya existe; la base inicial no se reemplaza.".format(slug)) from None
    finally:
        if temporal is not None:
            temporal.unlink(missing_ok=True)
    return punto, contenido


def _huella_extractos(archivos):
    huella = hashlib.sha256()
    for archivo in archivos:
        nombre = archivo.name.encode("utf-8")
        contenido = archivo.read_bytes()
        huella.update(len(nombre).to_bytes(8, "big"))
        huella.update(nombre)
        huella.update(len(contenido).to_bytes(8, "big"))
        huella.update(contenido)
    return huella.hexdigest()


def _leer_especies(ruta):
    if ruta.is_symlink() or ruta.resolve().parent != ruta.parent.resolve():
        raise ErrorCartera("especies.json debe permanecer en la carpeta del cliente y no ser un enlace.")
    try:
        contenido = json.loads(ruta.read_text(encoding="utf-8"), parse_constant=_rechazar_constante)
    except FileNotFoundError:
        raise ErrorCartera("No existe especies.json en la carpeta del cliente.") from None
    except (OSError, ValueError, UnicodeError):
        raise ErrorCartera("especies.json no es un JSON válido.") from None
    if not isinstance(contenido, dict):
        raise ErrorCartera("especies.json debe contener un objeto por ticker.")
    return contenido


def _movimientos_posteriores(ruta):
    if not ruta.exists():
        return False
    if ruta.is_symlink() or ruta.resolve().parent != ruta.parent.resolve() or not ruta.is_file():
        raise ErrorCartera("movimientos.csv debe permanecer en la carpeta del cliente y no ser un enlace.")
    try:
        lineas = [linea for linea in ruta.read_text(encoding="utf-8-sig").splitlines() if linea.strip()]
    except (OSError, UnicodeError):
        raise ErrorCartera("No se puede leer movimientos.csv antes de reemplazar la base.") from None
    return len(lineas) > 1


def _publicar_base_derivada(ruta, serializado, reemplazar):
    """Publica la base completa y, al reemplazar, conserva los bytes previos."""
    ruta.parent.mkdir(parents=True, exist_ok=True)
    temporal_nuevo = temporal_historial = None
    if not ruta.exists():
        try:
            temporal_nuevo = _escribir_temporal(ruta.parent, serializado)
            try:
                os.link(str(temporal_nuevo), str(ruta))
            except FileExistsError:
                raise ErrorCartera("cartera.json ya existe; usá --reemplazar para derivarla nuevamente.") from None
        finally:
            if temporal_nuevo is not None:
                temporal_nuevo.unlink(missing_ok=True)
        return
    if not reemplazar:
        raise ErrorCartera("cartera.json ya existe; usá --reemplazar para derivarla nuevamente.")
    anterior = ruta.read_bytes()
    ahora = datetime.now(ZoneInfo("America/Argentina/Buenos_Aires"))
    carpeta_historial = ruta.parent / "historial_cartera"
    if carpeta_historial.is_symlink() or carpeta_historial.resolve().parent != ruta.parent.resolve():
        raise ErrorCartera("historial_cartera debe permanecer en la carpeta del cliente.")
    nombre = "cartera_{}_{}.json".format(ahora.strftime("%Y%m%dT%H%M%S_%f"), uuid.uuid4().hex)
    respaldo = carpeta_historial / nombre
    try:
        temporal_nuevo = _escribir_temporal(ruta.parent, serializado)
        carpeta_historial.mkdir(exist_ok=True)
        temporal_historial = _escribir_temporal(carpeta_historial, anterior)
        os.link(str(temporal_historial), str(respaldo))
        temporal_historial.unlink()
        temporal_historial = None
        os.replace(str(temporal_nuevo), str(ruta))
        temporal_nuevo = None
    finally:
        if temporal_nuevo is not None:
            temporal_nuevo.unlink(missing_ok=True)
        if temporal_historial is not None:
            temporal_historial.unlink(missing_ok=True)


def derivar_base(datos, slug, reemplazar=False):
    """Deriva la base inicial de los lotes FIFO abiertos del historial completo."""
    from .historial import ErrorHistorial, _archivos_extractos, _construir_desde_archivos

    ruta = _ruta_cartera(datos, slug)
    if ruta.is_symlink():
        raise ErrorCartera("cartera.json no puede ser un enlace.")
    existe = ruta.exists()
    if existe and not reemplazar:
        raise ErrorCartera("cartera.json ya existe; usá --reemplazar para derivarla nuevamente.")
    if existe and reemplazar:
        if (ruta.parent / "dia_cero.json").exists():
            raise ErrorCartera("No se puede reemplazar la base porque ya existe un día cero.")
        if _movimientos_posteriores(ruta.parent / "movimientos.csv"):
            raise ErrorCartera("No se puede reemplazar la base porque movimientos.csv ya contiene movimientos posteriores.")

    especies = _leer_especies(ruta.parent / "especies.json")
    historial, _ = _construir_desde_archivos(ruta.parent)
    problemas = []
    faltantes = {}
    for realizado in historial.realizados:
        if realizado.cantidad_sin_lote > 0:
            faltantes[realizado.ticker] = faltantes.get(realizado.ticker, Decimal(0)) + Decimal(str(realizado.cantidad_sin_lote))
    for ticker, cantidad in sorted(faltantes.items()):
        problemas.append("{}: historia incompleta; faltan lotes para {} unidades vendidas o cerradas.".format(ticker, cantidad))
    for fila in historial.sin_clasificar:
        if abs(float(fila.get("cantidad", 0))) > 0:
            problemas.append("Movimiento sin clasificar con cantidad: {}.".format(
                fila.get("referencia") or fila.get("comprobante") or fila.get("numero", "sin referencia")))
    if not historial.lotes:
        problemas.append("El historial no deja ningún lote abierto para derivar la base.")

    unidades = {"cedear": 1, "accion": 1, "bono": 100, "on": 100, "letra": 100}
    abiertos = []
    vistos = set()
    for lote in historial.lotes:
        if lote.ticker not in vistos:
            abiertos.append(lote.ticker)
            vistos.add(lote.ticker)
    definiciones = {}
    for ticker in abiertos:
        definicion = especies.get(ticker)
        if not isinstance(definicion, dict):
            problemas.append("{}: falta en especies.json.".format(ticker))
            continue
        especie, tipo = definicion.get("especie"), definicion.get("tipo")
        if not isinstance(especie, str) or not especie.strip() or tipo not in unidades:
            problemas.append("{}: especie o tipo inválido en especies.json.".format(ticker))
            continue
        definiciones[ticker] = (especie.strip(), tipo, unidades[tipo])
    if problemas:
        raise ErrorHistorial(problemas)

    posiciones, lotes = [], []
    for ticker in abiertos:
        especie, tipo, cotiza_cada = definiciones[ticker]
        propios = [lote for lote in historial.lotes if lote.ticker == ticker]
        cantidad = float(sum((Decimal(str(lote.cantidad)) for lote in propios), Decimal(0)))
        posiciones.append(Posicion(ticker, especie, tipo, cantidad, cotiza_cada))
        for lote in propios:
            if lote.costo is None:
                lotes.append(Lote(ticker, lote.cantidad, "pendiente", lote.fecha, None, None, lote.nota))
            else:
                precio = float(Decimal(str(lote.costo)) / Decimal(str(lote.cantidad)) * Decimal(cotiza_cada))
                if not math.isfinite(precio) or precio <= 0 or lote.costo <= 0:
                    raise ErrorHistorial("{}: un lote abierto tiene costo no positivo o fuera de rango.".format(ticker))
                lotes.append(Lote(ticker, lote.cantidad, lote.origen, lote.fecha, precio, lote.costo, lote.nota))
    punto = PuntoPartida(posiciones=posiciones, lotes=lotes)
    archivos = _archivos_extractos(ruta.parent)
    origen = {"archivo": "extractos", "sha256": _huella_extractos(archivos)}
    contenido = _contenido_base(punto, origen, datetime.now(ZoneInfo("America/Argentina/Buenos_Aires")))
    serializado = _serializar(contenido)
    _publicar_base_derivada(ruta, serializado, reemplazar)
    return punto, contenido


def _positivo(valor):
    return isinstance(valor, (int, float)) and not isinstance(valor, bool) and math.isfinite(valor) and valor > 0


def _rechazar_constante(texto):
    raise ValueError("Número no finito: " + texto)


def cargar_cartera(datos, slug):
    """Lee la base versionada sin consultar precios ni modificar archivos."""
    ruta = _ruta_cartera(datos, slug)
    try:
        serializado = ruta.read_bytes()
    except FileNotFoundError:
        raise ErrorCartera("No existe una cartera importada para {}.".format(slug)) from None
    return _deserializar_base(serializado)


def _deserializar_base(serializado):
    try:
        contenido = json.loads(serializado.decode("utf-8"), parse_constant=_rechazar_constante)
    except (ValueError, UnicodeError):
        raise ErrorCartera("cartera.json no es un JSON válido; no se modificó la base.") from None
    try:
        punto = _reconstruir(contenido)
    except ErrorCartera:
        raise
    except (ValueError, TypeError, KeyError, AttributeError, OverflowError):
        raise ErrorCartera("cartera.json tiene un formato o datos inválidos; no se modificó la base.") from None
    return punto, contenido


def _clave_lote(lote):
    return (lote.ticker, lote.cantidad, lote.origen, lote.fecha, lote.precio, lote.costo, lote.nota)


def _comparar_posiciones(anterior, nuevo):
    previas = {posicion.ticker: posicion for posicion in anterior.posiciones}
    nuevas = {posicion.ticker: posicion for posicion in nuevo.posiciones}
    errores = []
    for ticker in sorted(previas.keys() - nuevas.keys()):
        errores.append("{}: falta una especie presente en la base.".format(ticker))
    for ticker in sorted(nuevas.keys() - previas.keys()):
        errores.append("{}: no se permite agregar una especie a la base al actualizar costos.".format(ticker))
    for ticker in sorted(previas.keys() & nuevas.keys()):
        for campo in ("especie", "tipo", "cotiza_cada", "cantidad"):
            if getattr(previas[ticker], campo) != getattr(nuevas[ticker], campo):
                errores.append("{}: {} no coincide con la base; actualizar-costos solo corrige lotes.".format(ticker, campo))
    if errores:
        raise ErrorCartera("\n".join(errores))


def _resumir_cambios(anterior, nuevo):
    cambios, advertencias = [], []
    for posicion in anterior.posiciones:
        ticker = posicion.ticker
        previos = [lote for lote in anterior.lotes if lote.ticker == ticker]
        nuevos = [lote for lote in nuevo.lotes if lote.ticker == ticker]
        if Counter(map(_clave_lote, previos)) == Counter(map(_clave_lote, nuevos)):
            continue
        cambios.append({
            "ticker": ticker,
            "costo_anterior": costo_total(previos),
            "costo_nuevo": costo_total(nuevos),
            "origen_anterior": estado_costo(previos),
            "origen_nuevo": estado_costo(nuevos),
        })
        # Sin ID de lote, no inferir continuidad por fila ni por costo total.
        # La fecha y cantidad permiten advertir también ante reorganizaciones.
        clave_extracto = lambda lote: (lote.cantidad, lote.fecha, lote.costo)
        extractos_previos = Counter(clave_extracto(lote) for lote in previos if lote.origen == "extracto")
        extractos_nuevos = Counter(clave_extracto(lote) for lote in nuevos if lote.origen == "extracto")
        reales_detalle_antes = Counter(_clave_lote(lote) for lote in previos if lote.origen == "extracto")
        reales_detalle_despues = Counter(_clave_lote(lote) for lote in nuevos if lote.origen == "extracto")
        otros_antes = Counter(_clave_lote(lote) for lote in previos if lote.origen != "extracto")
        otros_despues = Counter(_clave_lote(lote) for lote in nuevos if lote.origen != "extracto")
        # También advertir si cambia la distribución de orígenes entre lotes de
        # igual cantidad/fecha/costo pero notas distintas: no tienen ID estable.
        ambiguo = reales_detalle_antes != reales_detalle_despues and otros_antes != otros_despues
        if extractos_previos - extractos_nuevos or ambiguo:
            advertencias.append(
                "ADVERTENCIA {}: se modificaron o reorganizaron lotes de extracto; "
                "revisá su costo y origen, también ante cambios ambiguos entre lotes. "
                "La versión anterior se conserva en el historial.".format(ticker)
            )
        estimados_antes = Counter(_clave_lote(lote) for lote in previos if lote.origen == "estimado")
        estimados_despues = Counter(_clave_lote(lote) for lote in nuevos if lote.origen == "estimado")
        pendientes_antes = Counter(_clave_lote(lote) for lote in previos if lote.origen == "pendiente")
        pendientes_despues = Counter(_clave_lote(lote) for lote in nuevos if lote.origen == "pendiente")
        if estimados_antes - estimados_despues and pendientes_despues - pendientes_antes:
            advertencias.append(
                "ADVERTENCIA {}: un lote estimado pudo volver a pendiente; "
                "revisá si se usó un Excel viejo y se perdió una estimación.".format(ticker)
            )
    return cambios, advertencias


def _verificar_version(ruta, entrada, serializado):
    actual = ruta.stat()
    abierta = os.fstat(entrada.fileno())
    if (actual.st_dev, actual.st_ino) != (abierta.st_dev, abierta.st_ino) or ruta.read_bytes() != serializado:
        raise ErrorCartera("La base cambió durante la actualización; volvé a intentar con la versión actual.")


def actualizar_costos(datos, slug, archivo):
    """Corrige lotes sin cambiar posiciones; respalda bytes previos antes del commit."""
    ruta = _ruta_cartera(datos, slug)
    if ruta.is_symlink():
        raise ErrorCartera("cartera.json no puede ser un enlace al actualizar costos.")
    try:
        entrada = ruta.open("rb")
    except FileNotFoundError:
        raise ErrorCartera("No existe una cartera importada para {}.".format(slug)) from None
    with entrada:
        # No se crea un archivo de lock: un intento inválido o sin cambios no escribe.
        fcntl.flock(entrada.fileno(), fcntl.LOCK_EX)
        serializado_anterior = entrada.read()
        _verificar_version(ruta, entrada, serializado_anterior)
        anterior, contenido_anterior = _deserializar_base(serializado_anterior)
        nuevo, origen = _leer_excel(archivo)
        _comparar_posiciones(anterior, nuevo)
        cambios, advertencias = _resumir_cambios(anterior, nuevo)
        if not cambios:
            return {"cambios": [], "advertencias": [], "historial": None}
        # Se conserva el orden de posiciones de la base al corregir únicamente lotes.
        nuevo.posiciones = anterior.posiciones
        ahora = datetime.now(ZoneInfo("America/Argentina/Buenos_Aires"))
        contenido = _contenido_base(nuevo, origen, ahora, anterior=contenido_anterior)
        serializado_nuevo = _serializar(contenido)
        carpeta_historial = ruta.parent / "historial_cartera"
        if carpeta_historial.is_symlink():
            raise ErrorCartera("historial_cartera no puede ser un enlace a otra carpeta.")
        if carpeta_historial.resolve().parent != ruta.parent.resolve():
            raise ErrorCartera("El historial debe permanecer en la carpeta del cliente.")
        nombre = "cartera_{}_{}.json".format(ahora.strftime("%Y%m%dT%H%M%S_%f"), uuid.uuid4().hex)
        historial = carpeta_historial / nombre
        resultado = {"cambios": cambios, "advertencias": advertencias, "historial": historial}
        temporal_nuevo = temporal_historial = None
        try:
            temporal_nuevo = _escribir_temporal(ruta.parent, serializado_nuevo)
            carpeta_historial.mkdir(exist_ok=True)
            temporal_historial = _escribir_temporal(carpeta_historial, serializado_anterior)
            # Publicación exclusiva: nunca sobrescribir una versión histórica.
            os.link(str(temporal_historial), str(historial))
            temporal_historial.unlink()
            temporal_historial = None
            _verificar_version(ruta, entrada, serializado_anterior)
            # Única mutación de la base. Todos los controles y escrituras ya terminaron.
            os.replace(str(temporal_nuevo), str(ruta))
            temporal_nuevo = None
            return resultado
        finally:
            if temporal_nuevo is not None:
                temporal_nuevo.unlink(missing_ok=True)
            if temporal_historial is not None:
                temporal_historial.unlink(missing_ok=True)


def _reconstruir(contenido):
    if not isinstance(contenido, dict) or type(contenido.get("esquema_version")) is not int:
        raise ValueError("Versión ausente")
    if contenido["esquema_version"] != 1:
        raise ErrorCartera("Versión de cartera.json no compatible; no se modificó la base.")
    if datetime.fromisoformat(contenido["importado_en"]).utcoffset() is None:
        raise ValueError("Fecha sin zona horaria")
    origen = contenido["origen"]
    if not isinstance(origen["archivo"], str) or not origen["archivo"]:
        raise ValueError("Archivo ausente")
    if not re.fullmatch(r"[0-9a-f]{64}", origen["sha256"]):
        raise ValueError("Huella inválida")
    if not isinstance(contenido["posiciones"], list) or not contenido["posiciones"]:
        raise ValueError("Posiciones ausentes")
    if not isinstance(contenido["lotes"], list):
        raise ValueError("Lotes inválidos")
    posiciones = [Posicion(**registro) for registro in contenido["posiciones"]]
    por_ticker = {}
    unidades = {"cedear": 1, "accion": 1, "bono": 100, "on": 100, "letra": 100}
    for posicion in posiciones:
        if not isinstance(posicion.ticker, str) or not posicion.ticker.strip() or posicion.ticker in por_ticker:
            raise ValueError("Ticker inválido o repetido")
        if not isinstance(posicion.especie, str) or not _positivo(posicion.cantidad):
            raise ValueError("Posición inválida")
        if not _positivo(posicion.cotiza_cada) or unidades.get(posicion.tipo) != posicion.cotiza_cada:
            raise ValueError("Unidad inválida")
        por_ticker[posicion.ticker] = posicion
    lotes = []
    cantidades = {ticker: [] for ticker in por_ticker}
    for registro in contenido["lotes"]:
        atributos = dict(registro)
        atributos["fecha"] = date.fromisoformat(atributos["fecha"]) if atributos["fecha"] is not None else None
        lote = Lote(**atributos)
        if lote.ticker not in por_ticker or not _positivo(lote.cantidad) or not isinstance(lote.nota, str):
            raise ValueError("Lote inválido")
        if lote.origen == "pendiente":
            if lote.precio is not None or lote.costo is not None:
                raise ValueError("Costo pendiente con importe")
        elif lote.origen in ("extracto", "estimado"):
            if not _positivo(lote.precio) or not _positivo(lote.costo):
                raise ValueError("Costo inválido")
            if lote.origen == "estimado" and lote.fecha is None:
                raise ValueError("Estimación sin fecha")
            esperado = lote.cantidad * lote.precio / por_ticker[lote.ticker].cotiza_cada
            if not math.isclose(lote.costo, esperado, rel_tol=1e-10, abs_tol=1e-8):
                raise ValueError("Costo inconsistente")
        else:
            raise ValueError("Origen desconocido")
        cantidades[lote.ticker].append(lote.cantidad)
        lotes.append(lote)
    for ticker, valores in cantidades.items():
        suma = sum((Decimal(str(valor)) for valor in valores), Decimal(0))
        if not valores or abs(suma - Decimal(str(por_ticker[ticker].cantidad))) > Decimal("0.5"):
            raise ValueError("Cantidades inconsistentes")
    return PuntoPartida(posiciones=posiciones, lotes=lotes)
