"""Etapa 12: informe para el cliente a partir del dashboard (docs/INFORME.md)."""

import copy
import datetime as dt
import io
import json
import re
import shutil
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from decimal import Decimal
from pathlib import Path
from unittest import mock

from cartera.__main__ import main
from cartera.informe import ErrorInforme, armar_informe, exportar_pdf, informe_html, leer_datos_dashboard

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "informe"
D = Decimal


def cargar():
    datos = leer_datos_dashboard(FIXTURES / "dashboard.html")
    instrumentos = json.loads((FIXTURES / "instrumentos.json").read_text(encoding="utf-8"))
    perfil = json.loads((FIXTURES / "perfil.json").read_text(encoding="utf-8"))
    return datos, instrumentos, perfil


class Lectura(unittest.TestCase):
    def test_lee_el_bloque_del_dashboard(self):
        datos = leer_datos_dashboard(FIXTURES / "dashboard.html")
        self.assertEqual(datos["cliente"]["nombre"], "Cliente Demo")

    def test_errores(self):
        with tempfile.TemporaryDirectory() as carpeta:
            sin_bloque = Path(carpeta) / "dashboard.html"
            sin_bloque.write_text("<html><body>sin datos</body></html>", encoding="utf-8")
            for ruta in (Path(carpeta) / "no-existe.html", sin_bloque):
                with self.assertRaises(ErrorInforme):
                    leer_datos_dashboard(ruta)


