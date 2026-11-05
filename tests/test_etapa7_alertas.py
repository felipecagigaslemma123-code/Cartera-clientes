import copy
import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from cartera import notificar
from cartera._dashboard_js import SCRIPT
from test_extra_dashboard_js import DATOS, MOTOR, PANELES, PRELUDIO, RAIZ

ABIERTO = "instante = relojReal.parse('2026-11-04T12:00:00-03:00');\n"
CERRADO = "instante = relojReal.parse('2026-11-04T18:00:00-03:00');\n"
NODOS = "nodos['alertas-panel'] = new Elemento('section', 'alertas-panel'); nodos['alertas-estado'] = new Elemento('p', 'alertas-estado');\n"
NODOS += "nodos['alertas-lista'] = new Elemento('ul', 'alertas-lista'); nodos['avisos-estado'] = new Elemento('p', 'avisos-estado');\n"
NODOS += "nodos['activar-avisos'] = new Elemento('button', 'activar-avisos'); document.title = 'Cartera';\n"
NOTIFICACIONES = """
const enviadas = [];
globalThis.Notification = class { constructor(titulo, opciones) { enviadas.push({titulo, cuerpo: opciones.body}); } };
Notification.permission = 'PERMISO';
Notification.requestPermission = async () => { Notification.permission = 'PEDIDO'; return 'PEDIDO'; };
"""
RONDA = "await nodos.actualizar.listeners.click(); await vaciar();\n"


def datos(take_profit=1500, stop_loss=None):
    copia = copy.deepcopy(DATOS)
    copia["cliente"] = {"slug": "demo", "nombre": "Nombre Reservado"}
    copia["posiciones"] = copia["posiciones"][:1]
    copia["posiciones"][0].update(take_profit=take_profit, stop_loss=stop_loss)
    return copia


def paneles(bid=1299, c=1300):
    return {"arg_cedears": [{"symbol": "AAA", "c": c, "px_bid": bid, "px_ask": c + 1, "pct_change": 1.5}],
            "mep": PANELES["mep"]}


def cambiar_bid(valor):
    return "PANELES.arg_cedears[0].px_bid = {}; {}".format(valor, RONDA)


