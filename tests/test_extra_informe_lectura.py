"""Informe 1.3: presente, pasado y futuro separados y explicados (docs/INFORME.md). Datos ficticios.

Pedido de Felipe del 18/11/2026: una clienta sin experiencia no distinguía los cobros futuros de las ganancias
pasadas. El informe va en tres partes con su momento a la vista, y cada número dice qué es.
"""

import copy
import json
import re
import unittest
from decimal import Decimal
from pathlib import Path

from cartera.informe import armar_informe, informe_html, leer_datos_dashboard

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "informe"
D = Decimal


def cargar():
    datos = leer_datos_dashboard(FIXTURES / "dashboard.html")
    instrumentos = json.loads((FIXTURES / "instrumentos.json").read_text(encoding="utf-8"))
    return datos, instrumentos


def html(datos, instrumentos):
    return informe_html(armar_informe(datos, instrumentos))


def posicion(texto, buscado):
    indice = texto.find(buscado)
    if indice < 0:
        raise AssertionError("No está: " + buscado)
    return indice


class Orden(unittest.TestCase):
    def setUp(self):
        self.datos, self.instrumentos = cargar()
        self.h = html(self.datos, self.instrumentos)

    def test_presente_pasado_y_futuro_en_ese_orden(self):
        # La guía de la primera hoja nombra las partes: se buscan los títulos de cada sección.
        hitos = ['class="ts">1. Tu cartera hoy', "Tus títulos", 'class="ts">2. Lo que ya ganaste',
                 "De dónde sale la ganancia ya cobrada", 'class="ts">3. Lo que vas a ganar desde hoy<', "Próximos cobros",
                 "Rendimiento al precio de compra", "Cobros futuros por título", "Cobros futuros en dólares, año por año",
                 "Palabras que usamos"]
        indices = [posicion(self.h, hito) for hito in hitos]
        self.assertEqual(indices, sorted(indices))

    def test_cada_parte_dice_a_que_momento_mira(self):
        etiquetas = re.findall(r'<div class="seccion"><span class="tag">([^<]+)</span>', self.h)
        self.assertEqual(etiquetas, ["Hoy", "Hoy", "Hasta hoy", "De acá en adelante", "De acá en adelante"])
        self.assertIn("<b>Todavía no los cobraste</b>", self.h)

    def test_resumen_con_las_tres_partes_y_su_numero(self):
        guia = self.h.split('class="guia"')[1].split('<div class="seccion">')[0]
        self.assertIn("Este informe en tres partes", self.h)
        self.assertEqual(re.findall(r"<b>(\d)\. ([^<]+)</b>", guia),
                         [("1", "Tu cartera hoy"), ("2", "Lo que ya ganaste"), ("3", "Lo que vas a ganar desde hoy")])
        numeros = re.findall(r'<span class="gv">(.*?)</span>(?=[A-Z])', guia)
        self.assertEqual(numeros[0], "$ 2.010.000")      # patrimonio
        self.assertEqual(numeros[1], "$ 395.000")        # resultado total hasta hoy
        # Lo que se va a ganar, no el total a cobrar, y cada moneda por separado. En pesos falta la separación de
        # un título: sin dato, nunca la ganancia de los demás como si fuera toda.
        self.assertEqual(numeros[2], "sin dato <small>pesos</small><br>US$ 9,00 <small>MEP</small><br>"
                                     "US$ 3,50 <small>cable</small>")
        self.assertNotIn("Total a cobrar desde hoy", guia)

    def test_la_ganancia_que_depende_de_un_indice_se_marca(self):
        datos = copy.deepcopy(self.datos)
        tzv28 = [p for p in datos["flujo_fondos"]["posiciones"] if p["ticker"] == "TZV28"][0]
        tzv28["capital_pendiente"], tzv28["ganancia_pendiente"] = 50000.0, 20000.0
        m = armar_informe(datos, self.instrumentos)
        self.assertEqual(m["a_ganar"], {"ARS": D("60000.00"), "USD MEP": D("9.00"), "USD cable": D("3.50")})
        self.assertEqual(m["a_ganar_estimada"], {"ARS": True, "USD MEP": False, "USD cable": False})
        guia = informe_html(m).split('class="guia"')[1].split('<div class="seccion">')[0]
        self.assertIn("$ 60.000 <small>incluye estimados</small>", guia)

    def test_sin_historial_el_futuro_es_la_parte_dos(self):
        datos = copy.deepcopy(self.datos)
        del datos["historial"]
        h = html(datos, self.instrumentos)
        self.assertNotIn("Lo que ya ganaste", h)
        self.assertIn("2. Lo que vas a ganar desde hoy", h)
        self.assertEqual(len(re.findall(r"<b>\d\. ", h.split('class="guia"')[1].split('<div class="seccion">')[0])), 2)
        self.assertIn("Este informe en dos partes", h)

    def test_sin_renta_fija_no_hay_parte_de_cobros(self):
        datos = copy.deepcopy(self.datos)
        datos["flujo_fondos"]["posiciones"] = []
        datos["flujo_fondos"]["calendario"] = []
        datos["letras"]["posiciones"] = []
        h = html(datos, self.instrumentos)
        self.assertNotIn("Lo que vas a ganar", h)
        self.assertNotIn("Próximos cobros", h)
        self.assertNotIn("TIR", h.split("Palabras que usamos")[1])


