"""Cálculos de letras y asociación de compras: solo carteras ficticias."""

import copy
import unittest
from datetime import date, datetime, timezone
from decimal import Decimal
from unittest.mock import patch

from cartera.letras import (
    ErrorLetra, calcular_letras, referencias_compras, validar_compras,
    validar_dato_compra,
)
from cartera.punto_partida import Lote, Posicion, PuntoPartida


HOY = date(2026, 11, 5)
COMPRA = date(2026, 1, 1)
TICKER = "LETRA_DEMO"


def punto(cantidad=1000, lotes=None):
    if lotes is None:
        lotes = [Lote(TICKER, cantidad, "extracto", COMPRA, 999, 9990, "Costo ficticio con gastos")]
    return PuntoPartida([Posicion(TICKER, "Letra ficticia", "letra", cantidad, 100)], lotes)


def contrato(**cambios):
    letra = {"familia": "LECAP", "moneda_pago": "ARS", "fecha_emision": "2026-01-01",
             "tem_emision": "0", "base_nominal": "100", "fuente": "Contrato ficticio"}
    vencimiento = cambios.pop("vencimiento", "2027-01-01")
    letra.update(cambios)
    return {TICKER: {"vencimiento": vencimiento, "letra": letra}}


def movimiento(tipo, fecha=date(2026, 2, 1), **cambios):
    registro = {"fecha": fecha, "tipo": tipo, "ticker": TICKER, "cantidad": 100,
                "importe": 100, "moneda": "ARS", "tc": None, "tipo_activo": "", "nota": "Ficticio"}
    registro.update(cambios)
    return registro


def precio(base, movimientos=(), referencia="base:1", valor="80", moneda="ARS", liquidacion="2026-01-01"):
    fuente = next(dato for dato in referencias_compras(base, movimientos) if dato["referencia"] == referencia)
    return {"referencia": referencia, "huella": fuente["huella"], "precio": valor,
            "moneda": moneda, "fecha_liquidacion": liquidacion}


def archivo(*compras):
    return {"esquema_version": 1, "compras": list(compras)}


def fila(base=None, movimientos=(), instrumentos=None, compras=None, hoy=HOY):
    return calcular_letras(base or punto(), movimientos,
                          contrato() if instrumentos is None else instrumentos, compras, hoy)["posiciones"][0]


