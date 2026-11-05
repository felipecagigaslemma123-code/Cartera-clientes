"""Bordes de alertas con DOM, reloj, sonido y notificaciones ficticios."""

import json
import subprocess
import tempfile
import unittest
from pathlib import Path

from cartera._dashboard_js import SCRIPT
from test_extra_dashboard_js import MOTOR, PRELUDIO, RAIZ
from test_etapa7_alertas import NODOS, RONDA, datos, paneles


AVISOS_FICTICIOS = r"""
const enviadas = [];
let pedidos = 0;
globalThis.Notification = class {
  constructor(titulo, opciones) { enviadas.push({titulo, cuerpo: opciones.body}); }
};
Notification.permission = 'default';
Notification.requestPermission = async () => { pedidos += 1; Notification.permission = 'granted'; return 'granted'; };
let tonos = 0;
let contextos = 0;
let reanudaciones = 0;
globalThis.AudioContext = class {
  constructor() { contextos += 1; this.state = 'suspended'; this.currentTime = 0; this.destination = {}; }
  resume() { reanudaciones += 1; this.state = 'running'; return Promise.resolve(); }
  createOscillator() {
    return {frequency: {value: 0, setValueAtTime() {}}, connect() {}, start() { tonos += 1; }, stop() {}, disconnect() {}};
  }
  createGain() {
    return {gain: {value: 0, setValueAtTime() {}, linearRampToValueAtTime() {}, exponentialRampToValueAtTime() {}, setTargetAtTime() {}}, connect() {}, disconnect() {}};
  }
};
globalThis.window = globalThis;
"""


def dos_especies():
    base = datos(take_profit=1200)
    segunda = dict(base["posiciones"][0], ticker="BBB", especie="Segunda ficticia", take_profit=None, stop_loss=1400)
    base["posiciones"].append(segunda)
    tablas = paneles()
    tablas["arg_cedears"].append({"symbol": "BBB", "c": 1300, "px_bid": 1299})
    return base, tablas


