"""Proyecciones de letras separadas de la valuación y del resultado de cartera.

Reutiliza exclusivamente el motor Decimal validado del Fixed Income Toolkit.
Los precios originales se informan aparte: nunca se deducen del costo neto.
Las letras dólar linked se listan sin activar su metodología todavía pendiente.
"""

from dataclasses import asdict, dataclass
from datetime import date, datetime
from decimal import Decimal, InvalidOperation, localcontext
import hashlib
import json
import re
from zoneinfo import ZoneInfo

from ._motor_letras.letras_yield import LetraYieldInput, calculate_letra_yield
from ._motor_letras.maturity_value import (
    InstrumentType, MaturityValueInput, calculate_maturity_value,
)
from .movimientos import aplicar_movimientos, cartera_actual
from .punto_partida import Lote


class ErrorLetra(ValueError):
    """Datos de letras inválidos; no se sustituyen por valores supuestos."""

    def __init__(self, errores):
        self.errores = [errores] if isinstance(errores, str) else list(errores)
        super().__init__("\n".join(self.errores))


@dataclass
class _LoteReferenciado(Lote):
    referencia: str = ""


def _hoy_argentina():
    return datetime.now(ZoneInfo("America/Argentina/Buenos_Aires")).date()


def _fecha(valor, campo):
    if isinstance(valor, datetime):
        raise ErrorLetra("{} debe ser una fecha sin hora.".format(campo))
    if isinstance(valor, date):
        return valor
    if isinstance(valor, str) and re.fullmatch(r"\d{4}-\d{2}-\d{2}", valor):
        try:
            return date.fromisoformat(valor)
        except ValueError:
            pass
    raise ErrorLetra("{} inválida; usá AAAA-MM-DD.".format(campo))


def _decimal(valor, campo, cero=False):
    if isinstance(valor, bool) or not isinstance(valor, (str, int, float, Decimal)):
        raise ErrorLetra("{} debe ser un número finito {}.".format(campo, "no negativo" if cero else "positivo"))
    try:
        numero = Decimal(str(valor))
    except (InvalidOperation, ValueError):
        raise ErrorLetra("{} inválido; usá punto decimal y sin separadores de miles.".format(campo))
    if not numero.is_finite() or numero < 0 or not cero and numero == 0:
        raise ErrorLetra("{} debe ser un número finito {}.".format(campo, "no negativo" if cero else "positivo"))
    return numero


def _texto_decimal(valor):
    return format(valor, "f")


def _canonico(valor):
    if isinstance(valor, (date, datetime)):
        return valor.isoformat()
    if isinstance(valor, Decimal):
        return _texto_decimal(valor)
    if isinstance(valor, dict):
        return {clave: _canonico(dato) for clave, dato in valor.items()}
    if isinstance(valor, (list, tuple)):
        return [_canonico(dato) for dato in valor]
    return valor


def _huella(referencia, dato):
    contenido = json.dumps({"referencia": referencia, "origen": _canonico(dato)},
                           sort_keys=True, ensure_ascii=False, separators=(",", ":"),
                           allow_nan=False).encode("utf-8")
    return hashlib.sha256(contenido).hexdigest()


def letras_indexadas(instrumentos):
    """Letras CER o dólar linked que siguen el flujo indexado de IAMC en lugar del panel de letras."""
    resultado = set()
    for ticker, configuracion in (instrumentos or {}).items():
        vinculo = configuracion.get("iamc") if isinstance(configuracion, dict) else None
        if isinstance(vinculo, dict) and isinstance(vinculo.get("indice"), dict):
            resultado.add(ticker)
    return resultado


def referencias_flujo(base, movimientos, instrumentos):
    """Compras con precio en compras_bonos.json: bonos, ON y letras indexadas vinculadas a IAMC."""
    indexadas = letras_indexadas(instrumentos)
    referencias = referencias_compras(base, movimientos, tipos=("bono", "on"))
    if indexadas:
        referencias += [ref for ref in referencias_compras(base, movimientos, tipos=("letra",))
                        if ref["ticker"] in indexadas]
    return referencias


