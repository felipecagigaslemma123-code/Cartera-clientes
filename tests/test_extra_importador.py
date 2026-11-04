"""Casos de integridad de entrada adicionales a las pruebas de aceptación."""

from io import BytesIO
from pathlib import Path
import re
import tempfile
import unittest
from zipfile import ZipFile

from openpyxl import load_workbook

from cartera.punto_partida import ErrorPuntoPartida, cargar_punto_partida


DEMO = Path(__file__).resolve().parents[1] / "fixtures" / "punto_partida_demo.xlsx"


class IntegridadImportador(unittest.TestCase):
    def cambiar(self, cambio):
        libro = load_workbook(DEMO)
        try:
            cambio(libro)
            contenido = BytesIO()
            libro.save(contenido)
            contenido.seek(0)
            return contenido
        finally:
            libro.close()

    def errores(self, cambio):
        with self.cambiar(cambio) as contenido:
            with self.assertRaises(ErrorPuntoPartida) as contexto:
                cargar_punto_partida(contenido)
        return contexto.exception.errores

    def test_lee_bytes_sin_alterarlos_ni_ejecutar_formulas(self):
        contenido = DEMO.read_bytes()
        punto = cargar_punto_partida(BytesIO(contenido))
        self.assertEqual(len(punto.posiciones), 6)
        self.assertEqual(punto.lotes[0].costo, 60600.0)
        self.assertEqual(punto.lotes[3].costo, 18000.0)

    def test_informa_ambas_hojas_faltantes(self):
        def cambio(libro):
            libro["Cartera"].title = "Otra"
            libro.remove(libro["Lotes"])

        errores = self.errores(cambio)
        self.assertTrue(any("Cartera" in e for e in errores))
        self.assertTrue(any("Lotes" in e for e in errores))

    def test_rechaza_cartera_vacia(self):
        self.assertTrue(self.errores(lambda libro: setattr(libro["Cartera"]["A5"], "value", None)))

    def test_no_acepta_booleanos_como_cantidades(self):
        errores = self.errores(lambda libro: setattr(libro["Cartera"]["D5"], "value", True))
        self.assertTrue(any("AAA" in e and "cantidad" in e for e in errores))

    def test_rechaza_cantidad_cero_y_precio_negativo_en_distintos_lotes(self):
        def cambio(libro):
            libro["Lotes"]["B5"] = 0
            libro["Lotes"]["F8"] = -900

        errores = self.errores(cambio)
        self.assertTrue(any("AAA" in e and "cantidad" in e for e in errores))
        self.assertTrue(any("BBB" in e and "precio" in e for e in errores))

    def test_rechaza_formula_en_dato_numerico_necesario(self):
        errores = self.errores(lambda libro: setattr(libro["Lotes"]["G5"], "value", "=60000+600"))
        self.assertTrue(any("AAA" in e and "costo" in e for e in errores))

    def test_ignora_las_columnas_calculadas_de_precio_y_costo(self):
        def cambio(libro):
            libro["Lotes"]["F5"] = "cualquier cosa"
            libro["Lotes"]["G8"] = "cualquier cosa"

        with self.cambiar(cambio) as contenido:
            punto = cargar_punto_partida(contenido)
        self.assertEqual(punto.lotes[0].precio, 1010)
        self.assertEqual(punto.lotes[3].costo, 18000)

    def test_unidad_del_lote_debe_coincidir_con_la_posicion(self):
        errores = self.errores(lambda libro: setattr(libro["Lotes"]["E5"], "value", 100))
        self.assertTrue(any("AAA" in e and "cotiza" in e for e in errores))

    def test_lote_huerfano_y_especie_sin_lotes_se_informan_juntos(self):
        def cambio(libro):
            libro["Lotes"]["A9"] = "ZZZ"

        errores = self.errores(cambio)
        self.assertTrue(any("ZZZ" in e and "Cartera" in e for e in errores))
        self.assertTrue(any("CCC" in e and "sin lotes" in e for e in errores))

    def test_tolerancia_incluye_exactamente_medio_nominal(self):
        with self.cambiar(lambda libro: setattr(libro["Lotes"]["B5"], "value", 60.5)) as contenido:
            punto = cargar_punto_partida(contenido)
        self.assertEqual(punto.lotes[0].cantidad, 60.5)

    def test_tolerancia_no_admite_mas_de_medio_nominal(self):
        errores = self.errores(lambda libro: setattr(libro["Lotes"]["B5"], "value", 60.5001))
        self.assertTrue(any("AAA" in e and "suma" in e for e in errores))

    def test_tolerancia_en_frontera_decimal_con_varios_lotes(self):
        def cambio(libro):
            libro["Cartera"]["D5"] = 1000.5
            libro["Lotes"]["B5"] = 100.1
            libro["Lotes"]["B6"] = 100.1
            for _ in range(8):
                libro["Lotes"].append(["AAA", 100.1, "Extracto", None, 1, None, 1000, ""])

        with self.cambiar(cambio) as contenido:
            punto = cargar_punto_partida(contenido)
        self.assertEqual(len([l for l in punto.lotes if l.ticker == "AAA"]), 10)

    def test_cantidad_fuera_de_rango_se_agrega_a_los_errores(self):
        contenido = BytesIO()
        with ZipFile(DEMO) as original, ZipFile(contenido, "w") as roto:
            for nombre in original.namelist():
                datos = original.read(nombre)
                if nombre == "xl/worksheets/sheet1.xml":
                    datos = re.sub(
                        rb'(<c r="D5"[^>]*><v>).*?(</v>)',
                        lambda m: m[1] + b"1" + b"0" * 400 + m[2], datos,
                    )
                    datos = re.sub(
                        rb'(<c r="D6"[^>]*><v>).*?(</v>)',
                        lambda m: m[1] + b"0" + m[2], datos,
                    )
                roto.writestr(nombre, datos)
        contenido.seek(0)
        with self.assertRaises(ErrorPuntoPartida) as contexto:
            cargar_punto_partida(contenido)
        errores = contexto.exception.errores
        self.assertTrue(any("AAA" in e and "finito" in e for e in errores))
        self.assertTrue(any("BBB" in e and "cantidad" in e for e in errores))

    def test_referencia_a_texto_inexistente_da_error_de_entrada(self):
        contenido = BytesIO()
        with ZipFile(DEMO) as original, ZipFile(contenido, "w") as roto:
            for nombre in original.namelist():
                datos = original.read(nombre)
                if nombre == "xl/worksheets/sheet1.xml":
                    datos = re.sub(
                        rb'<c r="A5".*?</c>',
                        b'<c r="A5" t="s"><v>999999</v></c>', datos,
                    )
                roto.writestr(nombre, datos)
        contenido.seek(0)
        with self.assertRaises(ErrorPuntoPartida) as contexto:
            cargar_punto_partida(contenido)
        self.assertTrue(contexto.exception.errores)

    def test_rechaza_fecha_invalida_aunque_el_lote_este_pendiente(self):
        errores = self.errores(lambda libro: setattr(libro["Lotes"]["D10"], "value", "fecha desconocida"))
        self.assertTrue(any("BOND1" in e and "fecha" in e for e in errores))

    def test_archivo_ilegible_da_error_de_entrada(self):
        with tempfile.TemporaryDirectory() as carpeta:
            ruta = Path(carpeta) / "roto.xlsx"
            ruta.write_text("No es un Excel", encoding="utf-8")
            with self.assertRaises(ErrorPuntoPartida) as contexto:
                cargar_punto_partida(ruta)
        self.assertTrue(contexto.exception.errores)

    def test_xml_roto_dentro_del_excel_da_error_de_entrada(self):
        contenido = BytesIO()
        with ZipFile(DEMO) as original, ZipFile(contenido, "w") as roto:
            for nombre in original.namelist():
                datos = original.read(nombre)
                if nombre == "xl/worksheets/sheet1.xml":
                    datos = b"<worksheet><sheetData><"
                roto.writestr(nombre, datos)
        contenido.seek(0)
        with self.assertRaises(ErrorPuntoPartida):
            cargar_punto_partida(contenido)


if __name__ == "__main__":
    unittest.main()
