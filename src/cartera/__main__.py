"""Comandos de base inicial, precios y referencia del día cero."""

import argparse
import json
import os
import sys
from datetime import date, datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

from .almacenamiento import ErrorCartera, _ruta_cartera, actualizar_costos, cargar_cartera, importar_cartera
from .calculos import costo_total, estado_costo
from .dia_cero import _leer_dia_cero, _validar_efectivo
from .precios import (
    ClientePrecios, ErrorDiaCero, advertencias_precio, capturar_historial,
    cargar_efectivo_dia_cero, fijar_dia_cero, patrimonio_inicial,
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


def _mostrar_estado(slug, punto, contenido, referencia=None):
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
        lineas.extend(_lineas_dia_cero(punto, referencia))
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


def main(argumentos=None):
    parser = argparse.ArgumentParser(description="Seguimiento local de carteras: base inicial, precios y día cero.")
    parser.add_argument("--datos", metavar="RUTA", help="Carpeta de datos; alternativa: CARTERA_DATOS.")
    comandos = parser.add_subparsers(dest="comando", required=True)
    importar = comandos.add_parser("importar", help="Validar y conservar el Excel de punto de partida.")
    importar.add_argument("--cliente", required=True, metavar="SLUG")
    importar.add_argument("--archivo", required=True, metavar="EXCEL")
    actualizar = comandos.add_parser("actualizar-costos", help="Corregir lotes y costos conservando la versión anterior.")
    actualizar.add_argument("--cliente", required=True, metavar="SLUG")
    actualizar.add_argument("--archivo", required=True, metavar="EXCEL")
    estado = comandos.add_parser("estado", help="Mostrar la base inicial y el origen de sus costos.")
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
    opciones = parser.parse_args(argumentos)
    datos = opciones.datos if opciones.datos is not None else os.environ.get("CARTERA_DATOS")
    if not datos or not datos.strip():
        parser.error("Indicá --datos RUTA o definí CARTERA_DATOS.")
    try:
        if opciones.comando == "importar":
            punto, _ = importar_cartera(datos, opciones.cliente, opciones.archivo)
            print("Base inicial guardada para {}: {} posiciones y {} lotes.".format(
                opciones.cliente, len(punto.posiciones), len(punto.lotes)))
        elif opciones.comando == "actualizar-costos":
            _mostrar_actualizacion(actualizar_costos(datos, opciones.cliente, opciones.archivo))
        else:
            punto, contenido = cargar_cartera(datos, opciones.cliente)
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
                carpeta = _ruta_cartera(datos, opciones.cliente).parent
                entrega = crear_dashboard(punto, carpeta, opciones.cliente, consultar_json)
                print("Dashboard guardado: {}".format(entrega["ruta"]))
                _avisos_cotizaciones(entrega["cotizaciones"])
                for aviso in entrega["avisos"]:
                    print("ADVERTENCIA: " + aviso)
                return 0
            if opciones.comando == "capturar":
                return _capturar(datos, opciones.cliente, punto)
            if opciones.comando == "fijar-dia-cero":
                return _fijar_referencia(opciones, datos, punto)
            if opciones.comando == "efectivo-dia-cero":
                return _cargar_efectivo(opciones, datos, punto)
            ruta = _archivo_cliente(datos, opciones.cliente, "dia_cero.json")
            referencia = _leer_dia_cero(ruta) if ruta.exists() else None
            _mostrar_estado(opciones.cliente, punto, contenido, referencia)
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
