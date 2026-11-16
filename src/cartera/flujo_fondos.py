"""Cronogramas y rendimiento de compra de renta fija a partir de cierres IAMC."""

from bisect import bisect_right
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal, DecimalException, localcontext
from typing import List, Optional

from .letras import (
    ErrorLetra, _decimal, _fecha, _hoy_argentina, _texto_decimal, letras_indexadas, referencias_flujo,
    validar_compras, validar_dato_compra,
)
from .movimientos import ErrorMovimiento, _normalizados, cartera_actual


_MONEDAS = ("ARS", "USD MEP", "USD cable")
_FIJA = "fix"
_PENDIENTE = "proyección pendiente: requiere supuestos"
_TOLERANCIA = Decimal("0.01")


@dataclass
class Pago:
    fecha: date
    amortizacion: Decimal
    renta: Decimal
    origen: str
    dual: Optional[tuple] = None

    @property
    def total(self):
        return self.amortizacion + self.renta


@dataclass
class Cronograma:
    ticker: str
    grupo: str
    familia: str
    moneda: str
    plaza: str
    habilitado: bool
    fecha_cierre: date
    liquidacion: date
    pagos: List[Pago]


@dataclass
class CronogramaCompra:
    pagos: List[Pago]
    completo: bool
    faltante_desde: Optional[date]
    faltante_hasta: Optional[date]
    advertencias: List[str]


def _fecha_cierre(cierre):
    if not isinstance(cierre, dict):
        raise ValueError("Cada cierre de IAMC debe ser un objeto.")
    return _fecha(cierre.get("fecha_cierre"), "Fecha del cierre IAMC")


def _fecha_a3500_iamc(cierre, fecha_cierre):
    """Fecha del A3500 con que IAMC expresa los flujos dólar linked de ese cierre."""
    variables = (cierre.get("macro") or {}).get("vars") if isinstance(cierre.get("macro"), dict) else None
    for variable in variables or ():
        if isinstance(variable, dict) and variable.get("k") == "a3500":
            return _fecha(variable.get("f"), "Fecha del A3500 de IAMC")
    return fecha_cierre


def cronograma_iamc(cierre, ticker, grupo, *, contrato=None, indices=None, avisos=None):
    """Lee pagos por 100 nominales originales del registro exacto de calculadora."""
    fecha_cierre = _fecha_cierre(cierre)
    calculadora = cierre.get("calculadora_bonos")
    if not isinstance(calculadora, dict) or not isinstance(calculadora.get("ins"), list):
        raise ValueError("El cierre IAMC carece de calculadora_bonos.ins.")
    if any(not isinstance(registro, dict) for registro in calculadora["ins"]):
        raise ValueError("El cierre IAMC contiene registros de instrumentos inválidos.")
    registros = [fila for fila in calculadora["ins"] if fila.get("tk") == ticker and fila.get("g") == grupo]
    if not registros:
        return None
    if len(registros) != 1:
        raise ValueError("{} {}: registros duplicados en IAMC al {}.".format(ticker, grupo, fecha_cierre))
    fila = registros[0]
    familia, moneda, plaza = (fila.get(campo) for campo in ("k", "cur", "fxr"))
    liquidacion = _fecha(fila.get("liq"), "Liquidación IAMC")
    habilitado = familia == _FIJA
    pagos = {}
    if contrato is not None and indices is not None and familia in ("cer", "dl", "var", "capv"):
        from .pagos_indexados import proyectar_pagos
        # IAMC expresa los flujos dólar linked al A3500 de su bloque macro, que puede
        # ser anterior a la fecha del cierre (el 12/11/2026 usó el del 11/11).
        fila = dict(fila, _fecha_a3500_iamc=_fecha_a3500_iamc(cierre, fecha_cierre))
        pagos = {fecha: Pago(fecha, amortizacion, renta, origen, dual)
                 for fecha, amortizacion, renta, origen, dual in proyectar_pagos(
                     fila, contrato, fecha_cierre, liquidacion, indices, avisos)}
        habilitado, moneda, plaza = True, "ARS", "ARS"
    elif habilitado:
        if moneda not in ("ARS", "USD") or moneda == "USD" and plaza not in ("MEP", "CCL"):
            raise ValueError("{}: moneda o plaza inválida para un flujo de tasa fija.".format(ticker))
        if not isinstance(fila.get("f"), list):
            raise ValueError("{}: falta el flujo de calculadora IAMC.".format(ticker))
        for registro in fila["f"]:
            if not isinstance(registro, (list, tuple)) or len(registro) != 4:
                raise ValueError("{}: pago inválido en la calculadora IAMC.".format(ticker))
            dias = _decimal(registro[0], "Días del pago IAMC", cero=True)
            if dias != dias.to_integral_value() or dias > (date.max - liquidacion).days:
                raise ValueError("{}: fecha inválida en el flujo IAMC.".format(ticker))
            fecha = liquidacion + timedelta(days=int(dias))
            if fecha in pagos:
                raise ValueError("{}: pago duplicado en IAMC el {}.".format(ticker, fecha))
            pagos[fecha] = Pago(fecha, _decimal(registro[1], "Amortización", cero=True),
                               _decimal(registro[2], "Renta", cero=True), "iamc " + fecha_cierre.isoformat())
    return Cronograma(ticker, grupo, familia, moneda, plaza, habilitado, fecha_cierre, liquidacion,
                      [pagos[fecha] for fecha in sorted(pagos)])


