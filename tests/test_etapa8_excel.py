"""Descarga en Excel: el archivo se genera con el motor de JavaScript y se lee con openpyxl."""

import copy
import datetime as dt
import io
import json
import re
import subprocess
import tempfile
import unittest
import zipfile
from pathlib import Path
from zoneinfo import ZoneInfo

from openpyxl import load_workbook

from cartera._dashboard_js import SCRIPT
from cartera.calculos import resumen_cartera
from cartera.dashboard import generar_html
from test_extra_dashboard_js import DATOS, MOTOR, PANELES, PRELUDIO, RAIZ

TIPO = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
ENTORNO = r"""
nodos['descargar-excel'] = new Elemento('button', 'descargar-excel');
nodos['excel-estado'] = new Elemento('p', 'excel-estado');
const descargas = [];
const liberadas = [];
let fallarBlob = false;
Elemento.prototype.click = function () { descargas.push({href: this.href, nombre: this.download}); };
globalThis.Blob = class {
  constructor(partes, opciones) {
    if (fallarBlob) throw new Error('sin memoria');
    this.partes = partes;
    this.type = opciones && opciones.type;
  }
};
const blobs = new Map();
globalThis.URL = {
  createObjectURL(blob) { const url = 'blob:prueba-' + blobs.size; blobs.set(url, blob); return url; },
  revokeObjectURL(url) { liberadas.push(url); }
};
if (typeof TextEncoder === 'undefined') {
  globalThis.TextEncoder = class {
    encode(texto) { return Uint8Array.from(unescape(encodeURIComponent(texto)), letra => letra.charCodeAt(0)); }
  };
}
const octetos = blob => {
  const salida = [];
  for (const parte of blob.partes) {
    const vista = parte instanceof ArrayBuffer ? new Uint8Array(parte) :
      new Uint8Array(parte.buffer, parte.byteOffset, parte.byteLength);
    for (const octeto of vista) salida.push(octeto);
  }
  return salida;
};
"""
CLICK = "await nodos['descargar-excel'].listeners.click(); await vaciar();\n"


def base():
    copia = copy.deepcopy(DATOS)
    copia["cliente"] = {"slug": "demo", "nombre": "Nombre Reservado"}
    return copia


def historial():
    vacio = {"ARS": 0.0, "USD": 0.0, "equivalente_ars": 0.0}
    return {
        "total_conocido": 500.5, "realizado_extracto": 400.25, "realizado_estimado": 100.25,
        "ingresos": {"dividendo": {"ARS": 100.0, "USD": 2.0, "equivalente_ars": 3100.0},
                     "compensacion": {"ARS": 50.0, "USD": 0.0, "equivalente_ars": 50.0},
                     "clase_nueva": {"ARS": 7.0, "USD": None, "equivalente_ars": None}},
        "aportes": {"ARS": 5000.0, "USD": 0.0, "equivalente_ars": 5000.0}, "retiros": vacio,
        "realizados": [
            {"ticker": "AAA", "fecha": "2026-07-31", "cantidad": 10.0, "cantidad_sin_lote": 0.0, "importe_ars": 2000.0,
             "costo_ars": 1500.0, "resultado_ars": 500.0, "origen_costo": "mixto", "clase": "venta"},
            {"ticker": "CCC", "fecha": "2026-06-30", "cantidad": 5.0, "cantidad_sin_lote": 5.0, "importe_ars": 900.0,
             "costo_ars": None, "resultado_ars": None, "origen_costo": "incompleto", "clase": "cierre"},
        ],
        "ventas_sin_dato": 1, "valores_sin_dato": 0, "sin_clasificar": [], "cantidad_sin_clasificar": 0, "avisos": [],
    }


def tabla(hoja):
    filas = list(hoja.iter_rows(values_only=True))
    encabezados = filas[0]
    return encabezados, [dict(zip(encabezados, fila)) for fila in filas[1:]]


def resumen(libro):
    return {fila[0]: fila[1] for fila in libro["Resumen"].iter_rows(values_only=True)}