def referencias_compras(base, movimientos, tipos=("letra",)):
    """Relaciona compras originales y remanentes usando el FIFO ya existente.

    Los índices incluyen todos los lotes y movimientos de origen.
    La huella protege el dato original: una corrección nunca reasocia un precio
    manual a otra compra que haya ocupado su renglón.
    """
    tipos_por_ticker = {posicion.ticker: posicion.tipo for posicion in base.posiciones}
    referencias = []
    por_referencia = {}
    lotes = []
    for indice, lote in enumerate(base.lotes, 1):
        referencia = "base:{}".format(indice)
        datos_lote = asdict(lote)
        lotes.append(_LoteReferenciado(**datos_lote, referencia=referencia))
        tipo = tipos_por_ticker.get(lote.ticker)
        if tipo not in tipos:
            continue
        dato = {"referencia": referencia,
                "huella": _huella(referencia, {"lote": datos_lote, "tipo": tipo}),
                "ticker": lote.ticker,
                "fecha_compra": None if lote.fecha is None else lote.fecha.isoformat(),
                "cantidad": lote.cantidad, "cantidad_restante": 0.0}
        referencias.append(dato)
        por_referencia[referencia] = dato

    def crear_compra(indice, movimiento, lote):
        referencia = "movimiento:{}".format(indice)
        tipo = tipos_por_ticker.setdefault(lote.ticker, movimiento.get("tipo_activo", ""))
        if tipo in tipos:
            dato = {"referencia": referencia, "huella": _huella(referencia, movimiento),
                    "ticker": lote.ticker, "fecha_compra": lote.fecha.isoformat(),
                    "cantidad": lote.cantidad, "cantidad_restante": 0.0}
            referencias.append(dato)
            por_referencia[referencia] = dato
        return _LoteReferenciado(**asdict(lote), referencia=referencia)

    restantes, _ = aplicar_movimientos(lotes, movimientos, _crear_compra=crear_compra)
    for lote in restantes:
        if lote.referencia in por_referencia:
            por_referencia[lote.referencia]["cantidad_restante"] = lote.cantidad
    return referencias


def _normalizar_dato_compra(registro, *, bonos=False):
    especie = "bonos" if bonos else "letras"
    if not isinstance(registro, dict):
        raise ErrorLetra("Cada compra de {} debe ser un objeto.".format(especie))
    claves = {"referencia", "huella", "precio", "moneda", "fecha_liquidacion"}
    opcionales = {"tc"} if bonos else set()
    if set(registro) - opcionales != claves:
        sufijo = " y permite tc opcional" if bonos else ""
        raise ErrorLetra("La compra requiere solamente referencia, huella, precio, moneda y fecha_liquidacion{}.".format(sufijo))
    referencia, huella = registro.get("referencia"), registro.get("huella")
    if not isinstance(referencia, str) or not re.fullmatch(r"(?:base|movimiento):[1-9]\d*", referencia):
        raise ErrorLetra("Referencia de compra inválida; usá base:N o movimiento:N.")
    if not isinstance(huella, str) or not re.fullmatch(r"[0-9a-f]{64}", huella):
        raise ErrorLetra("Huella de compra inválida; debe ser SHA-256 hexadecimal.")
    moneda = registro.get("moneda")
    if not isinstance(moneda, str) or moneda.upper() not in ("ARS", "USD"):
        raise ErrorLetra("Moneda de compra inválida; usá ARS o USD.")
    dato = {"referencia": referencia, "huella": huella,
            "precio": _texto_decimal(_decimal(registro.get("precio"), "precio de compra")),
            "moneda": moneda.upper(),
            "fecha_liquidacion": _fecha(registro.get("fecha_liquidacion"), "Fecha de liquidación").isoformat()}
    if bonos and "tc" in registro:
        dato["tc"] = _texto_decimal(_decimal(registro["tc"], "Tipo de cambio de compra"))
    return dato