def _serie(cierres, ticker, grupo, *, contrato=None, indices=None, avisos=None):
    serie = []
    for cierre in sorted(cierres, key=_fecha_cierre):
        try:
            cronograma = cronograma_iamc(cierre, ticker, grupo, contrato=contrato, indices=indices, avisos=avisos)
        except (ValueError, DecimalException, KeyError, TypeError) as error:
            if contrato is None or cierre is max(cierres, key=_fecha_cierre):
                raise
            avisos.append("Cierre IAMC del {} sin proyección: {}.".format(_fecha_cierre(cierre), error))
            cronograma = None
        if cronograma is None:
            liquidacion = _fecha(cierre.get("fecha_liquidacion"), "Liquidación del cierre IAMC")
            serie.append((liquidacion, {}, None))
        else:
            serie.append((cronograma.liquidacion, {pago.fecha: pago for pago in cronograma.pagos}, cronograma))
    return serie


def _manuales(registros):
    pagos = {}
    for fila in registros:
        if not isinstance(fila, (list, tuple)) or len(fila) != 3:
            raise ValueError("Cada pago manual requiere fecha, amortización y renta.")
        fecha = _fecha(fila[0], "Fecha del pago manual")
        if fecha in pagos:
            raise ValueError("Pago manual duplicado el {}.".format(fecha))
        pagos[fecha] = Pago(fecha, _decimal(fila[1], "Amortización manual", cero=True),
                           _decimal(fila[2], "Renta manual", cero=True), "manual")
    return pagos


