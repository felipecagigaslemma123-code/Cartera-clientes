"""Informe para el cliente a partir del último dashboard (etapa 12, docs/INFORME.md)."""

import json
import math
import os
import re
import subprocess
import sys
import tempfile
from datetime import date, datetime
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from html import escape
from pathlib import Path
from zoneinfo import ZoneInfo

_NAVEGADOR = Path("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome")
_ANTIGUEDAD_MAXIMA = 3
_FILAS_SIN_COMPACTAR = 15  # con más títulos, la tabla de la hoja 2 usa filas más bajas
_BLOQUE = re.compile(r'<script id="datos-cartera" type="application/json">(.*?)</script>', re.S)
_MESES = "ene feb mar abr may jun jul ago sep oct nov dic".split()
_CLASES_USD = ("Bonos en dólares", "Obligaciones negociables en dólares")
_FAMILIAS_LETRA = {"LECAP", "BONCAP", "LECER", "LELINK", "BONCER"}

# Paleta: dólares y títulos, pesos y positivos, negativos y acentos.
_AZUL, _VERDE, _CELESTE, _DORADO, _OLIVA, _ROJO = "#1f3a5f", "#3d8b8b", "#7fa7c9", "#c9a96e", "#a4b494", "#b5654a"
_COLORES_CLASE = [_AZUL, _VERDE, _CELESTE, _DORADO, _OLIVA, "#8c7aa9", "#9aa5b1", "#d4a5a5", "#6b8f71", "#b8b08d"]


class ErrorInforme(ValueError):
    """Datos insuficientes o inválidos para armar el informe."""


def _hoy():
    return datetime.now(ZoneInfo("America/Argentina/Buenos_Aires")).date()


# ---------------------------------------------------------------- lectura

def leer_datos_dashboard(ruta):
    ruta = Path(ruta)
    try:
        texto = ruta.read_text(encoding="utf-8")
    except OSError as error:
        raise ErrorInforme("No se pudo leer el dashboard {}: {}. Generalo con el comando dashboard.".format(
            ruta, error.strerror or error)) from None
    encontrado = _BLOQUE.search(texto)
    if encontrado is None:
        raise ErrorInforme("El dashboard {} no tiene el bloque datos-cartera. Generalo de nuevo.".format(ruta))
    try:
        datos = json.loads(encontrado.group(1))
    except ValueError:
        raise ErrorInforme("El bloque datos-cartera del dashboard {} no es JSON válido.".format(ruta)) from None
    if not isinstance(datos, dict) or not isinstance(datos.get("posiciones"), list):
        raise ErrorInforme("El dashboard {} no trae posiciones.".format(ruta))
    return datos


# ---------------------------------------------------------------- modelo

def _d(valor):
    if valor is None or isinstance(valor, bool):
        return None
    try:
        numero = Decimal(str(valor))
    except (InvalidOperation, ValueError):
        return None
    return numero if numero.is_finite() else None


def _f(valor):
    if not isinstance(valor, str) or len(valor) < 10:
        return None
    try:
        return date.fromisoformat(valor[:10])
    except ValueError:
        return None


def _division(a, b):
    return None if a is None or not b else a / b


def _clase(posicion, flujo, instrumentos):
    ticker, tipo = posicion.get("ticker"), posicion.get("tipo")
    config = instrumentos.get(ticker) if isinstance(instrumentos.get(ticker), dict) else {}
    iamc = config.get("iamc") if isinstance(config.get("iamc"), dict) else {}
    indice = iamc.get("indice") if isinstance(iamc.get("indice"), dict) else {}
    tipo_indice = indice.get("tipo")
    if tipo_indice in ("A3500", "DUAL"):
        return "Dólar linked"
    if tipo_indice == "CER":
        return "Ajustables por CER"
    if tipo_indice == "TAMAR":
        return "Tasa variable TAMAR"
    if tipo == "letra":
        return "Letras y BONCAP en pesos"
    posicion_flujo = flujo.get(ticker)
    if tipo in ("bono", "on") and posicion_flujo is not None:
        if posicion_flujo.get("moneda") == "USD":
            return "Obligaciones negociables en dólares" if tipo == "on" else "Bonos en dólares"
        return "Bonos en pesos"
    if tipo == "cedear":
        return "CEDEARs"
    if tipo == "accion":
        return "Acciones"
    return "Otros títulos"


def _verdadero(valor):
    return valor is True or valor == "True" or valor == "true"


def _capital_por_fecha(posicion):
    """Capital que devuelve cada pago futuro de la posición, sumando sus compras.

    Sin dato para una fecha si alguna compra no tiene la separación.
    """
    resultado, faltan = {}, set()
    for compra in posicion.get("compras") or []:
        if not isinstance(compra, dict):
            continue
        for pago in compra.get("pagos") or []:
            dia = _f(pago.get("fecha")) if isinstance(pago, dict) else None
            if dia is None or pago.get("estado") != "proyectado":
                continue
            capital = _d(pago.get("capital"))
            if capital is None:
                faltan.add(dia)
            else:
                resultado[dia] = resultado.get(dia, Decimal(0)) + capital
    return {dia: valor for dia, valor in resultado.items() if dia not in faltan}


