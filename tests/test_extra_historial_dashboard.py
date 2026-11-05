"""Historial en el tablero: datos ficticios, completo para revisar y sin mezclar resultados."""

import copy
import datetime as dt
import json
import re
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from zoneinfo import ZoneInfo

from cartera.almacenamiento import importar_cartera
from cartera.calculos import resumen_cartera
from cartera.dashboard import generar_html
from cartera.dashboard_archivos import crear_dashboard
from test_etapa6_historial import D1, D2, D3, PANELES, escribir_extracto, fila_xlsx

DEMO = Path(__file__).resolve().parents[1] / "fixtures" / "punto_partida_demo.xlsx"
HORA = dt.datetime(2026, 11, 5, 12, tzinfo=ZoneInfo("America/Argentina/Buenos_Aires"))


def datos(html):
    return json.loads(re.search(r'<script id="datos-cartera" type="application/json">(.*?)</script>', html, re.S).group(1))


def flujo(ars=0.0, usd=0.0, equivalente=0.0):
    return {"ARS": ars, "USD": usd, "equivalente_ars": equivalente}


def historial_ficticio():
    clases = ("dividendo", "retencion", "renta", "caucion_colocada", "caucion_tomada", "fci", "gastos")
    return SimpleNamespace(total_conocido=500.0, realizado_extracto=400.0, realizado_estimado=100.0,
                           ingresos={clase: flujo() for clase in clases}, aportes=flujo(5000, 0, 5000),
                           retiros=flujo(100, 0, 100), realizados=[], ventas_sin_dato=0, valores_sin_dato=0,
                           sin_clasificar=[], avisos=[], diferencias_tenencias={}, diferencias_costos={})


class PresentacionHistorica(unittest.TestCase):
    def generar(self, historial=None, integral=None):
        return generar_html({"slug": "demo"}, [], resumen_cartera([]), {}, {}, {}, None, {}, HORA,
                            posiciones=[], integral=integral, historial_realizado=historial)

    def test_sin_historial_no_agrega_seccion_ni_datos(self):
        html = self.generar()
        self.assertNotIn('id="rendimiento-realizado"', html)
        self.assertNotIn("historial", datos(html))

    def test_historial_lista_renglon_completo_y_escapa_textos(self):
        h = historial_ficticio()
        fila = {"operado": D1, "comprobante": "NUEVO </script><script>alert(1)</script>", "numero": 123,
                "cantidad": 2.0, "especie": "FICTICIO", "importe": 765.5, "saldo": None,
                "referencia": "nota <img src=x onerror=alert(2)>", "archivo": "demo.xlsx", "fila": 7,
                "moneda": "USD", "cuenta": "CABLE", "extra": {"Liquida": D2, "Precio": 999.25}}
        h.sin_clasificar = [fila]
        html = self.generar(h)
        d = datos(html)["historial"]
        self.assertEqual(d["cantidad_sin_clasificar"], 1)
        self.assertEqual(d["sin_clasificar"][0]["operado"], "2026-01-10")
        self.assertEqual(d["sin_clasificar"][0]["extra"]["Liquida"], "2026-02-10")
        for campo in fila:
            self.assertIn("<dt>" + campo + "</dt>", html)
        self.assertIn("&lt;img", html)
        self.assertIn("&lt;/script&gt;", html)
        self.assertIn(r'"comprobante": "NUEVO \u003c/script>', html)
        self.assertNotIn("<script>alert(1)</script>", html)
        self.assertIn("Resultado parcial", html)
        self.assertEqual(h.sin_clasificar[0], fila)

    def test_los_faltantes_se_muestran_y_no_aparecen_como_cero(self):
        h = historial_ficticio()
        h.ventas_sin_dato = 1
        h.valores_sin_dato = 1
        h.ingresos["dividendo"] = flujo(0, 10, None)
        h.realizados = [SimpleNamespace(ticker="FICTICIO", fecha=D2, cantidad=10, cantidad_sin_lote=6,
                                       importe_ars=1000, costo_ars=None, resultado_ars=None,
                                       origen_costo="incompleto", clase="venta")]
        html = self.generar(h)
        self.assertIn("Resultado parcial", html)
        self.assertIn("1 ventas o cierres sin resultado conocido", html)
        self.assertIn("1 valores sin equivalente en pesos", html)
        self.assertIsNone(datos(html)["historial"]["ingresos"]["dividendo"]["equivalente_ars"])
        self.assertIn("<td>sin dato</td>", html)
        # Un costo en USD puede estar observado pero carecer del MEP histórico.
        # El origen incompleto no permite afirmar que falte estimar una compra.
        self.assertIn("<td>incompleto (sin dato)</td>", html)
        historico = html.split('id="rendimiento-realizado"', 1)[1].split('</section>', 1)[0]
        self.assertNotIn("falta estimar", historico)

    def test_caucion_incompleta_aparece_como_parcial_con_su_aviso(self):
        h = historial_ficticio()
        h.avisos = ["Caución incompleta: números 100, 101; no se suma capital."]
        html = self.generar(h)
        self.assertIn("Resultado parcial", html)
        self.assertIn("números 100, 101", html)

    def test_no_se_suma_al_resultado_desde_dia_cero(self):
        h = historial_ficticio()
        integral = SimpleNamespace(total=123.0, patrimonio_inicial=1000, patrimonio_final=1123,
                                   valuacion_final=1123, efectivo_ars=0, efectivo_usd=0,
                                   flujos=SimpleNamespace(aportes=0, retiros=0, rentas=0, dividendos=0, gastos=0),
                                   faltantes=[], faltantes_fijos=[])
        html = self.generar(h, integral)
        d = datos(html)
        self.assertEqual(d["integral"]["total"], 123)
        self.assertEqual(d["historial"]["total_conocido"], 500)
        self.assertIn('id="integral-total" class="dato-destacado">123,00', html)
        self.assertIn("Total conocido: 500,00 ARS", html)
        self.assertNotIn("porcentaje", d["historial"])

    def test_origen_y_diferencias_con_base_quedan_visibles(self):
        h = historial_ficticio()
        h.diferencias_tenencias = {"FICTICIO": {"derivada": 10, "base": 20, "diferencia": -10}}
        h.diferencias_costos = {"FICTICIO": {"derivada": 1000, "base": None, "diferencia": None}}
        html = self.generar(h)
        d = datos(html)["historial"]
        self.assertEqual(d["realizado_extracto"], 400)
        self.assertEqual(d["realizado_estimado"], 100)
        self.assertEqual(d["diferencias_tenencias"]["FICTICIO"]["diferencia"], -10)
        self.assertIn("Realizado que incluye estimaciones", html)
        self.assertIn("Diferencias de cantidad", html)
        self.assertIn("Diferencias de costo", html)


