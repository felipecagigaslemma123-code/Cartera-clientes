"""Fronteras del historial realizado; exclusivamente importes y especies ficticios."""

import copy
import datetime as dt
import unittest

from cartera.historial import ErrorHistorial, construir_historial, conciliar_tenencias
from cartera.punto_partida import Posicion
from test_etapa6_historial import D1, D2, D3, ajuste, compra, f, venta


class HistorialLotesAdicional(unittest.TestCase):
    def test_no_muta_filas_ajustes_mep_ni_lotes_originales(self):
        filas = [compra(D1, "AAA", 10, 100), venta(D2, "AAA", 12, 200),
                 f(D3, "DESCONOCIDO", 50, referencia="texto íntegro")]
        ajustes = [ajuste(D1, "compra", "AAA", 5, 80)]
        mep = {D1: 1500}
        copia = copy.deepcopy((filas, ajustes, mep))
        h = construir_historial(filas, ajustes, mep=mep)
        self.assertEqual((filas, ajustes, mep), copia)
        h.lotes[0].costo = -1
        h.sin_clasificar[0]["referencia"] = "editado"
        self.assertEqual((filas, ajustes, mep), copia)

    def test_venta_incompleta_no_asigna_compras_posteriores_a_su_costo(self):
        h = construir_historial([compra(D1, "AAA", 4, 400), venta(D2, "AAA", 10, 1500), compra(D3, "AAA", 2, 300)])
        self.assertEqual(h.realizados[0].cantidad_sin_lote, 6)
        self.assertIsNone(h.realizados[0].resultado_ars)
        self.assertEqual(h.lotes[0].cantidad, 2)
        self.assertEqual(h.lotes[0].costo, 300)
        self.assertEqual(h.total_conocido, 0)
        self.assertTrue(any("6" in aviso for aviso in h.avisos))

    def test_fifo_decimal_no_deja_lotes_cero_ni_residuo(self):
        h = construir_historial([compra(D1, "AAA", 0.3, 30),
                                 venta(D2, "AAA", 0.1, 12, 2), venta(D2, "AAA", 0.2, 24, 3)])
        self.assertEqual(h.lotes, [])
        self.assertEqual(h.ventas_sin_dato, 0)
        self.assertAlmostEqual(h.total_conocido, 6)

    def test_compras_misma_fecha_respetan_orden_numero(self):
        h = construir_historial([compra(D1, "AAA", 1, 300, 20), compra(D1, "AAA", 1, 100, 10), venta(D2, "AAA", 1, 200)])
        self.assertEqual(h.realizados[0].costo_ars, 100)
        self.assertEqual(h.lotes[0].costo, 300)

    def test_compra_ajustada_mismo_dia_esta_disponible_antes_de_venta(self):
        h = construir_historial([venta(D1, "AAA", 1, 110)], ajustes=[ajuste(D1, "compra", "AAA", 1, 100)])
        self.assertEqual(h.realizados[0].resultado_ars, 10)
        self.assertEqual(h.realizados[0].origen_costo, "estimado")
        self.assertEqual(h.realizado_estimado, 10)

    def test_venta_usd_sin_mep_conserva_costo_conocido_y_no_inventa_resultado(self):
        h = construir_historial([compra(D1, "AAA", 1, 100), venta(D2, "AAA", 1, 2, moneda="USD", cuenta="CABLE")])
        r = h.realizados[0]
        self.assertEqual(r.costo_ars, 100)
        self.assertIsNone(r.importe_ars)
        self.assertIsNone(r.resultado_ars)
        self.assertEqual((h.ventas_sin_dato, h.valores_sin_dato), (1, 1))
        self.assertEqual(h.total_conocido, 0)

    def test_cierre_agrega_cuentas_y_monedas_del_dia_una_sola_vez(self):
        filas = [compra(D1, "BON", 10, 1000), f(D2, "RENTA Y AMORTIZ", 700, "BON", numero=3),
                 f(D2, "RENTA Y AMORTIZ", 0.3, "BON", numero=4, moneda="USD", cuenta="CABLE")]
        h = construir_historial(filas, cierres=["BON"], mep={D2: 1500})
        self.assertEqual(len(h.realizados), 1)
        self.assertEqual(h.realizados[0].cantidad, 10)
        self.assertEqual(h.realizados[0].importe_ars, 1150)
        self.assertEqual(h.total_conocido, 150)
        self.assertEqual(h.ingresos["renta"]["equivalente_ars"], 0)
        self.assertEqual(h.lotes, [])

    def test_cierre_con_un_pago_sin_mep_queda_sin_dato_entero(self):
        filas = [compra(D1, "BON", 10, 1000), f(D2, "RENTA Y AMORTIZ", 700, "BON", numero=3),
                 f(D2, "RENTA Y AMORTIZ", 1, "BON", numero=4, moneda="USD", cuenta="DOLARES")]
        h = construir_historial(filas, cierres=["BON"])
        self.assertIsNone(h.realizados[0].importe_ars)
        self.assertIsNone(h.realizados[0].resultado_ars)
        self.assertEqual(h.realizados[0].costo_ars, 1000)
        self.assertEqual((h.ventas_sin_dato, h.valores_sin_dato), (1, 1))
        self.assertEqual(h.lotes, [])

    def test_venta_y_cierre_mismo_dia_por_numero(self):
        filas = [compra(D1, "BON", 10, 1000), f(D2, "RENTA Y AMORTIZ", 750, "BON", numero=8),
                 venta(D2, "BON", 4, 440, numero=7)]
        h = construir_historial(filas, cierres=["BON"])
        self.assertEqual([r.clase for r in h.realizados], ["venta", "cierre"])
        self.assertEqual([r.cantidad for r in h.realizados], [4, 6])
        self.assertEqual(h.total_conocido, 190)

    def test_rechaza_trade_sin_especie_o_cantidad_cero(self):
        for fila in (compra(D1, "", 1, 100), venta(D1, "AAA", 0, 100)):
            with self.subTest(fila=fila), self.assertRaises(ErrorHistorial):
                construir_historial([fila])


