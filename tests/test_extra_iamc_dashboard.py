"""El comando dashboard guarda el cierre de IAMC del día. Datos ficticios, sin red."""

import io
import json
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import patch

from cartera import iamc
from cartera.__main__ import main
from cartera.almacenamiento import importar_cartera
from test_extra_dashboard_cli import DEMO, PANELES
from test_extra_iamc_extraer import html


class Base(unittest.TestCase):
    def setUp(self):
        self.temporal = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporal.cleanup)
        self.datos = Path(self.temporal.name) / "datos"
        self.cierres = self.datos / "iamc" / "cierres"
        self.llamadas = []

    def usar_iamc(self):
        """Deja un cierre anterior: la carpeta de datos ya usa IAMC."""
        self.cierres.mkdir(parents=True)
        (self.cierres / "2026-11-04.json").write_text("{}", encoding="utf-8")

    def fetch(self, url):
        self.llamadas.append(url)
        if url == iamc.ROBOTS:
            return b"User-agent: *\nAllow: /\n", {"estado_http": 200, "headers": {"Content-Type": "text/plain"}}
        return html(), {"estado_http": 200, "headers": {"Content-Type": "text/html"}}

    def sin_red(self, url):
        self.llamadas.append(url)
        raise OSError("sin conexión")


class GuardarCierreDelDia(Base):
    def test_sin_cierres_guardados_no_consulta(self):
        self.assertEqual(iamc.guardar_cierre_del_dia(self.datos, self.fetch), (None, None))
        self.assertEqual(self.llamadas, [])
        self.assertFalse((self.datos / "iamc").exists())

    def test_guarda_el_cierre_y_no_vuelve_a_consultar_ese_dia(self):
        self.usar_iamc()
        mensaje, aviso = iamc.guardar_cierre_del_dia(self.datos, self.fetch)
        self.assertEqual((mensaje, aviso), ("Cierre IAMC 2026-11-05 guardado.", None))
        guardado = json.loads((self.cierres / "2026-11-05.json").read_text(encoding="utf-8"))
        self.assertEqual(guardado["fecha_liquidacion"], "2026-11-06")
        self.assertEqual(self.llamadas, [iamc.ROBOTS, iamc.URL])
        # Segunda corrida del día: lee la caché y no anuncia un cierre nuevo.
        self.assertEqual(iamc.guardar_cierre_del_dia(self.datos, self.fetch), (None, None))
        self.assertEqual(len(self.llamadas), 2)

    def test_una_falla_avisa_y_no_se_reintenta_ese_dia(self):
        self.usar_iamc()
        mensaje, aviso = iamc.guardar_cierre_del_dia(self.datos, self.sin_red)
        self.assertIsNone(mensaje)
        self.assertIn("No se pudo guardar el cierre de IAMC de hoy", aviso)
        self.assertIn("Se usa el último cierre guardado.", aviso)
        _, segundo = iamc.guardar_cierre_del_dia(self.datos, self.fetch)
        self.assertIn("Ya hubo un intento", segundo)
        self.assertEqual(self.llamadas, [iamc.ROBOTS])
        self.assertFalse((self.cierres / "2026-11-05.json").exists())

    def test_cualquier_error_queda_en_el_aviso(self):
        self.usar_iamc()

        def roto(url):
            raise RuntimeError("respuesta inesperada")

        mensaje, aviso = iamc.guardar_cierre_del_dia(self.datos, roto)
        self.assertIsNone(mensaje)
        self.assertIn("respuesta inesperada", aviso)


class ComandoDashboard(Base):
    def setUp(self):
        super().setUp()
        importar_cartera(self.datos, "demo", DEMO)
        self.salida = self.datos / "clientes" / "demo" / "dashboard.html"

    def ejecutar(self, obtener):
        salida, errores = io.StringIO(), io.StringIO()
        precios = lambda url: PANELES[url.rsplit("/", 1)[-1]]
        with patch("cartera.__main__.consultar_json", side_effect=precios), \
                patch("cartera.iamc._obtener_url", side_effect=obtener), \
                redirect_stdout(salida), redirect_stderr(errores):
            codigo = main(["--datos", str(self.datos), "dashboard", "--cliente", "demo"])
        return codigo, salida.getvalue(), errores.getvalue()

    def test_sin_iamc_en_la_carpeta_no_consulta(self):
        codigo, salida, _ = self.ejecutar(lambda url, espera=30: self.fetch(url))
        self.assertEqual(codigo, 0)
        self.assertEqual(self.llamadas, [])
        self.assertNotIn("IAMC", salida)

    def test_guarda_el_cierre_antes_de_generar(self):
        self.usar_iamc()
        codigo, salida, _ = self.ejecutar(lambda url, espera=30: self.fetch(url))
        self.assertEqual(codigo, 0)
        self.assertIn("Cierre IAMC 2026-11-05 guardado.", salida)
        self.assertTrue((self.cierres / "2026-11-05.json").exists())

    def test_la_falla_no_impide_el_dashboard_y_se_ve_en_pantalla(self):
        self.usar_iamc()
        (self.cierres / "2026-11-04.json").unlink()
        cierre = iamc.extraer_html(html())
        cierre["fecha_cierre"] = "2026-11-04"
        iamc.guardar_cierre(cierre, self.cierres)
        codigo, salida, _ = self.ejecutar(lambda url, espera=30: self.sin_red(url))
        self.assertEqual(codigo, 0)
        self.assertIn("ADVERTENCIA: No se pudo guardar el cierre de IAMC de hoy", salida)
        self.assertIn("No se pudo guardar el cierre de IAMC de hoy", self.salida.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