class Modelo(unittest.TestCase):
    def setUp(self):
        self.datos, self.instrumentos, self.perfil = cargar()
        self.m = armar_informe(self.datos, self.instrumentos, self.perfil)

    def test_resumen(self):
        m = self.m
        self.assertEqual((m["cliente"], m["asesor"], m["fecha"]), ("Cliente Demo", "Asesor Demo", dt.date(2026, 11, 16)))
        self.assertEqual(m["patrimonio"], D("2010000"))
        self.assertEqual(m["invertido"], D("2000000"))
        self.assertEqual(m["efectivo"], {"ARS": D("10000"), "USD": D("0")})
        self.assertEqual(m["mep"], D("1500"))

    def test_composicion_por_clase_desde_los_datos(self):
        clases = [(c["clase"], c["valuacion"], c["tickers"]) for c in self.m["composicion"]]
        self.assertEqual(clases, [
            ("Bonos en dólares", D("1000000"), ["AL30"]),
            ("Letras y BONCAP en pesos", D("640000"), ["S30N6"]),
            ("CEDEARs", D("150000"), ["SPY"]),
            ("Obligaciones negociables en dólares", D("150000"), ["YM34O"]),
            ("Dólar linked", D("60000"), ["TZV28"]),
        ])
        self.assertEqual(self.m["composicion"][0]["peso"], D("0.5"))
        self.assertEqual(self.m["peso_dolares"], D("0.575"))

    def test_la_clase_no_depende_del_ticker(self):
        instrumentos = copy.deepcopy(self.instrumentos)
        instrumentos["TZV28"]["iamc"]["indice"]["tipo"] = "CER"
        clases = {c["clase"] for c in armar_informe(self.datos, instrumentos, self.perfil)["composicion"]}
        self.assertIn("Ajustables por CER", clases)
        self.assertNotIn("Dólar linked", clases)
        sin_instrumentos = {c["clase"]: c["tickers"] for c in armar_informe(self.datos)["composicion"]}
        self.assertEqual(sin_instrumentos["Bonos en pesos"], ["TZV28"])

    def test_tenencia(self):
        filas = {f["ticker"]: f for f in self.m["tenencia"]}
        self.assertEqual([f["ticker"] for f in self.m["tenencia"]], ["AL30", "S30N6", "SPY", "YM34O", "TZV28"])
        self.assertEqual(filas["S30N6"]["descripcion"], "LECAP 30/11/2026")
        self.assertEqual(filas["AL30"]["descripcion"], "Bono Demo USD 2030")
        self.assertAlmostEqual(float(filas["AL30"]["vs_compra"]), 50000 / 950000, places=12)
        self.assertEqual(filas["AL30"]["peso"], D("0.5"))
        self.assertEqual(filas["SPY"]["vencimiento"], None)
        self.assertEqual(filas["TZV28"]["vencimiento"], dt.date(2028, 6, 30))

    def test_tir_ponderada_por_inversion_y_rango(self):
        r = {x["ticker"]: x for x in self.m["rendimientos"]}
        self.assertEqual([x["ticker"] for x in self.m["rendimientos"]], ["AL30", "YM34O", "S30N6", "TZV28"])
        self.assertEqual((r["AL30"]["tir"], r["AL30"]["tir_min"], r["AL30"]["tir_max"]), (D("0.12"), D("0.10"), D("0.15")))
        self.assertEqual((r["AL30"]["moneda"], r["AL30"]["compras"], r["AL30"]["estimada"]), ("USD MEP", 2, False))
        self.assertAlmostEqual(float(r["S30N6"]["tir"]), (0.25 * 360000 + 0.30 * 250000) / 610000, places=12)
        self.assertEqual(r["S30N6"]["moneda"], "ARS")
        self.assertTrue(r["TZV28"]["estimada"])
        self.assertEqual(r["AL30"]["proximo_pago"], {"fecha": dt.date(2027, 1, 9), "importe": D("45.00")})
        self.assertEqual(r["S30N6"]["proximo_pago"], {"fecha": dt.date(2026, 11, 30), "importe": D("650000.00")})

    def test_compras_sin_tir(self):
        datos = copy.deepcopy(self.datos)
        compras = datos["flujo_fondos"]["posiciones"][0]["compras"]
        compras[1]["tir"] = None
        r = armar_informe(datos, self.instrumentos)["rendimientos"][0]
        self.assertEqual((r["tir"], r["tir_min"], r["tir_max"]), (D("0.10"), D("0.10"), D("0.10")))
        for compra in compras:
            compra["tir"] = None
        self.assertIsNone(armar_informe(datos, self.instrumentos)["rendimientos"][0]["tir"])

    def test_a_cobrar_nunca_suma_monedas(self):
        self.assertEqual(self.m["a_cobrar"], {"ARS": D("720000.00"), "USD MEP": D("89.00"), "USD cable": D("3.50")})

    def test_proximos_cobros(self):
        cobros = [(c["fecha"], c["ticker"], c["concepto"], c["moneda"], c["importe"], c["estimado"])
                  for c in self.m["proximos_cobros"]]
        self.assertEqual(cobros, [
            (dt.date(2026, 11, 30), "S30N6", "Vencimiento", "ARS", D("650000.00"), False),
            (dt.date(2027, 1, 9), "AL30", "Renta y amortización", "USD MEP", D("45.00"), False),
            (dt.date(2027, 4, 28), "YM34O", "Renta", "USD cable", D("3.50"), False),
            (dt.date(2027, 7, 9), "AL30", "Renta y amortización", "USD MEP", D("44.00"), False),
            (dt.date(2028, 6, 30), "TZV28", "Vencimiento", "ARS", D("70000.00"), True),
        ])
        self.assertEqual(len(armar_informe(self.datos, self.instrumentos, cantidad_cobros=2)["proximos_cobros"]), 2)

    def test_cobros_por_anio(self):
        self.assertEqual(self.m["cobros_por_anio"], {
            "2026": {"ARS": D("650000.00")},
            "2027": {"USD MEP": D("89.00"), "USD cable": D("3.50")},
            "2028": {"ARS": D("70000.00")},
        })

    def test_resultados(self):
        r = self.m["resultados"]
        self.assertEqual(r["ganancia_realizada"], D("300000"))
        self.assertEqual(r["ventas"], D("200000"))
        self.assertEqual((r["rentas_ars"], r["rentas_usd"], r["rentas_equivalente"]), (D("50000"), D("20"), D("80000")))
        self.assertEqual(r["otros"], D("20000"))
        self.assertEqual(r["acumulado"], D("2010000") - D("3000000") + D("1200000"))
        self.assertEqual([o["ticker"] for o in r["operaciones"]], ["TX26", "S31O5"])
        self.assertEqual(r["operaciones"][1], {"ticker": "S31O5", "fecha": dt.date(2025, 10, 31), "resultado": D("-10000")})

    def test_datos_faltantes_no_se_inventan(self):
        datos = copy.deepcopy(self.datos)
        datos["integral"]["patrimonio_final"] = None
        del datos["historial"]
        m = armar_informe(datos, self.instrumentos)
        self.assertIsNone(m["patrimonio"])
        self.assertIsNone(m["resultados"])
        self.assertIsNone(m["asesor"])
        self.assertEqual(m["cliente"], "Cliente Demo")
        del datos["integral"]
        self.assertIsNone(armar_informe(datos)["efectivo"])


