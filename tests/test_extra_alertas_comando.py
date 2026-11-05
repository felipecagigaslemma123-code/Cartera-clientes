"""Integridad, concurrencia y entrega simulada de corridas de alertas."""

import contextlib
import datetime as dt
import fcntl
import io
import json
import os
from pathlib import Path
import stat
import tempfile
import unittest
from unittest.mock import patch
from zoneinfo import ZoneInfo

from cartera.__main__ import main
from cartera.alertas_comando import correr_alertas
from cartera.almacenamiento import importar_cartera


DEMO = Path(__file__).resolve().parents[1] / "fixtures" / "punto_partida_demo.xlsx"
AR = ZoneInfo("America/Argentina/Buenos_Aires")
T = dt.datetime(2026, 11, 4, 12, tzinfo=AR)
SECRETO_FICTICIO = "SECRETO-FICTICIO-NO-IMPRIMIR"


class IntegridadCorridas(unittest.TestCase):
    def setUp(self):
        self.temporal = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporal.cleanup)
        self.datos = Path(self.temporal.name) / "datos"
        self.punto, _ = importar_cartera(self.datos, "demo", DEMO)
        self.carpeta = self.datos / "clientes" / "demo"
        self.estado = self.carpeta / "estado_alertas.json"
        self.precio = 1600
        self.llamadas, self.recibidos = [], []
        (self.carpeta / "niveles.json").write_text(json.dumps({"AAA": {"take_profit": 1500, "stop_loss": 900}}))

    def fetch(self, url):
        self.llamadas.append(url)
        return [{"symbol": "AAA", "c": self.precio, "px_bid": self.precio, "px_ask": self.precio}]

    def canal(self, titulo, mensaje):
        self.recibidos.append((titulo, mensaje))

    def correr(self, canales=None, ahora=T):
        return correr_alertas(self.carpeta, self.punto, "demo", self.fetch,
                              [self.canal] if canales is None else canales, ahora)

    def archivos(self):
        return {p.name: (p.read_bytes(), p.stat().st_mtime_ns, stat.S_IMODE(p.stat().st_mode))
                for p in self.carpeta.iterdir() if p.is_file()}

    def test_corrida_simultanea_no_lee_canales_no_consulta_ni_escribe(self):
        bloqueo = self.carpeta / ".alertas.lock"
        bloqueo.touch(mode=0o600)
        descriptor = os.open(str(bloqueo), os.O_RDWR)
        def canales():
            raise AssertionError("No debe descubrir canales al omitir la corrida")
            yield self.canal
        antes = self.archivos()
        try:
            fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
            resultado = self.correr(canales=canales())
        finally:
            os.close(descriptor)
        self.assertTrue(resultado["omitida"])
        self.assertTrue(resultado["entregado"])
        self.assertEqual(resultado["eventos"], [])
        self.assertEqual(self.llamadas, [])
        self.assertEqual(self.archivos(), antes)

    def test_sin_canales_reintenta_y_no_guarda_estado_nuevo(self):
        resultado = self.correr(canales=[])
        self.assertFalse(resultado["entregado"])
        self.assertTrue(resultado["errores"])
        self.assertFalse(self.estado.exists())
        resultado = self.correr(ahora=T + dt.timedelta(minutes=5))
        self.assertIn("take_profit", [e.tipo for e in resultado["eventos"]])
        self.assertTrue(self.estado.exists())
        self.assertEqual(len(self.recibidos), 1)

    def test_niveles_invalidos_no_impiden_vencimiento_y_error_no_expone_valores(self):
        (self.carpeta / "niveles.json").write_text('{"' + SECRETO_FICTICIO + '": {"take_profit": 10}}')
        (self.carpeta / "instrumentos.json").write_text('{"BOND1": {"vencimiento": "2026-11-10"}}')
        resultado = self.correr()
        self.assertFalse(resultado["evaluo_niveles"])
        self.assertEqual(self.llamadas, [])
        self.assertIn("vencimiento", [e.tipo for e in resultado["eventos"]])
        self.assertNotIn(SECRETO_FICTICIO, repr(self.recibidos))
        self.assertNotIn(SECRETO_FICTICIO, (self.carpeta / "alertas.log").read_text())

    def test_estado_semantico_invalido_se_respalda_sin_perder_sus_bytes(self):
        bruto = json.dumps({"esquema_version": 1, "niveles": {"AAA": False}, "vencimientos": {}}).encode()
        self.estado.write_bytes(bruto)
        resultado = self.correr()
        self.assertTrue(resultado["entregado"])
        respaldo = self.carpeta / "estado_alertas.corrupto.json"
        self.assertEqual(respaldo.read_bytes(), bruto)
        self.assertEqual(stat.S_IMODE(respaldo.stat().st_mode), 0o600)
        self.assertIn("estado_corrupto", (self.carpeta / "alertas.log").read_text())

    def test_dos_estados_corruptos_distintos_no_pisan_su_historia(self):
        primero = b"{primer estado roto"
        segundo = b"{segundo estado roto"
        self.estado.write_bytes(primero)
        self.correr()
        self.estado.write_bytes(segundo)
        self.correr(ahora=T + dt.timedelta(minutes=5))
        respaldos = list(self.carpeta.glob("estado_alertas.corrupto*.json"))
        self.assertEqual(len(respaldos), 2)
        self.assertEqual({p.read_bytes() for p in respaldos}, {primero, segundo})

    def test_falla_cache_no_impide_alertas_y_no_filtra_excepcion(self):
        with patch("cartera.alertas_comando.ClientePrecios.guardar_cache", side_effect=OSError(SECRETO_FICTICIO)):
            resultado = self.correr()
        self.assertTrue(resultado["entregado"])
        self.assertIn("take_profit", [e.tipo for e in resultado["eventos"]])
        self.assertTrue(resultado["avisos"])
        self.assertNotIn(SECRETO_FICTICIO, repr(resultado))
        self.assertNotIn(SECRETO_FICTICIO, (self.carpeta / "alertas.log").read_text())

    def test_estado_no_se_confirma_si_falla_su_publicacion(self):
        self.correr()
        anterior = self.estado.read_bytes()
        self.precio = 1400  # Rearma take profit; es necesario guardar el nuevo estado.
        reemplazar = os.replace
        def fallar_estado(origen, destino):
            if Path(destino) == self.estado:
                raise OSError("No se pudo publicar el estado")
            return reemplazar(origen, destino)
        with patch("cartera.alertas_comando.os.replace", side_effect=fallar_estado):
            with self.assertRaises(OSError):
                self.correr(ahora=T + dt.timedelta(minutes=5))
        self.assertEqual(self.estado.read_bytes(), anterior)
        self.assertEqual(list(self.carpeta.glob("*.tmp")), [])

    def test_reintenta_si_el_log_falla_despues_de_entregar(self):
        with patch("cartera.alertas_comando._agregar_log", side_effect=OSError("No se pudo registrar")):
            with self.assertRaises(OSError):
                self.correr()
        self.assertEqual(len(self.recibidos), 1)
        self.assertFalse(self.estado.exists())
        self.correr(ahora=T + dt.timedelta(minutes=5))
        self.assertEqual(len(self.recibidos), 2)
        self.assertTrue(self.estado.exists())

    def test_log_es_privado_append_y_no_guarda_nombres_ni_costos(self):
        (self.carpeta / "perfil.json").write_text('{"nombre": "Persona Ficticia Privada"}')
        self.correr()
        log = self.carpeta / "alertas.log"
        anterior = log.read_bytes()
        self.correr(ahora=T + dt.timedelta(days=1))
        self.assertTrue(log.read_bytes().startswith(anterior))
        self.assertEqual(stat.S_IMODE(log.stat().st_mode), 0o600)
        self.assertEqual(stat.S_IMODE(self.estado.stat().st_mode), 0o600)
        self.assertNotIn("Persona Ficticia Privada", log.read_text())
        self.assertNotIn("104600", log.read_text())
        self.assertNotIn("Persona Ficticia Privada", repr(self.recibidos))

    def test_cli_no_descubre_canales_fuera_de_horario_sin_eventos(self):
        salida, errores = io.StringIO(), io.StringIO()
        with patch("cartera.notificar.canales_disponibles") as canales, patch(
            "cartera.alertas_comando.ahora_argentina", return_value=T.replace(hour=20)
        ), patch("cartera.__main__.consultar_json") as red:
            with contextlib.redirect_stdout(salida), contextlib.redirect_stderr(errores):
                codigo = main(["--datos", str(self.datos), "alertas", "--cliente", "demo"])
        self.assertEqual(codigo, 0, errores.getvalue())
        canales.assert_not_called()
        red.assert_not_called()


if __name__ == "__main__":
    unittest.main()
