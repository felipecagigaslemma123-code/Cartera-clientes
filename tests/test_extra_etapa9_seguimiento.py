"""Regresiones del seguimiento de la etapa 9 con datos ficticios y sin red."""

from decimal import Decimal
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from cartera import iamc
from cartera.dashboard import _panel_flujo
from cartera.flujo_fondos import calcular_flujo
from test_extra_flujo_revision import D, DIA_CERO, INSTRUMENTOS, base, flujo, mov, posicion
from test_extra_iamc_extraer import html, payload


class ControlDePagos(unittest.TestCase):
    def test_venta_total_el_dia_del_pago_conserva_el_cobro_en_el_calendario(self):
        venta = mov(D(2027, 1, 9), "venta", "BON1", cantidad=10000, importe=100)
        resultado = flujo([venta], hoy=D(2027, 1, 20))
        fila = posicion(resultado, "BON1")
        self.assertEqual(Decimal(fila["cantidad"]), 0)
        self.assertEqual(fila["compras"], [])
        self.assertIsNone(fila["proximo_pago"])
        self.assertEqual([pago["fecha"] for pago in fila["pagos"]], ["2027-01-09"])
        self.assertEqual(Decimal(fila["pagos"][0]["cobro"]["teorico"]), Decimal("824"))
        _, excel = _panel_flujo(resultado)
        enero = next(f for f in excel if f[:2] == ["2027-01", "Debería haberse cobrado"])
        self.assertEqual(enero[3]["valor"], 824)

    def test_pago_anterior_al_dia_cero_no_se_lista_solo_por_movimiento_manual(self):
        instrumentos = dict(INSTRUMENTOS, BON1={"iamc": {
            "ticker": "BON1", "grupo": "tp", "pagos_manuales": {
                "fuente": "Prospecto ficticio", "pagos": [["2026-09-29", "84", "1"]],
            },
        }})
        renta = mov(D(2026, 10, 2), "renta", "BON1", importe=100, moneda="USD", tc=1500)
        resultado = flujo([renta], instrumentos=instrumentos)
        self.assertNotIn("2026-09-29", [pago["fecha"] for pago in posicion(resultado, "BON1")["pagos"]])

    def test_letra_que_vence_hoy_usa_nominales_del_dia_anterior(self):
        compra = mov(D(2026, 10, 5), "compra", "LETF", cantidad=400, importe=400, tipo_activo="letra")
        compra_hoy = mov(D(2026, 11, 11), "compra", "LETF", cantidad=100, importe=100)
        letras = {"posiciones": [{"ticker": "LETF", "familia": "LECAP", "cantidad": "500",
                                  "vencimiento": "2026-11-11", "pago_vencimiento": "600",
                                  "base_nominal": "100", "valor_por_base": "120"}]}
        resultado = calcular_flujo(base(), [compra, compra_hoy], {}, [], letras=letras,
                                   hoy=D(2026, 11, 11), fecha_dia_cero=DIA_CERO)
        noviembre = next(m for m in resultado["calendario"] if m["mes"] == "2026-11")
        self.assertEqual(Decimal(noviembre["deberia_haberse_cobrado"]["ARS"]), Decimal("480"))

    def test_letra_vencida_antes_del_dia_cero_no_entra_al_calendario(self):
        letras = {"posiciones": [{"ticker": "LETF", "familia": "LECAP", "cantidad": "500",
                                  "vencimiento": "2026-09-20", "pago_vencimiento": "600",
                                  "base_nominal": "100", "valor_por_base": "120"}]}
        resultado = calcular_flujo(base(), [], {}, [], letras=letras,
                                   hoy=D(2026, 11, 11), fecha_dia_cero=DIA_CERO)
        self.assertNotIn("2026-09", [mes["mes"] for mes in resultado["calendario"]])


class CierreAutomatico(unittest.TestCase):
    def setUp(self):
        temporal = TemporaryDirectory()
        self.addCleanup(temporal.cleanup)
        self.datos = Path(temporal.name)
        cierre = iamc.extraer_html(html())
        cierre["metadatos"]["adquisicion"] = {"modo": "archivo_local"}
        self.archivo = iamc.guardar_cierre(cierre, self.datos / "iamc" / "cierres")

    @staticmethod
    def fuente(contenido):
        def fetch(url):
            if url == iamc.ROBOTS:
                return b"User-agent: *\nAllow: /\n", {"estado_http": 200}
            return contenido, {"estado_http": 200}
        return fetch

    def test_liquidacion_incoherente_no_se_archiva_y_conserva_el_cierre_previo(self):
        datos = payload()
        datos["tp"]["fecha"] = datos["on"]["fecha"] = "2026-11-07"
        mensaje, aviso = iamc.guardar_cierre_del_dia(self.datos, self.fuente(html(datos)))
        self.assertIsNone(mensaje)
        self.assertIn("liquidación", aviso)
        self.assertFalse(self.archivo.with_name("2026-11-07.json").exists())
        self.assertEqual([c["fecha_cierre"] for c in iamc.leer_cierres(self.datos)], ["2026-11-05"])

    def test_el_dashboard_conserva_un_cierre_de_la_misma_fecha_ya_archivado(self):
        anterior = self.archivo.read_bytes()
        self.assertEqual(iamc.guardar_cierre_del_dia(self.datos, self.fuente(html())), (None, None))
        self.assertEqual(self.archivo.read_bytes(), anterior)
