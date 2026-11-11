"""Panel de letras con datos ficticios; HTML y reloj simulado, sin avisos reales."""

import copy
import datetime as dt
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile
import unittest
from zoneinfo import ZoneInfo

from cartera._dashboard_js import SCRIPT
from cartera.calculos import resumen_cartera
from cartera.dashboard import generar_html
from test_extra_dashboard_js import DATOS, MOTOR, PANELES, PRELUDIO, RAIZ


T = dt.datetime(2026, 11, 6, 18, tzinfo=ZoneInfo("America/Argentina/Buenos_Aires"))


def letras_demo():
    return {
        "fecha_calculo": "2026-11-06", "avisos": [],
        "posiciones": [{
            "ticker": "LETRADEMO", "cantidad": "9007199254740993.00123",
            "moneda_pago": "ARS", "familia": "LECAP", "vencimiento": "2026-11-07",
            "dias_restantes": 1, "valor_por_base": "125.123456789", "base_nominal": "100",
            "pago_vencimiento": "12345678901234567890.123456789",
            "avisos": [], "lotes": [{
                "referencia": "base:1", "huella": "a" * 64, "fecha_compra": "2026-10-01",
                "cantidad_restante": "9007199254740993.00123", "precio": "99.123456789",
                "moneda": "ARS", "fecha_liquidacion": "2026-10-02",
                "rendimiento": "0.1234567890123456789012345678901234567", "tea": "0.5",
            }],
        }],
    }


def generar(letras=None):
    return generar_html(
        cliente={"slug": "demo", "nombre": "Demo ficticio"}, resultados=[],
        resumen=resumen_cartera([]), cotizaciones={}, niveles={}, instrumentos={},
        efectivo={}, historial={}, generado_en=T, letras=letras,
    )


def datos_html(html):
    return json.loads(re.search(r'<script id="datos-cartera" type="application/json">(.*?)</script>', html, re.S).group(1))


def panel_html(html):
    return re.search(r'<section id="letras-panel".*?</section>', html, re.S).group(0)


class LetrasHTML(unittest.TestCase):
    def test_panel_de_lectura_preciso_y_detalle_de_compra(self):
        letras = letras_demo()
        copia = copy.deepcopy(letras)
        html = generar(letras)
        panel = panel_html(html)
        self.assertIn("Tenencia de letras", panel)
        self.assertIn("Días corridos restantes", panel)
        self.assertIn("9.007.199.254.740.993,00123", panel)
        self.assertIn("12.345.678.901.234.567.890,12 ARS", panel)
        self.assertIn("99,123456789 ARS por 100 VN", panel)
        self.assertIn("12,35 %", panel)
        self.assertIn("01/10/2026", panel)
        self.assertIn("02/10/2026", panel)
        self.assertIn("<details>", panel)
        self.assertIn("<summary>Ver compras (1)</summary>", panel)
        self.assertNotIn("<input", panel)
        self.assertNotIn("<form", panel)
        self.assertNotIn("TEA", panel)
        self.assertIn("no se suma al efectivo ni al resultado", panel)
        self.assertEqual(letras, copia)
        self.assertEqual(datos_html(html)["letras"], copia)

    def test_ausencia_es_compatible_con_html_anterior(self):
        html = generar()
        self.assertNotIn('id="letras-panel"', html)
        self.assertNotIn("letras", datos_html(html))
        self.assertEqual(datos_html(generar(letras_demo()))["integral"], datos_html(html)["integral"])
        self.assertEqual(datos_html(generar(letras_demo()))["efectivo"], datos_html(html)["efectivo"])

    def test_faltantes_se_muestran_y_no_se_inventan_ceros(self):
        letras = letras_demo()
        posicion = letras["posiciones"][0]
        posicion.update(vencimiento=None, pago_vencimiento=None, base_nominal=None)
        posicion["lotes"][0].update(precio=None, moneda=None, fecha_compra=None, fecha_liquidacion=None, rendimiento=None)
        panel = panel_html(generar(letras))
        self.assertIn("sin dato; falta vencimiento", panel)
        self.assertIn("faltan datos para el pago al vencimiento", panel)
        self.assertIn("falta precio o moneda de compra", panel)
        self.assertIn("falta fecha de compra o liquidación", panel)
        self.assertNotIn("0,00 ARS", panel)
        self.assertNotIn("1970", panel)

    def test_lelink_no_presenta_calculo_aunque_reciba_valores(self):
        letras = letras_demo()
        letras["posiciones"][0]["familia"] = "LELINK"
        panel = panel_html(generar(letras))
        self.assertIn("Cálculo dólar linked pendiente de validación del Toolkit", panel)
        self.assertNotIn("12.345.678.901.234.567.890,123456789", panel)
        self.assertNotIn("12,35 %", panel)
        self.assertIn("99,123456789 ARS por 100 VN", panel)

    def test_hoy_cero_y_vencida_no_confirma_cobro(self):
        letras = letras_demo()
        letras["posiciones"][0]["vencimiento"] = "2026-11-06"
        self.assertIn("0 días · vence hoy", panel_html(generar(letras)))
        letras["posiciones"][0]["vencimiento"] = "2026-11-04"
        self.assertIn("Vencida hace 2 días; cobro sin confirmar", panel_html(generar(letras)))

    def test_avisos_y_tickers_escapados_y_csp_sin_cambios(self):
        letras = letras_demo()
        ataque = '</script><img src=x onerror="prueba">&'
        letras["posiciones"][0]["ticker"] = ataque
        letras["avisos"] = [ataque]
        html = generar(letras)
        panel = panel_html(html)
        self.assertNotIn("<img", panel)
        self.assertIn("&lt;/script&gt;", panel)
        self.assertNotIn("</script><img", html)
        self.assertEqual(datos_html(html)["letras"]["avisos"], [ataque])
        csp = re.search(r'<meta http-equiv="Content-Security-Policy"[^>]*>', html).group(0)
        self.assertEqual(csp, re.search(r'<meta http-equiv="Content-Security-Policy"[^>]*>', generar()).group(0))
        self.assertNotIn("innerHTML", html)
        self.assertNotIn("localStorage", html)

    def test_sin_tenencias_no_inventa_pagos(self):
        panel = panel_html(generar({"fecha_calculo": "2026-11-06", "posiciones": [], "avisos": ["Aviso ficticio"]}))
        self.assertIn("No hay tenencias de letras vigentes", panel)
        self.assertIn("Aviso ficticio", panel)
        self.assertNotIn("0,00", panel)


