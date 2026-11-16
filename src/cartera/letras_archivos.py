"""Precios manuales de renta fija, separados de los costos y de la base importada."""

import fcntl
import json
import os
import tempfile
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from .almacenamiento import _ruta_cartera, cargar_cartera
from .dia_cero import _leer_dia_cero
from .letras import (
    ErrorLetra, precio_en_moneda_flujo, referencias_compras, referencias_flujo, validar_compras,
    validar_dato_compra,
)
from .movimientos import leer_movimientos, validar_movimientos


def _ruta(carpeta, nombre):
    ruta = carpeta / nombre
    if ruta.is_symlink() or ruta.resolve().parent != carpeta.resolve():
        raise ErrorLetra(nombre + " debe permanecer en la carpeta del cliente y no ser un enlace.")
    if ruta.exists() and not ruta.is_file():
        raise ErrorLetra(nombre + " debe ser un archivo.")
    return ruta


def _objeto(pares):
    objeto = {}
    for clave, valor in pares:
        if clave in objeto:
            raise ErrorLetra("Clave JSON repetida: " + clave)
        objeto[clave] = valor
    return objeto


def _constante(texto):
    raise ErrorLetra("Número no finito: " + texto)


def _compras_desde_bytes(ruta, bruto, bonos):
    if bruto is None:
        return {"esquema_version": 1, "compras": []}
    try:
        datos = json.loads(bruto.decode("utf-8"), object_pairs_hook=_objeto, parse_constant=_constante)
        return validar_compras(datos, bonos=bonos)
    except (ValueError, UnicodeError) as error:
        raise ErrorLetra(ruta.name + ": " + str(error)) from None


def leer_compras(ruta, *, bonos=False):
    ruta = Path(ruta)
    _ruta(ruta.parent, ruta.name)
    bruto = ruta.read_bytes() if ruta.exists() else None
    return _compras_desde_bytes(ruta, bruto, bonos)


def leer_compras_bonos(ruta):
    return leer_compras(ruta, bonos=True)


def guardar_compra(ruta, registro, anteriores=None, *, bonos=False):
    """Publica un archivo completo con el directorio bloqueado por el llamador."""
    ruta = Path(ruta)
    _ruta(ruta.parent, ruta.name)
    previo = ruta.read_bytes() if ruta.exists() else None
    contenido = _compras_desde_bytes(ruta, previo, bonos)
    if anteriores is not None and validar_compras(anteriores, bonos=bonos) != contenido:
        raise ErrorLetra(ruta.name + " cambió durante la carga. Volvé a intentar.")
    compras = [registro if dato["referencia"] == registro["referencia"] else dato for dato in contenido["compras"]]
    if not any(dato["referencia"] == registro["referencia"] for dato in contenido["compras"]):
        compras.append(registro)
    nuevo = validar_compras({"esquema_version": 1, "compras": compras}, bonos=bonos)
    if nuevo == contenido:
        return False
    serializado = (json.dumps(nuevo, ensure_ascii=False, indent=2, allow_nan=False) + "\n").encode("utf-8")
    temporal = None
    try:
        with tempfile.NamedTemporaryFile(mode="wb", dir=ruta.parent, prefix=".compras-", suffix=".tmp", delete=False) as salida:
            temporal = Path(salida.name)
            os.fchmod(salida.fileno(), 0o600)
            salida.write(serializado)
            salida.flush()
            os.fsync(salida.fileno())
        _ruta(ruta.parent, ruta.name)
        if (ruta.read_bytes() if ruta.exists() else None) != previo:
            raise ErrorLetra(ruta.name + " cambió durante la carga. Volvé a intentar.")
        if previo is None:
            os.link(str(temporal), str(ruta))
        else:
            os.replace(str(temporal), str(ruta))
        return True
    finally:
        if temporal is not None:
            temporal.unlink(missing_ok=True)


