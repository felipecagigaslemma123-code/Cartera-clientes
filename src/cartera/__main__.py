"""Comandos de base, movimientos, precios y seguimiento patrimonial."""

import argparse
import json
import os
import sys
import unicodedata
from datetime import date, datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

from .almacenamiento import (
    ErrorCartera, _ruta_cartera, actualizar_costos, cargar_cartera, derivar_base,
    importar_cartera,
)
from .calculos import costo_total, estado_costo
from .dia_cero import _leer_dia_cero, _validar_efectivo
from .precios import (
    ClientePrecios, ErrorDiaCero, advertencias_precio, capturar_historial,
    cargar_efectivo_dia_cero, fijar_dia_cero, patrimonio_inicial,
)
from .movimientos import (
    agregar_movimiento, cartera_actual, conciliar_efectivo, flujos, leer_movimientos,
    saldos_efectivo, validar_movimientos,
)
from .punto_partida import ErrorPuntoPartida
from .transporte import consultar_json


def _numero(valor):
    return format(valor, ",.2f").translate(str.maketrans({",": ".", ".": ","}))


def _cantidad(valor):
    texto = format(Decimal(str(valor)), ",f")
    if "." in texto:
        texto = texto.rstrip("0").rstrip(".")
    return texto.translate(str.maketrans({",": ".", ".": ","}))


def _origen(estado):
    return {"extracto": "extracto", "estimado": "estimado", "mixto": "mixto (incluye estimado)",
            "incompleto": "incompleto (falta estimar)"}[estado]


def _mostrar_estado(slug, punto, contenido, referencia=None, base=None, movimientos=(), realizados=(), control=None):
    lineas = ["Cliente: {}".format(slug),
              "Base inicial importada: {}".format(contenido["importado_en"])]
    for posicion in punto.posiciones:
        lotes = [lote for lote in punto.lotes if lote.ticker == posicion.ticker]
        estado = estado_costo(lotes)
        costo = costo_total(lotes)
        origen = _origen(estado)
        importe = "falta estimar" if costo is None else "$ " + _numero(costo)
        lineas.append("{} · {} · {} · cantidad {} · cotiza cada {}".format(
            posicion.ticker, posicion.especie, posicion.tipo,
            _cantidad(posicion.cantidad), posicion.cotiza_cada))
        lineas.append("  Costo: {} · origen: {}".format(importe, origen))
        lineas.append("  Precio: sin dato · valuación: sin dato · resultado: sin dato")
    lineas.append("Sin cotizaciones actuales: no se informa valuación ni resultado de la cartera.")
    if referencia is not None:
        lineas.extend(_lineas_dia_cero(base or punto, referencia))
    saldos = saldos_efectivo(referencia["efectivo"] if referencia else {}, movimientos)
    for moneda in ("ARS", "USD"):
        valor = saldos[moneda]
        lineas.append("Efectivo calculado {}: {}".format(moneda, "sin dato" if valor is None else _numero(valor)))
    fondos = flujos(movimientos)
    lineas.append("Flujos en ARS · aportes: {} · retiros: {} · rentas: {} · dividendos: {} · gastos: {}".format(
        *(_numero(getattr(fondos, campo)) for campo in ("aportes", "retiros", "rentas", "dividendos", "gastos"))))
    if fondos.amortizaciones:
        lineas.append("Amortizaciones en ARS: " + _numero(fondos.amortizaciones))
    conocidos, excluidos = [], 0
    for venta in realizados:
        importe = "falta estimar" if venta.resultado is None else "$ " + _numero(venta.resultado)
        lineas.append("Realizado de {}: {} · {} · origen: {}".format(
            venta.ticker, venta.fecha.isoformat(), importe, _origen(venta.origen_costo)))
        if venta.amortizaciones is not None:
            lineas.append("  Amortizaciones de la posición: $ " + _numero(venta.amortizaciones))
        if venta.resultado is None:
            excluidos += 1
        else:
            conocidos.append(venta.resultado)
    if realizados:
        from math import fsum
        try:
            total_realizado = "$ " + _numero(fsum(conocidos))
        except OverflowError:
            total_realizado = "sin dato (suma fuera de rango)"
        lineas.append("Realizado con costo conocido: {} · ventas excluidas por costo incompleto: {}. "
                      "Ya está incluido en el resultado completo; no se suma otra vez.".format(
                          total_realizado, excluidos))
    if control is not None:
        lineas.append("Control de efectivo: {}.".format(control.estado.replace("_", " ")))
        if control.estado == "no_concilia":
            for moneda, diferencia in control.diferencias.items():
                lineas.append("  Diferencia reportado menos calculado {}: {}".format(moneda, _numero(diferencia)))
            lineas.append("ADVERTENCIA: revisá los movimientos; el resultado usa el efectivo calculado.")
    print("\n".join(lineas))


