"""Comandos de la primera etapa: importar y consultar la base inicial."""

import argparse
import os
import sys
from decimal import Decimal

from .almacenamiento import actualizar_costos, cargar_cartera, importar_cartera
from .calculos import costo_total, estado_costo
from .punto_partida import ErrorPuntoPartida


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


def _mostrar_estado(slug, punto, contenido):
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
    print("\n".join(lineas))


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
    parser = argparse.ArgumentParser(description="Seguimiento local de carteras: base inicial.")
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
            _mostrar_estado(opciones.cliente, punto, contenido)
    except ErrorPuntoPartida as error:
        for mensaje in error.errores:
            print(mensaje, file=sys.stderr)
        return 1
    except (ValueError, OSError) as error:
        print(str(error), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