class Html(unittest.TestCase):
    def setUp(self):
        datos, instrumentos, perfil = cargar()
        self.datos, self.instrumentos = datos, instrumentos
        self.html = informe_html(armar_informe(datos, instrumentos, perfil))

    def test_autosuficiente_e_imprimible(self):
        self.assertNotRegex(self.html, r"(?i)<script|<link|@import|https?://")
        self.assertIn("size:A4", self.html.replace(" ", ""))
        self.assertIn("@media screen", self.html)
        self.assertNotRegex(self.html, r"@media\s*\(max-width")
        self.assertEqual(self.html.count("<svg"), 4)  # dona, TIR, cobros por año, resultados

    def test_textos_y_formato(self):
        h = self.html
        for texto in ("Asesor Demo", "Cliente Demo", "16 nov 2026", "$ 2.010.000", "57,5 %", "Uso exclusivo del cliente",
                      "no constituye una recomendación de inversión", "sin ajuste por inflación", "estimada",
                      "LECAP 30/11/2026", "US$ 89,00", "US$ 3,50", "$ 720.000"):
            self.assertIn(texto, h)

    def test_sin_dato_y_secciones_vacias(self):
        datos = copy.deepcopy(self.datos)
        datos["integral"]["patrimonio_final"] = None
        del datos["historial"]
        h = informe_html(armar_informe(datos, self.instrumentos))
        self.assertIn("sin dato", h)
        self.assertNotIn("Resultados desde el inicio", h)
        self.assertEqual(h.count("<svg"), 3)

    def test_escapa_los_textos(self):
        datos = copy.deepcopy(self.datos)
        datos["posiciones"][3]["especie"] = "<b>CEDEAR & Co</b>"
        h = informe_html(armar_informe(datos, self.instrumentos))
        self.assertIn("&lt;b&gt;CEDEAR &amp; Co&lt;/b&gt;", h)


class Pdf(unittest.TestCase):
    def test_sin_navegador(self):
        with tempfile.TemporaryDirectory() as carpeta:
            html = Path(carpeta) / "informe.html"
            html.write_text("<html></html>", encoding="utf-8")
            with self.assertRaises(ErrorInforme):
                exportar_pdf(html, Path(carpeta) / "informe.pdf", navegador=Path(carpeta) / "no-existe")
            self.assertFalse((Path(carpeta) / "informe.pdf").exists())


class Comando(unittest.TestCase):
    def setUp(self):
        temporal = tempfile.TemporaryDirectory()
        self.addCleanup(temporal.cleanup)
        self.datos = Path(temporal.name)
        self.carpeta = self.datos / "clientes" / "demo"
        self.carpeta.mkdir(parents=True)
        for nombre in ("dashboard.html", "instrumentos.json", "perfil.json"):
            shutil.copyfile(FIXTURES / nombre, self.carpeta / nombre)

    def correr(self, *argumentos):
        salida, errores = io.StringIO(), io.StringIO()
        with redirect_stdout(salida), redirect_stderr(errores):
            codigo = main(["--datos", str(self.datos), "informe", "--cliente", "demo"] + list(argumentos))
        return codigo, salida.getvalue(), errores.getvalue()

    def test_escribe_el_informe_en_la_carpeta_del_cliente(self):
        codigo, salida, _ = self.correr()
        self.assertEqual(codigo, 0)
        ruta = self.carpeta / "informes" / "informe-2026-11-16.html"
        self.assertTrue(ruta.exists())
        self.assertIn("Cliente Demo", ruta.read_text(encoding="utf-8"))
        self.assertIn(str(ruta), salida)

    def test_salida_elegida(self):
        destino = self.datos / "otra"
        self.assertEqual(self.correr("--salida", str(destino))[0], 0)
        self.assertTrue((destino / "informe-2026-11-16.html").exists())

    def test_sin_dashboard_no_escribe_nada(self):
        (self.carpeta / "dashboard.html").unlink()
        codigo, _, errores = self.correr()
        self.assertNotEqual(codigo, 0)
        self.assertIn("dashboard", errores)
        self.assertFalse((self.carpeta / "informes").exists())

    def test_pdf_sin_chrome_deja_el_html_y_falla(self):
        with mock.patch("cartera.informe._NAVEGADOR", self.datos / "no-existe"):
            codigo, _, errores = self.correr("--pdf")
        self.assertNotEqual(codigo, 0)
        self.assertTrue((self.carpeta / "informes" / "informe-2026-11-16.html").exists())
        self.assertFalse((self.carpeta / "informes" / "informe-2026-11-16.pdf").exists())
        self.assertRegex(errores, r"(?i)chrome|navegador")

    def test_avisa_un_dashboard_viejo(self):
        with mock.patch("cartera.informe._hoy", return_value=dt.date(2026, 11, 25)):
            codigo, salida, errores = self.correr()
        self.assertEqual(codigo, 0)
        self.assertRegex(salida + errores, r"9 días")


if __name__ == "__main__":
    unittest.main()
