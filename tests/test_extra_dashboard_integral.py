"""Resultado completo en HTML y JavaScript: DOM y red ficticios, sin navegador real."""

import copy
import datetime as dt
import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from zoneinfo import ZoneInfo

from cartera._dashboard_js import SCRIPT
from cartera.calculos import resultado_posicion, resumen_cartera
from cartera.dashboard import generar_html
from cartera.precios import Cotizacion
from cartera.punto_partida import Lote, Posicion
from test_extra_dashboard_js import DATOS, MOTOR, PANELES, PRELUDIO, RAIZ


INTEGRAL = {
    "total": 17000.0, "patrimonio_inicial": 116000.0, "patrimonio_final": 137000.0,
    "valuacion_final": 120000.0, "efectivo": {"ARS": 2000.0, "USD": 10.0},
    "aportes": 5000.0, "retiros": 1000.0, "rentas": 700.0,
    "dividendos": 800.0, "gastos": 300.0, "faltantes": [], "faltantes_fijos": [],
}


def datos_integrales():
    datos = copy.deepcopy(DATOS)
    datos["posiciones"] = datos["posiciones"][:1]
    datos["integral"] = copy.deepcopy(INTEGRAL)
    datos["realizados"] = [{"ticker": "VENDIDA", "resultado": 999999999}]
    return datos


@unittest.skipUnless(MOTOR, "No hay motor JavaScript disponible")
class RecalculoIntegralJavaScript(unittest.TestCase):
    def ejecutar(self, datos=None, paneles=None, accion="", antes=""):
        inicial = "const DATOS = " + json.dumps(datos if datos is not None else datos_integrales()) + ";\n"
        inicial += "const PANELES = " + json.dumps(paneles if paneles is not None else PANELES) + ";\n"
        nodos = "for (const id of ['inicial','valuacion','final','total','aportes','retiros','rentas','dividendos','gastos','faltantes','estado']) nodos['integral-'+id] = new Elemento('',id);\n"
        cierre = r"""
(async () => {
  await vaciar();
  ACCION
  print(JSON.stringify({
    inicial: nodos['integral-inicial'].textContent,
    valuacion: nodos['integral-valuacion'].textContent,
    final: nodos['integral-final'].textContent,
    total: nodos['integral-total'].textContent,
    faltantes: nodos['integral-faltantes'].textContent,
    estado: nodos['integral-estado'].textContent,
    avisoDatos: nodos['aviso-datos'].textContent,
    aportes: nodos['integral-aportes'].textContent,
    rentas: nodos['integral-rentas'].textContent,
    original: original === nodos['datos-cartera'].textContent,
    llamadas: llamadas.map(llamada => llamada.url)
  }));
})().catch(error => print(JSON.stringify({error: String(error), pila: error.stack})));
""".replace("ACCION", accion)
        codigo = inicial + PRELUDIO + nodos + antes + SCRIPT + cierre
        with tempfile.TemporaryDirectory(prefix="integral-js-") as temporal:
            ruta = Path(temporal) / "prueba.js"
            ruta.write_text(codigo, encoding="utf-8")
            proceso = subprocess.run([MOTOR, str(ruta)], cwd=str(RAIZ), capture_output=True, text=True, timeout=15)
        self.assertEqual(proceso.returncode, 0, proceso.stdout + proceso.stderr)
        respuesta = json.loads(proceso.stdout.strip().splitlines()[-1])
        self.assertNotIn("error", respuesta, respuesta)
        return respuesta

    def test_recalcula_precio_y_mep_sin_sumar_cobros_ni_realizado_dos_veces(self):
        r = self.ejecutar()
        self.assertEqual(r["valuacion"], "130.000,00")
        self.assertEqual(r["final"], "148.000,00")
        self.assertEqual(r["total"], "28.000,00")
        self.assertEqual(r["aportes"], "5.000,00")
        self.assertEqual(r["rentas"], "700,00")
        self.assertEqual(r["faltantes"], "")
        self.assertTrue(r["original"])
        self.assertEqual(len(r["llamadas"]), 2)

    def test_segunda_ronda_recalcula_cada_componente(self):
        accion = "PANELES.arg_cedears[0].c=1400; PANELES.mep[0].mark=1700; await nodos.actualizar.listeners.click(); await vaciar();"
        r = self.ejecutar(accion=accion)
        self.assertEqual(r["final"], "159.000,00")
        self.assertEqual(r["total"], "39.000,00")

    def test_recupera_precio_y_mep_antes_faltantes(self):
        datos = datos_integrales()
        datos["posiciones"][0].update(ultimo=None, estado="sin_dato")
        datos["mep"] = None
        datos["integral"].update(total=None, patrimonio_final=None, valuacion_final=None,
                                 faltantes=["precio actual de AAA", "dólar MEP actual"])
        r = self.ejecutar(datos=datos)
        self.assertEqual(r["total"], "28.000,00")
        self.assertEqual(r["faltantes"], "")

    def test_faltante_fijo_no_desaparece_con_la_cotizacion(self):
        datos = datos_integrales()
        datos["integral"].update(total=None, patrimonio_inicial=None, faltantes=["patrimonio inicial"],
                                 faltantes_fijos=["patrimonio inicial"])
        r = self.ejecutar(datos=datos)
        self.assertEqual(r["total"], "sin dato")
        self.assertIn("patrimonio inicial", r["faltantes"])
        self.assertEqual(r["final"], "148.000,00")

    def test_falla_posterior_conserva_total_y_advierte_ultimo_dato(self):
        r = self.ejecutar(accion="fallar=true; await nodos.actualizar.listeners.click(); await vaciar();")
        self.assertEqual(r["total"], "28.000,00")
        self.assertIn("último dato", r["estado"])

    def test_saldo_usd_cero_no_necesita_mep(self):
        datos = datos_integrales()
        datos["integral"]["efectivo"]["USD"] = 0
        datos["mep"] = None
        paneles = copy.deepcopy(PANELES)
        paneles["mep"] = []
        r = self.ejecutar(datos=datos, paneles=paneles)
        self.assertEqual(r["total"], "12.000,00")
        self.assertEqual(r["faltantes"], "")

    def test_saldo_usd_no_cero_sin_mep_no_inventa_total(self):
        datos = datos_integrales()
        datos["mep"] = None
        paneles = copy.deepcopy(PANELES)
        paneles["mep"] = []
        r = self.ejecutar(datos=datos, paneles=paneles)
        self.assertEqual(r["total"], "sin dato")
        self.assertIn("dólar MEP actual", r["faltantes"])

    def test_todo_vendido_consulta_solo_mep_y_valua_cero_posiciones(self):
        datos = datos_integrales()
        datos["posiciones"] = []
        r = self.ejecutar(datos=datos)
        self.assertEqual(r["valuacion"], "0,00")
        self.assertEqual(r["final"], "18.000,00")
        self.assertEqual(r["total"], "-102.000,00")
        self.assertEqual(r["llamadas"], ["https://data912.com/live/mep"])
        self.assertEqual(r["avisoDatos"], "")

    def test_saldo_desconocido_no_se_completa_con_cero(self):
        datos = datos_integrales()
        datos["integral"]["efectivo"]["ARS"] = None
        datos["integral"]["faltantes_fijos"] = ["efectivo ARS calculado"]
        r = self.ejecutar(datos=datos)
        self.assertEqual(r["total"], "sin dato")
        self.assertEqual(r["final"], "sin dato")
        self.assertIn("efectivo ARS calculado", r["faltantes"])


