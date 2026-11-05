"""HTML local de seguimiento: valores conocidos, procedencia y actualización por panel."""

import html
import json
import math
from datetime import date, datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

from .dia_cero import patrimonio_inicial
from .precios import ENDPOINTS
from ._dashboard_js import SCRIPT


def _texto(valor):
    return html.escape(str(valor), quote=True)


def _numero(valor, positivo=False):
    if isinstance(valor, bool) or not isinstance(valor, (int, float)):
        return None
    try:
        numero = float(valor)
    except (ValueError, OverflowError):
        return None
    if not math.isfinite(numero) or (positivo and numero <= 0):
        return None
    return numero


def _importe(valor):
    if valor is None:
        return "sin dato"
    return format(valor, ",.2f").translate(str.maketrans({",": ".", ".": ","}))


def _cantidad(valor):
    if valor is None:
        return "sin dato"
    texto = format(Decimal(str(valor)), ",f")
    if "." in texto:
        texto = texto.rstrip("0").rstrip(".")
    return texto.translate(str.maketrans({",": ".", ".": ","}))


def _porcentaje(valor):
    return "sin dato" if valor is None else _importe(valor * 100) + " %"


def _fecha(valor):
    if isinstance(valor, datetime):
        return valor.date().isoformat()
    if isinstance(valor, date):
        return valor.isoformat()
    if isinstance(valor, str):
        return date.fromisoformat(valor).isoformat()
    return None


def _instante(valor):
    if valor is None:
        return None
    if not isinstance(valor, datetime) or valor.utcoffset() is None:
        raise ValueError("Las horas del dashboard deben incluir zona horaria.")
    return valor.isoformat()


def _momento(valor):
    """Fecha y hora de Argentina, para mostrar; acepta ISO o datetime."""
    if not valor or valor == "sin dato":
        return "sin dato"
    instante = valor if isinstance(valor, datetime) else datetime.fromisoformat(valor)
    return instante.astimezone(ZoneInfo("America/Argentina/Buenos_Aires")).strftime("%d/%m/%Y %H:%M")


def _dia(valor):
    return "sin dato" if not valor else date.fromisoformat(valor).strftime("%d/%m/%Y")


def _dias(cantidad):
    return "1 día" if cantidad == 1 else "{} días".format(cantidad)


def _calcular(cantidad, precio, unidad):
    if None in (cantidad, precio, unidad) or unidad not in (1, 100):
        return None
    return _numero(cantidad / unidad * precio)


def _origen(estado):
    return {"extracto": "extracto", "estimado": "estimado", "mixto": "incluye estimado",
            "incompleto": "falta estimar"}.get(estado, "falta estimar")


def _estado_precio(posicion):
    if posicion["estado"] == "sin_dato" or posicion["ultimo"] is None:
        return "Sin dato"
    return "Último dato"


def _efectivo(efectivo):
    efectivo = efectivo or {}
    return {"fecha": _fecha(efectivo.get("fecha")),
            "ARS": _numero(efectivo.get("ARS")), "USD": _numero(efectivo.get("USD")),
            "nota": str(efectivo.get("nota") or "")}


def _referencia(dia_cero, posiciones):
    if dia_cero is None:
        return None
    if posiciones is None:
        total, valor, faltantes = None, None, ["unidades de cotización"]
    else:
        patrimonio = patrimonio_inicial(posiciones, dia_cero)
        total, valor, faltantes = patrimonio.total, patrimonio.valuacion_posiciones, patrimonio.faltantes
    return {"fecha": dia_cero["fecha"], "mep": _numero(dia_cero.get("mep"), positivo=True),
            "valuacion_posiciones": valor, "efectivo": _efectivo(dia_cero.get("efectivo")),
            "patrimonio_inicial": total, "faltantes": list(faltantes),
            "cantidades": dict(dia_cero.get("cantidades", {})), "precios": dict(dia_cero.get("precios", {}))}