@unittest.skipUnless(MOTOR, "No hay motor JavaScript para simular el dashboard")
class AlertasNavegadorAdicionales(unittest.TestCase):
    def ejecutar(self, accion="", base=None, tablas=None, antes="", fecha="2026-11-04T12:00:00-03:00"):
        inicial = "const DATOS = " + json.dumps(datos() if base is None else base) + ";\n"
        inicial += "const PANELES = " + json.dumps(paneles() if tablas is None else tablas) + ";\n"
        reloj = "instante = relojReal.parse(" + json.dumps(fecha) + ");\n"
        cierre = r"""
(async () => {
  await vaciar();
  ACCION
  print(JSON.stringify({
    estado: nodos['alertas-estado'].textContent,
    lista: nodos['alertas-lista'].children.map(hijo => hijo.textContent),
    avisos: nodos['avisos-estado'].textContent,
    datosEstado: nodos['aviso-datos'].textContent,
    titulo: document.title, enviadas, pedidos, tonos, contextos, reanudaciones,
    llamadas: llamadas.length, extra: globalThis.extra || {},
    intervalos: intervalos.map(intervalo => intervalo.demora)
  }));
})().catch(error => print(JSON.stringify({error: String(error), pila: error.stack})));
""".replace("ACCION", accion)
        codigo = inicial + PRELUDIO + reloj + NODOS + AVISOS_FICTICIOS + antes + SCRIPT + cierre
        with tempfile.TemporaryDirectory(prefix="alertas-extra-js-") as temporal:
            ruta = Path(temporal) / "prueba.js"
            ruta.write_text(codigo, encoding="utf-8")
            proceso = subprocess.run([MOTOR, str(ruta)], cwd=str(RAIZ), capture_output=True, text=True, timeout=15)
        self.assertEqual(proceso.returncode, 0, proceso.stdout + proceso.stderr)
        respuesta = json.loads(proceso.stdout.strip().splitlines()[-1])
        self.assertNotIn("error", respuesta, respuesta)
        return respuesta

    def test_rearme_stop_loss_exige_mas_del_uno_por_ciento(self):
        accion = "PANELES.arg_cedears[0].px_bid = 1414; " + RONDA
        accion += "PANELES.arg_cedears[0].px_bid = 1300; " + RONDA
        accion += "globalThis.extra = {enLimite: nodos['alertas-lista'].children.length};"
        accion += "PANELES.arg_cedears[0].px_bid = 1414.01; " + RONDA
        accion += "PANELES.arg_cedears[0].px_bid = 1300; " + RONDA
        r = self.ejecutar(accion, base=datos(take_profit=None, stop_loss=1400))
        self.assertEqual(r["extra"]["enLimite"], 1)
        self.assertEqual(len(r["lista"]), 2)

    def test_rearme_take_profit_exige_mas_del_uno_por_ciento(self):
        accion = "PANELES.arg_cedears[0].px_bid = 1188; " + RONDA
        accion += "PANELES.arg_cedears[0].px_bid = 1250; " + RONDA
        accion += "globalThis.extra = {enLimite: nodos['alertas-lista'].children.length};"
        accion += "PANELES.arg_cedears[0].px_bid = 1187.99; " + RONDA
        accion += "PANELES.arg_cedears[0].px_bid = 1250; " + RONDA
        r = self.ejecutar(accion, base=datos(take_profit=1200))
        self.assertEqual(r["extra"]["enLimite"], 1)
        self.assertEqual(len(r["lista"]), 2)

    def test_rearme_take_profit_decimal_no_confunde_redondeo_con_mas_del_uno_por_ciento(self):
        accion = "PANELES.arg_cedears[0].px_bid = 0.2673; " + RONDA
        accion += "PANELES.arg_cedears[0].px_bid = 0.27; " + RONDA
        accion += "globalThis.extra = {enLimite: nodos['alertas-lista'].children.length};"
        accion += "PANELES.arg_cedears[0].px_bid = 0.26729999; " + RONDA
        accion += "PANELES.arg_cedears[0].px_bid = 0.27; " + RONDA
        r = self.ejecutar(accion, base=datos(take_profit=0.27), tablas=paneles(bid=0.27, c=0.27))
        self.assertEqual(r["extra"]["enLimite"], 1)
        self.assertEqual(len(r["lista"]), 2)

    def test_rearme_stop_loss_decimal_no_confunde_redondeo_con_mas_del_uno_por_ciento(self):
        accion = "PANELES.arg_cedears[0].px_bid = 0.2121; " + RONDA
        accion += "PANELES.arg_cedears[0].px_bid = 0.21; " + RONDA
        accion += "globalThis.extra = {enLimite: nodos['alertas-lista'].children.length};"
        accion += "PANELES.arg_cedears[0].px_bid = 0.21210001; " + RONDA
        accion += "PANELES.arg_cedears[0].px_bid = 0.21; " + RONDA
        r = self.ejecutar(accion, base=datos(take_profit=None, stop_loss=0.21), tablas=paneles(bid=0.21, c=0.21))
        self.assertEqual(r["extra"]["enLimite"], 1)
        self.assertEqual(len(r["lista"]), 2)

    def test_dos_eventos_generan_una_notificacion_agregada(self):
        base, tablas = dos_especies()
        r = self.ejecutar(base=base, tablas=tablas, antes="Notification.permission = 'granted';")
        self.assertEqual(len(r["lista"]), 2)
        self.assertEqual(len(r["enviadas"]), 1)
        self.assertEqual(r["enviadas"][0]["titulo"], "Alertas · demo")
        self.assertIn("AAA take profit", r["enviadas"][0]["cuerpo"])
        self.assertIn("BBB stop loss", r["enviadas"][0]["cuerpo"])
        self.assertNotIn("Reservado", json.dumps(r["enviadas"]))
        self.assertTrue(r["titulo"].startswith("(2) "))

    def test_falla_parcial_no_apaga_la_especie_con_precio_vivo(self):
        base, tablas = dos_especies()
        tablas["arg_cedears"] = tablas["arg_cedears"][:1]
        r = self.ejecutar(base=base, tablas=tablas)
        self.assertEqual(len(r["lista"]), 1)
        self.assertIn("AAA take profit", r["lista"][0])
        self.assertIn("no se pudo chequear", r["estado"].lower())
        self.assertIn("BBB", r["estado"])
        self.assertIn("chequeado", r["estado"].lower())

    def test_no_evalua_antes_de_terminar_la_primera_ronda(self):
        accion = "globalThis.extra = {antes: nodos['alertas-estado'].textContent, lineasAntes: nodos['alertas-lista'].children.length};"
        accion += "retener = false; for (const resolver of resoluciones) resolver(); await vaciar();"
        r = self.ejecutar(accion, base=datos(take_profit=1200), antes="retener = true;")
        self.assertIn("sin chequear", r["extra"]["antes"].lower())
        self.assertEqual(r["extra"]["lineasAntes"], 0)
        self.assertEqual(len(r["lista"]), 1)
        self.assertIn("chequeado", r["estado"].lower())

    def test_viernes_abierto_en_argentina_con_reloj_local_utc(self):
        antes = "Date.prototype.getHours = relojReal.prototype.getUTCHours; Date.prototype.getMinutes = relojReal.prototype.getUTCMinutes; Date.prototype.getDay = relojReal.prototype.getUTCDay;"
        r = self.ejecutar(base=datos(take_profit=1200), antes=antes, fecha="2026-11-06T19:59:59Z")
        self.assertEqual(len(r["lista"]), 1)
        self.assertIn("16:59", r["lista"][0])

    def test_lunes_diez_y_media_argentina_no_es_horario_aunque_utc_lo_sea(self):
        antes = "Date.prototype.getHours = relojReal.prototype.getUTCHours; Date.prototype.getMinutes = relojReal.prototype.getUTCMinutes; Date.prototype.getDay = relojReal.prototype.getUTCDay;"
        r = self.ejecutar(base=datos(take_profit=1200), antes=antes, fecha="2026-11-09T13:30:00Z")
        self.assertEqual(r["lista"], [])
        self.assertIn("fuera de horario", r["estado"].lower())

    def test_permiso_que_falla_no_interrumpe_los_avisos_en_pantalla(self):
        antes = "Notification.requestPermission = async () => { pedidos += 1; throw new Error('permiso ficticio fallido'); };"
        accion = "await nodos['activar-avisos'].listeners.click(); await vaciar(); PANELES.arg_cedears[0].px_bid = 2100; " + RONDA
        r = self.ejecutar(accion, base=datos(take_profit=2000), antes=antes)
        self.assertIn("no disponibles", r["avisos"].lower())
        self.assertIn("pantalla", r["avisos"].lower())
        self.assertEqual(len(r["lista"]), 1)
        self.assertEqual(r["enviadas"], [])

    def test_se_puede_reintentar_la_activacion_tras_un_fallo(self):
        antes = "Notification.requestPermission = async () => { pedidos += 1; if (pedidos === 1) throw new Error('fallo ficticio'); Notification.permission = 'granted'; return 'granted'; };"
        accion = "await nodos['activar-avisos'].listeners.click(); await vaciar(); await nodos['activar-avisos'].listeners.click(); await vaciar();"
        r = self.ejecutar(accion, antes=antes)
        self.assertEqual(r["pedidos"], 2)
        self.assertIn("activas", r["avisos"].lower())

    def test_tono_unico_por_ronda_con_dos_eventos_tras_activar(self):
        base, tablas = dos_especies()
        base["posiciones"][0]["take_profit"] = 2000
        base["posiciones"][1]["stop_loss"] = 1000
        accion = "await nodos['activar-avisos'].listeners.click(); await vaciar(); PANELES.arg_cedears[0].px_bid = 2100; PANELES.arg_cedears[1].px_bid = 900; " + RONDA
        r = self.ejecutar(accion, base=base, tablas=tablas)
        # Un tono de confirmación del botón y uno solo por la ronda con dos eventos.
        self.assertEqual(r["tonos"], 2)
        self.assertGreaterEqual(r["reanudaciones"], 1)
        self.assertEqual(len(r["lista"]), 2)
        self.assertEqual(len(r["enviadas"]), 1)

    def test_fallo_del_sonido_no_corta_alerta_ni_notificacion(self):
        antes = "AudioContext.prototype.createOscillator = () => { throw new Error('sonido ficticio bloqueado'); };"
        accion = "await nodos['activar-avisos'].listeners.click(); await vaciar(); PANELES.arg_cedears[0].px_bid = 2100; " + RONDA
        r = self.ejecutar(accion, base=datos(take_profit=2000), antes=antes)
        self.assertEqual(len(r["lista"]), 1)
        self.assertEqual(len(r["enviadas"]), 1)
        self.assertEqual(r["tonos"], 0)

    def test_sin_notificaciones_se_puede_habilitar_sonido_y_queda_pantalla(self):
        antes = "delete globalThis.Notification;"
        accion = "await nodos['activar-avisos'].listeners.click(); await vaciar(); PANELES.arg_cedears[0].px_bid = 2100; " + RONDA
        r = self.ejecutar(accion, base=datos(take_profit=2000), antes=antes)
        self.assertEqual(r["tonos"], 2)
        self.assertEqual(len(r["lista"]), 1)
        self.assertIn("no disponibles", r["avisos"].lower())
        self.assertIn("pantalla", r["avisos"].lower())
        self.assertEqual(r["enviadas"], [])

    def test_fuera_de_horario_no_rearma_evento_ya_disparado(self):
        accion = "instante = relojReal.parse('2026-11-04T18:00:00-03:00'); PANELES.arg_cedears[0].px_bid = 1100; " + RONDA
        accion += "instante = relojReal.parse('2026-11-05T12:00:00-03:00'); PANELES.arg_cedears[0].px_bid = 1300; " + RONDA
        r = self.ejecutar(accion, base=datos(take_profit=1200))
        self.assertEqual(len(r["lista"]), 1)

    def test_datos_desactualizados_solo_al_superar_once_minutos_sin_solapar(self):
        accion = "instante += 660000; retener = true; intervalos[0].funcion(); await vaciar(); const alLimite = nodos['aviso-datos'].textContent; const consultas = llamadas.length; instante += 1; intervalos[0].funcion(); await vaciar(); globalThis.extra = {alLimite, consultas};"
        r = self.ejecutar(accion)
        self.assertEqual(r["extra"]["alLimite"], "")
        self.assertNotEqual(r["datosEstado"], "")
        self.assertIn("desactualizados", r["datosEstado"])
        self.assertEqual(r["llamadas"], r["extra"]["consultas"])
        self.assertEqual(r["intervalos"], [300000])

    def test_niveles_embebidos_no_cambian_sin_regenerar_la_pagina(self):
        accion = "DATOS.posiciones[0].take_profit = 1200; " + RONDA
        r = self.ejecutar(accion, base=datos(take_profit=2000))
        self.assertEqual(r["lista"], [])

    def test_revocar_permiso_con_pagina_abierta_refresca_estado_y_no_envia(self):
        accion = "Notification.permission = 'denied'; PANELES.arg_cedears[0].px_bid = 1100; " + RONDA
        accion += "PANELES.arg_cedears[0].px_bid = 1300; " + RONDA
        r = self.ejecutar(accion, base=datos(take_profit=1200), antes="Notification.permission = 'granted';")
        self.assertEqual(len(r["lista"]), 2)
        self.assertEqual(len(r["enviadas"]), 1)
        self.assertIn("bloqueadas", r["avisos"].lower())
        self.assertIn("pantalla", r["avisos"].lower())

    def test_entrega_posterior_exitosa_recupera_estado_tras_fallo(self):
        antes = "const NotificationInicial = Notification; let fallarEntrega = true; globalThis.Notification = class extends NotificationInicial { constructor(titulo, opciones) { if (fallarEntrega) throw new Error('entrega ficticia fallida'); super(titulo, opciones); } }; Notification.permission = 'granted';"
        accion = "PANELES.arg_cedears[0].px_bid = 2100; " + RONDA
        accion += "globalThis.extra = {alFallar: nodos['avisos-estado'].textContent}; fallarEntrega = false; PANELES.arg_cedears[0].px_bid = 1900; " + RONDA
        accion += "PANELES.arg_cedears[0].px_bid = 2100; " + RONDA
        r = self.ejecutar(accion, base=datos(take_profit=2000), antes=antes)
        self.assertIn("no disponibles", r["extra"]["alFallar"].lower())
        self.assertEqual(len(r["lista"]), 2)
        self.assertEqual(len(r["enviadas"]), 1)
        self.assertIn("activas", r["avisos"].lower())

    def test_los_dos_lados_tienen_estado_independiente(self):
        accion = "PANELES.arg_cedears[0].px_bid = 1100; " + RONDA
        accion += "PANELES.arg_cedears[0].px_bid = 1500; " + RONDA
        r = self.ejecutar(accion, base=datos(take_profit=1400, stop_loss=1200), tablas=paneles(bid=1500, c=1501))
        self.assertEqual(len(r["lista"]), 3)
        self.assertIn("take profit", r["lista"][0])
        self.assertIn("stop loss", r["lista"][1])
        self.assertIn("take profit", r["lista"][2])


if __name__ == "__main__":
    unittest.main()
