"""Resultado histórico realizado: lotes y cobros, separado del día cero."""

import copy
import math
from collections import defaultdict, deque
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from numbers import Real
from typing import Dict, List, Optional

from ._historial_lectura import ErrorHistorial, _normalizar_ajuste, clasificar, consolidar
from .punto_partida import Lote


_CLASES_INGRESOS = ("dividendo", "retencion", "renta", "caucion_colocada", "caucion_tomada", "fci", "gastos", "compensacion")
_PATAS = {
    "caucion_colocada": {"COMPRA CAUCION CONTADO", "VENTA CAUCION TERMINO"},
    "caucion_tomada": {"VENTA CAUCION CONTADO", "COMPRA CAUCION TERMINO"},
}
# Un cobro corresponde al pago del cronograma de hasta 10 días corridos antes, como en el control de cobros.
_VENTANA_COBRO = 10
_TOLERANCIA_CRONOGRAMA = Decimal("0.01")


def _bolsa():
    return {"ARS": 0.0, "USD": 0.0, "equivalente_ars": 0.0}


@dataclass
class RealizadoHistorico:
    ticker: str
    fecha: date
    cantidad: float
    cantidad_sin_lote: float
    importe_ars: Optional[float]
    costo_ars: Optional[float]
    resultado_ars: Optional[float]
    origen_costo: str
    clase: str


@dataclass
class Historial:
    realizados: List[RealizadoHistorico] = field(default_factory=list)
    ingresos: Dict[str, dict] = field(default_factory=lambda: {clase: _bolsa() for clase in _CLASES_INGRESOS})
    aportes: dict = field(default_factory=_bolsa)
    retiros: dict = field(default_factory=_bolsa)
    lotes: List[Lote] = field(default_factory=list)
    total_conocido: float = 0.0
    realizado_extracto: float = 0.0
    realizado_estimado: float = 0.0
    ventas_sin_dato: int = 0
    valores_sin_dato: int = 0
    sin_clasificar: List[dict] = field(default_factory=list)
    avisos: List[str] = field(default_factory=list)
    diferencias_tenencias: dict = field(default_factory=dict)
    diferencias_costos: dict = field(default_factory=dict)
    cobros: List[dict] = field(default_factory=list)
    capital_devuelto: dict = field(default_factory=_bolsa)
    amortizaciones: List[dict] = field(default_factory=list)


def _numero(valor, nombre, positivo=False):
    if isinstance(valor, bool) or not isinstance(valor, (Real, Decimal)):
        raise ErrorHistorial(nombre + " debe ser un número finito.")
    try:
        numero = float(valor)
    except (ValueError, OverflowError):
        raise ErrorHistorial(nombre + " excede el rango numérico.") from None
    if not math.isfinite(numero) or positivo and numero <= 0:
        raise ErrorHistorial(nombre + " debe ser un número finito" + (" positivo." if positivo else "."))
    return numero


def _decimal(valor):
    return Decimal(str(valor))


def _suma(valores):
    return _numero(sum((_decimal(v) for v in valores), Decimal(0)), "El acumulado histórico")


def _fecha(valor):
    if isinstance(valor, datetime):
        return valor.date()
    if isinstance(valor, date):
        return valor
    if isinstance(valor, str):
        try:
            return date.fromisoformat(valor)
        except ValueError:
            pass
    raise ErrorHistorial("La fecha operada debe tener formato AAAA-MM-DD.")


def _contexto(fila):
    return "{} fila {} (comprobante {}): ".format(
        fila.get("archivo", "historial"), fila.get("fila", "sin número"), fila.get("numero", "sin número"))


def _fila_normalizada(fila):
    if not isinstance(fila, dict):
        raise ErrorHistorial("Cada renglón de historial debe ser un diccionario.")
    nueva = copy.deepcopy(fila)
    contexto = _contexto(nueva)
    try:
        nueva["operado"] = _fecha(nueva.get("operado"))
        for campo in ("importe", "cantidad"):
            nueva[campo] = _numero(nueva.get(campo, 0), campo)
        if nueva.get("saldo") is not None:
            nueva["saldo"] = _numero(nueva["saldo"], "saldo")
        for campo in ("comprobante", "especie", "referencia"):
            valor = nueva.get(campo, "")
            if valor is None:
                valor = ""
            if not isinstance(valor, str):
                raise ErrorHistorial(campo + " debe ser texto.")
            nueva[campo] = valor.strip()
        if nueva.get("moneda") not in ("ARS", "USD"):
            raise ErrorHistorial("La moneda debe ser ARS o USD.")
        if nueva.get("cuenta") not in ("PESOS", "DOLARES", "CABLE"):
            raise ErrorHistorial("La cuenta debe ser PESOS, DOLARES o CABLE.")
    except ErrorHistorial as error:
        raise ErrorHistorial(contexto + str(error)) from None
    return nueva


