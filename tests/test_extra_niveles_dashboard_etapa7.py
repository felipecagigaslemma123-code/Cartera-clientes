"""Alertas del tablero: no aceptar configuraciones ambiguas ni silenciarlas."""

import json
import tempfile
import unittest
from pathlib import Path

from cartera.almacenamiento import importar_cartera
from cartera.dashboard_archivos import crear_dashboard
from test_etapa5_comando import DIA_CERO, ENCABEZADO, PANELES, datos_de

DEMO = Path(__file__).resolve().parents[1] / "fixtures" / "punto_partida_demo.xlsx"


class NivelesDelDashboard(unittest.TestCase):
    def setUp(self):
        temporal = tempfile.TemporaryDirectory()
        self.addCleanup(temporal.cleanup)
        self.datos = Path(temporal.name) / "datos"
        self.base, _ = importar_cartera(self.datos, "demo", DEMO)
        self.carpeta = self.datos / "clientes" / "demo"
        self.llamadas = []
        (self.carpeta / "dia_cero.json").write_text(json.dumps(DIA_CERO), encoding="utf-8")

    def fetch(self, url):
        self.llamadas.append(url)
        return PANELES[url.rsplit("/", 1)[-1]]

    def arbol(self):
        return {p.name: (p.read_bytes(), p.stat().st_mtime_ns) for p in self.carpeta.iterdir() if p.is_file()}

    def rechazar(self, niveles):
        (self.carpeta / "niveles.json").write_text(json.dumps(niveles), encoding="utf-8")
        (self.carpeta / "dashboard.html").write_text("Tablero ficticio previo", encoding="utf-8")
        (self.carpeta / "cache_precios.json").write_text("{}", encoding="utf-8")
        antes = self.arbol()
        with self.assertRaises(ValueError) as error:
            crear_dashboard(self.base, self.carpeta, "demo", self.fetch)
        self.assertIn("niveles.json", str(error.exception))
        self.assertEqual(self.llamadas, [])
        self.assertEqual(self.arbol(), antes)

    def test_take_profit_no_puede_ser_menor_que_stop_loss(self):
        self.rechazar({"AAA": {"take_profit": 1000, "stop_loss": 2000}})

    def test_take_profit_igual_a_stop_loss_no_dispara_dos_eventos(self):
        self.rechazar({"AAA": {"take_profit": 1000, "stop_loss": 1000}})

    def test_ticker_desconocido_no_desaparece_como_si_no_hubiera_niveles(self):
        self.rechazar({"ZZZ": {"stop_loss": 5000}})

    def test_clave_mal_escrita_no_deja_un_nivel_sin_control_en_silencio(self):
        self.rechazar({"AAA": {"takeprofit": 5000}})

    def test_especie_conocida_totalmente_vendida_se_ignora_con_aviso(self):
        (self.carpeta / "movimientos.csv").write_text(
            ENCABEZADO + "\n2026-10-10,venta,AAA,100,120000,ARS,,,\n", encoding="utf-8")
        (self.carpeta / "niveles.json").write_text(json.dumps({
            "AAA": {"takeprofit": "viejo"}, "BBB": {"stop_loss": 5000}}), encoding="utf-8")
        salida = crear_dashboard(self.base, self.carpeta, "demo", self.fetch)
        self.assertTrue(any("AAA" in a and "ignorado" in a for a in salida["avisos"]))
        html = salida["ruta"].read_text(encoding="utf-8")
        datos = datos_de(html)
        self.assertNotIn("AAA", [p["ticker"] for p in datos["posiciones"]])
        self.assertEqual(next(p for p in datos["posiciones"] if p["ticker"] == "BBB")["stop_loss"], 5000)
        self.assertIn('id="alertas-panel"', html)


if __name__ == "__main__":
    unittest.main()