def armar_informe(datos, instrumentos=None, perfil=None, cantidad_cobros=7):
    instrumentos = instrumentos if isinstance(instrumentos, dict) else {}
    perfil = perfil if isinstance(perfil, dict) else {}
    cliente = datos.get("cliente") if isinstance(datos.get("cliente"), dict) else {}
    fecha = _f(datos.get("generado_en"))
    ff = datos.get("flujo_fondos") if isinstance(datos.get("flujo_fondos"), dict) else {}
    flujo = {p["ticker"]: p for p in ff.get("posiciones") or [] if isinstance(p, dict) and p.get("ticker")}
    bloque_letras = datos.get("letras") if isinstance(datos.get("letras"), dict) else {}
    # Una letra ajustable (LECER, LELINK) va por el flujo de fondos: si figura en los dos bloques, gana el flujo.
    letras = {l["ticker"]: l for l in bloque_letras.get("posiciones") or []
              if isinstance(l, dict) and l.get("ticker") and l["ticker"] not in flujo}
    posiciones = [p for p in datos.get("posiciones") or [] if isinstance(p, dict) and p.get("ticker")]

    invertido = sum((_d(p.get("valuacion")) or Decimal(0) for p in posiciones), Decimal(0))
    clase_de = {p["ticker"]: _clase(p, flujo, instrumentos) for p in posiciones}

    grupos = {}
    for posicion in posiciones:
        grupos.setdefault(clase_de[posicion["ticker"]], []).append(posicion)
    composicion = []
    for nombre, miembros in grupos.items():
        miembros = sorted(miembros, key=lambda p: (-(_d(p.get("valuacion")) or 0), p["ticker"]))
        valuacion = sum((_d(p.get("valuacion")) or Decimal(0) for p in miembros), Decimal(0))
        composicion.append({"clase": nombre, "valuacion": valuacion, "peso": _division(valuacion, invertido),
                            "tickers": [p["ticker"] for p in miembros]})
    composicion.sort(key=lambda c: (-c["valuacion"], c["clase"]))
    orden_clase = {c["clase"]: i for i, c in enumerate(composicion)}
    en_dolares = sum((c["valuacion"] for c in composicion if c["clase"] in _CLASES_USD), Decimal(0))

    tenencia = []
    for posicion in sorted(posiciones, key=lambda p: (orden_clase[clase_de[p["ticker"]]],
                                                       -(_d(p.get("valuacion")) or 0), p["ticker"])):
        ticker = posicion["ticker"]
        letra = letras.get(ticker)
        descripcion = posicion.get("especie") or ticker
        if letra and _f(letra.get("vencimiento")) and letra.get("familia"):
            descripcion = "{} {}".format(letra["familia"], _f(letra["vencimiento"]).strftime("%d/%m/%Y"))
        valuacion = _d(posicion.get("valuacion"))
        costo = _d(posicion.get("costo"))
        tenencia.append({
            "ticker": ticker, "descripcion": descripcion, "clase": clase_de[ticker],
            "cantidad": _d(posicion.get("cantidad")), "precio": _d(posicion.get("ultimo")), "valuacion": valuacion,
            "peso": _division(valuacion, invertido),
            "vs_compra": _division(_d(posicion.get("resultado")), costo) if costo else None,
            "vencimiento": _f(posicion.get("vencimiento"))})
    orden_tenencia = {fila["ticker"]: i for i, fila in enumerate(tenencia)}

    rendimientos = []
    for ticker, posicion in flujo.items():
        compras = [c for c in posicion.get("compras") or [] if isinstance(c, dict)]
        con_tir = [(_d(c.get("tir")), _d(c.get("inversion"))) for c in compras]
        con_tir = [(t, i) for t, i in con_tir if t is not None and i]
        tir = (sum(t * i for t, i in con_tir) / sum(i for _, i in con_tir)) if con_tir else None
        proximo = posicion.get("proximo_pago") if isinstance(posicion.get("proximo_pago"), dict) else None
        rendimientos.append({
            "ticker": ticker, "moneda": posicion.get("moneda_etiqueta") or posicion.get("moneda"), "tir": tir,
            "tir_min": min((t for t, _ in con_tir), default=None), "tir_max": max((t for t, _ in con_tir), default=None),
            "estimada": any(_verdadero(c.get("tir_estimada")) for c in compras), "compras": len(compras),
            "proximo_pago": ({"fecha": _f(proximo.get("fecha")), "importe": _d(proximo.get("total"))}
                             if proximo else None),
            "total_a_cobrar": _d(posicion.get("total_proyectado")),
            "capital": _d(posicion.get("capital_pendiente")), "ganancia": _d(posicion.get("ganancia_pendiente"))})
    capital_por_letra = {}
    for ticker, letra in letras.items():
        lotes = [(_d(x.get("cantidad_restante")), _d(x.get("precio")), _d(x.get("tea")))
                 for x in letra.get("lotes") or [] if isinstance(x, dict)]
        pesados = [(c * p, t) for c, p, t in lotes if c and p and t is not None]
        pago_letra = _d(letra.get("pago_vencimiento"))
        capital_letra = (sum(c * p / 100 for c, p, _ in lotes)
                         if lotes and all(c and p for c, p, _ in lotes)
                         and sum(c for c, _, _ in lotes) == _d(letra.get("cantidad")) else None)
        capital_por_letra[ticker] = capital_letra
        rendimientos.append({
            "ticker": ticker, "moneda": letra.get("moneda_pago") or "ARS",
            "tir": (sum(w * t for w, t in pesados) / sum(w for w, _ in pesados)) if pesados else None,
            "tir_min": min((t for _, t in pesados), default=None), "tir_max": max((t for _, t in pesados), default=None),
            "estimada": False, "compras": len(lotes),
            "proximo_pago": {"fecha": _f(letra.get("vencimiento")), "importe": pago_letra},
            "total_a_cobrar": pago_letra, "capital": capital_letra,
            "ganancia": pago_letra - capital_letra if None not in (pago_letra, capital_letra) else None})
    rendimientos.sort(key=lambda r: (r["moneda"] == "ARS", orden_tenencia.get(r["ticker"], len(orden_tenencia)),
                                     r["ticker"]))

    a_cobrar, a_cobrar_capital = {}, {}
    for rendimiento in rendimientos:
        moneda = rendimiento["moneda"]
        if rendimiento["total_a_cobrar"] is not None and moneda:
            a_cobrar[moneda] = a_cobrar.get(moneda, Decimal(0)) + rendimiento["total_a_cobrar"]
            anterior = a_cobrar_capital.get(moneda, Decimal(0))
            # Si a un título le falta la separación, la de toda la moneda queda sin dato.
            a_cobrar_capital[moneda] = (None if anterior is None or rendimiento["capital"] is None
                                        else anterior + rendimiento["capital"])

    # Lo que se va a ganar: lo que se cobra por encima de lo invertido. Sin dato si a la moneda le falta la
    # separación; "estimada" si algún título de esa moneda depende de un índice proyectado.
    a_ganar = {mo: None if a_cobrar_capital.get(mo) is None else total - a_cobrar_capital[mo]
               for mo, total in a_cobrar.items()}
    a_ganar_estimada = {mo: any(r["estimada"] for r in rendimientos if r["moneda"] == mo) for mo in a_cobrar}

    vencimientos = {p["ticker"]: _f(p.get("vencimiento")) for p in posiciones}
    eventos = []
    for ticker, posicion in flujo.items():
        pagos = [p for p in posicion.get("pagos") or [] if isinstance(p, dict) and _f(p.get("fecha"))]
        final = vencimientos.get(ticker) or (max(_f(p["fecha"]) for p in pagos) if pagos else None)
        capital_por_fecha = _capital_por_fecha(posicion)
        for pago in pagos:
            if pago.get("estado") != "proyectado" or _d(pago.get("total")) is None:
                continue
            dia = _f(pago["fecha"])
            if dia == final:
                concepto = "Vencimiento"
            elif (_d(pago.get("amortizacion")) or 0) > 0:
                concepto = "Renta y amortización"
            else:
                concepto = "Renta"
            eventos.append({"fecha": dia, "ticker": ticker, "concepto": concepto,
                            "moneda": posicion.get("moneda_etiqueta") or posicion.get("moneda"),
                            "importe": _d(pago["total"]), "capital": capital_por_fecha.get(dia),
                            "estimado": str(pago.get("origen") or "").startswith("estimado")})
    for ticker, letra in letras.items():
        if _f(letra.get("vencimiento")) and _d(letra.get("pago_vencimiento")) is not None:
            eventos.append({"fecha": _f(letra["vencimiento"]), "ticker": ticker, "concepto": "Vencimiento",
                            "moneda": letra.get("moneda_pago") or "ARS", "importe": _d(letra["pago_vencimiento"]),
                            "capital": capital_por_letra.get(ticker), "estimado": False})
    # Capital que devuelve lo cobrado en cada año y moneda; sin dato si a algún pago le falta.
    cobros_por_anio_capital = {}
    for evento in eventos:
        anio = cobros_por_anio_capital.setdefault(str(evento["fecha"].year), {})
        anterior = anio.get(evento["moneda"], Decimal(0))
        anio[evento["moneda"]] = (None if anterior is None or evento["capital"] is None
                                  else anterior + evento["capital"])
    eventos = [e for e in eventos if fecha is None or e["fecha"] > fecha]
    eventos.sort(key=lambda e: (e["fecha"], e["ticker"]))

    cobros_por_anio = {}
    for mes in ff.get("calendario") or []:
        if not isinstance(mes, dict) or not isinstance(mes.get("proyectado"), dict) or not mes.get("mes"):
            continue
        anio = cobros_por_anio.setdefault(str(mes["mes"])[:4], {})
        for moneda, valor in mes["proyectado"].items():
            if _d(valor) is not None:
                anio[moneda] = anio.get(moneda, Decimal(0)) + _d(valor)

    integral = datos.get("integral") if isinstance(datos.get("integral"), dict) else None
    patrimonio = _d(integral.get("patrimonio_final")) if integral else None
    efectivo = None
    if integral and isinstance(integral.get("efectivo"), dict):
        efectivo = {moneda: _d(valor) for moneda, valor in integral["efectivo"].items()}

    resultados = None
    historial = datos.get("historial") if isinstance(datos.get("historial"), dict) else None
    if historial:
        ingresos = historial.get("ingresos") if isinstance(historial.get("ingresos"), dict) else {}

        def ingreso(clave, campo="equivalente_ars"):
            bloque = ingresos.get(clave) if isinstance(ingresos.get(clave), dict) else {}
            return _d(bloque.get(campo)) or Decimal(0)

        def equivalente(clave):
            bloque = historial.get(clave) if isinstance(historial.get(clave), dict) else {}
            return _d(bloque.get("equivalente_ars"))

        aportes, retiros = equivalente("aportes"), equivalente("retiros")
        operaciones = [{"ticker": r.get("ticker"), "fecha": _f(r.get("fecha")), "resultado": _d(r.get("resultado_ars"))}
                       for r in historial.get("realizados") or [] if isinstance(r, dict)]
        operaciones = sorted((o for o in operaciones if o["fecha"] and o["resultado"] is not None),
                             key=lambda o: (o["fecha"], o["ticker"] or ""))
        ganancia = _d(historial.get("total_conocido"))
        # El acumulado suma resultados en vez de restarle aportes al patrimonio: una tenencia anterior al
        # primer extracto o un título transferido desde otro broker entra sin aporte registrado, pero con su
        # costo de entrada. Así tampoco depende del día cero.
        sin_resultado = [p["ticker"] for p in posiciones if _d(p.get("resultado")) is None]
        no_realizado = None if sin_resultado else sum((_d(p["resultado"]) for p in posiciones), Decimal(0))
        ventas_dia_cero = [_d(r.get("resultado")) for r in datos.get("realizados") or [] if isinstance(r, dict)]
        sin_costo = sum(1 for valor in ventas_dia_cero if valor is None)
        cobros_dia_cero = Decimal(0)
        if integral:
            cobros_dia_cero = (sum((_d(integral.get(c)) or Decimal(0) for c in ("rentas", "dividendos", "amortizaciones")),
                                   Decimal(0)) - (_d(integral.get("gastos")) or Decimal(0)))
        desde_dia_cero = None if sin_costo else sum(ventas_dia_cero, Decimal(0)) + cobros_dia_cero
        incompletos = sum(int(_d(historial.get(c)) or 0)
                          for c in ("ventas_sin_dato", "valores_sin_dato", "cantidad_sin_clasificar"))
        faltantes = []
        if ganancia is None:
            faltantes.append("la ganancia realizada")
        if incompletos:
            faltantes.append("{} {} del historial sin resultado".format(
                incompletos, "operación" if incompletos == 1 else "operaciones"))
        if sin_resultado:
            faltantes.append("el costo o el precio de " + ", ".join(sin_resultado))
        if sin_costo:
            faltantes.append("el costo de {} {} desde el día cero".format(sin_costo, "venta" if sin_costo == 1 else "ventas"))
        # El desglose de la ganancia ya cobrada tiene que sumar exactamente el total: las ventas incluyen las
        # que salen de lotes estimados, y "otros" es lo que queda (dividendos, cauciones, fondos, retenciones,
        # compensaciones y gastos).
        extracto, estimado = _d(historial.get("realizado_extracto")), _d(historial.get("realizado_estimado"))
        ventas = None if extracto is None else extracto + (estimado or Decimal(0))
        rentas = ingreso("renta")
        dia_cero = datos.get("dia_cero") if isinstance(datos.get("dia_cero"), dict) else {}
        resultados = {
            "ganancia_realizada": ganancia,
            "ventas": ventas,
            "rentas_ars": ingreso("renta", "ARS"), "rentas_usd": ingreso("renta", "USD"),
            "rentas_equivalente": rentas,
            "otros": None if None in (ganancia, ventas) else ganancia - ventas - rentas,
            "aportes": aportes, "retiros": retiros,
            "tenencia": no_realizado, "desde_dia_cero": desde_dia_cero, "incompletos": incompletos,
            "cobrada": None if None in (ganancia, desde_dia_cero) else ganancia + desde_dia_cero,
            "dia_cero": _f(dia_cero.get("fecha")),
            "faltantes": faltantes,
            "acumulado": None if faltantes else ganancia + desde_dia_cero + no_realizado,
            "operaciones": operaciones}

    mep = datos.get("mep") if isinstance(datos.get("mep"), dict) else {}
    return {
        "cliente": perfil.get("nombre") or cliente.get("nombre") or cliente.get("slug"),
        "asesor": perfil.get("asesor") or None,
        "fecha": fecha, "mep": _d(mep.get("ultimo")),
        "patrimonio": patrimonio, "invertido": invertido, "efectivo": efectivo,
        "composicion": composicion, "peso_dolares": _division(en_dolares, invertido),
        "tenencia": tenencia, "rendimientos": rendimientos, "a_cobrar": a_cobrar,
        "a_cobrar_capital": a_cobrar_capital, "a_ganar": a_ganar, "a_ganar_estimada": a_ganar_estimada,
        "proximos_cobros": eventos[:cantidad_cobros], "cobros_por_anio": cobros_por_anio,
        "cobros_por_anio_capital": cobros_por_anio_capital,
        "resultados": resultados}


