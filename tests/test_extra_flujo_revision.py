"""Revisión de la etapa 9: panel de flujo, control de cobros y calendario.

Datos ficticios. Cubre lo que `test_etapa9_flujo.py` no ejercita: `calcular_flujo`,
el movimiento `amortizacion` y la pantalla.
"""

import datetime as dt
import unittest
from decimal import Decimal

from cartera.dashboard import _panel_flujo
from cartera.flujo_fondos import calcular_flujo
from cartera.letras import referencias_compras
from cartera.movimientos import cartera_actual
from cartera.punto_partida import Lote, Posicion, PuntoPartida

D = dt.date
DIA_CERO = D(2026, 10, 1)


def cierre(fecha, liq, instrumentos):
    liq_d = D.fromisoformat(liq)
    ins = []
    for ticker, familia, moneda, plaza, pagos in instrumentos:
        f = [[(D.fromisoformat(d) - liq_d).days, a, r, 0.0] for d, a, r in pagos]
        ins.append({"tk": ticker, "g": "tp", "seg": "x", "k": familia, "cur": moneda, "fxc": 1.0,
                    "fxr": plaza, "px": 50.0, "pxa": 50.0, "liq": liq, "f": f})
    return {"fecha_cierre": fecha, "fecha_liquidacion": liq,
            "calculadora_bonos": {"liq": liq, "fx": {}, "ins": ins}}


PAGOS_BON1 = [("2027-01-09", 8.0, 0.24), ("2027-07-09", 8.0, 0.21)]
CIERRES = [cierre("2026-11-05", "2026-11-06", [
    ("BON1", "fix", "USD", "MEP", PAGOS_BON1),
    ("ONC1", "fix", "USD", "CCL", [("2027-01-17", 0.0, 4.125), ("2027-07-17", 100.0, 4.125)]),
    ("CER1", "cer", "ARS", "ARS", [("2027-03-01", 100.0, 1.0)]),
])]
INSTRUMENTOS = {"BON1": {"iamc": {"ticker": "BON1", "grupo": "tp"}},
                "ONC1": {"iamc": {"ticker": "ONC1", "grupo": "tp"}},
                "CER1": {"iamc": {"ticker": "CER1", "grupo": "tp"}}}


def base():
    return PuntoPartida(
        [Posicion("BON1", "Bono", "bono", 10000, 100), Posicion("ONC1", "ON", "on", 5000, 100),
         Posicion("CER1", "CER", "bono", 1000, 100), Posicion("SINV", "Sin vínculo", "bono", 1000, 100)],
        [Lote("BON1", 10000, "extracto", D(2026, 3, 10), None, 100.0, ""),
         Lote("ONC1", 5000, "extracto", D(2026, 9, 1), None, 100.0, ""),
         Lote("CER1", 1000, "extracto", D(2026, 9, 1), None, 100.0, ""),
         Lote("SINV", 1000, "extracto", D(2026, 9, 1), None, 100.0, "")])


def mov(fecha, tipo, ticker="", cantidad=0, importe=1, moneda="ARS", tc="", tipo_activo=""):
    return dict(fecha=fecha, tipo=tipo, ticker=ticker, cantidad=cantidad, importe=importe,
                moneda=moneda, tc=tc, tipo_activo=tipo_activo, nota="")


def flujo(movimientos=(), hoy=D(2026, 11, 11), instrumentos=INSTRUMENTOS, cierres=CIERRES, compras=(), **extra):
    movimientos = list(movimientos)
    huellas = {r["referencia"]: r["huella"] for r in referencias_compras(base(), movimientos, tipos=("bono", "on"))}
    archivo = {"esquema_version": 1, "compras": [dict(c, huella=huellas[c["referencia"]]) for c in compras]}
    return calcular_flujo(base(), movimientos, instrumentos, cierres, archivo, None, hoy, DIA_CERO, **extra)


def posicion(resultado, ticker):
    return [p for p in resultado["posiciones"] if p["ticker"] == ticker][0]


