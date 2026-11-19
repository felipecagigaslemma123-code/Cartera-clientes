"""Riesgo interno del asesor (etapa 14, docs/RIESGO.md).

El modelo es puro: aplica los pesos actuales a retornos históricos de precio,
sin completar huecos. La descarga y la publicación viven al final del módulo.
"""

import calendar
import copy
import json
import math
import os
import re
import sys
import tempfile
import time
from datetime import date, datetime
from html import escape
from html.parser import HTMLParser
from pathlib import Path
from zoneinfo import ZoneInfo

from . import _riesgo_calculos as calculos
from .transporte import consultar_json


PARAMETROS = {
    "ventana": 252, "minimo": 126, "cobertura_minima": 0.95,
    "ventana_cola": 504, "minimo_cola": 250, "confianza": 0.95,
    "lambda_ewma": 0.94, "minimo_ewma": 60, "salto": 0.25,
    "periodos": 252, "escenarios_pb": [-200, -100, 100, 200],
    "pago_antes": 6, "pago_despues": 1,
}
EVENTOS_CONOCIDOS = {("SPY", "2026-05-29"): "cambio de ratio 3:1"}
_SEGMENTOS = {"arg_cedears": "cedears", "arg_stocks": "stocks", "arg_bonds": "bonds"}
_MESES_CUPON = {"Mensual": 1, "Trimestral": 3, "Semestral": 6, "Anual": 12}
_FAMILIAS = ("USD", "ARS tasa fija", "CER", "TAMAR", "dólar linked")
_ZONA = ZoneInfo("America/Argentina/Buenos_Aires")


class ErrorRiesgo(ValueError):
    """Datos inválidos o sin una referencia CCL utilizable."""


def _hoy():
    return datetime.now(_ZONA).date()


def _numero(valor):
    if isinstance(valor, bool) or not isinstance(valor, (int, float)):
        return None
    try:
        return float(valor) if math.isfinite(valor) else None
    except OverflowError:
        return None


def _fecha(texto):
    if not isinstance(texto, str):
        return None
    try:
        return date.fromisoformat(texto)
    except ValueError:
        return None


def segmento_historico(endpoint):
    return _SEGMENTOS.get(endpoint)


def historicos_necesarios(datos):
    claves = ["bonds/AL30", "bonds/AL30C", "cedears/SPY"]
    for posicion in datos["posiciones"]:
        segmento = segmento_historico(posicion.get("endpoint"))
        if segmento:
            clave = segmento + "/" + posicion["ticker"]
            if clave not in claves:
                claves.append(clave)
    return claves


def _validar_datos(datos):
    if not isinstance(datos, dict) or not isinstance(datos.get("posiciones"), list):
        raise ErrorRiesgo("El bloque datos-cartera no trae posiciones válidas.")
    generado = datos.get("generado_en")
    try:
        fecha = datetime.fromisoformat(generado).date()
    except (TypeError, ValueError):
        raise ErrorRiesgo("El bloque datos-cartera no tiene una fecha generado_en válida.") from None
    cliente = datos.get("cliente")
    if not isinstance(cliente, dict) or not isinstance(cliente.get("nombre"), str) or not cliente["nombre"].strip():
        raise ErrorRiesgo("El bloque datos-cartera no identifica al cliente.")
    vistos = set()
    for posicion in datos["posiciones"]:
        if not isinstance(posicion, dict):
            raise ErrorRiesgo("El bloque datos-cartera tiene una posición inválida.")
        ticker = posicion.get("ticker")
        if not isinstance(ticker, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]*", ticker):
            raise ErrorRiesgo("El bloque datos-cartera tiene un ticker inválido.")
        if ticker in vistos:
            raise ErrorRiesgo("{}: ticker repetido en datos-cartera.".format(ticker))
        vistos.add(ticker)
        if not isinstance(posicion.get("tipo"), str) or not isinstance(posicion.get("endpoint"), (str, type(None))):
            raise ErrorRiesgo("{}: tipo o endpoint inválido.".format(ticker))
        valor = posicion.get("valuacion")
        if valor is not None and (_numero(valor) is None or valor < 0):
            raise ErrorRiesgo("{}: valuación inválida.".format(ticker))
    return fecha.isoformat()


def _parametros(reemplazos):
    parametros = copy.deepcopy(PARAMETROS)
    if reemplazos is not None:
        if not isinstance(reemplazos, dict) or set(reemplazos) - set(parametros):
            raise ErrorRiesgo("Parámetros de riesgo desconocidos.")
        parametros.update(copy.deepcopy(reemplazos))
    for clave in ("ventana", "minimo", "ventana_cola", "minimo_cola", "minimo_ewma", "periodos",
                  "pago_antes", "pago_despues"):
        valor = parametros[clave]
        minimo = 0 if clave.startswith("pago_") else (2 if clave == "minimo" else 1)
        if isinstance(valor, bool) or not isinstance(valor, int) or valor < minimo:
            raise ErrorRiesgo("Parámetro {} inválido.".format(clave))
    for clave, bajo, alto in (("confianza", 0.5, 1), ("lambda_ewma", 0, 1)):
        valor = _numero(parametros[clave])
        if valor is None or not bajo < valor < alto:
            raise ErrorRiesgo("Parámetro {} inválido.".format(clave))
    cobertura = _numero(parametros["cobertura_minima"])
    salto = _numero(parametros["salto"])
    if cobertura is None or not 0 < cobertura <= 1 or salto is None or salto <= 0:
        raise ErrorRiesgo("Cobertura mínima o umbral de salto inválidos.")
    escenarios = parametros["escenarios_pb"]
    if not isinstance(escenarios, list) or not escenarios or any(_numero(pb) is None for pb in escenarios):
        raise ErrorRiesgo("Escenarios de tasa inválidos.")
    return parametros


