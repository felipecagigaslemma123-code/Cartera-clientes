"""Extractor estático de metodología, con HTML sintético y sin red."""

import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


RAIZ = Path(__file__).resolve().parents[1]
HERRAMIENTA = RAIZ / 'tools' / 'iamc_metodologias.py'
ESPEC = importlib.util.spec_from_file_location('iamc_metodologias_prueba', HERRAMIENTA)
IAMC = importlib.util.module_from_spec(ESPEC)
sys.modules[ESPEC.name] = IAMC
ESPEC.loader.exec_module(IAMC)
URL = 'https://fuente.invalid/ejemplo-publico'

HTML = r"""<!doctype html>
<script>
const MET = {
  rf: {nombre:'Renta Fija', grupos:[
    {g:'Rendimientos', cards:[
      {t:'TIR de prueba', f:'P = Σ CF<sub>t</sub> / (1+r)<sup>d/365</sup>',
       d:'PARRAFO_LARGO_NO_COPIAR', v:'variables', n:'nota'},
      {t:'Sin ecuación', f:'', d:'PARRAFO_LARGO_NO_COPIAR'}
    ]}
  ]},
  calc: {nombre:'Calculadoras', grupos:[
    {g:'Calculadora de Caución', cards:[
      {t:'Interés', f:'I = C × TNA × n / ' + '365'},
      {t:'Escape', f:'T = \\' + '\u03c4' + ' &gt; 0'}
    ]}
  ]}
};
const CC_BASE = 365, CC_BASE_DER = 90, CC_TOPE_DER = 90;
const SC = {lado:'col', pl:'1', der:'0,045', iva:'21', baseCom:'ini', baseDer:'vto',
            ivaCom:'si', ivaDer:'no', mom:'vto', car:[]};
function calcularC(p){
  const n=p.n, I=p.monto*p.tna*n/CC_BASE, Mv=p.monto+I;
  const bc=p.baseComVto?Mv:p.monto, comB=bc*p.com*n/CC_BASE, com=Math.max(comB,p.commin);
  r.ok = r.f0>0 && r.f1>0 && G<p.monto;
  r.teaN=Math.pow(r.f1/r.f0,CC_BASE/n)-1; r.temN=Math.pow(r.f1/r.f0,30/n)-1;
}
</script>
"""


