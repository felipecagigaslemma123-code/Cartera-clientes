"""Lecturas del historial con libros y CSV ficticios; sin modificar fixtures."""

import copy
import datetime as dt
import tempfile
import unittest
from pathlib import Path

from openpyxl import Workbook

from cartera._historial_lectura import (
    ErrorHistorial, clasificar, consolidar, leer_ajustes, leer_extracto, leer_mep,
)


FECHA = dt.date(2026, 1, 10)
ENCABEZADO = ["Liquida", "Operado", "Comprobante", "Numero", "Cantidad", "Especie", "Precio", "Importe", "Saldo", "Referencia"]
AJUSTES = "fecha,tipo,ticker,cantidad,importe,moneda,tc,tipo_activo,nota\n"


def renglon(numero=1, importe=-100, saldo=900, **cambios):
    fila = dict(operado=FECHA, comprobante="COMPRA NORMAL", numero=numero, cantidad=1, especie="AAA",
                importe=importe, saldo=saldo, referencia="", moneda="ARS", cuenta="PESOS", archivo="ficticio.xlsx", fila=numero+1)
    fila.update(cambios)
    return fila


class LecturaDeExtractos(unittest.TestCase):
    def setUp(self):
        temporal = tempfile.TemporaryDirectory()
        self.addCleanup(temporal.cleanup)
        self.raiz = Path(temporal.name)
        self.ruta = self.raiz / "ficticio.xlsx"

    def libro(self, titulo="PESOS", filas=None, encabezado=None):
        libro = Workbook()
        hoja = libro.active
        hoja.title = titulo
        hoja.append(ENCABEZADO if encabezado is None else encabezado)
        for fila in filas or []:
            hoja.append(fila)
        segunda = libro.create_sheet("Otra hoja")
        segunda.append(["Este contenido no es la cuenta solicitada"])
        libro.save(self.ruta)
        libro.close()

    def fila(self, **cambios):
        valores = dict(Liquida=FECHA, Operado=FECHA, Comprobante="COMPRA NORMAL", Numero=1, Cantidad=10,
                       Especie="AAA", Precio=10, Importe=-100, Saldo=900, Referencia=None)
        valores.update(cambios)
        return [valores[campo] for campo in ENCABEZADO]

    def test_primera_hoja_y_preservacion_de_datos_no_calculados(self):
        self.libro(filas=[self.fila(Comprobante="NO CONOCIDO", Precio="=1+2", Referencia="texto ficticio")])
        fila = leer_extracto(self.ruta)[0]
        self.assertEqual(fila["operado"], FECHA)
        self.assertEqual(fila["liquida"], FECHA)
        self.assertEqual(fila["precio"], "=1+2")
        self.assertEqual(fila["referencia"], "texto ficticio")
        self.assertEqual(clasificar(fila, []), "sin_clasificar")
        self.assertEqual((fila["archivo"], fila["fila"]), ("ficticio.xlsx", 2))

    def test_recoge_errores_de_todas_las_filas_con_contexto(self):
        self.libro(filas=[self.fila(Operado="no fecha", Cantidad="sin cantidad"), self.fila(Importe="=A1")])
        with self.assertRaises(ErrorHistorial) as error:
            leer_extracto(self.ruta)
        texto = str(error.exception)
        for esperado in ("ficticio.xlsx", "PESOS", "fila 2", "fila 3", "Operado", "Cantidad", "Importe"):
            self.assertIn(esperado, texto)

    def test_cantidad_vacia_y_especie_vacia_no_se_inventan_como_titulos(self):
        self.libro(filas=[self.fila(Comprobante="RECIBO DE COBRO", Cantidad=None, Especie=None)])
        fila = leer_extracto(self.ruta)[0]
        self.assertEqual(fila["cantidad"], 0)
        self.assertEqual(fila["especie"], "")

    def test_titulo_ambiguo_o_moneda_parcial_no_se_adivina(self):
        for titulo in ("PESOS DOLARES", "CABLE", "OTROSPESOS", "PESOS CABLE"):
            with self.subTest(titulo=titulo):
                self.libro(titulo=titulo)
                with self.assertRaises(ErrorHistorial):
                    leer_extracto(self.ruta)

    def test_filas_vacias_se_omiten_y_columnas_extra_no(self):
        self.libro(filas=[[None] * 10, self.fila()])
        self.assertEqual(leer_extracto(self.ruta)[0]["fila"], 3)
        self.libro(filas=[self.fila() + ["dato extra"]])
        with self.assertRaises(ErrorHistorial):
            leer_extracto(self.ruta)

    def test_encabezado_no_se_corrige_ni_se_infiere(self):
        encabezado = list(ENCABEZADO)
        encabezado[0] = "Liquida "
        self.libro(encabezado=encabezado)
        with self.assertRaises(ErrorHistorial):
            leer_extracto(self.ruta)

    def test_importe_y_numero_booleanos_no_son_validos(self):
        for cambios in ({"Importe": True}, {"Numero": True}):
            with self.subTest(cambios=cambios):
                self.libro(filas=[self.fila(**cambios)])
                with self.assertRaises(ErrorHistorial):
                    leer_extracto(self.ruta)

    def test_identificadores_alfanumericos_fraccionarios_y_vacios_se_conservan(self):
        self.libro(filas=[self.fila(Comprobante="NO CONOCIDO", Numero=valor) for valor in ("AB-12", 1.5, None)])
        filas = leer_extracto(self.ruta)
        self.assertEqual([fila["numero"] for fila in filas], ["AB-12", 1.5, ""])
        self.assertEqual([clasificar(fila, []) for fila in filas], ["sin_clasificar"] * 3)

    def test_numeros_de_comprobante_textuales_no_pierden_precision(self):
        self.libro(filas=[self.fila(Numero="10000000000000001"), self.fila(Numero="10000000000000002")])
        filas = leer_extracto(self.ruta)
        self.assertEqual([fila["numero"] for fila in filas], [10000000000000001, 10000000000000002])
        self.assertEqual(len(consolidar(filas)[0]), 2)

    def test_archivo_que_no_es_excel_informa_error_del_dominio(self):
        self.ruta.write_bytes(b"archivo ficticio roto")
        with self.assertRaises(ErrorHistorial) as error:
            leer_extracto(self.ruta)
        self.assertIn("ficticio.xlsx", str(error.exception))