def _fusionar_pagos(serie, manuales):
    if not serie or serie[-1][2] is None or not serie[-1][2].habilitado:
        return {}, None, []
    vigente = serie[-1][2]
    # Moneda y plaza del instrumento actual también gobiernan qué datos son comparables.
    fuentes = [(liq, pagos, c) for liq, pagos, c in serie
               if c is not None and c.habilitado and (c.moneda, c.plaza) == (vigente.moneda, vigente.plaza)]
    primera_liq = min(liq for liq, _, _ in fuentes)
    fechas = {fecha for _, pagos, _ in fuentes for fecha in pagos}
    seleccion, avisos = {}, []
    for fecha in sorted(fechas):
        for liq, pagos, cierre in reversed(serie):
            if liq >= fecha:
                continue
            if (cierre is not None and cierre.habilitado
                    and (cierre.moneda, cierre.plaza) == (vigente.moneda, vigente.plaza)
                    and fecha in pagos):
                seleccion[fecha] = pagos[fecha]
            else:
                avisos.append("Pago del {} ausente del último cierre aplicable: posible reprogramación.".format(fecha))
            break
    if manuales is not None:
        for fecha, manual in manuales.items():
            pago = seleccion.get(fecha)
            if pago is not None:
                if (abs(pago.amortizacion - manual.amortizacion) > _TOLERANCIA
                        or abs(pago.renta - manual.renta) > _TOLERANCIA):
                    avisos.append("{}: pago manual (amortización {}, renta {}) difiere de IAMC "
                                  "(amortización {}, renta {}). Se usa IAMC.".format(
                                      fecha, manual.amortizacion, manual.renta, pago.amortizacion, pago.renta))
            elif fecha <= primera_liq:
                seleccion[fecha] = manual
        amortizado = sum((p.amortizacion for p in seleccion.values()), Decimal(0))
        if abs(amortizado - 100) > _TOLERANCIA:
            avisos.append("El cronograma con pagos manuales suma {} de amortización por 100 VN y no 100: "
                          "falta cargar pagos del prospecto o hay un importe mal cargado.".format(amortizado))
    return seleccion, primera_liq, avisos


def _para_compra(seleccion, primera_liq, avisos, liquidacion, tiene_manuales):
    pagos = [seleccion[fecha] for fecha in sorted(seleccion) if fecha > liquidacion]
    falta = primera_liq is None or liquidacion < primera_liq and not tiene_manuales
    return CronogramaCompra(pagos, not falta, liquidacion if falta else None,
                            primera_liq if falta else None, list(avisos))


def cronograma_compra(cierres, ticker, grupo, liquidacion, pagos_manuales=None):
    """Combina cierres para recuperar los pagos posteriores a la liquidación."""
    liquidacion = _fecha(liquidacion, "Liquidación de la compra")
    manuales = None if pagos_manuales is None else _manuales(pagos_manuales)
    seleccion, primera_liq, avisos = _fusionar_pagos(_serie(cierres, ticker, grupo), manuales)
    return _para_compra(seleccion, primera_liq, avisos, liquidacion, manuales is not None)


def tir_compra(precio, liquidacion, pagos):
    """Resuelve la TIR ACT/365 con el flujo contractual por 100 VN."""
    try:
        precio = _decimal(precio, "Precio de compra")
        liquidacion = _fecha(liquidacion, "Liquidación de la compra")
        with localcontext() as contexto:
            contexto.prec = 50
            flujos = [(pago.total, Decimal((pago.fecha - liquidacion).days) / 365)
                      for pago in pagos if pago.fecha > liquidacion]
            if not flujos or any(total < 0 or not total.is_finite() for total, _ in flujos):
                return None

            def diferencia(tasa):
                return sum((total / (1 + tasa) ** plazo for total, plazo in flujos), Decimal(0)) - precio

            inferior, superior = Decimal("-0.99"), Decimal(10)
            if diferencia(inferior) <= 0 or diferencia(superior) >= 0:
                return None
            for _ in range(180):
                media = (inferior + superior) / 2
                residuo = diferencia(media)
                if abs(residuo) < Decimal("1e-10"):
                    return media
                if residuo > 0:
                    inferior = media
                else:
                    superior = media
    except (ValueError, DecimalException):
        return None
    return None


def _importe(valor):
    return None if valor is None else _texto_decimal(valor)


def _moneda(cronograma):
    if cronograma.moneda == "ARS":
        return "ARS"
    return "USD MEP" if cronograma.plaza == "MEP" else "USD cable"