def _listar_compras(referencias, compras, nombre_plural):
    por_ref = {dato["referencia"]: dato for dato in compras["compras"]}
    encontradas = set()
    for compra in referencias:
        referencia = compra["referencia"]
        encontradas.add(referencia)
        dato = por_ref.get(referencia)
        precio = "sin dato"
        if dato and dato["huella"] == compra["huella"]:
            precio = "{} {} · liquidación {}".format(dato["precio"], dato["moneda"], dato["fecha_liquidacion"])
            if "tc" in dato:
                precio += " · TC {} ARS/USD".format(dato["tc"])
        elif dato:
            precio = "sin dato · fuente modificada: volvé a cargar el precio"
        print("{} · {} · VN remanentes {} · compra {} · precio {}".format(
            referencia, compra["ticker"], compra["cantidad_restante"], compra["fecha_compra"] or "sin dato", precio))
    for referencia in por_ref:
        if referencia not in encontradas:
            print("ADVERTENCIA: {} no corresponde a una compra de {}. Revisá el precio guardado.".format(
                referencia, nombre_plural))
    if not referencias:
        print("No hay compras de {} en la base ni en los movimientos.".format(nombre_plural))


def _instrumentos_crudos(bruto):
    if bruto is None:
        return {}
    try:
        instrumentos = json.loads(bruto.decode("utf-8"), object_pairs_hook=_objeto, parse_constant=_constante)
    except (AttributeError, UnicodeError, ValueError) as error:
        raise ErrorLetra("instrumentos.json: " + str(error)) from None
    return instrumentos if isinstance(instrumentos, dict) else {}


def _configuracion_instrumento(bruto, ticker):
    if bruto is None:
        return {}
    try:
        instrumentos = json.loads(bruto.decode("utf-8"), object_pairs_hook=_objeto, parse_constant=_constante)
        configuracion = instrumentos.get(ticker, {})
        if not isinstance(configuracion, dict):
            raise ErrorLetra("{} debe ser un objeto.".format(ticker))
        return configuracion
    except (AttributeError, UnicodeError, ValueError) as error:
        raise ErrorLetra("instrumentos.json: " + str(error)) from None


def _validar_contrato_bono(datos, configuracion, ticker, registro):
    from .flujo_fondos import cronograma_iamc
    from .iamc import leer_cierres

    vinculo = configuracion.get("iamc")
    if not isinstance(vinculo, dict):
        raise ErrorLetra("{} sin vincular con IAMC en instrumentos.json.".format(ticker))
    simbolo, grupo = vinculo.get("ticker"), vinculo.get("grupo")
    if not isinstance(simbolo, str) or not simbolo.strip() or grupo not in ("tp", "on"):
        raise ErrorLetra("Vínculo IAMC inválido para {}. Indicá ticker y grupo tp u on.".format(ticker))
    cierres = leer_cierres(datos)
    if not cierres:
        raise ErrorLetra("Falta un cierre guardado de IAMC para validar la compra.")
    cierre = cierres[-1]
    cronograma = cronograma_iamc(cierre, simbolo, grupo)
    if cronograma is None:
        raise ErrorLetra("{} sin cronograma en IAMC al {}.".format(ticker, cierre["fecha_cierre"]))
    indexado = not cronograma.habilitado and isinstance(vinculo.get("indice"), dict) \
        and cronograma.familia in ("cer", "dl", "var", "capv")
    if not cronograma.habilitado and not indexado:
        raise ErrorLetra("{} con proyección pendiente: falta el bloque indice en instrumentos.json.".format(ticker))
    if indexado:
        # Los títulos ajustables se validan con las fechas crudas de IAMC: el precio no
        # depende de la proyección, y sus pagos se cobran en pesos.
        fila = next(f for f in cierre["calculadora_bonos"]["ins"] if f.get("tk") == simbolo and f.get("g") == grupo)
        dias = [registro_iamc[0] for registro_iamc in fila.get("f") or ()]
        if not dias:
            raise ErrorLetra("El cronograma de {} no informa el último pago.".format(ticker))
        ultimo, moneda = cronograma.liquidacion + timedelta(days=int(max(dias))), "ARS"
    else:
        if not cronograma.pagos:
            raise ErrorLetra("El cronograma de {} no informa el último pago.".format(ticker))
        ultimo, moneda = cronograma.pagos[-1].fecha, cronograma.moneda
    if date.fromisoformat(registro["fecha_liquidacion"]) >= ultimo:
        raise ErrorLetra("La liquidación debe ser anterior al último pago de IAMC.")
    precio_en_moneda_flujo(registro, moneda)