def _orden_numero(valor):
    # Los números de comprobante suelen ser enteros; los alfanuméricos conservan
    # un orden determinista sin tratarlos como una clasificación financiera.
    if valor is None:
        return (2, "")
    if isinstance(valor, bool):
        return (1, str(valor))
    try:
        numero = Decimal(str(valor))
        if numero.is_finite():
            return (0, numero)
    except Exception:
        pass
    return (1, str(valor))


def _filas_ajustes(ajustes):
    filas = []
    for indice, ajuste in enumerate(ajustes, 1):
        normalizado = _normalizar_ajuste(ajuste)
        fila = copy.deepcopy(normalizado)
        tipo = normalizado["tipo"]
        signo = -1 if tipo in ("compra", "gasto") else 1
        fila.update(operado=normalizado["fecha"], comprobante="AJUSTE " + tipo.upper(),
                    numero=None, cantidad=normalizado["cantidad"], especie=normalizado["ticker"],
                    importe=signo * normalizado["importe"], saldo=None,
                    referencia=normalizado["nota"], cuenta="PESOS" if normalizado["moneda"] == "ARS" else "DOLARES",
                    archivo=normalizado.get("archivo", "ajustes_historial.csv"),
                    fila=normalizado.get("fila", indice + 1),
                    _clase="gastos" if tipo == "gasto" else tipo, _origen="estimado")
        filas.append(fila)
    return filas


def _cronogramas(cronogramas):
    """Pagos por 100 VN originales de cada especie, en orden de fecha; None si no se pasaron."""
    if cronogramas is None:
        return None
    if not isinstance(cronogramas, dict):
        raise ErrorHistorial("Los cronogramas deben ser un diccionario de especie a pagos.")
    # El mismo formato y las mismas validaciones que iamc.pagos_manuales del flujo de fondos.
    from .flujo_fondos import _manuales
    pagos = {}
    for ticker, registros in cronogramas.items():
        if not isinstance(ticker, str) or not ticker.strip():
            raise ErrorHistorial("Cada cronograma debe identificar una especie con texto no vacío.")
        if not isinstance(registros, (list, tuple)):
            raise ErrorHistorial("{}: el cronograma debe ser una lista de pagos.".format(ticker))
        try:
            manuales = _manuales(registros)
        except ValueError as error:
            raise ErrorHistorial("{}: cronograma inválido: {}".format(ticker, error)) from None
        pagos[ticker.strip()] = [manuales[fecha] for fecha in sorted(manuales)]
    return pagos