@unittest.skipUnless(MOTOR, "No hay motor JavaScript disponible")
class Alertas(unittest.TestCase):
    def ejecutar(self, accion="", base=None, tablas=None, reloj=ABIERTO, permiso="granted", pedido="granted", sin_notificacion=False):
        inicial = "const DATOS = {};\nconst PANELES = {};\n".format(json.dumps(base or datos()), json.dumps(tablas or paneles()))
        extra = "" if sin_notificacion else NOTIFICACIONES.replace("PERMISO", permiso).replace("PEDIDO", pedido)
        if sin_notificacion:
            extra = "const enviadas = [];\n"
        cierre = r"""
(async () => {
  await vaciar();
  ACCION
  print(JSON.stringify({
    estado: nodos['alertas-estado'].textContent,
    lista: nodos['alertas-lista'].children.map(hijo => hijo.textContent),
    avisos: nodos['avisos-estado'].textContent,
    titulo: document.title,
    enviadas,
    intervalos: intervalos.map(intervalo => intervalo.demora)
  }));
})().catch(error => print(JSON.stringify({error: String(error), pila: error.stack})));
""".replace("ACCION", accion)
        codigo = inicial + PRELUDIO + reloj + NODOS + extra + SCRIPT + cierre
        with tempfile.TemporaryDirectory(prefix="alertas-js-") as temporal:
            ruta = Path(temporal) / "prueba.js"
            ruta.write_text(codigo, encoding="utf-8")
            proceso = subprocess.run([MOTOR, str(ruta)], cwd=str(RAIZ), capture_output=True, text=True, timeout=15)
        self.assertEqual(proceso.returncode, 0, proceso.stdout + proceso.stderr)
        respuesta = json.loads(proceso.stdout.strip().splitlines()[-1])
        self.assertNotIn("error", respuesta, respuesta)
        return respuesta

    def test_cada_cinco_minutos(self):
        self.assertEqual(self.ejecutar()["intervalos"], [300000])

    def test_no_dispara_dentro_del_rango(self):
        r = self.ejecutar()
        self.assertEqual(r["lista"], [])
        self.assertIn("chequeado", r["estado"].lower())
        self.assertIn("1", r["estado"])
        self.assertEqual(r["enviadas"], [])

    def test_take_profit(self):
        r = self.ejecutar(base=datos(take_profit=1200))
        self.assertEqual(len(r["lista"]), 1)
        self.assertIn("AAA take profit: precio 1.299,00, nivel 1.200,00", r["lista"][0])
        self.assertTrue(r["titulo"].startswith("(1) "))

    def test_stop_loss(self):
        r = self.ejecutar(base=datos(take_profit=None, stop_loss=1400))
        self.assertIn("AAA stop loss: precio 1.299,00, nivel 1.400,00", r["lista"][0])

    def test_usa_el_ultimo_si_no_hay_bid(self):
        r = self.ejecutar(base=datos(take_profit=1300), tablas=paneles(bid=0, c=1300))
        self.assertIn("precio 1.300,00", r["lista"][0])

    def test_una_vez_por_evento(self):
        r = self.ejecutar(RONDA + RONDA, base=datos(take_profit=1200))
        self.assertEqual(len(r["lista"]), 1)
        self.assertEqual(len(r["enviadas"]), 1)

    def test_rearma_al_volver_mas_de_uno_por_ciento(self):
        accion = cambiar_bid(1187) + cambiar_bid(1250)
        self.assertEqual(len(self.ejecutar(accion, base=datos(take_profit=1200))["lista"]), 2)

    def test_no_rearma_dentro_del_uno_por_ciento(self):
        accion = cambiar_bid(1190) + cambiar_bid(1250)
        self.assertEqual(len(self.ejecutar(accion, base=datos(take_profit=1200))["lista"]), 1)

    def test_fuera_de_horario_no_evalua(self):
        r = self.ejecutar(base=datos(take_profit=1200), reloj=CERRADO)
        self.assertEqual(r["lista"], [])
        self.assertIn("fuera de horario", r["estado"].lower())

    def test_fin_de_semana_no_evalua(self):
        r = self.ejecutar(base=datos(take_profit=1200), reloj="instante = relojReal.parse('2026-11-07T12:00:00-03:00');\n")
        self.assertEqual(r["lista"], [])

    def test_las_17_estan_excluidas(self):
        r = self.ejecutar(base=datos(take_profit=1200), reloj="instante = relojReal.parse('2026-11-04T17:00:00-03:00');\n")
        self.assertEqual(r["lista"], [])

    def test_las_11_estan_incluidas(self):
        r = self.ejecutar(base=datos(take_profit=1200), reloj="instante = relojReal.parse('2026-11-04T11:00:00-03:00');\n")
        self.assertEqual(len(r["lista"]), 1)

    def test_sin_niveles(self):
        r = self.ejecutar(base=datos(take_profit=None))
        self.assertIn("sin niveles", r["estado"].lower())

    def test_sin_red_no_dispara_y_lo_dice(self):
        r = self.ejecutar("fallar = true; " + RONDA, base=datos(take_profit=1200, stop_loss=None), tablas=paneles(bid=1000, c=1000))
        self.assertEqual(r["lista"], [])
        self.assertIn("no se pudo chequear", r["estado"].lower())
        self.assertIn("AAA", r["estado"])

    def test_dato_guardado_no_dispara_antes_de_la_ronda(self):
        base = datos(take_profit=1200)
        r = self.ejecutar("", base=base, tablas={"arg_cedears": [], "mep": PANELES["mep"]})
        self.assertEqual(r["lista"], [])
        self.assertIn("no se pudo chequear", r["estado"].lower())

    def test_notificacion_sin_nombre_del_cliente(self):
        r = self.ejecutar(base=datos(take_profit=1200))
        self.assertEqual(r["enviadas"][0]["titulo"], "Alertas · demo")
        self.assertIn("AAA take profit", r["enviadas"][0]["cuerpo"])
        self.assertNotIn("Reservado", json.dumps(r["enviadas"]))

    def test_sin_permiso_no_notifica_pero_avisa_en_pantalla(self):
        r = self.ejecutar(base=datos(take_profit=1200), permiso="default")
        self.assertEqual(r["enviadas"], [])
        self.assertEqual(len(r["lista"]), 1)
        self.assertIn("sin activar", r["avisos"].lower())

    def test_sin_soporte_avisa_en_pantalla(self):
        r = self.ejecutar(base=datos(take_profit=1200), sin_notificacion=True)
        self.assertEqual(len(r["lista"]), 1)
        self.assertIn("no disponibles", r["avisos"].lower())

    def test_una_falla_de_la_notificacion_no_interrumpe(self):
        antes = "globalThis.Notification = class { constructor() { throw new Error('no'); } }; Notification.permission = 'granted';\n"
        base = datos(take_profit=1200)
        inicial = json.dumps(base)
        codigo = "const DATOS = {};\nconst PANELES = {};\n".format(inicial, json.dumps(paneles())) + PRELUDIO + ABIERTO + NODOS + antes + SCRIPT + r"""
(async () => { await vaciar(); print(JSON.stringify({lista: nodos['alertas-lista'].children.length})); })();
"""
        with tempfile.TemporaryDirectory(prefix="alertas-js-") as temporal:
            ruta = Path(temporal) / "prueba.js"
            ruta.write_text(codigo, encoding="utf-8")
            proceso = subprocess.run([MOTOR, str(ruta)], cwd=str(RAIZ), capture_output=True, text=True, timeout=15)
        self.assertEqual(json.loads(proceso.stdout.strip().splitlines()[-1])["lista"], 1, proceso.stderr)

    def test_activar_permiso_concedido(self):
        r = self.ejecutar("await nodos['activar-avisos'].listeners.click(); await vaciar();", permiso="default", pedido="granted")
        self.assertIn("activas", r["avisos"].lower())

    def test_activar_permiso_negado(self):
        r = self.ejecutar("await nodos['activar-avisos'].listeners.click(); await vaciar();", permiso="default", pedido="denied")
        self.assertIn("bloqueadas", r["avisos"].lower())

    def test_activar_hace_sonar_el_tono(self):
        audio = """
globalThis.tonos = 0;
globalThis.AudioContext = class {
  constructor() { this.state = 'suspended'; this.currentTime = 0; this.destination = {}; }
  async resume() { this.state = 'running'; }
  createOscillator() { return {frequency: {}, connect() {}, start() { globalThis.tonos += 1; }, stop() {}}; }
  createGain() { return {gain: {}, connect() {}}; }
};
"""
        codigo = "const DATOS = {};\nconst PANELES = {};\n".format(json.dumps(datos()), json.dumps(paneles())) + PRELUDIO + ABIERTO + NODOS + audio + SCRIPT + r"""
(async () => {
  await vaciar();
  const antes = globalThis.tonos;
  await nodos['activar-avisos'].listeners.click();
  await vaciar();
  print(JSON.stringify({antes, despues: globalThis.tonos}));
})().catch(error => print(JSON.stringify({error: String(error)})));
"""
        with tempfile.TemporaryDirectory(prefix="alertas-js-") as temporal:
            ruta = Path(temporal) / "prueba.js"
            ruta.write_text(codigo, encoding="utf-8")
            proceso = subprocess.run([MOTOR, str(ruta)], cwd=str(RAIZ), capture_output=True, text=True, timeout=15)
        self.assertEqual(json.loads(proceso.stdout.strip().splitlines()[-1]), {"antes": 0, "despues": 1}, proceso.stderr)

    def test_ya_concedido_al_abrir(self):
        self.assertIn("activas", self.ejecutar()["avisos"].lower())