@unittest.skipUnless(MOTOR, "No hay motor JavaScript disponible")
class Base(unittest.TestCase):
    def descargar(self, datos=None, antes="", accion=CLICK):
        inicial = "const DATOS = {};\nconst PANELES = {};\n".format(json.dumps(datos or base()), json.dumps(PANELES))
        cierre = r"""
(async () => {
  await vaciar();
  const antesDelClic = llamadas.length;
  ACCION
  print(JSON.stringify({
    descargas,
    tipos: [...blobs.values()].map(blob => blob.type),
    bytes: blobs.size ? octetos([...blobs.values()][0]) : [],
    estado: nodos['excel-estado'].textContent,
    nuevasConsultas: llamadas.length - antesDelClic
  }));
})().catch(error => print(JSON.stringify({error: String(error), pila: error.stack})));
""".replace("ACCION", accion)
        codigo = inicial + PRELUDIO + ENTORNO + antes + SCRIPT + cierre
        with tempfile.TemporaryDirectory(prefix="excel-js-") as temporal:
            ruta = Path(temporal) / "prueba.js"
            ruta.write_text(codigo, encoding="utf-8")
            proceso = subprocess.run([MOTOR, str(ruta)], cwd=str(RAIZ), capture_output=True, text=True, timeout=30)
        self.assertEqual(proceso.returncode, 0, proceso.stdout + proceso.stderr)
        respuesta = json.loads(proceso.stdout.strip().splitlines()[-1])
        self.assertNotIn("error", respuesta, respuesta)
        return respuesta

    def libro(self, datos=None, antes=""):
        r = self.descargar(datos, antes)
        self.assertEqual(len(r["descargas"]), 1, r["estado"])
        return load_workbook(io.BytesIO(bytes(r["bytes"])))

    def posiciones(self, datos=None, antes=""):
        _, filas = tabla(self.libro(datos, antes)["Posiciones"])
        return {fila["Ticker"]: fila for fila in filas}


class Archivo(Base):
    def test_es_un_xlsx_integro_del_tipo_correcto(self):
        r = self.descargar()
        self.assertEqual(r["tipos"], [TIPO])
        contenido = zipfile.ZipFile(io.BytesIO(bytes(r["bytes"])))
        self.assertIsNone(contenido.testzip())
        for nombre in ("[Content_Types].xml", "_rels/.rels", "xl/workbook.xml", "xl/styles.xml"):
            self.assertIn(nombre, contenido.namelist())

    def test_nombre_con_slug_y_hora_de_argentina(self):
        r = self.descargar()
        self.assertEqual(r["descargas"][0]["nombre"], "cartera-demo-2026-11-04-1800.xlsx")

    def test_el_nombre_del_cliente_no_viaja_en_el_archivo(self):
        r = self.descargar()
        contenido = zipfile.ZipFile(io.BytesIO(bytes(r["bytes"])))
        for nombre in contenido.namelist():
            self.assertNotIn(b"Nombre Reservado", contenido.read(nombre), nombre)
        self.assertNotIn("Reservado", r["descargas"][0]["nombre"])

    def test_no_consulta_la_red_e_informa(self):
        r = self.descargar()
        self.assertEqual(r["nuevasConsultas"], 0)
        self.assertIn("descargado", r["estado"])
        self.assertIn("18:00", r["estado"])

    def test_una_falla_avisa_y_no_rompe_la_pagina(self):
        r = self.descargar(antes="fallarBlob = true;\n", accion=CLICK + "await nodos.actualizar.listeners.click(); await vaciar();\n")
        self.assertIn("No se pudo generar", r["estado"])
        self.assertEqual(r["descargas"], [])

    def test_primera_fila_en_negrita(self):
        libro = self.libro()
        self.assertTrue(libro["Posiciones"]["A1"].font.bold)


