"""Un bono capitalizable se carga como letra y cotiza en el panel de bonos."""

import copy
import datetime as dt
import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from zoneinfo import ZoneInfo

from cartera._dashboard_js import SCRIPT
from cartera.precios import ClientePrecios
from cartera.punto_partida import Posicion
from test_extra_dashboard_js import DATOS, MOTOR, PRELUDIO, RAIZ

T = dt.datetime(2026, 11, 4, 12, 0, tzinfo=ZoneInfo("America/Argentina/Buenos_Aires"))
BASE = "https://data912.com/live/"


def fila(ticker, precio):
    return {"symbol": ticker, "c": precio, "px_bid": precio, "px_ask": precio, "pct_change": 0.5}


class Python(unittest.TestCase):
    def setUp(self):
        temporal = tempfile.TemporaryDirectory()
        self.addCleanup(temporal.cleanup)
        self.cache = Path(temporal.name) / "cache.json"
        self.llamadas = []
        self.paneles = {"arg_notes": [fila("LECAP1", 128.5)], "arg_bonds": [fila("BONCAP1", 139.8), fila("BOND1", 160000.0)]}

    def fetch(self, url):
        self.llamadas.append(url)
        return self.paneles.get(url[len(BASE):], [])

    def obtener(self, *posiciones):
        return ClientePrecios(self.fetch, self.cache, ahora=lambda: T).obtener(posiciones)

    def test_la_boncap_toma_el_precio_del_panel_de_bonos(self):
        r = self.obtener(Posicion("BONCAP1", "Bono capitalizable", "letra", 1000.0, 100))
        self.assertEqual((r["BONCAP1"].estado, r["BONCAP1"].ultimo), ("vivo", 139.8))
        self.assertEqual(self.llamadas, [BASE + "arg_notes", BASE + "arg_bonds"])

    def test_una_letra_en_su_panel_no_consulta_el_de_bonos(self):
        r = self.obtener(Posicion("LECAP1", "Letra", "letra", 1000.0, 100))
        self.assertEqual(r["LECAP1"].ultimo, 128.5)
        self.assertEqual(self.llamadas, [BASE + "arg_notes"])

    def test_el_panel_de_bonos_se_pide_una_sola_vez(self):
        r = self.obtener(Posicion("BOND1", "Bono", "bono", 100.0, 100), Posicion("BONCAP1", "Bono capitalizable", "letra", 1000.0, 100),
                         Posicion("LECAP1", "Letra", "letra", 1000.0, 100))
        self.assertEqual({t: c.estado for t, c in r.items()}, {"BOND1": "vivo", "BONCAP1": "vivo", "LECAP1": "vivo"})
        self.assertEqual(sorted(self.llamadas), [BASE + "arg_bonds", BASE + "arg_notes"])

    def test_el_precio_del_panel_propio_tiene_prioridad(self):
        self.paneles["arg_bonds"].append(fila("LECAP1", 999.0))
        self.assertEqual(self.obtener(Posicion("LECAP1", "Letra", "letra", 1000.0, 100))["LECAP1"].ultimo, 128.5)

    def test_un_bono_no_se_busca_en_otro_panel(self):
        r = self.obtener(Posicion("LECAP1", "Mal cargada como bono", "bono", 100.0, 100))
        self.assertEqual(r["LECAP1"].estado, "sin_dato")
        self.assertEqual(self.llamadas, [BASE + "arg_bonds"])

    def test_sin_precio_en_ninguno_queda_sin_dato(self):
        r = self.obtener(Posicion("OTRA", "Letra sin cotización", "letra", 100.0, 100))
        self.assertEqual(r["OTRA"].estado, "sin_dato")


@unittest.skipUnless(MOTOR, "No hay motor JavaScript disponible")
class Navegador(unittest.TestCase):
    def ejecutar(self, paneles):
        datos = copy.deepcopy(DATOS)
        base = dict(datos["posiciones"][0], take_profit=None, ultimo=None, bid=None, ask=None, estado="sin_dato", costo=None,
                    estado_costo="incompleto", tipo="letra", cotiza_cada=100, endpoint="arg_notes", endpoint_alterno="arg_bonds")
        datos["posiciones"] = [dict(base, ticker="BONCAP1", cantidad=1000), dict(base, ticker="LECAP1", cantidad=2000)]
        inicial = "const DATOS = {};\nconst PANELES = {};\n".format(json.dumps(datos), json.dumps(paneles))
        cierre = r"""
(async () => {
  await vaciar();
  print(JSON.stringify({
    llamadas: llamadas.map(llamada => llamada.url),
    filas: nodos['posiciones-body'].children.map(fila => fila.children.map(celda => celda.textContent))
  }));
})().catch(error => print(JSON.stringify({error: String(error), pila: error.stack})));
"""
        with tempfile.TemporaryDirectory(prefix="boncap-js-") as temporal:
            ruta = Path(temporal) / "prueba.js"
            ruta.write_text(inicial + PRELUDIO + SCRIPT + cierre, encoding="utf-8")
            proceso = subprocess.run([MOTOR, str(ruta)], cwd=str(RAIZ), text=True, capture_output=True, timeout=15)
        self.assertEqual(proceso.returncode, 0, proceso.stdout + proceso.stderr)
        respuesta = json.loads(proceso.stdout.strip().splitlines()[-1])
        self.assertNotIn("error", respuesta, respuesta)
        return respuesta

    def test_busca_en_el_panel_alterno_y_pide_cada_panel_una_vez(self):
        r = self.ejecutar({"arg_notes": [fila("LECAP1", 128.5)], "arg_bonds": [fila("BONCAP1", 139.8), fila("LECAP1", 999.0)],
                           "mep": [{"ticker": "AL30", "mark": 1600}]})
        self.assertEqual(sorted(r["llamadas"]), [BASE + "arg_bonds", BASE + "arg_notes", BASE + "mep"])
        filas = {f[0]: f for f in r["filas"]}
        self.assertIn("1.398,00", filas["BONCAP1"][5])
        self.assertIn("En vivo", filas["BONCAP1"][14])
        self.assertIn("2.570,00", filas["LECAP1"][5])


if __name__ == "__main__":
    unittest.main()