class ConsolidacionAdicional(unittest.TestCase):
    def test_saldos_se_controlan_antes_de_quitar_duplicados_de_otros_archivos(self):
        primera = renglon(saldo=900, archivo="a.xlsx", fila=2)
        duplicada = dict(primera, archivo="b.xlsx")
        otra = renglon(numero=2, importe=-100, saldo=500, archivo="b.xlsx", fila=3)
        filas, avisos = consolidar([primera, duplicada, otra])
        self.assertEqual(len(filas), 2)
        self.assertEqual(len(avisos), 1)
        self.assertIn("b.xlsx", avisos[0])
        self.assertIn("3", avisos[0])

    def test_consolidacion_no_muta_entradas_y_copia_extras(self):
        originales = [renglon(datos={"nota": "ficticia"})]
        antes = copy.deepcopy(originales)
        filas, _ = consolidar(originales)
        filas[0]["datos"]["nota"] = "editada"
        self.assertEqual(originales, antes)

    def test_saldo_usa_orden_fisico_por_archivo_y_tolerancia_inclusiva(self):
        a = renglon(numero=1, importe=0, saldo=100)
        b = renglon(numero=2, importe=0, saldo=101)
        self.assertEqual(consolidar([b, a])[1], [])
        b["saldo"] = 101.001
        self.assertEqual(len(consolidar([b, a])[1]), 1)

    def test_dato_de_saldo_desconocido_no_permite_control_falso(self):
        filas = [renglon(numero=1, saldo=100), renglon(numero=2, saldo=None), renglon(numero=3, saldo=1000)]
        self.assertEqual(consolidar(filas)[1], [])

    def test_clasificacion_desconocida_no_tiene_heuristicas(self):
        for comprobante in ("VENTA ESPECIAL", "VENTA TRADING EXTRA", "DIVIDENDO", ""):
            self.assertEqual(clasificar({"comprobante": comprobante}, []), "sin_clasificar")
        self.assertEqual(clasificar({"comprobante": "NOTA DE CREDITO U$S", "referencia": None}, []), "sin_clasificar")


