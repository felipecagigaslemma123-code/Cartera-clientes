"""Series publicadas por el BCRA y curvas de expectativas del REM."""

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal, ROUND_CEILING, localcontext
from functools import wraps
import json
import os
from pathlib import Path
from tempfile import NamedTemporaryFile
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

from openpyxl import load_workbook


URL = "https://api.bcra.gob.ar/estadisticas/v4.0/monetarias"
SERIES = {"cer": 30, "tamar_tna": 44, "a3500": 5}
_IDENTIDAD = {
    "cer": ("Coeficiente de estabilización de referencia (base 2.2.02=1)", "Índice base 2.2.02=1"),
    "tamar_tna": ("Tasa de interes TAMAR de bancos privados", "En porcentaje nominal anual"),
    "a3500": ("Tipo de cambio mayorista de referencia", "Pesos argentinos por dólar estadounidense"),
}
_LIMITE = 1000
_MAX_BYTES = 2_000_000


class ErrorBCRA(ValueError):
    """Respuesta inválida del BCRA o imposibilidad de completar la captura."""


def _descargar(url):
    solicitud = Request(url, headers={"Accept": "application/json", "Accept-Language": "es-AR",
                                     "Accept-Encoding": "identity", "User-Agent": "cartera-bcra/0.1"})
    with urlopen(solicitud, timeout=10) as respuesta:
        return respuesta.read(_MAX_BYTES + 1)


def _pagina(url, fetch, offset):
    try:
        cuerpo = fetch(url)
        if not isinstance(cuerpo, bytes) or len(cuerpo) > _MAX_BYTES:
            raise ValueError("respuesta fuera del formato o tamaño esperado")
        pagina = json.loads(cuerpo, parse_float=Decimal, parse_constant=Decimal)
        if not isinstance(pagina, dict) or pagina.get("status") != 200:
            raise ValueError("la API no informó un estado 200")
        resultados = pagina["results"]
        datos = pagina["metadata"]["resultset"]
        cantidad, limite = datos["count"], datos["limit"]
        if (not isinstance(resultados, list) or type(cantidad) is not int or cantidad < offset
                or type(limite) is not int or limite <= 0 or datos.get("offset") != offset
                or any(not isinstance(fila, dict) for fila in resultados)):
            raise ValueError("paginación o resultados inválidos")
    except (OSError, ValueError, KeyError, TypeError, RecursionError) as error:
        raise ErrorBCRA("No se pudo leer {}. {}".format(url, error)) from None
    return resultados, cantidad, limite


def _fecha(texto):
    try:
        fecha = date.fromisoformat(texto)
    except (TypeError, ValueError):
        raise ErrorBCRA("Fecha inválida, se espera AAAA-MM-DD.") from None
    if fecha.isoformat() != texto:
        raise ErrorBCRA("Fecha inválida, se espera AAAA-MM-DD.")
    return fecha


def _catalogo(clave, id_variable, fetch):
    url = URL + "?" + urlencode({"idVariable": id_variable, "limit": 1, "offset": 0})
    filas, cantidad, _ = _pagina(url, fetch, 0)
    if cantidad != 1 or len(filas) != 1 or filas[0].get("idVariable") != id_variable:
        raise ErrorBCRA("{}: la serie {} no se encontró en el catálogo.".format(clave, id_variable))
    fila = filas[0]
    nombre, unidad = _IDENTIDAD[clave]
    descripcion = fila.get("descripcion")
    if (not isinstance(descripcion, str) or " ".join(descripcion.split()).casefold() != nombre.casefold()
            or fila.get("periodicidad") != "D" or fila.get("categoria") != "Principales Variables"
            or fila.get("unidadExpresion") != unidad):
        raise ErrorBCRA("{}: la descripción, frecuencia o unidad de la serie {} cambió.".format(clave, id_variable))
    return fila