def _lineas_dia_cero(punto, referencia):
    patrimonio = patrimonio_inicial(punto.posiciones, referencia)
    lineas = ["Día cero: {}".format(referencia["fecha"]),
              "Valuación inicial de posiciones: $ {}".format(_numero(patrimonio.valuacion_posiciones))]
    for moneda, saldo in (("ARS", patrimonio.efectivo_ars), ("USD", patrimonio.efectivo_usd)):
        lineas.append("Efectivo inicial {}: {}".format(moneda, "sin dato" if saldo is None else _numero(saldo)))
    if patrimonio.total is None:
        lineas.append("Patrimonio inicial: sin dato; faltan: {}.".format(", ".join(patrimonio.faltantes)))
    else:
        lineas.append("Patrimonio inicial: $ {}".format(_numero(patrimonio.total)))
    mep = referencia.get("mep")
    lineas.append("Dólar MEP del día cero: {}".format("sin dato" if mep is None else _numero(mep)))
    aviso = _aviso_fecha_efectivo(referencia)
    if aviso:
        lineas.append(aviso)
    return lineas


def _aviso_fecha_efectivo(referencia):
    efectivo = referencia["efectivo"]
    if efectivo.get("ARS") is None and efectivo.get("USD") is None:
        return None
    fecha = efectivo.get("fecha")
    if fecha == referencia["fecha"]:
        return None
    return ("ADVERTENCIA: el efectivo {} y el día cero es del {}; "
            "revisá que el saldo corresponda a ese día.").format(
                "no tiene fecha" if fecha is None else "es del {}".format(fecha), referencia["fecha"])


def _archivo_cliente(datos, slug, nombre):
    carpeta = _ruta_cartera(datos, slug).parent
    ruta = carpeta / nombre
    if ruta.is_symlink() or ruta.resolve().parent != carpeta.resolve():
        raise ErrorCartera("{} debe permanecer en la carpeta del cliente y no ser un enlace.".format(nombre))
    return ruta


def _rechazar_futura(fecha, nombre):
    if fecha > datetime.now(ZoneInfo("America/Argentina/Buenos_Aires")).date():
        raise ErrorDiaCero("La fecha {} no puede ser futura en Argentina.".format(nombre))


def _fecha_cli(texto, defecto, nombre="del día cero"):
    try:
        fecha = date.fromisoformat(texto) if texto is not None else defecto
    except (TypeError, ValueError):
        raise ErrorDiaCero("La fecha debe tener formato AAAA-MM-DD.") from None
    _rechazar_futura(fecha, nombre)
    return fecha


def _leer_efectivo(datos, slug):
    ruta = _archivo_cliente(datos, slug, "efectivo.json")
    if not ruta.exists():
        return _validar_efectivo(None)
    try:
        contenido = json.loads(ruta.read_text(encoding="utf-8"))
    except (ValueError, UnicodeError):
        raise ErrorDiaCero("efectivo.json no es un JSON válido.") from None
    efectivo = _validar_efectivo(contenido)
    if efectivo["fecha"] is not None:
        _rechazar_futura(date.fromisoformat(efectivo["fecha"]), "del efectivo")
    return efectivo


def _avisos_cotizaciones(cotizaciones):
    for ticker, cotizacion in cotizaciones.items():
        if cotizacion.estado != "vivo":
            precio = "sin dato" if cotizacion.ultimo is None else _numero(cotizacion.ultimo)
            print("{}: {} · precio {} · consulta {}".format(
                ticker, cotizacion.estado, precio, cotizacion.consultado_en.isoformat()))


