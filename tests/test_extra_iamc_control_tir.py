"""Control experimental: casos sintéticos sin datos de cliente ni red."""
import copy
import math
import io
import os
import json
import tempfile
from pathlib import Path
from contextlib import redirect_stdout, redirect_stderr
from unittest.mock import patch
import unittest
from tools.iamc_control_tir import comparar, resolver_tir, main


def payload():
    return {"calc": {"ins": [{"tk": "DEMO", "g": "tp", "cur": "ARS", "px": 100,
            "liq": "2026-01-01", "f": [[365, 110, 0, 0]], "cal": 99999}]},
            "tp": {"fecha": "2025-12-31", "rows": [{"tk": "DEMO", "ytm": 10,
                   "mp": "ARS", "amo": [["2027-01-01", 110]], "ren": []}]},
            "on": {"rows": []}}


class ControlTIR(unittest.TestCase):
    def test_cupon_cero_conocido(self):
        tasa, residuo = resolver_tir([(365, 110)], 100)
        self.assertAlmostEqual(tasa, .1, places=12)
        self.assertAlmostEqual(residuo, 0, places=10)

    def test_varios_cupones_con_tir_conocida(self):
        tasa, residuo = resolver_tir([(365, 10), (730, 110)], 100)
        self.assertAlmostEqual(tasa, .1, places=12)
        self.assertAlmostEqual(residuo, 0, places=10)

    def test_tasa_negativa(self):
        self.assertAlmostEqual(resolver_tir([(365, 90)], 100)[0], -.1, places=12)

    def test_rechaza_datos_no_verificables(self):
        for flujos, precio in (([], 100), ([(0, 110)], 100), ([(365, -1)], 100),
                               ([(365, 0)], 100), ([(365, 110)], 0),
                               ([(365, math.inf)], 100), ([(365, 110)], True)):
            with self.subTest(flujos=flujos, precio=precio), self.assertRaises(ValueError):
                resolver_tir(flujos, precio)

    def test_compara_sin_usar_calibracion_ni_tasa_publicada(self):
        datos = payload()
        copia = copy.deepcopy(datos)
        caso = comparar(datos, ["DEMO"])["resultados"][0]
        self.assertEqual(caso["estado"], "coincide")
        self.assertLess(abs(caso["diferencia_pb"]), 1e-8)
        datos["tp"]["rows"][0]["ytm"] = 12
        caso = comparar(datos, ["DEMO"])["resultados"][0]
        self.assertEqual(caso["estado"], "difiere")
        self.assertAlmostEqual(caso["tir_recalculada_pct"], 10, places=10)
        self.assertAlmostEqual(caso["diferencia_pb"], -200, places=8)
        self.assertEqual(copia["calc"], datos["calc"])

    def test_ausente_no_es_cero_ni_sustituido(self):
        caso = comparar(payload(), ["AUSENTE"])["resultados"][0]
        self.assertEqual(caso["estado"], "sin_dato")
        self.assertNotIn("tir_recalculada_pct", caso)

    def test_detecta_flujos_distintos_entre_informe_y_calculadora(self):
        datos = payload()
        datos["tp"]["rows"][0]["amo"][0][1] = 108
        control = comparar(datos, ["DEMO"])["resultados"][0]["control_cruzado_flujo_informe"]
        self.assertTrue(control["supera_1_pb"])
        self.assertFalse(control["flujos_coinciden"])

    def test_no_muta_datos(self):
        datos = payload()
        copia = copy.deepcopy(datos)
        comparar(datos, ["DEMO"])
        self.assertEqual(datos, copia)


class ControlArchivos(unittest.TestCase):
    def preparar(self, carpeta):
        ruta = Path(carpeta) / "original.html"
        ruta.write_text('<script id="payload" type="application/json">' + json.dumps(payload()) + '</script>')
        return ruta

    def test_no_sobrescribe_html_original(self):
        with tempfile.TemporaryDirectory() as carpeta:
            original = self.preparar(carpeta)
            antes = original.read_bytes()
            with redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as error:
                main(["--html", str(original), "--salida", str(original)])
            self.assertEqual(error.exception.code, 1)
            self.assertEqual(original.read_bytes(), antes)

    def test_no_sobrescribe_otra_ruta_del_mismo_archivo(self):
        with tempfile.TemporaryDirectory() as carpeta:
            original = self.preparar(carpeta)
            otro = Path(carpeta) / "enlace.json"
            os.link(str(original), str(otro))
            antes = original.read_bytes()
            with redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
                main(["--html", str(original), "--salida", str(otro)])
            self.assertEqual(original.read_bytes(), antes)

    def test_fallo_de_publicacion_conserva_salida_anterior_y_original(self):
        with tempfile.TemporaryDirectory() as carpeta:
            original = self.preparar(carpeta)
            antes = original.read_bytes()
            salida = Path(carpeta) / "control.json"
            salida.write_text("versión anterior ficticia")
            with patch("tools.iamc_control_tir.os.replace", side_effect=OSError("falla ficticia")):
                with redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
                    main(["--html", str(original), "--salida", str(salida)])
            self.assertEqual(salida.read_text(), "versión anterior ficticia")
            self.assertEqual(original.read_bytes(), antes)
            self.assertEqual(sorted(p.name for p in Path(carpeta).iterdir()), ["control.json", "original.html"])


if __name__ == "__main__":
    unittest.main()