def _observaciones(id_variable, desde, hasta, fetch):
    consulta = "{}/{}?{}".format(URL, id_variable, urlencode({"desde": desde, "hasta": hasta}))
    valores = {}
    cantidad = None
    while True:
        offset = len(valores)
        url = "{}&limit={}&offset={}".format(consulta, _LIMITE, offset)
        filas, total, limite = _pagina(url, fetch, offset)
        if cantidad is None:
            cantidad = total
        detalle = filas[0].get("detalle") if len(filas) == 1 and filas[0].get("idVariable") == id_variable else None
        if (total != cantidad or total > (hasta - desde).days + 1 or not isinstance(detalle, list)
                or len(detalle) != min(limite, total - offset)):
            raise ErrorBCRA("Serie {}: detalle o paginación incoherente.".format(id_variable))
        for registro in detalle:
            if not isinstance(registro, dict):
                raise ErrorBCRA("Serie {}: observación inválida.".format(id_variable))
            fecha, valor = _fecha(registro.get("fecha")), registro.get("valor")
            if fecha in valores or not desde <= fecha <= hasta:
                raise ErrorBCRA("Serie {}: fecha duplicada o fuera de rango, {}.".format(id_variable, fecha))
            if type(valor) not in (int, Decimal) or not Decimal(valor).is_finite():
                raise ErrorBCRA("Serie {}: valor no numérico o no finito en {}.".format(id_variable, fecha))
            valores[fecha] = str(valor)
        if len(valores) == cantidad:
            break
    return [{"fecha": fecha.isoformat(), "valor": valores[fecha]} for fecha in sorted(valores)]


def extraer(desde, hasta, *, fetch=None, hasta_cer=None):
    """Devuelve una captura fechada con la serie publicada y su procedencia."""
    if type(desde) is not date or type(hasta) is not date or desde > hasta:
        raise ErrorBCRA("El rango debe tener dos fechas válidas, desde ≤ hasta.")
    if hasta_cer is not None and (type(hasta_cer) is not date or hasta_cer < hasta):
        raise ErrorBCRA("El límite de CER debe ser igual o posterior al fin del rango general.")
    fetch = _descargar if fetch is None else fetch
    series = {}
    for clave, id_variable in SERIES.items():
        metadatos = _catalogo(clave, id_variable, fetch)
        fin = hasta_cer if clave == "cer" and hasta_cer is not None else hasta
        observaciones = _observaciones(id_variable, desde, fin, fetch)
        series[clave] = {"id_variable": id_variable, "url": "{}/{}".format(URL, id_variable),
                         "descripcion": metadatos["descripcion"].strip(), "unidad": metadatos["unidadExpresion"],
                         "periodicidad": metadatos["periodicidad"],
                         "primera_fecha_catalogo": metadatos.get("primerFechaInformada"),
                         "ultima_fecha_catalogo": metadatos.get("ultFechaInformada"),
                         "estado": "publicado" if observaciones else "sin dato", "observaciones": observaciones}
        if fin != hasta:
            series[clave]["hasta_consultado"] = fin.isoformat()
    return {"esquema_version": 1, "fuente": "BCRA",
            "consultado_en": datetime.now(ZoneInfo("America/Argentina/Buenos_Aires")).isoformat(),
            "desde": desde.isoformat(), "hasta": hasta.isoformat(), "series": series}


def _guardar(datos, destino):
    destino.parent.mkdir(parents=True, exist_ok=True)
    temporal = None
    try:
        with NamedTemporaryFile(mode="w", encoding="utf-8", dir=destino.parent, delete=False) as archivo:
            temporal = Path(archivo.name)
            json.dump(datos, archivo, ensure_ascii=False, indent=2, allow_nan=False)
            archivo.write("\n")
        os.link(temporal, destino)
    finally:
        if temporal is not None:
            temporal.unlink(missing_ok=True)


@dataclass(frozen=True)
class Rem:
    mes: date
    ipc: dict[date, Decimal]
    ipc_12m: Decimal
    ipc_24m: Decimal
    tamar: dict[date, Decimal]
    tamar_12m: Decimal
    tc: dict[date, Decimal]
    tc_12m: Decimal


@dataclass(frozen=True)
class Valor:
    valor: Decimal
    origen: str


def _precision(funcion):
    @wraps(funcion)
    def calcular(*args, **kwargs):
        with localcontext() as contexto:
            contexto.prec = 50
            return funcion(*args, **kwargs)
    return calcular