def _capturar(datos, slug, punto):
    cache = _archivo_cliente(datos, slug, "cache_precios.json")
    historial = _archivo_cliente(datos, slug, "historial.csv")
    cliente = ClientePrecios(consultar_json, cache, persistir_cache=False)
    cotizaciones = cliente.obtener(punto.posiciones)
    mep = cliente.dolar_mep()
    if mep is not None:
        cotizaciones["MEP"] = mep
    filas = capturar_historial(cotizaciones, historial)
    print("Historial: {} filas agregadas.".format(filas))
    _avisos_cotizaciones(cotizaciones)
    if mep is None:
        print("Dólar MEP: sin dato; no se agregó al historial.")
    for aviso in advertencias_precio(punto.lotes, punto.posiciones, cotizaciones):
        print(aviso)
    try:
        cliente.guardar_cache()
    except OSError as error:
        print("ADVERTENCIA: el historial guardó {} filas, pero no se pudo guardar la caché: {}".format(
            filas, error), file=sys.stderr)
        return 1
    if not filas:
        print("No se obtuvo ninguna cotización viva; el historial no se actualizó.", file=sys.stderr)
        return 1
    return 0


def _fijar_referencia(opciones, datos, punto):
    hoy = datetime.now(ZoneInfo("America/Argentina/Buenos_Aires")).date()
    fecha = _fecha_cli(opciones.fecha, hoy)
    ruta = _archivo_cliente(datos, opciones.cliente, "dia_cero.json")
    cache = _archivo_cliente(datos, opciones.cliente, "cache_precios.json")
    habia_dia_cero = ruta.exists()
    if habia_dia_cero and not opciones.forzar:
        raise ErrorDiaCero("El día cero ya existe; usá --forzar solo si querés volver a tomar la referencia.")
    # Validar antes de consultar precios o modificar la foto y la caché.
    movimientos = leer_movimientos(_archivo_cliente(datos, opciones.cliente, "movimientos.csv"))
    validar_movimientos(punto, movimientos, fecha, hoy)
    efectivo = _leer_efectivo(datos, opciones.cliente)
    cliente = ClientePrecios(consultar_json, cache, persistir_cache=False)
    cotizaciones = cliente.obtener(punto.posiciones)
    mep = cliente.dolar_mep()
    # La consulta queda en memoria hasta que todos los datos validan y se fija la foto.
    referencia = fijar_dia_cero(punto.posiciones, cotizaciones, ruta, fecha,
                               forzar=opciones.forzar, mep=mep.ultimo if mep else None, efectivo=efectivo)
    try:
        cliente.guardar_cache()
    except OSError as error:
        # La foto ya quedó guardada: avisar la falla de caché sin fingir que falló la fijación.
        print("ADVERTENCIA: el día cero se guardó, pero no se pudo guardar la caché: {}".format(error), file=sys.stderr)
    print("Día cero fijado.")
    if habia_dia_cero:
        print("Versión anterior guardada en {}.".format(ruta.parent / "historial_dia_cero"))
    if fecha != hoy:
        print("ADVERTENCIA: --fecha etiqueta el día cero; los precios son de la consulta actual, "
              "no cotizaciones históricas de esa fecha.")
    print("\n".join(_lineas_dia_cero(punto, referencia)))
    for aviso in advertencias_precio(punto.lotes, punto.posiciones, cotizaciones):
        print(aviso)
    return 0


