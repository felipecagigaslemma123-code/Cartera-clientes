"""Pruebas de JavaScript con DOM y red ficticios, sin dependencias instaladas."""

import copy
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

from cartera._dashboard_js import SCRIPT


JSC = "/System/Library/Frameworks/JavaScriptCore.framework/Versions/A/Helpers/jsc"
MOTOR = JSC if os.path.isfile(JSC) and os.access(JSC, os.X_OK) else shutil.which("node")
RAIZ = Path(__file__).resolve().parents[1]

DATOS = {
    "generado_en": "2026-11-04T12:00:00-03:00", "actualizacion_habilitada": True,
    "posiciones": [
        {"ticker": "AAA", "especie": "Demo A", "tipo": "cedear", "cantidad": 100, "cotiza_cada": 1,
         "endpoint": "arg_cedears", "costo": 100000, "estado_costo": "extracto", "ultimo": 1200,
         "bid": 1199, "ask": 1201, "pct_dia": 1.5, "estado": "vivo", "consultado_en": "2026-11-04T12:00:00-03:00",
         "precio_dia_cero": 1000, "take_profit": 1500, "stop_loss": None, "vencimiento": None},
        {"ticker": "BOND1", "especie": "Bono Demo", "tipo": "bono", "cantidad": 1000, "cotiza_cada": 100,
         "endpoint": "arg_bonds", "costo": None, "estado_costo": "incompleto", "ultimo": 160000,
         "bid": 159000, "ask": 161000, "pct_dia": 1.5, "estado": "vivo", "consultado_en": "2026-11-04T12:00:00-03:00",
         "precio_dia_cero": 150000, "take_profit": None, "stop_loss": 150000, "vencimiento": "2026-11-22"},
        {"ticker": "BBB", "especie": "Demo sin precio", "tipo": "cedear", "cantidad": 50, "cotiza_cada": 1,
         "endpoint": "arg_cedears", "costo": 50000, "estado_costo": "estimado", "ultimo": None,
         "bid": None, "ask": None, "pct_dia": None, "estado": "sin_dato", "consultado_en": "2026-11-04T12:00:00-03:00",
         "precio_dia_cero": 1000, "take_profit": None, "stop_loss": None, "vencimiento": "2026-11-01"},
    ],
    "dia_cero": {"fecha": "2026-11-04", "mep": 1500},
    "mep": {"ultimo": 1500, "estado": "vivo", "consultado_en": "2026-11-04T12:00:00-03:00"},
    "efectivo": {"ARS": 999999999, "USD": 999999999},
}

PANELES = {
    "arg_cedears": [{"symbol": "AAA", "c": 1300, "px_bid": 1299, "px_ask": 1301, "pct_change": 1.5}],
    "arg_bonds": [{"symbol": "BOND1", "c": 160000, "px_bid": 159000, "px_ask": 161000, "pct_change": 2}],
    "mep": [{"ticker": "AL30", "mark": 1600}],
}

