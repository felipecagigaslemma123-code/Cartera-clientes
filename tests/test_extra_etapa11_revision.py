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


class VentanaTamar(Base):
    """Cupón TAMAR: promedio de los días hábiles con dato de [inicio − rezago, pago − rezago).

    Así se reproducen al centésimo de diezmilésimo los 12 cupones pagados de BAM27 y RVS1O en
    2025 y 2026 (avisos de MAE y CNV). El motor anterior excluía el inicio e incluía el fin.
    """

    def contrato(self, **extra):
        return dict({"tipo": "TAMAR", "rezago_habiles": 7, "fuente": "fixture",
                     "_pagos_previos": (date(2026, 5, 27), date(2026, 8, 27))}, **extra)

    def primer_pago(self, contrato):
        return cronograma_iamc(self.cierre, "RVS1O", "on", contrato=contrato, indices=self.indices,
                               avisos=[]).pagos[0]

    def test_ventana_incluye_el_inicio_y_excluye_el_fin(self):
        from cartera.pagos_indexados import _ventana_tamar
        indices = {"tamar_tna": {date(2026, 8, 3): Decimal("0.30"), date(2026, 8, 4): Decimal("0.20"),
                                 date(2026, 8, 6): Decimal("0.10"), date(2026, 8, 7): Decimal("0.90")},
                   "feriados": {}, "tamar": {}, "rem": None}
        valores = _ventana_tamar(indices, date(2026, 8, 3), date(2026, 8, 7))
        # El 05/08 no tiene dato publicado: no cuenta ni arrastra el anterior.
        self.assertEqual([v.valor for v in valores], [Decimal("0.30"), Decimal("0.20"), Decimal("0.10")])

    def test_cupon_en_curso_se_calcula_desde_el_ultimo_pago(self):
        pago = self.primer_pago(self.contrato())
        self.assertEqual(pago.fecha, date(2026, 11, 27))
        serie = self.indices["tamar_tna"]
        # 7 hábiles antes del 27/08 y del 27/11 (sin feriados cargados en el fixture).
        ultimo = max(serie)
        publicados = [serie[d] for d in serie if date(2026, 8, 18) <= d < date(2026, 11, 18)]
        # Los hábiles posteriores al último dato van con la mediana del REM de noviembre.
        proyectados = [d for d in (date(2026, 11, 12), date(2026, 11, 13), date(2026, 11, 16), date(2026, 11, 17))
                       if d > ultimo]
        self.assertEqual(ultimo, date(2026, 11, 11))
        valores = publicados + [Decimal("0.239")] * len(proyectados)
        promedio = sum(valores) / len(valores)
        self.assertTrue(pago.origen.startswith("estimado · REM"))
        self.assertAlmostEqual(pago.renta, Decimal("6.30137") * (promedio + Decimal("0.0389")), places=20)
        self.assertNotAlmostEqual(float(pago.renta), 2.201816, places=2)  # IAMC con v.vig

    def test_sin_pagos_previos_usa_la_tasa_vigente_de_iamc(self):
        contrato = self.contrato()
        del contrato["_pagos_previos"]
        pago = self.primer_pago(contrato)
        self.assertAlmostEqual(float(pago.renta), 2.201816, places=5)
        self.assertEqual(pago.origen, "definitivo · IAMC publicado")

    def test_piso_de_la_tasa(self):
        pago = self.primer_pago(self.contrato(piso="0.9"))
        self.assertEqual(pago.renta, Decimal("6.30137") * Decimal("0.9"))
