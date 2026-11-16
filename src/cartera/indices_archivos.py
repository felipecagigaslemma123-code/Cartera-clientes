"""Actualización y lectura de las fuentes macroeconómicas compartidas."""

from datetime import date, timedelta
from decimal import Decimal, DecimalException
from html.parser import HTMLParser
from io import BytesIO
import json
import os
from pathlib import Path
from tempfile import NamedTemporaryFile
from urllib.error import HTTPError
from urllib.parse import urljoin, urlparse
from urllib.request import Request, urlopen
from zipfile import BadZipFile

from .indices import Valor, _guardar, _mes, extraer, leer_rem, serie_bcra
from .letras import _hoy_argentina

_PAGINA_REM = "https://www.bcra.gob.ar/relevamiento-expectativas-mercado-rem/"
_ARCHIVOS_REM = "https://www.bcra.gob.ar/archivos/Pdfs/PublicacionesEstadisticas/informes/"
_NOMBRE_REM = "relevamiento-expectativas-mercado-tablas-{}.xlsx"
_ERRORES = (ValueError, OSError, KeyError, TypeError, DecimalException, BadZipFile)


class _Enlaces(HTMLParser):
    def __init__(self):
        super().__init__()
        self.rutas = []

    def handle_starttag(self, tag, attrs):
        if tag == "a":
            ruta = dict(attrs).get("href")
            if ruta:
                self.rutas.append(urljoin(_PAGINA_REM, ruta))


def _descargar(url):
    solicitud = Request(url, headers={"User-Agent": "cartera/0.2"})
    limite = 8 * 1024 * 1024
    with urlopen(solicitud, timeout=10) as respuesta:
        contenido = respuesta.read(limite + 1)
    if len(contenido) > limite:
        raise ValueError("La descarga del REM supera el tamaño permitido.")
    return contenido


def _archivos(carpeta, extension, hoy, mensual=False):
    encontrados = []
    for ruta in carpeta.glob("*" + extension):
        try:
            fecha = date.fromisoformat(ruta.stem + "-01" if mensual else ruta.stem)
        except ValueError:
            continue
        if fecha <= hoy and ruta.is_file() and not ruta.is_symlink():
            encontrados.append((fecha, ruta))
    return sorted(encontrados, reverse=True)


def _bajar_rem(carpeta, hoy):
    esperado = _mes(hoy, -1)
    disponibles = _archivos(carpeta, ".xlsx", esperado, mensual=True)
    ultimo = disponibles[0][0] if disponibles else date.min
    if ultimo == esperado:
        return
    mes = esperado.isoformat()[:7]
    nombre = _NOMBRE_REM.format(mes)
    try:
        contenido = _descargar(_ARCHIVOS_REM + nombre)
    except HTTPError as error:
        if error.code not in (404, 410):
            raise
        pagina = _Enlaces()
        pagina.feed(_descargar(_PAGINA_REM).decode("utf-8"))
        opciones = []
        for enlace in pagina.rutas:
            url = urlparse(enlace)
            archivo = url.path.rsplit("/", 1)[-1]
            if (url.scheme != "https" or url.hostname not in ("bcra.gob.ar", "www.bcra.gob.ar")
                    or not archivo.startswith(_NOMBRE_REM.split("{}")[0]) or not archivo.endswith(".xlsx")):
                continue
            try:
                fecha = date.fromisoformat(archivo[-12:-5] + "-01")
            except ValueError:
                continue
            if ultimo < fecha <= esperado:
                opciones.append((fecha, enlace))
        if not opciones:
            raise ValueError("No figura un REM más reciente que el guardado.")
        esperado, enlace = max(opciones)
        contenido = _descargar(enlace)
    if leer_rem(BytesIO(contenido)).mes != esperado:
        raise ValueError("El mes del Excel del REM no coincide con el de la descarga.")
    carpeta.mkdir(parents=True, exist_ok=True)
    temporal = None
    try:
        with NamedTemporaryFile(dir=carpeta, delete=False) as archivo:
            temporal = Path(archivo.name)
            archivo.write(contenido)
        os.link(temporal, carpeta / (esperado.isoformat()[:7] + ".xlsx"))
    finally:
        if temporal is not None:
            temporal.unlink(missing_ok=True)


def actualizar_indices(datos, hoy=None, *, automatico=False):
    hoy = _hoy_argentina() if hoy is None else hoy
    raiz = Path(datos).expanduser() / "indices"
    bcra, rem = raiz / "bcra", raiz / "rem"
    captura = _archivos(bcra, ".json", hoy)
    meses = _archivos(rem, ".xlsx", _mes(hoy, -1), mensual=True)
    vence_bcra = not captura or (hoy - captura[0][0]).days > 7
    vence_rem = hoy.day > 10 and (not meses or meses[0][0] < _mes(hoy, -1))
    if automatico:
        if not (vence_bcra or vence_rem):
            return []
        intento = raiz / ("intento-" + hoy.isoformat())
        raiz.mkdir(parents=True, exist_ok=True)
        try:
            intento.touch(exist_ok=False)
        except FileExistsError:
            return []
    avisos = []
    if (vence_bcra or not automatico) and (not captura or captura[0][0] != hoy):
        try:
            hasta_cer = _mes(hoy, 1).replace(day=15)
            datos_bcra = extraer(date(hoy.year - 1, 1, 1), hoy, hasta_cer=hasta_cer)
            _guardar(datos_bcra, bcra / (hoy.isoformat() + ".json"))
        except FileExistsError:
            pass
        except _ERRORES as error:
            avisos.append("No se pudo actualizar el BCRA: {}.".format(error))
    if vence_rem or not automatico:
        try:
            _bajar_rem(rem, hoy)
        except FileExistsError:
            pass
        except _ERRORES as error:
            avisos.append("No se pudo actualizar el REM: {}.".format(error))
    return avisos