class Calendario(unittest.TestCase):
    def test_no_suma_monedas_y_distingue_sin_pagos_de_sin_dato(self):
        enero = [m for m in flujo()["calendario"] if m["mes"] == "2027-01"][0]["proyectado"]
        self.assertEqual(Decimal(enero["USD MEP"]), Decimal("824"))
        self.assertEqual(Decimal(enero["USD cable"]), Decimal("206.25"))
        # No hay pagos en pesos ese mes: la moneda no figura, no vale None ("sin dato").
        self.assertNotIn("ARS", enero)

    def test_la_pantalla_muestra_raya_donde_no_hay_pagos(self):
        _, excel = _panel_flujo(flujo())
        fila = [f for f in excel if f and f[0] == "2027-01"][0]
        self.assertEqual(fila[2], "—")
        self.assertNotIn("sin dato", [celda for celda in fila if isinstance(celda, str)])

    def test_familias_no_habilitadas_no_muestran_importes(self):
        r = flujo()
        self.assertEqual(posicion(r, "CER1")["motivo"], "proyección pendiente: requiere supuestos")
        self.assertEqual(posicion(r, "CER1")["pagos"], [])
        self.assertEqual(posicion(r, "SINV")["motivo"], "sin vincular con IAMC")
        self.assertFalse(any(m["mes"] == "2027-03" for m in r["calendario"]))


class ControlDeCobros(unittest.TestCase):
    MANUAL = dict(INSTRUMENTOS, BON1={"iamc": {"ticker": "BON1", "grupo": "tp", "pagos_manuales": {
        "fuente": "Prospecto ficticio", "pagos": [["2026-01-09", "42", "0.30"], ["2026-07-09", "42", "0.27"]]}}})

    def test_pago_anterior_al_dia_cero_sin_registro_no_es_cobro_no_registrado(self):
        r = flujo(instrumentos=self.MANUAL)
        fechas = [p["fecha"] for p in posicion(r, "BON1")["pagos"]]
        self.assertEqual(fechas, ["2027-01-09", "2027-07-09"])
        self.assertFalse(any(m["mes"].startswith("2026") for m in r["calendario"]))
        self.assertEqual(r["control_desde"], "2026-10-01")

    def test_pago_anterior_al_dia_cero_con_extracto_se_muestra_sin_teorico(self):
        cobro = {"ticker": "BON1", "fecha": D(2026, 7, 10), "moneda": "USD", "cuenta": "DOLARES", "importe": 800.0}
        r = flujo(instrumentos=self.MANUAL, cobros_historial=[cobro])
        pago = [p for p in posicion(r, "BON1")["pagos"] if p["fecha"] == "2026-07-09"][0]
        self.assertIsNone(pago["total"])
        self.assertEqual(pago["cobro"]["origen"], "extracto")
        self.assertIsNone(pago["cobro"]["teorico"])
        self.assertEqual(Decimal(pago["cobro"]["registrado"]), Decimal("800"))
        # Sin importe teórico no entra al calendario.
        self.assertFalse(any(m["mes"] == "2026-07" for m in r["calendario"]))

    def test_el_manual_sigue_alimentando_la_tir_de_la_compra(self):
        compra = {"referencia": "base:1", "precio": "60", "moneda": "USD", "fecha_liquidacion": "2026-03-11"}
        fila = posicion(flujo(instrumentos=self.MANUAL, compras=[compra]), "BON1")["compras"][0]
        self.assertEqual([p["fecha"] for p in fila["pagos"]][0], "2026-07-09")
        self.assertIsNotNone(fila["tir"])

    def test_renta_y_amortizacion_se_comparan_juntas_y_no_bajan_nominales(self):
        movs = [mov(D(2027, 1, 11), "renta", "BON1", importe=24, moneda="USD", tc=1500),
                mov(D(2027, 1, 11), "amortizacion", "BON1", importe=800, moneda="USD", tc=1500)]
        actual, _ = cartera_actual(base(), movs)
        self.assertEqual([p.cantidad for p in actual.posiciones if p.ticker == "BON1"], [10000.0])
        pago = posicion(flujo(movs, hoy=D(2027, 1, 20)), "BON1")["pagos"][0]
        self.assertEqual(pago["cobro"]["estado"], "cobro registrado")
        self.assertEqual(Decimal(pago["cobro"]["diferencia"]), 0)

    def test_cobro_en_pesos_se_convierte_con_su_tc_y_se_marca(self):
        movs = [mov(D(2027, 1, 18), "renta", "ONC1", importe=300000, moneda="ARS", tc=1500)]
        cobro = posicion(flujo(movs, hoy=D(2027, 1, 20)), "ONC1")["pagos"][0]["cobro"]
        self.assertTrue(cobro["convertido"])
        self.assertEqual(Decimal(cobro["registrado"]), Decimal("200"))
        self.assertEqual(Decimal(cobro["diferencia"]), Decimal("-6.25"))

    def test_pago_vencido_sin_movimiento_no_se_da_por_cobrado(self):
        pago = posicion(flujo(hoy=D(2027, 1, 20)), "BON1")["pagos"][0]
        self.assertEqual(pago["estado"], "debería haberse cobrado")
        self.assertEqual(pago["cobro"]["estado"], "cobro no registrado")
        self.assertIsNone(pago["cobro"]["registrado"])

    def test_compra_del_dia_del_pago_no_tiene_derecho_a_ese_pago(self):
        movs = [mov(D(2027, 1, 9), "compra", "BON1", cantidad=5000, importe=100)]
        r = posicion(flujo(movs, hoy=D(2027, 1, 20)), "BON1")
        self.assertEqual(Decimal(r["pagos"][0]["total"]), Decimal("824"))       # 10.000 VN
        self.assertEqual(Decimal(r["pagos"][1]["total"]), Decimal("1231.5"))    # 15.000 VN

    def test_venta_del_dia_del_pago_conserva_ese_pago(self):
        movs = [mov(D(2027, 1, 9), "venta", "BON1", cantidad=4000, importe=100)]
        r = posicion(flujo(movs, hoy=D(2027, 1, 20)), "BON1")
        self.assertEqual(Decimal(r["pagos"][0]["total"]), Decimal("824"))       # 10.000 VN
        self.assertEqual(Decimal(r["pagos"][1]["total"]), Decimal("492.6"))     # 6.000 VN

    def test_venta_anterior_reduce_el_teorico(self):
        movs = [mov(D(2026, 12, 1), "venta", "BON1", cantidad=4000, importe=100)]
        r = posicion(flujo(movs, hoy=D(2027, 1, 20)), "BON1")
        self.assertEqual(Decimal(r["pagos"][0]["total"]), Decimal("494.4"))     # 6.000 VN