def _pago(pago, nominales, hoy):
    factor = None if nominales is None else nominales / 100
    lunes = pago.fecha + timedelta(days=7 - pago.fecha.weekday()) if pago.fecha.weekday() >= 5 else None
    fila = {"fecha": pago.fecha.isoformat(), "fecha_cobro": lunes.isoformat() if lunes else None,
            "amortizacion": _importe(pago.amortizacion * factor if factor is not None else None),
            "renta": _importe(pago.renta * factor if factor is not None else None),
            "total": _importe(pago.total * factor if factor is not None else None),
            "origen": pago.origen,
            "estado": "proyectado" if pago.fecha > hoy else "debería haberse cobrado"}
    if pago.dual is not None:
        pata, diferencia = pago.dual
        fila["pata"] = pata
        fila["diferencia_patas"] = _importe(diferencia * factor if factor is not None else None)
        fila["origen"] += " · pata " + pata
        if factor is not None:
            fila["origen"] += " (diferencia ARS " + format(diferencia * factor, ".2f") + ")"
    return fila


def _compra(referencia, registro, vigente, seleccion, primera_liq, manuales, hoy, contrato=None, indices=None):
    from .letras import precio_en_moneda_flujo

    nominales = Decimal(str(referencia["cantidad_restante"]))
    fila = {"referencia": referencia["referencia"], "fecha_compra": referencia["fecha_compra"],
            "liquidacion": None, "nominales": _importe(nominales), "precio": None,
            "moneda_precio": None, "tc": None, "precio_flujo": None, "inversion": None,
            "total_a_cobrar": None, "resultado_vto": None, "tir": None, "motivo": None,
            "pagos": []}
    if registro is None:
        fila["motivo"] = "falta precio de compra"
        fila["pagos"] = [_pago(seleccion[f], nominales, hoy) for f in sorted(seleccion) if f > hoy]
        return fila
    liquidacion = _fecha(registro["fecha_liquidacion"], "Liquidación")
    fila.update(liquidacion=liquidacion.isoformat(), precio=registro["precio"],
                moneda_precio=registro["moneda"], tc=registro.get("tc"))
    if not vigente.pagos or liquidacion >= vigente.pagos[-1].fecha:
        fila["motivo"] = "sin dato: la liquidación debe ser anterior al último pago"
        return fila
    # Un título ajustable de pago único sin renta (LECER, BONCER cero cupón, LELINK,
    # capitalizable) no tiene pagos antes del vencimiento: no hay hueco que completar.
    cero_cupon = (vigente.familia in ("cer", "dl", "capv") and len(seleccion) == 1
                  and all(pago.renta == 0 for pago in seleccion.values()))
    cronograma = _para_compra(seleccion, primera_liq, [], liquidacion, manuales is not None or cero_cupon)
    fila["pagos"] = [_pago(pago, nominales, hoy) for pago in cronograma.pagos]
    try:
        precio = precio_en_moneda_flujo(registro, vigente.moneda)
    except ErrorLetra as error:
        fila["motivo"] = "sin dato: " + str(error)
        return fila
    inversion = precio * nominales / 100
    fila.update(precio_flujo=_importe(precio), inversion=_importe(inversion))
    if not cronograma.completo:
        fila["motivo"] = "sin dato: faltan pagos entre {} y {}".format(cronograma.faltante_desde, cronograma.faltante_hasta)
        return fila
    if not cronograma.pagos:
        fila["motivo"] = "sin dato: falta el cronograma de pagos posterior a la liquidación"
        return fila
    total = sum((pago.total for pago in cronograma.pagos), Decimal(0)) * nominales / 100
    tir = tir_compra(precio, liquidacion, cronograma.pagos)
    fila.update(total_a_cobrar=_importe(total), resultado_vto=_importe(total - inversion), tir=_importe(tir))
    # La TIR es estimada si algún pago usa el REM o un supuesto manual; con todos los
    # índices publicados es definitiva aunque el título sea ajustable.
    if vigente.familia != _FIJA and any(not str(p.origen).startswith("definitivo") for p in cronograma.pagos):
        fila["tir_estimada"] = True
    if vigente.familia == "cer" and contrato and indices:
        from .pagos_indexados import _cer, _referencia
        try:
            inicial = _decimal(contrato["valor_inicial"], "CER inicial")
            # El precio real se deflacta con el CER de la referencia contractual de la
            # liquidación, igual que los pagos.
            ref_liq = _referencia(liquidacion, contrato.get("rezago_habiles"), indices["feriados"], [])
            precio_real = precio * inicial / _cer(indices, ref_liq).valor
            pagos_reales = []
            for pago in cronograma.pagos:
                ref = _referencia(pago.fecha, contrato.get("rezago_habiles"), indices["feriados"], [])
                factor = inicial / _cer(indices, ref).valor
                pagos_reales.append(Pago(pago.fecha, pago.amortizacion * factor, pago.renta * factor, pago.origen))
            fila["tir_real"] = _importe(tir_compra(precio_real, liquidacion, pagos_reales))
        except (ValueError, DecimalException, KeyError) as error:
            fila["motivo_tir_real"] = str(error)
    if tir is None:
        fila["motivo"] = "TIR sin dato: fuera del intervalo de cálculo"
    return fila