def _cierres(respuesta, hasta):
    """Solo cierres negociados, finitos y fechados; duplicados conflictivos se invalidan."""
    if not isinstance(respuesta, list):
        return None
    precios, conflictos = {}, set()
    for fila in respuesta:
        if not isinstance(fila, dict):
            continue
        fecha, precio, volumen = _fecha(fila.get("date")), _numero(fila.get("c")), _numero(fila.get("v"))
        if fecha is None or fecha.isoformat() > hasta or precio is None or precio <= 0 or volumen is None or volumen <= 0:
            continue
        texto = fecha.isoformat()
        if texto in precios and precios[texto] != precio:
            conflictos.add(texto)
        precios[texto] = precio
    return {fecha: precio for fecha, precio in precios.items() if fecha not in conflictos}


def _filas_iamc(cierre):
    filas = {}
    informes = cierre.get("informes", {}) if isinstance(cierre, dict) else {}
    for grupo in ("titulos_publicos", "on"):
        bloque = informes.get(grupo) or {}
        for fila in bloque.get("rows", []):
            if isinstance(fila, dict) and isinstance(fila.get("tk"), str):
                filas[fila["tk"]] = fila
    return filas


def _pagos_pasados(fila, desde):
    if not fila or fila.get("fc") not in _MESES_CUPON:
        return []
    proximo = _fecha(fila.get("pc"))
    if proximo is None:
        return []
    limite = max(desde, _fecha(fila.get("fe")) or desde)
    pagos, paso = [], _MESES_CUPON[fila["fc"]]
    k = 1
    while True:
        meses = proximo.year * 12 + proximo.month - 1 - paso * k
        anio, mes = divmod(meses, 12)
        mes += 1
        if anio < 1:
            break
        pago = date(anio, mes, min(proximo.day, calendar.monthrange(anio, mes)[1]))
        if pago < limite:
            break
        pagos.append(pago)
        k += 1
    return pagos


def _retornos(ticker, tipo, precios, sesiones, ccl, fila, parametros):
    pagos = _pagos_pasados(fila, _fecha(sesiones[0])) if tipo in ("bono", "on", "letra") else []
    retornos, excluidos = {}, []
    for anterior, actual in zip(sesiones, sesiones[1:]):
        retornos[actual] = None
        if anterior not in precios or actual not in precios:
            continue
        fecha = _fecha(actual)
        pago = next((p for p in pagos if -parametros["pago_despues"] <= (p - fecha).days <= parametros["pago_antes"]), None)
        motivo = None
        if pago is not None:
            motivo = "rueda cercana al pago del " + pago.isoformat()
        elif (ticker, actual) in EVENTOS_CONOCIDOS:
            motivo = EVENTOS_CONOCIDOS[(ticker, actual)]
        else:
            salto = precios[actual] / precios[anterior] - 1
            if abs(salto) > parametros["salto"]:
                motivo = "salto de {:+.0%} en pesos sin evento conocido".format(salto)
        if motivo is not None:
            excluidos.append({"fecha": actual, "motivo": motivo})
        else:
            retornos[actual] = (precios[actual] / ccl[actual]) / (precios[anterior] / ccl[anterior]) - 1
    return retornos, excluidos


def _regresion(retornos, mercado, fechas, minimo):
    pares = [(retornos[f], mercado.get(f)) for f in fechas
             if retornos.get(f) is not None and mercado.get(f) is not None]
    if len(pares) < max(3, minimo):
        return None
    try:
        return calculos.modelo_indice([a for a, _ in pares], [b for _, b in pares])
    except ValueError:
        # Mercado constante: beta indefinida; no impide medir la volatilidad.
        return None


def _sensibilidad(fila, valor):
    if not fila or _numero(fila.get("dm")) is None:
        return None
    familia = ("CER" if fila.get("aj") == "CER" else
               "dólar linked" if fila.get("aj") == "DL" else
               "TAMAR" if fila.get("idx") == "TAMAR" else
               "USD" if fila.get("me") == "USD" else "ARS tasa fija")
    dm = _numero(fila["dm"])
    return {"familia": familia, "dm": dm, "cx": _numero(fila.get("cx")),
            "tir": _numero(fila.get("ytm")), "dv01_ars": valor * dm * 0.0001}