class CalculosLetrasAprobados(unittest.TestCase):
    def test_tasa_cero_y_nominales_no_usan_costo_neto_como_precio(self):
        base = punto()
        copia = copy.deepcopy(base)
        salida = fila(base)
        self.assertEqual(Decimal(salida["valor_por_base"]), Decimal("100"))
        self.assertEqual(Decimal(salida["pago_vencimiento"]), Decimal("1000"))
        self.assertIsNone(salida["lotes"][0]["precio"])
        self.assertIsNone(salida["lotes"][0]["rendimiento"])
        self.assertIn("no se deducen del costo neto", " ".join(salida["avisos"]))
        self.assertEqual(base, copia)

    def test_una_tasa_mensual_capitaliza_doce_meses_contractuales(self):
        for familia in ("LECAP", "BONCAP"):
            with self.subTest(familia=familia):
                salida = fila(instrumentos=contrato(familia=familia, tem_emision="0.01"))
                self.assertEqual(Decimal(salida["valor_por_base"]), Decimal("112.682503013196972066120100"))
                self.assertEqual(Decimal(salida["pago_vencimiento"]), Decimal("1126.825030131969720661201000"))

    def test_base_contractual_distinta_no_cambia_precio_por100_ni_rendimiento(self):
        base = punto()
        compras = archivo(precio(base))
        pequena = fila(base, instrumentos=contrato(base_nominal="100"), compras=compras)
        grande = fila(base, instrumentos=contrato(base_nominal="1000"), compras=compras)
        self.assertEqual(Decimal(pequena["pago_vencimiento"]), Decimal(grande["pago_vencimiento"]))
        self.assertEqual(Decimal(grande["valor_por_base"]), Decimal("1000"))
        self.assertEqual(grande["lotes"][0]["precio"], "80")
        self.assertEqual(grande["lotes"][0]["base_precio"], "100")
        self.assertEqual(Decimal(grande["lotes"][0]["rendimiento"]), Decimal("0.25"))
        self.assertEqual(pequena["lotes"][0]["rendimiento"], grande["lotes"][0]["rendimiento"])
        self.assertEqual(pequena["lotes"][0]["tea"], grande["lotes"][0]["tea"])

    def test_dia_31_y_fin_febrero_conservan_convencion_contractual(self):
        for emision, vencimiento in (("2024-01-31", "2024-02-29"),
                                     ("2024-02-29", "2024-03-31"),
                                     ("2025-02-28", "2025-03-31")):
            with self.subTest(emision=emision, vencimiento=vencimiento):
                salida = fila(instrumentos=contrato(fecha_emision=emision, vencimiento=vencimiento, tem_emision="0.01"))
                self.assertEqual(Decimal(salida["valor_por_base"]), Decimal("101"))

    def test_rendimiento_a_un_ano_act365_usa_precio_manual(self):
        base = punto()
        salida = fila(base, compras=archivo(precio(base)))
        compra = salida["lotes"][0]
        self.assertEqual(compra["precio"], "80")
        self.assertEqual(Decimal(compra["rendimiento"]), Decimal("0.25"))
        self.assertEqual(Decimal(compra["tea"]), Decimal("0.25"))
        self.assertEqual(Decimal(salida["pago_vencimiento"]), Decimal("1000"))

    def test_liquidacion_cambia_anualizacion_sin_cambiar_hpr_o_pago(self):
        base = punto()
        temprana = fila(base, compras=archivo(precio(base)))
        tardia = fila(base, compras=archivo(precio(base, liquidacion="2026-07-01")))
        self.assertEqual(temprana["pago_vencimiento"], tardia["pago_vencimiento"])
        self.assertEqual(temprana["lotes"][0]["rendimiento"], tardia["lotes"][0]["rendimiento"])
        self.assertGreater(Decimal(tardia["lotes"][0]["tea"]), Decimal(temprana["lotes"][0]["tea"]))

    def test_cambio_de_precio_cambia_rendimiento_no_pago(self):
        base = punto()
        barata = fila(base, compras=archivo(precio(base, valor="80")))
        cara = fila(base, compras=archivo(precio(base, valor="125")))
        self.assertEqual(barata["pago_vencimiento"], cara["pago_vencimiento"])
        self.assertEqual(Decimal(cara["lotes"][0]["rendimiento"]), Decimal("-0.2"))

    def test_pago_usa_cantidad_vigente_con_diferencia_de_lotes(self):
        base = punto(1000, [Lote(TICKER, 1000.2, "extracto", COMPRA, None, 9990, "")])
        salida = fila(base)
        self.assertEqual(salida["cantidad"], 1000)
        self.assertEqual(salida["lotes"][0]["cantidad_restante"], 1000.2)
        self.assertEqual(Decimal(salida["pago_vencimiento"]), Decimal("1000"))
        self.assertIn("discrepancia nominal", " ".join(salida["avisos"]))

    def test_base_nominal_explicita_se_conserva_en_lelink_sin_formula(self):
        base = punto()
        datos = contrato(familia="LELINK", base_nominal="1000", moneda_pago="ARS")
        salida = fila(base, instrumentos=datos, compras=archivo(precio(base, valor="980", moneda="USD")))
        self.assertEqual(salida["base_nominal"], "1000")
        self.assertIsNone(salida["valor_por_base"])
        self.assertIsNone(salida["pago_vencimiento"])
        self.assertIsNone(salida["lotes"][0]["rendimiento"])
        self.assertIsNone(salida["lotes"][0]["tea"])
        self.assertIn("pendiente de validación", " ".join(salida["avisos"]))

    def test_lelink_sin_unidad_no_inventa_base_ni_pago(self):
        datos = contrato(familia="LELINK")
        del datos[TICKER]["letra"]["base_nominal"]
        salida = fila(instrumentos=datos)
        self.assertIsNone(salida["base_nominal"])
        self.assertIsNone(salida["pago_vencimiento"])
        self.assertIn("Base nominal", " ".join(salida["avisos"]))

    def test_familias_y_monedas_no_aprobadas_no_publican_pago(self):
        for cambios in ({"familia": "CER"}, {"familia": "TAMAR"}, {"moneda_pago": "USD"}):
            with self.subTest(cambios=cambios):
                salida = fila(instrumentos=contrato(**cambios))
                self.assertIsNone(salida["pago_vencimiento"])
                self.assertTrue(salida["avisos"])

    def test_campos_contractuales_faltantes_o_invalidos_no_se_sustituyen(self):
        for campo in ("familia", "moneda_pago", "fecha_emision", "tem_emision", "base_nominal", "fuente"):
            with self.subTest(campo=campo):
                datos = contrato()
                del datos[TICKER]["letra"][campo]
                salida = fila(instrumentos=datos)
                self.assertIsNone(salida["pago_vencimiento"])
                self.assertTrue(salida["avisos"])
        for cambios in ({"fecha_emision": "2027-01-01"}, {"fecha_emision": "fecha rota"},
                        {"tem_emision": "NaN"}, {"tem_emision": "-0.01"}, {"base_nominal": "0"}):
            with self.subTest(cambios=cambios):
                salida = fila(instrumentos=contrato(**cambios))
                self.assertIsNone(salida["pago_vencimiento"])
                self.assertTrue(salida["avisos"])

    def test_metadata_emision_invalida_con_precio_manual_no_interrumpe_panel(self):
        base = punto()
        salida = fila(base, instrumentos=contrato(fecha_emision="fecha rota"), compras=archivo(precio(base)))
        self.assertIsNone(salida["pago_vencimiento"])
        self.assertIsNone(salida["lotes"][0]["rendimiento"])
        self.assertIn("Emisión", " ".join(salida["avisos"]))

    def test_liquidacion_antes_de_emision_omite_solo_rendimiento(self):
        base = punto()
        salida = fila(base, instrumentos=contrato(fecha_emision="2026-02-01"), compras=archivo(precio(base)))
        self.assertIsNotNone(salida["pago_vencimiento"])
        self.assertIsNone(salida["lotes"][0]["rendimiento"])
        self.assertIn("precede la emisión", " ".join(salida["avisos"]))

    def test_precio_en_moneda_distinta_no_calcula_rendimiento(self):
        base = punto()
        salida = fila(base, compras=archivo(precio(base, moneda="USD")))
        self.assertEqual(salida["lotes"][0]["precio"], "80")
        self.assertIsNone(salida["lotes"][0]["rendimiento"])
        self.assertIn("monedas diferentes", " ".join(salida["avisos"]))

    def test_sin_fecha_compra_no_publica_rendimiento(self):
        base = punto(lotes=[Lote(TICKER, 1000, "extracto", None, None, 1000, "")])
        salida = fila(base, compras=archivo(precio(base)))
        self.assertIsNone(salida["lotes"][0]["rendimiento"])
        self.assertIn("falta fecha de compra", " ".join(salida["avisos"]))

    def test_liquidacion_en_o_despues_de_vencimiento_no_publica_rendimiento(self):
        base = punto()
        for liquidacion in ("2026-10-01", "2026-11-01"):
            with self.subTest(liquidacion=liquidacion):
                salida = fila(base, instrumentos=contrato(vencimiento="2026-10-01"),
                              compras=archivo(precio(base, liquidacion=liquidacion)))
                self.assertIsNone(salida["lotes"][0]["rendimiento"])
                self.assertIn("anterior al vencimiento", " ".join(salida["avisos"]))


