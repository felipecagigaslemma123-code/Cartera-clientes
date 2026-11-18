"""Copia del informe en la carpeta del cliente (`perfil.carpeta_informes`), pedido del 18/11/2026."""

import io
import json
import shutil
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest import mock

from cartera.__main__ import main

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "informe"


def chrome_falso(ruta_html, ruta_pdf, navegador=None):
    Path(ruta_pdf).write_bytes(b"%PDF-1.4 prueba")
    return Path(ruta_pdf)


class Entrega(unittest.TestCase):
    def setUp(self):
        temporal = tempfile.TemporaryDirectory()
        self.addCleanup(temporal.cleanup)
        self.raiz = Path(temporal.name)
        self.datos = self.raiz / "privado"
        self.carpeta = self.datos / "clientes" / "demo"
        self.carpeta.mkdir(parents=True)
        for nombre in ("dashboard.html", "instrumentos.json"):
            shutil.copyfile(FIXTURES / nombre, self.carpeta / nombre)

    def perfil(self, **extra):
        contenido = json.loads((FIXTURES / "perfil.json").read_text(encoding="utf-8"))
        contenido.update(extra)
        (self.carpeta / "perfil.json").write_text(json.dumps(contenido), encoding="utf-8")

    def correr(self, *argumentos, pdf=chrome_falso):
        salida, errores = io.StringIO(), io.StringIO()
        with mock.patch("cartera.informe.exportar_pdf", pdf), redirect_stdout(salida), redirect_stderr(errores):
            codigo = main(["--datos", str(self.datos), "informe", "--cliente", "demo"] + list(argumentos))
        return codigo, salida.getvalue(), errores.getvalue()

    def test_copia_el_pdf_en_la_carpeta_relativa_a_los_datos(self):
        self.perfil(carpeta_informes="../Clientes/Cliente Demo/Informes")
        codigo, salida, _ = self.correr()  # sin --pdf: la carpeta de entrega ya lo pide
        self.assertEqual(codigo, 0)
        copia = self.raiz / "Clientes" / "Cliente Demo" / "Informes" / "Informe de cartera 2026-11-16.pdf"
        self.assertEqual(copia.read_bytes(), b"%PDF-1.4 prueba")
        self.assertIn(str(copia.resolve()), salida)
        self.assertTrue((self.carpeta / "informes" / "informe-2026-11-16.pdf").exists())

    def test_ruta_absoluta_y_reemplazo(self):
        destino = self.raiz / "otro lugar"
        self.perfil(carpeta_informes=str(destino))
        self.assertEqual(self.correr()[0], 0)
        self.assertEqual(self.correr()[0], 0)
        self.assertEqual(sorted(p.name for p in destino.iterdir()), ["Informe de cartera 2026-11-16.pdf"])

    def test_sin_carpeta_no_copia_ni_genera_pdf(self):
        self.perfil()
        llamado = mock.Mock(side_effect=chrome_falso)
        self.assertEqual(self.correr(pdf=llamado)[0], 0)
        llamado.assert_not_called()
        self.assertFalse((self.raiz / "Clientes").exists())

    def test_sin_chrome_deja_el_html_en_la_carpeta(self):
        from cartera.informe import ErrorInforme

        def falla(*_args, **_kwargs):
            raise ErrorInforme("No se encontró Google Chrome.")

        self.perfil(carpeta_informes="../Clientes/Cliente Demo")
        codigo, _, errores = self.correr(pdf=falla)
        self.assertNotEqual(codigo, 0)
        self.assertIn("Chrome", errores)
        self.assertTrue((self.raiz / "Clientes" / "Cliente Demo" / "Informe de cartera 2026-11-16.html").exists())

    def test_ruta_invalida(self):
        self.perfil(carpeta_informes="")
        codigo, _, errores = self.correr()
        self.assertNotEqual(codigo, 0)
        self.assertIn("carpeta_informes", errores)
        self.assertFalse((self.carpeta / "informes").exists())


if __name__ == "__main__":
    unittest.main()