def _activo(posicion, total, ultimo_ccl, historicos, sesiones, ccl, filas, mercado, parametros, avisos, hay_cierre):
    ticker, tipo = posicion["ticker"], posicion["tipo"]
    valor = float(posicion["valuacion"])
    activo = {"ticker": ticker, "tipo": tipo, "peso": valor / total if total else None,
              "valor_ars": valor, "valor_usd": valor / ultimo_ccl,
              "historia": None, "vol_anual": None, "ewma_anual": None, "ewma_n": None,
              "beta": None, "r2": None, "beta_ic95": None, "var95_usd": None, "es95_usd": None,
              "excluidos": [], "renta_fija": None}
    if tipo in ("bono", "on", "letra"):
        activo["renta_fija"] = _sensibilidad(filas.get(ticker), valor)
        if hay_cierre and activo["renta_fija"] is None:
            avisos.append("{}: sin duration en el cierre IAMC.".format(ticker))
        elif activo["renta_fija"] is not None and activo["renta_fija"]["cx"] is None:
            avisos.append("{}: sin convexidad en el cierre IAMC; escenarios sin dato.".format(ticker))
    segmento = segmento_historico(posicion.get("endpoint"))
    respuesta = historicos.get(segmento + "/" + ticker) if segmento else None
    precios = _cierres(respuesta, sesiones[-1]) if segmento else None
    if segmento is None or precios is None:
        motivo = ("data912 no tiene histórico de letras ni ON" if segmento is None else
                  "no se pudo consultar data912" if respuesta is None else "data912 no tiene su historia")
        activo["historia"] = {"estado": "sin_fuente" if segmento is None else "sin_serie",
                              "motivo": motivo, "n": None, "ruedas": None, "cobertura": None}
        return activo, None
    retornos, excluidos = _retornos(ticker, tipo, precios, sesiones, ccl, filas.get(ticker), parametros)
    fechas = sesiones[1:][-parametros["ventana"]:]
    valores = [retornos[f] for f in fechas]
    validos = [r for r in valores if r is not None]
    cobertura = len(validos) / len(fechas) if fechas else 0.0
    suficiente = len(validos) >= parametros["minimo"] and cobertura >= parametros["cobertura_minima"]
    activo["historia"] = {"estado": "suficiente" if suficiente else "insuficiente", "n": len(validos),
                          "ruedas": len(fechas), "cobertura": cobertura,
                          "motivo": None if suficiente else "{} retornos válidos de {} ruedas".format(len(validos), len(fechas))}
    activo["excluidos"] = [e for e in excluidos if e["fecha"] in fechas]
    if not suficiente:
        return activo, retornos
    sigma = calculos.volatilidad(validos, 1)
    activo["vol_anual"] = sigma * math.sqrt(parametros["periodos"])
    tramo = []
    for retorno in valores:
        if retorno is None:
            tramo = []
        else:
            tramo.append(math.log1p(retorno))
    if len(tramo) >= parametros["minimo_ewma"]:
        activo["ewma_anual"] = math.sqrt(parametros["periodos"] * calculos.ewma(tramo, parametros["lambda_ewma"])["siguiente"])
        activo["ewma_n"] = len(tramo)
    cola = calculos.var_es_normal(0, sigma, parametros["confianza"], valor=activo["valor_usd"])
    activo["var95_usd"], activo["es95_usd"] = cola["var"], cola["es"]
    regresion = _regresion(retornos, mercado, fechas, parametros["minimo"])
    if regresion is not None:
        activo.update(beta=regresion["beta"], r2=regresion["r_cuadrado"], beta_ic95=regresion["intervalo_beta"])
    return activo, retornos