PRELUDIO = r"""
if (typeof print === 'undefined') globalThis.print = valor => console.log(valor);
const relojReal = Date;
let instante = relojReal.parse('2026-11-04T18:00:00-03:00');
globalThis.Date = class extends relojReal {
  constructor(...argumentos) { super(...(argumentos.length ? argumentos : [instante])); }
  static now() { return instante; }
};
class Elemento {
  constructor(etiqueta = '', id = '') { this.tagName = etiqueta; this.id = id; this.children = []; this.dataset = {}; this.listeners = {}; this.hidden = false; this.disabled = false; this._texto = ''; }
  set textContent(valor) { this._texto = String(valor); this.children = []; }
  get textContent() { return this._texto + this.children.map(hijo => hijo.textContent).join(' '); }
  appendChild(hijo) { this.children.push(hijo); return hijo; }
  replaceChildren(...hijos) { this._texto = ''; this.children = hijos; }
  addEventListener(tipo, funcion) { this.listeners[tipo] = funcion; }
}
const nodos = {};
for (const id of ['datos-cartera', 'ultima-consulta', 'aviso-datos', 'aviso-dia-distinto', 'aviso-parcial', 'posiciones-body', 'totales-body', 'resultado-compra', 'variacion-precios', 'mep-dato', 'vencimientos-lista', 'actualizar']) nodos[id] = new Elemento('', id);
nodos['datos-cartera'].textContent = JSON.stringify(DATOS);
const original = nodos['datos-cartera'].textContent;
globalThis.document = {getElementById: id => nodos[id] || null, createElement: etiqueta => new Elemento(etiqueta)};
let secuencia = 0;
const temporizadores = new Map();
const intervalos = [];
globalThis.setTimeout = (funcion, demora) => { const id = ++secuencia; temporizadores.set(id, {funcion, demora}); return id; };
globalThis.clearTimeout = id => temporizadores.delete(id);
globalThis.setInterval = (funcion, demora) => { intervalos.push({funcion, demora}); return ++secuencia; };
globalThis.AbortController = class {
  constructor() { this.signal = {aborted: false, listeners: [], addEventListener(tipo, funcion) { this.listeners.push(funcion); }}; }
  abort() { this.signal.aborted = true; for (const funcion of this.signal.listeners) funcion(); }
};
let fallar = false;
let retener = false;
const resoluciones = [];
const llamadas = [];
globalThis.fetch = (url, opciones) => {
  llamadas.push({url, opciones});
  if (fallar) return Promise.reject(new Error('sin red'));
  if (retener) return new Promise((resolver, rechazar) => {
    resoluciones.push(() => resolver({ok: true, json: async () => PANELES[url.split('/').pop()]}));
    opciones.signal.addEventListener('abort', () => rechazar(new Error('timeout')));
  });
  return Promise.resolve({ok: true, json: async () => PANELES[url.split('/').pop()]});
};
const vaciar = async () => { for (let vuelta = 0; vuelta < 40; vuelta++) await Promise.resolve(); };
const filas = id => nodos[id].children.map(fila => fila.children.map(celda => celda.textContent));
"""