# ---------------------------------------------------------------- formato

def _n(valor, decimales=0):
    if valor is None:
        return "sin dato"
    redondeado = Decimal(valor).quantize(Decimal(1).scaleb(-decimales), rounding=ROUND_HALF_UP)
    texto = "{:,.{}f}".format(redondeado, decimales)
    return texto.replace(",", "X").replace(".", ",").replace("X", ".")


def _en_palabras(valor):
    """Un resultado con su signo dicho en palabras: "una pérdida de $ 1.234" se lee mejor que "$ -1.234"."""
    if valor > 0:
        return "una ganancia de $\u00a0" + _n(valor)
    if valor < 0:
        return "una pérdida de $\u00a0" + _n(-valor)
    return "un resultado nulo"


def _pct(valor, decimales=1):
    return "sin dato" if valor is None else _n(Decimal(valor) * 100, decimales) + " %"


def _fecha_larga(dia):
    return "—" if dia is None else "{} {} {}".format(dia.day, _MESES[dia.month - 1], dia.year)


def _es_usd(moneda):
    return bool(moneda) and moneda.startswith("USD")


def _monto(valor, moneda, sufijo=False):
    if valor is None:
        return "sin dato"
    if _es_usd(moneda):
        texto = "US$ " + _n(valor, 2)
        if sufijo:
            texto += " <small>{}</small>".format(escape(moneda.split()[1] if " " in moneda else ""))
        return texto
    return "$ " + _n(valor)


def _nombre_moneda(moneda):
    return {"ARS": "Pesos", "USD MEP": "Dólar MEP", "USD cable": "Dólar cable"}.get(moneda, moneda or "—")


def _moneda_corta(moneda):
    return {"ARS": "pesos", "USD MEP": "dólar MEP", "USD cable": "dólar cable"}.get(moneda, moneda or "")


# ---------------------------------------------------------------- gráficos

def _svg(ancho, alto, etiqueta, contenido):
    return '<svg viewBox="0 0 {} {}" width="100%" role="img" aria-label="{}">{}</svg>'.format(
        ancho, alto, escape(etiqueta), "".join(contenido))


def _dona(composicion, cantidad):
    radio, grosor = 64, 22
    centro = radio + grosor // 2 + 2
    total = sum(float(c["valuacion"]) for c in composicion)
    partes, angulo = [], -math.pi / 2
    for i, clase in enumerate(composicion):
        fraccion = float(clase["valuacion"]) / total if total else 0
        if fraccion <= 0:
            continue
        color = _COLORES_CLASE[i % len(_COLORES_CLASE)]
        if fraccion >= 0.9999:
            partes.append('<circle cx="{0}" cy="{0}" r="{1}" fill="none" stroke="{2}" stroke-width="{3}"/>'.format(
                centro, radio, color, grosor))
            break
        fin = angulo + 2 * math.pi * fraccion
        x1, y1 = centro + radio * math.cos(angulo), centro + radio * math.sin(angulo)
        x2, y2 = centro + radio * math.cos(fin), centro + radio * math.sin(fin)
        partes.append('<path d="M{:.2f},{:.2f} A{r},{r} 0 {} 1 {:.2f},{:.2f}" fill="none" stroke="{}" '
                      'stroke-width="{}"/>'.format(x1, y1, 1 if fin - angulo > math.pi else 0, x2, y2, color, grosor,
                                                   r=radio))
        angulo = fin
    partes.append('<text x="{0}" y="{1}" text-anchor="middle" class="d1">{2}</text>'
                  '<text x="{0}" y="{3}" text-anchor="middle" class="d2">{4}</text>'.format(
                      centro, centro - 4, cantidad, centro + 14, "posición" if cantidad == 1 else "posiciones"))
    lado = 2 * centro
    return '<svg viewBox="0 0 {0} {0}" width="{0}" height="{0}" role="img" aria-label="Composición">{1}</svg>'.format(
        lado, "".join(partes))


def _barras_tir(rendimientos):
    filas = [r for r in rendimientos if r["tir"] is not None]
    ancho, alto_fila, x0 = 640, 34, 120
    tope = max([0.1] + [float(r["tir_max"] or r["tir"]) for r in filas])
    tope = math.ceil(tope * 10 + 0.5) / 10
    escala = (ancho - x0 - 90) / tope
    contenido = []
    for i, r in enumerate(rendimientos):
        y = 14 + i * alto_fila
        color = _VERDE if r["moneda"] == "ARS" else _AZUL
        contenido.append('<text x="0" y="{}" class="bl">{}</text>'.format(y + 13, escape(r["ticker"])))
        contenido.append('<text x="0" y="{}" class="bs">{}</text>'.format(y + 26, escape(_moneda_corta(r["moneda"]))))
        if r["tir"] is None:
            contenido.append('<text x="{}" y="{}" class="bv">sin dato</text>'.format(x0, y + 17))
            continue
        largo = max(0.0, float(r["tir"])) * escala
        opacidad = ' fill-opacity="0.5"' if r["estimada"] else ""
        contenido.append('<rect x="{}" y="{}" width="{:.1f}" height="16" rx="3" fill="{}"{}/>'.format(
            x0, y + 4, largo, color, opacidad))
        if r["tir_min"] is not None and r["tir_max"] - r["tir_min"] > Decimal("0.002"):
            desde, hasta = x0 + max(0.0, float(r["tir_min"])) * escala, x0 + float(r["tir_max"]) * escala
            contenido.append('<path d="M{0:.1f},{2} V{3} M{0:.1f},{4} H{1:.1f} M{1:.1f},{2} V{3}" stroke="#5d6b78" '
                             'stroke-width="1.5" fill="none"/>'.format(desde, hasta, y + 7, y + 17, y + 12))
        etiqueta = _pct(r["tir"]) + (" estimada" if r["estimada"] else "")
        contenido.append('<text x="{:.1f}" y="{}" class="bv">{}</text>'.format(
            x0 + max(largo, float(r["tir_max"] or 0) * escala) + 8, y + 17, etiqueta))
    base = 14 + len(rendimientos) * alto_fila
    paso = 0.1 if tope <= 0.6 else 0.2
    marca = 0.0
    while marca <= tope + 1e-9:
        x = x0 + marca * escala
        contenido.append('<line x1="{0:.1f}" x2="{0:.1f}" y1="8" y2="{1}" class="grid"/>'.format(x, base))
        contenido.append('<text x="{:.1f}" y="{}" text-anchor="middle" class="ax">{} %</text>'.format(
            x, base + 12, int(round(marca * 100))))
        marca += paso
    # Las líneas de la grilla van detrás de las barras.
    grilla = [c for c in contenido if 'class="grid"' in c or 'class="ax"' in c]
    resto = [c for c in contenido if c not in grilla]
    return _svg(ancho, base + 18, "TIR de compra", grilla + resto)