def _cartera(activos, series, sesiones, mercado, total, ultimo_ccl, parametros):
    incluidos = [a for a in activos if a["historia"]["estado"] == "suficiente"]
    cobertura = sum(a["peso"] for a in incluidos) if total else 0.0
    cartera = {"estado": "sin_dato", "motivo": None, "cobertura_patrimonial": cobertura,
               "incluidos": [a["ticker"] for a in incluidos],
               "excluidos": [{"ticker": a["ticker"], "peso": a["peso"], "motivo": a["historia"]["motivo"]}
                             for a in activos if a["historia"]["estado"] != "suficiente"],
               "filas": 0, "vol_anual": None, "var95_usd": None, "es95_usd": None,
               "valor_medido_usd": None, "beta": None, "r2": None,
               "ratio_diversificacion": None, "correlacion_media": None,
               "contribuciones": [], "peor_dia": None}
    historico = {"estado": "sin_dato", "motivo": None, "filas": 0, "var95_usd": None, "es95_usd": None}
    if not incluidos or not cobertura:
        motivo = "ninguna posición tiene historia suficiente" if not incluidos else "la cartera no tiene valuación positiva"
        cartera["motivo"] = historico["motivo"] = motivo
        return cartera, historico
    tickers = cartera["incluidos"]
    pesos = [a["peso"] / cobertura for a in incluidos]
    valor = total * cobertura / ultimo_ccl
    fechas = [f for f in sesiones[1:][-parametros["ventana"]:] if all(series[t].get(f) is not None for t in tickers)]
    cartera["filas"] = len(fechas)
    if len(fechas) < parametros["minimo"]:
        cartera["motivo"] = "{} ruedas comunes; el mínimo es {}".format(len(fechas), parametros["minimo"])
    else:
        columnas = [[series[t][f] for f in fechas] for t in tickers]
        matriz = calculos.matriz_covarianzas(columnas)
        riesgo = calculos.riesgo_cartera(pesos, matriz, parametros["periodos"])
        cola = calculos.var_es_normal(0, riesgo["vol_diaria"], parametros["confianza"], valor=valor)
        cartera.update(estado="calculada", vol_anual=riesgo["vol_anual"], var95_usd=cola["var"],
                       es95_usd=cola["es"], valor_medido_usd=valor,
                       ratio_diversificacion=riesgo["ratio_diversificacion"])
        correlaciones = [calculos.correlacion(columnas[i], columnas[j])
                         for i in range(len(columnas)) for j in range(i + 1, len(columnas))]
        conocidas = [c for c in correlaciones if c is not None]
        cartera["correlacion_media"] = sum(conocidas) / len(conocidas) if conocidas else None
        cartera["contribuciones"] = sorted(
            [{"ticker": t, "peso_medido": w, "fraccion": fraccion}
             for t, w, fraccion in zip(tickers, pesos, riesgo["fracciones_riesgo"])],
            key=lambda c: (c["fraccion"] is None, -(c["fraccion"] or 0), c["ticker"]))
        retornos = {f: sum(series[t][f] * w for t, w in zip(tickers, pesos)) for f in fechas}
        peor = min(fechas, key=lambda f: retornos[f])
        cartera["peor_dia"] = {"fecha": peor, "retorno": retornos[peor]}
        regresion = _regresion(retornos, mercado, fechas, parametros["minimo"])
        if regresion is not None:
            cartera.update(beta=regresion["beta"], r2=regresion["r_cuadrado"])
    fechas_cola = [f for f in sesiones[1:][-parametros["ventana_cola"]:] if all(series[t].get(f) is not None for t in tickers)]
    historico["filas"] = len(fechas_cola)
    if len(fechas_cola) < parametros["minimo_cola"]:
        historico["motivo"] = "{} ruedas comunes; el mínimo es {}".format(len(fechas_cola), parametros["minimo_cola"])
    else:
        retornos_cola = [sum(series[t][f] * w for t, w in zip(tickers, pesos)) for f in fechas_cola]
        cola = calculos.var_es_historico(retornos_cola, parametros["confianza"], valor)
        historico.update(estado="calculado", var95_usd=cola["var"], es95_usd=cola["es"])
    return cartera, historico


def _agrupar_renta_fija(activos, parametros):
    familias = []
    for familia in _FAMILIAS:
        grupo = [a for a in activos if a["renta_fija"] is not None and a["renta_fija"]["familia"] == familia]
        if not grupo:
            continue
        valor = sum(a["valor_ars"] for a in grupo)
        dm = sum(a["valor_ars"] * a["renta_fija"]["dm"] for a in grupo) / valor if valor else None
        convexidades = all(a["renta_fija"]["cx"] is not None for a in grupo)
        cx = sum(a["valor_ars"] * a["renta_fija"]["cx"] for a in grupo) / valor if valor and convexidades else None
        escenarios = {}
        for pb in parametros["escenarios_pb"]:
            dy = pb / 10000
            escenarios[str(pb)] = sum(a["valor_ars"] * (-a["renta_fija"]["dm"] * dy + 0.5 * a["renta_fija"]["cx"] * dy * dy)
                                      for a in grupo) if convexidades else None
        familias.append({"familia": familia, "tickers": [a["ticker"] for a in grupo], "valor_ars": valor,
                         "dm": dm, "cx": cx, "dv01_ars": sum(a["renta_fija"]["dv01_ars"] for a in grupo),
                         "escenarios": escenarios})
    return familias


def armar_riesgo(datos, historicos, cierre_iamc=None, parametros=None):
    """Construye un modelo serializable, sin E/S ni modificaciones de las entradas."""
    fecha_tablero = _validar_datos(datos)
    parametros = _parametros(parametros)
    al30 = _cierres(historicos.get("bonds/AL30"), fecha_tablero)
    al30c = _cierres(historicos.get("bonds/AL30C"), fecha_tablero)
    if not al30 or not al30c:
        raise ErrorRiesgo("Sin historia de AL30/AL30C no se puede calcular el CCL.")
    sesiones = sorted(set(al30) & set(al30c))
    if not sesiones:
        raise ErrorRiesgo("AL30 y AL30C no tienen ruedas comunes para calcular el CCL.")
    ccl = {f: al30[f] / al30c[f] for f in sesiones}
    ultimo_ccl = ccl[sesiones[-1]]
    avisos = []
    if cierre_iamc is None:
        avisos.append("Sin cierre IAMC: no se conocen las duraciones ni las fechas de pago contractuales.")
    filas = _filas_iamc(cierre_iamc)
    precios_spy = _cierres(historicos.get("cedears/SPY"), fecha_tablero)
    if not precios_spy:
        avisos.append("SPY: sin historia de mercado; beta y R² sin dato.")
    mercado, _ = _retornos("SPY", "cedear", precios_spy or {},
                           sesiones, ccl, None, parametros)
    posiciones = []
    for posicion in datos["posiciones"]:
        if posicion.get("valuacion") is None:
            avisos.append("{}: sin valuación; queda fuera de pesos y cálculos.".format(posicion["ticker"]))
        else:
            posiciones.append(posicion)
    total = sum(float(p["valuacion"]) for p in posiciones)
    activos, series = [], {}
    for posicion in posiciones:
        activo, retornos = _activo(posicion, total, ultimo_ccl, historicos, sesiones, ccl, filas,
                                  mercado, parametros, avisos, cierre_iamc is not None)
        activos.append(activo)
        if retornos is not None:
            series[activo["ticker"]] = retornos
    activos.sort(key=lambda a: (-(a["peso"] or 0), a["ticker"]))
    concentracion = dict.fromkeys(("herfindahl", "numero_efectivo", "peso_maximo", "ticker_maximo"))
    if total:
        concentracion = calculos.concentracion([a["peso"] for a in activos])
        concentracion["ticker_maximo"] = activos[0]["ticker"]
    cartera, historico = _cartera(activos, series, sesiones, mercado, total, ultimo_ccl, parametros)
    return {"cliente": datos["cliente"]["nombre"], "fecha_tablero": fecha_tablero, "fecha_datos": sesiones[-1],
            "moneda": "USD CCL", "ccl": ultimo_ccl, "parametros": parametros,
            "total_ars": total, "total_usd": total / ultimo_ccl, "concentracion": concentracion,
            "activos": activos, "cartera": cartera, "var_historico": historico,
            "renta_fija": _agrupar_renta_fija(activos, parametros), "avisos": avisos}