class LecturaAuxiliares(unittest.TestCase):
    def setUp(self):
        temporal = tempfile.TemporaryDirectory()
        self.addCleanup(temporal.cleanup)
        self.raiz = Path(temporal.name)

    def test_ajuste_usd_sin_tc_conserva_faltante_para_mep_historico(self):
        ruta = self.raiz / "ajustes_historial.csv"
        ruta.write_text(AJUSTES + "2026-01-10,compra,AAA,1,10,USD,,cedear,transferencia ficticia\n", encoding="utf-8")
        ajuste = leer_ajustes(ruta)[0]
        self.assertEqual(ajuste["moneda"], "USD")
        self.assertIsNone(ajuste["tc"])
        self.assertEqual(ajuste["fila"], 2)

    def test_ajuste_con_tc_positivo_lo_conserva(self):
        ruta = self.raiz / "ajustes_historial.csv"
        ruta.write_text(AJUSTES + "2026-01-10,compra,AAA,1,10,USD,1400,cedear,\n", encoding="utf-8")
        self.assertEqual(leer_ajustes(ruta)[0]["tc"], 1400)

    def test_ajustes_inaplicables_reunen_errores_de_filas(self):
        ruta = self.raiz / "ajustes_historial.csv"
        ruta.write_text(AJUSTES + "2026-01-10,venta,,1,10,ARS,,,\n2026-01-10,renta,AAA,1,10,ARS,,,\n", encoding="utf-8")
        with self.assertRaises(ErrorHistorial) as error:
            leer_ajustes(ruta)
        self.assertIn("fila 2", str(error.exception))
        self.assertIn("fila 3", str(error.exception))

    def test_mep_rechaza_valores_no_positivos_no_finitos_y_fechas_ambiguas(self):
        ruta = self.raiz / "mep_diario.csv"
        for datos in ("2026-01-10,0\n", "2026-01-10,NaN\n", "10/01/2026,1500\n",
                      "2026-01-10,1500\n2026-01-10,1501\n"):
            with self.subTest(datos=datos):
                ruta.write_text("fecha,mep\n" + datos, encoding="utf-8")
                with self.assertRaises(ErrorHistorial):
                    leer_mep(ruta)

    def test_mep_misma_fecha_mismo_valor_no_es_ambiguo(self):
        ruta = self.raiz / "mep_diario.csv"
        ruta.write_text("fecha,mep\n2026-01-10,1500\n2026-01-10,1500.00\n", encoding="utf-8")
        self.assertEqual(leer_mep(ruta), {FECHA: 1500})

    def test_archivos_auxiliares_ausentes_son_opcionales_y_directorios_invalidos(self):
        self.assertEqual(leer_mep(self.raiz / "falta.csv"), {})
        self.assertEqual(leer_ajustes(self.raiz / "falta.csv"), [])
        for leer in (leer_mep, leer_ajustes):
            with self.assertRaises(ErrorHistorial):
                leer(self.raiz)


class OrdenDelDia(unittest.TestCase):
    def test_compras_del_extracto_antes_que_ajustes(self):
        from cartera.historial import construir_historial
        dia = dt.date(2026, 1, 10)
        fila = {"operado": dia, "comprobante": "COMPRA NORMAL", "numero": 1, "cantidad": 10, "especie": "AAA", "importe": -1000.0,
                "saldo": None, "referencia": "", "moneda": "ARS", "cuenta": "PESOS", "archivo": "x", "fila": 2}
        venta = dict(fila, comprobante="VENTA", numero=2, cantidad=-10, importe=1100.0)
        ajuste = {"fecha": dia, "tipo": "compra", "ticker": "AAA", "cantidad": 10, "importe": 900.0, "moneda": "ARS", "tc": None, "tipo_activo": "", "nota": ""}
        h = construir_historial([fila, venta], ajustes=[ajuste])
        self.assertAlmostEqual(h.realizados[0].costo_ars, 1000.0)
        self.assertEqual(h.lotes[0].origen, "estimado")


class DimensionDeclarada(unittest.TestCase):
    def test_lee_todo_aunque_declare_un_rango_menor(self):
        import re
        import zipfile
        from openpyxl import Workbook
        with tempfile.TemporaryDirectory() as carpeta:
            origen, destino = Path(carpeta) / "o.xlsx", Path(carpeta) / "d.xlsx"
            libro = Workbook()
            libro.active.title = "Cuenta Corriente DOLARES"
            libro.active.append(["Liquida", "Operado", "Comprobante", "Numero", "Cantidad", "Especie", "Precio", "Importe", "Saldo", "Referencia"])
            momento = dt.datetime(2026, 1, 10)
            libro.active.append([momento, momento, "DIVIDENDOS", 5, 0, "AAA", 0, 1.5, 1.5, None])
            libro.save(origen)
            with zipfile.ZipFile(origen) as entrada, zipfile.ZipFile(destino, "w") as salida:
                for nombre in entrada.namelist():
                    datos = entrada.read(nombre)
                    if nombre == "xl/worksheets/sheet1.xml":
                        datos = re.sub(rb'<dimension ref="[^"]+"', b'<dimension ref="A1:E2"', datos)
                    salida.writestr(nombre, datos)
            filas = leer_extracto(destino)
            self.assertEqual(filas[0]["importe"], 1.5)
            self.assertEqual(filas[0]["especie"], "AAA")


if __name__ == "__main__":
    unittest.main()
