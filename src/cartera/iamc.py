"""Adquisición y archivo local de los cierres diarios de IAMC/BYMA."""

import copy
import fcntl
import hashlib
from html.parser import HTMLParser
import json
import math
import os
from pathlib import Path
import re
import tempfile
from datetime import date, datetime
from urllib.error import HTTPError
from urllib.parse import urljoin, urlparse
from urllib.request import Request, urlopen
from urllib.robotparser import RobotFileParser
from zoneinfo import ZoneInfo


URL = "https://www.iamc.com.ar/informediario/"
ROBOTS = "https://www.iamc.com.ar/robots.txt"
AGENTE = "cartera-fuente-iamc-relevamiento/0.1"
MAX_BYTES = 10_000_000


class ErrorExtraccion(ValueError):
    """El cierre no puede extraerse o no corresponde repetir una descarga."""


def _pares(pares):
    objeto = {}
    for clave, valor in pares:
        if clave in objeto:
            raise ErrorExtraccion("Clave JSON repetida: " + clave)
        objeto[clave] = valor
    return objeto


def _constante(texto):
    raise ErrorExtraccion("Número JSON no finito: " + texto)


def _finitos(valor):
    if isinstance(valor, float) and not math.isfinite(valor):
        raise ErrorExtraccion("El JSON contiene un número fuera de rango finito.")
    if isinstance(valor, dict):
        for dato in valor.values():
            _finitos(dato)
    elif isinstance(valor, list):
        for dato in valor:
            _finitos(dato)


def _json(texto):
    try:
        valor = json.loads(texto, object_pairs_hook=_pares, parse_constant=_constante)
    except (ValueError, TypeError, RecursionError) as error:
        raise ErrorExtraccion("JSON inválido: " + str(error)) from None
    _finitos(valor)
    return valor


class _Payload(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=False)
        self.capturando = False
        self.cantidad = 0
        self.fragmentos = []

    def handle_starttag(self, etiqueta, atributos):
        if etiqueta.lower() != "script":
            return
        atributos = dict(atributos)
        if atributos.get("id") == "payload":
            self.cantidad += 1
            if atributos.get("type", "").lower() != "application/json":
                raise ErrorExtraccion("script#payload no tiene tipo application/json.")
            self.capturando = True

    def handle_endtag(self, etiqueta):
        if etiqueta.lower() == "script":
            self.capturando = False

    def handle_data(self, texto):
        if self.capturando:
            self.fragmentos.append(texto)