def _cantidad_en_fecha(fecha, dia_cero, base, movimientos):
    """Nominales con derecho al pago: los que había al cierre del día anterior.

    Una compra o una venta hecha el mismo día del pago no lo cambia: el título
    ya negocia sin ese cupón. Antes del día cero la tenencia no se conoce.
    """
    if dia_cero is None or fecha < dia_cero:
        return None
    cantidad = base
    for movimiento in movimientos:
        if movimiento["fecha"] >= fecha:
            break
        if movimiento["tipo"] in ("compra", "venta"):
            signo = 1 if movimiento["tipo"] == "compra" else -1
            cantidad += signo * Decimal(str(movimiento["cantidad"]))
    return cantidad


def _asignar_cobros(fechas, registros, hoy):
    """Asocia cada registro a un solo vencimiento aunque coincidan ventanas."""
    por_fecha = defaultdict(list)
    for registro in registros:
        fecha = registro["fecha"]
        if fecha > hoy:
            continue
        indice = bisect_right(fechas, fecha) - 1
        if indice >= 0 and (fecha - fechas[indice]).days <= 10:
            por_fecha[fechas[indice]].append(registro)
    return por_fecha


def _control_cobro(registros, teorico, cronograma, origen):
    if not registros:
        return {"estado": "cobro no registrado", "teorico": teorico, "registrado": None,
                "diferencia": None, "convertido": False, "origen": None}
    total, convertido, problema = Decimal(0), False, None
    for registro in registros:
        importe = Decimal(str(registro["importe"]))
        moneda = registro["moneda"]
        if moneda == cronograma.moneda:
            cuenta = registro.get("cuenta")
            if moneda == "USD" and cuenta is not None:
                plaza = "CABLE" if cronograma.plaza == "CCL" else "DOLARES"
                if cuenta != plaza:
                    problema = "plaza distinta de la del cronograma"
                    break
        elif moneda == "ARS" and cronograma.moneda == "USD":
            if registro.get("tc") is None:
                problema = "falta tc del cobro en ARS"
                break
            importe /= Decimal(str(registro["tc"]))
            convertido = True
        else:
            problema = "moneda distinta de la del cronograma"
            break
        total += importe
    if problema:
        return {"estado": "cobro sin dato: " + problema, "teorico": teorico, "registrado": None,
                "diferencia": None, "convertido": convertido, "origen": origen}
    return {"estado": "cobro registrado" if teorico is not None else "cobro registrado; nominales históricos sin dato",
            "teorico": teorico, "registrado": _importe(total),
            "diferencia": _importe(total - Decimal(teorico)) if teorico is not None else None,
            "convertido": convertido, "origen": origen}