def _barras_anuales(cobros_por_anio, monedas, colores, capital_por_anio=None, anio_actual=None):
    """Una barra por año y moneda. Con la separación, la parte de abajo devuelve lo invertido (color de la
    moneda) y la de arriba es ganancia (verde). El año en curso lleva "desde hoy" debajo: solo suma lo que
    falta cobrar, y un cliente lo leía como lo cobrado en el año."""
    capital_por_anio = capital_por_anio or {}
    anios = sorted(a for a, valores in cobros_por_anio.items() if any(valores.get(m) for m in monedas))
    if not anios:
        return None
    ancho, alto, base, x0 = 640, 160, 122, 8
    tope = max(float(cobros_por_anio[a].get(m, 0)) for a in anios for m in monedas) or 1
    paso = (ancho - x0) / len(anios)
    barra = paso * 0.62 / len(monedas)
    contenido = ['<line x1="{}" x2="{}" y1="{}" y2="{}" class="grid"/>'.format(x0, ancho, base, base)]
    for i, anio in enumerate(anios):
        for j, moneda in enumerate(monedas):
            valor = cobros_por_anio[anio].get(moneda)
            if not valor:
                continue
            alto_barra = max(2.0, float(valor) / tope * (base - 30))
            x = x0 + i * paso + paso * 0.19 + j * barra
            capital = capital_por_anio.get(anio, {}).get(moneda)
            if capital is None:
                contenido.append('<rect x="{:.1f}" y="{:.1f}" width="{:.1f}" height="{:.1f}" rx="2" fill="{}"/>'.format(
                    x, base - alto_barra, barra, alto_barra, colores[j]))
            else:
                parte = max(0.0, min(1.0, float(capital) / float(valor))) * alto_barra
                contenido.append('<rect x="{:.1f}" y="{:.1f}" width="{:.1f}" height="{:.1f}" rx="2" fill="{}"/>'.format(
                    x, base - alto_barra, barra, alto_barra, _VERDE))
                if parte > 0:
                    contenido.append('<rect x="{:.1f}" y="{:.1f}" width="{:.1f}" height="{:.1f}" fill="{}"/>'.format(
                        x, base - parte, barra, parte, colores[j]))
            contenido.append('<text x="{:.1f}" y="{:.1f}" text-anchor="middle" class="bv2">{}</text>'.format(
                x + barra / 2, base - alto_barra - 5, _n(valor)))
        contenido.append('<text x="{:.1f}" y="{}" text-anchor="middle" class="ax">{}</text>'.format(
            x0 + i * paso + paso / 2, base + 17, anio))
        if anio == anio_actual:
            contenido.append('<text x="{:.1f}" y="{}" text-anchor="middle" class="bs">desde hoy</text>'.format(
                x0 + i * paso + paso / 2, base + 30))
    return _svg(ancho, alto, "Cobros en dólares por año", contenido)


def _corto(valor):
    valor = float(valor)
    if abs(valor) >= 1e6:
        return _n(Decimal(str(valor / 1e6)), 1) + " M"
    return _n(Decimal(str(valor / 1e3))) + "k"


_MAXIMO_BARRAS = 14


def _agrupar_por_mes(operaciones):
    """Con muchas operaciones, una barra por mes con la suma del resultado."""
    meses = {}
    for operacion in operaciones:
        clave = operacion["fecha"].replace(day=1)
        meses[clave] = meses.get(clave, Decimal(0)) + operacion["resultado"]
    return [{"ticker": None, "fecha": mes, "resultado": total} for mes, total in sorted(meses.items())]


def _barras_resultados(operaciones):
    if len(operaciones) > _MAXIMO_BARRAS:
        operaciones = _agrupar_por_mes(operaciones)
    ancho, alto, medio, x0 = 640, 165, 88, 6
    tope = max(abs(float(o["resultado"])) for o in operaciones) or 1
    paso = (ancho - x0) / len(operaciones)
    barra = min(paso * 0.6, 48)
    contenido = ['<line x1="{}" x2="{}" y1="{}" y2="{}" class="grid"/>'.format(x0, ancho, medio, medio)]
    letra = 10.5 if len(operaciones) <= 14 else 8.5
    for i, operacion in enumerate(operaciones):
        valor = float(operacion["resultado"])
        alto_barra = abs(valor) / tope * 62
        x = x0 + i * paso + (paso - barra) / 2
        color = _VERDE if valor >= 0 else _ROJO
        y = medio - alto_barra if valor >= 0 else medio
        contenido.append('<rect x="{:.1f}" y="{:.1f}" width="{:.1f}" height="{:.1f}" rx="2" fill="{}"/>'.format(
            x, y, barra, alto_barra, color))
        y_texto = medio - alto_barra - 5 if valor >= 0 else medio + alto_barra + 13
        centro = x + barra / 2
        contenido.append('<text x="{:.1f}" y="{:.1f}" text-anchor="middle" class="bv2">{}</text>'.format(
            centro, y_texto, _corto(valor)))
        if operacion["ticker"]:
            contenido.append('<text x="{:.1f}" y="{}" text-anchor="middle" class="ax" style="font-size:{}px">{}</text>'
                             .format(centro, alto - 22, letra, escape(operacion["ticker"])))
        dia = operacion["fecha"]
        contenido.append('<text x="{:.1f}" y="{}" text-anchor="middle" class="bs">{} {}</text>'.format(
            centro, alto - 8, _MESES[dia.month - 1], str(dia.year)[2:]))
    return _svg(ancho, alto, "Resultados realizados", contenido)


# ---------------------------------------------------------------- HTML

