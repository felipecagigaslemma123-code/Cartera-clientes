"""Lectura verificable de extractos y archivos auxiliares del historial.

Conserva la procedencia y los campos de cada renglón; la clasificación es una
lista explícita, sin inferencias por nombres o importes.
"""

import copy
import csv
import math
import re
from collections import OrderedDict
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from html.parser import HTMLParser
from numbers import Real
from pathlib import Path
from xml.etree.ElementTree import ParseError
from zipfile import BadZipFile

from openpyxl import load_workbook
from openpyxl.utils.exceptions import InvalidFileException

from .movimientos import ErrorMovimiento, _normalizar


_ENCABEZADO = ("Liquida", "Operado", "Comprobante", "Numero", "Cantidad", "Especie", "Precio", "Importe", "Saldo", "Referencia")
_AJUSTES = ("fecha", "tipo", "ticker", "cantidad", "importe", "moneda", "tc", "tipo_activo", "nota")
_TIPOS_AJUSTES = {"compra", "venta", "renta", "dividendo", "gasto"}
_CLASES = {
    "COMPRA NORMAL": "compra", "COMPRA TRADING": "compra", "COMPRA PARIDAD": "compra",
    "COMPRA CABLE": "compra",
    "VENTA": "venta", "VENTA TRADING": "venta", "VENTA PARIDAD": "venta", "VENTA CABLE": "venta",
    "DIVIDENDOS": "dividendo", "RETENCION": "retencion",
    "SUSCRIPCION FCI": "fci", "LIQUIDACION RESCATE FCI": "fci",
    "CREDITO DERMERC-": "gastos", "N C ARANCELES": "gastos", "NOTA DE CREDITO EO": "compensacion",
    "RECIBO DE COBRO": "aporte", "ORDEN DE PAGO": "retiro",
    "COMPRA CAUCION CONTADO": "caucion_colocada", "VENTA CAUCION TERMINO": "caucion_colocada",
    "VENTA CAUCION CONTADO": "caucion_tomada", "COMPRA CAUCION TERMINO": "caucion_tomada",
    "IOL COMPRA": "compra", "IOL VENTA": "venta", "IOL IMPUESTO": "gastos",
    "IOL RENTA": "renta", "IOL DIVIDENDO": "dividendo", "IOL GASTO DE COBRO": "gastos",
    "IOL AMORTIZACION": "amortizacion", "IOL DEPOSITO": "aporte", "IOL EXTRACCION": "retiro",
    "IOL SUSCRIPCION FCI": "fci", "IOL RESCATE FCI": "fci", "IOL CREDITO": "gastos",
    "IOL CAUCION": "caucion_iol", "IOL LIQUIDACION CAUCION": "caucion_iol",
}

_ENCABEZADO_IOL = (
    "Nro. de Mov.", "Nro. de Boleto", "Tipo Mov.", "Concert.", "Liquid.", "Est",
    "Cant. titulos", "Precio", "Comis.", "Iva Com.", "Otros Imp.", "Monto",
    "Observaciones", "Tipo Cuenta",
)


