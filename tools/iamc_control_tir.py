"""Control de investigación IAMC. No es un motor aprobado ni integra cartera.

Resuelve la TIR efectiva anual ACT/365 de los flujos crudos de la calculadora.
No usa la TIR publicada ni el campo de calibración para obtener el resultado.
"""

import argparse
import hashlib
import json
import math
import os
import tempfile
import re
from datetime import date, timedelta
from pathlib import Path

TICKERS = ("AL30", "TX26", "TZXS7", "TMVE8", "YM34O")
FUENTE = "https://www.iamc.com.ar/informediario/"


def _numero(valor, campo):
    if isinstance(valor, bool) or not isinstance(valor, (float, int)) or not math.isfinite(valor):
        raise ValueError(campo + " debe ser un número finito observado.")
    return valor


def resolver_tir(flujos, precio):
    """Bisección independiente para pagos no negativos en días corridos futuros."""
    precio = _numero(precio, "Precio")
    if precio <= 0 or not flujos:
        raise ValueError("Se requieren precio positivo y flujos futuros.")
    pagos = []
    for dias, monto in flujos:
        dias, monto = _numero(dias, "Días"), _numero(monto, "Pago")
        if dias <= 0 or monto < 0:
            raise ValueError("Este control requiere días positivos y pagos no negativos.")
        if monto:
            pagos.append((dias / 365.0, monto))
    if not pagos:
        raise ValueError("El flujo no tiene pagos positivos.")

    def diferencia(tasa):
        try:
            return math.fsum(pago * math.exp(-plazo * math.log1p(tasa)) for plazo, pago in pagos) - precio
        except OverflowError:
            return math.inf

    inferior, superior = -0.999999999999, 1.0
    if diferencia(inferior) < 0:
        raise ValueError("La raíz queda fuera del rango numérico comprobable.")
    for _ in range(60):
        if diferencia(superior) <= 0:
            break
        superior = superior * 2 + 1
    else:
        raise ValueError("No se pudo acotar la TIR.")
    for _ in range(200):
        medio = (inferior + superior) / 2
        if diferencia(medio) > 0:
            inferior = medio
        else:
            superior = medio
    tasa = (inferior + superior) / 2
    residuo = diferencia(tasa)
    if not math.isfinite(tasa) or abs(residuo) > max(1, precio) * 1e-10:
        raise ValueError("La TIR no cerró contra el precio con tolerancia numérica suficiente.")
    return tasa, residuo


def _flujos_calculadora(instrumento):
    liquidacion = date.fromisoformat(instrumento["liq"])
    pagos, detalle = [], []
    for fila in instrumento["f"]:
        if not isinstance(fila, list) or len(fila) != 4:
            raise ValueError("Flujo de calculadora con estructura inesperada.")
        dias, amortizacion, renta, base_variable = fila
        dias = _numero(dias, "Días de flujo")
        if dias != int(dias):
            raise ValueError("Días de flujo debe ser entero.")
        amortizacion, renta = _numero(amortizacion, "Amortización"), _numero(renta, "Renta")
        _numero(base_variable, "Base variable")
        total = amortizacion + renta
        pagos.append((dias, total))
        detalle.append({"fecha": (liquidacion + timedelta(days=int(dias))).isoformat(),
                        "dias_corridos": dias, "amortizacion": amortizacion, "renta": renta,
                        "total": total, "base_variable_cruda": base_variable})
    return pagos, detalle


def _flujos_informe(fila, liquidacion):
    pagos = {}
    for campo in ("amo", "ren"):
        if not isinstance(fila.get(campo), list):
            raise ValueError("Falta el cronograma " + campo)
        for fecha, monto in fila[campo]:
            dias = (date.fromisoformat(fecha) - liquidacion).days
            if dias <= 0:
                raise ValueError("El informe contiene un pago no futuro.")
            pagos[dias] = pagos.get(dias, 0) + _numero(monto, "Pago de informe")
    return sorted(pagos.items())