class IntegracionHistoricaDashboard(unittest.TestCase):
    def setUp(self):
        temporal = tempfile.TemporaryDirectory()
        self.addCleanup(temporal.cleanup)
        self.datos = Path(temporal.name) / "datos"
        self.punto, _ = importar_cartera(self.datos, "demo", DEMO)
        self.carpeta = self.datos / "clientes" / "demo"

    def extractos(self):
        carpeta = self.carpeta / "extractos"
        carpeta.mkdir()
        escribir_extracto(carpeta / "ficticio.xlsx", "PESOS", [
            fila_xlsx(D1, "COMPRA NORMAL", 1, 10, "AAA", -1000, -1000),
            fila_xlsx(D2, "VENTA", 2, -5, "AAA", 750, -250),
            fila_xlsx(D3, "NUEVO", 3, 0, "BBB", 1e6, 999750, "revisar ficticio")])
        return carpeta

    def generar(self):
        entrega = crear_dashboard(self.punto, self.carpeta, "demo", lambda url: copy.deepcopy(PANELES[url.rsplit("/", 1)[-1]]))
        return entrega, (self.carpeta / "dashboard.html").read_text()

    def test_calcula_historial_sin_publicar_realizado_ni_alterar_base(self):
        self.extractos()
        base = (self.carpeta / "cartera.json").read_bytes()
        entrega, html = self.generar()
        self.assertFalse((self.carpeta / "realizado.csv").exists())
        self.assertFalse((self.carpeta / "mep_diario.csv").exists())
        self.assertEqual((self.carpeta / "cartera.json").read_bytes(), base)
        h = datos(html)["historial"]
        self.assertEqual(h["total_conocido"], 250)
        self.assertEqual(h["cantidad_sin_clasificar"], 1)
        self.assertEqual(h["sin_clasificar"][0]["comprobante"], "NUEVO")
        self.assertIn("revisar ficticio", html)
        self.assertIn('id="rendimiento-realizado"', html)

    def test_carpeta_vacia_genera_tablero_con_aviso(self):
        (self.carpeta / "extractos").mkdir()
        entrega, html = self.generar()
        self.assertNotIn("historial", datos(html))
        self.assertNotIn('id="rendimiento-realizado"', html)
        self.assertTrue(entrega["avisos"])
        self.assertFalse((self.carpeta / "realizado.csv").exists())

    def test_extractos_como_archivo_invalido_no_frena_tablero(self):
        (self.carpeta / "extractos").write_text("ficticio")
        entrega, html = self.generar()
        self.assertNotIn("historial", datos(html))
        self.assertTrue(any("rendimiento realizado" in aviso for aviso in entrega["avisos"]))

    def test_historial_no_cambia_calculo_del_dia_cero(self):
        _, previo = self.generar()
        self.extractos()
        _, posterior = self.generar()
        p, d = datos(previo), datos(posterior)
        for campo in ("integral", "dia_cero", "realizados", "conciliacion"):
            self.assertEqual(p[campo], d[campo])
        self.assertEqual([fila["cantidad"] for fila in p["posiciones"]], [fila["cantidad"] for fila in d["posiciones"]])


if __name__ == "__main__":
    unittest.main()