_ESTILO = """
:root{--ink:#17222e;--mute:#5d6b78;--line:#e3e7ec;--soft:#f4f6f8;--navy:#1f3a5f;--teal:#3d8b8b;--neg:#b5654a}
*{box-sizing:border-box}
body{margin:0;background:#e9edf1;color:var(--ink);font:13px/1.45 -apple-system,BlinkMacSystemFont,"Helvetica Neue",Arial,sans-serif;-webkit-print-color-adjust:exact;print-color-adjust:exact}
.hoja{width:210mm;min-height:297mm;margin:16px auto;background:#fff;padding:13mm 15mm 16mm;position:relative;box-shadow:0 2px 14px rgba(0,0,0,.08)}
@page{size:A4;margin:0}
@media print{body{background:#fff}.hoja{margin:0;box-shadow:none;break-after:page}.hoja:last-child{break-after:auto}}
@media screen and (max-width:820px){.hoja{width:auto;min-height:0;margin:0 0 12px;padding:22px 16px}.kpis,.dos,.tres,.guia,.ecuacion,dl.glosario{grid-template-columns:1fr!important}.pie{position:static;margin-top:20px}}
.marca{display:flex;justify-content:space-between;align-items:flex-end;border-bottom:2px solid var(--navy);padding-bottom:8px;margin-bottom:14px}
.marca .firma{font-size:11px;letter-spacing:.14em;text-transform:uppercase;color:var(--navy);font-weight:700}
.marca .fecha{font-size:11px;color:var(--mute)}
h1{font-size:26px;margin:0 0 2px;font-weight:700;letter-spacing:-.01em}
.lead{color:var(--mute);margin:0 0 18px}
h2{font-size:14px;margin:18px 0 8px;color:var(--navy);text-transform:uppercase;letter-spacing:.06em}
h2.primero{margin-top:0}
h2 small{text-transform:none;letter-spacing:0;color:var(--mute);font-weight:400;font-size:12px;margin-left:6px}
.kpis{display:grid;grid-template-columns:1.4fr 1fr 1fr;gap:10px}
.tres{display:grid;grid-template-columns:repeat(3,1fr);gap:10px}
.kpi{background:var(--soft);border-radius:8px;padding:12px 14px}
.kpi.main{background:var(--navy);color:#fff}
.kpi .k{font-size:11px;text-transform:uppercase;letter-spacing:.06em;opacity:.75}
.kpi .v{font-size:22px;font-weight:700;margin-top:2px;font-variant-numeric:tabular-nums;white-space:nowrap}
.kpi.main .v{font-size:27px}
.kpi .s{font-size:11.5px;opacity:.8}
.dos{display:grid;grid-template-columns:170px 1fr;gap:18px;align-items:center}
.d1{font-size:26px;font-weight:700;fill:var(--ink)} .d2{font-size:11px;fill:var(--mute)}
ul.ley,ul.prox{list-style:none;margin:0;padding:0}
ul.ley li{display:grid;grid-template-columns:14px 1fr 64px 110px;gap:8px;align-items:center;padding:5px 0;border-bottom:1px solid var(--line)}
.sw{width:12px;height:12px;border-radius:3px} .lv{text-align:right;font-weight:700} .la{text-align:right;color:var(--mute);font-variant-numeric:tabular-nums}
table{width:100%;border-collapse:collapse;font-variant-numeric:tabular-nums}
tr{break-inside:avoid}
th{font-size:10.5px;text-transform:uppercase;letter-spacing:.05em;color:var(--mute);font-weight:600;text-align:left;padding:6px;border-bottom:1.5px solid var(--ink)}
td{padding:4px 6px;font-size:12px;border-bottom:1px solid var(--line);vertical-align:top}
.r{text-align:right;white-space:nowrap} th.r{text-align:right}
.sub{display:block;font-size:11px;color:var(--mute);font-weight:400}
.pos{color:var(--teal)} .neg{color:var(--neg)}
.nota{font-size:10.5px;color:var(--mute);margin-top:6px}
.callout{background:var(--soft);border-left:3px solid var(--teal);padding:8px 12px;border-radius:0 6px 6px 0;margin:10px 0}
svg text{font-family:inherit} .bl{font-size:13px;font-weight:700;fill:var(--ink)} .bs{font-size:10px;fill:var(--mute)}
.bv{font-size:12px;font-weight:600;fill:var(--ink)} .bv2{font-size:9.5px;fill:var(--ink)} .ax{font-size:10.5px;fill:var(--mute)}
.grid{stroke:#d5dbe1;stroke-width:1}
ul.prox li{display:grid;grid-template-columns:96px 62px 1fr auto;gap:10px;padding:4px 0;border-bottom:1px solid var(--line);align-items:baseline;break-inside:avoid}
.pf{color:var(--mute)} .pt{font-weight:700} .pk{color:var(--mute);font-size:12px} .pv{font-weight:700;text-align:right;font-variant-numeric:tabular-nums}
.pv small{font-weight:400;color:var(--mute)}
.leyb{display:flex;gap:16px;font-size:11.5px;color:var(--mute);margin:4px 0 0}
.leyb span:before{content:"";display:inline-block;width:10px;height:10px;border-radius:2px;margin-right:6px;background:var(--c)}
.parte{height:6px;border-radius:3px;background:var(--teal);margin:6px 0 5px;overflow:hidden}
.parte span{display:block;height:100%;background:#9aa8b6}
.guia-t{font-size:10.5px;text-transform:uppercase;letter-spacing:.08em;color:var(--mute);font-weight:700;margin:2px 0 6px}
.guia{display:grid;gap:8px;margin:0 0 18px}
.guia div{border:1px solid var(--line);border-radius:8px;padding:8px 10px;font-size:11.5px;color:var(--mute);line-height:1.35}
.guia b{display:block;color:var(--ink);font-size:12.5px;margin:6px 0 4px}
.guia .gk{display:block;font-size:10px;text-transform:uppercase;letter-spacing:.06em}
.guia .gv{display:block;color:var(--ink);font-size:17px;font-weight:700;margin:0 0 4px;font-variant-numeric:tabular-nums;line-height:1.25}
.guia .gv small{font-size:11px;font-weight:400;color:var(--mute)}
table.cobros td:first-child{white-space:nowrap} table.cobros th{white-space:normal;vertical-align:bottom}
table.titulos th{white-space:normal;vertical-align:bottom}
table.compacta td{padding:2px 6px;line-height:1.3} table.compacta .sub{font-size:10.5px}
.tag{display:inline-block;font-size:9.5px;letter-spacing:.08em;text-transform:uppercase;font-weight:700;color:var(--navy);border:1px solid var(--navy);border-radius:10px;padding:1px 8px}
.seccion{margin:0 0 14px;padding-bottom:10px;border-bottom:1px solid var(--line)}
.seccion .ts{font-size:20px;font-weight:700;margin:6px 0 2px;color:var(--ink)}
.seccion p{margin:0;color:var(--mute);font-size:12.5px}
.ecuacion{display:grid;grid-template-columns:1fr 26px 1fr 26px 1fr;gap:6px;align-items:stretch}
.ecuacion .kpi.main .v{font-size:24px}
.op{display:flex;align-items:center;justify-content:center;font-size:24px;font-weight:700;color:var(--mute)}
ul.desglose{list-style:none;margin:0;padding:0}
ul.desglose li{display:grid;grid-template-columns:1fr auto;gap:14px;padding:6px 0;border-bottom:1px solid var(--line);break-inside:avoid}
ul.desglose li.total{border-bottom:none;border-top:1.5px solid var(--ink)}
.dv{font-weight:700;text-align:right;font-variant-numeric:tabular-nums;white-space:nowrap}
.aclara{font-size:12px;color:var(--mute);margin:0}
dl.glosario{display:grid;grid-template-columns:1fr 1fr;gap:0 26px;margin:0}
dl.glosario div{break-inside:avoid;padding:6px 0;border-bottom:1px solid var(--line)}
dl.glosario dt{font-weight:700;font-size:12px} dl.glosario dd{margin:1px 0 0;font-size:11.5px;color:var(--mute)}
.pie{position:absolute;left:15mm;right:15mm;bottom:9mm;font-size:9.5px;color:var(--mute);display:flex;justify-content:space-between;border-top:1px solid var(--line);padding-top:6px}
"""


def _hoja(asesor, titulo, fecha, cuerpo):
    return ('<section class="hoja"><div class="marca"><div class="firma">{}</div><div class="fecha">{} · {}</div></div>'
            '{}<div class="pie"><span>{}Uso exclusivo del cliente</span><span>{}</span></div></section>').format(
                escape(asesor or ""), escape(titulo), _fecha_larga(fecha), cuerpo,
                escape(asesor) + " · " if asesor else "", escape(titulo))


def _kpi(titulo, valor, detalle, principal=False):
    return '<div class="kpi{}"><div class="k">{}</div><div class="v">{}</div><div class="s">{}</div></div>'.format(
        " main" if principal else "", escape(titulo), valor, detalle)


def _pesos(valor):
    """Importe en pesos con el signo delante del símbolo: "−$ 1.234" y no "$ -1.234"."""
    if valor is None:
        return "sin dato"
    return "−$ " + _n(-valor) if valor < 0 else "$ " + _n(valor)


def _partes_cobro(total, capital, moneda):
    """Barra y texto con la parte que devuelve lo invertido y la que es ganancia."""
    if capital is None or not total or total <= 0:
        return ""
    ganancia = total - capital
    proporcion = max(Decimal(0), min(Decimal(1), capital / total)) * 100
    return ('<div class="parte" role="img" aria-label="Devuelve lo invertido y ganancia">'
            '<span style="width:{:.1f}%"></span></div>{} devuelve lo invertido · <b>{}</b> de ganancia').format(
                proporcion, _monto(capital, moneda), _monto(ganancia, moneda))


def _detalle_capital(evento):
    # En una renta, el capital es solo el interés corrido de una compra: no se detalla.
    capital = evento.get("capital")
    if evento["concepto"] == "Renta" or capital is None or capital <= 0:
        return ""
    ganancia = evento["importe"] - capital if evento["importe"] is not None else None
    if ganancia is None:
        return ""
    return " ({} de ganancia)".format(_monto(ganancia, evento["moneda"]))


# Las partes del informe, en el orden en que se leen. Cada una dice a qué momento mira: es lo que más confunde a
# un cliente sin experiencia, que tomaba los cobros futuros por ganancias pasadas (pedido de Felipe, 18/11/2026).
_PARTES = {
    "hoy": ("Hoy", "Tu cartera hoy", "Qué tenés y cuánto vale."),
    "pasado": ("Hasta hoy", "Lo que ya ganaste", "El resultado desde que empezaste a invertir."),
    "futuro": ("De acá en adelante", "Lo que vas a ganar desde hoy",
               "Lo que vas a cobrar por encima de lo que pusiste. Todavía no lo cobraste."),
}


def _nombre(parte, m):
    """Título de la parte. Con resultado total negativo, "Lo que ya ganaste" contradice al número: la parte 2 pasa a
    llamarse "Tu resultado hasta hoy" (pedido de Felipe, 19/11/2026)."""
    if parte == "pasado" and m["resultados"] is not None:
        acumulado = m["resultados"]["acumulado"]
        if acumulado is not None and acumulado < 0:
            return "Tu resultado hasta hoy"
    return _PARTES[parte][1]


def _numeros(modelo):
    """Número de cada parte presente; una parte sin datos no se muestra ni se cuenta."""
    numeros = {"hoy": 1}
    if modelo["resultados"] is not None:
        numeros["pasado"] = len(numeros) + 1
    if modelo["rendimientos"] or modelo["proximos_cobros"]:
        numeros["futuro"] = len(numeros) + 1
    return numeros


def _seccion(parte, numeros, texto, titulo=None):
    etiqueta, nombre, _ = _PARTES[parte]
    return '<div class="seccion"><span class="tag">{}</span><div class="ts">{}. {}</div><p>{}</p></div>'.format(
        escape(etiqueta), numeros[parte], escape(titulo or nombre), texto)