def _objeto(ruta):
    try:
        contenido = json.loads(ruta.read_text(encoding="utf-8"), parse_float=Decimal)
    except FileNotFoundError:
        return {}
    if not isinstance(contenido, dict):
        raise ValueError("{} debe contener un objeto JSON.".format(ruta.name))
    return contenido


def _supuestos(contenido, clave):
    supuestos = {}
    for mes, entrada in contenido.get(clave, {}).items():
        fecha = date.fromisoformat(mes + "-01")
        valor = Decimal(str(entrada))
        if not valor.is_finite() or (clave == "inflacion" and valor <= -1) or (clave == "a3500" and valor <= 0):
            raise ValueError("Supuesto inválido para {} en {}.".format(clave, mes))
        supuestos[fecha] = Valor(valor, "manual")
    return supuestos


def leer_indices(datos, hoy):
    datos = Path(datos).expanduser()
    raiz = datos / "indices"
    resultado = {"cer": {}, "a3500": {}, "tamar_tna": {}, "rem": None, "inflacion": {},
                 "tamar": {}, "tc": {}, "feriados": {}, "captura": None, "avisos": []}
    avisos = resultado["avisos"]
    for fecha, ruta in _archivos(raiz / "bcra", ".json", hoy):
        try:
            captura = _objeto(ruta)
            resultado.update({clave: serie_bcra(captura, clave) for clave in ("cer", "a3500", "tamar_tna")})
            resultado["captura"] = fecha
            break
        except _ERRORES as error:
            avisos.append("Captura del BCRA de {} inválida: {}.".format(fecha, error))
    for mes, ruta in _archivos(raiz / "rem", ".xlsx", _mes(hoy, -1), mensual=True):
        try:
            rem = leer_rem(ruta)
            if rem.mes != mes:
                raise ValueError("el mes del archivo no coincide con el contenido")
            resultado["rem"] = rem
            break
        except _ERRORES as error:
            avisos.append("REM de {} inválido: {}.".format(mes, error))
    try:
        contenido = _objeto(datos / "supuestos_manual.json")
        resultado.update(inflacion=_supuestos(contenido, "inflacion"),
                         tamar=_supuestos(contenido, "tamar"), tc=_supuestos(contenido, "a3500"))
    except _ERRORES + (AttributeError,) as error:
        avisos.append("No se pudieron leer los supuestos manuales: {}.".format(error))
    try:
        resultado["feriados"] = {
            anio: {date.fromisoformat(fecha) for fecha in fechas}
            for anio, fechas in _objeto(datos / "feriados.json").items()
        }
    except _ERRORES as error:
        avisos.append("No se pudieron leer los feriados: {}.".format(error))
    return resultado


def estado_indices(indices, hoy):
    partes = ["Captura BCRA: {}".format(indices["captura"] or "sin dato")]
    for clave in ("cer", "a3500", "tamar_tna"):
        serie = indices[clave]
        fechas = sorted(serie)
        partes.append("{}: último dato {}".format(clave, fechas[-1] if fechas else "sin dato"))
        if clave == "cer" or not fechas or indices["captura"] is None:
            continue
        huecos = []
        fecha = max(fechas[0], indices["captura"] - timedelta(days=14))
        while fecha < indices["captura"]:
            if (fecha.weekday() < 5 and fecha not in serie
                    and fecha not in indices["feriados"].get(str(fecha.year), ())):
                huecos.append(fecha.isoformat())
            fecha += timedelta(days=1)
        if huecos:
            partes.append("posibles huecos {} en las últimas dos semanas: {}".format(clave, ", ".join(huecos)))
    rem = indices["rem"]
    partes.append("REM: " + (rem.mes.isoformat()[:7] if rem else "sin dato"))
    return " · ".join(partes)


def registrar_proyecciones(carpeta, flujo, hoy):
    carpeta = carpeta / "proyecciones"
    anteriores = _archivos(carpeta, ".json", hoy)
    nuevas = []
    instantaneas = None
    for posicion in flujo["posiciones"]:
        for pago in posicion["pagos"]:
            if not pago["origen"].startswith(("estimado ·", "definitivo ·")) or pago["total"] is None:
                continue
            if pago["estado"] == "proyectado" and pago["origen"].startswith("estimado ·"):
                nuevas.append({"ticker": posicion["ticker"], "fecha": pago["fecha"],
                               "importe": pago["total"], "origen": pago["origen"]})
            cobro = pago.get("cobro")
            if cobro and cobro.get("registrado") is not None:
                fecha_pago = date.fromisoformat(pago["fecha"])
                if instantaneas is None:
                    instantaneas = [(fecha, _objeto(ruta).get("pagos", [])) for fecha, ruta in anteriores]
                for fecha, estimaciones in instantaneas:
                    if fecha >= fecha_pago:
                        continue
                    coincidencias = [e for e in estimaciones if e["ticker"] == posicion["ticker"]
                                    and e["fecha"] == pago["fecha"]]
                    if coincidencias:
                        cobro["estimacion_anterior"] = coincidencias[0]["importe"]
                        cobro["fecha_estimacion"] = fecha.isoformat()
                        break
    if nuevas and (not anteriores or (hoy - anteriores[0][0]).days >= 7):
        try:
            _guardar({"fecha": hoy.isoformat(), "pagos": nuevas}, carpeta / (hoy.isoformat() + ".json"))
        except FileExistsError:
            pass