def validar_compras(contenido, *, bonos=False):
    """Valida y copia el archivo auxiliar, sin consultar el reloj ni escribir."""
    if (not isinstance(contenido, dict) or set(contenido) != {"esquema_version", "compras"}
            or type(contenido.get("esquema_version")) is not int
            or contenido["esquema_version"] != 1 or not isinstance(contenido.get("compras"), list)):
        especie = "bonos" if bonos else "letras"
        raise ErrorLetra("Compras de {}: se requiere esquema_version 1 y una lista compras.".format(especie))
    normalizadas, vistas, errores = [], set(), []
    for indice, registro in enumerate(contenido["compras"], 1):
        try:
            normalizado = _normalizar_dato_compra(registro, bonos=bonos)
            if normalizado["referencia"] in vistas:
                raise ErrorLetra("Referencia de compra repetida: {}.".format(normalizado["referencia"]))
            vistas.add(normalizado["referencia"])
            normalizadas.append(normalizado)
        except ErrorLetra as error:
            errores.extend("Compra {}: {}".format(indice, mensaje) for mensaje in error.errores)
    if errores:
        raise ErrorLetra(errores)
    return {"esquema_version": 1, "compras": normalizadas}


def validar_dato_compra(registro, referencias, hoy, *, bonos=False):
    """Valida la asociación a una compra exacta y su liquidación histórica."""
    dato = _normalizar_dato_compra(registro, bonos=bonos)
    fecha_hoy = _fecha(hoy, "Fecha de hoy")
    fuentes = {fuente["referencia"]: fuente for fuente in referencias}
    fuente = fuentes.get(dato["referencia"])
    if fuente is None:
        especie = "bonos" if bonos else "letras"
        raise ErrorLetra("{}: no existe esa referencia de compra de {}.".format(dato["referencia"], especie))
    if dato["huella"] != fuente["huella"]:
        raise ErrorLetra("{}: cambió la huella de la compra original; revisá el precio manual, no se reasocia.".format(dato["referencia"]))
    liquidacion = _fecha(dato["fecha_liquidacion"], "Fecha de liquidación")
    if liquidacion > fecha_hoy:
        raise ErrorLetra("{}: fecha de liquidación futura.".format(dato["referencia"]))
    compra = fuente.get("fecha_compra")
    if compra is not None and liquidacion < _fecha(compra, "Fecha de compra"):
        raise ErrorLetra("{}: la liquidación no puede ser anterior a la compra.".format(dato["referencia"]))
    return dato


def precio_en_moneda_flujo(registro, moneda_flujo):
    """Devuelve el precio por 100 VN en moneda de flujo usando el TC de compra."""
    moneda = registro.get("moneda")
    if moneda not in ("ARS", "USD") or moneda_flujo not in ("ARS", "USD"):
        raise ErrorLetra("Las monedas de compra y de los flujos deben ser ARS o USD.")
    precio = _decimal(registro.get("precio"), "Precio de compra")
    if moneda == moneda_flujo:
        return precio
    if registro.get("tc") is None:
        raise ErrorLetra("La moneda de compra difiere de la moneda de los flujos. Indicá --tc en pesos por dólar.")
    cambio = _decimal(registro["tc"], "Tipo de cambio de compra")
    with localcontext() as contexto:
        contexto.prec = 50
        return precio / cambio if moneda == "ARS" else precio * cambio


def _datos_instrumento(ticker, instrumentos, avisos):
    configuracion = instrumentos.get(ticker, {}) if isinstance(instrumentos, dict) else {}
    if not isinstance(configuracion, dict):
        avisos.append("{}: datos contractuales de instrumento inválidos.".format(ticker))
        return {}, {}, None
    letra = configuracion.get("letra", {})
    if not isinstance(letra, dict):
        avisos.append("{}: configuración letra inválida.".format(ticker))
        letra = {}
    vencimiento = None
    if configuracion.get("vencimiento") is not None:
        try:
            vencimiento = _fecha(configuracion["vencimiento"], "Vencimiento de {}".format(ticker))
        except ErrorLetra as error:
            avisos.extend(error.errores)
    else:
        avisos.append("{}: falta vencimiento contractual; no se deduce del ticker.".format(ticker))
    return configuracion, letra, vencimiento