def _guia(m, numeros):
    """Resumen de la primera hoja: las partes del informe, cada una con su momento y su número principal."""
    if len(numeros) < 2:
        return ""
    cifras = {"hoy": "$ " + _n(m["patrimonio"]) if m["patrimonio"] is not None else "$ " + _n(m["invertido"])}
    if "pasado" in numeros:
        cifras["pasado"] = _pesos(m["resultados"]["acumulado"])
    if "futuro" in numeros:
        # La ganancia y no el total a cobrar: el total incluye lo que vuelve de lo invertido y el cliente lo
        # leía como ganancia. Cada moneda en su renglón, sin sumarlas.
        orden = sorted(m["a_ganar"], key=lambda mo: ({"ARS": 0, "USD MEP": 1, "USD cable": 2}.get(mo, 3), mo))
        renglones = []
        for mo in orden:
            valor = m["a_ganar"][mo]
            texto = (_monto(valor, mo, sufijo=True) if valor is not None
                     else "sin dato <small>{}</small>".format(escape(_moneda_corta(mo))))
            if valor is not None and m["a_ganar_estimada"].get(mo):
                texto += " <small>incluye estimados</small>"
            renglones.append(texto)
        cifras["futuro"] = "<br>".join(renglones) or "sin dato"
    rotulos = {"hoy": "Patrimonio" if m["patrimonio"] is not None else "Invertido en títulos",
               "pasado": "Resultado total hasta hoy", "futuro": "Ganancia en cada moneda"}
    tarjetas = "".join(
        '<div><span class="tag">{}</span><b>{}. {}</b><span class="gk">{}</span><span class="gv">{}</span>{}</div>'.format(
            escape(_PARTES[parte][0]), numeros[parte], escape(_nombre(parte, m)), escape(rotulos[parte]),
            cifras[parte], escape(_PARTES[parte][2]))
        for parte in ("hoy", "pasado", "futuro") if parte in numeros)
    return ('<div class="guia-t">Este informe en {} partes</div>'
            '<div class="guia" style="grid-template-columns:repeat({},1fr)">{}</div>'.format(
                "dos" if len(numeros) == 2 else "tres", len(numeros), tarjetas))


def _hoja_hoy(m, numeros):
    patrimonio, mep, efectivo = m["patrimonio"], m["mep"], m["efectivo"]
    equivalente = ("Equivale a US$ {} al dólar MEP".format(_n(patrimonio / mep))
                   if patrimonio is not None and mep else "")
    peso_invertido = _division(m["invertido"], patrimonio)
    pesos = (efectivo or {}).get("ARS")
    dolares = (efectivo or {}).get("USD")
    cuerpo = ['<h1>{}</h1>'.format(escape(m["cliente"] or "")),
              '<p class="lead">Informe al {}, con precios de mercado{}.</p>'.format(
                  _fecha_larga(m["fecha"]), " y dólar MEP de $ {}".format(_n(mep, 2)) if mep else ""),
              _guia(m, numeros),
              _seccion("hoy", numeros, "Todo lo que tenés en tu cuenta al {}, valuado a los precios de ese día.".format(
                  _fecha_larga(m["fecha"]))),
              '<div class="kpis">',
              _kpi("Patrimonio total", "$ " + _n(patrimonio) if patrimonio is not None else "sin dato",
                   "Todo lo que tenés en la cuenta" + ("<br>" + equivalente if equivalente else ""), True),
              _kpi("Invertido en títulos", "$ " + _n(m["invertido"]),
                   "Lo que valen hoy tus títulos" + ("<br>{} del patrimonio".format(_pct(peso_invertido))
                                                      if peso_invertido is not None else "")),
              _kpi("Efectivo disponible", "$ " + _n(pesos) if pesos is not None else "sin dato",
                   "Plata en la cuenta, sin invertir" + ("<br>y US$ " + _n(dolares, 2) if dolares is not None else "")),
              '</div>']
    if m["composicion"] and m["invertido"]:
        leyenda = "".join(
            '<li><span class="sw" style="background:{}"></span><span>{}</span><span class="lv">{}</span>'
            '<span class="la">$ {}</span></li>'.format(_COLORES_CLASE[i % len(_COLORES_CLASE)], escape(c["clase"]),
                                                       _pct(c["peso"]), _n(c["valuacion"]))
            for i, c in enumerate(m["composicion"]))
        cuerpo += ['<h2>Composición <small>cómo se reparte lo que tenés en títulos</small></h2>'
                   '<div class="dos"><div>{}</div><ul class="ley">{}</ul></div>'.format(
                       _dona(m["composicion"], len(m["tenencia"])), leyenda)]
        frases = []
        if m["peso_dolares"]:
            frases.append("<b>{} de tu cartera está en títulos que pagan en dólares</b> (bonos y obligaciones "
                          "negociables en dólares).".format(_pct(m["peso_dolares"])))
        cedears = next((c["peso"] for c in m["composicion"] if c["clase"] == "CEDEARs"), None)
        if cedears:
            frases.append("Los CEDEARs ({}) cotizan en pesos, pero su precio sigue al dólar.".format(_pct(cedears)))
        if frases:
            cuerpo.append('<div class="callout">{}</div>'.format(" ".join(frases)))
    return _hoja(m["asesor"], "Informe de cartera", m["fecha"], "".join(cuerpo))


def _hoja_titulos(m, numeros):
    filas = []
    for f in m["tenencia"]:
        variacion = f["vs_compra"]
        clase = "" if variacion is None or variacion == 0 else (" pos" if variacion > 0 else " neg")
        filas.append('<tr><td><b>{}</b><span class="sub">{}</span></td><td class="r">{}</td><td class="r">{}</td>'
                     '<td class="r">{}</td><td class="r">{}</td><td class="r{}">{}</td><td class="r">{}</td></tr>'.format(
                         escape(f["ticker"]), escape(f["descripcion"]), _n(f["cantidad"]),
                         "$ " + _n(f["precio"], 2) if f["precio"] is not None else "sin dato",
                         "$ " + _n(f["valuacion"]) if f["valuacion"] is not None else "sin dato",
                         _pct(f["peso"]), clase, _pct(variacion) if variacion is not None else "—",
                         _fecha_larga(f["vencimiento"])))
    if not filas:
        return None
    cuerpo = [_seccion("hoy", numeros, "Cuánto vale hoy cada título y cuánto cambió desde que lo compraste.",
                       titulo="Tu cartera hoy, título por título"),
              '<h2 class="primero">Tus títulos</h2>'
              '<table class="titulos{}"><thead><tr><th>Título</th><th class="r">Cantidad</th>'
              '<th class="r">Precio</th><th class="r">Valuación</th><th class="r">Peso</th>'
              '<th class="r">Desde la compra</th><th class="r">Vence</th></tr></thead><tbody>{}</tbody></table>'
              '<p class="nota">Desde la compra: cuánto subió o bajó lo que vale cada título frente a lo que '
              'pagaste, en pesos. Es una ganancia o una pérdida en papel: se concreta cuando lo vendés o '
              'cuando vence. No incluye las rentas que ya cobraste. El precio de los bonos y las letras es '
              'por cada 100 nominales.</p>'.format(
                  # Con muchos títulos, filas más bajas para que la tabla y su nota entren en la hoja.
                  " compacta" if len(filas) > _FILAS_SIN_COMPACTAR else "", "".join(filas))]
    return _hoja(m["asesor"], "Tu cartera hoy", m["fecha"], "".join(cuerpo))


def _hoja_pasado(m, numeros):
    r = m["resultados"]
    if r is None:
        return None
    adelante = (" Los pagos que todavía no cobraste están en la parte {}.".format(numeros["futuro"])
                if "futuro" in numeros else "")
    partes = [_seccion("pasado", numeros, "Lo que ganaste o perdiste desde que empezaste a invertir hasta hoy. "
                                          "Esta parte mira hacia atrás." + adelante, titulo=_nombre("pasado", m))]
    detalle = "En ventas, vencimientos, rentas y dividendos"
    if r["incompletos"]:
        detalle += "<br>suma lo conocido · {} sin dato".format(r["incompletos"])
    tenencia = r["tenencia"]
    if tenencia is None:
        signo, caja = "+", _kpi("Lo que todavía tenés", "sin dato", "Falta el costo o el precio de algún título")
    else:
        signo = "+" if tenencia >= 0 else "−"
        caja = _kpi("{} de lo que todavía tenés".format("Suba" if tenencia >= 0 else "Baja"), "$ " + _n(abs(tenencia)),
                    "Lo que valen hoy tus títulos frente a lo que pagaste. Todavía no es plata cobrada")
    perdida = r["acumulado"] is not None and r["acumulado"] < 0
    partes.append('<div class="ecuacion">{}<div class="op">{}</div>{}<div class="op">=</div>{}</div>'.format(
        _kpi("Ganancia ya cobrada", _pesos(r["cobrada"]), detalle), signo, caja,
        _kpi("Resultado total hasta hoy", _pesos(r["acumulado"]),
             "Lo que {} desde que empezaste".format("perdiste" if perdida else "ganaste"), True)))

    filas = [("Ventas y vencimientos", r["ventas"],
              "Lo que recibiste al vender un título o cuando venció, menos lo que habías pagado por él."),
             ("Rentas", r["rentas_equivalente"],
              "Lo que te pagaron tus bonos en intereses{}.".format(
                  ", incluidos US$ {} convertidos al dólar MEP del día de cada cobro".format(_n(r["rentas_usd"], 2))
                  if r["rentas_usd"] else "")),
             ("Dividendos, cauciones y otros", r["otros"],
              "Dividendos de acciones y CEDEARs, cauciones y fondos, menos gastos e impuestos.")]
    if r["desde_dia_cero"]:
        filas.append(("Desde el " + _fecha_larga(r["dia_cero"]) if r["dia_cero"] else "Desde el día cero",
                      r["desde_dia_cero"], "Ventas y cobros registrados después del último extracto."))
    items = "".join('<li><span><b>{}</b><span class="sub">{}</span></span><span class="dv">{}</span></li>'.format(
        escape(titulo), texto, _pesos(valor)) for titulo, valor, texto in filas)
    items += '<li class="total"><span><b>Ganancia ya cobrada</b></span><span class="dv">{}</span></li>'.format(
        _pesos(r["cobrada"]))
    partes.append('<h2>De dónde sale la ganancia ya cobrada</h2><ul class="desglose">{}</ul>'.format(items))

    if r["operaciones"]:
        agrupado = len(r["operaciones"]) > _MAXIMO_BARRAS
        partes.append('<h2>Ganancia o pérdida en lo que vendiste o venció <small>{}</small></h2>{}'.format(
            "por mes" if agrupado else "una barra por título", _barras_resultados(r["operaciones"])))
        partes.append('<p class="nota">Cada barra compara lo que recibiste al vender un título (o cuando venció) con lo '
                      'que habías pagado por él: hacia arriba, ganancia; hacia abajo, pérdida. No incluye rentas ni '
                      'dividendos.{}</p>'.format(" {} operaciones, agrupadas por mes.".format(len(r["operaciones"]))
                                                 if agrupado else ""))
    if r["acumulado"] is None:
        explicacion = "Resultado total: sin dato; falta {}.".format(escape("; ".join(r["faltantes"])))
    else:
        explicacion = ("Resultado total hasta hoy: la ganancia ya cobrada más {} en lo que todavía tenés, frente a lo "
                       "que pagaste. No incluye la variación del dólar sobre el efectivo en dólares.".format(
                           _en_palabras(r["tenencia"])))
    partes.append('<p class="nota" id="nota-resultado">{} Los importes están en pesos de cada momento, sin ajuste por '
                  'inflación.</p>'.format(explicacion))
    return _hoja(m["asesor"], _nombre("pasado", m), m["fecha"], "".join(partes))