def _pagos_posicion(seleccion, vigente, nominales, base, movimientos, extractos, hoy, dia_cero):
    fechas = sorted(seleccion)
    fechas_control = [fecha for fecha in fechas if dia_cero is not None and fecha >= dia_cero]
    cobros = _asignar_cobros(fechas_control,
                            (m for m in movimientos if m["tipo"] in ("renta", "amortizacion")), hoy)
    historicos = _asignar_cobros(fechas, extractos, hoy)
    filas = []
    for fecha in fechas:
        cantidad = nominales if fecha > hoy else _cantidad_en_fecha(fecha, dia_cero, base, movimientos)
        if cantidad == 0:
            continue
        registros = cobros.get(fecha)
        respaldo = registros or historicos.get(fecha)
        if cantidad is None and not respaldo:
            # Anterior al día cero y sin registro: no se sabe si el cliente tenía
            # el título. No es un "cobro no registrado".
            continue
        fila = _pago(seleccion[fecha], cantidad, hoy)
        fila["cobro"] = None
        if fecha <= hoy:
            origen = "movimientos" if registros else "extracto"
            fila["cobro"] = _control_cobro(respaldo, fila["total"], vigente, origen)
        filas.append(fila)
    return filas


def _sumar_calendario(calendario, moneda, pago):
    mes = pago["fecha"][:7]
    estado = "proyectado" if pago["estado"] == "proyectado" else "deberia_haberse_cobrado"
    acumulado = calendario.setdefault(mes, {"proyectado": {}, "deberia_haberse_cobrado": {}})[estado]
    anterior, total = acumulado.get(moneda, Decimal(0)), pago["total"]
    acumulado[moneda] = None if anterior is None or total is None else anterior + Decimal(total)


def _precios_compras(compras, referencias, hoy, avisos):
    registros = {}
    if compras is None:
        return registros
    try:
        contenido = validar_compras(compras, bonos=True)
    except ErrorLetra as error:
        avisos.append("compras_bonos.json: " + str(error))
        return registros
    for fila in contenido["compras"]:
        try:
            registro = validar_dato_compra(fila, referencias, hoy, bonos=True)
            registros[registro["referencia"]] = registro
        except ErrorLetra as error:
            avisos.append("compras_bonos.json: " + str(error))
    return registros


def _configuracion_manual(vinculo, ticker, avisos):
    bloque = vinculo.get("pagos_manuales")
    if bloque is None:
        return None
    try:
        if (not isinstance(bloque, dict) or not isinstance(bloque.get("fuente"), str)
                or not bloque["fuente"].strip() or not isinstance(bloque.get("pagos"), list)):
            raise ValueError("pagos_manuales requiere fuente y una lista de pagos.")
        return _manuales(bloque["pagos"])
    except ValueError as error:
        avisos.append("{}: {}. Revisá el cronograma manual.".format(ticker, error))
        return None


def _fila_posicion(ticker, nominales):
    return {"ticker": ticker, "cantidad": _importe(nominales), "moneda": None, "plaza": None,
            "moneda_etiqueta": None, "motivo": None, "proximo_pago": None, "total_proyectado": None,
            "pagos_restantes": None, "compras": [], "pagos": []}