class LoQueYaGanaste(unittest.TestCase):
    def setUp(self):
        self.datos, self.instrumentos = cargar()

    def test_la_ecuacion_suma(self):
        m = armar_informe(self.datos, self.instrumentos)
        r = m["resultados"]
        self.assertEqual(r["cobrada"] + r["tenencia"], r["acumulado"])
        h = informe_html(m)
        ecuacion = h.split('class="ecuacion">')[1].split('<h2>')[0]
        self.assertIn("Ganancia ya cobrada", ecuacion)
        self.assertIn("Suba de lo que todavía tenés", ecuacion)
        self.assertIn('<div class="op">+</div>', ecuacion)
        self.assertIn("Resultado total hasta hoy", ecuacion)
        self.assertIn("$ 395.000", ecuacion)

    def test_una_baja_resta_y_se_muestra_sin_signo(self):
        for p in self.datos["posiciones"]:
            p["resultado"] = -20000.0
        h = html(self.datos, self.instrumentos)
        ecuacion = h.split('class="ecuacion">')[1].split('<h2>')[0]
        self.assertIn("Baja de lo que todavía tenés", ecuacion)
        self.assertIn('<div class="op">−</div>', ecuacion)
        self.assertIn("$ 100.000", ecuacion)
        self.assertIn("$ 200.000", ecuacion)  # 300.000 − 100.000
        self.assertNotIn("$ -", ecuacion)

    def test_el_desglose_suma_la_ganancia_ya_cobrada(self):
        # Con ventas de lotes estimados y retenciones, el desglose tiene que cerrar igual.
        historial = self.datos["historial"]
        historial.update(total_conocido=345000.0, realizado_extracto=200000.0, realizado_estimado=45000.0)
        r = armar_informe(self.datos, self.instrumentos)["resultados"]
        self.assertEqual(r["ventas"], D("245000"))
        self.assertEqual(r["ventas"] + r["rentas_equivalente"] + r["otros"], r["cobrada"])

    def test_rentas_en_dolares_se_explican(self):
        h = html(self.datos, self.instrumentos)
        desglose = h.split('class="desglose">')[1].split("</ul>")[0]
        self.assertIn("incluidos US$ 20,00 convertidos al dólar MEP del día de cada cobro", desglose)
        self.assertIn("$ 80.000", desglose)

    def test_barras_con_titulo_y_explicacion(self):
        h = html(self.datos, self.instrumentos)
        self.assertIn("Ganancia o pérdida en lo que vendiste o venció", h)
        self.assertIn("hacia arriba, ganancia; hacia abajo, pérdida", h)


class LoQueVasACobrar(unittest.TestCase):
    def setUp(self):
        self.datos, self.instrumentos = cargar()

    def test_el_anio_en_curso_dice_desde_hoy(self):
        self.datos["generado_en"] = "2027-03-01T12:00:00-03:00"
        h = html(self.datos, self.instrumentos)
        grafico = h.split('aria-label="Cobros en dólares por año"')[1].split("</svg>")[0]
        self.assertIn(">2027</text>", grafico)
        self.assertIn(">desde hoy</text>", grafico)
        self.assertIn("No incluye lo que ya cobraste.", h)
        self.assertIn("2027 muestra solo lo que falta cobrar desde el 1 mar 2027", h)

    def test_sin_cobros_en_el_anio_en_curso_no_lo_aclara(self):
        h = html(self.datos, self.instrumentos)  # 16 nov 2026: los cobros en dólares empiezan en 2027
        grafico = h.split('aria-label="Cobros en dólares por año"')[1].split("</svg>")[0]
        self.assertNotIn("desde hoy", grafico)
        self.assertNotIn("muestra solo lo que falta cobrar", h)

    def test_nombres_que_dicen_que_es_futuro(self):
        h = html(self.datos, self.instrumentos)
        for texto in ("Cobros futuros por título", "Total a cobrar desde hoy", "Cobros futuros en dólares, año por año",
                      "<b>Renta</b>: intereses", "<b>Vencimiento</b>: el último pago"):
            self.assertIn(texto, h)


class Glosario(unittest.TestCase):
    def test_solo_las_palabras_de_esta_cartera(self):
        datos, instrumentos = cargar()
        glosario = html(datos, instrumentos).split('class="glosario">')[1].split("</dl>")[0]
        for termino in ("TIR", "Renta", "Amortización", "Dólar MEP", "Dólar cable", "CEDEAR", "LECAP y BONCAP",
                        "Obligación negociable", "Dólar linked", "Ganancia ya cobrada"):
            self.assertIn("<dt>{}</dt>".format(termino), glosario)
        for ausente in ("TAMAR", "CER"):
            self.assertNotIn("<dt>{}</dt>".format(ausente), glosario)

    def test_cedears_siguen_al_dolar(self):
        datos, instrumentos = cargar()
        h = html(datos, instrumentos)
        self.assertIn("Los CEDEARs (7,5 %) cotizan en pesos, pero su precio sigue al dólar.", h)


if __name__ == "__main__":
    unittest.main()