def _hoja_futuro(m, numeros):
    if "futuro" not in numeros:
        return None
    partes = [_seccion("futuro", numeros,
                       "Los pagos que tus bonos y letras van a hacer desde hoy hasta que vencen. Una parte te devuelve "
                       "lo que pusiste y el resto es tu ganancia. <b>Todavía no los cobraste</b>: son pagos futuros y "
                       "dependen de que cada emisor pague.")]
    if m["proximos_cobros"]:
        items = "".join(
            '<li><span class="pf">{}</span><span class="pt">{}</span><span class="pk">{}{}{}</span>'
            '<span class="pv">{}</span></li>'.format(
                _fecha_larga(e["fecha"]), escape(e["ticker"]), escape(e["concepto"]),
                " · estimado" if e["estimado"] else "", _detalle_capital(e),
                _monto(e["importe"], e["moneda"], sufijo=True))
            for e in m["proximos_cobros"])
        partes.append('<h2>Próximos cobros <small>los pagos más cercanos, en orden de fecha</small></h2>'
                      '<ul class="prox">{}</ul>'
                      '<p class="nota"><b>Renta</b>: intereses. <b>Amortización</b>: te devuelven una parte de lo '
                      'invertido. <b>Vencimiento</b>: el último pago, que devuelve lo que queda. Entre paréntesis, '
                      'cuánto de ese pago es ganancia; el resto te devuelve lo invertido. <b>Estimado</b>: el importe '
                      'depende de cómo sigan la inflación, la tasa o el dólar.</p>'.format(items))
    if m["rendimientos"]:
        partes.append('<h2>Rendimiento al precio de compra <small>ganancia anual si mantenés cada título hasta que '
                      'vence</small></h2>{}'
                      '<p class="nota">Es la tasa anual que ganás con cada título si lo mantenés hasta el vencimiento, '
                      'según el precio al que lo compraste: no cambia con el precio de hoy. Si compraste varias veces, '
                      'se muestra el promedio y la línea fina marca el rango entre compras. Bonos en dólares: tasa en '
                      'dólares. Letras y bonos en pesos: tasa en pesos. Estimada: depende de la inflación, la tasa '
                      'TAMAR o el dólar que vengan, según lo que esperan los analistas que consulta el BCRA.</p>'.format(
                          _barras_tir(m["rendimientos"])))
    return _hoja(m["asesor"], "Lo que vas a ganar desde hoy", m["fecha"], "".join(partes))


def _hoja_futuro_titulos(m, numeros):
    if "futuro" not in numeros or not m["rendimientos"]:
        return None
    filas = []
    for r in m["rendimientos"]:
        proximo = r["proximo_pago"] or {}
        filas.append('<tr><td><b>{}</b><span class="sub">{} compra{} · {}</span></td>'
                     '<td class="r">{}<span class="sub">{}</span></td><td class="r"><b>{}</b></td>'
                     '<td class="r">{}</td><td class="r pos">{}</td><td class="r"><b>{}</b>{}</td></tr>'.format(
                         escape(r["ticker"]), r["compras"], "" if r["compras"] == 1 else "s",
                         escape(_moneda_corta(r["moneda"])), _fecha_larga(proximo.get("fecha")),
                         _monto(proximo.get("importe"), r["moneda"]), _monto(r["total_a_cobrar"], r["moneda"]),
                         _monto(r["capital"], r["moneda"]), _monto(r["ganancia"], r["moneda"]),
                         _pct(r["tir"]), '<span class="sub">estimada</span>' if r["estimada"] else ""))
    detalle = {"ARS": "letras y títulos en pesos", "USD MEP": "títulos que pagan en dólar MEP",
               "USD cable": "títulos que pagan en dólar cable"}
    orden = sorted(m["a_cobrar"], key=lambda mo: ({"ARS": 0, "USD MEP": 1, "USD cable": 2}.get(mo, 3), mo))
    totales = "".join(_kpi("A cobrar en " + _moneda_corta(mo), _monto(m["a_cobrar"][mo], mo),
                           _partes_cobro(m["a_cobrar"][mo], m["a_cobrar_capital"].get(mo), mo)
                           or escape(detalle.get(mo, "")))
                      for mo in orden)
    partes = [_seccion("futuro", numeros, "Cuánto te va a pagar cada título de acá a su vencimiento, cuánto de eso es "
                                          "ganancia y en qué año lo vas a cobrar.",
                       titulo="Lo que vas a ganar desde hoy, título por título"),
              '<h2 class="primero">Cobros futuros por título</h2><table class="cobros"><thead><tr><th>Título</th>'
              '<th class="r">Próximo pago</th><th class="r">Total a cobrar desde hoy</th>'
              '<th class="r">Devuelve lo invertido</th><th class="r">Ganancia</th><th class="r">TIR de compra</th>'
              '</tr></thead><tbody>{}</tbody></table>'
              '<p class="nota">Total a cobrar desde hoy: todo lo que te va a pagar cada título de acá a su vencimiento, '
              'en intereses y devolución del capital, para lo que tenés hoy. No todo es ganancia: una parte te devuelve '
              'lo que pagaste al comprar. La ganancia es lo que cobrás por encima: los intereses y la diferencia por '
              'haber comprado por debajo de lo que paga el título (en uno ajustable, también el ajuste por el índice). '
              'Cada moneda se suma por separado.</p>'
              '<div class="tres" style="margin-top:12px">{}</div>'.format("".join(filas), totales)]
    monedas = [mo for mo in ("USD MEP", "USD cable") if any(v.get(mo) for v in m["cobros_por_anio"].values())]
    anio_actual = str(m["fecha"].year) if m["fecha"] else None
    grafico = (_barras_anuales(m["cobros_por_anio"], monedas, [_AZUL, _CELESTE][:len(monedas)],
                               m.get("cobros_por_anio_capital"), anio_actual) if monedas else None)
    if grafico:
        separado = any(valor is not None for anio in (m.get("cobros_por_anio_capital") or {}).values()
                       for mo, valor in anio.items() if mo in monedas)
        sufijo = ": devuelve lo invertido" if separado else ""
        leyenda = "".join('<span style="--c:{}">{}{}</span>'.format(c, _nombre_moneda(mo), sufijo)
                          for mo, c in zip(monedas, (_AZUL, _CELESTE)))
        if separado:
            leyenda += '<span style="--c:{}">Ganancia</span>'.format(_VERDE)
        en_curso = any((m["cobros_por_anio"].get(anio_actual) or {}).get(mo) for mo in monedas)
        hoy = (" {} muestra solo lo que falta cobrar desde el {}.".format(anio_actual, _fecha_larga(m["fecha"]))
               if en_curso else "")
        partes.append('<h2>Cobros futuros en dólares, año por año</h2>{}<div class="leyb">{}</div>'
                      '<p class="nota">Lo que vas a cobrar cada año de los títulos que pagan en dólares, desde hoy hasta '
                      'su vencimiento. <b>No incluye lo que ya cobraste.</b>{}{} Lo que vas a cobrar en pesos está en el '
                      'total «A cobrar en pesos».</p>'.format(
                          grafico, leyenda, hoy, " En cada barra, la parte verde es ganancia y el resto te devuelve lo "
                          "invertido." if separado else ""))
    return _hoja(m["asesor"], "Lo que vas a ganar desde hoy", m["fecha"], "".join(partes))