def _posicion(ticker, nominales, instrumentos, cierres, fecha_cierre, lotes, precios, base,
              movimientos, extractos, hoy, dia_cero, avisos, indices):
    fila = _fila_posicion(ticker, nominales)
    configuracion = instrumentos.get(ticker, {})
    vinculo = configuracion.get("iamc") if isinstance(configuracion, dict) else None
    if (not isinstance(vinculo, dict) or not isinstance(vinculo.get("ticker"), str)
            or not vinculo["ticker"].strip() or vinculo.get("grupo") not in ("tp", "on")):
        fila["motivo"] = "sin vincular con IAMC"
        if vinculo is not None:
            avisos.append("{}: vínculo IAMC inválido.".format(ticker))
        return fila
    if fecha_cierre is None:
        fila["motivo"] = "sin cronograma: falta un cierre de IAMC guardado"
        return fila
    contrato = vinculo.get("indice")
    if contrato is not None and not isinstance(contrato, dict):
        fila["motivo"] = "proyección pendiente: bloque contractual de índice inválido"
        return fila
    manuales = _configuracion_manual(vinculo, ticker, avisos)
    if contrato is not None and manuales:
        # Un cupón TAMAR en curso devenga desde el último pago del prospecto.
        contrato = dict(contrato, _pagos_previos=tuple(sorted(manuales)))
    try:
        serie = _serie(cierres, vinculo["ticker"], vinculo["grupo"], contrato=contrato,
                       indices=indices, avisos=avisos)
        vigente = serie[-1][2]
        if vigente is None or vigente.habilitado and not vigente.pagos:
            fila["motivo"] = "sin cronograma en IAMC al {}".format(fecha_cierre)
            return fila
        if not vigente.habilitado:
            fila["motivo"] = _PENDIENTE
            return fila
        seleccion, primera_liq, advertencias = _fusionar_pagos(serie, manuales)
    except (ValueError, DecimalException, KeyError, TypeError) as error:
        fila["motivo"] = ("proyección pendiente: " + str(error) if contrato is not None else
                          "sin cronograma válido en IAMC al {}".format(fecha_cierre))
        avisos.append("{}: {}".format(ticker, error))
        return fila
    avisos.extend("{}: {}".format(ticker, aviso) for aviso in advertencias)
    vencimiento = configuracion.get("vencimiento")
    if vencimiento and _fecha(vencimiento, "Vencimiento") != vigente.pagos[-1].fecha:
        avisos.append("{}: vencimiento {} distinto del último pago IAMC {}.".format(
            ticker, vencimiento, vigente.pagos[-1].fecha))
    saldo_lotes = sum((Decimal(str(ref["cantidad_restante"])) for ref in lotes), Decimal(0))
    if saldo_lotes != nominales:
        avisos.append("{}: los lotes remanentes suman {} VN y la posición {} VN.".format(ticker, saldo_lotes, nominales))
    pagos = _pagos_posicion(seleccion, vigente, nominales, base, movimientos, extractos, hoy, dia_cero)
    futuros = [pago for pago in pagos if pago["estado"] == "proyectado"]
    fila.update(moneda=vigente.moneda, plaza=vigente.plaza, moneda_etiqueta=_moneda(vigente),
                pagos=pagos, proximo_pago=futuros[0] if futuros else None, pagos_restantes=len(futuros),
                total_proyectado=_importe(sum((Decimal(p["total"]) for p in futuros), Decimal(0))),
                compras=[_compra(ref, precios.get(ref["referencia"]), vigente, seleccion, primera_liq, manuales, hoy,
                                  contrato, indices)
                         for ref in lotes])
    return fila