def construir_historial(filas, ajustes=(), cierres=(), mep=None, cronogramas=None):
    """Calcula lotes abiertos y resultado observado sin tocar la base ni el día cero.

    Con ``cronogramas`` ({especie: [[fecha, amortizacion, renta], ...]} por 100 VN originales), un cobro
    ``RENTA Y AMORTIZ`` que amortiza se separa: el capital baja el costo de los lotes y no es renta.
    """
    cierres = set(cierres)
    if any(not isinstance(ticker, str) or not ticker for ticker in cierres):
        raise ErrorHistorial("Los cierres deben identificar especies con texto no vacío.")
    mapa_mep = {}
    for fecha, cambio in (mep or {}).items():
        mapa_mep[_fecha(fecha)] = _numero(cambio, "MEP", positivo=True)
    fechas_mep = sorted(mapa_mep)
    pagos_cronograma = _cronogramas(cronogramas)
    origenes, avisos = consolidar([_fila_normalizada(fila) for fila in filas])
    historial = Historial(avisos=list(avisos))
    procesables = []
    cierres_agrupados, amortizaciones = {}, defaultdict(list)
    cauciones, cauciones_iol = defaultdict(list), defaultdict(list)
    rentas_con_amortizacion = defaultdict(list)
    entradas = [(fila, False) for fila in origenes] + [(fila, True) for fila in _filas_ajustes(ajustes)]
    for indice, (original, es_ajuste) in enumerate(entradas):
        # Los metadatos que agregue un llamador a un renglón de extracto nunca
        # pueden reemplazar su clasificación ni la procedencia observada.
        clase = original["_clase"] if es_ajuste else clasificar(original, cierres)
        if clase == "sin_clasificar":
            historial.sin_clasificar.append(copy.deepcopy(original))
            continue
        fila = dict(original)
        fila["_clase"] = clase
        fila["_indice"] = indice
        fila["_origen"] = "estimado" if es_ajuste else "extracto"
        if (not es_ajuste and clase in ("renta", "cierre", "amortizacion")
                and fila["especie"] and (clase != "amortizacion" or fila["importe"] != 0)):
            historial.cobros.append(dict(ticker=fila["especie"], fecha=fila["operado"],
                                         moneda=fila["moneda"], cuenta=fila["cuenta"], importe=fila["importe"]))
        if clase == "conversion":
            continue
        if clase in ("compra", "venta", "cierre", "amortizacion"):
            if not fila["especie"]:
                raise ErrorHistorial(_contexto(fila) + "Una compra, venta, cierre o amortización necesita especie.")
            if clase in ("compra", "venta") and fila["cantidad"] == 0:
                raise ErrorHistorial(_contexto(fila) + "Una compra o venta necesita cantidad distinta de cero.")
        if clase == "caucion_iol":
            cauciones_iol[(fila["moneda"], fila.get("numero"))].append(fila)
        elif clase.startswith("caucion_"):
            cauciones[(fila["moneda"], clase, fila["operado"])].append(fila)
        elif clase == "cierre":
            clave = (fila["especie"], fila["operado"])
            cierres_agrupados.setdefault(clave, []).append(fila)
        elif clase == "amortizacion":
            clave = (fila["especie"], fila["operado"])
            amortizaciones.setdefault(clave, []).append(fila)
        elif (clase == "renta" and not es_ajuste and pagos_cronograma is not None
              and fila["comprobante"] == "RENTA Y AMORTIZ" and fila["especie"]):
            # Bull informa renta y amortización juntas: se separan con el cronograma más abajo.
            rentas_con_amortizacion[fila["especie"]].append(fila)
        else:
            procesables.append(fila)

    def orden_comprobante(fila):
        return (fila["operado"], _orden_numero(fila.get("numero")), fila["_indice"])

    # Un cierre reúne todos los pagos de la especie en el día, incluso cuentas
    # o monedas distintas; su lugar en el orden es el primer comprobante.
    for grupo in cierres_agrupados.values():
        primera = min(grupo, key=lambda fila: (_orden_numero(fila.get("numero")), fila["_indice"]))
        evento = dict(primera)
        evento["_pagos"] = grupo
        procesables.append(evento)
    # IOL informa por separado el pago y la baja de nominales. Una baja cierra
    # solo esa cantidad; sin baja, el pago es una devolución parcial de capital.
    for grupo in amortizaciones.values():
        bajas = [-fila["cantidad"] for fila in grupo if fila["cantidad"] < 0]
        if bajas:
            primera = min(grupo, key=lambda fila: (_orden_numero(fila.get("numero")), fila["_indice"]))
            evento = dict(primera)
            evento["_clase"] = "cierre"
            evento["_pagos"] = grupo
            evento["_cantidad_cierre"] = _suma(bajas)
            procesables.append(evento)
        else:
            for fila in grupo:
                evento = dict(fila)
                if fila["importe"] > 0:
                    # Todo capital: IOL ya lo separa de la renta, no hace falta cronograma.
                    evento.update(_clase="capital_devuelto", _fecha_pago=fila["operado"], _pago=None,
                                  _cobros=[fila], _final=False)
                    procesables.append(evento)
                elif fila["importe"] < 0:
                    evento["_clase"] = "gastos"
                    procesables.append(evento)
    # RENTA Y AMORTIZ de Bull: cada cobro va al pago del cronograma de hasta 10 días antes. Si ese pago
    # amortiza, el capital es devolución de lo invertido; si con él la amortización llega a 100, cierra.
    sin_cronograma = defaultdict(set)
    for ticker, cobros_especie in rentas_con_amortizacion.items():
        pagos = pagos_cronograma.get(ticker) or []
        if not pagos:
            sin_cronograma[ticker].update(fila["operado"] for fila in cobros_especie)
            procesables.extend(cobros_especie)
            continue
        por_pago = {}
        for fila in sorted(cobros_especie, key=orden_comprobante):
            candidatos = [pago for pago in pagos
                          if pago.fecha <= fila["operado"] and (fila["operado"] - pago.fecha).days <= _VENTANA_COBRO]
            if not candidatos:
                historial.avisos.append(_contexto(fila) + "{}: el cobro del {} no tiene un pago del cronograma en los {} "
                                        "días anteriores; se cuenta entero como renta.".format(
                                            ticker, fila["operado"].isoformat(), _VENTANA_COBRO))
                procesables.append(fila)
                continue
            pago = candidatos[-1]
            por_pago.setdefault(pago.fecha, (pago, []))[1].append(fila)
        for fecha_pago in sorted(por_pago):
            pago, grupo = por_pago[fecha_pago]
            if pago.amortizacion == 0:
                procesables.extend(grupo)
                continue
            if len({fila["moneda"] for fila in grupo}) > 1:
                historial.avisos.append("{}: los cobros del pago del {} están en monedas distintas; no se separa el "
                                        "capital y se cuentan como renta.".format(ticker, fecha_pago.isoformat()))
                procesables.extend(grupo)
                continue
            if _decimal(_suma(fila["importe"] for fila in grupo)) <= 0:
                historial.avisos.append("{}: los cobros del pago del {} no suman un importe positivo; no se separa el "
                                        "capital y se cuentan como renta.".format(ticker, fecha_pago.isoformat()))
                procesables.extend(grupo)
                continue
            amortizado = sum((otro.amortizacion for otro in pagos if otro.fecha <= fecha_pago), Decimal(0))
            evento = dict(grupo[0])
            evento.update(_clase="capital_devuelto", _fecha_pago=fecha_pago, _pago=pago, _cobros=grupo,
                          _final=amortizado >= 100 - _TOLERANCIA_CRONOGRAMA)
            procesables.append(evento)
    for ticker in sorted(sin_cronograma):
        historial.avisos.append(
            "{}: sin cronograma en instrumentos.json; sus cobros RENTA Y AMORTIZ ({}) se cuentan enteros como renta. "
            "Si el título amortiza, cargá el cronograma en iamc.pagos_manuales.".format(
                ticker, ", ".join(fecha.isoformat() for fecha in sorted(sin_cronograma[ticker]))))

    def cambio_de(fila, valor):
        """Pesos por unidad de una fila en dólares; sin MEP cercano, None con aviso."""
        cambio = fila.get("tc")
        if cambio is None:
            anteriores = [fecha for fecha in fechas_mep if fecha <= fila["operado"]]
            fecha = anteriores[-1] if anteriores else None
            if fecha is not None and (fila["operado"] - fecha).days <= 5:
                cambio = mapa_mep[fecha]
        if cambio is None:
            historial.valores_sin_dato += 1
            historial.avisos.append(_contexto(fila) + "Sin MEP del día o anterior de hasta cinco días para {} USD.".format(valor))
        return cambio

    def valor_ars(fila, importe=None):
        valor = fila["importe"] if importe is None else importe
        if fila["moneda"] == "ARS" or valor == 0:
            return valor
        cambio = cambio_de(fila, valor)
        if cambio is None:
            return None
        return _numero(valor * cambio, "El valor histórico en pesos")

    conocidos = []
    # El capital devuelto, como aportes y retiros, se informa y nunca entra al total conocido.
    _fuera_del_total = ("aporte", "retiro", "capital_devuelto")
    componentes = {clase: {"ARS": [], "USD": [], "equivalente_ars": [], "incompleto": False}
                   for clase in _CLASES_INGRESOS + _fuera_del_total}
    _calcular = object()

    def agregar_ingreso(clase, fila, importe=None, equivalente=_calcular):
        importe = fila["importe"] if importe is None else importe
        if clase in ("aporte", "retiro"):
            importe = abs(importe)
        if equivalente is _calcular:
            equivalente = valor_ars(fila, importe)
        grupo = componentes[clase]
        grupo[fila["moneda"]].append(importe)
        if equivalente is None:
            grupo["incompleto"] = True
        else:
            grupo["equivalente_ars"].append(equivalente)
            if clase not in _fuera_del_total:
                conocidos.append(equivalente)

    for (_, clase, _), grupo in cauciones.items():
        presentes = {fila["comprobante"] for fila in grupo}
        if not _PATAS[clase].issubset(presentes):
            numeros = ", ".join(str(fila.get("numero", "sin número")) for fila in grupo)
            historial.avisos.append("Caución {} en {} {} sin ambas patas; no se suma capital. Comprobantes: {}.".format(
                clase, grupo[0]["operado"].isoformat(), grupo[0]["moneda"], numeros))
            continue
        agregar_ingreso(clase, grupo[0], _suma(fila["importe"] for fila in grupo))
    for (moneda, numero), grupo in cauciones_iol.items():
        presentes = {fila["comprobante"] for fila in grupo}
        requeridos = {"IOL CAUCION", "IOL LIQUIDACION CAUCION"}
        if not requeridos.issubset(presentes):
            historial.avisos.append(
                "Caución IOL {} en {} sin ambas patas; no se suma capital.".format(numero, moneda))
            continue
        contado = next(fila for fila in grupo if fila["comprobante"] == "IOL CAUCION")
        if contado["importe"] == 0:
            historial.avisos.append(
                "Caución IOL {} en {} sin signo de colocación/toma; no se suma capital.".format(numero, moneda))
            continue
        clase = "caucion_colocada" if contado["importe"] < 0 else "caucion_tomada"
        liquidaciones = [fila for fila in grupo if fila["comprobante"] == "IOL LIQUIDACION CAUCION"]
        referencia = max(liquidaciones, key=lambda fila: (fila["operado"], fila["_indice"]))
        agregar_ingreso(clase, referencia, _suma(fila["importe"] for fila in grupo))

    creados, abiertos = [], defaultdict(deque)
    importes_extracto, importes_estimados = [], []

    def consumir(ticker, cantidad):
        restante, costo = _decimal(cantidad), Decimal(0)
        origenes_consumidos, costo_incompleto = set(), False
        while restante > 0 and abiertos[ticker]:
            lote = abiertos[ticker][0]
            disponible = _decimal(lote.cantidad)
            tomado = min(restante, disponible)
            origenes_consumidos.add(lote.origen)
            if lote.costo is None:
                costo_incompleto = True
            else:
                costo_tomado = _decimal(lote.costo) * tomado / disponible
                costo += costo_tomado
                lote.costo = _numero(_decimal(lote.costo) - costo_tomado, "El costo restante")
            lote.cantidad = _numero(disponible - tomado, "La cantidad restante")
            restante -= tomado
            if lote.cantidad == 0:
                abiertos[ticker].popleft()
        falta = _numero(restante, "La cantidad sin lote")
        incompleto = costo_incompleto or falta > 0 or not origenes_consumidos
        origen = ("incompleto" if incompleto else next(iter(origenes_consumidos))
                  if len(origenes_consumidos) == 1 else "mixto")
        return (None if incompleto else _numero(costo, "El costo realizado")), falta, origen

    def realizar(resultado, origen):
        conocidos.append(resultado)
        (importes_extracto if origen == "extracto" else importes_estimados).append(resultado)

    def devolver_capital(evento):
        """Separa capital y renta de un pago que amortiza y baja el costo de los lotes que lo cobraron."""
        ticker, pago, cobros, fecha_pago = evento["especie"], evento["_pago"], evento["_cobros"], evento["_fecha_pago"]
        # Se procesa antes que las compras del día del pago: estos son los lotes abiertos al cierre del día anterior.
        lotes = list(abiertos[ticker])
        nominales = _suma(lote.cantidad for lote in lotes)
        moneda = cobros[0]["moneda"]
        cobrado = _suma(fila["importe"] for fila in cobros)
        fecha_cobro = max(fila["operado"] for fila in cobros)
        registro = {"ticker": ticker, "fecha_pago": fecha_pago, "fecha_cobro": fecha_cobro, "nominales": nominales,
                    "amortizacion_100": None if pago is None else _numero(pago.amortizacion, "La amortización"),
                    "renta_100": None if pago is None else _numero(pago.renta, "La renta"),
                    "moneda": moneda, "cobrado": cobrado, "capital": None, "renta": None, "capital_ars": None}
        if nominales == 0:
            historial.amortizaciones.append(registro)
            historial.valores_sin_dato += 1
            historial.avisos.append(_contexto(evento) + "{}: el pago del {} amortiza y ningún lote lo cobró; el cobro "
                                    "queda sin dato.".format(ticker, fecha_pago.isoformat()))
            return
        if pago is None:
            capital = _decimal(cobrado)
        else:
            capital = pago.amortizacion * _decimal(nominales) / 100
            esperado = (pago.amortizacion + pago.renta) * _decimal(nominales) / 100
            minimo = Decimal("1") if moneda == "ARS" else Decimal("0.01")
            if abs(_decimal(cobrado) - esperado) > max(esperado / 100, minimo):
                historial.avisos.append(_contexto(evento) + "{}: por el pago del {} se cobraron {} {} y el cronograma da "
                                        "{} por {} VN; revisá nominales y cronograma.".format(
                                            ticker, fecha_pago.isoformat(), round(cobrado, 2), moneda,
                                            round(_numero(esperado, "El cobro esperado"), 2), nominales))
            if capital > _decimal(cobrado):
                historial.avisos.append(_contexto(evento) + "{}: lo cobrado por el pago del {} es menor que la amortización "
                                        "del cronograma; se toma todo como capital.".format(ticker, fecha_pago.isoformat()))
                capital = _decimal(cobrado)
        # El capital se toma de los cobros en orden; lo que queda de cada uno es renta.
        restante, capital_ars = capital, []
        for fila in cobros:
            importe = _decimal(fila["importe"])
            tomado = min(restante, importe) if importe > 0 else Decimal(0)
            restante -= tomado
            capital_fila = _numero(tomado, "El capital devuelto")
            renta_fila = _numero(importe - tomado, "La renta del cobro")
            cambio = 1.0 if fila["moneda"] == "ARS" or fila["importe"] == 0 else cambio_de(fila, fila["importe"])
            pesos = [None if cambio is None else _numero(valor * cambio, "El valor histórico en pesos")
                     for valor in (capital_fila, renta_fila)]
            if renta_fila:
                agregar_ingreso("renta", fila, renta_fila, pesos[1])
            if capital_fila and not evento["_final"]:
                agregar_ingreso("capital_devuelto", fila, capital_fila, pesos[0])
            capital_ars.append(pesos[0])
        total_ars = None if any(valor is None for valor in capital_ars) else _suma(capital_ars)
        registro.update(capital=_numero(capital, "El capital devuelto"),
                        renta=_numero(_decimal(cobrado) - capital, "La renta del pago"), capital_ars=total_ars)
        if evento["_final"]:
            # Pago final: el capital cierra la posición, como un cierre por los nominales que cobraron.
            costo, falta, origen = consumir(ticker, nominales)
            resultado = None if costo is None or total_ars is None else _suma((total_ars, -costo))
            historial.realizados.append(RealizadoHistorico(ticker, fecha_cobro, nominales, falta, total_ars, costo,
                                                         resultado, origen, "cierre"))
            if resultado is None:
                historial.ventas_sin_dato += 1
            else:
                realizar(resultado, origen)
            return
        historial.amortizaciones.append(registro)
        for lote in lotes:
            if total_ars is None:
                # Sin el capital en pesos tampoco se conoce lo que queda del costo.
                lote.costo = None
                continue
            if lote.costo is None:
                continue
            parte = _decimal(total_ars) * _decimal(lote.cantidad) / _decimal(nominales)
            costo = _decimal(lote.costo)
            if parte <= costo:
                lote.costo = _numero(costo - parte, "El costo restante")
                continue
            # Ya se recuperó todo lo pagado por el lote: el excedente es ganancia realizada.
            resultado = _numero(parte - costo, "El resultado de la amortización")
            lote.costo = 0.0
            historial.realizados.append(RealizadoHistorico(ticker, fecha_cobro, lote.cantidad, 0.0,
                                                         _numero(parte, "El capital del lote"),
                                                         _numero(costo, "El costo del lote"), resultado,
                                                         lote.origen, "amortizacion"))
            realizar(resultado, lote.origen)

    def orden_proceso(actual):
        if actual["_clase"] == "capital_devuelto":
            # Cobran los lotes abiertos al cierre del día anterior al pago: va antes que las compras de ese día.
            return (actual["_fecha_pago"], -1, _orden_numero(actual.get("numero")), actual["_indice"])
        return (actual["operado"], 0 if actual["_clase"] == "compra" else 1,
                _orden_numero(actual.get("numero")), actual["_indice"])

    for fila in sorted(procesables, key=orden_proceso):
        clase = fila["_clase"]
        if clase == "compra":
            costo = valor_ars(fila, abs(fila["importe"]))
            lote = Lote(fila["especie"], abs(fila["cantidad"]), fila.get("_origen", "extracto"),
                        fila["operado"], None, costo, fila.get("referencia", ""))
            creados.append(lote)
            abiertos[lote.ticker].append(lote)
        elif clase in ("venta", "cierre"):
            ticker = fila["especie"]
            if clase == "cierre":
                cantidad = fila.get("_cantidad_cierre")
                if cantidad is None:
                    cantidad = _suma(lote.cantidad for lote in abiertos[ticker])
                importes = [valor_ars(pago) for pago in fila["_pagos"]]
                importe = None if any(valor is None for valor in importes) else _suma(importes)
            else:
                cantidad = abs(fila["cantidad"])
                importe = valor_ars(fila)
            costo, falta, origen = consumir(ticker, cantidad)
            # Una venta por ajuste no sale de un extracto: su importe no es un dato observado.
            if fila.get("_origen") == "estimado" and origen == "extracto":
                origen = "mixto"
            resultado = None if costo is None or importe is None else _suma((importe, -costo))
            historial.realizados.append(RealizadoHistorico(ticker, fila["operado"], cantidad, falta,
                                                         importe, costo, resultado, origen, clase))
            if resultado is None:
                historial.ventas_sin_dato += 1
                if falta > 0:
                    historial.avisos.append(_contexto(fila) + "Venta de {} sin lotes para {} unidades; resultado sin dato.".format(ticker, falta))
                elif clase == "cierre" and cantidad == 0:
                    historial.avisos.append(_contexto(fila) + "Cierre de {} sin lotes abiertos; resultado sin dato.".format(ticker))
            else:
                realizar(resultado, origen)
        elif clase == "capital_devuelto":
            devolver_capital(fila)
        elif clase in componentes:
            agregar_ingreso(clase, fila)
        else:
            # Solo se llega aquí si se agregó una clase sin tratamiento explícito.
            # Tampoco ese caso puede convertirse en ganancia o desaparecer.
            desconocida = {clave: copy.deepcopy(valor) for clave, valor in fila.items() if not clave.startswith("_")}
            historial.sin_clasificar.append(desconocida)

    for clase, grupo in componentes.items():
        bolsa = {moneda: _suma(grupo[moneda]) for moneda in ("ARS", "USD")}
        bolsa["equivalente_ars"] = None if grupo["incompleto"] else _suma(grupo["equivalente_ars"])
        if clase == "aporte":
            historial.aportes = bolsa
        elif clase == "retiro":
            historial.retiros = bolsa
        elif clase == "capital_devuelto":
            historial.capital_devuelto = bolsa
        else:
            historial.ingresos[clase] = bolsa
    historial.lotes = [lote for lote in creados if lote.cantidad > 0]
    historial.total_conocido = _suma(conocidos)
    historial.realizado_extracto = _suma(importes_extracto)
    historial.realizado_estimado = _suma(importes_estimados)
    return historial


def conciliar_tenencias(lotes, posiciones):
    """Informa diferencias nominales mayores a 0,5 sin modificar las entradas."""
    derivadas, base = defaultdict(Decimal), defaultdict(Decimal)
    for lote in lotes:
        derivadas[lote.ticker] += _decimal(_numero(lote.cantidad, "La cantidad del lote"))
    for posicion in posiciones:
        base[posicion.ticker] += _decimal(_numero(posicion.cantidad, "La cantidad base"))
    diferencias = {}
    for ticker in sorted(set(derivadas) | set(base)):
        diferencia = derivadas[ticker] - base[ticker]
        if abs(diferencia) > Decimal("0.5"):
            diferencias[ticker] = {"derivada": _numero(derivadas[ticker], "La cantidad derivada"),
                                   "base": _numero(base[ticker], "La cantidad base"),
                                   "diferencia": _numero(diferencia, "La diferencia de cantidad")}
    return diferencias