def _mes(fecha, desplazamiento=0):
    anio, mes = divmod(fecha.year * 12 + fecha.month - 1 + desplazamiento, 12)
    return date(anio, mes + 1, 1)


def _distancia_meses(a, b):
    return (b.year - a.year) * 12 + b.month - a.month


@_precision
def leer_rem(ruta):
    """Lee las medianas de la hoja oficial, sin depender del nombre del archivo."""
    encabezados = {
        "Precios minoristas (IPC nivel general-Nacional; INDEC)": ("ipc", "var. % mensual", 100),
        "Tasa de interés (TAMAR)": ("tamar", "TNA; %", 100),
        "Tipo de cambio nominal": ("tc", "$/USD", 1),
    }
    series = {nombre: {} for nombre, _, _ in encabezados.values()}
    horizontes = {}
    bloque = None
    libro = load_workbook(ruta, read_only=True, data_only=True)
    try:
        for _, periodo, referencia, mediana in libro["Cuadros de resultados"].iter_rows(
            max_col=4, values_only=True
        ):
            if periodo in encabezados:
                bloque = encabezados[periodo]
                continue
            if periodo is None:
                bloque = None
            if bloque is None or mediana is None:
                continue
            nombre, unidad, escala = bloque
            if isinstance(periodo, date) and referencia == unidad:
                destino, clave = series[nombre], _mes(periodo)
            elif periodo == "próx. 12 meses" or (periodo == "próx. 24 meses" and nombre == "ipc"):
                destino, clave = horizontes, (nombre, periodo)
            else:
                continue
            if clave in destino or type(mediana) not in (float, int, Decimal):
                raise ValueError("Mediana inválida o duplicada en el REM.")
            valor = Decimal(str(mediana)) / escala
            if not valor.is_finite():
                raise ValueError("Mediana no finita en el REM.")
            destino[clave] = valor
    finally:
        libro.close()
    try:
        return Rem(min(series["ipc"]), series["ipc"], horizontes["ipc", "próx. 12 meses"],
                   horizontes["ipc", "próx. 24 meses"], series["tamar"],
                   horizontes["tamar", "próx. 12 meses"], series["tc"],
                   horizontes["tc", "próx. 12 meses"])
    except (KeyError, ValueError):
        raise ValueError("El REM no contiene las medianas requeridas.") from None


@_precision
def serie_bcra(captura, clave):
    observaciones = captura["series"][clave]["observaciones"]
    escala = 100 if clave == "tamar_tna" else 1
    serie = {}
    for observacion in observaciones:
        fecha = _fecha(observacion["fecha"])
        valor = Decimal(observacion["valor"]) / escala
        if fecha in serie or not valor.is_finite():
            raise ErrorBCRA("Observación inválida o duplicada en {}.".format(clave))
        serie[fecha] = valor
    return serie


@_precision
def inflacion_mensual(rem, hasta):
    meses = [_mes(rem.mes, i) for i in range(1, 13)]
    producto = Decimal(1)
    faltantes = 0
    for mes in meses:
        if mes in rem.ipc:
            producto *= 1 + rem.ipc[mes]
        else:
            faltantes += 1
    tasa_complementaria = ((1 + rem.ipc_12m) / producto) ** (Decimal(1) / faltantes) - 1 if faltantes else None
    tasa_segundo_anio = (1 + rem.ipc_24m) ** (Decimal(1) / 12) - 1
    resultado = {}
    for distancia in range(_distancia_meses(rem.mes, hasta) + 1):
        mes = _mes(rem.mes, distancia)
        if mes in rem.ipc:
            resultado[mes] = rem.ipc[mes]
        elif distancia:
            resultado[mes] = tasa_complementaria if distancia <= 12 else tasa_segundo_anio
        else:
            raise ValueError("Falta la mediana de IPC del mes relevado.")
    return resultado


def _publicado(serie, fecha):
    anterior = max((dia for dia in serie if dia <= fecha), default=None)
    if anterior is None:
        raise ValueError("No hay observaciones publicadas al {}.".format(fecha))
    return anterior, Valor(serie[anterior], "publicado")


