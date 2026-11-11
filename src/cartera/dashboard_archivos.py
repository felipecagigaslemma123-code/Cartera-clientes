"""Carga de datos opcionales y publicación privada del dashboard."""

import csv
import json
import math
import os
import tempfile
from collections import defaultdict, deque
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from .calculos import resultado_posicion, resumen_cartera
from .dashboard import generar_html
from .dia_cero import _leer_dia_cero, _validar_efectivo
from .precios import ClientePrecios, patrimonio_inicial
from .movimientos import (
    cartera_actual, conciliar_efectivo, leer_movimientos, resultado_integral, validar_movimientos,
)


class ErrorDashboard(ValueError):
    """Un archivo de entrada no puede interpretarse de forma confiable."""


def _camino(carpeta, nombre):
    ruta = carpeta / nombre
    if ruta.is_symlink() or ruta.resolve().parent != carpeta.resolve():
        raise ErrorDashboard("{} debe estar en la carpeta del cliente y no ser un enlace.".format(nombre))
    if ruta.exists() and not ruta.is_file():
        raise ErrorDashboard("{} debe ser un archivo.".format(nombre))
    return ruta


def _constante_invalida(texto):
    raise ErrorDashboard("Número no finito: " + texto)


def _objeto_opcional(ruta):
    if not ruta.exists():
        return None
    try:
        contenido = json.loads(ruta.read_text(encoding="utf-8"), parse_constant=_constante_invalida)
    except (ValueError, UnicodeError):
        raise ErrorDashboard("{} no contiene un JSON válido.".format(ruta.name)) from None
    if not isinstance(contenido, dict):
        raise ErrorDashboard("{} debe contener un objeto JSON.".format(ruta.name))
    return contenido


def _niveles(contenido, punto, conocidas, avisos):
    # La pantalla y el comando manual deben interpretar el mismo niveles.json.
    from .alertas_comando import _niveles_validos
    try:
        return _niveles_validos(contenido or {}, punto, conocidas, avisos)
    except ValueError as error:
        raise ErrorDashboard(str(error)) from None


def _instrumentos(contenido):
    contenido = contenido or {}
    for ticker, instrumento in contenido.items():
        if not isinstance(ticker, str) or not ticker or not isinstance(instrumento, dict):
            raise ErrorDashboard("instrumentos.json contiene una especie o un objeto inválido.")
        vencimiento = instrumento.get("vencimiento")
        if vencimiento is not None:
            try:
                date.fromisoformat(vencimiento)
            except (TypeError, ValueError):
                raise ErrorDashboard("instrumentos.json: {} tiene un vencimiento inválido.".format(ticker)) from None
    return contenido


def _perfil(contenido, slug):
    contenido = dict(contenido or {})
    for clave in ("nombre", "asesor"):
        if contenido.get(clave) is not None and not isinstance(contenido[clave], str):
            raise ErrorDashboard("perfil.json: {} debe ser texto.".format(clave))
    contenido["slug"] = slug
    return contenido


def _historial(ruta, tickers):
    datos = defaultdict(lambda: deque(maxlen=500))
    omitidas = 0
    if not ruta.exists():
        return {}, []
    try:
        with ruta.open(encoding="utf-8", newline="") as entrada:
            lector = csv.DictReader(entrada)
            if lector.fieldnames != ["consultado_en", "ticker", "ultimo", "bid", "ask"]:
                raise ErrorDashboard("historial.csv no tiene los encabezados esperados.")
            for fila in lector:
                ticker = fila.get("ticker")
                if ticker == "MEP" or ticker not in tickers:
                    continue
                try:
                    if None in fila:
                        raise ValueError("Columnas adicionales")
                    instante = datetime.fromisoformat(fila["consultado_en"])
                    precio = float(fila["ultimo"])
                    if instante.utcoffset() is None or not math.isfinite(precio) or precio <= 0:
                        raise ValueError("Fecha o precio inválido")
                except (TypeError, ValueError, KeyError, OverflowError):
                    omitidas += 1
                    continue
                datos[ticker].append((instante, precio))
    except (UnicodeError, csv.Error):
        raise ErrorDashboard("historial.csv no se puede interpretar como CSV UTF-8.") from None
    avisos = ["historial.csv: se omitieron {} filas inválidas.".format(omitidas)] if omitidas else []
    return {ticker: list(filas) for ticker, filas in datos.items()}, avisos


def _publicar(ruta, html):
    temporal = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=ruta.parent,
                                         prefix=".dashboard-", suffix=".tmp", delete=False) as salida:
            temporal = Path(salida.name)
            os.fchmod(salida.fileno(), 0o600)
            salida.write(html)
            salida.flush()
            os.fsync(salida.fileno())
        os.replace(str(temporal), str(ruta))
        temporal = None
    finally:
        if temporal is not None:
            temporal.unlink(missing_ok=True)