def _monto_contractual(ticker, letra, vencimiento, avisos):
    familia = letra.get("familia")
    if familia == "LELINK":
        avisos.append("{}: Cálculo dólar linked pendiente de validación del Toolkit.".format(ticker))
        # La base nominal es una unidad declarada, no una fórmula de pago.
        # Conservarla permite leer un precio manual sin habilitar R-006.
        try:
            base = _decimal(letra.get("base_nominal"), "Base nominal de {}".format(ticker))
        except ErrorLetra as error:
            avisos.extend(error.errores)
            base = None
        return None, base
    if familia not in ("LECAP", "BONCAP"):
        avisos.append("{}: falta familia contractual aprobada (LECAP o BONCAP).".format(ticker))
        return None, None
    if letra.get("moneda_pago") != "ARS":
        avisos.append("{}: la metodología aprobada LECAP/BONCAP requiere moneda de pago ARS explícita.".format(ticker))
        return None, None
    campos = ("fecha_emision", "tem_emision", "base_nominal", "fuente")
    faltantes = [campo for campo in campos if letra.get(campo) in (None, "")]
    if faltantes or vencimiento is None:
        if faltantes:
            avisos.append("{}: faltan datos contractuales: {}.".format(ticker, ", ".join(faltantes)))
        return None, None
    try:
        if not isinstance(letra["fuente"], str) or not letra["fuente"].strip():
            raise ErrorLetra("{}: falta fuente contractual verificable.".format(ticker))
        base = _decimal(letra["base_nominal"], "Base nominal de {}".format(ticker))
        resultado = calculate_maturity_value(MaturityValueInput(
            instrument_type=InstrumentType(familia),
            issue_date=_fecha(letra["fecha_emision"], "Emisión de {}".format(ticker)),
            maturity_date=vencimiento,
            monthly_issue_rate=_decimal(letra["tem_emision"], "TEM de emisión de {}".format(ticker), cero=True),
            reference_face_value=base,
            # Igual que local_dashboard.metrics del Toolkit: no hay VPV oficial
            # para comparar. Se consume solo maturity_value, jamás diferencia.
            official_maturity_value=Decimal(0), source_reference=letra["fuente"].strip()))
        return resultado.maturity_value, base
    except (ErrorLetra, ArithmeticError, ValueError) as error:
        avisos.append("{}: no se pudo calcular el pago contractual: {}".format(ticker, error))
    except Exception as error:
        # El motor copiado define excepciones de dominio propias.
        avisos.append("{}: datos contractuales rechazados por el motor: {}".format(ticker, error))
    return None, None


