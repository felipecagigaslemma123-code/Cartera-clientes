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




class PrecioDeTitulosAjustables(unittest.TestCase):
    """precio-bono acepta un título ajustable con contrato de índice (antes lo rechazaba)."""

    def setUp(self):
        temporal = tempfile.TemporaryDirectory()
        self.addCleanup(temporal.cleanup)
        self.datos = Path(temporal.name)
        (self.datos / "iamc" / "cierres").mkdir(parents=True)
        copyfile(FIXTURES / "iamc" / "cierres" / "2026-11-05.json",
                 self.datos / "iamc" / "cierres" / "2026-11-05.json")

    def validar(self, configuracion, liquidacion="2026-09-21", moneda="ARS"):
        from cartera.letras_archivos import _validar_contrato_bono
        registro = {"referencia": "base:1", "huella": "x", "precio": "102.3645", "moneda": moneda,
                    "fecha_liquidacion": liquidacion}
        _validar_contrato_bono(self.datos, configuracion, "X29E7", registro)

    def test_con_indice_se_acepta_en_pesos(self):
        indice = {"tipo": "CER", "valor_inicial": "815.43451086916", "rezago_habiles": 10, "fuente": "fixture"}
        self.validar({"iamc": {"ticker": "X29E7", "grupo": "tp", "indice": indice}})

    def test_sin_indice_se_rechaza(self):
        from cartera.letras import ErrorLetra
        with self.assertRaises(ErrorLetra):
            self.validar({"iamc": {"ticker": "X29E7", "grupo": "tp"}})

    def test_liquidacion_posterior_al_pago_se_rechaza(self):
        from cartera.letras import ErrorLetra
        indice = {"tipo": "CER", "valor_inicial": "815.43451086916", "rezago_habiles": 10, "fuente": "fixture"}
        with self.assertRaises(ErrorLetra):
            self.validar({"iamc": {"ticker": "X29E7", "grupo": "tp", "indice": indice}}, liquidacion="2027-01-29")


class CompraAnteriorAlPrimerCierre(Base):
    """Una letra CER comprada antes del primer cierre guardado tiene TIR: no hay pagos intermedios."""

    def flujo(self, cierre, **contrato):
        from cartera.letras import referencias_flujo
        base = PuntoPartida([Posicion("X29E7", "LECER", "letra", 1000, 100)],
                            [Lote("X29E7", 1000, "extracto", date(2026, 9, 18), None, 1000.0, "")])
        instrumentos = {"X29E7": {"vencimiento": "2027-01-29",
                                  "iamc": {"ticker": "X29E7", "grupo": "tp",
                                           "indice": {"tipo": "CER", "valor_inicial": "815.43451086916",
                                                      "rezago_habiles": 10, "fuente": "fixture",
                                                      **contrato}}}}
        ref = referencias_flujo(base, [], instrumentos)[0]
        compras = {"esquema_version": 1, "compras": [{
            "referencia": ref["referencia"], "huella": ref["huella"], "precio": "102.3645",
            "moneda": "ARS", "fecha_liquidacion": "2026-09-21"}]}
        flujo = calcular_flujo(base, [], instrumentos, [cierre], compras, None, HOY, None,
                               indices=self.indices)
        return next(p for p in flujo["posiciones"] if p["ticker"] == "X29E7")["compras"][0]

    def test_letra_cer_tiene_tir(self):
        compra = self.flujo(self.cierre)
        self.assertIsNone(compra["motivo"])
        self.assertIsNotNone(compra["tir"])

    def test_bono_con_cupones_sigue_pidiendo_los_pagos(self):
        cierre = copy.deepcopy(self.cierre)
        fila = next(f for f in cierre["calculadora_bonos"]["ins"] if f["tk"] == "X29E7")
        fila["f"] = [[40, 0.0, 1.0, 0.0], [84, 100.0, 1.0, 0.0]]
        reales = [["2026-12-16", "0", "1"], ["2027-01-29", "100", "1"]]
        compra = self.flujo(cierre, pagos_reales=reales)
        self.assertTrue(compra["motivo"].startswith("sin dato: faltan pagos"))


class TirDeAjustablesEnPantalla(CompraAnteriorAlPrimerCierre):
    def test_tir_estimada_se_muestra_en_pantalla_y_excel(self):
        from cartera.dashboard import _panel_flujo
        compra = self.flujo(self.cierre)
        self.assertTrue(compra["tir_estimada"])
        flujo = {"posiciones": [{"ticker": "X29E7", "moneda_etiqueta": "ARS", "moneda": "ARS", "cantidad": "1000",
                                 "pagos": [], "compras": [compra], "proximo_pago": None,
                                 "pagos_restantes": 0, "total_proyectado": None}],
                 "calendario": [], "avisos": [], "fecha_cierre": "2026-11-05", "fecha_calculo": "2026-11-13"}
        html, excel = _panel_flujo(flujo)
        self.assertIn("(estimada, ARS)", html)
        self.assertTrue(any(isinstance(c, str) and "(estimada, ARS)" in c for fila in excel for c in fila))


if __name__ == "__main__":
    unittest.main()