def crear_dashboard(punto, carpeta, slug, fetch, *, datos=None, aviso_iamc=None):
    carpeta = Path(carpeta)
    nombres = ("perfil.json", "niveles.json", "instrumentos.json", "efectivo.json",
               "dia_cero.json", "movimientos.csv", "historial.csv", "cache_precios.json", "dashboard.html",
               "compras_letras.json", "compras_bonos.json")
    rutas = {nombre: _camino(carpeta, nombre) for nombre in nombres}
    cliente = _perfil(_objeto_opcional(rutas["perfil.json"]), slug)
    niveles_brutos = _objeto_opcional(rutas["niveles.json"])
    instrumentos = _instrumentos(_objeto_opcional(rutas["instrumentos.json"]))
    efectivo_bruto = _objeto_opcional(rutas["efectivo.json"])
    efectivo = _validar_efectivo(efectivo_bruto)
    if efectivo_bruto is not None:
        nota = efectivo_bruto.get("nota", "")
        if not isinstance(nota, str):
            raise ErrorDashboard("efectivo.json: nota debe ser texto.")
        efectivo["nota"] = nota
    dia_cero = _leer_dia_cero(rutas["dia_cero.json"]) if rutas["dia_cero.json"].exists() else None
    if dia_cero is not None:
        patrimonio_inicial(punto.posiciones, dia_cero)
    base = punto
    movimientos = leer_movimientos(rutas["movimientos.csv"])
    generado_en = datetime.now(ZoneInfo("America/Argentina/Buenos_Aires"))
    fecha_dia_cero = date.fromisoformat(dia_cero["fecha"]) if dia_cero else None
    validar_movimientos(base, movimientos, fecha_dia_cero, generado_en.date())
    punto, realizados = cartera_actual(base, movimientos)
    control = conciliar_efectivo(dia_cero, movimientos, efectivo)
    historial, avisos = _historial(rutas["historial.csv"], {p.ticker for p in punto.posiciones})
    conocidas = {p.ticker for p in base.posiciones} | {m["ticker"] for m in movimientos if m["tipo"] == "compra"}
    niveles = _niveles(niveles_brutos, punto, conocidas, avisos)
    historial_realizado = None
    ruta_extractos = carpeta / "extractos"
    if ruta_extractos.exists() or ruta_extractos.is_symlink():
        # El historial es independiente de los movimientos desde el día cero y no
        # publica realizado.csv ni actualiza el MEP al generar la pantalla.
        try:
            from .historial import _cargar_historial
            historial_realizado = _cargar_historial(carpeta, base)
        except (ValueError, OSError) as error:
            avisos.append("No se pudo calcular el rendimiento realizado histórico: {}".format(error))
    from .flujo_fondos import calcular_flujo
    from .iamc import leer_cierres
    from .letras import calcular_letras
    from .letras_archivos import leer_compras, leer_compras_bonos
    try:
        compras_letras = leer_compras(rutas["compras_letras.json"])
    except (ValueError, OSError) as error:
        compras_letras = None
        avisos.append("No se pudieron leer los precios manuales de letras: {}".format(error))
    letras = calcular_letras(base, movimientos, instrumentos, compras_letras, generado_en.date())
    avisos.extend(letras["avisos"])
    avisos_flujo = [aviso_iamc] if aviso_iamc else []
    try:
        compras_bonos = leer_compras_bonos(rutas["compras_bonos.json"])
    except (ValueError, OSError) as error:
        compras_bonos = None
        avisos_flujo.append("No se pudieron leer las compras de bonos: {}.".format(error))
    if datos is None and carpeta.parent.name == "clientes":
        datos = carpeta.parent.parent
    try:
        cierres_iamc = leer_cierres(datos) if datos is not None else []
    except (ValueError, OSError) as error:
        cierres_iamc = []
        avisos_flujo.append("No se pudieron leer los cierres de IAMC: {}.".format(error))
    flujo = calcular_flujo(base, movimientos, instrumentos, cierres_iamc, compras_bonos,
                           letras, generado_en.date(), fecha_dia_cero, actual=punto,
                           cobros_historial=getattr(historial_realizado, "cobros", ()))
    flujo["avisos"][:0] = avisos_flujo
    cliente_precios = ClientePrecios(fetch, rutas["cache_precios.json"], persistir_cache=False)
    cotizaciones = cliente_precios.obtener(punto.posiciones)
    mep = cliente_precios.dolar_mep()
    resultados = [resultado_posicion(p, [lote for lote in punto.lotes if lote.ticker == p.ticker],
                                    cotizaciones[p.ticker].ultimo,
                                    dia_cero["precios"].get(p.ticker) if dia_cero else None)
                  for p in punto.posiciones]
    resumen = resumen_cartera(resultados)
    integral = resultado_integral(base.posiciones, dia_cero, punto.posiciones, movimientos,
                                  {ticker: c.ultimo for ticker, c in cotizaciones.items()},
                                  mep.ultimo if mep else None)
    try:
        cliente_precios.guardar_cache()
    except OSError as error:
        avisos.append("Al generar el archivo no se pudo guardar la caché de precios: {}".format(error))
    if mep is None:
        avisos.append("Al generar el archivo, dólar MEP sin dato; el navegador intentará obtenerlo para mostrar los totales en dólares.")
    cliente["_avisos_datos"] = avisos
    html = generar_html(cliente=cliente, resultados=resultados, resumen=resumen,
                        cotizaciones=cotizaciones, niveles=niveles, instrumentos=instrumentos,
                        efectivo=efectivo, historial=historial,
                        generado_en=generado_en,
                        posiciones=punto.posiciones, dia_cero=dia_cero, mep=mep,
                        posiciones_base=base.posiciones, integral=integral,
                        realizados=realizados, conciliacion=control, historial_realizado=historial_realizado,
                        letras=letras, flujo_fondos=flujo)
    _publicar(rutas["dashboard.html"], html)
    return {"ruta": rutas["dashboard.html"], "cotizaciones": cotizaciones, "avisos": avisos}
