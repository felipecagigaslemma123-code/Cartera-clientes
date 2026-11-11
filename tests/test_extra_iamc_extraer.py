"""Relevamiento IAMC: fixtures sintéticos, sin acceso real a red ni cartera."""

import copy
from datetime import date
import importlib.util
import io
import json
from pathlib import Path
import tempfile
import unittest
from contextlib import redirect_stdout, redirect_stderr
from unittest.mock import patch
from concurrent.futures import ThreadPoolExecutor


RUTA = Path(__file__).resolve().parents[1] / "tools" / "iamc_extraer.py"
SPEC = importlib.util.spec_from_file_location("iamc_extraer_prueba", RUTA)
iamc = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(iamc)


def payload():
    return {
        "tp": {"fecha": "2026-11-05", "fecha_liq": "2026-11-06", "rows": [
            {"tk": "S30N6", "seg": "lec", "px": 120.25, "tna": None},
            {"tk": "T30A7", "seg": "lec", "px": 0, "nota": "Ficticio"},
            {"tk": "DUAL_DEMO", "seg": "dua", "lec": 1},
            {"tk": "AL30", "seg": "sob", "vt": 100.5, "vr": 100, "ai": 0.5}]},
        "on": {"fecha": "2026-11-05", "fecha_liq": "2026-11-06", "rows": []},
        "calc": {"liq": "2026-11-06", "fx": {"mep": 1500}, "ins": [
            {"tk": "AL30", "f": [[10, 100, 0.5, 0]], "px": 99.25},
            {"tk": "TZXS7", "f": [[20, 110, 0, 0]]},
            {"tk": "S30N6", "g": "tp", "k": "cap", "pxa": 120.2500001,
             "f": [[25, 121.123456789, 0, 0]]}]},
        "macro": {"vars": [{"k": "cer", "v": 100, "f": "2026-11-04"}]},
        "ins": {"fecha": "2026-11-05", "rows": []},
        "cat": [{"tk": "AL30", "i": "ISIN_FICTICIO", "c": "CAJA_DEMO"}],
        "__dif": {"ins": "d/ins.json"}, "din": {"cau": {"c": [0]}},
        "ccau": {"fecha": "2026-11-05"},
    }


def html(datos=None):
    datos = payload() if datos is None else datos
    return ('<!doctype html><html><script id="payload" type="application/json">' +
            json.dumps(datos, ensure_ascii=False, allow_nan=False) + '</script></html>').encode("utf-8")