def calcular_letras(base, movimientos, instrumentos, compras=None, hoy=None):
    """Lista tenencias vigentes y proyecciones; nunca altera otros resultados.

    Un pago esperado no se suma al efectivo ni a la valuación actual. Las
    cantidades provienen de cartera_actual y el remanente de su mismo FIFO.
    """
    fecha_hoy = _hoy_argentina() if hoy is None else _fecha(hoy, "Fecha de hoy")
    actual, _ = cartera_actual(base, movimientos)
    referencias = referencias_compras(base, movimientos)
    avisos, datos = [], {}
    if compras is not None:
        try:
            registros = validar_compras(compras)["compras"]
        except ErrorLetra as error:
            avisos.extend("Compras de letras: {}".format(mensaje) for mensaje in error.errores)
            registros = []
        for registro in registros:
            try:
                dato = validar_dato_compra(registro, referencias, fecha_hoy)
                datos[dato["referencia"]] = dato
            except ErrorLetra as error:
                avisos.extend(error.errores)
    filas = []
    for posicion in actual.posiciones:
        if posicion.tipo != "letra":
            continue
        avisos_fila = []
        _, letra, vencimiento = _datos_instrumento(posicion.ticker, instrumentos, avisos_fila)
        valor, base_nominal = _monto_contractual(posicion.ticker, letra, vencimiento, avisos_fila)
        abiertos = [ref for ref in referencias if ref["ticker"] == posicion.ticker and ref["cantidad_restante"] > 0]
        nominal_lotes = sum((Decimal(str(ref["cantidad_restante"])) for ref in abiertos), Decimal(0))
        if nominal_lotes != Decimal(str(posicion.cantidad)):
            avisos_fila.append("{}: discrepancia nominal; tenencia {} y lotes {}. El pago usa la tenencia vigente, no suma lotes.".format(
                posicion.ticker, posicion.cantidad, nominal_lotes))
        lotes = []
        for ref in abiertos:
            registro = datos.get(ref["referencia"])
            lote = {"referencia": ref["referencia"], "huella": ref["huella"],
                    "fecha_compra": ref["fecha_compra"], "cantidad_restante": ref["cantidad_restante"],
                    "precio": None, "moneda": None, "base_precio": "100", "fecha_liquidacion": None,
                    "rendimiento": None, "tea": None}
            if registro is None:
                avisos_fila.append("{} {}: falta precio original de compra y liquidación; no se deducen del costo neto.".format(
                    posicion.ticker, ref["referencia"]))
            else:
                lote.update({campo: registro[campo] for campo in ("precio", "moneda", "fecha_liquidacion")})
                liquidacion = _fecha(registro["fecha_liquidacion"], "Liquidación")
                if ref["fecha_compra"] is None:
                    avisos_fila.append("{} {}: falta fecha de compra; rendimiento sin dato.".format(posicion.ticker, ref["referencia"]))
                elif vencimiento is not None and liquidacion >= vencimiento:
                    avisos_fila.append("{} {}: la liquidación debe ser anterior al vencimiento; rendimiento sin dato.".format(posicion.ticker, ref["referencia"]))
                elif (valor is not None
                      and liquidacion < _fecha(letra["fecha_emision"], "Fecha de emisión")):
                    avisos_fila.append("{} {}: la liquidación precede la emisión contractual; rendimiento sin dato.".format(posicion.ticker, ref["referencia"]))
                elif registro["moneda"] != letra.get("moneda_pago"):
                    avisos_fila.append("{} {}: precio y pago en monedas diferentes; rendimiento sin dato.".format(posicion.ticker, ref["referencia"]))
                elif valor is not None:
                    try:
                        # Los precios manuales conservan la unidad de cotización
                        # de cartera: cada 100 VN. El VPV contractual puede venir
                        # en otra base explícita y se normaliza antes de compararlo.
                        with localcontext() as contexto:
                            contexto.prec = 50
                            valor_precio = valor / base_nominal * Decimal(100)
                        rendimiento = calculate_letra_yield(LetraYieldInput(
                            market_price=Decimal(registro["precio"]), settlement_date=liquidacion,
                            maturity_date=vencimiento, maturity_value=valor_precio,
                            source_reference=letra["fuente"]))
                        lote["rendimiento"] = _texto_decimal(rendimiento.holding_period_return)
                        lote["tea"] = _texto_decimal(rendimiento.tea)
                    except Exception as error:
                        avisos_fila.append("{} {}: rendimiento sin dato; {}".format(posicion.ticker, ref["referencia"], error))
            lotes.append(lote)
        pago = None
        if valor is not None:
            with localcontext() as contexto:
                contexto.prec = 50
                pago = Decimal(str(posicion.cantidad)) / base_nominal * valor
        filas.append({"ticker": posicion.ticker, "cantidad": posicion.cantidad,
                      "moneda_pago": letra.get("moneda_pago"), "familia": letra.get("familia"),
                      "vencimiento": None if vencimiento is None else vencimiento.isoformat(),
                      "dias_restantes": None if vencimiento is None else (vencimiento - fecha_hoy).days,
                      "valor_por_base": None if valor is None else _texto_decimal(valor),
                      "base_nominal": None if base_nominal is None else _texto_decimal(base_nominal),
                      "pago_vencimiento": None if pago is None else _texto_decimal(pago),
                      "lotes": lotes, "avisos": avisos_fila})
    return {"fecha_calculo": fecha_hoy.isoformat(), "posiciones": filas, "avisos": avisos}