class _TablasHTML(HTMLParser):
    """Extrae tablas sin interpretar el resto de la página exportada por IOL."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.tablas = []
        self._tabla = None
        self._fila = None
        self._celda = None

    def handle_starttag(self, etiqueta, atributos):
        etiqueta = etiqueta.lower()
        if etiqueta == "table" and self._tabla is None:
            self._tabla = []
        elif etiqueta == "tr" and self._tabla is not None:
            self._fila = []
        elif etiqueta in ("th", "td") and self._fila is not None:
            self._celda = []

    def handle_data(self, datos):
        if self._celda is not None:
            self._celda.append(datos)

    def handle_endtag(self, etiqueta):
        etiqueta = etiqueta.lower()
        if etiqueta in ("th", "td") and self._celda is not None:
            self._fila.append(" ".join("".join(self._celda).split()))
            self._celda = None
        elif etiqueta == "tr" and self._fila is not None:
            if self._fila:
                self._tabla.append(self._fila)
            self._fila = None
        elif etiqueta == "table" and self._tabla is not None:
            self.tablas.append(self._tabla)
            self._tabla = None


def _numero_iol(valor, nombre, vacio=0.0):
    texto = "" if valor is None else str(valor).strip()
    if not texto:
        return vacio
    if not re.fullmatch(r"[+-]?(?:\d{1,3}(?:\.\d{3})+|\d+)(?:,\d+)?", texto):
        raise ErrorHistorial(nombre + " debe usar punto de miles y coma decimal.")
    try:
        numero = float(texto.replace(".", "").replace(",", "."))
    except (ValueError, OverflowError):
        raise ErrorHistorial(nombre + " debe ser un número finito.") from None
    if not math.isfinite(numero):
        raise ErrorHistorial(nombre + " debe ser un número finito.")
    return numero


def _fecha_iol(valor):
    try:
        return datetime.strptime(valor.strip(), "%d/%m/%y").date()
    except (AttributeError, ValueError):
        raise ErrorHistorial("Concert. debe ser una fecha válida (dd/mm/aa).") from None


def _especie_iol(tipo):
    coincidencia = re.search(r"\(([^()]*)\)", tipo)
    especie = coincidencia.group(1).strip() if coincidencia else ""
    if especie.endswith(" US$"):
        especie = especie[:-4].rstrip()
    return especie


def _comprobante_iol(tipo, importe, cantidad):
    if tipo.startswith("Compra("):
        return "IOL COMPRA", abs(cantidad)
    if tipo.startswith("Venta("):
        return "IOL VENTA", -abs(cantidad)
    if tipo.startswith("Pago de Renta"):
        return ("IOL GASTO DE COBRO" if importe < 0 else "IOL RENTA"), 0.0
    if tipo.startswith("Pago de Dividendos"):
        return ("IOL GASTO DE COBRO" if importe < 0 else "IOL DIVIDENDO"), 0.0
    if tipo.startswith("Pago de Amortización"):
        if cantidad > 0:
            raise ErrorHistorial("Una amortización no puede aumentar nominales.")
        return "IOL AMORTIZACION", cantidad
    if tipo.startswith("Depósito de Fondos"):
        return "IOL DEPOSITO", 0.0
    if tipo.startswith("Extracción de Fondos"):
        return "IOL EXTRACCION", 0.0
    if tipo.startswith("Suscripción FCI("):
        return "IOL SUSCRIPCION FCI", 0.0
    if tipo.startswith("Rescate FCI("):
        return "IOL RESCATE FCI", 0.0
    if tipo.startswith("Caución("):
        return "IOL CAUCION", 0.0
    if tipo == "Liquidación de Caución":
        return "IOL LIQUIDACION CAUCION", 0.0
    if tipo == "Crédito":
        return "IOL CREDITO", 0.0
    return tipo, cantidad


def leer_extracto_iol(ruta):
    """Lee la tabla HTML que IOL entrega con extensión ``.xls``."""
    ruta = Path(ruta)
    try:
        texto = ruta.read_bytes().decode("utf-8")
        analizador = _TablasHTML()
        analizador.feed(texto)
        analizador.close()
    except (OSError, UnicodeError, ValueError):
        raise ErrorHistorial(ruta.name + ": no se puede leer como extracto HTML de IOL válido.") from None
    candidatas = [tabla for tabla in analizador.tablas if tabla and tuple(tabla[0]) == _ENCABEZADO_IOL]
    if len(candidatas) != 1:
        raise ErrorHistorial(ruta.name + ": no contiene una única tabla de operaciones históricas de IOL con el encabezado esperado.")
    errores, filas = [], []
    for numero_fila, valores in enumerate(candidatas[0][1:], 2):
        contexto = "{} · fila {}".format(ruta.name, numero_fila)
        if len(valores) != len(_ENCABEZADO_IOL):
            errores.append(contexto + ": se requieren exactamente 14 columnas.")
            continue
        datos = dict(zip(_ENCABEZADO_IOL, valores))
        if datos["Est"] != "Terminada":
            continue
        problemas = []
        try:
            numero = _numero_comprobante(datos["Nro. de Mov."])
            if numero == "":
                raise ErrorHistorial("Nro. de Mov. no puede estar vacío.")
            operado = _fecha_iol(datos["Concert."])
            importe = _numero_iol(datos["Monto"], "Monto")
            cantidad = _numero_iol(datos["Cant. titulos"], "Cant. titulos")
            cuentas = {
                "Inversion Argentina Pesos": ("ARS", "PESOS"),
                "Inversion Argentina Dolares": ("USD", "DOLARES"),
            }
            if datos["Tipo Cuenta"] not in cuentas:
                raise ErrorHistorial("Tipo Cuenta no identifica una cuenta admitida de IOL.")
            moneda, cuenta = cuentas[datos["Tipo Cuenta"]]
            referencia = datos["Tipo Mov."]
            comprobante, cantidad = _comprobante_iol(referencia, importe, cantidad)
            especie = _especie_iol(referencia)
        except ErrorHistorial as error:
            problemas.extend(error.errores)
        if problemas:
            errores.extend(contexto + ": " + problema for problema in problemas)
            continue
        filas.append({
            "moneda": moneda, "cuenta": cuenta, "operado": operado,
            "comprobante": comprobante, "numero": numero, "cantidad": cantidad,
            "especie": especie, "importe": importe, "saldo": None,
            "referencia": referencia, "archivo": ruta.name, "fila": numero_fila,
        })
    operaciones = OrderedDict()
    for fila in filas:
        if fila["comprobante"] in ("IOL COMPRA", "IOL VENTA"):
            operaciones.setdefault(fila["numero"], []).append(fila)
    for numero, grupo in operaciones.items():
        if len(grupo) > 1:
            valido = (len(grupo) == 2 and {fila["moneda"] for fila in grupo} == {"ARS", "USD"}
                      and len({fila["comprobante"] for fila in grupo}) == 1
                      and len({fila["referencia"] for fila in grupo}) == 1)
            if not valido:
                errores.append("{}: Nro. de Mov. {} está repetido entre compras o ventas sin formar una operación en dólares válida.".format(
                    ruta.name, numero))
                continue
        if len(grupo) == 1 and grupo[0]["moneda"] != "USD":
            continue
        for fila in grupo:
            if fila["especie"].endswith("D"):
                fila["especie"] = fila["especie"][:-1]
        for fila in grupo:
            if fila["moneda"] == "ARS" and len(grupo) == 2:
                fila["comprobante"] = "IOL IMPUESTO"
                fila["cantidad"] = 0.0
    if errores:
        raise ErrorHistorial(errores)
    return filas


class ErrorHistorial(ValueError):
    """Un archivo inválido conserva todos los problemas detectados."""

    def __init__(self, errores):
        self.errores = [errores] if isinstance(errores, str) else list(errores)
        super().__init__("\n".join(self.errores))


def _vacio(valor):
    return valor is None or isinstance(valor, str) and not valor.strip()


def _fecha(valor, nombre):
    if isinstance(valor, datetime):
        return valor.date()
    if isinstance(valor, date):
        return valor
    if isinstance(valor, str) and re.fullmatch(r"\d{4}-\d{2}-\d{2}", valor.strip()):
        try:
            return date.fromisoformat(valor.strip())
        except ValueError:
            pass
    raise ErrorHistorial(nombre + " debe ser una fecha válida (AAAA-MM-DD).")


def _numero(valor, nombre, vacio=None):
    if _vacio(valor) and vacio is not None:
        return vacio
    if isinstance(valor, bool) or not isinstance(valor, (Real, str)):
        raise ErrorHistorial(nombre + " debe ser un número finito.")
    try:
        numero = float(valor)
    except (TypeError, ValueError, OverflowError):
        raise ErrorHistorial(nombre + " debe ser un número finito, con punto decimal y sin miles.") from None
    if not math.isfinite(numero):
        raise ErrorHistorial(nombre + " debe ser un número finito.")
    return numero


def _numero_comprobante(valor):
    # Es un identificador, no un importe ni una cantidad. Puede ser alfanumérico
    # o estar ausente; los enteros textuales no deben perder precisión.
    if _vacio(valor):
        return ""
    if isinstance(valor, bool) or not isinstance(valor, (Real, str)):
        raise ErrorHistorial("Numero debe ser un identificador de texto o un número finito.")
    try:
        numero = Decimal(str(valor).strip())
    except InvalidOperation:
        if isinstance(valor, str):
            return valor.strip()
        raise ErrorHistorial("Numero debe ser un identificador válido.") from None
    if not numero.is_finite():
        raise ErrorHistorial("Numero debe ser finito.")
    try:
        finito = math.isfinite(float(numero))
    except (OverflowError, ValueError):
        finito = False
    if not finito:
        raise ErrorHistorial("Numero excede el rango finito admitido.")
    return int(numero) if numero == numero.to_integral_value() else float(numero)


def _texto(valor, nombre):
    if valor is None:
        return ""
    if not isinstance(valor, str):
        raise ErrorHistorial(nombre + " debe ser texto.")
    return valor.strip()


def _dato_original(valor):
    # Los campos no usados en cálculos se conservan, incluidas fórmulas como texto.
    if isinstance(valor, datetime):
        return valor.date()
    if isinstance(valor, float) and not math.isfinite(valor):
        raise ErrorHistorial("El dato original debe ser finito.")
    return valor


def _cuenta(titulo):
    titulo = titulo.upper()
    pesos = re.search(r"\bPESOS\b", titulo) is not None
    dolares = re.search(r"\bDOLARES\b", titulo) is not None
    cable = re.search(r"\bCABLE\b", titulo) is not None
    if pesos == dolares or cable and not dolares:
        raise ErrorHistorial("No se puede determinar una moneda única del título de la primera hoja: " + titulo)
    return ("USD", "CABLE" if cable else "DOLARES") if dolares else ("ARS", "PESOS")


def leer_extracto(ruta):
    """Lee solo la primera hoja y devuelve fechas, números y contexto de origen."""
    ruta = Path(ruta)
    libro = None
    errores, filas = [], []
    try:
        # Sin read_only: algunos extractos reales declaran un rango menor al que contienen.
        libro = load_workbook(ruta, data_only=False)
        hoja = libro.worksheets[0]
        moneda, cuenta = _cuenta(hoja.title)
        lector = hoja.iter_rows(values_only=True)
        encabezado = list(next(lector, ()))
        while encabezado and encabezado[-1] is None:
            encabezado.pop()
        if tuple(encabezado) != _ENCABEZADO:
            raise ErrorHistorial("Fila 1: el encabezado debe ser exactamente " + ", ".join(_ENCABEZADO) + ".")
        for numero_fila, valores in enumerate(lector, 2):
            if all(valor is None for valor in valores):
                continue
            if any(valor is not None for valor in valores[len(_ENCABEZADO):]):
                errores.append("{} · hoja {} · fila {}: hay columnas adicionales.".format(ruta.name, hoja.title, numero_fila))
                continue
            valores = tuple(valores[:len(_ENCABEZADO)])
            valores += (None,) * (len(_ENCABEZADO) - len(valores))
            datos = dict(zip(_ENCABEZADO, valores))
            contexto = "{} · hoja {} · fila {}".format(ruta.name, hoja.title, numero_fila)
            fila = {"moneda": moneda, "cuenta": cuenta, "archivo": ruta.name, "fila": numero_fila}
            problemas = []
            campos = {
                "operado": lambda: _fecha(datos["Operado"], "Operado"),
                "comprobante": lambda: _texto(datos["Comprobante"], "Comprobante"),
                "numero": lambda: _numero_comprobante(datos["Numero"]),
                "cantidad": lambda: _numero(datos["Cantidad"], "Cantidad", vacio=0.0),
                "especie": lambda: _texto(datos["Especie"], "Especie"),
                "importe": lambda: _numero(datos["Importe"], "Importe"),
                "saldo": lambda: None if _vacio(datos["Saldo"]) else _numero(datos["Saldo"], "Saldo"),
                "referencia": lambda: _texto(datos["Referencia"], "Referencia"),
                "liquida": lambda: _dato_original(datos["Liquida"]),
                "precio": lambda: _dato_original(datos["Precio"]),
            }
            for campo, leer in campos.items():
                try:
                    fila[campo] = leer()
                except ErrorHistorial as error:
                    problemas.extend(error.errores)
            if problemas:
                errores.extend(contexto + ": " + problema for problema in problemas)
            else:
                filas.append(fila)
    except ErrorHistorial as error:
        raise ErrorHistorial([ruta.name + ": " + problema for problema in error.errores]) from None
    except (OSError, ValueError, TypeError, KeyError, IndexError, BadZipFile, InvalidFileException, ParseError):
        raise ErrorHistorial(ruta.name + ": no se puede leer como extracto Excel válido.") from None
    finally:
        if libro is not None:
            libro.close()
    if errores:
        raise ErrorHistorial(errores)
    return filas


def consolidar(filas):
    """Comprueba saldos por archivo y quita las transacciones idénticas."""
    filas = list(filas)
    por_archivo = OrderedDict()
    for fila in filas:
        if not isinstance(fila, dict):
            raise ErrorHistorial("Cada renglón del extracto debe ser un diccionario.")
        por_archivo.setdefault(fila.get("archivo", "extracto"), []).append(fila)
    avisos = []
    for archivo, originales in por_archivo.items():
        anterior = None
        for fila in sorted(originales, key=lambda valor: valor.get("fila", 0)):
            saldo = fila.get("saldo")
            if saldo is not None:
                saldo = _numero(saldo, "Saldo")
                if anterior is not None:
                    importe = _numero(fila.get("importe"), "Importe")
                    diferencia = Decimal(str(saldo)) - Decimal(str(anterior)) - Decimal(str(importe))
                    if abs(diferencia) > Decimal("1"):
                        avisos.append("{} · fila {}: Saldo no coincide con el anterior más el Importe (diferencia {}).".format(
                            archivo, fila.get("fila", "sin dato"), diferencia))
            anterior = saldo
    vistas, unicas = set(), []
    identidad = ("moneda", "cuenta", "operado", "comprobante", "numero", "especie", "importe")
    for fila in filas:
        try:
            clave = tuple(fila[campo] for campo in identidad)
            repetida = clave in vistas
        except (KeyError, TypeError):
            raise ErrorHistorial("El renglón no contiene una identidad válida para consolidar.") from None
        if not repetida:
            vistas.add(clave)
            unicas.append(copy.deepcopy(fila))
    return unicas, avisos


def clasificar(fila, cierres):
    """Clasifica únicamente comprobantes expresamente especificados."""
    comprobante = fila.get("comprobante", "")
    if not isinstance(comprobante, str):
        return "sin_clasificar"
    comprobante = comprobante.strip()
    if comprobante == "RENTA Y AMORTIZ":
        return "cierre" if fila.get("especie") in cierres else "renta"
    if comprobante in ("NOTA DE CREDITO U$S", "NOTA DE DEBITOS U$S"):
        referencia = fila.get("referencia", "")
        return "conversion" if isinstance(referencia, str) and referencia.strip() == "CONV CABLE A ME" else "sin_clasificar"
    return _CLASES.get(comprobante, "sin_clasificar")


def _normalizar_ajuste(movimiento):
    """Valida ajustes sin pedir base, límites de fechas ni cambio obligatorio en USD."""
    if not isinstance(movimiento, dict):
        raise ErrorHistorial("El ajuste debe ser un diccionario.")
    bruto = dict(movimiento)
    moneda = bruto.get("moneda")
    sin_tc = isinstance(moneda, str) and moneda.strip().upper() == "USD" and _vacio(bruto.get("tc"))
    if sin_tc:
        # Solo permite reutilizar las reglas escalares; el dato devuelto sigue sin tc.
        bruto["tc"] = 1.0
    try:
        normalizado = _normalizar(bruto)
    except ErrorMovimiento as error:
        raise ErrorHistorial(error.errores) from None
    if sin_tc:
        normalizado["tc"] = None
    errores = []
    tipo = normalizado["tipo"]
    if tipo not in _TIPOS_AJUSTES:
        errores.append("El historial solo admite compra, venta, renta, dividendo y gasto como ajustes.")
    if tipo in ("compra", "venta", "renta", "dividendo") and not normalizado["ticker"]:
        errores.append(tipo + " requiere ticker.")
    if tipo in ("compra", "venta"):
        if normalizado["cantidad"] <= 0:
            errores.append(tipo + " requiere cantidad positiva.")
    elif normalizado["cantidad"] != 0:
        errores.append(tipo + " no admite cantidad; dejala vacía o en 0.")
    if tipo != "compra" and normalizado["tipo_activo"]:
        errores.append("tipo_activo solo corresponde a una compra.")
    if errores:
        raise ErrorHistorial(errores)
    for campo in ("archivo", "fila"):
        if campo in movimiento:
            normalizado[campo] = movimiento[campo]
    return normalizado


def leer_ajustes(ruta):
    """Lee ajustes con el formato de movimientos, sin exigir tenencias previas."""
    ruta = Path(ruta)
    try:
        entrada = ruta.open("r", encoding="utf-8-sig", newline="")
    except FileNotFoundError:
        return []
    except OSError:
        raise ErrorHistorial(ruta.name + ": no se puede abrir el archivo de ajustes.") from None
    errores, ajustes = [], []
    lector = None
    try:
        with entrada:
            lector = csv.reader(entrada, strict=True)
            if next(lector, None) != list(_AJUSTES):
                raise ErrorHistorial(ruta.name + ": fila 1: encabezado de ajustes inválido.")
            for valores in lector:
                if not valores:
                    continue
                contexto = "{} · fila {}".format(ruta.name, lector.line_num)
                if len(valores) != len(_AJUSTES):
                    errores.append(contexto + ": se requieren nueve columnas.")
                    continue
                try:
                    ajuste = _normalizar_ajuste(dict(zip(_AJUSTES, valores)))
                except ErrorHistorial as error:
                    errores.extend(contexto + ": " + problema for problema in error.errores)
                else:
                    ajuste.update(archivo=ruta.name, fila=lector.line_num)
                    ajustes.append(ajuste)
    except (csv.Error, UnicodeError):
        errores.append("{} · fila {}: no es un CSV UTF-8 válido.".format(ruta.name, lector.line_num if lector else 1))
    if errores:
        raise ErrorHistorial(errores)
    return ajustes


def leer_mep(ruta):
    """Lee cambios históricos positivos; rechaza fechas repetidas ambiguas."""
    ruta = Path(ruta)
    try:
        entrada = ruta.open("r", encoding="utf-8-sig", newline="")
    except FileNotFoundError:
        return {}
    except OSError:
        raise ErrorHistorial(ruta.name + ": no se puede abrir el archivo MEP.") from None
    errores, valores = [], {}
    lector = None
    try:
        with entrada:
            lector = csv.reader(entrada, strict=True)
            if next(lector, None) != ["fecha", "mep"]:
                raise ErrorHistorial(ruta.name + ": fila 1: el encabezado debe ser fecha,mep.")
            for fila in lector:
                if not fila:
                    continue
                contexto = "{} · fila {}".format(ruta.name, lector.line_num)
                if len(fila) != 2:
                    errores.append(contexto + ": se requieren dos columnas.")
                    continue
                try:
                    fecha = _fecha(fila[0], "fecha")
                    numero = _numero(fila[1], "mep")
                    if numero <= 0:
                        raise ErrorHistorial("mep debe ser positivo.")
                    if fecha in valores and valores[fecha] != numero:
                        raise ErrorHistorial("La fecha tiene dos valores MEP distintos.")
                except ErrorHistorial as error:
                    errores.extend(contexto + ": " + problema for problema in error.errores)
                else:
                    valores[fecha] = numero
    except (csv.Error, UnicodeError):
        errores.append("{} · fila {}: no es un CSV UTF-8 válido.".format(ruta.name, lector.line_num if lector else 1))
    if errores:
        raise ErrorHistorial(errores)
    return valores