class ParseoIAMC(unittest.TestCase):
    def test_extrae_cierre_y_conserva_datos_crudos_sin_calcular(self):
        original = payload()
        copia = copy.deepcopy(original)
        datos = iamc.extraer_html(html(original))
        self.assertEqual(datos["fecha_cierre"], "2026-11-05")
        self.assertEqual(datos["fecha_liquidacion"], "2026-11-06")
        self.assertEqual(datos["calculadora_bonos"], original["calc"])
        self.assertEqual(datos["macro"], original["macro"])
        self.assertEqual(datos["calculadora_letras"]["instrumentos"], original["tp"]["rows"][:2])
        self.assertEqual(datos["informes"]["titulos_publicos"], original["tp"])
        self.assertEqual(datos["calculadora_letras"]["registros_calculadora"], [original["calc"]["ins"][2]])
        self.assertEqual(datos["calculadora_letras"]["registros_calculadora"][0]["f"][0][1], 121.123456789)
        self.assertEqual(datos["caucion"]["mercado_dinero"], original["din"])
        self.assertEqual(original, copia)
        self.assertIsNone(datos["calculadora_letras"]["instrumentos"][0]["tna"])
        self.assertEqual(datos["calculadora_letras"]["instrumentos"][1]["px"], 0)
        self.assertEqual(len(datos["metadatos"]["html_sha256"]), 64)

    def test_datos_independientes_y_padron_diferido_no_parece_completo(self):
        p = payload()
        datos = iamc.extraer_html(html(p))
        datos["calculadora_bonos"]["ins"][0]["px"] = 123
        self.assertEqual(p["calc"]["ins"][0]["px"], 99.25)
        self.assertEqual(datos["padron"]["estado"], "pendiente_carga_diferida")
        self.assertEqual(datos["padron"]["pendiente_url"], iamc.URL + "d/ins.json")
        self.assertTrue(any("ni se presenta como completo" in aviso for aviso in datos["metadatos"]["avisos"]))

    def test_rechaza_ausencia_duplicado_tipo_y_script_incompleto(self):
        for contenido in (b'<html>Sin datos</html>', html() + html(),
                          html().replace(b'application/json', b'text/javascript'),
                          html().replace(b'</script>', b'')):
            with self.subTest(contenido=contenido[:70]):
                with self.assertRaises(iamc.ErrorExtraccion):
                    iamc.extraer_html(contenido)

    def test_rechaza_json_duplicado_no_finito_y_numeros_inmensos(self):
        for texto in ('{"tp":{},"tp":{}}', '{"x":NaN}', '{"x":Infinity}', '{"x":1e999}'):
            contenido = '<script id="payload" type="application/json">' + texto + '</script>'
            with self.subTest(texto=texto):
                with self.assertRaises(iamc.ErrorExtraccion):
                    iamc.extraer_html(contenido)

    def test_rechaza_utf8_invalido_y_tamano_excesivo(self):
        with self.assertRaises(iamc.ErrorExtraccion):
            iamc.extraer_html(b'\xff')
        with patch.object(iamc, "MAX_BYTES", 5):
            with self.assertRaises(iamc.ErrorExtraccion):
                iamc.extraer_html(html())

    def test_rechaza_fechas_mixtas_y_estructura_rotas(self):
        variantes = []
        for campo, valor in (("tp", None), ("calc", []), ("macro", None)):
            p = payload(); p[campo] = valor; variantes.append(p)
        for campo, valor in (("fecha", "2026-02-30"), ("fecha_liq", "2026-11-05")):
            p = payload(); p["tp"][campo] = valor; variantes.append(p)
        p = payload(); p["on"]["fecha"] = "2026-11-04"; variantes.append(p)
        p = payload(); p["calc"]["ins"] = [{"tk": "DUP"}, {"tk": "DUP"}]; variantes.append(p)
        p = payload(); p["macro"]["vars"] = {}; variantes.append(p)
        p = payload(); p["calc"]["ins"] = [None]; variantes.append(p)
        p = payload(); p["__dif"]["ins"] = "https://ajeno.example/ins"; variantes.append(p)
        for p in variantes:
            with self.subTest(payload=p):
                with self.assertRaises(iamc.ErrorExtraccion):
                    iamc.extraer_html(html(p))

    def test_secciones_vacias_se_conservan_con_aviso(self):
        p = payload(); p["calc"]["ins"] = []; p["tp"]["rows"] = []
        datos = iamc.extraer_html(html(p))
        self.assertEqual(datos["calculadora_bonos"]["ins"], [])
        self.assertEqual(datos["calculadora_letras"]["instrumentos"], [])
        self.assertTrue(any("no trae instrumentos" in aviso for aviso in datos["metadatos"]["avisos"]))
        self.assertTrue(any("No hay instrumentos" in aviso for aviso in datos["metadatos"]["avisos"]))