def _formato(valor, decimales=1):
    if valor is None:
        return "sin dato"
    return format(valor, ",.{}f".format(decimales)).translate(str.maketrans({",": ".", ".": ","}))


def _porcentaje(valor):
    return "sin dato" if valor is None else _formato(valor * 100) + " %"


def _tabla(encabezados, filas):
    # Todas las celdas son texto: ningún dato de entrada se interpreta como HTML.
    return ('<div class="tabla"><table><thead><tr>' +
            "".join("<th>" + escape(str(c)) + "</th>" for c in encabezados) +
            "</tr></thead><tbody>" +
            "".join("<tr>" + "".join("<td>" + escape(str(c)) + "</td>" for c in fila) + "</tr>" for fila in filas) +
            "</tbody></table></div>")


def riesgo_html(modelo):
    """Reporte interno autocontenido; no consulta recursos al abrirse."""
    m, p, cartera = modelo, modelo["parametros"], modelo["cartera"]
    partes = ['<!doctype html><html lang="es"><head><meta charset="utf-8">',
              '<meta name="viewport" content="width=device-width, initial-scale=1">',
              '<title>Riesgo de la cartera · ' + escape(m["cliente"]) + '</title>',
              '''<style>
              :root{color-scheme:light}*{box-sizing:border-box}body{margin:0;background:#f0f3f5;color:#243346;
              font:16px/1.55 -apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif}
              main{max-width:1280px;margin:auto;padding:40px 28px}header{border-bottom:3px solid #297978;
              padding-bottom:24px}h1{font-size:34px;line-height:1.2;margin:8px 0}h2{font-size:23px;margin:0 0 16px}
              h3{font-size:17px;margin-bottom:8px}section{background:white;padding:26px;margin-top:24px;
              border:1px solid #d5dde2;border-radius:8px}.etiqueta{color:#297978;font-weight:700;
              text-transform:uppercase;letter-spacing:.1em;font-size:12px}p{margin:8px 0 14px}
              .tabla{overflow-x:auto}table{border-collapse:collapse;width:100%;font-variant-numeric:tabular-nums;
              font-size:14px}th,td{text-align:right;border-bottom:1px solid #e2e8eb;padding:12px 10px;
              vertical-align:top}th{background:#eef4f4;font-size:12px}th:first-child,td:first-child{text-align:left}
              .aviso{padding:14px 18px;border-left:4px solid #ad7531;background:#fbf6ed}
              .indicadores{display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:14px}
              .indicador{border:1px solid #d5dde2;padding:16px;border-radius:6px}.indicador strong{display:block;
              font-size:26px;color:#1e6365}.detalle{font-size:14px;color:#526173}li{margin:6px 0}
              footer{font-size:13px;padding:24px 0;color:#526173}@media print{body{background:white}
              main{padding:0}section{border:0;border-radius:0;padding:18px 0}tr,.indicador{break-inside:avoid}
              h2,h3{break-after:avoid}.tabla{overflow:visible}table{font-size:10px}th,td{padding:7px 4px}}
              </style></head><body><main><header><span class="etiqueta">Uso interno del asesor</span>''',
              "<h1>Riesgo de la cartera</h1><p>" + escape(m["cliente"]) + "</p>",
              "<p>Tablero: {} · Datos: {} · Moneda: {} · CCL: {} ARS/USD</p>".format(
                  escape(m["fecha_tablero"]), escape(m["fecha_datos"]), escape(m["moneda"]), _formato(m["ccl"], 2)),
              '<p class="detalle">Ventana: {} ruedas; mínimo: {}; cobertura temporal mínima: {}. '
              'EWMA λ = {}; mínimo: {} retornos consecutivos. VaR y ES: {}, una rueda, media cero. '
              'Cola histórica: {} ruedas; mínimo: {}. Anualización: √{}.</p></header>'.format(
                  p["ventana"], p["minimo"], _porcentaje(p["cobertura_minima"]), _formato(p["lambda_ewma"], 2),
                  p["minimo_ewma"], _porcentaje(p["confianza"]), p["ventana_cola"], p["minimo_cola"], p["periodos"]),
              '<section><h2>Cómo leerlo</h2><ul>',
              '<li><b>Volatilidad:</b> dispersión anualizada de los retornos de precio, en ambas direcciones.</li>',
              '<li><b>VaR:</b> umbral de pérdida de una rueda al nivel de confianza indicado; no es una pérdida máxima.</li>',
              '<li><b>ES:</b> pérdida media en la fracción de escenarios que supera ese umbral.</li>',
              '<li><b>Contribución:</b> fracción de la volatilidad conjunta que explica cada posición; puede ser negativa.</li>',
              '<li><b>Beta:</b> sensibilidad frente al CEDEAR SPY en USD CCL; R² indica cuánto explica la regresión.</li>',
              '<li><b>Cobertura:</b> peso de las posiciones con historia suficiente sobre todas las posiciones valuadas.</li>',
              '</ul><p class="aviso">Lo excluido no tiene riesgo cero. El efectivo queda aparte y no entra '
              'en los pesos ni en estos cálculos.</p><p class="detalle">Retornos simples de cierre sin ajuste por '
              'dividendos; se excluyen pagos de renta fija y eventos conocidos. La cartera aplica los pesos '
              'actuales a shocks históricos; no representa el rendimiento realizado del cliente. '
              'EWMA usa retornos logarítmicos del último tramo sin huecos.</p></section>',
              '<section><h2>Cartera</h2><div class="indicadores">']
    indicadores = [("Cobertura patrimonial", _porcentaje(cartera["cobertura_patrimonial"])),
                   ("Patrimonio medido · USD CCL", _formato(cartera["valor_medido_usd"], 2)),
                   ("Volatilidad anual", _porcentaje(cartera["vol_anual"])),
                   ("VaR normal · USD", _formato(cartera["var95_usd"], 2)),
                   ("ES normal · USD", _formato(cartera["es95_usd"], 2))]
    for etiqueta, valor in indicadores:
        partes.append('<div class="indicador">{}<strong>{}</strong></div>'.format(escape(etiqueta), escape(valor)))
    partes.append('</div><p>Posiciones valuadas: {} ARS / {} USD CCL. Filas comunes: {}.</p>'.format(
        _formato(m["total_ars"], 2), _formato(m["total_usd"], 2), cartera["filas"]))
    if cartera["motivo"] is not None:
        partes.append('<p class="aviso">sin dato: ' + escape(cartera["motivo"]) + '</p>')
    peor = cartera["peor_dia"]
    partes.append(_tabla(["Indicador", "Valor"], [
        ["Beta frente a SPY (R²)", "{} ({})".format(_formato(cartera["beta"], 2), _porcentaje(cartera["r2"]))],
        ["Ratio de diversificación", _formato(cartera["ratio_diversificacion"], 2)],
        ["Correlación media", _formato(cartera["correlacion_media"], 2)],
        ["Peor día de lo medido", "{} · {}".format(peor["fecha"], _porcentaje(peor["retorno"])) if peor else "sin dato"],
    ]))
    historico = m["var_historico"]
    partes.append('<h3>VaR histórico</h3><p>{} filas comunes. VaR: {} USD · ES: {} USD.</p>'.format(
        historico["filas"], _formato(historico["var95_usd"], 2), _formato(historico["es95_usd"], 2)))
    if historico["motivo"] is not None:
        partes.append('<p class="aviso">sin dato: ' + escape(historico["motivo"]) + '</p>')
    partes.append('<p class="detalle">Cuantil empírico inverso; ES con peso fraccional de cola. '
                  'Los modelos normales pueden subestimar pérdidas extremas y dependencias de crisis.</p>')
    concentracion = m["concentracion"]
    partes.append('<h3>Concentración de todas las posiciones valuadas</h3>' + _tabla(
        ["Herfindahl", "Número efectivo", "Peso máximo", "Ticker"], [[
            _formato(concentracion["herfindahl"], 3), _formato(concentracion["numero_efectivo"], 2),
            _porcentaje(concentracion["peso_maximo"]), concentracion["ticker_maximo"] or "sin dato"]]) + '</section>')
    partes.append('<section><h2>Quién explica el riesgo</h2>')
    if cartera["contribuciones"]:
        partes.append(_tabla(["Ticker", "Peso dentro de lo medido", "Fracción del riesgo"], [
            [c["ticker"], _porcentaje(c["peso_medido"]), _porcentaje(c["fraccion"])] for c in cartera["contribuciones"]]))
    else:
        partes.append('<p>sin dato</p>')
    partes.append('</section><section><h2>Por especie</h2>')
    partes.append(_tabla(["Ticker", "Tipo", "Peso", "Vol. anual", "EWMA anual", "Beta (R²)", "VaR · USD", "Historia"], [
        [a["ticker"], a["tipo"], _porcentaje(a["peso"]), _porcentaje(a["vol_anual"]), _porcentaje(a["ewma_anual"]),
         "{} ({})".format(_formato(a["beta"], 2), _porcentaje(a["r2"])), _formato(a["var95_usd"], 2),
         a["historia"]["motivo"] or "{} / {} ruedas · {}".format(
             a["historia"]["n"], a["historia"]["ruedas"], _porcentaje(a["historia"]["cobertura"]))]
        for a in m["activos"]]))
    for activo in m["activos"]:
        if activo["excluidos"]:
            partes.append('<h3>' + escape(activo["ticker"]) + ': retornos excluidos en la ventana</h3><ul>')
            partes.extend('<li>{}: {}</li>'.format(escape(e["fecha"]), escape(e["motivo"])) for e in activo["excluidos"])
            partes.append('</ul>')
    partes.append('</section><section><h2>Renta fija</h2>')
    if m["renta_fija"]:
        partes.append(_tabla(["Familia / títulos", "Valor · ARS", "Duration", "Convexidad", "DV01 · ARS"] +
                             ["{:+g} pb · ARS".format(pb) for pb in p["escenarios_pb"]], [
            [r["familia"] + " / " + ", ".join(r["tickers"]), _formato(r["valor_ars"], 2), _formato(r["dm"], 2),
             _formato(r["cx"], 2), _formato(r["dv01_ars"], 2)] +
            [_formato(r["escenarios"][str(pb)], 2) for pb in p["escenarios_pb"]] for r in m["renta_fija"]]))
    else:
        partes.append('<p>sin dato</p>')
    partes.append('<p class="aviso">En CER, TAMAR y dólar linked, la duration mide la tasa real o el margen, '
                  'no el riesgo del índice. Cada familia tiene su propia curva.</p><p class="detalle">'
                  'Duration y convexidad: último cierre IAMC anterior o igual al tablero. DV01: sensibilidad '
                  'aproximada ante una suba de 1 pb. Los escenarios son aproximaciones de duration y convexidad '
                  'en pesos, no pronósticos. No se miden aquí crédito, liquidez ni el riesgo de los índices.</p></section>')
    partes.append('<section><h2>Fuera del cálculo y avisos</h2>')
    if cartera["excluidos"]:
        partes.append(_tabla(["Ticker", "Peso", "Motivo"], [
            [a["ticker"], _porcentaje(a["peso"]), a["motivo"]] for a in cartera["excluidos"]]))
    else:
        partes.append('<p>Sin posiciones excluidas por historia.</p>')
    partes.extend('<p class="aviso">' + escape(aviso) + '</p>' for aviso in m["avisos"])
    partes.append('</section><footer>Metodología: Administración de Carteras; convenciones y citas en '
                  'RIESGO_METODOLOGIA.md. Medición interna con datos de data912 e IAMC.</footer></main></body></html>')
    return "".join(partes)


