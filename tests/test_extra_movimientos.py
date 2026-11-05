"""Casos adicionales de la etapa 5: solo carteras y movimientos ficticios."""

import copy
import datetime as dt
import stat
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch

from cartera.movimientos import (
    ErrorMovimiento, agregar_movimiento, aplicar_movimientos, cartera_actual,
    leer_movimientos, validar_movimientos,
)
from cartera.punto_partida import Lote, Posicion, PuntoPartida


CERO = dt.date(2026, 10, 1)
FECHA = dt.date(2026, 10, 10)
HOY = dt.date(2026, 10, 20)
COLUMNAS = "fecha,tipo,ticker,cantidad,importe,moneda,tc,tipo_activo,nota"


def movimiento(tipo="deposito", **cambios):
    valor = dict(fecha=FECHA, tipo=tipo, ticker="", cantidad=0, importe=100, nota="")
    valor.update(cambios)
    return valor


def punto(cantidad=10.0, cantidad_lote=None):
    return PuntoPartida(
        [Posicion("DEMO", "Especie ficticia", "cedear", cantidad, 1)],
        [Lote("DEMO", cantidad if cantidad_lote is None else cantidad_lote,
              "estimado", dt.date(2026, 1, 1), 100, cantidad * 100, "ficticio")],
    )


class FifoYTenenciasAdicionales(unittest.TestCase):
    def test_cantidades_decimales_no_dejan_residuos_ni_mutan_entradas(self):
        lotes = [Lote("DEMO", 0.3, "extracto", CERO, None, 30, "")]
        movimientos = [movimiento("venta", ticker="DEMO", cantidad=0.1, importe=12),
                       movimiento("venta", ticker="DEMO", cantidad=0.2, importe=24)]
        copia = copy.deepcopy((lotes, movimientos))
        restantes, realizados = aplicar_movimientos(lotes, movimientos)
        self.assertEqual(restantes, [])
        self.assertAlmostEqual(sum(venta.costo for venta in realizados), 30)
        self.assertEqual((lotes, movimientos), copia)

    def test_fifo_de_lotes_con_igual_fecha_conserva_orden_de_carga(self):
        lotes = [Lote("DEMO", 1, "estimado", CERO, 100, 100, "primero"),
                 Lote("DEMO", 1, "extracto", CERO, None, 300, "segundo")]
        restantes, realizados = aplicar_movimientos(lotes, [movimiento("venta", ticker="DEMO", cantidad=1, importe=200)])
        self.assertEqual(restantes[0].nota, "segundo")
        self.assertEqual(realizados[0].origen_costo, "estimado")
        self.assertEqual(realizados[0].resultado, 100)

    def test_venta_mixta_con_pendiente_no_publica_un_costo_parcial(self):
        lotes = [Lote("DEMO", 1, "pendiente", None, None, None, ""),
                 Lote("DEMO", 1, "extracto", CERO, None, 100, "")]
        restantes, realizados = aplicar_movimientos(lotes, [movimiento("venta", ticker="DEMO", cantidad=1.5, importe=200)])
        self.assertEqual((restantes[0].cantidad, restantes[0].costo), (0.5, 50))
        self.assertEqual(realizados[0].origen_costo, "incompleto")
        self.assertIsNone(realizados[0].costo)
        self.assertIsNone(realizados[0].resultado)

    def test_cantidad_nominal_se_conserva_aunque_lotes_tengan_tolerancia(self):
        base = punto(cantidad=10, cantidad_lote=10.2)
        actual, _ = cartera_actual(base, [movimiento("venta", ticker="DEMO", cantidad=1, importe=200)])
        self.assertEqual(actual.posiciones[0].cantidad, 9)
        self.assertAlmostEqual(actual.lotes[0].cantidad, 9.2)
        self.assertEqual(base.posiciones[0].cantidad, 10)

    def test_tolerancia_en_lotes_no_autoriza_una_tenencia_negativa(self):
        with self.assertRaises(ErrorMovimiento):
            validar_movimientos(punto(cantidad=10, cantidad_lote=10.2),
                                [movimiento("venta", ticker="DEMO", cantidad=10.1)], CERO, HOY)

    def test_recompra_nueva_conserva_metadatos_aun_despues_de_venta_total(self):
        historial = [movimiento("compra", ticker="NUEVA", cantidad=10, tipo_activo="on"),
                     movimiento("venta", ticker="NUEVA", cantidad=10),
                     movimiento("compra", ticker="NUEVA", cantidad=3)]
        actual, _ = cartera_actual(punto(), historial)
        nueva = next(posicion for posicion in actual.posiciones if posicion.ticker == "NUEVA")
        self.assertEqual((nueva.cantidad, nueva.tipo, nueva.cotiza_cada, nueva.especie), (3, "on", 100, "NUEVA"))

    def test_especie_es_conocida_solo_desde_su_primera_compra(self):
        compra = movimiento("compra", ticker="NUEVA", cantidad=1, tipo_activo="bono")
        renta = movimiento("renta", ticker="NUEVA")
        with self.assertRaises(ErrorMovimiento):
            validar_movimientos(punto(), [renta, compra], CERO, HOY)
        validar_movimientos(punto(), [compra, renta], CERO, HOY)
        renta_anterior = dict(renta, fecha=FECHA - dt.timedelta(days=1))
        with self.assertRaises(ErrorMovimiento):
            validar_movimientos(punto(), [compra, renta_anterior], CERO, HOY)

    def test_cobros_de_especie_vendida_siguen_siendo_conocidos(self):
        historial = [movimiento("venta", ticker="DEMO", cantidad=10),
                     movimiento("renta", ticker="DEMO")]
        validar_movimientos(punto(), historial, CERO, HOY)

    def test_recoge_errores_de_formato_y_de_dominio_de_todas_las_filas(self):
        historial = [movimiento(fecha=CERO), movimiento(importe=True), movimiento("renta", ticker="DESCONOCIDA")]
        with self.assertRaises(ErrorMovimiento) as error:
            validar_movimientos(punto(), historial, CERO, HOY)
        self.assertIsInstance(error.exception, ValueError)
        self.assertGreaterEqual(len(error.exception.errores), 3)
        for indice in (1, 2, 3):
            self.assertIn("Movimiento {}".format(indice), str(error.exception))

    def test_numeros_no_finitos_y_booleanos_no_son_movimientos(self):
        for campo, valor in (("cantidad", float("inf")), ("cantidad", True),
                             ("importe", float("nan")), ("importe", False)):
            with self.subTest(campo=campo, valor=valor), self.assertRaises(ErrorMovimiento):
                validar_movimientos(punto(), [movimiento("compra", ticker="DEMO", cantidad=1, **{campo: valor})]
                                    if campo != "cantidad" else [movimiento("compra", ticker="DEMO", cantidad=valor)], CERO, HOY)
        with self.assertRaises(ErrorMovimiento):
            validar_movimientos(punto(), [movimiento(importe=1e308, moneda="USD", tc=1e308)], CERO, HOY)

    def test_rechaza_desbordes_de_cantidad_y_costo_acumulado(self):
        for campo in ("cantidad", "costo"):
            base = punto()
            base.posiciones[0].cantidad = 1e308 if campo == "cantidad" else 1
            base.lotes[0].cantidad = base.posiciones[0].cantidad
            base.lotes[0].costo = 1e308 if campo == "costo" else 1
            compra = movimiento("compra", ticker="DEMO", cantidad=base.posiciones[0].cantidad,
                                importe=base.lotes[0].costo)
            with self.subTest(campo=campo), self.assertRaises(ErrorMovimiento):
                validar_movimientos(base, [compra], CERO, HOY)
            with self.subTest(campo=campo), self.assertRaises(ErrorMovimiento):
                aplicar_movimientos(base.lotes, [compra])

    def test_limites_temporales_usan_hoy_inyectado_y_no_el_reloj(self):
        validar_movimientos(punto(), [movimiento(fecha=HOY)], CERO, HOY)
        validar_movimientos(punto(), [movimiento(fecha=CERO)], None, HOY)
        with self.assertRaises(ErrorMovimiento):
            validar_movimientos(punto(), [movimiento(fecha=HOY + dt.timedelta(days=1))], CERO, HOY)