def _posiciones(resultados, cotizaciones, niveles, instrumentos, posiciones, dia_cero):
    metadatos = {p.ticker: p for p in posiciones or []}
    filas = []
    for resultado in resultados:
        ticker = resultado.ticker
        posicion = metadatos.get(ticker)
        cotizacion = cotizaciones.get(ticker)
        ultimo = _numero(cotizacion.ultimo, positivo=True) if cotizacion else None
        estado = cotizacion.estado if cotizacion else "sin_dato"
        if estado not in ("vivo", "cache") or ultimo is None:
            estado, ultimo = "sin_dato", None
        cantidad = _numero(posicion.cantidad, positivo=True) if posicion else None
        unidad = posicion.cotiza_cada if posicion else None
        costo = _numero(resultado.costo, positivo=True)
        origen = resultado.estado_costo
        if origen not in ("extracto", "estimado", "mixto") or costo is None:
            origen, costo = "incompleto", None
        nivel = niveles.get(ticker) or {}
        instrumento = instrumentos.get(ticker) or {}
        precio_cero = _numero((dia_cero or {}).get("precios", {}).get(ticker), positivo=True)
        valor = _calcular(cantidad, ultimo, unidad) if posicion else _numero(resultado.valuacion)
        if ultimo is None:
            valor = None
        ganancia = _numero(valor - costo) if valor is not None and costo is not None else None
        cambio = None
        porcentaje_cero = _numero(resultado.resultado_dia_cero_pct)
        if posicion:
            base = _calcular(cantidad, precio_cero, unidad)
            cambio = _numero(valor - base) if valor is not None and base is not None else None
            porcentaje_cero = _numero(cambio / base) if cambio is not None and base else None
        else:
            cambio = _numero(resultado.resultado_dia_cero)
        filas.append({
            "ticker": ticker, "especie": posicion.especie if posicion else ticker,
            "tipo": posicion.tipo if posicion else resultado.tipo,
            "cantidad": cantidad, "cotiza_cada": unidad,
            "endpoint": ENDPOINTS.get(posicion.tipo) if posicion else None,
            "costo": costo, "estado_costo": origen,
            "ultimo": ultimo, "bid": _numero(cotizacion.bid, positivo=True) if cotizacion else None,
            "ask": _numero(cotizacion.ask, positivo=True) if cotizacion else None,
            "pct_dia": _numero(cotizacion.pct_dia) if cotizacion else None,
            "estado": estado, "consultado_en": _instante(cotizacion.consultado_en) if cotizacion else None,
            "valuacion": valor, "precio_dia_cero": precio_cero,
            "take_profit": _numero(nivel.get("take_profit"), positivo=True),
            "stop_loss": _numero(nivel.get("stop_loss"), positivo=True),
            "vencimiento": _fecha(instrumento.get("vencimiento")),
            "resultado": ganancia, "resultado_pct": _numero(ganancia / costo) if ganancia is not None else None,
            "resultado_dia_cero": cambio,
            "resultado_dia_cero_pct": porcentaje_cero,
        })
    return filas


def _vencimientos(filas, hoy):
    resultado = []
    for fila in filas:
        if fila["vencimiento"] is None:
            continue
        dias = (date.fromisoformat(fila["vencimiento"]) - hoy).days
        if dias <= 60:
            resultado.append({"ticker": fila["ticker"], "vencimiento": fila["vencimiento"],
                              "dias": dias, "vencida": dias < 0})
    return sorted(resultado, key=lambda x: (x["vencimiento"], x["ticker"]))


def _sumar(valores):
    valores = [valor for valor in valores if valor is not None]
    if not valores:
        return None
    try:
        return _numero(math.fsum(valores))
    except OverflowError:
        return None


def _comparables(filas):
    return [fila for fila in filas if fila["valuacion"] is not None and fila["costo"] is not None]


def _resumen_compra(filas):
    comparables = _comparables(filas)
    valor = _sumar(fila["valuacion"] for fila in comparables)
    costo = _sumar(fila["costo"] for fila in comparables)
    resultado = _numero(valor - costo) if valor is not None and costo is not None else None
    cantidad = len(comparables)
    texto = "Desde la compra: {} ARS; {} de {} posiciones con precio y costo completo".format(
        _importe(resultado), cantidad, len(filas))
    if any(fila["estado_costo"] != "extracto" for fila in comparables):
        texto += "; incluye estimado"
    return texto + "."


