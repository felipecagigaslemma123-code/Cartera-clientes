"""Plantillas de operación: calendario, rutas y ausencia de credenciales."""

from pathlib import Path
import plistlib
import unittest


RAIZ = Path(__file__).resolve().parents[1]
VALORES = {
    '{{PYTHON}}': '/Users/demo/.venvs/cartera/bin/python',
    '{{PROYECTO}}': '/Users/demo/OneDrive-Personal/Proyecto de prueba & cartera',
    '{{DATOS}}': '/Users/demo/Datos ficticios',
    '{{CLIENTE}}': 'cliente-demo',
    '{{LOGS}}': '/Users/demo/Library/Logs/cartera',
}


class PlantillasOperativas(unittest.TestCase):
    def leer(self, comando):
        archivo = RAIZ / 'ops' / ('cartera.' + comando + '.plist.template')
        texto = archivo.read_text(encoding='utf-8')
        for marcador in VALORES:
            self.assertIn(marcador, texto)
        contenido = plistlib.loads(texto.encode('utf-8'))
        def reemplazar(valor):
            if isinstance(valor, str):
                for marcador, texto in VALORES.items():
                    valor = valor.replace(marcador, texto)
                return valor
            if isinstance(valor, list):
                return [reemplazar(item) for item in valor]
            if isinstance(valor, dict):
                return {clave: reemplazar(item) for clave, item in valor.items()}
            return valor
        contenido = reemplazar(contenido)
        return plistlib.loads(plistlib.dumps(contenido))

    def test_argumentos_con_espacios_siguen_separados_y_sin_shell(self):
        for comando in ('alertas', 'capturar'):
            with self.subTest(comando=comando):
                plantilla = self.leer(comando)
                self.assertEqual(plantilla['ProgramArguments'], [
                    VALORES['{{PYTHON}}'], '-m', 'cartera', '--datos',
                    VALORES['{{DATOS}}'], comando, '--cliente', VALORES['{{CLIENTE}}'],
                ])
                self.assertNotIn('/bin/sh', plantilla['ProgramArguments'])
                self.assertEqual(plantilla['WorkingDirectory'], VALORES['{{PROYECTO}}'])

    def test_entorno_define_codigo_y_datos_sin_credenciales(self):
        for comando in ('alertas', 'capturar'):
            with self.subTest(comando=comando):
                plantilla = self.leer(comando)
                self.assertEqual(plantilla['EnvironmentVariables'], {
                    'PYTHONPATH': VALORES['{{PROYECTO}}'] + '/src',
                    'CARTERA_DATOS': VALORES['{{DATOS}}'],
                })
                serializado = plistlib.dumps(plantilla).decode('utf-8')
                self.assertNotIn('TELEGRAM_BOT_TOKEN', serializado)
                self.assertNotIn('TELEGRAM_CHAT_ID', serializado)

    def test_logs_privados_fuera_de_onedrive_y_rutas_distintas(self):
        for comando in ('alertas', 'capturar'):
            with self.subTest(comando=comando):
                plantilla = self.leer(comando)
                self.assertEqual(plantilla['Umask'], 0o077)
                self.assertFalse(plantilla['RunAtLoad'])
                self.assertNotIn('KeepAlive', plantilla)
                self.assertNotEqual(plantilla['StandardOutPath'], plantilla['StandardErrorPath'])
                for clave in ('StandardOutPath', 'StandardErrorPath'):
                    ruta = Path(plantilla[clave])
                    self.assertTrue(ruta.is_absolute())
                    self.assertEqual(ruta.parent, Path(VALORES['{{LOGS}}']))
                    self.assertNotIn('onedrive', str(ruta).lower())

    def test_alertas_tiene_un_unico_intervalo_de_cinco_minutos(self):
        plantilla = self.leer('alertas')
        self.assertEqual(plantilla['StartInterval'], 300)
        self.assertNotIn('StartCalendarInterval', plantilla)

    def test_captura_tiene_exactamente_los_35_horarios_previstos(self):
        plantilla = self.leer('capturar')
        horarios = plantilla['StartCalendarInterval']
        self.assertEqual(len(horarios), 35)
        esperados = {(dia, hora, 0) for dia in range(1, 6) for hora in range(11, 18)}
        recibidos = {(h['Weekday'], h['Hour'], h['Minute']) for h in horarios}
        self.assertEqual(recibidos, esperados)
        self.assertNotIn('StartInterval', plantilla)


if __name__ == '__main__':
    unittest.main()