class ArchivosIAMC(unittest.TestCase):
    def setUp(self):
        self.temporal = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporal.cleanup)
        self.raiz = Path(self.temporal.name)
        self.datos = iamc.extraer_html(html())

    def test_archivo_se_fecha_por_cierre_no_consulta(self):
        ruta = iamc.guardar_cierre(self.datos, self.raiz)
        self.assertEqual(ruta.name, "2026-11-05.json")
        self.assertEqual(json.loads(ruta.read_text()), self.datos)
        self.assertEqual(ruta.stat().st_mode & 0o777, 0o600)
        instante = ruta.stat().st_mtime_ns
        iamc.guardar_cierre(self.datos, self.raiz)
        self.assertEqual(ruta.stat().st_mtime_ns, instante)

    def test_fallo_reemplazo_no_pierde_archivo_ni_deja_temporal(self):
        ruta = iamc.guardar_cierre(self.datos, self.raiz)
        previo = ruta.read_bytes()
        datos = copy.deepcopy(self.datos); datos["metadatos"]["observacion"] = "Ficticia"
        with patch.object(iamc.os, "replace", side_effect=OSError("fallo ficticio")):
            with self.assertRaises(OSError):
                iamc.guardar_cierre(datos, self.raiz)
        self.assertEqual(ruta.read_bytes(), previo)
        self.assertEqual(list(self.raiz.iterdir()), [ruta])

    def test_rechaza_publicacion_sobre_enlace(self):
        destino = self.raiz / "ajeno"
        destino.write_text("ficticio")
        (self.raiz / "2026-11-05.json").symlink_to(destino)
        with self.assertRaises(iamc.ErrorExtraccion):
            iamc.guardar_cierre(self.datos, self.raiz)
        self.assertEqual(destino.read_text(), "ficticio")

    def test_muestras_ausentes_no_se_sustituyen_y_crudas_coinciden(self):
        estado = iamc.guardar_muestras(self.datos, self.raiz)
        muestra = json.loads((self.raiz / "bonos/AL30.json").read_text())
        self.assertEqual(muestra["calculadora"], self.datos["calculadora_bonos"]["ins"][0])
        self.assertEqual(muestra["informe"], self.datos["informes"]["titulos_publicos"]["rows"][3])
        self.assertEqual(muestra["catalogo"], self.datos["catalogo"][0])
        self.assertEqual(muestra["origenes"]["informe"], "payload.tp.rows[3]")
        self.assertEqual(muestra["informe"]["ai"], 0.5)
        letra = json.loads((self.raiz / "letras/S30N6.json").read_text())
        self.assertEqual(letra["informe"], self.datos["informes"]["titulos_publicos"]["rows"][0])
        self.assertEqual(letra["calculadora"], self.datos["calculadora_bonos"]["ins"][2])
        self.assertEqual(letra["origenes"]["calculadora"], "payload.calc.ins[2]")
        self.assertEqual(letra["calculadora"]["f"][0][1], 121.123456789)
        self.assertIsNone(letra["catalogo"])
        ausente = json.loads((self.raiz / "bonos/TX26.ausente.json").read_text())
        self.assertFalse(ausente["disponible"])
        self.assertNotIn("precio", ausente)
        self.assertFalse((self.raiz / "bonos/TX26.json").exists())
        self.assertEqual(len(estado["muestras"]), 7)
        self.assertEqual(json.loads((self.raiz / "macro_payload_crudo.json").read_text()), self.datos["macro"])

    def test_cli_html_no_toca_red(self):
        fuente = self.raiz / "fuente.html"
        fuente.write_bytes(html())
        salida, errores = io.StringIO(), io.StringIO()
        with patch.object(iamc, "descargar_cierre") as red, redirect_stdout(salida), redirect_stderr(errores):
            codigo = iamc.main(["--html", str(fuente), "--salida", str(self.raiz / "json"), "--muestras", str(self.raiz / "muestras")])
        self.assertEqual(codigo, 0, errores.getvalue())
        red.assert_not_called()
        self.assertTrue((self.raiz / "json/2026-11-05.json").exists())

    def test_cli_conserva_metadatos_http_locales_y_verifica_huella(self):
        fuente = self.raiz / "fuente.html"
        fuente.write_bytes(html())
        import hashlib
        ficha = {"url_solicitada": iamc.URL, "sha256": hashlib.sha256(html()).hexdigest(), "estado_http": 200,
                 "consultado_en": "2026-11-05T18:00:00-03:00"}
        ruta_meta = fuente.with_name(fuente.name + ".http.json")
        ruta_meta.write_text(json.dumps(ficha))
        with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
            codigo = iamc.main(["--html", str(fuente), "--salida", str(self.raiz / "json")])
        self.assertEqual(codigo, 0)
        datos = json.loads((self.raiz / "json/2026-11-05.json").read_text())
        self.assertEqual(datos["metadatos"]["adquisicion"]["http_guardado"], ficha)
        ruta_meta.write_text(json.dumps(dict(ficha, sha256="a" * 64)))
        with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
            codigo = iamc.main(["--html", str(fuente), "--salida", str(self.raiz / "otro")])
        self.assertEqual(codigo, 1)
        self.assertFalse((self.raiz / "otro").exists())

    def test_cli_invalido_no_publica(self):
        fuente = self.raiz / "fuente.html"; fuente.write_text("<html>vacío</html>")
        with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
            codigo = iamc.main(["--html", str(fuente), "--salida", str(self.raiz / "json")])
        self.assertEqual(codigo, 1)
        self.assertFalse((self.raiz / "json").exists())