class ResultadoIntegralHTML(unittest.TestCase):
    def generar(self, integral=True, posiciones=True):
        hora = dt.datetime(2026, 11, 4, 12, tzinfo=ZoneInfo("America/Argentina/Buenos_Aires"))
        base = [Posicion("VENDIDA", "Bono vendido", "bono", 1000, 100)]
        actuales = [Posicion("NUE", "Nueva ficticia", "cedear", 10, 1)] if posiciones else []
        cotizaciones = {"NUE": Cotizacion("NUE", 500, None, None, None, "vivo", hora)} if posiciones else {}
        resultados = [resultado_posicion(p, [Lote(p.ticker, 10, "extracto", hora.date(), None, 4000, "")], 500) for p in actuales]
        dia_cero = {"esquema_version": 2, "fecha": "2026-10-01", "fijado_en": "2026-10-01T12:00:00-03:00",
                    "cantidades": {"VENDIDA": 1000}, "precios": {"VENDIDA": 150000}, "mep": None,
                    "efectivo": {"ARS": 1000, "USD": 0, "fecha": "2026-10-01"}}
        resultado = SimpleNamespace(total=2000, patrimonio_inicial=1501000, patrimonio_final=1503000,
                                    valuacion_final=5000, efectivo_ars=1498000, efectivo_usd=0,
                                    flujos=SimpleNamespace(aportes=0, retiros=0, rentas=0, dividendos=0, gastos=0),
                                    faltantes=[], faltantes_fijos=[])
        vendido = SimpleNamespace(ticker="VENDIDA", fecha=dt.date(2026, 10, 10), cantidad=1000,
                                  importe=1497000, costo=1400000, resultado=97000, origen_costo="estimado")
        control = SimpleNamespace(estado="no_concilia", fecha=dt.date(2026, 10, 20), diferencias={"ARS": -6000})
        return generar_html({"slug": "demo"}, resultados, resumen_cartera(resultados), cotizaciones, {}, {},
                            {"fecha": "2026-10-20", "ARS": 1492000, "USD": 0}, {}, hora,
                            posiciones=actuales, posiciones_base=base, dia_cero=dia_cero,
                            integral=resultado if integral else None, realizados=[vendido], conciliacion=control)

    def test_referencia_inicial_usa_base_aunque_original_vendida(self):
        import re
        html = self.generar()
        datos = json.loads(re.search(r'<script id="datos-cartera" type="application/json">(.*?)</script>', html, re.S).group(1))
        self.assertEqual(datos["dia_cero"]["patrimonio_inicial"], 1501000)
        self.assertEqual(datos["integral"]["faltantes_fijos"], [])
        self.assertEqual(datos["realizados"][0]["fecha"], "2026-10-10")
        self.assertNotIn("porcentaje", datos["integral"])
        self.assertIn('id="resultado-completo"', html)
        self.assertIn('id="resultado-realizado"', html)
        self.assertIn("incluye estimado", html)
        self.assertIn("Efectivo calculado", html)
        self.assertIn("no concilia", html)
        self.assertIn("Revisá los movimientos", html)

    def test_todo_vendido_habilita_mep_para_resultado_integral(self):
        html = self.generar(posiciones=False)
        self.assertIn('"actualizacion_habilitada": true', html)

    def test_sin_integral_conserva_recuadro_de_api_anterior(self):
        html = self.generar(integral=False)
        self.assertIn("Se calcula cuando estén los movimientos", html)
        self.assertNotIn('id="resultado-completo"', html)


if __name__ == "__main__":
    unittest.main()
