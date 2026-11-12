"""Base derivada del historial, sin Excel de punto de partida."""

import datetime as dt
import io
import json
import stat
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

from cartera.__main__ import main
from cartera.almacenamiento import cargar_cartera, derivar_base
from cartera.historial import correr_historial
from test_etapa10_iol import F1, F2, F3, escribir_iol, mov
from test_etapa6_historial import escribir_extracto, fila_xlsx

ESPECIES = {"AAA": {"especie": "CEDEAR Demo A", "tipo": "cedear"}, "BOND1": {"especie": "Bono Demo", "tipo": "bono"},
            "LET1": {"especie": "Letra Demo", "tipo": "letra"}, "VIEJA": {"especie": "Ya vendida", "tipo": "accion"}}
MOVIMIENTOS = [
    mov(1, "Compra(AAA)", F1, "-10.000,00", 10), mov(2, "Compra(AAA)", F2, "-24.000,00", 20), mov(3, "Venta(AAA)", F3, "18.000,00", 15),
    mov(4, "Compra(BOND1)", F1, "-80.000,00", 100), mov(5, "Compra(LET1)", F1, "-900,00", 1000),
    mov(6, "Pago de Amortización(LET1)", F2, "1.000,00"), mov(7, "Pago de Amortización(LET1)", F2, "0,00", -1000),
    mov(8, "Compra(VIEJA)", F1, "-500,00", 5), mov(9, "Venta(VIEJA)", F2, "600,00", 5),
]


class Base(unittest.TestCase):
    def setUp(self):
        temporal = tempfile.TemporaryDirectory()
        self.addCleanup(temporal.cleanup)
        self.datos = Path(temporal.name) / "datos"
        self.carpeta = self.datos / "clientes" / "demo"
        (self.carpeta / "extractos").mkdir(parents=True)
        self.base = self.carpeta / "cartera.json"

    def preparar(self, movimientos=None, especies=ESPECIES):
        escribir_iol(self.carpeta / "extractos" / "mov.xls", MOVIMIENTOS if movimientos is None else movimientos)
        if especies is not None:
            (self.carpeta / "especies.json").write_text(json.dumps(especies), encoding="utf-8")

    def falla(self, *textos, **opciones):
        with self.assertRaises(ValueError) as contexto:
            derivar_base(self.datos, "demo", **opciones)
        for texto in textos:
            self.assertIn(texto, str(contexto.exception))
        return contexto.exception


