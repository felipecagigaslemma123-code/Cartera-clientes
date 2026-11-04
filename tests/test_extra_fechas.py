"""Fechas de compra respecto del día de Argentina, con reloj controlado."""

import datetime as dt
from io import BytesIO
from pathlib import Path
import unittest
from unittest.mock import patch
from zoneinfo import ZoneInfo

from openpyxl import load_workbook

from cartera.punto_partida import ErrorPuntoPartida, _hoy_argentina, cargar_punto_partida


DEMO = Path(__file__).resolve().parents[1] / "fixtures" / "punto_partida_demo.xlsx"
HOY = dt.date(2026, 11, 4)


class FechasCompra(unittest.TestCase):
    def libro_con_fechas(self, cambios):
        libro = load_workbook(DEMO)
        try:
            for celda, fecha in cambios.items():
                libro["Lotes"][celda] = fecha
            salida = BytesIO()
            libro.save(salida)
            salida.seek(0)
            return salida
        finally:
            libro.close()

    def cargar(self, cambios):
        with self.libro_con_fechas(cambios) as entrada, patch(
            "cartera.punto_partida._hoy_argentina", return_value=HOY
        ) as reloj:
            punto = cargar_punto_partida(entrada)
        reloj.assert_called_once_with()
        return punto

    def errores(self, cambios):
        with self.assertRaises(ErrorPuntoPartida) as contexto:
            self.cargar(cambios)
        return contexto.exception.errores

    def test_fecha_futura_extracto_se_rechaza_con_hoja_fila_y_ticker(self):
        errores = self.errores({"D5": HOY + dt.timedelta(days=1)})
        self.assertTrue(any("Lotes fila 5 (AAA)" in e and "futura" in e for e in errores))

    def test_fecha_futura_estimada_se_rechaza_con_hoja_fila_y_ticker(self):
        errores = self.errores({"D8": "2026-11-05"})
        self.assertTrue(any("Lotes fila 8 (BBB)" in e and "futura" in e for e in errores))

    def test_fecha_hoy_extracto_y_estimada_se_aceptan(self):
        punto = self.cargar({"D5": HOY, "D8": dt.datetime(2026, 11, 4, 23, 59)})
        self.assertEqual(punto.lotes[0].fecha, HOY)
        self.assertEqual(punto.lotes[3].fecha, HOY)
        self.assertEqual(punto.lotes[0].origen, "extracto")
        self.assertEqual(punto.lotes[3].origen, "estimado")

    def test_fecha_hoy_iso_se_acepta(self):
        punto = self.cargar({"D5": HOY.isoformat(), "D8": HOY.isoformat()})
        self.assertEqual(punto.lotes[0].fecha, HOY)
        self.assertEqual(punto.lotes[3].fecha, HOY)

    def test_fecha_futura_pendiente_tambien_se_rechaza(self):
        errores = self.errores({"D10": HOY + dt.timedelta(days=1)})
        self.assertTrue(any("Lotes fila 10 (BOND1)" in e and "futura" in e for e in errores))

    def test_varias_fechas_futuras_se_acumulan(self):
        errores = self.errores({"D5": "2026-11-05", "D8": "2026-11-06"})
        self.assertTrue(any("Lotes fila 5 (AAA)" in e and "futura" in e for e in errores))
        self.assertTrue(any("Lotes fila 8 (BBB)" in e and "futura" in e for e in errores))

    def test_hoy_se_obtiene_en_argentina_en_frontera_utc(self):
        # A la 01:30 UTC aún es el día anterior en Argentina.
        instante = dt.datetime(2026, 11, 5, 1, 30, tzinfo=dt.timezone.utc)

        class Reloj:
            @classmethod
            def now(cls, zona):
                self.assertEqual(zona, ZoneInfo("America/Argentina/Buenos_Aires"))
                return instante.astimezone(zona)

        with patch("cartera.punto_partida.datetime", Reloj):
            self.assertEqual(_hoy_argentina(), HOY)


if __name__ == "__main__":
    unittest.main()