def _glosario(m):
    """Palabras del informe, solo las que aparecen en esta cartera."""
    clases = {c["clase"] for c in m["composicion"]}
    monedas = {r["moneda"] for r in m["rendimientos"]}
    terminos = []
    if m["rendimientos"]:
        terminos += [
            ("Renta", "Los intereses que paga un bono."),
            ("Amortización", "La devolución de una parte de lo invertido en un bono, antes del vencimiento."),
            ("Vencimiento", "La fecha del último pago de un título: ese día devuelve lo que queda del capital."),
            ("TIR", "Tasa interna de retorno: la ganancia anual que obtenés si mantenés un título hasta el "
                    "vencimiento, según el precio al que lo compraste."),
            ("Nominales", "La unidad en la que se cuenta un bono o una letra. Su precio se expresa cada 100 nominales."),
        ]
    terminos.append(("Dólar MEP", "El dólar que se obtiene comprando un bono con pesos y vendiéndolo en dólares, en "
                                  "el mercado local. Con él se pasan a dólares los importes de este informe."))
    if "USD cable" in monedas:
        terminos.append(("Dólar cable", "Dólares que se cobran en una cuenta del exterior."))
    if "CEDEARs" in clases:
        terminos.append(("CEDEAR", "Certificado que representa acciones de una empresa del exterior. Cotiza en pesos "
                                   "y su precio sigue al dólar."))
    if "Obligaciones negociables en dólares" in clases:
        terminos.append(("Obligación negociable", "Un bono emitido por una empresa."))
    if "Letras y BONCAP en pesos" in clases:
        terminos.append(("LECAP y BONCAP", "Títulos del Tesoro en pesos, a tasa fija, que pagan todo junto al "
                                           "vencimiento."))
    if "Ajustables por CER" in clases:
        terminos.append(("CER", "Índice del Banco Central que sigue a la inflación. Un bono ajustable por CER "
                                "actualiza su capital con ese índice."))
    if "Tasa variable TAMAR" in clases:
        terminos.append(("TAMAR", "La tasa que pagan los bancos privados por plazos fijos grandes, publicada por el "
                                  "Banco Central. Un bono TAMAR paga esa tasa más un adicional."))
    if "Dólar linked" in clases:
        terminos.append(("Dólar linked", "Un bono en pesos cuyo capital se ajusta por el dólar oficial."))
    if m["resultados"] is not None:
        terminos += [
            ("Ganancia ya cobrada", "Lo que ganaste con lo que vendiste, con lo que venció y con las rentas y "
                                    "dividendos que cobraste."),
            ("Ganancia o pérdida en papel", "La suba o la baja de un título que todavía tenés. Se concreta cuando lo "
                                            "vendés o cuando vence."),
        ]
    return "".join('<div><dt>{}</dt><dd>{}</dd></div>'.format(escape(t), escape(d)) for t, d in terminos)


def _hoja_cierre(m):
    partes = ['<h2 class="primero">Aclaraciones</h2><p class="aclara">Los cobros futuros surgen de las condiciones de '
              'emisión de cada título y suponen que se mantienen hasta el vencimiento; están sujetos al pago del emisor. '
              'Los importes en dólares no se convierten ni se suman a los de pesos. Valuación con el último precio '
              'disponible al {}. Este informe no constituye una recomendación de inversión.</p>'.format(
                  _fecha_larga(m["fecha"])),
              '<h2>Palabras que usamos</h2><dl class="glosario">{}</dl>'.format(_glosario(m))]
    return _hoja(m["asesor"], "Aclaraciones", m["fecha"], "".join(partes))


def informe_html(modelo):
    numeros = _numeros(modelo)
    hojas = [h for h in (_hoja_hoy(modelo, numeros), _hoja_titulos(modelo, numeros), _hoja_pasado(modelo, numeros),
                         _hoja_futuro(modelo, numeros), _hoja_futuro_titulos(modelo, numeros), _hoja_cierre(modelo)) if h]
    titulo = "Informe de cartera · {}".format(modelo["cliente"] or "")
    return ('<!doctype html>\n<html lang="es"><head><meta charset="utf-8">'
            '<meta name="viewport" content="width=device-width, initial-scale=1"><title>{}</title><style>{}</style>'
            '</head><body>{}</body></html>\n').format(escape(titulo), _ESTILO, "".join(hojas))


# ---------------------------------------------------------------- archivos

def _escribir_atomico(ruta, contenido):
    ruta.parent.mkdir(parents=True, exist_ok=True)
    temporal = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=ruta.parent, prefix=".informe-",
                                         suffix=".tmp", delete=False) as salida:
            temporal = Path(salida.name)
            os.fchmod(salida.fileno(), 0o600)
            salida.write(contenido)
            salida.flush()
            os.fsync(salida.fileno())
        os.replace(str(temporal), str(ruta))
        temporal = None
    finally:
        if temporal is not None:
            temporal.unlink(missing_ok=True)


def exportar_pdf(ruta_html, ruta_pdf, navegador=None):
    ruta_html, ruta_pdf = Path(ruta_html).resolve(), Path(ruta_pdf)
    navegador = Path(navegador if navegador is not None else _NAVEGADOR)
    if not navegador.exists():
        raise ErrorInforme("No se encontró Google Chrome en {}. Abrí {} en el navegador e imprimilo como PDF "
                           "(A4, sin encabezados ni pies).".format(navegador, ruta_html))
    temporal = ruta_pdf.with_name(".informe-{}.pdf.tmp".format(os.getpid()))
    try:
        proceso = subprocess.run(
            [str(navegador), "--headless=new", "--disable-gpu", "--no-pdf-header-footer",
             "--print-to-pdf={}".format(temporal), ruta_html.as_uri()],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=120)
        if proceso.returncode != 0 or not temporal.exists() or temporal.stat().st_size == 0:
            raise ErrorInforme("Chrome no pudo generar el PDF. Abrí {} en el navegador e imprimilo como PDF.".format(
                ruta_html))
        os.replace(str(temporal), str(ruta_pdf))
    except (OSError, subprocess.SubprocessError) as error:
        raise ErrorInforme("Chrome no pudo generar el PDF ({}). Abrí {} en el navegador e imprimilo como PDF.".format(
            error, ruta_html)) from None
    finally:
        if temporal.exists():
            temporal.unlink()
    return ruta_pdf


def _json_opcional(ruta):
    if not ruta.exists():
        return None
    try:
        return json.loads(ruta.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        raise ErrorInforme("{} inválido: {}.".format(ruta.name, error)) from None


def ejecutar_informe(opciones, datos):
    """Comando `informe`: escribe el HTML (y el PDF con --pdf) desde el último dashboard."""
    from .almacenamiento import _ruta_cartera

    carpeta = _ruta_cartera(datos, opciones.cliente).parent
    try:
        datos_dashboard = leer_datos_dashboard(carpeta / "dashboard.html")
        perfil = _json_opcional(carpeta / "perfil.json")
        entrega = _carpeta_entrega(perfil, datos)
        modelo = armar_informe(datos_dashboard, _json_opcional(carpeta / "instrumentos.json"), perfil)
    except ErrorInforme as error:
        print(str(error), file=sys.stderr)
        return 1
    if modelo["fecha"] is None:
        print("El dashboard no informa su fecha de generación. Generalo de nuevo.", file=sys.stderr)
        return 1
    destino = Path(opciones.salida).expanduser() if opciones.salida else carpeta / "informes"
    ruta_html = destino / "informe-{}.html".format(modelo["fecha"].isoformat())
    _escribir_atomico(ruta_html, informe_html(modelo))
    print("Informe guardado: {}".format(ruta_html))
    antiguedad = (_hoy() - modelo["fecha"]).days
    if antiguedad > _ANTIGUEDAD_MAXIMA:
        print("ADVERTENCIA: el dashboard tiene {} días. Si hay datos nuevos, generalo de nuevo antes del informe.".format(
            antiguedad))
    ruta_pdf = None
    if opciones.pdf or entrega is not None:
        try:
            ruta_pdf = exportar_pdf(ruta_html, ruta_html.with_suffix(".pdf"))
        except ErrorInforme as error:
            print(str(error), file=sys.stderr)
            if entrega is not None:
                _entregar(ruta_html, entrega, modelo["fecha"])
            return 1
        print("PDF guardado: {}".format(ruta_pdf))
    if entrega is not None:
        _entregar(ruta_pdf, entrega, modelo["fecha"])
    return 0


def _carpeta_entrega(perfil, datos):
    """Carpeta del cliente donde se deja una copia del informe (`perfil.carpeta_informes`).

    Ruta absoluta o relativa a la carpeta de datos. None si el perfil no la define.
    """
    valor = (perfil or {}).get("carpeta_informes") if isinstance(perfil, dict) else None
    if valor is None:
        return None
    if not isinstance(valor, str) or not valor.strip():
        raise ErrorInforme("perfil.json: carpeta_informes debe ser una ruta.")
    ruta = Path(valor).expanduser()
    return (ruta if ruta.is_absolute() else Path(datos).expanduser() / ruta).resolve()


def _entregar(origen, carpeta, fecha):
    import shutil

    carpeta.mkdir(parents=True, exist_ok=True)
    destino = carpeta / "Informe de cartera {}{}".format(fecha.isoformat(), origen.suffix)
    temporal = destino.with_name("." + destino.name + ".tmp")
    shutil.copyfile(str(origen), str(temporal))
    os.replace(str(temporal), str(destino))
    print("Copia para el cliente: {}".format(destino))
