"""Datos opcionales extremos y advertencias de la generación del tablero."""

import contextlib
import csv
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from cartera.__main__ import main
from cartera.almacenamiento import importar_cartera


DEMO = Path(__file__).resolve().parents[1] / "fixtures" / "punto_partida_demo.xlsx"


class IntegridadDashboard(unittest.TestCase):
    def setUp(self):
        self.temporal = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporal.cleanup)
        self.datos = Path(self.temporal.name) / "datos"
        importar_cartera(self.datos, "demo", DEMO)
        self.carpeta = self.datos / "clientes" / "demo"
        self.salida = self.carpeta / "dashboard.html"

    def correr(self, fetch):
        salida, errores = io.StringIO(), io.StringIO()
        with patch("cartera.__main__.consultar_json", side_effect=fetch):
            with contextlib.redirect_stdout(salida), contextlib.redirect_stderr(errores):
                codigo = main(["--datos", str(self.datos), "dashboard", "--cliente", "demo"])
        return codigo, salida.getvalue(), errores.getvalue()

    def test_nivel_fuera_de_rango_falla_antes_de_red_y_sin_tocar_html(self):
        self.salida.write_text("versión anterior", encoding="utf-8")
        (self.carpeta / "niveles.json").write_text(json.dumps({"AAA": {"take_profit": 10 ** 400}}))
        llamadas = []
        def fetch(url):
            llamadas.append(url)
            return []
        codigo, _, errores = self.correr(fetch)
        self.assertNotEqual(codigo, 0)
        self.assertIn("niveles.json", errores)
        self.assertNotIn("Traceback", errores)
        self.assertEqual(llamadas, [])
        self.assertEqual(self.salida.read_text(encoding="utf-8"), "versión anterior")
        self.assertFalse((self.carpeta / "cache_precios.json").exists())

    def test_historial_invalido_se_omite_con_aviso_y_se_conserva_archivo(self):
        historial = self.carpeta / "historial.csv"
        with historial.open("w", encoding="utf-8", newline="") as archivo:
            escritor = csv.writer(archivo)
            escritor.writerow(["consultado_en", "ticker", "ultimo", "bid", "ask"])
            escritor.writerow(["2026-11-04T12:00:00-03:00", "AAA", "1100", "", ""])
            escritor.writerow(["fecha rota", "AAA", "1200", "", ""])
            escritor.writerow(["2026-11-04T12:00:00-03:00", "AAA", "NaN", "", ""])
            escritor.writerow(["2026-11-04T12:00:00-03:00", "MEP", "1500", "", ""])
        previo = historial.read_bytes()
        codigo, salida, errores = self.correr(lambda url: [])
        self.assertEqual(codigo, 0, errores)
        self.assertIn("2 filas inválidas", salida)
        self.assertIn("2 filas inválidas", self.salida.read_text(encoding="utf-8"))
        self.assertEqual(historial.read_bytes(), previo)

    def test_aviso_mep_no_afirma_indisponibilidad_despues_de_generar(self):
        codigo, salida, errores = self.correr(lambda url: [])
        self.assertEqual(codigo, 0, errores)
        self.assertIn("Al generar el archivo", salida)
        self.assertIn("el navegador intentará obtenerlo", salida)
        self.assertNotIn("los totales en dólares no están disponibles", self.salida.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