class DescargaIAMC(unittest.TestCase):
    def setUp(self):
        self.temporal = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporal.cleanup)
        self.raiz = Path(self.temporal.name)
        self.hoy = date(2026, 11, 5)
        self.llamadas = []

    def fetch(self, url):
        self.llamadas.append(url)
        if url == iamc.ROBOTS:
            return b"User-agent: *\nAllow: /\n", {"estado_http": 200, "headers": {"Content-Type": "text/plain"}}
        return html(), {"estado_http": 200, "headers": {"Content-Type": "text/html"}}

    def test_descarga_una_vez_por_url_y_dia_y_reutiliza_cache(self):
        a = iamc.descargar_cierre(self.raiz, self.hoy, self.fetch)
        b = iamc.descargar_cierre(self.raiz, self.hoy, self.fetch)
        self.assertEqual(a, b)
        self.assertEqual(self.llamadas, [iamc.ROBOTS, iamc.URL])
        iamc.descargar_cierre(self.raiz, date(2026, 11, 6), self.fetch)
        self.assertEqual(self.llamadas, [iamc.ROBOTS, iamc.URL] * 2)

    def test_fallo_no_se_reintenta_ese_dia(self):
        def falla(url):
            if url == iamc.URL:
                self.llamadas.append(url)
                raise OSError("caída ficticia")
            return self.fetch(url)
        with self.assertRaisesRegex(OSError, "ficticia"):
            iamc.descargar_cierre(self.raiz, self.hoy, falla)
        registro = json.loads((self.raiz / self.hoy.isoformat() / "intentos.json").read_text())
        self.assertEqual(registro[iamc.URL]["estado"], "error")
        with self.assertRaisesRegex(iamc.ErrorExtraccion, "Ya hubo un intento"):
            iamc.descargar_cierre(self.raiz, self.hoy, falla)
        self.assertEqual(self.llamadas, [iamc.ROBOTS, iamc.URL])

    def test_reserva_antes_de_solicitud_y_respeta_bloqueo(self):
        def observar(url):
            registro = json.loads((self.raiz / self.hoy.isoformat() / "intentos.json").read_text())
            self.assertEqual(registro[url]["estado"], "iniciado")
            return self.fetch(url)
        with ThreadPoolExecutor(max_workers=2) as equipo:
            futuros = [equipo.submit(iamc.descargar_cierre, self.raiz, self.hoy, observar) for _ in range(2)]
            for futuro in futuros:
                self.assertIn(b'payload', futuro.result()[0])
        self.assertEqual(self.llamadas, [iamc.ROBOTS, iamc.URL])

    def test_robots_disallow_bloquea_cierre_sin_otra_solicitud(self):
        def bloqueado(url):
            self.llamadas.append(url)
            return b"User-agent: *\nDisallow: /informediario/\n", {"estado_http": 200, "headers": {}}
        for _ in range(2):
            with self.assertRaisesRegex(iamc.ErrorExtraccion, "prohíbe"):
                iamc.descargar_cierre(self.raiz, self.hoy, bloqueado)
        self.assertEqual(self.llamadas, [iamc.ROBOTS])

    def test_robots_html_no_se_confunde_con_permiso(self):
        def html_robot(url):
            if url == iamc.ROBOTS:
                self.llamadas.append(url)
                return html(), {"estado_http": 200, "headers": {"Content-Type": "text/html"}}
            return self.fetch(url)
        cuerpo, meta = iamc.descargar_cierre(self.raiz, self.hoy, html_robot)
        self.assertEqual(cuerpo, html())
        self.assertIn("no reglas robots válidas", meta["robots_avisos"][0])
        self.assertIn("No se interpreta como autorización", meta["robots_avisos"][0])

    def test_cache_corrupta_no_se_descarga_de_nuevo(self):
        iamc.descargar_cierre(self.raiz, self.hoy, self.fetch)
        carpeta = self.raiz / self.hoy.isoformat()
        (carpeta / "informediario.html").write_text("alterado")
        with self.assertRaisesRegex(iamc.ErrorExtraccion, "huella"):
            iamc.descargar_cierre(self.raiz, self.hoy, self.fetch)
        self.assertEqual(self.llamadas, [iamc.ROBOTS, iamc.URL])

    def test_cache_incompleta_no_repite_descarga(self):
        carpeta = self.raiz / self.hoy.isoformat(); carpeta.mkdir()
        (carpeta / "robots.txt").write_text("parcial")
        with self.assertRaisesRegex(iamc.ErrorExtraccion, "incompleta"):
            iamc.descargar_cierre(self.raiz, self.hoy, self.fetch)
        self.assertEqual(self.llamadas, [])

    def test_http_erroneo_y_html_sin_payload_no_se_reintentan(self):
        for status, cuerpo in ((503, "Caída".encode("utf-8")), (200, b"<html>Error</html>")):
            with tempfile.TemporaryDirectory() as temporal:
                llamadas = []
                def malo(url):
                    llamadas.append(url)
                    if url == iamc.ROBOTS:
                        return b"no", {"estado_http": 404, "headers": {}}
                    return cuerpo, {"estado_http": status, "headers": {}}
                for _ in range(2):
                    with self.assertRaises(iamc.ErrorExtraccion):
                        iamc.descargar_cierre(temporal, self.hoy, malo)
                self.assertEqual(llamadas, [iamc.ROBOTS, iamc.URL])


if __name__ == "__main__":
    unittest.main()