@unittest.skipUnless(MOTOR, "No hay JavaScriptCore ni Node disponibles para ejecutar la página simulada")
class JavaScriptDashboard(unittest.TestCase):
    def ejecutar(self, accion="", datos=None, paneles=None, antes=""):
        inicial = "const DATOS = " + json.dumps(datos if datos is not None else DATOS, ensure_ascii=False) + ";\n"
        inicial += "const PANELES = " + json.dumps(paneles if paneles is not None else PANELES, ensure_ascii=False) + ";\n"
        cierre = r"""
(async () => {
  await vaciar();
  ACCION
  print(JSON.stringify({
    llamadas: llamadas.map(llamada => llamada.url),
    filas: filas('posiciones-body'), totales: filas('totales-body'),
    compra: nodos['resultado-compra'].textContent, variacion: nodos['variacion-precios'].textContent,
    mep: nodos['mep-dato'].textContent, avisos: nodos['aviso-datos'].textContent,
    parcial: nodos['aviso-parcial'].textContent, distinto: nodos['aviso-dia-distinto'].textContent,
    vencimientos: nodos['vencimientos-lista'].textContent,
    original: original === nodos['datos-cartera'].textContent,
    botonDeshabilitado: nodos.actualizar.disabled,
    intervalos: intervalos.map(intervalo => intervalo.demora)
  }));
})().catch(error => { print(JSON.stringify({error: String(error), pila: error.stack})); });
""".replace("ACCION", accion)
        codigo = inicial + PRELUDIO + antes + SCRIPT + cierre
        with tempfile.TemporaryDirectory(prefix="dashboard-js-") as temporal:
            ruta = Path(temporal) / "prueba.js"
            ruta.write_text(codigo, encoding="utf-8")
            proceso = subprocess.run([MOTOR, str(ruta)], cwd=str(RAIZ), text=True, capture_output=True, timeout=15)
        self.assertEqual(proceso.returncode, 0, proceso.stdout + proceso.stderr)
        respuesta = json.loads(proceso.stdout.strip().splitlines()[-1])
        self.assertNotIn("error", respuesta, respuesta)
        return respuesta

    def test_actualiza_por_panel_y_recalcula_sin_sumar_efectivo(self):
        r = self.ejecutar()
        self.assertEqual(sorted(r["llamadas"]), ["https://data912.com/live/arg_bonds", "https://data912.com/live/arg_cedears", "https://data912.com/live/mep"])
        filas = {fila[0]: fila for fila in r["filas"]}
        self.assertIn("1.600.000,00", filas["BOND1"][5])
        self.assertIn("30.000,00", filas["AAA"][10])
        self.assertEqual(filas["AAA"][7], "1,50%")
        self.assertIn("falta estimar", filas["BOND1"][10])
        self.assertIn("-5,66%", filas["BOND1"][13])
        self.assertIn("sin dato", filas["BBB"][5])
        self.assertEqual(r["totales"][-1][1], "$ 1.730.000,00")
        self.assertIn("14,58", r["variacion"])
        self.assertIn("1 de 3", r["compra"])
        self.assertTrue(r["original"])
        self.assertEqual(r["intervalos"], [60000])

    def test_caida_posterior_conserva_precios_y_hora_y_avisa(self):
        r = self.ejecutar("fallar = true; instante += 60000; await nodos.actualizar.listeners.click(); await vaciar();")
        filas = {fila[0]: fila for fila in r["filas"]}
        self.assertEqual(r["totales"][-1][1], "$ 1.730.000,00")
        self.assertIn("Último dato", filas["AAA"][14])
        self.assertIn("ninguna posición", r["avisos"])
        self.assertIn("Último dato", r["mep"])
        self.assertFalse(r["botonDeshabilitado"])

    def test_falla_de_una_especie_no_borra_la_cotizacion_de_otra(self):
        paneles = copy.deepcopy(PANELES)
        paneles["arg_bonds"] = {"Error": "sin datos"}
        paneles["arg_cedears"].append({"symbol": "BBB", "c": True})
        r = self.ejecutar(paneles=paneles)
        filas = {fila[0]: fila for fila in r["filas"]}
        self.assertIn("En vivo", filas["AAA"][14])
        self.assertIn("Último dato", filas["BOND1"][14])
        self.assertIn("Sin dato", filas["BBB"][14])
        self.assertIn("1.600.000,00", filas["BOND1"][5])
        self.assertIn("2 de 3", r["parcial"])

    def test_no_solapa_rondas_y_corta_consultas_a_quince_segundos(self):
        accion = """
if (llamadas.length !== 3) throw new Error('Se esperaba una ronda inicial');
await nodos.actualizar.listeners.click();
intervalos[0].funcion();
if (llamadas.length !== 3) throw new Error('Se solaparon rondas');
if (![...temporizadores.values()].every(t => t.demora === 15000)) throw new Error('Timeout distinto de 15 segundos');
for (const temporizador of [...temporizadores.values()]) temporizador.funcion();
await vaciar();
"""
        r = self.ejecutar(accion, antes="retener = true;\n")
        self.assertEqual(len(r["llamadas"]), 3)
        self.assertIn("ninguna posición", r["avisos"])
        self.assertFalse(r["botonDeshabilitado"])

    def test_sin_posiciones_no_consulta_y_preserva_vista_estatica(self):
        datos = copy.deepcopy(DATOS)
        datos["actualizacion_habilitada"] = False
        r = self.ejecutar(datos=datos, antes="nodos['posiciones-body'].textContent = 'vista estática original';\n")
        self.assertEqual(r["llamadas"], [])
        self.assertTrue(r["botonDeshabilitado"])
        self.assertIn("Vista estática", r["avisos"])
        self.assertTrue(r["original"])

    def test_hora_faltante_no_inventa_la_fecha_del_inicio_de_unix(self):
        datos = copy.deepcopy(DATOS)
        datos["posiciones"][0]["consultado_en"] = None
        r = self.ejecutar(datos=datos, antes="retener = true;\n")
        aaa = next(fila for fila in r["filas"] if fila[0] == "AAA")
        self.assertIn("consulta sin dato", aaa[14])
        self.assertNotIn("1970", aaa[14])

    def test_vencimientos_y_aviso_de_archivo_de_otro_dia(self):
        datos = copy.deepcopy(DATOS)
        datos["generado_en"] = "2026-11-03T12:00:00-03:00"
        r = self.ejecutar(datos=datos)
        self.assertIn("otro día", r["distinto"])
        self.assertIn("vencida hace 3 días", r["vencimientos"])
        self.assertIn("faltan 18 días", r["vencimientos"])


if __name__ == "__main__":
    unittest.main()