@unittest.skipUnless(MOTOR, "No hay motor JavaScript disponible")
class LetrasRelojJavaScript(unittest.TestCase):
    def ejecutar(self, fecha="2026-11-07T02:59:30Z", accion="", datos=None):
        datos = copy.deepcopy(DATOS if datos is None else datos)
        datos.update(actualizacion_habilitada=False, posiciones=[], letras=letras_demo())
        inicial = "const DATOS = " + json.dumps(datos) + ";\nconst PANELES = " + json.dumps(PANELES) + ";\n"
        nodos = """
for (const id of ['letras-panel','letras-dias-0','letras-estado']) nodos[id] = new Elemento('',id);
instante = relojReal.parse(FECHA);
""".replace("FECHA", json.dumps(fecha))
        cierre = """
(async () => {
  await vaciar();
  const antes = nodos['letras-dias-0'].textContent;
  ACCION
  print(JSON.stringify({antes, despues: nodos['letras-dias-0'].textContent,
    estado: nodos['letras-estado'].textContent,
    intervalos: intervalos.map(i => i.demora), llamadas: llamadas.length,
    original: original === nodos['datos-cartera'].textContent,
    boton: nodos.actualizar.disabled}));
})().catch(error => print(JSON.stringify({error: String(error), pila: error.stack})));
""".replace("ACCION", accion)
        with tempfile.TemporaryDirectory(prefix="letras-js-") as temporal:
            ruta = Path(temporal) / "prueba.js"
            ruta.write_text(inicial + PRELUDIO + nodos + SCRIPT + cierre, encoding="utf-8")
            entorno = dict(os.environ, TZ="Pacific/Auckland")
            proceso = subprocess.run([MOTOR, str(ruta)], cwd=str(RAIZ), env=entorno, capture_output=True, text=True, timeout=15)
        self.assertEqual(proceso.returncode, 0, proceso.stdout + proceso.stderr)
        respuesta = json.loads(proceso.stdout.strip().splitlines()[-1])
        self.assertNotIn("error", respuesta, respuesta)
        return respuesta

    def test_medionoche_argentina_sin_precios_cuenta_sabado(self):
        r = self.ejecutar(accion="instante += 60000; intervalos.find(i => i.demora === 60000).funcion();")
        self.assertEqual(r["antes"], "1 día")
        self.assertEqual(r["despues"], "0 días · vence hoy")
        self.assertIn("07/11/2026", r["estado"])
        self.assertEqual(r["intervalos"], [60000])
        self.assertEqual(r["llamadas"], 0)
        self.assertTrue(r["boton"])
        self.assertTrue(r["original"])

    def test_despues_del_vencimiento_sigue_sin_confirmar_cobro(self):
        r = self.ejecutar(fecha="2026-11-09T03:10:00Z")
        self.assertEqual(r["despues"], "Vencida hace 2 días; cobro sin confirmar")


if __name__ == "__main__":
    unittest.main()