class PersistenciaAdicional(unittest.TestCase):
    def setUp(self):
        temporal = tempfile.TemporaryDirectory()
        self.addCleanup(temporal.cleanup)
        self.raiz = Path(temporal.name)
        self.ruta = self.raiz / "movimientos.csv"
        self.punto = punto()

    def agregar(self, valor=None):
        return agregar_movimiento(self.ruta, self.punto, valor or movimiento(), CERO, HOY)

    def test_invalido_no_crea_carpeta_ni_archivo(self):
        destino = self.raiz / "todavia_no_existe" / "movimientos.csv"
        with self.assertRaises(ErrorMovimiento):
            agregar_movimiento(destino, self.punto, movimiento(importe="1.234,56"), CERO, HOY)
        self.assertFalse(destino.parent.exists())
        self.assertEqual(list(self.raiz.iterdir()), [])

    def test_guarda_texto_libre_numeros_normalizados_y_permisos_privados(self):
        nota = 'Ficticio, con "comillas" y\nsegunda línea áé'
        devuelto = self.agregar(movimiento(fecha="2026-10-10", importe="123.50", cantidad="", moneda=" ars ", nota=nota))
        self.assertEqual(devuelto["importe"], 123.5)
        self.assertEqual(devuelto["fecha"], FECHA)
        self.assertEqual(devuelto["moneda"], "ARS")
        self.assertEqual(leer_movimientos(self.ruta), [devuelto])
        self.assertEqual(stat.S_IMODE(self.ruta.stat().st_mode), 0o600)
        self.assertEqual(list(self.raiz.iterdir()), [self.ruta])

    def test_agregar_conserva_todos_los_bytes_del_historial_previo(self):
        anterior = (COLUMNAS + "\r\n2026-10-10,deposito,,0,12.3400,ARS,,,nota ficticia").encode("utf-8")
        self.ruta.write_bytes(anterior)
        self.agregar(movimiento(importe=5))
        self.assertTrue(self.ruta.read_bytes().startswith(anterior + b"\n"))
        self.assertEqual([m["importe"] for m in leer_movimientos(self.ruta)], [12.34, 5])

    def test_desborde_acumulado_no_se_persiste(self):
        self.punto.posiciones[0].cantidad = 1
        self.punto.lotes[0].cantidad = 1
        self.punto.lotes[0].costo = 1e308
        with self.assertRaises(ErrorMovimiento):
            self.agregar(movimiento("compra", ticker="DEMO", cantidad=1, importe=1e308))
        self.assertFalse(self.ruta.exists())
        self.assertEqual(list(self.raiz.iterdir()), [])

    def test_historial_invalido_semantico_no_se_sobrescribe(self):
        anterior = (COLUMNAS + "\n2026-10-10,deposito,DEMO,0,100,ARS,,,\n").encode("utf-8")
        self.ruta.write_bytes(anterior)
        with self.assertRaises(ErrorMovimiento):
            self.agregar()
        self.assertEqual(self.ruta.read_bytes(), anterior)
        self.assertEqual(list(self.raiz.iterdir()), [self.ruta])

    def test_historial_invalido_de_formato_no_se_sobrescribe(self):
        anterior = (COLUMNAS + "\n2026-10-10,deposito,,,texto,ARS,,,\n").encode("utf-8")
        self.ruta.write_bytes(anterior)
        with self.assertRaises(ErrorMovimiento):
            self.agregar()
        self.assertEqual(self.ruta.read_bytes(), anterior)

    def test_carga_retroactiva_se_valida_con_las_ventas_posteriores(self):
        self.agregar(movimiento("venta", ticker="DEMO", cantidad=10))
        anterior = self.ruta.read_bytes()
        with self.assertRaises(ErrorMovimiento):
            self.agregar(movimiento("venta", fecha=FECHA - dt.timedelta(days=1), ticker="DEMO", cantidad=1))
        self.assertEqual(self.ruta.read_bytes(), anterior)

    def test_fallo_al_publicar_preserva_archivo_previo_y_limpia_temporal(self):
        self.agregar()
        anterior = self.ruta.read_bytes()
        with patch("cartera.movimientos.os.replace", side_effect=OSError("fallo ficticio")):
            with self.assertRaises(OSError):
                self.agregar()
        self.assertEqual(self.ruta.read_bytes(), anterior)
        self.assertEqual(list(self.raiz.iterdir()), [self.ruta])

    def test_fallo_antes_de_publicar_no_crea_historial(self):
        with patch("cartera.movimientos.os.fsync", side_effect=OSError("fallo ficticio")):
            with self.assertRaises(OSError):
                self.agregar()
        self.assertFalse(self.ruta.exists())
        self.assertEqual(list(self.raiz.iterdir()), [])

    def test_cargas_concurrentes_no_pierden_filas(self):
        with ThreadPoolExecutor(max_workers=4) as ejecutor:
            resultados = list(ejecutor.map(lambda importe: self.agregar(movimiento(importe=importe)), range(1, 9)))
        self.assertEqual(len(resultados), 8)
        self.assertEqual(sorted(m["importe"] for m in leer_movimientos(self.ruta)), list(range(1, 9)))

    def test_lector_reune_errores_con_filas_y_rechaza_columnas_distintas(self):
        self.ruta.write_text(COLUMNAS + "\n2026-10-10,deposito,,,abc,ARS,,,\n2026-10-10,deposito,,0,2,ARS,,,,extra\n", encoding="utf-8")
        with self.assertRaises(ErrorMovimiento) as error:
            leer_movimientos(self.ruta)
        self.assertIn("Fila 2", str(error.exception))
        self.assertIn("Fila 3", str(error.exception))

    def test_ausencia_y_solo_encabezado_son_historial_vacio(self):
        self.assertEqual(leer_movimientos(self.ruta), [])
        self.ruta.write_text(COLUMNAS + "\n", encoding="utf-8")
        self.assertEqual(leer_movimientos(self.ruta), [])


class LineasEnBlanco(unittest.TestCase):
    def test_se_ignoran_y_se_sigue_pudiendo_agregar(self):
        with tempfile.TemporaryDirectory() as carpeta:
            ruta = Path(carpeta) / "movimientos.csv"
            ruta.write_text("fecha,tipo,ticker,cantidad,importe,moneda,tc,tipo_activo,nota\n"
                            "\n2026-10-10,deposito,,,5,ARS,,,\n\n ,,,,,,,,\n", encoding="utf-8")
            self.assertEqual(len(leer_movimientos(ruta)), 1)
            agregar_movimiento(ruta, PuntoPartida([], []),
                               {"fecha": dt.date(2026, 10, 11), "tipo": "deposito", "importe": 7.0},
                               dt.date(2026, 10, 1), dt.date(2026, 10, 20))
            self.assertEqual([m["importe"] for m in leer_movimientos(ruta)], [5.0, 7.0])


if __name__ == "__main__":
    unittest.main()