def _geometrica(a, b, desde, hasta, fecha):
    return a * (b / a) ** (Decimal((fecha - desde).days) / (hasta - desde).days)


@_precision
def indice_cer(publicado, inflacion, fecha):
    desde, ultimo = _publicado(publicado, fecha)
    if fecha <= max(publicado):
        return ultimo
    valor = ultimo.valor
    origen = "proyectado"
    while desde < fecha:
        fin = desde.replace(day=15) if desde.day < 15 else _mes(desde, 1).replace(day=15)
        objetivo = min(fin, fecha)
        if desde.day != 15:
            anterior, previo = _publicado(publicado, desde - timedelta(days=1))
            tasa = (valor / previo.valor) ** (Decimal(1) / (desde - anterior).days)
            valor *= tasa ** (objetivo - desde).days
        else:
            mes = _mes(desde, -1)
            if mes not in inflacion:
                raise ValueError("Falta la inflación de {} para proyectar CER.".format(mes))
            tasa = inflacion[mes]
            if isinstance(tasa, Valor):
                if tasa.origen == "manual":
                    origen = "manual"
                tasa = tasa.valor
            valor *= (1 + tasa) ** (Decimal((objetivo - desde).days) / (fin - desde).days)
        desde = objetivo
    return Valor(valor, origen)


@_precision
def indice_a3500(publicado, rem, fecha):
    desde, ultimo = _publicado(publicado, fecha)
    if fecha <= max(publicado):
        return ultimo
    puntos_rem = {_mes(rem.mes, 12): rem.tc_12m, **rem.tc}
    puntos = [(desde, ultimo)]
    for mes, valor in sorted(puntos_rem.items()):
        dia = mes.replace(day=15)
        if dia > desde:
            puntos.append((dia, valor if isinstance(valor, Valor) else Valor(valor, "proyectado")))
    if len(puntos) < 2:
        raise ValueError("Faltan referencias futuras de A3500 en el REM.")
    for (inicio, a), (fin, b) in zip(puntos, puntos[1:]):
        if fecha <= fin:
            if fecha == fin:
                return b
            break
    origen = "manual" if "manual" in (a.origen, b.origen) else "proyectado"
    return Valor(_geometrica(a.valor, b.valor, inicio, fin, fecha), origen)


@_precision
def tamar_diaria(publicado, rem, fecha):
    if publicado and fecha <= max(publicado):
        return _publicado(publicado, fecha)[1]
    mes = _mes(fecha)
    puntos = {_mes(rem.mes, 12): rem.tamar_12m, **rem.tamar}
    if mes in puntos:
        valor = puntos[mes]
        return valor if isinstance(valor, Valor) else Valor(valor, "proyectado")
    anteriores = [dia for dia in puntos if dia < mes]
    if not anteriores:
        raise ValueError("Falta TAMAR del REM para {}.".format(mes))
    inicio = max(anteriores)
    a = puntos[inicio]
    a = a if isinstance(a, Valor) else Valor(a, "proyectado")
    fin = min((dia for dia in puntos if dia > mes), default=None)
    if fin is None:
        return a
    b = puntos[fin]
    b = b if isinstance(b, Valor) else Valor(b, "proyectado")
    fraccion = Decimal(_distancia_meses(inicio, mes)) / _distancia_meses(inicio, fin)
    origen = "manual" if "manual" in (a.origen, b.origen) else "proyectado"
    return Valor(a.valor + (b.valor - a.valor) * fraccion, origen)


@_precision
def tem_tamar(tna, margen):
    return (1 + (tna + margen) * 32 / 365) ** (Decimal(365) / 384) - 1


@_precision
def proyectar_capitalizable(mv, tem, n, me, tems):
    restantes = n - me
    if restantes < 0:
        raise ValueError("Los meses transcurridos superan el plazo del título.")
    cantidad = int(restantes.to_integral_value(rounding=ROUND_CEILING))
    if len(tems) < cantidad:
        raise ValueError("Faltan TEM para proyectar el pago capitalizable.")
    for k in range(cantidad):
        mv *= ((1 + tems[k]) / (1 + tem)) ** min(Decimal(1), restantes - k)
    return mv