def _resumen_variacion(filas, dia_cero, mep):
    con_base = [fila for fila in filas if fila["valuacion"] is not None and fila["precio_dia_cero"] is not None]
    ars = _sumar(fila["resultado_dia_cero"] for fila in con_base)
    usd = None
    if dia_cero and mep and dia_cero["mep"] and mep["ultimo"]:
        valores = []
        for fila in con_base:
            base = _calcular(fila["cantidad"], fila["precio_dia_cero"], fila["cotiza_cada"])
            if base is not None:
                valores.append(fila["valuacion"] / mep["ultimo"] - base / dia_cero["mep"])
        usd = _sumar(valores)
    return "Variación de precios desde el día cero: {} ARS / {} USD MEP; {} de {} posiciones comparables.".format(
        _importe(ars), _importe(usd), len(con_base), len(filas))


def _distancia(fila, nivel):
    referencia = fila["bid"] if fila["bid"] is not None else fila["ultimo"]
    if nivel is None or referencia is None:
        return None
    return _numero(nivel / referencia - 1)


def _filas_tabla(filas):
    total = _sumar(fila["valuacion"] for fila in filas)
    salida = []
    for fila in filas:
        resultado = "falta estimar" if fila["costo"] is None else _importe(fila["resultado"])
        if fila["resultado"] is not None:
            resultado += " (" + _porcentaje(fila["resultado_pct"]) + ")"
        cambio = _importe(fila["resultado_dia_cero"])
        if fila["resultado_dia_cero_pct"] is not None:
            cambio += " (" + _porcentaje(fila["resultado_dia_cero_pct"]) + ")"
        origen = _origen(fila["estado_costo"])
        consulta = _momento(fila["consultado_en"])
        diario = "sin dato" if fila["pct_dia"] is None else _importe(fila["pct_dia"]) + " %"
        celdas = [fila["ticker"], fila["especie"], fila["tipo"], _cantidad(fila["cantidad"]),
                  _importe(fila["ultimo"]), _importe(fila["valuacion"]),
                  _porcentaje(fila["valuacion"] / total) if fila["valuacion"] is not None and total else "sin dato",
                  diario, "falta estimar" if fila["costo"] is None else _importe(fila["costo"]), origen,
                  resultado, cambio,
                  _porcentaje(_distancia(fila, fila["take_profit"])),
                  _porcentaje(_distancia(fila, fila["stop_loss"])),
                  _estado_precio(fila) + " · consulta " + consulta]
        salida.append('<tr data-ticker="{}">{}</tr>'.format(_texto(fila["ticker"]),
            "".join('<td{}>{}</td>'.format(' class="numero"' if 3 <= i <= 13 and i != 9 else "", _texto(celda))
                    for i, celda in enumerate(celdas))))
    return "".join(salida)


def _totales(filas, mep):
    tipos = sorted({fila["tipo"] for fila in filas})
    salidas = []
    for tipo in tipos + [None]:
        grupo = [fila for fila in filas if tipo is None or fila["tipo"] == tipo]
        valor = _sumar(fila["valuacion"] for fila in grupo)
        usd = _numero(valor / mep["ultimo"]) if valor is not None and mep is not None else None
        faltantes = sum(fila["valuacion"] is None for fila in grupo)
        salidas.append("<tr><th scope=\"row\">{}</th><td class=\"numero\">{}</td><td class=\"numero\">{}</td><td>{}</td></tr>".format(
            _texto(tipo or "Total de posiciones"), _importe(valor), _importe(usd), faltantes))
    return "".join(salidas)


