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