def _cargar_efectivo(opciones, datos, punto):
    ruta = _archivo_cliente(datos, opciones.cliente, "dia_cero.json")
    referencia = _leer_dia_cero(ruta)
    fecha = _fecha_cli(opciones.fecha, date.fromisoformat(referencia["fecha"]), "del efectivo")
    efectivo = _validar_efectivo({"fecha": fecha.isoformat(), "ARS": opciones.ars, "USD": opciones.usd})
    # Un error de rango al convertir USD debe aparecer antes de modificar la foto.
    patrimonio_inicial(punto.posiciones, dict(referencia, efectivo=efectivo))
    habia_efectivo = any(referencia["efectivo"].get(moneda) is not None for moneda in ("ARS", "USD"))
    referencia = cargar_efectivo_dia_cero(ruta, efectivo, forzar=opciones.forzar)
    print("Efectivo del día cero cargado; se conservaron los precios y cantidades guardados.")
    if habia_efectivo:
        print("Versión anterior guardada en {}.".format(ruta.parent / "historial_dia_cero"))
    print("\n".join(_lineas_dia_cero(punto, referencia)))
    return 0


def _historia_actual(datos, slug, punto, referencia):
    movimientos = leer_movimientos(_archivo_cliente(datos, slug, "movimientos.csv"))
    fecha_cero = date.fromisoformat(referencia["fecha"]) if referencia else None
    hoy = datetime.now(ZoneInfo("America/Argentina/Buenos_Aires")).date()
    validar_movimientos(punto, movimientos, fecha_cero, hoy)
    actual, realizados = cartera_actual(punto, movimientos)
    return movimientos, actual, realizados


def _movimiento(opciones, datos, punto):
    ruta_cero = _archivo_cliente(datos, opciones.cliente, "dia_cero.json")
    if not ruta_cero.exists():
        raise ErrorDiaCero("Primero fijá el día cero para registrar movimientos.")
    referencia = _leer_dia_cero(ruta_cero)
    ruta = _archivo_cliente(datos, opciones.cliente, "movimientos.csv")
    movimiento = {campo: getattr(opciones, campo) for campo in (
        "fecha", "tipo", "ticker", "cantidad", "importe", "moneda", "tc", "tipo_activo", "nota")}
    agregado = agregar_movimiento(ruta, punto, movimiento, date.fromisoformat(referencia["fecha"]),
                                  datetime.now(ZoneInfo("America/Argentina/Buenos_Aires")).date())
    print("Movimiento guardado: {} · {} · {} {}.".format(
        agregado["fecha"].isoformat(), agregado["tipo"], _numero(agregado["importe"]), agregado["moneda"]))
    if agregado["ticker"]:
        actual, _ = cartera_actual(punto, leer_movimientos(ruta))
        cantidad = next((p.cantidad for p in actual.posiciones if p.ticker == agregado["ticker"]), 0)
        print("Tenencia actual {}: {}.".format(agregado["ticker"], _cantidad(cantidad)))
    return 0


def _mostrar_actualizacion(resultado):
    if not resultado["cambios"]:
        print("No hay cambios en los datos de la cartera; no se escribió ningún archivo.")
        return
    for cambio in resultado["cambios"]:
        anterior = "falta estimar" if cambio["costo_anterior"] is None else "$ " + _numero(cambio["costo_anterior"])
        nuevo = "falta estimar" if cambio["costo_nuevo"] is None else "$ " + _numero(cambio["costo_nuevo"])
        print("{} · costo anterior: {} · origen anterior: {} · costo nuevo: {} · origen nuevo: {}".format(
            cambio["ticker"], anterior, _origen(cambio["origen_anterior"]), nuevo, _origen(cambio["origen_nuevo"])))
    for advertencia in resultado["advertencias"]:
        print(advertencia)
    print("Costos actualizados. Versión anterior completa: {}".format(resultado["historial"]))


def _importe_historial(valor):
    return "sin dato" if valor is None else _numero(valor)