def _grafico(ticker, puntos):
    validos = []
    for instante, precio in puntos:
        valor = _numero(precio, positivo=True)
        if valor is not None:
            validos.append((datetime.fromisoformat(_instante(instante)), valor))
    validos = sorted(validos)[-500:]
    titulo = _texto(ticker)
    if len(validos) < 2:
        return ('<article class="grafico"><h3>{}</h3>'
                '<svg viewBox="0 0 640 180" role="img" aria-label="Sin historial suficiente para {}">'
                '<title>Sin historial suficiente para {}</title><path d="M24 16 V152 H620" fill="none" stroke="#ccd5df"/>'
                '</svg><p>Sin historial suficiente.</p></article>').format(titulo, titulo, titulo)
    precios = [valor for _, valor in validos]
    minimo, maximo = min(precios), max(precios)
    amplitud = maximo - minimo
    if amplitud == 0:
        amplitud = max(abs(maximo) * 0.02, 1)
        minimo -= amplitud / 2
    duracion = (validos[-1][0] - validos[0][0]).total_seconds()
    coordenadas = []
    for indice, (instante, valor) in enumerate(validos):
        fraccion = (instante - validos[0][0]).total_seconds() / duracion if duracion else indice / (len(validos) - 1)
        x, y = 24 + fraccion * 592, 152 - (valor - minimo) / amplitud * 128
        coordenadas.append("{:.2f},{:.2f}".format(x, y))
    return ('<article class="grafico"><h3>{}</h3>'
            '<svg viewBox="0 0 640 180" role="img" aria-label="Historial capturado de {}">'
            '<title>Historial capturado de {}</title><path d="M24 16 V152 H620" fill="none" stroke="#ccd5df"/>'
            '<polyline points="{}" fill="none" stroke="#225d8f" stroke-width="2.5"/>'
            '</svg><p>{} a {} · último {} · historial capturado, sin actualización en vivo.</p></article>').format(
                titulo, titulo, titulo, " ".join(coordenadas), _texto(_dia(validos[0][0].date().isoformat())),
                _texto(_dia(validos[-1][0].date().isoformat())), _importe(validos[-1][1]))


def _bloque_efectivo(titulo, efectivo):
    return ('<article><h3>{}</h3><p>Fecha: {}</p><dl><dt>ARS</dt><dd>{}</dd>'
            '<dt>USD</dt><dd>{}</dd></dl><p>{}</p></article>').format(
                _texto(titulo), _texto(_dia(efectivo["fecha"])), _importe(efectivo["ARS"]),
                _importe(efectivo["USD"]), _texto(efectivo.get("nota", "")))


def _campo(objeto, nombre, defecto=None):
    return objeto.get(nombre, defecto) if isinstance(objeto, dict) else getattr(objeto, nombre, defecto)


def _datos_integral(integral):
    if integral is None:
        return None
    flujos = _campo(integral, "flujos", {})
    datos = {campo: _numero(_campo(integral, campo)) for campo in
             ("total", "patrimonio_inicial", "patrimonio_final", "valuacion_final")}
    datos["efectivo"] = {"ARS": _numero(_campo(integral, "efectivo_ars")),
                          "USD": _numero(_campo(integral, "efectivo_usd"))}
    datos.update({campo: _numero(_campo(flujos, campo)) for campo in
                  ("aportes", "retiros", "rentas", "dividendos", "gastos")})
    datos["faltantes"] = list(_campo(integral, "faltantes", []))
    datos["faltantes_fijos"] = list(_campo(integral, "faltantes_fijos", []))
    # También aceptar implementaciones que solo tengan los campos públicos mínimos.
    if datos["patrimonio_inicial"] is None and not datos["faltantes_fijos"]:
        datos["faltantes_fijos"].append("patrimonio inicial")
    for moneda in ("ARS", "USD"):
        etiqueta = "efectivo " + moneda + " calculado"
        if datos["efectivo"][moneda] is None and etiqueta not in datos["faltantes_fijos"]:
            datos["faltantes_fijos"].append(etiqueta)
    return datos


def _datos_realizados(realizados):
    return [{"ticker": str(_campo(venta, "ticker")), "fecha": _fecha(_campo(venta, "fecha")),
             "cantidad": _numero(_campo(venta, "cantidad")), "importe": _numero(_campo(venta, "importe")),
             "costo": _numero(_campo(venta, "costo")), "resultado": _numero(_campo(venta, "resultado")),
             "origen_costo": str(_campo(venta, "origen_costo"))} for venta in realizados or []]


def _datos_conciliacion(conciliacion):
    if conciliacion is None:
        return {"estado": "sin_control", "fecha": None, "diferencias": {}}
    return {"estado": str(_campo(conciliacion, "estado", "sin_control")),
            "fecha": _fecha(_campo(conciliacion, "fecha")),
            "diferencias": {str(moneda): _numero(valor) for moneda, valor in
                            _campo(conciliacion, "diferencias", {}).items()}}