class HistorialIngresosAdicional(unittest.TestCase):
    def test_total_conocido_no_pierde_ingreso_ars_por_otro_usd_sin_cambio(self):
        filas = [f(D1, "DIVIDENDOS", 100, "AAA", numero=1),
                 f(D2, "DIVIDENDOS", 1, "AAA", numero=2, moneda="USD", cuenta="CABLE")]
        h = construir_historial(filas)
        self.assertEqual(h.total_conocido, 100)
        self.assertEqual(h.ingresos["dividendo"]["ARS"], 100)
        self.assertEqual(h.ingresos["dividendo"]["USD"], 1)
        self.assertIsNone(h.ingresos["dividendo"]["equivalente_ars"])
        self.assertEqual(h.valores_sin_dato, 1)

    def test_ajustes_dividendos_y_gasto_respetan_signos_y_tc(self):
        h = construir_historial([], ajustes=[ajuste(D1, "dividendo", "AAA", 0, 2, "USD", 1500),
                                            ajuste(D1, "gasto", "", 0, 300)])
        self.assertEqual(h.ingresos["dividendo"]["USD"], 2)
        self.assertEqual(h.ingresos["dividendo"]["equivalente_ars"], 3000)
        self.assertEqual(h.ingresos["gastos"]["ARS"], -300)
        self.assertEqual(h.total_conocido, 2700)

    def test_ajuste_usd_sin_tc_usa_mep_del_dia(self):
        h = construir_historial([], ajustes=[ajuste(D1, "renta", "BON", 0, 2, "USD")], mep={D1: 1450})
        self.assertEqual(h.ingresos["renta"]["equivalente_ars"], 2900)
        self.assertEqual(h.total_conocido, 2900)

    def test_ajuste_usd_sin_tc_ni_mep_no_se_convierte_a_pesos(self):
        h = construir_historial([], ajustes=[ajuste(D1, "renta", "BON", 0, 2, "USD")])
        self.assertEqual(h.total_conocido, 0)
        self.assertEqual(h.valores_sin_dato, 1)
        self.assertIsNone(h.ingresos["renta"]["equivalente_ars"])

    def test_mep_futuro_no_se_utiliza(self):
        h = construir_historial([f(D1, "DIVIDENDOS", 2, "AAA", moneda="USD", cuenta="CABLE")],
                                mep={D1 + dt.timedelta(days=1): 1500})
        self.assertEqual(h.total_conocido, 0)
        self.assertEqual(h.valores_sin_dato, 1)

    def test_mep_mas_reciente_anterior_tiene_prioridad(self):
        h = construir_historial([f(D1 + dt.timedelta(days=5), "DIVIDENDOS", 1, "AAA", moneda="USD", cuenta="CABLE")],
                                mep={D1: 1500, D1 + dt.timedelta(days=4): 1600})
        self.assertEqual(h.total_conocido, 1600)

    def test_aportes_usd_sin_cambio_se_muestran_y_no_alteran_ingreso_conocido(self):
        h = construir_historial([f(D1, "RECIBO DE COBRO", 2, moneda="USD", cuenta="CABLE"),
                                 f(D2, "DIVIDENDOS", 100, "AAA")])
        self.assertEqual(h.aportes["USD"], 2)
        self.assertIsNone(h.aportes["equivalente_ars"])
        self.assertEqual(h.total_conocido, 100)

    def test_conversion_desconocida_no_se_oculta_ni_suma(self):
        original = f(D1, "NOTA DE CREDITO U$S", 5, moneda="USD", cuenta="CABLE", referencia="OTRA")
        original.update(precio="dato íntegro", liquida=D2)
        h = construir_historial([original])
        self.assertEqual(h.total_conocido, 0)
        self.assertEqual(h.sin_clasificar, [original])
        self.assertEqual(h.valores_sin_dato, 0)

    def test_comprobante_vacio_queda_listado_y_no_suma(self):
        original = f(D1, "", 500)
        h = construir_historial([original])
        self.assertEqual(h.total_conocido, 0)
        self.assertEqual(h.sin_clasificar, [original])

    def test_metadatos_privados_no_reclasifican_un_renglon_desconocido(self):
        original = f(D1, "ALGO NUEVO", 500)
        original.update(_clase="renta", _origen="estimado", _indice=99)
        h = construir_historial([original])
        self.assertEqual(h.total_conocido, 0)
        self.assertEqual(h.sin_clasificar, [original])

    def test_metadatos_privados_no_alteran_procedencia_de_extracto(self):
        origen = compra(D1, "AAA", 1, 100)
        origen.update(_clase="dividendo", _origen="estimado")
        h = construir_historial([origen, venta(D2, "AAA", 1, 120)])
        self.assertEqual(h.total_conocido, 20)
        self.assertEqual(h.realizados[0].origen_costo, "extracto")
        self.assertEqual(h.realizado_extracto, 20)
        self.assertEqual(h.realizado_estimado, 0)

    def test_caucion_agrupa_cuentas_pero_no_monedas(self):
        filas = [f(D1, "COMPRA CAUCION CONTADO", -100, numero=1, moneda="USD", cuenta="DOLARES"),
                 f(D1, "VENTA CAUCION TERMINO", 102, numero=2, moneda="USD", cuenta="CABLE"),
                 f(D1, "COMPRA CAUCION CONTADO", -100, numero=3)]
        h = construir_historial(filas, mep={D1: 1500})
        self.assertEqual(h.ingresos["caucion_colocada"]["USD"], 2)
        self.assertEqual(h.ingresos["caucion_colocada"]["ARS"], 0)
        self.assertEqual(h.total_conocido, 3000)
        self.assertTrue(any("3" in a for a in h.avisos))

    def test_caucion_sin_pareja_lista_todos_los_comprobantes(self):
        h = construir_historial([f(D1, "COMPRA CAUCION TERMINO", -100, numero=21),
                                 f(D1, "COMPRA CAUCION TERMINO", -200, numero=35)])
        self.assertEqual(h.total_conocido, 0)
        self.assertTrue(any("21" in aviso and "35" in aviso for aviso in h.avisos))
        self.assertEqual(h.ingresos["caucion_tomada"]["ARS"], 0)

    def test_caucion_no_empareja_fechas_diferentes(self):
        h = construir_historial([f(D1, "COMPRA CAUCION CONTADO", -100, numero=1),
                                 f(D2, "VENTA CAUCION TERMINO", 102, numero=2)])
        self.assertEqual(h.total_conocido, 0)
        self.assertEqual(len(h.avisos), 2)

    def test_caucion_usd_con_patas_completas_sin_mep_excluye_solo_interes(self):
        h = construir_historial([f(D1, "COMPRA CAUCION CONTADO", -100, numero=1, moneda="USD", cuenta="CABLE"),
                                 f(D1, "VENTA CAUCION TERMINO", 102, numero=2, moneda="USD", cuenta="CABLE")])
        self.assertEqual(h.ingresos["caucion_colocada"]["USD"], 2)
        self.assertIsNone(h.ingresos["caucion_colocada"]["equivalente_ars"])
        self.assertEqual(h.total_conocido, 0)
        self.assertEqual(h.valores_sin_dato, 1)

    def test_dividendo_usd_cero_no_necesita_mep_para_saber_que_vale_cero(self):
        h = construir_historial([f(D1, "DIVIDENDOS", 0, "AAA", moneda="USD", cuenta="CABLE")])
        self.assertEqual(h.total_conocido, 0)
        self.assertEqual(h.valores_sin_dato, 0)
        self.assertEqual(h.ingresos["dividendo"]["equivalente_ars"], 0)


