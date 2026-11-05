"""Fronteras de integración de movimientos; solo datos y canales ficticios."""

import copy
import datetime as dt
import io
import json
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import patch

from cartera.__main__ import main
from cartera.alertas_comando import correr_alertas
from cartera.almacenamiento import importar_cartera
from test_etapa5_comando import ABIERTO, DIA_CERO, ENCABEZADO, PANELES, datos_de

DEMO = Path(__file__).resolve().parents[1] / "fixtures" / "punto_partida_demo.xlsx"


class IntegracionMovimientos(unittest.TestCase):
    def setUp(self):
        temporal = tempfile.TemporaryDirectory()
        self.addCleanup(temporal.cleanup)
        self.datos = Path(temporal.name) / "datos"
        self.base, _ = importar_cartera(self.datos, "demo", DEMO)
        self.carpeta = self.datos / "clientes" / "demo"
        self.csv = self.carpeta / "movimientos.csv"
        (self.carpeta / "dia_cero.json").write_text(json.dumps(DIA_CERO), encoding="utf-8")
        self.consultas = []

    def fetch(self, url):
        self.consultas.append(url)
        return copy.deepcopy(PANELES[url.rsplit("/", 1)[-1]])

    def cli(self, comando, *argumentos):
        salida, errores = io.StringIO(), io.StringIO()
        with patch("cartera.__main__.consultar_json", side_effect=self.fetch), redirect_stdout(salida), redirect_stderr(errores):
            codigo = main(["--datos", str(self.datos), comando, "--cliente", "demo", *argumentos])
        return codigo, salida.getvalue(), errores.getvalue()

    def arbol(self):
        return {str(p.relative_to(self.carpeta)): (p.read_bytes(), p.stat().st_mtime_ns)
                for p in self.carpeta.rglob("*") if p.is_file()}

    def cargar(self, tipo, ticker="", cantidad="", importe="1", fecha="2026-10-10", **campos):
        argumentos = ["--tipo", tipo, "--fecha", fecha, "--importe", importe]
        for clave, valor in dict(ticker=ticker, cantidad=cantidad, **campos).items():
            if valor != "":
                argumentos.extend(["--" + clave.replace("_", "-"), valor])
        codigo, _, errores = self.cli("movimiento", *argumentos)
        self.assertEqual(codigo, 0, errores)

    def test_csv_semanticamente_invalido_no_consulta_ni_escribe_en_ninguna_salida(self):
        self.csv.write_text(ENCABEZADO + "\n2026-10-10,venta,AAA,101,120000,ARS,,,\n", encoding="utf-8")
        antes = self.arbol()
        for comando in ("estado", "capturar", "dashboard"):
            with self.subTest(comando=comando):
                codigo, _, errores = self.cli(comando)
                self.assertEqual(codigo, 1)
                self.assertTrue(errores.strip())
                self.assertEqual(self.consultas, [])
                self.assertEqual(self.arbol(), antes)

    def test_fijar_rechaza_fecha_que_alcanza_movimientos_antes_de_consultar(self):
        self.cargar("deposito")
        antes = self.arbol()
        codigo, _, _ = self.cli("fijar-dia-cero", "--fecha", "2026-10-10", "--forzar")
        self.assertEqual(codigo, 1)
        self.assertEqual(self.consultas, [])
        self.assertEqual(self.arbol(), antes)

    def test_fijar_rechaza_csv_roto_antes_de_consultar(self):
        self.csv.write_text("a,b\n", encoding="utf-8")
        antes = self.arbol()
        codigo, _, _ = self.cli("fijar-dia-cero", "--fecha", "2026-10-02", "--forzar")
        self.assertEqual(codigo, 1)
        self.assertEqual(self.consultas, [])
        self.assertEqual(self.arbol(), antes)

    def test_fijar_usa_base_importada_aunque_haya_ventas(self):
        self.cargar("venta", "AAA", "100", "120000")
        base_antes = (self.carpeta / "cartera.json").read_bytes()
        csv_antes = self.csv.read_bytes()
        codigo, _, errores = self.cli("fijar-dia-cero", "--fecha", "2026-10-05", "--forzar")
        self.assertEqual(codigo, 0, errores)
        foto = json.loads((self.carpeta / "dia_cero.json").read_text())
        self.assertEqual(foto["cantidades"], DIA_CERO["cantidades"])
        self.assertEqual(foto["precios"]["AAA"], 1200)
        self.assertEqual((self.carpeta / "cartera.json").read_bytes(), base_antes)
        self.assertEqual(self.csv.read_bytes(), csv_antes)

    def test_cartera_completamente_vendida_no_necesita_paneles_de_especies(self):
        for ticker, cantidad in DIA_CERO["cantidades"].items():
            self.cargar("venta", ticker, str(cantidad), "100000")
        codigo, _, errores = self.cli("dashboard")
        self.assertEqual(codigo, 0, errores)
        datos = datos_de((self.carpeta / "dashboard.html").read_text())
        self.assertEqual(datos["posiciones"], [])
        self.assertEqual(self.consultas, ["https://data912.com/live/mep"])
        self.assertEqual(datos["integral"]["valuacion_final"], 0)
        self.assertEqual(datos["integral"]["patrimonio_inicial"], 2580000)
        self.assertEqual(datos["integral"]["patrimonio_final"], 610000)
        self.assertEqual(datos["integral"]["total"], -1970000)

    def test_estado_con_venta_conserva_base_para_patrimonio_y_no_consulta(self):
        self.cargar("venta", "AAA", "100", "120000")
        antes = self.arbol()
        codigo, salida, errores = self.cli("estado")
        self.assertEqual(codigo, 0, errores)
        self.assertIn("2.580.000,00", salida)
        self.assertIn("130.000,00", salida)
        self.assertIn("15.400,00", salida)
        self.assertEqual(self.consultas, [])
        self.assertEqual(self.arbol(), antes)

    def test_numeros_cli_invalidos_son_codigo_uno_sin_escritura(self):
        antes = self.arbol()
        for campo, valor in (("importe", "1.234,56"), ("cantidad", "1,5"), ("tc", "1.500,50")):
            argumentos = dict(tipo="compra", fecha="2026-10-10", ticker="AAA", cantidad="1", importe="1")
            argumentos[campo] = valor
            lista = [x for clave, valor in argumentos.items() for x in ("--" + clave, valor)]
            codigo, _, errores = self.cli("movimiento", *lista)
            self.assertEqual(codigo, 1)
            self.assertTrue(errores.strip())
            self.assertEqual(self.arbol(), antes)

    def test_alertas_no_evaluan_vencimientos_de_tenencia_vendida(self):
        self.cargar("venta", "BOND1", "1000", "1600000")
        (self.carpeta / "instrumentos.json").write_text(json.dumps({"BOND1": {"vencimiento": "2026-11-05"}}))
        eventos = []
        entrega = correr_alertas(self.carpeta, self.base, "demo", self.fetch,
                                 [lambda titulo, mensaje: eventos.append(mensaje)], ABIERTO)
        self.assertNotIn(("vencimiento", "BOND1"), [(e.tipo, e.ticker) for e in entrega["eventos"]])

    def test_especie_nueva_totalmente_vendida_se_ignora_sin_apagar_niveles(self):
        self.cargar("compra", "NUE", "1", "400", tipo_activo="cedear", fecha="2026-10-02")
        self.cargar("venta", "NUE", "1", "500", fecha="2026-10-03")
        (self.carpeta / "niveles.json").write_text(json.dumps({"NUE": {"stop_loss": 1000}, "AAA": {"stop_loss": 5000}}))
        entrega = correr_alertas(self.carpeta, self.base, "demo", self.fetch, [lambda *a: None], ABIERTO)
        self.assertTrue(entrega["evaluo_niveles"])
        self.assertIn(("stop_loss", "AAA"), [(e.tipo, e.ticker) for e in entrega["eventos"]])
        self.assertNotIn(("stop_loss", "NUE"), [(e.tipo, e.ticker) for e in entrega["eventos"]])
        self.assertTrue(any("NUE" in a for a in entrega["avisos"]))

    def test_error_movimientos_alertas_queda_persistido_y_se_repite_otro_dia(self):
        self.csv.write_text("a,b\n", encoding="utf-8")
        for instante in (ABIERTO, ABIERTO + dt.timedelta(minutes=5), ABIERTO + dt.timedelta(days=1)):
            entrega = correr_alertas(self.carpeta, self.base, "demo", self.fetch, [lambda *a: None], instante)
            cantidad = sum(e.tipo == "sin_chequeo" and e.ticker is None for e in entrega["eventos"])
            self.assertEqual(cantidad, 0 if instante == ABIERTO + dt.timedelta(minutes=5) else 1)
        estado = json.loads((self.carpeta / "estado_alertas.json").read_text())
        self.assertEqual(estado["error_movimientos"], "2026-11-05")


if __name__ == "__main__":
    unittest.main()