def _resultado_completo(integral):
    if integral is None:
        return '<section class="sin-movimientos"><h2>Resultado completo</h2><p>Se calcula cuando estén los movimientos.</p></section>'
    campos = [("inicial", "Patrimonio inicial", "patrimonio_inicial"),
              ("valuacion", "Valuación actual de posiciones", "valuacion_final"),
              ("final", "Patrimonio final", "patrimonio_final"),
              ("aportes", "Aportes", "aportes"), ("retiros", "Retiros", "retiros"),
              ("rentas", "Rentas", "rentas"), ("dividendos", "Dividendos", "dividendos"),
              ("gastos", "Gastos", "gastos"), ("total", "Resultado completo ARS", "total")]
    valores = ''.join('<dt>{}</dt><dd id="integral-{}"{}>{}</dd>'.format(
        titulo, identificador, ' class="dato-destacado"' if identificador == 'total' else '',
        _importe(integral[campo])) for identificador, titulo, campo in campos)
    faltantes = "Faltan: " + ", ".join(integral["faltantes"]) if integral["faltantes"] else ""
    return ('<section id="resultado-completo"><h2>Resultado completo en pesos</h2><dl>' + valores + '</dl>'
            '<p id="integral-faltantes" class="aviso">' + _texto(faltantes) + '</p>'
            '<p id="integral-estado" class="muted">Usa los últimos datos guardados hasta confirmar precios en vivo.</p>'
            '<p class="muted">Patrimonio final menos patrimonio inicial y aportes, más retiros. '
            'Las rentas, los dividendos y los gastos ya están incluidos en el efectivo calculado. '
            'El resultado realizado también está incluido; no se suma nuevamente.</p></section>')


def _resultado_realizado(realizados):
    filas = []
    for venta in realizados:
        celdas = [venta["ticker"], _dia(venta["fecha"]), _cantidad(venta["cantidad"]),
                  _importe(venta["importe"]), "falta estimar" if venta["costo"] is None else _importe(venta["costo"]),
                  _origen(venta["origen_costo"]), "falta estimar" if venta["resultado"] is None else _importe(venta["resultado"])]
        filas.append('<tr>' + ''.join('<td>{}</td>'.format(_texto(celda)) for celda in celdas) + '</tr>')
    conocidas = [venta for venta in realizados if venta["resultado"] is not None]
    total = _sumar(venta["resultado"] for venta in conocidas) if conocidas else 0.0
    encabezados = ["Ticker", "Fecha", "Cantidad", "Importe ARS", "Costo ARS", "Origen del costo", "Realizado ARS"]
    tabla = ('<div class="contenedor-tabla"><table><thead><tr>' +
             ''.join('<th scope="col">' + _texto(titulo) + '</th>' for titulo in encabezados) +
             '</tr></thead><tbody>' + ''.join(filas) + '</tbody></table></div>') if filas else '<p>Sin ventas registradas.</p>'
    estimacion = "; incluye estimado" if any(v["origen_costo"] != "extracto" for v in conocidas) else ""
    return ('<section id="resultado-realizado"><h2>Resultado realizado por venta</h2>' + tabla +
            '<p>Total con costo conocido: ' + _importe(total) + ' ARS' + estimacion + '. ' +
            str(len(realizados) - len(conocidas)) + ' ventas excluidas por costo incompleto.</p>'
            '<p class="muted">Ya está incluido en el resultado completo mediante el efectivo. No se suma nuevamente.</p></section>')


def _conciliacion(conciliacion):
    estado = conciliacion["estado"]
    fecha = _dia(conciliacion["fecha"])
    if estado == "no_concilia":
        diferencias = "; ".join(moneda + " " + _importe(valor) for moneda, valor in conciliacion["diferencias"].items())
        texto = "El efectivo no concilia al {}. Diferencia informado menos calculado: {}. Revisá los movimientos.".format(fecha, diferencias)
    elif estado == "concilia":
        texto = "El efectivo concilia al {} dentro de la tolerancia (1 ARS y 0,01 USD).".format(fecha)
    else:
        texto = "Efectivo sin control: falta una fecha válida o saldos comparables con el día cero."
    return '<p id="conciliacion-efectivo"{}>{}</p>'.format(' class="aviso"' if estado != "concilia" else '', _texto(texto))