def _mostrar_historial(historial, carpeta):
    lineas = ["Rendimiento realizado histórico · cálculo independiente del día cero."]
    titulos = {"dividendo": "Dividendos", "retencion": "Retenciones", "renta": "Rentas",
               "caucion_colocada": "Cauciones colocadas", "caucion_tomada": "Cauciones tomadas",
               "fci": "FCI", "gastos": "Gastos", "compensacion": "Compensaciones por error operativo"}
    for campo, bolsa in list(historial.ingresos.items()) + [("aportes", historial.aportes), ("retiros", historial.retiros)]:
        lineas.append("{}: ARS {} · USD {} · equivalente ARS {}{}".format(
            titulos.get(campo, campo.capitalize()), _importe_historial(bolsa["ARS"]),
            _importe_historial(bolsa["USD"]), _importe_historial(bolsa["equivalente_ars"]),
            " · dinero del cliente, fuera del resultado" if campo in ("aportes", "retiros") else ""))
    por_especie = {}
    for realizado in historial.realizados:
        por_especie.setdefault(realizado.ticker, []).append(realizado)
    for ticker, realizados in sorted(por_especie.items()):
        conocidos = [r.resultado_ars for r in realizados if r.resultado_ars is not None]
        suma = float(sum((Decimal(str(v)) for v in conocidos), Decimal(0))) if conocidos else None
        from math import isfinite
        if suma is not None and not isfinite(suma):
            suma = None
        lineas.append("Realizado de {}: ARS {} · {} ventas/cierres sin dato.".format(
            ticker, _importe_historial(suma), sum(r.resultado_ars is None for r in realizados)))
        for r in realizados:
            lineas.append("  {} · {} · cantidad {} · sin lote {} · importe ARS {} · costo ARS {} · resultado ARS {} · origen {}".format(
                r.fecha.isoformat(), r.clase, _cantidad(r.cantidad), _cantidad(r.cantidad_sin_lote),
                _importe_historial(r.importe_ars), _importe_historial(r.costo_ars),
                _importe_historial(r.resultado_ars), "incompleto (sin dato)" if r.origen_costo == "incompleto" else _origen(r.origen_costo)))
    lineas.append("Realizado de extracto: ARS {} · realizado que incluye estimaciones: ARS {}.".format(
        _importe_historial(historial.realizado_extracto), _importe_historial(historial.realizado_estimado)))
    lineas.append("Total conocido: ARS {}. Ventas/cierres sin dato: {}; valores sin dato: {}; renglones sin clasificar: {}.".format(
        _importe_historial(historial.total_conocido), historial.ventas_sin_dato,
        historial.valores_sin_dato, len(historial.sin_clasificar)))
    if historial.ventas_sin_dato or historial.valores_sin_dato or historial.sin_clasificar or historial.avisos:
        lineas.append("Total conocido sujeto a revisión: revisá los faltantes y avisos; no se presenta como un resultado completo.")
    for aviso in historial.avisos:
        lineas.append("ADVERTENCIA: " + aviso)
    for fila in historial.sin_clasificar:
        lineas.append("SIN CLASIFICAR (no se suma): " + json.dumps(fila, ensure_ascii=False, allow_nan=False, default=str))
    for titulo, diferencias in (("Cantidades", historial.diferencias_tenencias), ("Costos ARS", historial.diferencias_costos)):
        for ticker, valores in diferencias.items():
            lineas.append("{} de {}: derivada {} · base {} · diferencia {}.".format(
                titulo, ticker, _importe_historial(valores["derivada"]),
                _importe_historial(valores["base"]), _importe_historial(valores["diferencia"])))
    lineas.append("Ventas y cierres guardados: {}".format(carpeta / "realizado.csv"))
    print("\n".join(lineas))


def _revisar_amortizaciones(base, movimientos):
    cantidades = {p.ticker: Decimal(str(p.cantidad)) for p in base.posiciones}
    tipos = {p.ticker: p.tipo for p in base.posiciones}
    encontradas = 0
    for indice, movimiento in sorted(enumerate(movimientos, 1), key=lambda fila: fila[1]["fecha"]):
        tipo, ticker = movimiento["tipo"], movimiento["ticker"]
        if tipo == "compra":
            tipos.setdefault(ticker, movimiento["tipo_activo"])
            cantidades[ticker] = cantidades.get(ticker, Decimal(0)) + Decimal(str(movimiento["cantidad"]))
        elif tipo == "venta":
            cantidades[ticker] -= Decimal(str(movimiento["cantidad"]))
            nota = unicodedata.normalize("NFKD", movimiento["nota"].casefold())
            nota = "".join(c for c in nota if not unicodedata.combining(c))
            if tipos[ticker] in ("bono", "on") and cantidades[ticker] > 0 and "amortiz" in nota:
                encontradas += 1
                print("Movimiento {} · {} · {} · posible amortización parcial · {} VN remanentes.".format(
                    indice, movimiento["fecha"], ticker, _cantidad(cantidades[ticker])))
    print("{} ventas parciales para revisar.".format(encontradas))
    return 0


