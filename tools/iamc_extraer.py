#!/usr/bin/env python3
"""Extractor de relevamiento IAMC/BYMA con muestras por instrumento."""

import argparse
import copy
import hashlib
import os
from pathlib import Path
import sys

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from cartera import iamc
from cartera.iamc import (
    ErrorExtraccion, MAX_BYTES, ROBOTS, URL, _bytes_json, _fecha_iso, _json,
    _objeto, _publicar, descargar_cierre, guardar_cierre,
)

BONOS_MUESTRA = ("AL30", "TX26", "TZXS7", "TMVE8", "YM34O")
LETRAS_MUESTRA = ("S30N6", "T30A7")


def extraer_html(contenido):
    return iamc.extraer_html(contenido, max_bytes=MAX_BYTES)


def guardar_muestras(datos, salida):
    """Copia registros crudos; un ticker ausente se documenta sin reemplazarlo."""
    salida = Path(salida)
    estado = {"fecha_cierre": datos["fecha_cierre"], "origen": URL, "muestras": [],
              "fuente": {clave: copy.deepcopy(datos["metadatos"].get(clave))
                         for clave in ("fuente_url", "html_sha256", "payload_sha256", "adquisicion")}}
    secciones = {
        "calculadora_bonos.json": datos["calculadora_bonos"],
        "calculadora_letras.json": datos["calculadora_letras"],
        "informe_titulos_publicos.json": datos["informes"]["titulos_publicos"],
        "informe_on.json": datos["informes"]["on"],
        "macro_payload_crudo.json": datos["macro"],
        "padron_inicial.json": datos["padron"]["crudo"],
        "mercado_dinero.json": datos["caucion"]["mercado_dinero"],
        "calculadora_caucion_inicial.json": datos["caucion"]["calculadora"],
    }
    for nombre, contenido in secciones.items():
        _publicar(salida / nombre, _bytes_json(contenido))
    informes = {}
    for clave in ("titulos_publicos", "on"):
        for indice, registro in enumerate(datos["informes"][clave]["rows"]):
            informes[registro["tk"]] = (registro, "payload.{}.rows[{}]".format("tp" if clave == "titulos_publicos" else "on", indice))
    calculadoras = {registro["tk"]: (registro, "payload.calc.ins[{}]".format(indice))
                    for indice, registro in enumerate(datos["calculadora_bonos"]["ins"])}
    catalogo = {}
    for indice, registro in enumerate(datos.get("catalogo", [])):
        if isinstance(registro, dict) and isinstance(registro.get("tk"), str):
            catalogo[registro["tk"]] = (registro, "payload.cat[{}]".format(indice))
    for clase, tickers, registros in (
        ("bonos", BONOS_MUESTRA, datos["calculadora_bonos"]["ins"]),
        ("letras", LETRAS_MUESTRA, datos["calculadora_letras"]["instrumentos"]),
    ):
        indice = {registro["tk"]: registro for registro in registros}
        for ticker in tickers:
            registro = indice.get(ticker)
            if registro is None:
                nombre = clase + "/" + ticker + ".ausente.json"
                contenido = {"ticker": ticker, "fecha_cierre": datos["fecha_cierre"], "disponible": False,
                             "motivo": "No está en la sección del payload de este cierre; no se sustituyó por otro título.",
                             "calculadora": calculadoras.get(ticker, (None, None))[0], "informe": informes.get(ticker, (None, None))[0],
                             "catalogo": catalogo.get(ticker, (None, None))[0]}
            else:
                nombre = clase + "/" + ticker + ".json"
                contenido = {"calculadora": calculadoras.get(ticker, (None, None))[0],
                             "informe": informes.get(ticker, (None, None))[0],
                             "catalogo": catalogo.get(ticker, (None, None))[0],
                             "origenes": {"calculadora": calculadoras.get(ticker, (None, None))[1],
                                          "informe": informes.get(ticker, (None, None))[1],
                                          "catalogo": catalogo.get(ticker, (None, None))[1]}}
            _publicar(salida / nombre, _bytes_json(contenido))
            estado["muestras"].append({"ticker": ticker, "seccion": clase, "archivo": nombre,
                                       "disponible": registro is not None})
    _publicar(salida / "estado_muestras.json", _bytes_json(estado))
    return estado


def main(argumentos=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--html", type=Path, help="HTML guardado: extracción sin ninguna consulta de red.")
    parser.add_argument("--salida", type=Path, required=True, help="Carpeta para el JSON fechado por cierre.")
    parser.add_argument("--cache", type=Path, help="Caché diaria; por defecto SALIDA/.cache_iamc.")
    parser.add_argument("--muestras", type=Path, help="Carpeta para copias crudas de las secciones y tickers de prueba.")
    opciones = parser.parse_args(argumentos)
    try:
        if opciones.html is not None:
            cuerpo = opciones.html.read_bytes()
            meta = {"modo": "archivo_local", "html_origen": str(opciones.html.resolve()), "consulta_red": False}
            ruta_meta = opciones.html.with_name(opciones.html.name + ".http.json")
            if ruta_meta.exists():
                http = _objeto(_json(ruta_meta.read_text(encoding="utf-8")), "Metadatos HTTP locales")
                if http.get("sha256") != hashlib.sha256(cuerpo).hexdigest():
                    raise ErrorExtraccion("Los metadatos HTTP locales no coinciden con la huella del HTML.")
                meta["http_guardado"] = http
        else:
            cuerpo, meta = descargar_cierre(opciones.cache or opciones.salida / ".cache_iamc")
        datos = extraer_html(cuerpo)
        datos["metadatos"]["adquisicion"] = meta
        ruta = guardar_cierre(datos, opciones.salida)
        if opciones.muestras is not None:
            guardar_muestras(datos, opciones.muestras)
        print("Cierre extraído: {} · liquidación {} · {} bonos · {} letras.".format(
            datos["fecha_cierre"], datos["fecha_liquidacion"], len(datos["calculadora_bonos"]["ins"]),
            len(datos["calculadora_letras"]["instrumentos"])))
        print("JSON: " + str(ruta))
        for aviso in datos["metadatos"]["avisos"] + meta.get("robots_avisos", []):
            print("AVISO: " + aviso)
        return 0
    except (ErrorExtraccion, OSError, UnicodeError) as error:
        print("Error: " + str(error), file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
