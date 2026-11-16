#!/usr/bin/env python3
"""Descarga una muestra de CER, TAMAR privada TNA y A3500 del BCRA."""

import argparse
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from cartera.indices import ErrorBCRA, URL, SERIES, extraer, _fecha, _guardar


def main(argumentos=None, *, fetch=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--desde", required=True, help="Primera fecha de referencia, inclusive (AAAA-MM-DD).")
    parser.add_argument("--hasta", required=True, help="Última fecha de referencia, inclusive (AAAA-MM-DD).")
    parser.add_argument("--salida", required=True, type=Path, help="Archivo JSON nuevo fuera del proyecto.")
    opciones = parser.parse_args(argumentos)
    try:
        destino = opciones.salida.expanduser()
        destino = destino.parent.resolve() / destino.name
        proyecto = Path(__file__).resolve().parents[1]
        if destino == proyecto or proyecto in destino.parents:
            raise ErrorBCRA("Elegí un archivo de salida fuera del proyecto.")
        if destino.exists() or destino.is_symlink():
            raise ErrorBCRA("El archivo de salida ya existe. Elegí otro para conservar la captura.")
        datos = extraer(_fecha(opciones.desde), _fecha(opciones.hasta), fetch=fetch)
        _guardar(datos, destino)
    except (ErrorBCRA, OSError) as error:
        print("BCRA: {}".format(error), file=sys.stderr)
        return 1
    print("Muestra del BCRA guardada en {}.".format(destino))
    for clave, serie in datos["series"].items():
        observaciones = serie["observaciones"]
        if observaciones:
            print("{} · {} observaciones · última fecha {}".format(
                clave, len(observaciones), observaciones[-1]["fecha"]))
        else:
            print("{} · sin dato en el rango consultado".format(clave))
    return 0


if __name__ == "__main__":
    sys.exit(main())
