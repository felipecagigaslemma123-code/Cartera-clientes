"""Extrae fórmulas publicadas del HTML IAMC sin ejecutar JavaScript ni usar red.

Es una copia de evidencia estática, no un motor financiero ni una aprobación de
las convenciones. Se conserva la expresión original junto a su ubicación.
"""

import argparse
from dataclasses import dataclass
import hashlib
from html.parser import HTMLParser
import json
from pathlib import Path
import re


class ErrorExtraccion(ValueError):
    """La estructura publicada no puede leerse con este extractor limitado."""


@dataclass
class _Nodo:
    valor: object
    inicio: int
    fin: int


class _LiteralJS:
    """Lector de literales: jamás evalúa identificadores, funciones u operadores."""

    def __init__(self, texto, inicio):
        self.texto = texto
        self.i = inicio

    def _espacio(self):
        while self.i < len(self.texto):
            if self.texto[self.i].isspace():
                self.i += 1
            elif self.texto.startswith('//', self.i):
                fin = self.texto.find('\n', self.i)
                self.i = len(self.texto) if fin < 0 else fin + 1
            elif self.texto.startswith('/*', self.i):
                fin = self.texto.find('*/', self.i + 2)
                if fin < 0:
                    raise ErrorExtraccion('Comentario JavaScript sin cerrar.')
                self.i = fin + 2
            else:
                break

    def _exigir(self, signo):
        self._espacio()
        if not self.texto.startswith(signo, self.i):
            raise ErrorExtraccion('Se esperaba {!r} en posición {}.'.format(signo, self.i))
        self.i += len(signo)

    def _cadena(self):
        comilla = self.texto[self.i]
        self.i += 1
        resultado = []
        escapes = {'n': '\n', 'r': '\r', 't': '\t', 'b': '\b', 'f': '\f',
                   'v': '\v', '\\': '\\', "'": "'", '"': '"', '/': '/'}
        while self.i < len(self.texto):
            caracter = self.texto[self.i]
            self.i += 1
            if caracter == comilla:
                return ''.join(resultado)
            if caracter in '\r\n':
                raise ErrorExtraccion('Salto sin escapar dentro de un literal JavaScript.')
            if caracter != '\\':
                resultado.append(caracter)
                continue
            if self.i >= len(self.texto):
                break
            escape = self.texto[self.i]
            self.i += 1
            if escape in escapes:
                resultado.append(escapes[escape])
            elif escape in ('x', 'u'):
                n = 2 if escape == 'x' else 4
                hexadecimal = self.texto[self.i:self.i + n]
                if len(hexadecimal) != n or not re.fullmatch('[0-9a-fA-F]+', hexadecimal):
                    raise ErrorExtraccion('Escape hexadecimal inválido.')
                resultado.append(chr(int(hexadecimal, 16)))
                self.i += n
            elif escape in '\r\n':
                if escape == '\r' and self.texto[self.i:self.i + 1] == '\n':
                    self.i += 1
            else:
                raise ErrorExtraccion('Escape JavaScript no admitido: ' + escape)
        raise ErrorExtraccion('Cadena JavaScript sin cerrar.')

    def leer(self):
        self._espacio()
        inicio = self.i
        if self.i >= len(self.texto):
            raise ErrorExtraccion('Literal incompleto.')
        caracter = self.texto[self.i]
        if caracter in ("'", '"'):
            valor = self._cadena()
            while True:
                self._espacio()
                if self.texto[self.i:self.i + 1] != '+':
                    break
                self.i += 1
                self._espacio()
                if self.texto[self.i:self.i + 1] not in ("'", '"'):
                    raise ErrorExtraccion('Sólo se admite concatenar cadenas literales.')
                valor += self._cadena()
            return _Nodo(valor, inicio, self.i)
        if caracter == '{':
            self.i += 1
            valores = {}
            while True:
                self._espacio()
                if self.texto[self.i:self.i + 1] == '}':
                    self.i += 1
                    return _Nodo(valores, inicio, self.i)
                if self.texto[self.i:self.i + 1] in ("'", '"'):
                    clave = self._cadena()
                else:
                    coincidencia = re.match(r'[A-Za-z_$][\w$]*', self.texto[self.i:])
                    if coincidencia is None:
                        raise ErrorExtraccion('Clave JavaScript no admitida.')
                    clave = coincidencia[0]
                    self.i += len(clave)
                if clave in valores:
                    raise ErrorExtraccion('Clave JavaScript repetida: ' + clave)
                self._exigir(':')
                valores[clave] = self.leer()
                self._espacio()
                if self.texto[self.i:self.i + 1] == '}':
                    continue
                self._exigir(',')
        if caracter == '[':
            self.i += 1
            valores = []
            while True:
                self._espacio()
                if self.texto[self.i:self.i + 1] == ']':
                    self.i += 1
                    return _Nodo(valores, inicio, self.i)
                valores.append(self.leer())
                self._espacio()
                if self.texto[self.i:self.i + 1] == ']':
                    continue
                self._exigir(',')
        numero = re.match(r'-?(?:0|[1-9]\d*)(?:\.\d+)?(?:[eE][+-]?\d+)?', self.texto[self.i:])
        if numero:
            self.i += len(numero[0])
            return _Nodo(json.loads(numero[0]), inicio, self.i)
        for literal, valor in (('true', True), ('false', False), ('null', None)):
            if self.texto.startswith(literal, self.i):
                self.i += len(literal)
                return _Nodo(valor, inicio, self.i)
        raise ErrorExtraccion('Valor JavaScript no literal; no se ejecuta código.')