class Hojas(Base):
    def test_sin_historial_solo_dos_hojas(self):
        self.assertEqual(self.libro().sheetnames, ["Resumen", "Posiciones"])

    def test_encabezados_de_posiciones(self):
        encabezados, _ = tabla(self.libro()["Posiciones"])
        self.assertEqual(list(encabezados), [
            "Ticker", "Especie", "Tipo", "Cantidad", "Último", "Valuación ARS", "Peso", "Variación del día", "Costo ARS",
            "Origen del costo", "Resultado ARS", "Resultado %", "Take profit", "Stop loss", "Vencimiento",
            "Estado del precio", "Hora de consulta"])

    def test_usa_los_precios_en_vivo_como_numeros(self):
        filas = self.posiciones()
        aaa = filas["AAA"]
        self.assertEqual(aaa["Último"], 1300)
        self.assertEqual(aaa["Valuación ARS"], 130000)
        self.assertAlmostEqual(aaa["Peso"], 130000 / 1730000)
        self.assertAlmostEqual(aaa["Variación del día"], 0.015)
        self.assertEqual(aaa["Costo ARS"], 100000)
        self.assertEqual(aaa["Origen del costo"], "extracto")
        self.assertEqual(aaa["Resultado ARS"], 30000)
        self.assertAlmostEqual(aaa["Resultado %"], 0.3)
        self.assertEqual(aaa["Take profit"], 1500)
        self.assertIsNone(aaa["Stop loss"])
        self.assertEqual(aaa["Estado del precio"], "En vivo")
        self.assertEqual(aaa["Hora de consulta"], "04/11/2026 18:00")

    def test_bono_cotiza_cada_cien(self):
        self.assertEqual(self.posiciones()["BOND1"]["Valuación ARS"], 1600000)

    def test_faltantes_con_palabras_y_nunca_cero(self):
        filas = self.posiciones()
        bono, sin_precio = filas["BOND1"], filas["BBB"]
        self.assertEqual(bono["Costo ARS"], "falta estimar")
        self.assertEqual(bono["Origen del costo"], "falta estimar")
        self.assertEqual(bono["Resultado ARS"], "falta estimar")
        self.assertEqual(sin_precio["Último"], "sin dato")
        self.assertEqual(sin_precio["Valuación ARS"], "sin dato")
        self.assertEqual(sin_precio["Peso"], "sin dato")
        self.assertEqual(sin_precio["Resultado ARS"], "sin dato")
        self.assertEqual(sin_precio["Origen del costo"], "estimado")
        self.assertEqual(sin_precio["Estado del precio"], "Sin dato")

    def test_formatos_de_porcentaje_y_fecha(self):
        libro = self.libro()
        hoja = libro["Posiciones"]
        columnas = {celda.value: celda.column for celda in hoja[1]}
        fila = next(fila for fila in range(2, hoja.max_row + 1) if hoja.cell(fila, 1).value == "BOND1")
        self.assertIn("%", hoja.cell(fila, columnas["Peso"]).number_format)
        vencimiento = hoja.cell(fila, columnas["Vencimiento"])
        self.assertEqual(vencimiento.value, dt.datetime(2026, 11, 22))
        self.assertEqual(vencimiento.number_format.lower(), "dd/mm/yyyy")

    def test_resumen(self):
        datos = resumen(self.libro())
        self.assertEqual(datos["Cliente"], "demo")
        self.assertEqual(datos["Generado"], "04/11/2026 18:00")
        self.assertEqual(datos["Última consulta"], "04/11/2026 18:00")
        self.assertEqual(datos["Dólar MEP"], 1600)
        self.assertEqual(datos["Valuación conocida ARS"], 1730000)
        self.assertAlmostEqual(datos["Valuación conocida USD"], 1081.25)
        self.assertEqual(datos["Posiciones sin precio"], 1)
        self.assertEqual(datos["Posiciones sin confirmar en vivo"], 1)
        self.assertEqual(datos["Resultado desde la compra ARS"], 30000)
        self.assertNotIn("Total conocido realizado ARS", datos)

    def test_sin_red_informa_el_ultimo_dato(self):
        filas = self.posiciones(antes="fallar = true;\n")
        self.assertEqual(filas["AAA"]["Último"], 1200)
        self.assertEqual(filas["AAA"]["Estado del precio"], "Último dato")

    def test_vista_estatica_usa_lo_embebido(self):
        datos = base()
        datos["actualizacion_habilitada"] = False
        self.assertEqual(self.posiciones(datos)["AAA"]["Valuación ARS"], 120000)


