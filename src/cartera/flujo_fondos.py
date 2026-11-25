"""Cronogramas y rendimiento de compra de renta fija a partir de cierres IAMC."""

from bisect import bisect_right
from collections import defaultdict
from datetime import date, timedelta
from decimal import Decimal, DecimalException, localcontext

from .letras import (
    ErrorLetra, _decimal, _fecha, _hoy_argentina, _texto_decimal, letras_indexadas, referencias_flujo,
    validar_compras, validar_dato_compra,
)
from financial_engine.cash_flows import (
    CashFlowSchedule as Cronograma,
    PurchaseSchedule as CronogramaCompra,
    Payment as Pago,
    _fecha_a3500_iamc,
    _fecha_cierre,
    _fusionar_pagos,
    _manuales,
    _para_compra,
    _serie,
    purchase_schedule as cronograma_compra,
    iamc_schedule as cronograma_iamc,
    purchase_yield as tir_compra,
)

from .movimientos import ErrorMovimiento, _normalizados, cartera_actual


_MONEDAS = ("ARS", "USD MEP", "USD cable")
_FIJA = "fix"
_PENDIENTE = "proyección pendiente: requiere supuestos"


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


def _intereses_corridos(seleccion, pagos, liquidacion):
    """Renta devengada a la liquidación, por 100 VN, y si la fecha de inicio del cupón es estimada.

    El precio sucio la incluye y el primer cupón la devuelve: es capital, no ganancia. Se reparte
    lineal en días corridos entre el pago anterior y el siguiente. Si el pago anterior no está en el
    cronograma, se supone que el período mide lo mismo que el siguiente.
    """
    primero = pagos[0]
    if primero.renta == 0:
        return Decimal(0), False
    anteriores = [fecha for fecha in seleccion if fecha <= liquidacion]
    estimado = not anteriores
    if anteriores:
        inicio = max(anteriores)
    elif len(pagos) > 1:
        inicio = primero.fecha - (pagos[1].fecha - primero.fecha)
    else:
        return None, True
    periodo = (primero.fecha - inicio).days
    if periodo <= 0:
        return None, True
    transcurrido = min(max((liquidacion - inicio).days, 0), periodo)
    return primero.renta * transcurrido / periodo, estimado


def _separar_capital(fila, seleccion, pagos, liquidacion, inversion, nominales):
    """Divide lo que se cobra en capital invertido que vuelve y ganancia (docs/FLUJO_FONDOS.md).

    capital: la inversión (precio sucio). Los intereses corridos pagados al comprar vuelven con el
    primer cupón; el resto se recupera con cada amortización, en proporción a los nominales que
    amortiza. ganancia_precio = amortizaciones − capital limpio (comprar bajo la par, ajuste por
    índice); intereses = rentas − intereses corridos.
    """
    factor = nominales / 100
    corrido, estimado = _intereses_corridos(seleccion, pagos, liquidacion)
    amortizacion = sum((pago.amortizacion for pago in pagos), Decimal(0)) * factor
    renta = sum((pago.renta for pago in pagos), Decimal(0)) * factor
    if corrido is None or amortizacion <= 0:
        fila["motivo_capital"] = ("sin dato: no se pudo estimar el inicio del cupón" if corrido is None
                                  else "sin dato: el título no amortiza capital")
        return
    corrido *= factor
    limpio = inversion - corrido
    fila.update(intereses_corridos=_importe(corrido), ganancia_precio=_importe(amortizacion - limpio),
                intereses=_importe(renta - corrido))
    if estimado and corrido:
        fila["intereses_corridos_estimados"] = True
    for indice, (pago, salida) in enumerate(zip(pagos, fila["pagos"])):
        capital = limpio * pago.amortizacion * factor / amortizacion + (corrido if indice == 0 else 0)
        salida["capital"] = _importe(capital)
        salida["ganancia"] = _importe(pago.total * factor - capital)


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
    _separar_capital(fila, seleccion, cronograma.pagos, liquidacion, inversion, nominales)
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
    fila.update(_capital_pendiente(fila["compras"], futuros, saldo_lotes == nominales))
    return fila


def _capital_pendiente(compras, futuros, lotes_completos):
    """Cuánto de lo que falta cobrar devuelve capital invertido y cuánto es ganancia.

    Solo con todas las compras separadas: si a una le falta el precio, los dos quedan sin dato.
    """
    vacio = {"capital_pendiente": None, "ganancia_pendiente": None}
    if not futuros or not compras or not lotes_completos:
        return vacio
    capital = Decimal(0)
    for compra in compras:
        proyectados = [pago for pago in compra["pagos"] if pago["estado"] == "proyectado"]
        if any(pago.get("capital") is None for pago in proyectados):
            return vacio
        capital += sum((Decimal(pago["capital"]) for pago in proyectados), Decimal(0))
    total = sum((Decimal(pago["total"]) for pago in futuros), Decimal(0))
    return {"capital_pendiente": _importe(capital), "ganancia_pendiente": _importe(total - capital)}


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