def _escribir_atomico(ruta, contenido):
    ruta = Path(ruta)
    ruta.parent.mkdir(parents=True, exist_ok=True)
    temporal = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=ruta.parent,
                                         prefix=".riesgo-", suffix=".tmp", delete=False) as archivo:
            temporal = Path(archivo.name)
            archivo.write(contenido)
            archivo.flush()
            os.fsync(archivo.fileno())
        os.replace(str(temporal), str(ruta))
    finally:
        if temporal is not None:
            temporal.unlink(missing_ok=True)


def _preparar_historicos(claves, cache, fetch, hoy, sin_red):
    """Separa la consulta de la escritura para validar el comando antes de publicar."""
    cache = Path(cache)
    historicos, avisos, nuevos = {}, [], {}
    consultados = 0
    for clave in dict.fromkeys(claves):
        if not re.fullmatch(r"(?:cedears|stocks|bonds)/[A-Za-z0-9][A-Za-z0-9._-]*", clave):
            raise ErrorRiesgo("Clave de histórico inválida: {}.".format(clave))
        ruta = cache / (clave.replace("/", "_") + ".json")
        copia, vigente = None, False
        try:
            guardado = json.loads(ruta.read_text(encoding="utf-8"))
            if isinstance(guardado, dict) and "respuesta" in guardado:
                copia = guardado
                instante = datetime.fromisoformat(guardado.get("consultado_en", ""))
                vigente = instante.tzinfo is not None and instante.astimezone(_ZONA).date() == hoy
        except (OSError, ValueError, TypeError):
            pass
        if vigente or sin_red:
            historicos[clave] = copia["respuesta"] if copia is not None else None
            if copia is None:
                avisos.append("{}: sin copia guardada; no se pudo consultar data912 (sin red).".format(clave))
            elif not vigente:
                avisos.append("{}: se usa una copia de otra fecha (sin red).".format(clave))
            continue
        if consultados:
            time.sleep(0.5)
        consultados += 1
        try:
            respuesta = fetch("https://data912.com/historical/" + clave)
        except Exception:
            historicos[clave] = copia["respuesta"] if copia is not None else None
            avisos.append("{}: no se pudo consultar data912; {}.".format(
                clave, "se usa la copia guardada de otra fecha" if copia is not None else "sin copia guardada"))
        else:
            historicos[clave] = respuesta
            instante = datetime.combine(hoy, datetime.now(_ZONA).timetz())
            nuevos[ruta] = {"consultado_en": instante.isoformat(), "respuesta": respuesta}
    return historicos, avisos, nuevos