class Derivar(Base):
    def test_arma_posiciones_y_lotes_abiertos(self):
        self.preparar()
        punto, contenido = derivar_base(self.datos, "demo")
        posiciones = {p.ticker: p for p in punto.posiciones}
        self.assertEqual(sorted(posiciones), ["AAA", "BOND1"])
        self.assertEqual((posiciones["AAA"].especie, posiciones["AAA"].tipo, posiciones["AAA"].cotiza_cada), ("CEDEAR Demo A", "cedear", 1))
        self.assertAlmostEqual(posiciones["AAA"].cantidad, 15)
        self.assertEqual(posiciones["BOND1"].cotiza_cada, 100)
        lotes = [l for l in punto.lotes if l.ticker == "AAA"]
        self.assertEqual(len(lotes), 1)
        self.assertEqual((lotes[0].origen, lotes[0].fecha), ("extracto", dt.date(2026, 2, 10)))
        self.assertAlmostEqual(lotes[0].cantidad, 15)
        self.assertAlmostEqual(lotes[0].costo, 18000.0)
        self.assertAlmostEqual(lotes[0].precio, 1200.0)
        bono = next(l for l in punto.lotes if l.ticker == "BOND1")
        self.assertAlmostEqual(bono.costo, 80000.0)
        self.assertAlmostEqual(bono.precio, 80000.0)
        self.assertEqual(contenido["origen"]["archivo"], "extractos")
        self.assertRegex(contenido["origen"]["sha256"], r"^[0-9a-f]{64}$")

    def test_la_base_queda_guardada_y_privada(self):
        self.preparar()
        derivar_base(self.datos, "demo")
        punto, _ = cargar_cartera(self.datos, "demo")
        self.assertEqual(sorted(p.ticker for p in punto.posiciones), ["AAA", "BOND1"])
        self.assertEqual(stat.S_IMODE(self.base.stat().st_mode) & 0o077, 0)

    def test_el_historial_no_informa_diferencias_despues(self):
        self.preparar()
        punto, _ = derivar_base(self.datos, "demo")
        h = correr_historial(self.carpeta, punto)
        self.assertEqual(h.diferencias_tenencias, {})
        self.assertEqual(h.diferencias_costos, {})
        self.assertEqual(sorted(r.ticker for r in h.realizados), ["AAA", "LET1", "VIEJA"])

    def test_compra_en_dolares_sin_mep_queda_pendiente(self):
        self.preparar([mov(7, "Compra(AAAD)", F1, "-5,00", 10), mov(7, "Compra(AAAD)", F1, "-100,00", 10, "Dolares")])
        punto, _ = derivar_base(self.datos, "demo")
        self.assertEqual((punto.lotes[0].origen, punto.lotes[0].precio, punto.lotes[0].costo), ("pendiente", None, None))
        self.assertAlmostEqual(punto.posiciones[0].cantidad, 10)

    def test_compra_en_dolares_con_mep(self):
        self.preparar([mov(7, "Compra(AAAD)", F1, "-5,00", 10), mov(7, "Compra(AAAD)", F1, "-100,00", 10, "Dolares")])
        (self.carpeta / "mep_diario.csv").write_text("fecha,mep\n2026-01-10,1000\n", encoding="utf-8")
        punto, _ = derivar_base(self.datos, "demo")
        self.assertAlmostEqual(punto.lotes[0].costo, 100000.0)
        self.assertAlmostEqual(punto.lotes[0].precio, 10000.0)

    def test_extractos_xlsx_con_cierres(self):
        d1, d2 = dt.date(2026, 1, 10), dt.date(2026, 2, 10)
        escribir_extracto(self.carpeta / "extractos" / "pesos.xlsx", "Cuenta Corriente PESOS", [
            fila_xlsx(d1, "COMPRA NORMAL", 1, 10, "AAA", -10000.0, -10000.0), fila_xlsx(d1, "COMPRA NORMAL", 2, 1000, "LET1", -900.0, -10900.0),
            fila_xlsx(d2, "RENTA Y AMORTIZ", 3, 0, "LET1", 1000.0, -9900.0)])
        (self.carpeta / "especies.json").write_text(json.dumps(ESPECIES), encoding="utf-8")
        (self.carpeta / "cierres.json").write_text('["LET1"]', encoding="utf-8")
        punto, _ = derivar_base(self.datos, "demo")
        self.assertEqual([p.ticker for p in punto.posiciones], ["AAA"])


class Rechazos(Base):
    def test_sin_especies(self):
        self.preparar(especies=None)
        self.falla("especies.json")
        self.assertFalse(self.base.exists())

    def test_especie_faltante_o_tipo_invalido_las_lista_todas(self):
        self.preparar(especies={"AAA": {"especie": "CEDEAR Demo A", "tipo": "fondo"}})
        self.falla("AAA", "BOND1")
        self.assertFalse(self.base.exists())

    def test_venta_sin_lotes_es_historia_incompleta(self):
        self.preparar(MOVIMIENTOS + [mov(20, "Venta(BOND1)", F3, "200.000,00", 250)])
        self.falla("BOND1", "150")
        self.assertFalse(self.base.exists())

    def test_sin_clasificar_con_cantidad(self):
        self.preparar(MOVIMIENTOS + [mov(21, "Canje(AAA)", F3, "0,00", 5)])
        self.falla("Canje(AAA)")
        self.assertFalse(self.base.exists())

    def test_sin_clasificar_sin_cantidad_no_frena(self):
        self.preparar(MOVIMIENTOS + [mov(22, "Ajuste raro", F3, "1,00")])
        punto, _ = derivar_base(self.datos, "demo")
        self.assertEqual(len(punto.posiciones), 2)

    def test_sin_lotes_abiertos(self):
        self.preparar([mov(8, "Compra(VIEJA)", F1, "-500,00", 5), mov(9, "Venta(VIEJA)", F2, "600,00", 5)])
        self.falla()
        self.assertFalse(self.base.exists())

    def test_sin_extractos(self):
        (self.carpeta / "especies.json").write_text(json.dumps(ESPECIES), encoding="utf-8")
        self.falla()
        self.assertFalse(self.base.exists())


