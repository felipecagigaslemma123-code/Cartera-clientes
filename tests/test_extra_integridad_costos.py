"""Fechas por comando de importación y fallas de guardado de correcciones."""

import datetime as dt
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from zoneinfo import ZoneInfo

from openpyxl import load_workbook

from cartera.almacenamiento import actualizar_costos, importar_cartera
from cartera.punto_partida import ErrorPuntoPartida


DEMO = Path(__file__).resolve().parents[1] / "fixtures" / "punto_partida_demo.xlsx"


class IntegridadCorrecciones(unittest.TestCase):
    def setUp(self):
        self.temporal = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporal.cleanup)
        self.raiz = Path(self.temporal.name)
        self.datos = self.raiz / "datos"
        self.base = self.datos / "clientes" / "demo" / "cartera.json"
        self.historial = self.base.parent / "historial_cartera"
        self.hoy = dt.datetime.now(ZoneInfo("America/Argentina/Buenos_Aires")).date()

    def excel(self, nombre, modificar):
        ruta = self.raiz / nombre
        libro = load_workbook(DEMO)
        try:
            modificar(libro)
            libro.save(ruta)
        finally:
            libro.close()
        return ruta

    def test_importar_fecha_futura_extracto_y_estimada_no_crea_datos(self):
        def cambiar(libro):
            libro["Lotes"]["D5"] = self.hoy + dt.timedelta(days=1)
            libro["Lotes"]["D8"] = self.hoy + dt.timedelta(days=1)
        ruta = self.excel("futuro.xlsx", cambiar)
        with self.assertRaises(ErrorPuntoPartida) as contexto:
            importar_cartera(self.datos, "demo", ruta)
        self.assertTrue(any("Lotes fila 5 (AAA)" in e and "futura" in e for e in contexto.exception.errores))
        self.assertTrue(any("Lotes fila 8 (BBB)" in e and "futura" in e for e in contexto.exception.errores))
        self.assertFalse(self.datos.exists())

    def test_importar_fecha_hoy_extracto_y_estimada_se_acepta(self):
        def cambiar(libro):
            libro["Lotes"]["D5"] = self.hoy
            libro["Lotes"]["D8"] = self.hoy
        ruta = self.excel("hoy.xlsx", cambiar)
        punto, _ = importar_cartera(self.datos, "demo", ruta)
        self.assertEqual(punto.lotes[0].fecha, self.hoy)
        self.assertEqual(punto.lotes[3].fecha, self.hoy)

    def test_intercambio_ambiguo_de_origen_entre_lotes_con_notas_distintas_advierte(self):
        def inicial(libro):
            lotes = libro["Lotes"]
            for fila, nota in ((5, "lote A"), (6, "lote B")):
                lotes.cell(fila, 2, 50)
                lotes.cell(fila, 4, self.hoy)
                lotes.cell(fila, 6, 1000)
                lotes.cell(fila, 7, 50000)
                lotes.cell(fila, 8, nota)
            lotes["C6"] = "A estimar"
        ruta = self.excel("inicial.xlsx", inicial)
        importar_cartera(self.datos, "demo", ruta)
        libro = load_workbook(ruta)
        libro["Lotes"]["C5"] = "A estimar"
        libro["Lotes"]["C6"] = "Extracto"
        corregido = self.raiz / "intercambio.xlsx"
        libro.save(corregido)
        libro.close()
        resultado = actualizar_costos(self.datos, "demo", corregido)
        self.assertTrue(resultado["advertencias"])
        self.assertIn("AAA", resultado["advertencias"][0])
        self.assertIn("extracto", resultado["advertencias"][0])

    def test_colision_de_nombre_historico_no_pisa_version_ni_base(self):
        importar_cartera(self.datos, "demo", DEMO)
        original = self.base.read_bytes()
        primera = self.excel("primera.xlsx", lambda libro: setattr(libro["Lotes"]["G5"], "value", 60601))
        segunda = self.excel("segunda.xlsx", lambda libro: setattr(libro["Lotes"]["G5"], "value", 60602))
        instante = dt.datetime(2026, 11, 4, 15, tzinfo=ZoneInfo("America/Argentina/Buenos_Aires"))
        with patch("cartera.almacenamiento.datetime", wraps=dt.datetime) as reloj, patch(
            "cartera.almacenamiento.uuid.uuid4", return_value=SimpleNamespace(hex="colision")
        ):
            reloj.now.return_value = instante
            resultado = actualizar_costos(self.datos, "demo", primera)
            actual = self.base.read_bytes()
            with self.assertRaises(FileExistsError):
                actualizar_costos(self.datos, "demo", segunda)
        self.assertEqual(self.base.read_bytes(), actual)
        self.assertEqual(resultado["historial"].read_bytes(), original)
        self.assertEqual([ruta.resolve() for ruta in self.historial.glob("*.json")], [resultado["historial"].resolve()])
        self.assertEqual(list(self.base.parent.rglob("*.tmp")), [])

    def test_falla_de_escritura_de_backup_deja_base_y_limpia_temporales(self):
        importar_cartera(self.datos, "demo", DEMO)
        original = self.base.read_bytes()
        nuevo = self.excel("nuevo.xlsx", lambda libro: setattr(libro["Lotes"]["G5"], "value", 60601))
        with patch("cartera.almacenamiento.os.fsync", side_effect=[None, OSError("disco no disponible")]):
            with self.assertRaises(OSError):
                actualizar_costos(self.datos, "demo", nuevo)
        self.assertEqual(self.base.read_bytes(), original)
        self.assertEqual(list(self.base.parent.rglob("*.tmp")), [])
        self.assertEqual(list(self.historial.glob("*.json")), [])


if __name__ == "__main__":
    unittest.main()