def main(argumentos=None):
    parser = argparse.ArgumentParser(description="Seguimiento local de carteras: base, movimientos y resultado completo.")
    parser.add_argument("--datos", metavar="RUTA", help="Carpeta de datos; alternativa: CARTERA_DATOS.")
    comandos = parser.add_subparsers(dest="comando", required=True)
    importar = comandos.add_parser("importar", help="Validar y conservar el Excel de punto de partida.")
    importar.add_argument("--cliente", required=True, metavar="SLUG")
    importar.add_argument("--archivo", required=True, metavar="EXCEL")
    actualizar = comandos.add_parser("actualizar-costos", help="Corregir lotes y costos conservando la versión anterior.")
    actualizar.add_argument("--cliente", required=True, metavar="SLUG")
    actualizar.add_argument("--archivo", required=True, metavar="EXCEL")
    estado = comandos.add_parser("estado", help="Mostrar tenencias actuales, efectivo, flujos y origen de costos.")
    estado.add_argument("--cliente", required=True, metavar="SLUG")
    capturar = comandos.add_parser("capturar", help="Consultar precios y guardar el historial observado.")
    capturar.add_argument("--cliente", required=True, metavar="SLUG")
    fijar = comandos.add_parser("fijar-dia-cero", help="Guardar cantidades, precios y efectivo iniciales.")
    fijar.add_argument("--cliente", required=True, metavar="SLUG")
    fijar.add_argument("--fecha", metavar="AAAA-MM-DD")
    fijar.add_argument("--forzar", action="store_true")
    efectivo = comandos.add_parser("efectivo-dia-cero", help="Cargar efectivo inicial sin volver a consultar precios.")
    efectivo.add_argument("--cliente", required=True, metavar="SLUG")
    efectivo.add_argument("--ars", required=True, type=float, metavar="N")
    efectivo.add_argument("--usd", required=True, type=float, metavar="N")
    efectivo.add_argument("--fecha", metavar="AAAA-MM-DD")
    efectivo.add_argument("--forzar", action="store_true")
    dashboard = comandos.add_parser("dashboard", help="Generar el tablero local autocontenido.")
    dashboard.add_argument("--cliente", required=True, metavar="SLUG")
    alertas = comandos.add_parser("alertas", help="Chequear niveles y vencimientos y enviar avisos.")
    alertas.add_argument("--cliente", required=True, metavar="SLUG")
    movimiento = comandos.add_parser("movimiento", help="Registrar un movimiento posterior al día cero.")
    movimiento.add_argument("--cliente", required=True, metavar="SLUG")
    for campo in ("fecha", "tipo", "importe"):
        movimiento.add_argument("--" + campo, required=True)
    for campo in ("ticker", "tipo-activo", "nota"):
        movimiento.add_argument("--" + campo, default="")
    movimiento.add_argument("--cantidad", default="")
    movimiento.add_argument("--moneda", default="ARS")
    movimiento.add_argument("--tc", default=None)
    historial = comandos.add_parser("historial", help="Calcular lo vendido y cobrado desde los extractos.")
    historial.add_argument("--cliente", required=True, metavar="SLUG")
    historial.add_argument("--actualizar-mep", action="store_true", help="Actualizar MEP diario con cierres históricos de AL30 y AL30D.")
    derivar = comandos.add_parser("derivar-base", help="Crear cartera.json desde la historia completa de extractos.")
    derivar.add_argument("--cliente", required=True, metavar="SLUG")
    derivar.add_argument("--reemplazar", action="store_true")
    letras = comandos.add_parser("letras", help="Listar compras de letras para cargar su precio limpio.")
    letras.add_argument("--cliente", required=True, metavar="SLUG")
    precio_letra = comandos.add_parser("precio-letra", help="Registrar el precio manual de una compra de letra.")
    precio_letra.add_argument("--cliente", required=True, metavar="SLUG")
    precio_letra.add_argument("--referencia", required=True, metavar="REF")
    precio_letra.add_argument("--precio", required=True, metavar="N", help="Precio limpio por cada 100 nominales, sin gastos.")
    precio_letra.add_argument("--moneda", required=True, choices=("ARS", "USD"))
    precio_letra.add_argument("--liquidacion", required=True, metavar="AAAA-MM-DD")
    comandos.add_parser("indices", help="Actualizar series BCRA y el último REM publicado.")
    iamc = comandos.add_parser("iamc", help="Guardar el cierre diario de IAMC.")
    iamc.add_argument("--html", metavar="RUTA", help="Procesar un HTML guardado.")
    bonos = comandos.add_parser("bonos", help="Listar compras de bonos y ON.")
    bonos.add_argument("--cliente", required=True, metavar="SLUG")
    precio_bono = comandos.add_parser("precio-bono", help="Registrar el precio sucio de una compra de bono u ON.")
    precio_bono.add_argument("--cliente", required=True, metavar="SLUG")
    precio_bono.add_argument("--referencia", required=True, metavar="REF")
    precio_bono.add_argument("--precio", required=True, metavar="N", help="Precio sucio por cada 100 VN originales.")
    precio_bono.add_argument("--moneda", required=True, choices=("ARS", "USD"))
    precio_bono.add_argument("--liquidacion", required=True, metavar="AAAA-MM-DD")
    precio_bono.add_argument("--tc", metavar="N", help="Pesos por dólar de la compra, si difieren las monedas.")
    flujo = comandos.add_parser("flujo", help="Revisar ventas cargadas como amortizaciones parciales.")
    flujo.add_argument("--cliente", required=True, metavar="SLUG")
    flujo.add_argument("--revisar", required=True, action="store_true")
    informe = comandos.add_parser("informe", help="Generar el informe para el cliente desde el último dashboard.")
    informe.add_argument("--cliente", required=True, metavar="SLUG")
    informe.add_argument("--salida", metavar="CARPETA", help="Carpeta del informe; por defecto, informes/ del cliente.")
    informe.add_argument("--pdf", action="store_true", help="Generar también el PDF con Google Chrome.")
    riesgo = comandos.add_parser("riesgo", help="Medir el riesgo desde el último dashboard.")
    riesgo.add_argument("--cliente", required=True, metavar="SLUG")
    riesgo.add_argument("--sin-red", action="store_true", help="Usar solo históricos guardados.")
    opciones = parser.parse_args(argumentos)
    datos = opciones.datos if opciones.datos is not None else os.environ.get("CARTERA_DATOS")
    if not datos or not datos.strip():
        parser.error("Indicá --datos RUTA o definí CARTERA_DATOS.")
    try:
        if opciones.comando == "indices":
            from .indices_archivos import actualizar_indices
            avisos_indices = actualizar_indices(datos)
            for aviso in avisos_indices:
                print(aviso, file=sys.stderr)
            if not avisos_indices:
                print("Series del BCRA y REM al día.")
            return 1 if avisos_indices else 0
        if opciones.comando == "iamc":
            from .iamc import ejecutar_iamc
            return ejecutar_iamc(datos, opciones.html)
        if opciones.comando == "informe":
            from .informe import ejecutar_informe
            return ejecutar_informe(opciones, datos)
        if opciones.comando == "riesgo":
            from .riesgo import ejecutar_riesgo
            return ejecutar_riesgo(opciones, datos)
        if opciones.comando in ("bonos", "precio-bono"):
            from .letras_archivos import ejecutar_bonos
            return ejecutar_bonos(opciones, datos)
        if opciones.comando == "importar":
            punto, _ = importar_cartera(datos, opciones.cliente, opciones.archivo)
            print("Base inicial guardada para {}: {} posiciones y {} lotes.".format(
                opciones.cliente, len(punto.posiciones), len(punto.lotes)))
        elif opciones.comando == "derivar-base":
            punto, _ = derivar_base(datos, opciones.cliente, reemplazar=opciones.reemplazar)
            print("Base derivada guardada para {}: {} posiciones y {} lotes.".format(
                opciones.cliente, len(punto.posiciones), len(punto.lotes)))
            for posicion in punto.posiciones:
                print("{} · {} · cantidad {}.".format(
                    posicion.ticker, posicion.especie, _cantidad(posicion.cantidad)))
        elif opciones.comando == "actualizar-costos":
            _mostrar_actualizacion(actualizar_costos(datos, opciones.cliente, opciones.archivo))
        else:
            punto, contenido = cargar_cartera(datos, opciones.cliente)
            if opciones.comando in ("letras", "precio-letra"):
                from .letras_archivos import ejecutar_letras
                return ejecutar_letras(opciones, datos)
            if opciones.comando == "historial":
                from .historial import correr_historial
                carpeta = _ruta_cartera(datos, opciones.cliente).parent
                historial = correr_historial(carpeta, punto, fetch=consultar_json, actualizar_mep=opciones.actualizar_mep)
                _mostrar_historial(historial, carpeta)
                return 0
            if opciones.comando == "alertas":
                from . import alertas_comando, notificar
                carpeta = _ruta_cartera(datos, opciones.cliente).parent
                def canales_alertas():
                    yield from notificar.canales_disponibles()
                entrega = alertas_comando.correr_alertas(
                    carpeta, punto, opciones.cliente, consultar_json,
                    canales_alertas(), alertas_comando.ahora_argentina())
                if entrega.get("omitida"):
                    return 0
                print("Corrida de alertas: {} eventos nuevos; evaluación de niveles {}.".format(
                    len(entrega["eventos"]), "realizada" if entrega["evaluo_niveles"] else "omitida"))
                for aviso in entrega.get("avisos", []):
                    print("ADVERTENCIA: " + aviso)
                for error in entrega["errores"]:
                    print(error, file=sys.stderr)
                if not entrega["entregado"]:
                    print("Los avisos no se entregaron; el estado nuevo no se guardó y se reintentará.", file=sys.stderr)
                return 0 if entrega["entregado"] else 1
            if opciones.comando == "dashboard":
                from .dashboard_archivos import crear_dashboard
                from .iamc import guardar_cierre_del_dia
                carpeta = _ruta_cartera(datos, opciones.cliente).parent
                mensaje_iamc, aviso_iamc = guardar_cierre_del_dia(datos)
                entrega = crear_dashboard(punto, carpeta, opciones.cliente, consultar_json, datos=datos,
                                          aviso_iamc=aviso_iamc)
                print("Dashboard guardado: {}".format(entrega["ruta"]))
                if mensaje_iamc:
                    print(mensaje_iamc)
                if aviso_iamc:
                    print("ADVERTENCIA: " + aviso_iamc)
                _avisos_cotizaciones(entrega["cotizaciones"])
                for aviso in entrega["avisos"]:
                    print("ADVERTENCIA: " + aviso)
                return 0
            if opciones.comando == "fijar-dia-cero":
                return _fijar_referencia(opciones, datos, punto)
            if opciones.comando == "efectivo-dia-cero":
                return _cargar_efectivo(opciones, datos, punto)
            ruta = _archivo_cliente(datos, opciones.cliente, "dia_cero.json")
            referencia = _leer_dia_cero(ruta) if ruta.exists() else None
            if opciones.comando == "movimiento":
                return _movimiento(opciones, datos, punto)
            movimientos, actual, realizados = _historia_actual(datos, opciones.cliente, punto, referencia)
            if opciones.comando == "flujo":
                return _revisar_amortizaciones(punto, movimientos)
            if opciones.comando == "capturar":
                return _capturar(datos, opciones.cliente, actual)
            control = conciliar_efectivo(referencia, movimientos, _leer_efectivo(datos, opciones.cliente))
            _mostrar_estado(opciones.cliente, actual, contenido, referencia, punto, movimientos, realizados, control)
    except ErrorPuntoPartida as error:
        for mensaje in error.errores:
            print(mensaje, file=sys.stderr)
        return 1
    except (ValueError, OSError, ErrorDiaCero) as error:
        print(str(error), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