class MetodologiasEstaticas(unittest.TestCase):
    def extraer(self, html=HTML):
        return IAMC.extraer_metodologias(html.encode(), URL)

    def test_extrae_rf_y_calculadoras_sin_copiar_parrafos(self):
        datos = self.extraer()
        self.assertEqual(len(datos['formulas']), 4)
        self.assertEqual([f['seccion'] for f in datos['formulas']], ['rf', 'rf', 'calc', 'calc'])
        self.assertNotIn('PARRAFO_LARGO_NO_COPIAR', json.dumps(datos))
        self.assertIn('no valida ni aprueba', datos['naturaleza'])
        self.assertFalse(datos['formulas'][1]['tiene_formula'])

    def test_hash_fragmento_y_lineas_conservan_procedencia(self):
        datos = self.extraer()
        self.assertEqual(datos['fuente']['sha256'], hashlib.sha256(HTML.encode()).hexdigest())
        self.assertEqual(datos['fuente']['url'], URL)
        f = datos['formulas'][0]
        self.assertEqual(f['fragmento_js'], "'P = Σ CF<sub>t</sub> / (1+r)<sup>d/365</sup>'")
        linea = HTML[:HTML.index(f['fragmento_js'])].count('\n') + 1
        self.assertEqual(f['ubicacion'], {'linea_inicio': linea, 'linea_fin': linea})

    def test_subindices_exponentes_y_entidades_no_se_aplanan(self):
        datos = self.extraer()
        self.assertEqual(datos['formulas'][0]['formula_texto'], 'P = Σ CF_{t} / (1+r)^{d/365}')
        self.assertEqual(datos['formulas'][3]['formula_texto'], 'T = \\τ > 0')

    def test_concatenacion_literal_y_escapes_conservados(self):
        f = self.extraer()['formulas'][2]
        self.assertEqual(f['formula_html'], 'I = C × TNA × n / 365')
        self.assertIn("+ '365'", f['fragmento_js'])
        self.assertEqual(self.extraer()['formulas'][3]['formula_html'], 'T = \\τ &gt; 0')

    def test_no_ejecuta_expresiones_de_javascript(self):
        for malicioso in ('alert(1)', 'globalThis.secreto', '(()=>42)()', 'new Function("return 1")()', '`plantilla`'):
            html = HTML.replace("f:'I = C × TNA × n / ' + '365'", 'f:' + malicioso)
            with self.subTest(valor=malicioso), self.assertRaises(IAMC.ErrorExtraccion):
                self.extraer(html)

    def test_rechaza_estructura_incompleta_o_duplicada(self):
        casos = [HTML.replace('const MET', 'const OTRO'), HTML + HTML,
                 HTML.replace("t:'Interés', f:", "t:'Interés', otro:"),
                 HTML.replace("lado:'col',", "lado:'col', lado:'tom',")]
        for html in casos[:3]:
            with self.subTest(html=html[:40]), self.assertRaises(IAMC.ErrorExtraccion):
                self.extraer(html)
        with self.assertRaises(IAMC.ErrorExtraccion):
            IAMC.extraer_caucion(casos[3].encode(), URL)

    def test_defaults_y_expresiones_de_caucion_son_estaticos(self):
        datos = IAMC.extraer_caucion(HTML.encode(), URL)
        self.assertTrue(datos['disponible'])
        self.assertEqual(datos['constantes']['CC_BASE']['valor'], 365)
        self.assertEqual(datos['constantes']['CC_BASE_DER']['valor'], 90)
        self.assertEqual(datos['constantes']['CC_TOPE_DER']['valor'], 90)
        self.assertEqual(datos['parametros_iniciales']['der'], '0,045')
        self.assertEqual(datos['parametros_iniciales']['ivaDer'], 'no')
        self.assertEqual(datos['parametros_iniciales']['baseDer'], 'vto')
        self.assertEqual(len(datos['formulas_metodologia']), 2)
        codigo = [x['codigo'] for x in datos['expresiones_codigo']]
        self.assertTrue(any('30/n' in linea and 'CC_BASE/n' in linea for linea in codigo))
        self.assertNotIn('resultados', datos)

    def test_caucion_ausente_se_identifica(self):
        html = '<script>const MET = {rf:{nombre:"Renta fija",grupos:[]}};</script>'
        datos = IAMC.extraer_caucion(html.encode(), URL)
        self.assertFalse(datos['disponible'])
        self.assertNotIn('parametros_iniciales', datos)

    def test_salida_texto_mantiene_expresion_y_ubicacion(self):
        texto = IAMC.texto_metodologias(self.extraer())
        self.assertIn('P = Σ CF_{t} / (1+r)^{d/365}', texto)
        self.assertIn('Líneas', texto)
        self.assertIn(URL, texto)
        self.assertNotIn('PARRAFO_LARGO_NO_COPIAR', texto)

    def test_cli_no_permite_sobrescribir_html_original(self):
        with tempfile.TemporaryDirectory() as temporal:
            carpeta = Path(temporal)
            origen = carpeta / 'original.html'
            origen.write_text(HTML)
            antes = origen.read_bytes()
            proceso = subprocess.run([sys.executable, str(HERRAMIENTA), '--html', str(origen), '--url', URL,
                                      '--salida-json', str(origen), '--salida-texto', str(carpeta / 'met.txt'),
                                      '--salida-caucion', str(carpeta / 'cau.json')], capture_output=True, text=True, timeout=10)
            self.assertNotEqual(proceso.returncode, 0)
            self.assertEqual(origen.read_bytes(), antes)
            self.assertFalse((carpeta / 'met.txt').exists())
            self.assertFalse((carpeta / 'cau.json').exists())

    def test_cli_solo_lee_html_local_y_escribe_derivados(self):
        with tempfile.TemporaryDirectory() as temporal:
            carpeta = Path(temporal)
            origen = carpeta / 'ejemplo.html'
            origen.write_text(HTML)
            rutas = [carpeta / n for n in ('met.json', 'met.txt', 'caucion.json')]
            antes = origen.read_bytes()
            proceso = subprocess.run([sys.executable, str(HERRAMIENTA), '--html', str(origen), '--url', URL,
                                      '--salida-json', str(rutas[0]), '--salida-texto', str(rutas[1]),
                                      '--salida-caucion', str(rutas[2])], capture_output=True, text=True, timeout=10)
            self.assertEqual(proceso.returncode, 0, proceso.stdout + proceso.stderr)
            self.assertEqual(origen.read_bytes(), antes)
            self.assertEqual(len(json.loads(rutas[0].read_text())['formulas']), 4)
            self.assertIn('CF_{t}', rutas[1].read_text())
            self.assertTrue(json.loads(rutas[2].read_text())['disponible'])


if __name__ == '__main__':
    unittest.main()