def _guardar_historicos(nuevos):
    for ruta, contenido in nuevos.items():
        _escribir_atomico(ruta, json.dumps(contenido, ensure_ascii=False, allow_nan=False))


def descargar_historicos(claves, cache, fetch=None, hoy=None, sin_red=False):
    """Obtiene copias del día, consulta las viejas y conserva el último dato ante fallas."""
    historicos, avisos, nuevos = _preparar_historicos(
        claves, cache, fetch if fetch is not None else consultar_json, hoy if hoy is not None else _hoy(), sin_red)
    _guardar_historicos(nuevos)
    return historicos, avisos


class _BloqueDashboard(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=False)
        self.en_bloque = False
        self.bloques = []

    def handle_starttag(self, etiqueta, atributos):
        if etiqueta == "script" and dict(atributos).get("id") == "datos-cartera":
            self.en_bloque = True
            self.bloques.append("")

    def handle_endtag(self, etiqueta):
        if etiqueta == "script":
            self.en_bloque = False

    def handle_data(self, texto):
        if self.en_bloque:
            self.bloques[-1] += texto


def _leer_dashboard(ruta):
    try:
        texto = Path(ruta).read_text(encoding="utf-8")
    except (OSError, UnicodeError):
        raise ErrorRiesgo("No se pudo leer dashboard.html; generalo con el comando dashboard.") from None
    lector = _BloqueDashboard()
    lector.feed(texto)
    if len(lector.bloques) != 1:
        raise ErrorRiesgo("El dashboard debe tener un único bloque datos-cartera válido.")
    try:
        datos = json.loads(lector.bloques[0])
    except ValueError:
        raise ErrorRiesgo("El bloque datos-cartera del dashboard no es JSON válido.") from None
    _validar_datos(datos)
    return datos