class Textos(Base):
    def test_textos_peligrosos_quedan_como_texto(self):
        datos = base()
        datos["posiciones"][0]["especie"] = "=1+1"
        datos["posiciones"][1]["especie"] = 'Año & <Ñandú> "x"'
        datos["posiciones"][2]["especie"] = "con\x07control"
        libro = self.libro(datos)
        hoja = libro["Posiciones"]
        self.assertEqual(hoja["B2"].value, "=1+1")
        self.assertNotEqual(hoja["B2"].data_type, "f")
        self.assertEqual(hoja["B3"].value, 'Año & <Ñandú> "x"')
        self.assertEqual(hoja["B4"].value, "concontrol")


class ConHistorial(Base):
    def datos(self):
        copia = base()
        copia["historial"] = historial()
        return copia

    def test_agrega_las_hojas_y_los_totales(self):
        libro = self.libro(self.datos())
        self.assertEqual(libro.sheetnames, ["Resumen", "Posiciones", "Ventas", "Ingresos"])
        datos = resumen(libro)
        self.assertEqual(datos["Total conocido realizado ARS"], 500.5)
        self.assertEqual(datos["Realizado de extracto ARS"], 400.25)
        self.assertEqual(datos["Realizado con estimaciones ARS"], 100.25)

    def test_ventas_en_orden_y_con_faltantes(self):
        encabezados, filas = tabla(self.libro(self.datos())["Ventas"])
        self.assertEqual(list(encabezados), ["Ticker", "Fecha", "Clase", "Cantidad", "Sin lote", "Importe ARS", "Costo ARS",
                                             "Origen del costo", "Resultado ARS"])
        self.assertEqual([fila["Ticker"] for fila in filas], ["AAA", "CCC"])
        self.assertEqual(filas[0]["Fecha"], dt.datetime(2026, 7, 31))
        self.assertEqual(filas[0]["Resultado ARS"], 500)
        self.assertEqual(filas[0]["Origen del costo"], "incluye estimado")
        self.assertEqual(filas[1]["Costo ARS"], "sin dato")
        self.assertEqual(filas[1]["Resultado ARS"], "sin dato")

    def test_ingresos_con_etiquetas_y_sin_omitir_clases(self):
        encabezados, filas = tabla(self.libro(self.datos())["Ingresos"])
        self.assertEqual(list(encabezados), ["Concepto", "ARS", "USD", "Equivalente ARS"])
        conceptos = {fila["Concepto"]: fila for fila in filas}
        self.assertEqual(conceptos["Dividendos"]["USD"], 2)
        self.assertEqual(conceptos["Compensaciones por error operativo"]["ARS"], 50)
        self.assertEqual(conceptos["clase_nueva"]["USD"], "sin dato")
        self.assertEqual(conceptos["Aportes (no son ganancia)"]["ARS"], 5000)
        self.assertEqual(conceptos["Retiros (no son ganancia)"]["ARS"], 0)


class Pagina(unittest.TestCase):
    def setUp(self):
        hora = dt.datetime(2026, 11, 5, 12, tzinfo=ZoneInfo("America/Argentina/Buenos_Aires"))
        self.html = generar_html({"slug": "demo"}, [], resumen_cartera([]), {}, {}, {}, None, {}, hora, posiciones=[])

    def test_tiene_el_boton_y_el_estado(self):
        self.assertRegex(self.html, r'<button id="descargar-excel" type="button"[^>]*>Descargar Excel</button>')
        self.assertIn('id="excel-estado"', self.html)

    def test_la_politica_de_seguridad_no_cambia(self):
        self.assertIn("default-src 'none'; style-src 'unsafe-inline'; script-src 'unsafe-inline'; "
                      "connect-src https://data912.com; img-src data:", self.html)
        self.assertEqual(re.findall(r"<script[^>]+src=", self.html), [])


if __name__ == "__main__":
    unittest.main()