class DiasCorridosYReferencias(unittest.TestCase):
    def test_fin_de_semana_y_bisiesto_se_cuentan_completos(self):
        for hoy, vencimiento, dias in ((date(2026, 7, 3), "2026-07-06", 3),
                                       (date(2024, 2, 28), "2024-03-01", 2),
                                       (date(2026, 11, 5), "2026-11-05", 0),
                                       (date(2026, 11, 5), "2026-11-04", -1)):
            with self.subTest(hoy=hoy, vencimiento=vencimiento):
                salida = fila(instrumentos=contrato(vencimiento=vencimiento), hoy=hoy)
                self.assertEqual(salida["dias_restantes"], dias)

    def test_hoy_por_defecto_es_argentina_en_frontera_utc(self):
        instante = datetime(2026, 11, 6, 1, 0, tzinfo=timezone.utc)
        class Reloj(datetime):
            @classmethod
            def now(cls, tz=None):
                return instante.astimezone(tz) if tz else instante
        with patch("cartera.letras.datetime", Reloj):
            salida = calcular_letras(punto(), [], contrato(vencimiento="2026-11-06"))
        self.assertEqual(salida["fecha_calculo"], "2026-11-05")
        self.assertEqual(salida["posiciones"][0]["dias_restantes"], 1)

    def test_fifo_venta_parcial_conserva_precio_del_lote_remanente(self):
        base = punto(100, [Lote(TICKER, 100, "extracto", COMPRA, None, 90, "Inicial")])
        movimientos = [movimiento("compra", cantidad=200), movimiento("venta", fecha=date(2026, 3, 1), cantidad=150)]
        entradas = copy.deepcopy((base, movimientos))
        compras = archivo(precio(base, movimientos), precio(base, movimientos, referencia="movimiento:1", valor="85", liquidacion="2026-02-02"))
        salida = fila(base, movimientos, compras=compras)
        self.assertEqual(salida["cantidad"], 150)
        self.assertEqual(Decimal(salida["pago_vencimiento"]), Decimal("150"))
        self.assertEqual(len(salida["lotes"]), 1)
        self.assertEqual(salida["lotes"][0]["referencia"], "movimiento:1")
        self.assertEqual(salida["lotes"][0]["cantidad_restante"], 150)
        self.assertEqual(salida["lotes"][0]["precio"], "85")
        referencias = referencias_compras(base, movimientos)
        self.assertEqual(referencias[0]["cantidad_restante"], 0)
        self.assertEqual((base, movimientos), entradas)

    def test_referencias_cuentan_todos_los_lotes_y_movimientos(self):
        base = punto()
        base.posiciones.insert(0, Posicion("ACC_DEMO", "Acción ficticia", "accion", 1, 1))
        base.lotes.insert(0, Lote("ACC_DEMO", 1, "extracto", COMPRA, None, 100, ""))
        movimientos = [movimiento("deposito", ticker="", cantidad=0), movimiento("compra", cantidad=100)]
        referencias = referencias_compras(base, movimientos)
        self.assertEqual([dato["referencia"] for dato in referencias], ["base:2", "movimiento:2"])

    def test_compra_de_nueva_letra_aparece_automaticamente(self):
        base = PuntoPartida([], [])
        movimientos = [movimiento("compra", tipo_activo="letra")]
        salida = fila(base, movimientos)
        self.assertEqual(salida["cantidad"], 100)
        self.assertEqual(salida["lotes"][0]["referencia"], "movimiento:1")
        self.assertIsNone(salida["lotes"][0]["precio"])

    def test_venta_total_desaparece_sin_borrar_referencias(self):
        base = punto()
        movimientos = [movimiento("venta", cantidad=1000)]
        salida = calcular_letras(base, movimientos, contrato(), hoy=HOY)
        self.assertEqual(salida["posiciones"], [])
        self.assertEqual(referencias_compras(base, movimientos)[0]["cantidad_restante"], 0)

    def test_lote_sin_fecha_es_primero_en_fifo(self):
        base = punto(200, [Lote(TICKER, 100, "pendiente", None, None, None, "Sin fecha"),
                           Lote(TICKER, 100, "extracto", COMPRA, None, 100, "Con fecha")])
        salida = fila(base, [movimiento("venta", cantidad=100)])
        self.assertEqual(salida["lotes"][0]["referencia"], "base:2")

    def test_precio_no_se_reasocia_si_cambia_la_base_o_se_reordena(self):
        base = punto(200, [Lote(TICKER, 100, "extracto", COMPRA, None, 100, "Primero"),
                           Lote(TICKER, 100, "extracto", COMPRA, None, 100, "Segundo")])
        compra = precio(base)
        for mutacion in ("costo", "orden"):
            with self.subTest(mutacion=mutacion):
                cambiada = copy.deepcopy(base)
                if mutacion == "costo":
                    cambiada.lotes[0].costo = 101
                else:
                    cambiada.lotes.reverse()
                salida = calcular_letras(cambiada, [], contrato(), archivo(compra), HOY)
                self.assertIsNone(salida["posiciones"][0]["lotes"][0]["precio"])
                self.assertIn("huella", " ".join(salida["avisos"]))

    def test_precio_no_se_reasocia_si_cambia_o_se_reordena_movimiento(self):
        base = PuntoPartida([], [])
        movimientos = [movimiento("compra", tipo_activo="letra"),
                       movimiento("compra", fecha=date(2026, 3, 1), cantidad=200)]
        compra = precio(base, movimientos, referencia="movimiento:1", liquidacion="2026-02-02")
        for mutacion in ("importe", "orden"):
            with self.subTest(mutacion=mutacion):
                cambiados = copy.deepcopy(movimientos)
                if mutacion == "importe":
                    cambiados[0]["importe"] = 101
                else:
                    cambiados.reverse()
                salida = calcular_letras(base, cambiados, contrato(), archivo(compra), HOY)
                self.assertTrue(all(lote["precio"] is None for lote in salida["posiciones"][0]["lotes"]))
                self.assertIn("huella", " ".join(salida["avisos"]))