class Reemplazo(Base):
    def test_no_pisa_una_base_existente(self):
        self.preparar()
        derivar_base(self.datos, "demo")
        antes = self.base.read_bytes()
        self.falla("ya existe")
        self.assertEqual(self.base.read_bytes(), antes)

    def test_reemplazar_conserva_la_version_anterior(self):
        self.preparar()
        derivar_base(self.datos, "demo")
        antes = self.base.read_bytes()
        self.preparar(MOVIMIENTOS + [mov(30, "Compra(AAA)", F3, "-5.000,00", 5)])
        punto, _ = derivar_base(self.datos, "demo", reemplazar=True)
        self.assertAlmostEqual(next(p.cantidad for p in punto.posiciones if p.ticker == "AAA"), 20)
        versiones = list((self.carpeta / "historial_cartera").iterdir())
        self.assertEqual(len(versiones), 1)
        self.assertEqual(versiones[0].read_bytes(), antes)

    def test_reemplazar_se_niega_con_dia_cero_o_movimientos(self):
        self.preparar()
        derivar_base(self.datos, "demo")
        antes = self.base.read_bytes()
        (self.carpeta / "dia_cero.json").write_text("{}", encoding="utf-8")
        self.falla("día cero", reemplazar=True)
        (self.carpeta / "dia_cero.json").unlink()
        (self.carpeta / "movimientos.csv").write_text(
            "fecha,tipo,ticker,cantidad,importe,moneda,tc,tipo_activo,nota\n2026-04-01,aporte,,,1000,ARS,,,\n", encoding="utf-8")
        self.falla("movimientos", reemplazar=True)
        self.assertEqual(self.base.read_bytes(), antes)
        self.assertFalse((self.carpeta / "historial_cartera").exists())


class Comando(Base):
    def correr(self, *argumentos):
        salida, errores = io.StringIO(), io.StringIO()
        with redirect_stdout(salida), redirect_stderr(errores):
            codigo = main(["--datos", str(self.datos), "derivar-base", "--cliente", "demo"] + list(argumentos))
        return codigo, salida.getvalue(), errores.getvalue()

    def test_crea_la_base_e_informa(self):
        self.preparar()
        codigo, salida, _ = self.correr()
        self.assertEqual(codigo, 0)
        self.assertTrue(self.base.exists())
        self.assertIn("AAA", salida)
        self.assertIn("BOND1", salida)

    def test_error_sin_escribir(self):
        self.preparar(especies=None)
        codigo, _, errores = self.correr()
        self.assertNotEqual(codigo, 0)
        self.assertIn("especies.json", errores)
        self.assertFalse(self.base.exists())

    def test_historial_lee_el_xls(self):
        self.preparar()
        self.assertEqual(self.correr()[0], 0)
        salida = io.StringIO()
        with redirect_stdout(salida), redirect_stderr(io.StringIO()):
            codigo = main(["--datos", str(self.datos), "historial", "--cliente", "demo"])
        self.assertEqual(codigo, 0)
        self.assertTrue((self.carpeta / "realizado.csv").exists())


if __name__ == "__main__":
    unittest.main()