def comparar(payload, tickers=TICKERS):
    if not isinstance(payload, dict) or not isinstance(payload.get("calc", {}).get("ins"), list):
        raise ValueError("Falta payload.calc.ins; no se puede verificar la calculadora.")
    calculadora = payload["calc"]["ins"]
    informes = [fila for grupo in ("tp", "on") for fila in payload.get(grupo, {}).get("rows", [])]
    resultados = []
    for ticker in tickers:
        caso = {"ticker": ticker, "estado": "sin_dato", "convencion": "ACT/365", "comisiones": 0,
                "fuente_calculadora": FUENTE + "#cbon", "fuente_informe": FUENTE + "#rf"}
        instrumentos = [fila for fila in calculadora if fila.get("tk") == ticker]
        filas = [fila for fila in informes if fila.get("tk") == ticker]
        if len(instrumentos) != 1 or len(filas) != 1:
            caso["motivo"] = "No hay una única fila del instrumento en calculadora e informe del cierre. No se sustituye por otro ticker."
            resultados.append(caso)
            continue
        instrumento, fila = instrumentos[0], filas[0]
        try:
            precio = _numero(instrumento["px"], "Precio de calculadora")
            publicada = _numero(fila["ytm"], "TIR publicada")
            pagos, detalle = _flujos_calculadora(instrumento)
            tasa, residuo = resolver_tir(pagos, precio)
            diferencia = (tasa - publicada / 100.0) * 10000
            caso.update(estado="difiere" if abs(diferencia) > 1 else "coincide",
                        precio=precio, precio_unidad="por 100 VN; unidad de flujo de calc.cur",
                        unidad_flujos=instrumento["cur"], moneda_pago=fila.get("mp"),
                        fx_referencia=instrumento.get("fxr"), fx_valor=instrumento.get("fxc"),
                        liquidacion=instrumento["liq"], fecha_cierre=payload[instrumento["g"]]["fecha"],
                        tir_publicada_pct=publicada, tir_recalculada_pct=tasa * 100,
                        diferencia_pb=diferencia, supera_1_pb=abs(diferencia) > 1,
                        residuo_precio=residuo, flujos_calculadora=detalle,
                        tipo_calculadora=instrumento.get("k"), segmento=fila.get("seg"),
                        campo_cal_observado_no_utilizado=instrumento.get("cal"))
            pagos_informe = _flujos_informe(fila, date.fromisoformat(instrumento["liq"]))
            tasa_informe, residuo_informe = resolver_tir(pagos_informe, precio)
            diferencia_informe = (tasa_informe - publicada / 100.0) * 10000
            caso["control_cruzado_flujo_informe"] = {
                "tir_recalculada_pct": tasa_informe * 100, "diferencia_pb": diferencia_informe,
                "supera_1_pb": abs(diferencia_informe) > 1, "residuo_precio": residuo_informe,
                "flujos_coinciden": pagos_informe == sorted(pagos),
                "fuente": "payload.tp/on.rows.amo + ren; precio full precision calc.ins.px"}
        except (KeyError, TypeError, ValueError, OverflowError) as error:
            caso.update(estado="sin_dato", motivo=str(error))
        resultados.append(caso)
    return {"esquema_version": 1, "uso": "Control experimental, no aprobado para producción",
            "criterio": "Diferencia absoluta mayor a 1 pb; 1 pb = 0,01 puntos porcentuales",
            "calibracion": "No se utiliza la TIR publicada ni el campo cal para resolver la TIR",
            "resultados": resultados}


def main(argumentos=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--html", required=True, type=Path, help="HTML crudo previamente descargado; no consulta la red.")
    parser.add_argument("--salida", required=True, type=Path)
    opciones = parser.parse_args(argumentos)
    try:
        if (opciones.salida.resolve() == opciones.html.resolve()
                or (opciones.salida.exists() and opciones.html.exists() and opciones.salida.samefile(opciones.html))):
            raise ValueError("La salida no puede sobrescribir el HTML original.")
        if opciones.salida.is_symlink():
            raise ValueError("La salida no puede ser un enlace.")
        contenido = opciones.html.read_bytes()
        texto = contenido.decode("utf-8-sig")
        encontrado = re.search(r'<script\b(?=[^>]*\bid=[\"\']payload[\"\'])[^>]*>(.*?)</script\s*>', texto, re.S | re.I)
        if encontrado is None:
            raise ValueError("No se encontró el JSON payload del cierre.")
        def constante(valor):
            raise ValueError("JSON no finito: " + valor)
        payload = json.loads(encontrado.group(1), parse_constant=constante)
        resultado = comparar(payload)
        resultado["sha256_html"] = hashlib.sha256(contenido).hexdigest()
        opciones.salida.parent.mkdir(parents=True, exist_ok=True)
        temporal = None
        try:
            with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=opciones.salida.parent,
                                             prefix=".control-tir-", suffix=".tmp", delete=False) as salida:
                temporal = Path(salida.name)
                salida.write(json.dumps(resultado, ensure_ascii=False, indent=2, allow_nan=False) + "\n")
                salida.flush()
                os.fsync(salida.fileno())
            os.replace(str(temporal), str(opciones.salida))
        finally:
            if temporal is not None:
                temporal.unlink(missing_ok=True)
        for caso in resultado["resultados"]:
            print(caso["ticker"], caso["estado"], caso.get("diferencia_pb", "sin dato"), "pb")
        return 0
    except (OSError, ValueError, TypeError) as error:
        parser.exit(1, str(error) + "\n")


if __name__ == "__main__":
    raise SystemExit(main())
