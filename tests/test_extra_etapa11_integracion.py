import json
import tempfile
import unittest
from datetime import date
from decimal import Decimal
from pathlib import Path
from shutil import copyfile
from unittest.mock import patch

from cartera.flujo_fondos import cronograma_iamc
from cartera.indices_archivos import actualizar_indices, leer_indices, registrar_proyecciones

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"
HOY = date(2026, 11, 13)


class ProyeccionesIntegradas(unittest.TestCase):
    def setUp(self):
        temporal = tempfile.TemporaryDirectory()
        self.addCleanup(temporal.cleanup)
        self.datos = Path(temporal.name)
        self.bcra = self.datos / "indices" / "bcra"
        self.rem = self.datos / "indices" / "rem"
        self.bcra.mkdir(parents=True)
        self.rem.mkdir()
        copyfile(FIXTURES / "bcra" / "bcra-2026-11-13.json", self.bcra / "2026-11-13.json")
        copyfile(FIXTURES / "bcra" / "rem-tablas-2026-10.xlsx", self.rem / "2026-10.xlsx")
        self.indices = leer_indices(self.datos, HOY)
        self.cierre = json.loads((FIXTURES / "iamc" / "cierres" / "2026-11-05.json").read_text())

    def cronograma(self, ticker, tipo, **datos):
        avisos = []
        contrato = {"tipo": tipo, "fuente": "fixture", "rezago_habiles": 3, **datos}
        return cronograma_iamc(self.cierre, ticker, "tp", contrato=contrato, indices=self.indices, avisos=avisos)

    def test_familias_en_pesos_y_pago_estimado_proveniente_del_rem(self):
        for ticker, tipo, adicionales in (
            ("TZV28", "A3500", {}), ("X29E7", "CER", {"valor_inicial": "850"}),
            ("TMF27", "TAMAR", {}), ("TMVE8", "DUAL", {}),
        ):
            with self.subTest(ticker=ticker):
                flujo = self.cronograma(ticker, tipo, **adicionales)
                self.assertEqual(flujo.moneda, "ARS")
                self.assertGreater(flujo.pagos[0].total, Decimal(0))
                self.assertIn("estimado · REM 2026-10", flujo.pagos[0].origen)
        self.assertIn(self.cronograma("TMVE8", "DUAL").pagos[0].dual[0], ("TAMAR", "A3500", "empate"))

    def test_cupon_tamar_vigente_y_proyectado(self):
        flujo = self.cronograma("BAF27", "TAMAR")
        self.assertEqual(flujo.pagos[0].renta, Decimal("8.333333") * Decimal("0.31666126"))
        self.assertTrue(flujo.pagos[0].origen.startswith("definitivo"))
        self.assertTrue(flujo.pagos[1].origen.startswith("estimado"))

    def test_dashboard_intenta_una_vez_por_dia_y_conserva_la_captura_previa(self):
        with patch("cartera.indices_archivos.extraer", side_effect=OSError("sin red")) as extraer:
            fecha = date(2026, 11, 21)
            self.assertEqual(len(actualizar_indices(self.datos, fecha, automatico=True)), 1)
            self.assertEqual(actualizar_indices(self.datos, fecha, automatico=True), [])
            extraer.assert_called_once()
        self.assertEqual(leer_indices(self.datos, fecha)["captura"], HOY)

    def test_estimacion_anterior_queda_junto_al_cobro(self):
        pago = {"fecha": "2026-11-25", "origen": "estimado · REM 2026-10", "total": "110",
                "estado": "proyectado", "cobro": None}
        flujo = {"posiciones": [{"ticker": "DEMO", "pagos": [pago]}]}
        registrar_proyecciones(self.datos, flujo, HOY)
        pago.update(total="112", estado="debería haberse cobrado", origen="definitivo · BCRA publicado",
                    cobro={"registrado": "111"})
        registrar_proyecciones(self.datos, flujo, date(2026, 11, 26))
        self.assertEqual(pago["cobro"]["estimacion_anterior"], "110")

    def test_actualizacion_pide_cer_publicado_para_fechas_posteriores_a_hoy(self):
        fecha = date(2026, 12, 31)
        with patch("cartera.indices_archivos.extraer", return_value={}) as extraer:
            with patch("cartera.indices_archivos._bajar_rem"):
                self.assertEqual(actualizar_indices(self.datos, fecha), [])
        extraer.assert_called_once_with(date(2025, 1, 1), fecha, hasta_cer=date(2027, 1, 15))

    def test_pago_cer_estimado_identifica_el_ultimo_dato_oficial(self):
        flujo = self.cronograma("X29E7", "CER", valor_inicial="850")
        self.assertIn("CER publicado hasta 2026-12-15", flujo.pagos[0].origen)

    def test_referencia_cer_cubierta_aunque_sea_posterior_a_la_captura(self):
        fila = next(fila for fila in self.cierre["calculadora_bonos"]["ins"] if fila["tk"] == "X29E7")
        # Liquidación 06/11, pago 08/12, referencia 03/12 con 3 días hábiles de rezago.
        fila["f"] = [[32, 105, 0, 0]]
        flujo = self.cronograma("X29E7", "CER", valor_inicial="850")
        pago = flujo.pagos[0]
        self.assertEqual(pago.origen, "definitivo · BCRA publicado")
        self.assertAlmostEqual(pago.total, 100 * self.indices["cer"][date(2026, 12, 3)] / 850, places=24)