def _ejecutar_compras(opciones, datos, bonos):
    carpeta = _ruta_cartera(datos, opciones.cliente).parent
    archivo = "compras_bonos.json" if bonos else "compras_letras.json"
    listado = "bonos" if bonos else "letras"
    nombre_plural = "bonos u ON" if bonos else "letras"
    tipos = ("bono", "on") if bonos else ("letra",)
    try:
        descriptor = os.open(str(carpeta), os.O_RDONLY)
    except FileNotFoundError:
        raise ErrorLetra("No existe una cartera importada para {}.".format(opciones.cliente)) from None
    try:
        fcntl.flock(descriptor, fcntl.LOCK_EX)
        fuentes = [_ruta(carpeta, nombre) for nombre in ("cartera.json", "movimientos.csv", "dia_cero.json", "instrumentos.json")]
        previos = {ruta: ruta.read_bytes() if ruta.exists() else None for ruta in fuentes}
        base, _ = cargar_cartera(datos, opciones.cliente)
        movimientos = leer_movimientos(fuentes[1])
        referencia_cero = _leer_dia_cero(fuentes[2]) if fuentes[2].exists() else None
        hoy = datetime.now(ZoneInfo("America/Argentina/Buenos_Aires")).date()
        validar_movimientos(base, movimientos, date.fromisoformat(referencia_cero["fecha"]) if referencia_cero else None, hoy)
        if bonos:
            # Incluye las letras CER o dólar linked vinculadas a IAMC con su índice.
            instrumentos = _instrumentos_crudos(previos[fuentes[3]])
            referencias = referencias_flujo(base, movimientos, instrumentos)
        else:
            referencias = referencias_compras(base, movimientos, tipos=tipos)
        ruta = _ruta(carpeta, archivo)
        compras = leer_compras(ruta, bonos=bonos)
        if opciones.comando == listado:
            _listar_compras(referencias, compras, nombre_plural)
            return 0
        referencia = next((dato for dato in referencias if dato["referencia"] == opciones.referencia), None)
        if referencia is None:
            raise ErrorLetra("La referencia no corresponde a una compra de {}. Consultá el comando {}.".format(
                nombre_plural, listado))
        registro = {"referencia": referencia["referencia"], "huella": referencia["huella"],
                    "precio": opciones.precio, "moneda": opciones.moneda, "fecha_liquidacion": opciones.liquidacion}
        if bonos and opciones.tc is not None:
            registro["tc"] = opciones.tc
        registro = validar_dato_compra(registro, referencias, hoy, bonos=bonos)
        ticker = referencia["ticker"]
        configuracion = _configuracion_instrumento(previos[fuentes[3]], ticker)
        if bonos:
            _validar_contrato_bono(datos, configuracion, ticker, registro)
        elif configuracion.get("vencimiento") is not None:
            try:
                vencimiento = date.fromisoformat(configuracion["vencimiento"])
            except (TypeError, ValueError):
                raise ErrorLetra("instrumentos.json: vencimiento inválido para {}.".format(ticker)) from None
            if date.fromisoformat(registro["fecha_liquidacion"]) >= vencimiento:
                raise ErrorLetra("La liquidación debe ser anterior al vencimiento.")
        if any((fuente.read_bytes() if fuente.exists() else None) != previo for fuente, previo in previos.items()):
            raise ErrorLetra("La base o sus movimientos cambiaron. Volvé a intentar.")
        cambio = guardar_compra(ruta, registro, compras, bonos=bonos)
        print("Precio de compra guardado. Generá nuevamente el dashboard." if cambio else "Sin cambios en el precio de compra.")
        return 0
    finally:
        os.close(descriptor)


def ejecutar_letras(opciones, datos):
    return _ejecutar_compras(opciones, datos, bonos=False)


def ejecutar_bonos(opciones, datos):
    return _ejecutar_compras(opciones, datos, bonos=True)