class ValidacionPreciosLetras(unittest.TestCase):
    def test_schema_duplicados_y_claves_desconocidas_rechazados(self):
        base = punto()
        compra = precio(base)
        for bruto in ({"esquema_version": 2, "compras": []}, {"esquema_version": True, "compras": []},
                      {"esquema_version": 1, "compras": [], "extra": 1}, archivo(compra, compra),
                      archivo(dict(compra, extra=1))):
            with self.subTest(bruto=bruto):
                with self.assertRaises(ErrorLetra):
                    validar_compras(bruto)

    def test_precio_no_finito_no_positivo_o_bool_rechazado(self):
        base = punto()
        for valor in ("NaN", "Infinity", "-Infinity", "0", "-1", True, "1.234,56"):
            with self.subTest(valor=valor):
                with self.assertRaises(ErrorLetra):
                    validar_compras(archivo(precio(base, valor=valor)))

    def test_liquidacion_futura_o_previa_compra_no_se_usa(self):
        base = punto()
        referencias = referencias_compras(base, [])
        for liquidacion in ("2026-11-06", "2025-12-31"):
            with self.subTest(liquidacion=liquidacion):
                compra = precio(base, liquidacion=liquidacion)
                with self.assertRaises(ErrorLetra):
                    validar_dato_compra(compra, referencias, HOY)
                salida = calcular_letras(base, [], contrato(), archivo(compra), HOY)
                self.assertIsNone(salida["posiciones"][0]["lotes"][0]["precio"])
                self.assertTrue(salida["avisos"])

    def test_liquidacion_hoy_es_aceptada(self):
        base = punto()
        compra = precio(base, liquidacion=HOY.isoformat())
        salida = validar_dato_compra(compra, referencias_compras(base, []), HOY)
        self.assertEqual(salida["fecha_liquidacion"], HOY.isoformat())

    def test_referencia_ausente_se_lista_y_no_se_usa(self):
        base = punto()
        compra = precio(base)
        compra["referencia"] = "base:99"
        salida = calcular_letras(base, [], contrato(), archivo(compra), HOY)
        self.assertIn("no existe esa referencia", " ".join(salida["avisos"]))
        self.assertIsNone(salida["posiciones"][0]["lotes"][0]["precio"])

    def test_archivo_invalido_lista_problema_sin_ocultar_tenencias(self):
        salida = calcular_letras(punto(), [], contrato(), {"esquema_version": 99, "compras": []}, HOY)
        self.assertEqual(len(salida["posiciones"]), 1)
        self.assertIsNone(salida["posiciones"][0]["lotes"][0]["precio"])
        self.assertTrue(salida["avisos"])


if __name__ == "__main__":
    unittest.main()