def calcular_flujo(base, movimientos, instrumentos, cierres, compras=None, letras=None, hoy=None,
                   fecha_dia_cero=None, *, actual=None, cobros_historial=(), indices=None):
    """Construye el panel de pagos a partir de nominales y cronogramas guardados."""
    hoy = _hoy_argentina() if hoy is None else _fecha(hoy, "Fecha de hoy")
    dia_cero = None if fecha_dia_cero is None else _fecha(fecha_dia_cero, "Día cero")
    movimientos = list(movimientos)
    actual = cartera_actual(base, movimientos)[0] if actual is None else actual
    cierres = [cierre for cierre in cierres if _fecha_cierre(cierre) <= hoy]
    fecha_cierre = max((_fecha_cierre(cierre) for cierre in cierres), default=None)
    antiguedad = (hoy - fecha_cierre).days if fecha_cierre else None
    avisos = []
    if antiguedad is not None and antiguedad > 7:
        avisos.append("El cierre de IAMC al {} tiene {} días corridos.".format(fecha_cierre, antiguedad))
    normalizados, errores = _normalizados(movimientos)
    if errores:
        raise ErrorMovimiento(errores)
    tipos = ("bono", "on")
    # Las letras CER o dólar linked con contrato de índice siguen el flujo de IAMC.
    indexadas = letras_indexadas(instrumentos)

    def en_flujo(tipo, ticker):
        return tipo in tipos or tipo == "letra" and ticker in indexadas

    saldos = {p.ticker: Decimal(str(p.cantidad)) for p in actual.posiciones if en_flujo(p.tipo, p.ticker)}
    # Una especie cerrada puede tener derecho a pagos anteriores a su venta.
    for posicion in base.posiciones:
        if en_flujo(posicion.tipo, posicion.ticker):
            saldos.setdefault(posicion.ticker, Decimal(0))
    movimientos_por_ticker, lotes, extractos = defaultdict(list), defaultdict(list), defaultdict(list)
    for _, movimiento in sorted(normalizados, key=lambda fila: fila[1]["fecha"]):
        ticker = movimiento["ticker"]
        movimientos_por_ticker[ticker].append(movimiento)
        if movimiento["tipo"] == "compra" and (movimiento["tipo_activo"] in tipos or ticker in indexadas):
            saldos.setdefault(ticker, Decimal(0))
    for fila in cobros_historial:
        extractos[fila["ticker"]].append(fila)
    referencias = referencias_flujo(base, movimientos, instrumentos)
    for ref in referencias:
        if ref["cantidad_restante"] > 0:
            lotes[ref["ticker"]].append(ref)
    precios = _precios_compras(compras, referencias, hoy, avisos)
    inicial = {posicion.ticker: Decimal(str(posicion.cantidad)) for posicion in base.posiciones}
    posiciones, calendario = [], {}
    with localcontext() as contexto:
        contexto.prec = 50
        for ticker, nominales in saldos.items():
            avisos_posicion = []
            fila = _posicion(ticker, nominales, instrumentos, cierres, fecha_cierre, lotes[ticker],
                             precios, inicial.get(ticker, Decimal(0)), movimientos_por_ticker[ticker],
                             extractos[ticker], hoy, dia_cero, avisos_posicion, indices)
            if not nominales and not fila["pagos"]:
                continue
            avisos.extend(avisos_posicion)
            posiciones.append(fila)
            for pago in fila["pagos"]:
                # Un pago anterior al día cero figura en el control, sin importe
                # teórico: no entra al calendario.
                if pago["total"] is not None:
                    _sumar_calendario(calendario, fila["moneda_etiqueta"], pago)
        for letra in (letras or {}).get("posiciones", []):
            ticker = letra["ticker"]
            if ticker in indexadas:
                continue
            habilitada = letra["familia"] in ("LECAP", "BONCAP")
            total = letra["pago_vencimiento"]
            if not habilitada or total is None:
                fila = _fila_posicion(ticker, Decimal(str(letra["cantidad"])))
                fila["motivo"] = (_PENDIENTE if not habilitada and letra["familia"] else
                                  "sin cronograma de letra habilitada")
                posiciones.append(fila)
                continue
            fecha = _fecha(letra["vencimiento"], "Vencimiento de letra")
            if fecha <= hoy:
                cantidad = _cantidad_en_fecha(fecha, dia_cero, inicial.get(ticker, Decimal(0)),
                                             movimientos_por_ticker[ticker])
                if cantidad is None or cantidad == 0:
                    continue
                total = _importe(cantidad / Decimal(letra["base_nominal"]) * Decimal(letra["valor_por_base"]))
            estado = "proyectado" if fecha > hoy else "debería haberse cobrado"
            _sumar_calendario(calendario, "ARS", {"fecha": fecha.isoformat(), "estado": estado, "total": total})
    # Una moneda ausente no tiene pagos ese mes; presente con None, importe sin dato.
    meses = [dict(mes=mes, **{estado: {moneda: _importe(importes[moneda]) for moneda in _MONEDAS if moneda in importes}
                            for estado, importes in calendario[mes].items()}) for mes in sorted(calendario)]
    return {"fecha_calculo": hoy.isoformat(), "fecha_cierre": fecha_cierre.isoformat() if fecha_cierre else None,
            "antiguedad": antiguedad, "control_desde": dia_cero.isoformat() if dia_cero else None,
            "avisos": list(dict.fromkeys(avisos)),
            "calendario": meses, "posiciones": posiciones}