def _ultimo_cierre(raiz, fecha_tablero):
    avisos = []
    rutas = sorted((raiz / "iamc" / "cierres").glob("*.json"), reverse=True)
    for ruta in rutas:
        fecha = _fecha(ruta.stem)
        if fecha is None or fecha.isoformat() > fecha_tablero:
            continue
        try:
            _ruta_en_datos(ruta, raiz)
            cierre = json.loads(ruta.read_text(encoding="utf-8"))
            if not isinstance(cierre, dict) or cierre.get("fecha_cierre") != fecha.isoformat():
                raise ValueError("fecha de cierre inválida")
            _filas_iamc(cierre)
        except (OSError, ValueError, TypeError, AttributeError):
            avisos.append("IAMC {}: cierre ilegible o inválido; se busca uno anterior.".format(ruta.stem))
            continue
        return cierre, avisos
    return None, avisos


def _ruta_en_datos(ruta, raiz):
    if raiz not in ruta.resolve().parents:
        raise ErrorRiesgo("{} debe permanecer dentro de la carpeta de datos.".format(ruta.name))
    return ruta


def ejecutar_riesgo(opciones, datos):
    """Publica el modelo y su reporte con la fecha del tablero, sin necesitar la base."""
    from .almacenamiento import _ruta_cartera

    try:
        carpeta = _ruta_cartera(datos, opciones.cliente).parent
        raiz = Path(datos).expanduser().resolve()
        tablero = _leer_dashboard(_ruta_en_datos(carpeta / "dashboard.html", raiz))
        fecha_tablero = _validar_datos(tablero)
        destino = _ruta_en_datos(carpeta / "riesgo" / ("riesgo-" + fecha_tablero), raiz)
        cache = _ruta_en_datos(raiz / "cache" / "data912" / "historicos", raiz)
        _ruta_en_datos(raiz / "iamc" / "cierres", raiz)
        cierre, avisos_cierre = _ultimo_cierre(raiz, fecha_tablero)
        historicos, avisos_descarga, nuevos = _preparar_historicos(
            historicos_necesarios(tablero), cache,
            consultar_json, _hoy(), opciones.sin_red)
        modelo = armar_riesgo(tablero, historicos, cierre)
        modelo["avisos"].extend(avisos_cierre + avisos_descarga)
        serializado = json.dumps(modelo, ensure_ascii=False, indent=2, allow_nan=False) + "\n"
        html = riesgo_html(modelo)
        ruta_json, ruta_html = destino.with_suffix(".json"), destino.with_suffix(".html")
        _guardar_historicos(nuevos)
        _escribir_atomico(ruta_json, serializado)
        _escribir_atomico(ruta_html, html)
    except (ValueError, OSError) as error:
        print(str(error), file=sys.stderr)
        return 1
    print("Modelo guardado: {}".format(ruta_json))
    print("Reporte guardado: {}".format(ruta_html))
    cartera = modelo["cartera"]
    print("Cobertura: {} · volatilidad anual: {} · VaR: {} USD CCL.".format(
        _porcentaje(cartera["cobertura_patrimonial"]), _porcentaje(cartera["vol_anual"]), _formato(cartera["var95_usd"], 2)))
    if cartera["motivo"]:
        print("sin dato: " + cartera["motivo"])
    for aviso in modelo["avisos"]:
        print("ADVERTENCIA: " + aviso)
    return 0