def _fecha_iso(valor, nombre):
    if not isinstance(valor, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", valor):
        raise ErrorExtraccion(nombre + " debe ser una fecha AAAA-MM-DD.")
    try:
        return date.fromisoformat(valor).isoformat()
    except ValueError:
        raise ErrorExtraccion(nombre + " no es una fecha válida.") from None


def _objeto(valor, nombre):
    if not isinstance(valor, dict):
        raise ErrorExtraccion(nombre + " debe ser un objeto JSON.")
    return valor


def _registros(valor, nombre):
    if not isinstance(valor, list):
        raise ErrorExtraccion(nombre + " debe ser una lista JSON.")
    vistos = set()
    for numero, registro in enumerate(valor, 1):
        if not isinstance(registro, dict) or not isinstance(registro.get("tk"), str) or not registro["tk"]:
            raise ErrorExtraccion("{}: registro {} sin ticker válido.".format(nombre, numero))
        if registro["tk"] in vistos:
            raise ErrorExtraccion(nombre + ": ticker repetido " + registro["tk"])
        vistos.add(registro["tk"])
    return valor


def extraer_html(contenido, *, max_bytes=None):
    """Extrae exclusivamente el payload publicado y conserva sus secciones crudas.

    No sigue rutas diferidas ni interpreta flujos, rendimientos o monedas. Las
    unidades y fórmulas se relevan separadamente en docs/FUENTE_IAMC.md.
    """
    if isinstance(contenido, str):
        contenido = contenido.encode("utf-8")
    limite = MAX_BYTES if max_bytes is None else max_bytes
    if not isinstance(contenido, bytes) or len(contenido) > limite:
        raise ErrorExtraccion("Se esperaba un HTML de hasta {} bytes.".format(limite))
    try:
        texto = contenido.decode("utf-8-sig")
    except UnicodeError:
        raise ErrorExtraccion("El HTML no es UTF-8 válido.") from None
    lector = _Payload()
    try:
        lector.feed(texto)
        lector.close()
    except (ValueError, RecursionError) as error:
        raise ErrorExtraccion("No se pudo leer el HTML: " + str(error)) from None
    if lector.cantidad != 1 or lector.capturando:
        raise ErrorExtraccion("Se requiere un único script#payload application/json completo.")
    payload_texto = "".join(lector.fragmentos)
    datos = _objeto(_json(payload_texto), "payload")
    for clave in ("tp", "on", "calc", "macro"):
        _objeto(datos.get(clave), "payload." + clave)
    cierre = _fecha_iso(datos["tp"].get("fecha"), "tp.fecha")
    if _fecha_iso(datos["on"].get("fecha"), "on.fecha") != cierre:
        raise ErrorExtraccion("Los títulos públicos y las ON tienen fechas de cierre diferentes.")
    liquidacion = _fecha_iso(datos["calc"].get("liq"), "calc.liq")
    for clave in ("tp", "on"):
        if _fecha_iso(datos[clave].get("fecha_liq"), clave + ".fecha_liq") != liquidacion:
            raise ErrorExtraccion("La liquidación de {} no coincide con la calculadora.".format(clave))
    _registros(datos["calc"].get("ins"), "calc.ins")
    _registros(datos["tp"].get("rows"), "tp.rows")
    _registros(datos["on"].get("rows"), "on.rows")
    if not isinstance(datos["macro"].get("vars"), list):
        raise ErrorExtraccion("macro.vars debe ser una lista.")
    if not isinstance(datos.get("cat", []), list):
        raise ErrorExtraccion("cat debe ser una lista si está presente.")
    diferidos = _objeto(datos.get("__dif", {}), "__dif")
    avisos = []
    padron = copy.deepcopy(datos.get("ins"))
    if padron is not None:
        _objeto(padron, "ins")
        _fecha_iso(padron.get("fecha"), "ins.fecha")
        if not isinstance(padron.get("rows"), list):
            raise ErrorExtraccion("ins.rows debe ser una lista.")
    ruta_padron = diferidos.get("ins")
    if ruta_padron is not None and not isinstance(ruta_padron, str):
        raise ErrorExtraccion("La ruta diferida ins debe ser texto.")
    if ruta_padron:
        url_padron = urljoin(URL, ruta_padron)
        if urlparse(url_padron).scheme != "https" or urlparse(url_padron).hostname != "www.iamc.com.ar":
            raise ErrorExtraccion("La ruta diferida del padrón sale del origen HTTPS esperado.")
        avisos.append("El padrón completo requiere carga diferida; no se descargó ni se presenta como completo.")
    else:
        url_padron = None
    if not datos["calc"]["ins"]:
        avisos.append("La calculadora de bonos no trae instrumentos; no se completan con ceros.")
    letras = [copy.deepcopy(fila) for fila in datos["tp"]["rows"] if fila.get("seg") == "lec"]
    tickers_letras = {fila["tk"] for fila in letras}
    calculadoras_letras = [copy.deepcopy(fila) for fila in datos["calc"]["ins"] if fila["tk"] in tickers_letras]
    sin_calculadora = sorted(tickers_letras - {fila["tk"] for fila in calculadoras_letras})
    if sin_calculadora:
        avisos.append("Letras sin registro en calc.ins: {}. No se completa su valor final.".format(", ".join(sin_calculadora)))
    if not letras:
        avisos.append("No hay instrumentos seg=lec en este cierre.")
    return {
        "esquema_version": 1,
        "fecha_cierre": cierre,
        "fecha_liquidacion": liquidacion,
        "calculadora_bonos": copy.deepcopy(datos["calc"]),
        "calculadora_letras": {"fecha": cierre, "fecha_liquidacion": liquidacion,
                               "origen": "payload.tp.rows[seg=lec]", "instrumentos": letras,
                               "registros_calculadora": calculadoras_letras},
        "macro": copy.deepcopy(datos["macro"]),
        "catalogo": copy.deepcopy(datos.get("cat", [])),
        "padron": {"crudo": padron, "pendiente_url": url_padron,
                   "estado": "pendiente_carga_diferida" if url_padron else "embebido" if padron is not None else "ausente"},
        "informes": {"titulos_publicos": copy.deepcopy(datos["tp"]), "on": copy.deepcopy(datos["on"])},
        "caucion": {"mercado_dinero": copy.deepcopy(datos.get("din")),
                    "calculadora": copy.deepcopy(datos.get("ccau"))},
        "metadatos": {"fuente_url": URL, "html_sha256": hashlib.sha256(contenido).hexdigest(),
                      "payload_sha256": hashlib.sha256(payload_texto.encode("utf-8")).hexdigest(),
                      "rutas_diferidas_declaradas": copy.deepcopy(diferidos),
                      "caracter": "relevamiento experimental; no apto para producción sin revisión",
                      "avisos": avisos},
    }


def _bytes_json(contenido):
    return (json.dumps(contenido, ensure_ascii=False, indent=2, allow_nan=False) + "\n").encode("utf-8")


def _publicar(ruta, contenido):
    """Publicación atómica; el archivo anterior sobrevive a un fallo de reemplazo."""
    ruta = Path(ruta)
    if ruta.is_symlink():
        raise ErrorExtraccion("No se publica sobre un enlace: " + str(ruta))
    ruta.parent.mkdir(parents=True, exist_ok=True)
    if ruta.exists() and ruta.read_bytes() == contenido:
        return False
    temporal = None
    try:
        with tempfile.NamedTemporaryFile(mode="wb", dir=ruta.parent, prefix=".iamc-", delete=False) as salida:
            temporal = Path(salida.name)
            os.fchmod(salida.fileno(), 0o600)
            salida.write(contenido)
            salida.flush()
            os.fsync(salida.fileno())
        if ruta.is_symlink():
            raise ErrorExtraccion("El destino pasó a ser un enlace.")
        os.replace(str(temporal), str(ruta))
        return True
    finally:
        if temporal is not None:
            temporal.unlink(missing_ok=True)


def guardar_cierre(datos, salida):
    """Guarda un JSON por fecha de cierre, preservando los números de la fuente."""
    fecha = _fecha_iso(datos.get("fecha_cierre"), "fecha_cierre")
    ruta = Path(salida) / (fecha + ".json")
    _publicar(ruta, _bytes_json(datos))
    return ruta


def _obtener_url(url, espera=30):
    request = Request(url, headers={"User-Agent": AGENTE, "Accept-Encoding": "identity"})
    try:
        respuesta = urlopen(request, timeout=espera)
    except HTTPError as error:
        respuesta = error
    with respuesta:
        final = respuesta.geturl()
        if urlparse(final).scheme != "https" or urlparse(final).hostname != "www.iamc.com.ar":
            raise ErrorExtraccion("La respuesta redirige fuera del origen HTTPS permitido.")
        cuerpo = respuesta.read(MAX_BYTES + 1)
        if len(cuerpo) > MAX_BYTES:
            raise ErrorExtraccion("La respuesta supera el tamaño máximo de prueba.")
        return cuerpo, {"estado_http": respuesta.status, "url_final": final, "headers": dict(respuesta.headers)}


def _revisar_robots(cuerpo, meta):
    estado = meta["estado_http"]
    if estado in (404, 410):
        return "robots.txt no disponible (HTTP {}). No equivale a permiso de uso.".format(estado)
    if estado != 200:
        raise ErrorExtraccion("No se descargó el cierre: robots.txt devolvió HTTP {}.".format(estado))
    try:
        texto = cuerpo.decode("utf-8-sig")
    except UnicodeError:
        raise ErrorExtraccion("robots.txt no puede interpretarse como UTF-8.") from None
    tipo = str(meta.get("headers", {}).get("Content-Type", "")).lower()
    if "<html" in texto[:500].lower() or "<!doctype html" in texto[:500].lower() or "text/html" in tipo:
        return "robots.txt devuelve HTML, no reglas robots válidas. No se interpreta como autorización ni se buscan rutas alternativas."
    if not re.search(r"^\s*user-agent\s*:", texto, re.I | re.M):
        return "robots.txt no declara grupos User-agent; no se infiere autorización de uso."
    parser = RobotFileParser(ROBOTS)
    parser.parse(texto.splitlines())
    if not parser.can_fetch(AGENTE, URL):
        raise ErrorExtraccion("robots.txt prohíbe descargar el cierre para este agente.")
    return "robots.txt no prohíbe esta ruta para el agente; esto no sustituye los términos de uso."


def descargar_cierre(cache, hoy=None, fetch=None):
    """Una solicitud por URL y día argentino, sin reintentar fallos ese día.

    El registro de intento se persiste antes de cada solicitud. Así una caída o
    una respuesta inválida no termina en un bucle de descargas. No descarga los
    archivos diferidos ni consulta rutas históricas no documentadas.
    """
    hoy = hoy or datetime.now(ZoneInfo("America/Argentina/Buenos_Aires")).date()
    if type(hoy) is not date:
        raise ErrorExtraccion("hoy debe ser una fecha sin hora.")
    carpeta = Path(cache) / hoy.isoformat()
    carpeta.mkdir(parents=True, exist_ok=True)
    if carpeta.is_symlink():
        raise ErrorExtraccion("La carpeta de caché diaria no puede ser un enlace.")
    descriptor = os.open(str(carpeta), os.O_RDONLY)
    fetch = fetch or _obtener_url
    try:
        fcntl.flock(descriptor, fcntl.LOCK_EX)
        ruta_intentos = carpeta / "intentos.json"
        if ruta_intentos.is_symlink():
            raise ErrorExtraccion("El registro de intentos no puede ser un enlace.")
        intentos = _json(ruta_intentos.read_text(encoding="utf-8")) if ruta_intentos.exists() else {}
        _objeto(intentos, "Registro de intentos")
        avisos = []
        def recurso(url, nombre):
            ruta, ruta_meta = carpeta / nombre, carpeta / (nombre + ".http.json")
            if ruta.is_symlink() or ruta_meta.is_symlink():
                raise ErrorExtraccion("La caché no puede contener enlaces.")
            if ruta.exists() and ruta_meta.exists():
                cuerpo = ruta.read_bytes()
                meta = _objeto(_json(ruta_meta.read_text(encoding="utf-8")), "Metadatos de caché")
                if meta.get("url_solicitada") != url or meta.get("sha256") != hashlib.sha256(cuerpo).hexdigest():
                    raise ErrorExtraccion("La caché no coincide con su URL o huella; no se vuelve a descargar hoy.")
                return cuerpo, meta
            if ruta.exists() or ruta_meta.exists():
                raise ErrorExtraccion("La caché diaria está incompleta; no se repite la descarga de esa URL hoy.")
            if url in intentos:
                raise ErrorExtraccion("Ya hubo un intento de esta URL hoy; se evita una segunda descarga: " + url)
            intentos[url] = {"iniciado_en": datetime.now(ZoneInfo("America/Argentina/Buenos_Aires")).isoformat(), "estado": "iniciado"}
            _publicar(ruta_intentos, _bytes_json(intentos))
            try:
                cuerpo, recibido = fetch(url)
                if not isinstance(cuerpo, bytes) or len(cuerpo) > MAX_BYTES:
                    raise ErrorExtraccion("Respuesta fuera del tamaño o formato esperado.")
                meta = dict(recibido, url_solicitada=url,
                            consultado_en=intentos[url]["iniciado_en"], sha256=hashlib.sha256(cuerpo).hexdigest())
                _publicar(ruta, cuerpo)
                _publicar(ruta_meta, _bytes_json(meta))
                intentos[url]["estado"] = "recibido"
                _publicar(ruta_intentos, _bytes_json(intentos))
                return cuerpo, meta
            except Exception as error:
                intentos[url]["estado"] = "error"
                intentos[url]["error"] = str(error)
                _publicar(ruta_intentos, _bytes_json(intentos))
                raise
        robots, robots_meta = recurso(ROBOTS, "robots.txt")
        avisos.append(_revisar_robots(robots, robots_meta))
        cuerpo, meta = recurso(URL, "informediario.html")
        if meta.get("estado_http") != 200:
            raise ErrorExtraccion("El cierre devolvió HTTP {}.".format(meta.get("estado_http")))
        extraer_html(cuerpo)  # Rechazar HTML/JSON vacío antes de informar éxito.
        return cuerpo, dict(meta, robots_avisos=avisos)
    finally:
        os.close(descriptor)


def _carpeta_iamc(datos):
    raiz = Path(datos).expanduser().resolve()
    proyecto = Path(__file__).resolve().parents[2]
    if raiz == proyecto or proyecto in raiz.parents:
        raise ErrorExtraccion("Elegí una ruta de datos fuera de la carpeta del proyecto.")
    carpeta = raiz / "iamc"
    if carpeta.is_symlink() or any((carpeta / parte).is_symlink() for parte in ("cierres", "cache")):
        raise ErrorExtraccion("Las carpetas de IAMC no pueden ser enlaces.")
    return carpeta


def leer_cierres(datos):
    """Carga los cronogramas archivados, en orden de fecha de mercado."""
    carpeta = _carpeta_iamc(datos) / "cierres"
    if carpeta.exists() and not carpeta.is_dir():
        raise ErrorExtraccion("iamc/cierres debe ser una carpeta.")
    cierres = []
    for ruta in sorted(carpeta.glob("*.json")):
        try:
            if ruta.is_symlink() or not ruta.is_file():
                raise ErrorExtraccion("El cierre debe ser un archivo y no un enlace.")
            cierre = _objeto(_json(ruta.read_text(encoding="utf-8")), "cierre")
            fecha = _fecha_iso(cierre.get("fecha_cierre"), "fecha_cierre")
            if ruta.stem != fecha:
                raise ErrorExtraccion("La fecha del archivo difiere de fecha_cierre.")
            liquidacion = _fecha_iso(cierre.get("fecha_liquidacion"), "fecha_liquidacion")
            calculadora = _objeto(cierre.get("calculadora_bonos"), "calculadora_bonos")
            if liquidacion < fecha or calculadora.get("liq") != liquidacion:
                raise ErrorExtraccion("Las fechas de cierre y liquidación son inconsistentes.")
            _registros(calculadora.get("ins"), "calculadora_bonos.ins")
        except (ValueError, OSError) as error:
            raise ErrorExtraccion("{}: {}".format(ruta.name, error)) from None
        # Solo se conserva lo que necesita el flujo. Los informes completos
        # y sus series históricas siguen archivados en cada JSON.
        cierres.append({"fecha_cierre": fecha, "fecha_liquidacion": liquidacion,
                        "calculadora_bonos": calculadora})
    return cierres


def procesar_cierre(archivo=None, *, cache=None, hoy=None, fetch=None):
    """Prepara el cierre y su procedencia a partir de un HTML local o la caché."""
    if archivo is None:
        cuerpo, meta = descargar_cierre(cache, hoy=hoy, fetch=fetch)
    else:
        archivo = Path(archivo).expanduser()
        cuerpo = archivo.read_bytes()
        meta = {"modo": "archivo_local", "html_origen": str(archivo.resolve()), "consulta_red": False}
        ruta_meta = archivo.with_name(archivo.name + ".http.json")
        if ruta_meta.exists():
            http = _objeto(_json(ruta_meta.read_text(encoding="utf-8")), "Metadatos HTTP locales")
            if http.get("sha256") != hashlib.sha256(cuerpo).hexdigest():
                raise ErrorExtraccion("Los metadatos HTTP locales no coinciden con la huella del HTML.")
            meta["http_guardado"] = http
    cierre = extraer_html(cuerpo)
    cierre["metadatos"]["adquisicion"] = meta
    return cierre


def _archivar(datos, archivo=None, fetch=None):
    """Guarda el cierre publicado y dice si esa fecha de cierre era nueva."""
    carpeta = _carpeta_iamc(datos)
    cierre = procesar_cierre(archivo, cache=carpeta / "cache", fetch=fetch)
    cierre["metadatos"]["caracter"] = "cierre IAMC para cronogramas de tasa fija"
    destino = carpeta / "cierres" / (cierre["fecha_cierre"] + ".json")
    if archivo is not None:
        origen = Path(archivo).expanduser()
        if origen.resolve() == destino.resolve() or (destino.exists() and destino.samefile(origen)):
            raise ErrorExtraccion("El cierre JSON no puede sobrescribir el HTML de origen.")
    nuevo = not destino.exists()
    return cierre, guardar_cierre(cierre, destino.parent), nuevo


def guardar_cierre_del_dia(datos, fetch=None):
    """Para el comando dashboard: archiva el cierre publicado sin interrumpirlo.

    Solo actúa en una carpeta de datos que ya usa IAMC, es decir, que tiene
    algún cierre guardado. Conserva la regla de un intento por día: en el
    mismo día vuelve a leer la caché, sin otra consulta. Devuelve
    `(mensaje, aviso)`; un error nunca se propaga, queda en el aviso.
    """
    try:
        if not any((_carpeta_iamc(datos) / "cierres").glob("*.json")):
            return None, None
        cierre, _, nuevo = _archivar(datos, fetch=fetch or (lambda url: _obtener_url(url, espera=10)))
    except Exception as error:  # Un paso auxiliar no puede impedir el dashboard.
        return None, ("No se pudo guardar el cierre de IAMC de hoy: {} "
                      "Se usa el último cierre guardado.".format(str(error).rstrip(".") + "."))
    return ("Cierre IAMC {} guardado.".format(cierre["fecha_cierre"]) if nuevo else None), None


def ejecutar_iamc(datos, archivo=None):
    cierre, ruta, _ = _archivar(datos, archivo)
    print("Cierre IAMC {} guardado en {}.".format(cierre["fecha_cierre"], ruta))
    for aviso in cierre["metadatos"]["avisos"] + cierre["metadatos"]["adquisicion"].get("robots_avisos", []):
        print("ADVERTENCIA: " + aviso)
    return 0