_ESTILOS = """
:root{font-family:system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;color:#17212b;background:#f5f7fa;font-size:15px;line-height:1.45}
*{box-sizing:border-box}p,li,dd,h1,h2,h3{overflow-wrap:anywhere}body{margin:0}main{max-width:1520px;margin:auto;padding:24px;min-width:0}header{display:flex;flex-wrap:wrap;gap:16px;justify-content:space-between;align-items:start}h1{font-size:1.85rem;margin:0 0 8px}h2{font-size:1.2rem;margin:0 0 14px}h3{font-size:1rem;margin:0 0 10px}p{margin:8px 0}section,.tarjeta{background:#fff;border:1px solid #d6dee7;border-radius:8px;padding:18px;margin-top:18px;min-width:0}button{background:#205b8c;border:0;color:#fff;font:inherit;padding:10px 16px;border-radius:5px;cursor:pointer}button:disabled{background:#677684;cursor:default}button:focus-visible{outline:3px solid #f1ad37;outline-offset:3px}.aviso{background:#fff4d9;border-left:4px solid #b57c0d;padding:10px 12px;border-radius:3px}.aviso:empty{display:none}.contenedor-tabla{overflow-x:auto;width:100%;max-width:100%;border:1px solid #dde3ea;border-radius:4px}table{border-collapse:collapse;width:100%;font-variant-numeric:tabular-nums;font-size:.9rem}th,td{text-align:left;border-bottom:1px solid #e2e7ed;padding:9px 10px;white-space:nowrap}th{background:#edf2f7;font-weight:600}thead th{position:sticky;top:0}.numero{text-align:right}.grilla{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,280px),1fr));gap:18px}.grilla article{min-width:0}.grilla section{margin:0}dl{display:grid;grid-template-columns:auto 1fr;gap:5px 20px;margin:8px 0}dd{text-align:right;margin:0;font-variant-numeric:tabular-nums}.grafico{border:1px solid #dce3eb;border-radius:6px;padding:12px;min-width:0}.grafico svg{display:block;width:100%;height:auto}.grafico p{font-size:.83rem;color:#465666}.muted{color:#465666}.dato-destacado{font-size:1.15rem;font-weight:600}.sin-movimientos{border-left:4px solid #64788b}ul{padding-left:20px}li{margin:7px 0}[hidden]{display:none!important}.tabla-posiciones td:first-child,.tabla-posiciones th:first-child{position:sticky;left:0;z-index:1;font-weight:600;box-shadow:1px 0 0 #d6dee7}.tabla-posiciones td:first-child{background:#fff}.tabla-posiciones thead th:first-child{z-index:2}@media(max-width:600px){main{padding:12px}section,.tarjeta{padding:12px}h1{font-size:1.5rem}.grilla{grid-template-columns:minmax(0,1fr)}header>div{min-width:0;overflow-wrap:anywhere}}
"""


