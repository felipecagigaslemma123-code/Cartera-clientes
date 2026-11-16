"""Revisión de la etapa 11 (16/11/2026): base del A3500 de IAMC y letras indexadas en el flujo."""

import copy
import json
import tempfile
import unittest
from datetime import date
from decimal import Decimal
from pathlib import Path
from shutil import copyfile

from cartera.flujo_fondos import calcular_flujo, cronograma_iamc
from cartera.indices_archivos import leer_indices
from cartera.punto_partida import Lote, Posicion, PuntoPartida

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"
HOY = date(2026, 11, 13)


class Base(unittest.TestCase):
    def setUp(self):
        temporal = tempfile.TemporaryDirectory()
        self.addCleanup(temporal.cleanup)
        datos = Path(temporal.name)
        (datos / "indices" / "bcra").mkdir(parents=True)
        (datos / "indices" / "rem").mkdir()
        copyfile(FIXTURES / "bcra" / "bcra-2026-11-13.json", datos / "indices" / "bcra" / "2026-11-13.json")
        copyfile(FIXTURES / "bcra" / "rem-tablas-2026-10.xlsx", datos / "indices" / "rem" / "2026-10.xlsx")
        self.indices = leer_indices(datos, HOY)
        self.cierre = json.loads((FIXTURES / "iamc" / "cierres" / "2026-11-05.json").read_text())


class BaseDelA3500(Base):
    """IAMC expresa los flujos DL al A3500 de su bloque macro, no siempre el del día del cierre."""

    def cierre_tzv28(self, fecha_macro):
        cierre = copy.deepcopy(self.cierre)
        fila = next(f for f in cierre["calculadora_bonos"]["ins"] if f["tk"] == "TZV28")
        fila["f"] = [[3, 100.0, 0.0, 0.0]]  # liquidación 06/11, pago 09/11, referencia 04/11
        for variable in cierre["macro"]["vars"]:
            if variable["k"] == "a3500":
                variable["f"] = fecha_macro
        return cierre, Decimal(str(fila["fxc"]))

    def pago(self, cierre):
        contrato = {"tipo": "A3500", "rezago_habiles": 3, "fuente": "fixture"}
        return cronograma_iamc(cierre, "TZV28", "tp", contrato=contrato, indices=self.indices, avisos=[]).pagos[0]

    def test_usa_el_a3500_de_la_fecha_que_informa_iamc(self):
        cierre, fxc = self.cierre_tzv28("2026-11-04")
        self.assertAlmostEqual(self.pago(cierre).total, 100 * fxc, places=20)

    def test_con_la_fecha_del_cierre_aplica_la_variacion(self):
        cierre, fxc = self.cierre_tzv28("2026-11-05")
        a = self.indices["a3500"]
        esperado = 100 * fxc * a[date(2026, 11, 4)] / a[date(2026, 11, 5)]
        self.assertAlmostEqual(self.pago(cierre).total, esperado, places=20)


class LetrasIndexadas(Base):
    def test_letra_cer_con_indice_entra_al_flujo_y_no_queda_pendiente(self):
        base = PuntoPartida([Posicion("X29E7", "LECER", "letra", 1000, 100)],
                            [Lote("X29E7", 1000, "extracto", date(2026, 9, 1), None, 1000.0, "")])
        instrumentos = {"X29E7": {"vencimiento": "2027-01-29",
                                  "letra": {"familia": "LECER", "moneda_pago": "ARS"},
                                  "iamc": {"ticker": "X29E7", "grupo": "tp",
                                           "indice": {"tipo": "CER", "valor_inicial": "850",
                                                      "rezago_habiles": 10, "fuente": "fixture"}}}}
        letras = {"posiciones": [{"ticker": "X29E7", "familia": "LECER", "cantidad": "1000",
                                  "vencimiento": "2027-01-29", "pago_vencimiento": None,
                                  "base_nominal": None, "valor_por_base": None}]}
        flujo = calcular_flujo(base, [], instrumentos, [self.cierre], None, letras, HOY, None,
                               indices=self.indices)
        filas = [p for p in flujo["posiciones"] if p["ticker"] == "X29E7"]
        self.assertEqual(len(filas), 1)
        self.assertEqual(len(filas[0]["pagos"]), 1)
        self.assertIsNotNone(filas[0]["pagos"][0]["total"])

    def test_letra_sin_indice_sigue_en_el_panel_de_letras(self):
        base = PuntoPartida([Posicion("X29E7", "LECER", "letra", 1000, 100)],
                            [Lote("X29E7", 1000, "extracto", date(2026, 9, 1), None, 1000.0, "")])
        instrumentos = {"X29E7": {"vencimiento": "2027-01-29", "letra": {"familia": "LECER", "moneda_pago": "ARS"}}}
        letras = {"posiciones": [{"ticker": "X29E7", "familia": "LECER", "cantidad": "1000",
                                  "vencimiento": "2027-01-29", "pago_vencimiento": None,
                                  "base_nominal": None, "valor_por_base": None}]}
        flujo = calcular_flujo(base, [], instrumentos, [self.cierre], None, letras, HOY, None,
                               indices=self.indices)
        filas = [p for p in flujo["posiciones"] if p["ticker"] == "X29E7"]
        self.assertEqual(len(filas), 1)
        self.assertEqual(filas[0]["pagos"], [])


class ControlCerInicial(Base):
    """El flujo CER de IAMC está al CER de la liquidación menos el rezago: el control es exacto."""

    def avisos(self, valor_inicial):
        avisos = []
        contrato = {"tipo": "CER", "valor_inicial": valor_inicial, "rezago_habiles": 10, "fuente": "fixture"}
        cronograma_iamc(self.cierre, "X29E7", "tp", contrato=contrato, indices=self.indices, avisos=avisos)
        return [a for a in avisos if a.startswith("revisar valor inicial del CER")]

    def test_cer_inicial_contractual_no_avisa(self):
        # Resolución Conjunta 48/2026: CER del 31/07/2026, diez días hábiles antes de la emisión.
        self.assertEqual(self.avisos("815.43451086916"), [])

    def test_cer_inicial_corrido_tres_dias_avisa(self):
        # CER del 03/08/2026: el pago cambia 0,2 % y el control anterior (0,5 %) no lo detectaba.
        self.assertEqual(len(self.avisos("816.92114579699")), 1)


if __name__ == "__main__":
    unittest.main()