class Compras(unittest.TestCase):
    def test_sin_precio_muestra_pagos_futuros_y_dice_que_falta(self):
        fila = posicion(flujo(hoy=D(2027, 1, 20)), "BON1")["compras"][0]
        self.assertEqual(fila["motivo"], "falta precio de compra")
        self.assertEqual([p["fecha"] for p in fila["pagos"]], ["2027-07-09"])
        self.assertIsNone(fila["tir"])
        self.assertIsNone(fila["inversion"])

    def test_compra_anterior_al_primer_cierre_no_calcula_tir_con_pagos_futuros(self):
        compra = {"referencia": "base:1", "precio": "60", "moneda": "USD", "fecha_liquidacion": "2026-03-11"}
        fila = posicion(flujo(compras=[compra]), "BON1")["compras"][0]
        self.assertIsNone(fila["tir"])
        self.assertIsNone(fila["resultado_vto"])
        self.assertIn("faltan pagos entre 2026-03-11 y 2026-11-06", fila["motivo"])

    def test_precio_en_pesos_usa_el_tc_de_la_compra(self):
        compra = {"referencia": "base:2", "precio": "150000", "moneda": "ARS", "tc": "1500",
                  "fecha_liquidacion": "2026-11-06"}
        fila = posicion(flujo(compras=[compra]), "ONC1")["compras"][0]
        self.assertEqual(Decimal(fila["precio_flujo"]), Decimal("100"))
        self.assertEqual(Decimal(fila["inversion"]), Decimal("5000"))
        self.assertEqual(Decimal(fila["total_a_cobrar"]), Decimal("5412.5"))
        self.assertEqual(Decimal(fila["resultado_vto"]), Decimal("412.5"))


if __name__ == "__main__":
    unittest.main()