def generar_html(cliente, resultados, resumen, cotizaciones, niveles, instrumentos,
                 efectivo, historial, generado_en, posiciones=None, dia_cero=None, mep=None,
                 posiciones_base=None, integral=None, realizados=None, conciliacion=None):
    """Genera una vista completa incluso si el navegador no logra consultar la fuente."""
    generado = _instante(generado_en)
    resultados = list(resultados)
    posiciones = list(posiciones) if posiciones is not None else None
    filas = _posiciones(resultados, cotizaciones, niveles, instrumentos, posiciones, dia_cero)
    habilitada = posiciones is not None and (bool(filas) or integral is not None) and all(
        fila["cantidad"] is not None and fila["cotiza_cada"] in (1, 100) and fila["endpoint"] in ENDPOINTS.values()
        for fila in filas)
    referencia = _referencia(dia_cero, posiciones_base if posiciones_base is not None else posiciones)
    integral_datos = _datos_integral(integral)
    realizados_datos = _datos_realizados(realizados)
    conciliacion_datos = _datos_conciliacion(conciliacion)
    mep_valor = _numero(mep.ultimo, positivo=True) if mep is not None else None
    mep_datos = None if mep_valor is None else {"ultimo": mep_valor, "estado": mep.estado,
                                               "consultado_en": _instante(mep.consultado_en)}
    actual = _efectivo(efectivo)
    vencimientos = _vencimientos(filas, generado_en.astimezone(ZoneInfo("America/Argentina/Buenos_Aires")).date())
    avisos_datos = [str(aviso) for aviso in cliente.get("_avisos_datos", [])]
    datos = {"generado_en": generado, "cliente": {"slug": str(cliente.get("slug") or ""),
             "nombre": str(cliente.get("nombre") or cliente.get("slug") or "Cliente")},
             "posiciones": filas, "vencimientos": vencimientos, "dia_cero": referencia,
             "mep": mep_datos, "efectivo": actual,
             "actualizacion_habilitada": habilitada, "avisos_datos": avisos_datos,
             "integral": integral_datos, "realizados": realizados_datos, "conciliacion": conciliacion_datos}
    serializado = json.dumps(datos, ensure_ascii=False, allow_nan=False).replace("<", "\\u003c").replace("\u2028", "\\u2028").replace("\u2029", "\\u2029")
    avisos_html = ('<section id="avisos-lectura" class="aviso"><h2>Estado de los archivos</h2><ul>' +
                   "".join("<li>" + _texto(aviso) + "</li>" for aviso in avisos_datos) + "</ul></section>") if avisos_datos else ""
    nombre = _texto(datos["cliente"]["nombre"])
    consultas = [fila["consultado_en"] for fila in filas if fila["ultimo"] is not None and fila["consultado_en"]]
    if mep_datos and mep_datos["consultado_en"]:
        consultas.append(mep_datos["consultado_en"])
    ultima = max(consultas, key=datetime.fromisoformat) if consultas else "sin dato"
    faltantes = sum(fila["valuacion"] is None for fila in filas)
    mep_texto = "sin dato" if mep_datos is None else _importe(mep_valor) + " · Último dato · consulta " + _momento(mep_datos["consultado_en"])
    lista_vencimientos = "".join("<li>{}</li>".format(_texto(
        "{} · {} · {}".format(v["ticker"], _dia(v["vencimiento"]),
            "vencida hace {}; si dejó de cotizar, puede deberse al vencimiento".format(_dias(-v["dias"])) if v["vencida"]
            else "vence hoy" if v["dias"] == 0 else ("falta " if v["dias"] == 1 else "faltan ") + _dias(v["dias"])))) for v in vencimientos)
    if not lista_vencimientos:
        lista_vencimientos = "<li>No hay vencimientos dentro de los próximos 60 días ni especies vencidas informadas.</li>"
    if referencia is None:
        texto_dia = "Sin fijar. No hay una referencia del día cero."
        caja_dia = _efectivo(None)
    else:
        texto_dia = "Fecha: {} · Valuación inicial de posiciones: {} ARS · Patrimonio inicial: {} ARS".format(
            _dia(referencia["fecha"]), _importe(referencia["valuacion_posiciones"]), _importe(referencia["patrimonio_inicial"]))
        if referencia["faltantes"]:
            texto_dia += "; faltan: " + ", ".join(referencia["faltantes"])
        caja_dia = referencia["efectivo"]
    efectivo_calculado = ""
    if integral_datos is not None:
        calculado = dict(integral_datos["efectivo"], fecha=generado_en.astimezone(ZoneInfo("America/Argentina/Buenos_Aires")).date().isoformat(),
                         nota="Reconstruido desde los saldos del día cero y los movimientos. Se usa para el patrimonio final.")
        efectivo_calculado = _bloque_efectivo("Efectivo calculado", calculado)
    graficos = "".join(_grafico(fila["ticker"], historial.get(fila["ticker"], [])) for fila in filas)
    estado = "Precios guardados al generar este archivo: Último dato hasta que una consulta los confirme."
    if not habilitada:
        estado += " Vista estática sin actualización automática: faltan cantidades y unidades para recalcular."
    aviso_dia = "Este archivo se generó otro día; las posiciones pueden haber cambiado."
    otro_dia = generado_en.astimezone(ZoneInfo("America/Argentina/Buenos_Aires")).date() != datetime.now(ZoneInfo("America/Argentina/Buenos_Aires")).date()
    encabezados = ["Ticker", "Especie", "Tipo", "Cantidad", "Precio", "Valuación ARS", "Peso", "Variación del día",
                   "Costo ARS", "Origen del costo", "Desde la compra ARS", "Variación de precios día cero ARS", "Distancia TP", "Distancia SL", "Estado y consulta"]
    return ('<!doctype html><html lang="es-AR"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
        '<meta http-equiv="Content-Security-Policy" content="default-src \'none\'; style-src \'unsafe-inline\'; script-src \'unsafe-inline\'; connect-src https://data912.com; img-src data:">'
        '<title>Cartera · ' + nombre + '</title><style>' + _ESTILOS + '</style></head><body><main>'
        '<header><div><h1>Cartera · ' + nombre + '</h1><p class="muted">Generado: ' + _texto(_momento(generado_en)) + '</p>'
        '<p id="ultima-consulta">Última consulta de los precios guardados: ' + _texto(_momento(ultima)) + '</p></div>'
        '<button id="actualizar" type="button"' + (' disabled' if not habilitada else '') + '>Actualizar precios</button></header>'
        '<p id="aviso-datos" class="aviso" role="status" aria-live="polite">' + _texto(estado) + '</p>'
        '<p id="aviso-dia-distinto" class="aviso"' + ('' if otro_dia else ' hidden') + '>' + _texto(aviso_dia) + '</p>'
        '<p id="aviso-parcial" class="aviso"' + ('' if faltantes else ' hidden') + '>Totales parciales: ' + str(faltantes) + ' especies sin precio.</p>'
        + avisos_html + '<section><h2>Vencimientos próximos y especies vencidas</h2><ul id="vencimientos-lista">' + lista_vencimientos + '</ul></section>'
        '<section><h2>Posiciones</h2><p class="muted">El efectivo se muestra aparte. Deslizá la tabla para ver todas las columnas.</p>'
        '<div class="contenedor-tabla" tabindex="0" aria-label="Posiciones de la cartera"><table class="tabla-posiciones"><thead><tr>' +
        ''.join('<th scope="col">' + _texto(titulo) + '</th>' for titulo in encabezados) + '</tr></thead><tbody id="posiciones-body">' + _filas_tabla(filas) + '</tbody></table></div></section>'
        '<section><h2>Valuación de posiciones por tipo de activo</h2><p id="mep-dato">Dólar MEP: ' + _texto(mep_texto) + '</p>'
        '<div class="contenedor-tabla"><table><thead><tr><th>Tipo</th><th>ARS</th><th>USD MEP</th><th>Especies sin precio</th></tr></thead>'
        '<tbody id="totales-body">' + _totales(filas, mep_datos) + '</tbody></table></div>'
        '<p id="resultado-compra">' + _texto(_resumen_compra(filas)) + '</p><p id="variacion-precios">' + _texto(_resumen_variacion(filas, referencia, mep_datos)) + '</p>'
        '<p class="muted">La variación de precios compara las mismas cantidades y no incluye movimientos ni cobros.</p></section>'
        + _resultado_completo(integral_datos) + (_resultado_realizado(realizados_datos) if integral_datos is not None else "") +
        '<section><h2>Día cero</h2><p>' + _texto(texto_dia) + '</p></section>'
        '<section><h2>Efectivo, separado de las posiciones</h2><div class="grilla">' + _bloque_efectivo("Efectivo informado", actual) + efectivo_calculado + _bloque_efectivo("Efectivo del día cero", caja_dia) + '</div>' + (_conciliacion(conciliacion_datos) if integral_datos is not None else "") + '</section>'
        '<section><h2>Historial capturado por especie</h2><p class="muted">Los gráficos muestran las consultas guardadas y no se actualizan en vivo.</p><div class="grilla">' + graficos + '</div></section>'
        '<script id="datos-cartera" type="application/json">' + serializado + '</script><script>' + SCRIPT + '</script>'
        '<noscript><p class="aviso">JavaScript está desactivado. Se muestran los últimos datos guardados, sin consultar precios.</p></noscript>'
        '</main></body></html>')