class HistorialValidacionAdicional(unittest.TestCase):
    def test_rechaza_numeros_no_finitos_y_booleanos(self):
        for campo, valor in (("importe", float("nan")), ("cantidad", float("inf")), ("saldo", True)):
            fila = f(D1, "DIVIDENDOS", 1)
            fila[campo] = valor
            with self.subTest(campo=campo), self.assertRaises(ErrorHistorial):
                construir_historial([fila])

    def test_rechaza_tipo_ajuste_no_permitido_y_tc_invalido(self):
        for valor in (ajuste(D1, "deposito", "", 0, 1), ajuste(D1, "renta", "AAA", 0, 1, "USD", -1)):
            with self.subTest(valor=valor), self.assertRaises(ErrorHistorial):
                construir_historial([], ajustes=[valor])

    def test_rechaza_acumulados_no_finitos(self):
        with self.assertRaises(ErrorHistorial):
            construir_historial([f(D1, "DIVIDENDOS", 1e308, numero=1), f(D1, "DIVIDENDOS", 1e308, numero=2)])

    def test_no_cambia_entradas_al_conciliar_y_tol_exacto_es_inclusivo(self):
        h = construir_historial([compra(D1, "AAA", 10, 100)])
        posiciones = [Posicion("AAA", "Ficticia", "cedear", 10.5, 1)]
        copia = copy.deepcopy((h.lotes, posiciones))
        self.assertEqual(conciliar_tenencias(h.lotes, posiciones), {})
        self.assertEqual((h.lotes, posiciones), copia)
        posiciones[0].cantidad = 10.5001
        self.assertIn("AAA", conciliar_tenencias(h.lotes, posiciones))


if __name__ == "__main__":
    unittest.main()