class SinTelegram(unittest.TestCase):
    def test_solo_macos(self):
        self.assertEqual(notificar.canales_disponibles(), [notificar.canal_macos])
        self.assertFalse(hasattr(notificar, "canal_telegram"))
        self.assertFalse(hasattr(notificar, "credencial_telegram"))

    def test_no_consulta_el_llavero(self):
        with patch("cartera.notificar.subprocess.run") as correr:
            notificar.canales_disponibles()
        correr.assert_not_called()

    def test_sin_tareas_programadas(self):
        self.assertFalse((RAIZ / "ops").exists())


class Pantalla(unittest.TestCase):
    def test_html_tiene_el_panel(self):
        from cartera.dashboard import generar_html
        import datetime as dt
        from zoneinfo import ZoneInfo
        html = generar_html(cliente={"slug": "demo"}, resultados=[], resumen=None, cotizaciones={}, niveles={}, instrumentos={},
                            efectivo={}, historial={}, generado_en=dt.datetime(2026, 11, 4, 12, tzinfo=ZoneInfo("America/Argentina/Buenos_Aires")),
                            posiciones=[])
        for identificador in ("alertas-panel", "alertas-estado", "alertas-lista", "activar-avisos", "avisos-estado"):
            self.assertIn('id="{}"'.format(identificador), html)
        self.assertIn("abierta", html.lower())
        self.assertLess(html.index("</header>"), html.index('id="alertas-panel"'))
        self.assertNotIn("localStorage", html)


if __name__ == "__main__":
    unittest.main()