def _objeto_constante(texto, nombre, obligatorio=True):
    coincidencias = list(re.finditer(r'\bconst\s+' + re.escape(nombre) + r'\s*=\s*', texto))
    if not coincidencias and not obligatorio:
        return None
    if len(coincidencias) != 1:
        raise ErrorExtraccion('Se esperaba una única constante ' + nombre + '.')
    nodo = _LiteralJS(texto, coincidencias[0].end()).leer()
    if not isinstance(nodo.valor, dict):
        raise ErrorExtraccion(nombre + ' debe ser un objeto literal.')
    return nodo


def _plano(nodo):
    if isinstance(nodo.valor, dict):
        return {clave: _plano(valor) for clave, valor in nodo.valor.items()}
    if isinstance(nodo.valor, list):
        return [_plano(valor) for valor in nodo.valor]
    return nodo.valor


class _TextoFormula(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.partes = []

    def handle_starttag(self, tag, attrs):
        if tag in ('sub', 'sup'):
            self.partes.append(('_' if tag == 'sub' else '^') + '{')
        elif tag == 'br':
            self.partes.append('\n')

    def handle_endtag(self, tag):
        if tag in ('sub', 'sup'):
            self.partes.append('}')

    def handle_data(self, texto):
        self.partes.append(texto)


def _texto_formula(formula):
    parser = _TextoFormula()
    parser.feed(formula)
    parser.close()
    return ''.join(parser.partes)


def _fuente(contenido, url):
    return {'url': url, 'sha256': hashlib.sha256(contenido).hexdigest(),
            'bytes': len(contenido), 'tipo': 'HTML público guardado, sin ejecutar sus scripts'}


def _ubicacion(texto, inicio, fin):
    return {'linea_inicio': texto.count('\n', 0, inicio) + 1,
            'linea_fin': texto.count('\n', 0, max(inicio, fin - 1)) + 1}


def extraer_metodologias(contenido, fuente_url):
    """Devuelve expresiones t/f de MET con procedencia; no evalúa las fórmulas."""
    texto = contenido.decode('utf-8-sig')
    met = _objeto_constante(texto, 'MET')
    formulas = []
    for seccion, valor in met.valor.items():
        if not isinstance(valor.valor, dict):
            raise ErrorExtraccion('Sección MET inválida: ' + seccion)
        nombre = valor.valor.get('nombre')
        grupos = valor.valor.get('grupos')
        if nombre is None or grupos is None or not isinstance(grupos.valor, list):
            raise ErrorExtraccion('MET sin nombre/grupos en ' + seccion)
        for grupo in grupos.valor:
            if not isinstance(grupo.valor, dict) or not {'g', 'cards'} <= set(grupo.valor):
                raise ErrorExtraccion('Grupo MET inválido.')
            etiqueta, tarjetas = grupo.valor['g'], grupo.valor['cards']
            if not isinstance(etiqueta.valor, str) or not isinstance(tarjetas.valor, list):
                raise ErrorExtraccion('Etiqueta o tarjetas MET inválidas.')
            for tarjeta in tarjetas.valor:
                if not isinstance(tarjeta.valor, dict) or not {'t', 'f'} <= set(tarjeta.valor):
                    raise ErrorExtraccion('Tarjeta MET sin título o fórmula.')
                titulo, formula = tarjeta.valor['t'], tarjeta.valor['f']
                if not isinstance(titulo.valor, str) or not isinstance(formula.valor, str):
                    raise ErrorExtraccion('Título y fórmula deben ser cadenas estáticas.')
                registro = {'seccion': seccion, 'nombre_seccion': nombre.valor,
                            'grupo': etiqueta.valor, 'titulo': titulo.valor,
                            'formula_html': formula.valor, 'formula_texto': _texto_formula(formula.valor),
                            'tiene_formula': bool(formula.valor),
                            'fragmento_js': texto[formula.inicio:formula.fin],
                            'ubicacion': _ubicacion(texto, formula.inicio, formula.fin)}
                formulas.append(registro)
    return {'esquema_version': 1, 'naturaleza': 'transcripción estática; no valida ni aprueba fórmulas',
            'fuente': _fuente(contenido, fuente_url), 'formulas': formulas}


def _fragmentos_lineas(texto, expresiones):
    encontrados = []
    for numero, linea in enumerate(texto.splitlines(), 1):
        if any(re.search(expresion, linea) for expresion in expresiones):
            encontrados.append({'linea': numero, 'codigo': linea.strip()})
    return encontrados


def extraer_caucion(contenido, fuente_url):
    """Extrae defaults y expresiones observadas; no calcula cauciones ni tasas."""
    texto = contenido.decode('utf-8-sig')
    sc = _objeto_constante(texto, 'SC', obligatorio=False)
    metodologia = extraer_metodologias(contenido, fuente_url)
    formulas = [f for f in metodologia['formulas'] if f['grupo'] == 'Calculadora de Caución']
    constantes = {}
    for nombre in ('CC_BASE', 'CC_BASE_DER', 'CC_TOPE_DER'):
        coincidencias = list(re.finditer(r'\b' + nombre + r'\s*=\s*(\d+)\b', texto))
        if len(coincidencias) > 1:
            raise ErrorExtraccion('Constante de caución repetida: ' + nombre)
        if coincidencias:
            coincidencia = coincidencias[0]
            constantes[nombre] = {'valor': int(coincidencia[1]),
                                  'ubicacion': _ubicacion(texto, coincidencia.start(), coincidencia.end())}
    # Se recortan sólo asignaciones/expresiones, no párrafos de ayuda del sitio.
    expresiones = [r'^\s*const n=p\.n, I=', r'^\s*const bc=p\.baseComVto',
                   r'^\s*const bd=p\.baseDerVto', r'^\s*const der=bd\*p\.der',
                   r'^\s*const iva1=p\.ivaCom', r'^\s*const G=com\+',
                   r'^\s*r\.f0=p\.monto', r'^\s*r\.exig=', r'^\s*r\.ok = r\.f0',
                   r'^\s*r\.per=r\.neto', r'^\s*r\.teaN=', r'^\s*r\.teaB=',
                   r'^\s*const CC_ON =', r'^\s*return c \? \{v:c\.v',
                   r'^\s*if\(!SC\.admMan\) SC\.adm =',
                   r'^\s*if\(CC_ON\) SC\.tna =', r'^\s*const c=CC_CURVA\.find',
                   r'^\s*if\(c\)\{ SC\.tna=',
                   r'^\s*else if\(q>0\)\{ vm=', r'^\s*return \{d, vm, va:',
                   r'^\s*const g=totG\(\), exig =', r'^\s*const maxT = bien']
    codigo = _fragmentos_lineas(texto, expresiones)
    if sc is None and not formulas:
        return {'esquema_version': 1, 'fuente': _fuente(contenido, fuente_url),
                'disponible': False, 'naturaleza': 'no se encontró calculadora de caución en el HTML'}
    return {'esquema_version': 1, 'fuente': _fuente(contenido, fuente_url),
            'disponible': True, 'naturaleza': 'evidencia estática; sin cálculos ni validación de convenciones',
            'parametros_iniciales': None if sc is None else _plano(sc),
            'ubicacion_parametros': None if sc is None else _ubicacion(texto, sc.inicio, sc.fin),
            'constantes': constantes, 'formulas_metodologia': formulas,
            'expresiones_codigo': codigo,
            'mapeo_editorial_de_campos': {
                'lado': 'col: colocadora; tom: tomadora',
                'liq': 'fecha de liquidación', 'pl': 'plazo en días corridos',
                'vto': 'vencimiento', 'monto': 'capital en ARS', 'tna': 'TNA pactada, entrada en porcentaje',
                'com': 'comisión del agente, TNA en porcentaje', 'commin': 'mínimo de comisión en ARS',
                'der': 'porcentaje de derechos de mercado', 'adm': 'porcentaje de administración de garantía',
                'otros': 'otros gastos fijos en ARS', 'iva': 'porcentaje de IVA',
                'ivaInt': 'porcentaje de IVA sobre interés', 'ivaCom': 'aplicar IVA sobre comisión y gastos fijos',
                'ivaDer': 'aplicar IVA sobre derechos y administración',
                'baseCom': 'base de comisión: capital o monto final',
                'baseDer': 'base de derechos y administración: capital o monto final',
                'mom': 'cobro de gastos: inicial o final', 'exig': 'garantía: capital o capital más interés',
                'car': 'filas de garantías; lista diferida en la versión publicada'},
            'advertencias_del_relevamiento': [
                'Se copian expresiones de la fuente, no una aprobación del modelo ni de su vigencia tributaria.',
                'La TNA pactada debe corresponder al plazo de la operación; el fallback CC_ON puede ser el primer plazo disponible.',
                'Los días hábiles seleccionan la referencia de mercado; el interés se calcula con días corridos.',
                'TEM de caución usa 30/n; TEA usa 365/n. No sustituir por conversión mensual a 12 meses.',
                'La lista de garantías puede estar diferida; no se solicitó ni se completó con supuestos.']}


def texto_metodologias(datos):
    fuente = datos['fuente']
    lineas = ['Fórmulas IAMC — transcripción estática, sin ejecución ni aprobación',
              'URL: ' + fuente['url'], 'SHA-256: ' + fuente['sha256'],
              'Los subíndices se representan con _{...} y los exponentes con ^{...}.', '']
    for f in datos['formulas']:
        loc = f['ubicacion']
        lineas += ['{} / {} / {}'.format(f['nombre_seccion'], f['grupo'], f['titulo']),
                   'Líneas {}-{}'.format(loc['linea_inicio'], loc['linea_fin']),
                   f['formula_texto'] or '[Sin fórmula publicada en el campo f]', '']
    return '\n'.join(lineas)


def main(argumentos=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--html', type=Path, required=True)
    parser.add_argument('--url', required=True)
    parser.add_argument('--salida-json', type=Path, required=True)
    parser.add_argument('--salida-texto', type=Path, required=True)
    parser.add_argument('--salida-caucion', type=Path, required=True)
    opciones = parser.parse_args(argumentos)
    destinos = [ruta.resolve() for ruta in (opciones.salida_json, opciones.salida_texto, opciones.salida_caucion)]
    if opciones.html.resolve() in destinos or len(set(destinos)) != len(destinos):
        parser.error('Las tres salidas deben ser diferentes y no pueden reemplazar el HTML original.')
    contenido = opciones.html.read_bytes()
    datos = extraer_metodologias(contenido, opciones.url)
    caucion = extraer_caucion(contenido, opciones.url)
    salidas = ((opciones.salida_json, json.dumps(datos, ensure_ascii=False, indent=2, allow_nan=False) + '\n'),
               (opciones.salida_texto, texto_metodologias(datos)),
               (opciones.salida_caucion, json.dumps(caucion, ensure_ascii=False, indent=2, allow_nan=False) + '\n'))
    for ruta, valor in salidas:
        ruta.parent.mkdir(parents=True, exist_ok=True)
        ruta.write_text(valor, encoding='utf-8')
    print('Extraídas {} tarjetas metodológicas; fuente SHA-256 {}.'.format(len(datos['formulas']), datos['fuente']['sha256']))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
