"""Lectura de fórmulas y cachés OOXML, sin dependencias; no recalcula Excel."""
from pathlib import Path
from zipfile import ZipFile
import xml.etree.ElementTree as ET
N={'m':'http://schemas.openxmlformats.org/spreadsheetml/2006/main','r':'http://schemas.openxmlformats.org/officeDocument/2006/relationships'}

def leer_libro(ruta):
    with ZipFile(ruta) as z:
        compartidas=[]
        if 'xl/sharedStrings.xml' in z.namelist():
            compartidas=[''.join(si.itertext()) for si in ET.fromstring(z.read('xl/sharedStrings.xml'))]
        relaciones={el.attrib['Id']:el.attrib['Target'] for el in ET.fromstring(z.read('xl/_rels/workbook.xml.rels'))}
        hojas={}
        for s in ET.fromstring(z.read('xl/workbook.xml')).findall('m:sheets/m:sheet',N):
            target=relaciones[s.attrib['{'+N['r']+'}id']]
            archivo=target.lstrip('/') if target.startswith('/') else 'xl/'+target
            celdas={}
            for c in ET.fromstring(z.read(archivo)).findall('.//m:sheetData/m:row/m:c',N):
                v=c.find('m:v',N);f=c.find('m:f',N);tipo=c.attrib.get('t');valor=v.text if v is not None else None
                if tipo=='s' and valor is not None:valor=compartidas[int(valor)]
                elif tipo=='inlineStr':valor=''.join(c.find('m:is',N).itertext())
                elif tipo not in ('str','e') and valor is not None:
                    try:valor=float(valor)
                    except ValueError:pass
                celdas[c.attrib['r']]={'valor':valor,'formula':f.text if f is not None else None,'tipo':tipo}
            hojas[s.attrib['name']]=celdas
        return hojas
