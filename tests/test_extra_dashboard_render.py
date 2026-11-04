"""Integridad y presentación de la vista HTML, sin consultar la red."""

import datetime as dt
import json
import math
import re
import unittest
from zoneinfo import ZoneInfo

from cartera.calculos import resultado_posicion, resumen_cartera
from cartera.dashboard import generar_html
from cartera.precios import Cotizacion
from cartera.punto_partida import Lote, Posicion


T = dt.datetime(2026, 11, 4, 12, tzinfo=ZoneInfo("America/Argentina/Buenos_Aires"))


def datos(html):
    return json.loads(re.search(r'<script id="datos-cartera" type="application/json">(.*?)</script>', html, re.S).group(1))


class RenderDashboard(unittest.TestCase):
    def generar(self, posiciones=True, precio=1200, nombre="Demo", especie="Bono Demo", efectivo=None, puntos=None, niveles=None):
        posicion = Posicion("BOND1", especie, "bono", 1000, 100)
        lote = Lote("BOND1", 1000, "estimado", T.date(), 1000, 10000, "")
        resultado = resultado_posicion(posicion, [lote], precio, 1000)
        cotizacion = Cotizacion("BOND1", precio, precio - 10 if precio else None, None, 1.5, "vivo" if precio else "sin_dato", T)
        return generar_html(
            cliente={"slug": "demo", "nombre": nombre}, resultados=[resultado],
            resumen=resumen_cartera([resultado]), cotizaciones={"BOND1": cotizacion},
            niveles=niveles or {}, instrumentos={}, efectivo=efectivo or {},
            historial={"BOND1": puntos or []}, generado_en=T,
            posiciones=([posicion] if posiciones else None) if isinstance(posiciones, bool) else posiciones,
        )

    def test_json_escapa_cierre_script_y_conserva_texto(self):
        texto = '</script><script>alert("prueba")</script>&'
        html = self.generar(nombre=texto, especie=texto)
        self.assertNotIn('<script>alert(', html)
        self.assertIn('\\u003c/script>', html)
        self.assertEqual(datos(html)["posiciones"][0]["especie"], texto)
        self.assertEqual(datos(html)["cliente"]["nombre"], texto)

    def test_sin_posiciones_preserva_valuacion_y_es_estatico(self):
        html = self.generar(posiciones=False)
        d = datos(html)
        self.assertFalse(d["actualizacion_habilitada"])
        self.assertIsNone(d["posiciones"][0]["cantidad"])
        self.assertEqual(d["posiciones"][0]["valuacion"], 12000)
        self.assertIn('id="actualizar" type="button" disabled', html)
        self.assertIn('12.000,00', html)

    def test_lista_de_posiciones_incompleta_no_habilita_consultas(self):
        html = self.generar(posiciones=[])
        self.assertFalse(datos(html)["actualizacion_habilitada"])
        self.assertIsNone(datos(html)["posiciones"][0]["cantidad"])
        self.assertIn('id="actualizar" type="button" disabled', html)

    def test_importes_embebidos_no_se_presentan_como_confirmados_en_vivo(self):
        html = self.generar()
        tabla = re.search(r'<tbody id="posiciones-body">(.*?)</tbody>', html, re.S).group(1)
        self.assertIn("Último dato", tabla)
        self.assertNotIn("En vivo", tabla)
        self.assertEqual(datos(html)["posiciones"][0]["estado"], "vivo")

    def test_valor_por_cien_y_variacion_diaria_en_puntos(self):
        html = self.generar()
        fila = datos(html)["posiciones"][0]
        self.assertEqual(fila["valuacion"], 12000)
        self.assertIn('1,50 %', html)
        self.assertNotIn('150,00 %', html)

    def test_efectivo_cero_y_deudor_no_entran_en_valuacion(self):
        html = self.generar(efectivo={"ARS": -1000, "USD": 0})
        d = datos(html)
        self.assertEqual(d["efectivo"]["ARS"], -1000)
        self.assertEqual(d["efectivo"]["USD"], 0)
        self.assertEqual(d["posiciones"][0]["valuacion"], 12000)
        self.assertIn('-1.000,00', html)

    def test_sin_precios_no_fabrica_valuacion_total(self):
        html = self.generar(precio=None)
        self.assertIsNone(datos(html)["posiciones"][0]["valuacion"])
        total = re.search(r'<tbody id="totales-body">(.*?)</tbody>', html, re.S).group(1)
        self.assertIn('sin dato', total)
        self.assertNotIn('0,00', total)

    def test_grafico_plano_y_limite_de_puntos_no_rompen_svg(self):
        puntos = [(T + dt.timedelta(minutes=i), 1000) for i in range(600)]
        html = self.generar(puntos=puntos)
        linea = re.search(r'<polyline points="([^"]+)"', html).group(1)
        self.assertEqual(len(linea.split()), 500)
        self.assertNotRegex(linea.lower(), r'nan|inf')
        self.assertIn('historial capturado', html.lower())

    def test_niveles_usan_bid_para_distancia(self):
        html = self.generar(niveles={"BOND1": {"take_profit": 1500, "stop_loss": None}})
        # Referencia 1190: 1500/1190 - 1 = 26,05%.
        self.assertIn('26,05 %', html)
        self.assertIsNone(datos(html)["posiciones"][0]["stop_loss"])

    def test_csp_autocontenido_y_contenedor_de_tabla(self):
        html = self.generar()
        self.assertIn("default-src 'none'", html)
        self.assertIn('connect-src https://data912.com', html)
        self.assertIn('overflow-x:auto', html)
        self.assertNotIn('innerHTML', html)
        self.assertNotIn('localStorage', html)
        self.assertIn('Se calcula cuando estén los movimientos.', html)


if __name__ == "__main__":
    unittest.main()
