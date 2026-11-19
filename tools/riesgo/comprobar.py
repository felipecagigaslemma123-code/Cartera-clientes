"""Ejecutar desde cualquier carpeta: python3 entrega/verificacion/comprobar.py.
No necesita openpyxl, numpy ni acceso a red. Lee bibliografía original y oráculo.
No modifica el oráculo ni las fuentes. Sale con error si falla una comprobación.
"""
import json,math,statistics,csv,sys
from pathlib import Path
import riesgo_ref as r
from leer_excel import leer_libro
import caso

RAIZ=Path(__file__).resolve().parents[2]
BIB=RAIZ/'bibliografia'

def cerca(nombre, calculado, fuente, tolerancia=1e-12):
    diferencia=calculado-fuente
    print('%s | ref=%.12g | fuente=%.12g | diferencia=%+.6g'%(nombre,calculado,fuente,diferencia))
    if abs(diferencia)>tolerancia:raise AssertionError(nombre)

def comparar(a,b,ruta='raiz'):
    if isinstance(b,dict):
        assert set(a)==set(b),ruta
        return sum(comparar(a[k],b[k],ruta+'.'+k) for k in b)
    if isinstance(b,list):
        assert len(a)==len(b),ruta
        return sum(comparar(x,y,ruta+'[%d]'%i) for i,(x,y) in enumerate(zip(a,b)))
    if isinstance(b,(float,int)):
        assert math.isfinite(a) and math.isclose(a,b,rel_tol=1e-10,abs_tol=1e-12),ruta
        return 1
    assert a==b,ruta
    return 0

def main():
    libro=leer_libro(BIB/'Estimando volatilidades.xlsx');g=libro['GARCH (1,1) SP500'];ma=libro['MA']
    precios=[g['AG%d'%i]['valor'] for i in range(2,1281)]
    logs=r.retornos(precios,True)
    cerca('Excel: retorno log AH1280',logs[-1],g['AH1280']['valor'])
    hist=r.volatilidad(logs)
    cerca('Historica SP500: ref vs statistics.stdev*sqrt(252)',hist,statistics.stdev(logs)*math.sqrt(252))
    hma=r.volatilidad(r.retornos([ma['B%d'%i]['valor'] for i in range(2,244)],True))
    print('Historica MA reconstruida: n=241; vol anual=%.12g; MA!C3:C243 VACIO; MA!J1=0; no hay resultado fuente.'%hma)
    assert g['L21']['valor']=='#DIV/0!'
    print('Diferencia de fuente: GARCH!L21 guarda #DIV/0!; apunta a D3:D1280 vacio. Historica reconstruida, no igualdad bibliografica.')
    ew=r.ewma(logs,g['AN2']['valor'])
    cerca('Excel: EWMA previa AJ1280',ew['previas'][-1],g['AJ1280']['valor'])
    cerca('Excel: EWMA anual AL1280',math.sqrt(252*ew['previas'][-1]),g['AL1280']['valor'])
    maxdif=max(abs(v-g['AJ%d'%(i+3)]['valor']) for i,v in enumerate(ew['previas']))
    print('Excel: max diferencia 1278 varianzas EWMA = %.6g; pronostico siguiente=%.12g'%(maxdif,ew['siguiente']))
    assert maxdif<1e-12
    beta_libro=leer_libro(BIB/'EJERCICIOS 1:10'/'Clase 08_Testeando betas_2025.xlsm')['R - Rf']
    x=[beta_libro['C%d'%i]['valor'] for i in range(9,69)];y=[beta_libro['D%d'%i]['valor'] for i in range(9,69)]
    reg=r.modelo_indice(y,x)
    cerca('Clase 08: beta Alcoa R - Rf!D5',reg['beta'],beta_libro['D5']['valor'])
    cerca('Clase 08: alfa Alcoa R - Rf!D6',reg['alfa_periodica'],beta_libro['D6']['valor'])
    print('Beta Alcoa: IC95=[%.9f, %.9f]; t H0 beta=1: %.9f; p=%.9f'%(reg['intervalo_beta'][0],reg['intervalo_beta'][1],reg['prueba_beta']['t'],reg['prueba_beta']['p']))
    testcapm=leer_libro(BIB/'EJERCICIOS 1:10'/'Clase 08_Testeando betas_2025.xlsm')['Test CAPM']
    segunda=r.modelo_indice([testcapm['B%d'%i]['valor'] for i in range(3,33)], [testcapm['C%d'%i]['valor'] for i in range(3,33)])
    cerca('Clase 08 segunda pasada: pendiente G5',segunda['beta'],testcapm['G5']['valor'])
    cerca('Clase 08 segunda pasada: intercepto G4',segunda['alfa_periodica'],testcapm['G4']['valor'])
    mark=leer_libro(BIB/'EJERCICIOS 1:10'/'Clase 08_Markovitz no short sales_2025.xlsm')['Caso 0_con short sales']
    cov=[[mark['%s%d'%(c,i)]['valor'] for c in 'BCDE'] for i in range(3,7)]
    w=[mark['B%d'%i]['valor'] for i in range(11,15)]
    riesgo=r.riesgo_cartera(w,cov,1)
    cerca('Markowitz: sigma B18',riesgo['vol_diaria'],mark['B18']['valor'])
    cerca('Markowitz: varianza B18^2',riesgo['varianza_diaria'],mark['B18']['valor']**2)
    cola=r.var_es_cola_bodie([-.2503,-.2569,-.3349,-.4103,-.4564],84)
    cerca('Bodie PDF168 p139: VaR vs 25.56% redondeado',cola['var'],.2556,3e-5)
    print('Bodie PDF169 p140: ES ref=%.12g | fuente=.3594 | diferencia=%+.9g (NO COINCIDE; se conserva discrepancia)'%(cola['es'],cola['es']-.3594))
    cerca('ES Bodie: aritmetica independiente',cola['es'],(45.64+41.03+33.49+25.69+.2*25.03)/420)
    f=r.flujos_fijos(1000,.08,2,2);b=r.bono(f,.1,2)
    cerca('Bodie PDF550: precio bono 2 anios',b['precio_sucio'],964.540,.001)
    cerca('Bodie PDF549: Macaulay 2 anios',b['macaulay_anios'],1.8852,.0001)
    f30=r.flujos_fijos(1000,.08,30,1);b30=r.bono(f30,.08,1)
    cerca('Bodie PDF556: duration modificada 30 anios',b30['modificada_anios'],11.26,.005)
    cerca('Bodie PDF556: convexidad 30 anios',b30['convexidad_anios2'],212.4,.05)
    cerca('Bodie PDF556: precio TIR 10%',r.bono(f30,.1,1)['precio_sucio'],811.46,.005)
    fc=r.flujos_fijos(100,.11,5,1);bc=r.bono(fc,.15,1)
    cerca('CFA FI PDF104: convexidad',bc['convexidad_anios2'],16.915,.002)
    cerca('CFA FI PDF104: precio',bc['precio_sucio'],86.59138,.00001)
    cerca('CFA FI PDF105: precio TIR 14.5%',r.bono(fc,.145,1)['precio_sucio'],88.12721,.00001)
    cerca('CFA FI PDF120: perdida esperada %',r.perdida_crediticia(1,.03,.75),.0075)
    invalida=[[.002,.00005,.0003],[.00005,.00004,.0056],[.0003,.0056,.008]]
    try:r.riesgo_cartera([.2,.5,.3],invalida)
    except ValueError:print('Clase 1 estimacion prob PDF52: matriz RECHAZADA; rho23=%.9f >1 (error de fuente, no se corrige).'%(.0056/math.sqrt(.00004*.008)))
    else:raise AssertionError('Se admitio matriz invalida de la bibliografia')
    with (BIB/'hedgefundindices.csv').open() as archivo:fondos=list(csv.DictReader(archivo))
    for nombre,aproximado in [('Global Macro',.029),('Equity Market Neutral',.036)]:
        serie=[float(f[nombre])/100 for f in fondos]
        umbral=r.var_es_historico(serie,.99,metodo='lineal')['var']
        condicional=-r.media([x for x in serie if -x>=umbral])
        print('Resumen VAR (inferencia c=99%%): %s ES umbral=%.9f vs publicado aprox %.3f; ES fraccional=%.9f'%(nombre,condicional,aproximado,r.var_es_historico(serie,.99)['es']))
        assert abs(condicional-aproximado)<.0005
    # Verificación manual independiente 1: media 0, sum cuadrados .0008, n-1=2.
    cerca('MANUAL 1: varianza [-2%,0,2%]',r.varianza([-.02,0,.02]),.0004)
    cerca('MANUAL 1: EWMA .94*.0004+.06*.0001',r.ewma([.01],inicial=.0004)['siguiente'],.000382)
    # Verificación manual independiente 2: bono cero 2 años, P=100/1.1², D=2/1.1, C=6/1.1².
    cero=r.bono([(2,100)],.1,1)
    cerca('MANUAL 2: precio cero',cero['precio_sucio'],100/1.21)
    cerca('MANUAL 2: duration cero',cero['modificada_anios'],20/11)
    cerca('MANUAL 2: convexidad cero',cero['convexidad_anios2'],600/121)
    # Verificación manual del caso: HHI .04+.04+.0225+.04+.0225+.01=.175.
    calculado=caso.calcular();cerca('MANUAL caso: HHI',calculado['cartera']['concentracion']['herfindahl'],.175)
    cerca('MANUAL caso: bono cero DV01',calculado['bonos']['BONO_CERO']['medidas']['dv01_por_nominal_flujos'],(100/1.21)*(20/11)*.0001)
    cerca('MANUAL caso: CEDEAR +10% suby +20% CCL',calculado['otros']['cedear_retorno'],.32)
    cerca('QIA PDF414 p406: t critico df60',r.cuantil_student(.975,60),2.00,.001)
    cerca('QIA PDF414 p406: IC inferior beta',1.5-.2*r.cuantil_student(.975,60),1.10,.001)
    cerca('QIA PDF414 p406: estadistico beta',(1.5-1)/.2,2.5)
    cerca('Student bilateral t=1 df=1',r.p_student_bilateral(1,1),.5)
    cerca('Student cuantil 97.5% df=10',r.cuantil_student(.975,10),2.2281388519649385,1e-10)
    assert r.retornos_calendario({'a':100,'c':102},['a','b','c'])=={'b':None,'c':None}
    assert r.correlacion([0,0,0],[1,2,3]) is None
    assert r.drawdown([100,120,90,110,121])['maxima_caida']==.25
    cerca('VaR/ES cola fraccional [1,2,3,4], c=.625',r.cuantiles_perdidas([1,2,3,4],.625)['es'],11/3)
    cerca('Euler: suma componentes = sigma',sum(calculado['cartera']['riesgo']['componentes_diarias']),calculado['cartera']['riesgo']['vol_diaria'])
    rp=calculado['cartera'];mc=rp['monte_carlo'];normal=rp['var_es_normal']
    assert abs(mc['var']/normal['var']-1)<.1
    assert abs(mc['es']/normal['es']-1)<.1
    r.cholesky_semidefinida(calculado['covarianzas_diarias'])
    esperado=json.loads((Path(__file__).parent/'caso_ficticio'/'esperado.json').read_text())
    cantidad=comparar(calculado,esperado)
    print('Caso CSV vs esperado.json: %d valores numericos coinciden (rtol=1e-10, atol=1e-12).'%cantidad)
    print('Controles de huecos, correlacion indefinida, drawdown, Euler, PSD y Monte Carlo: OK.')
    print('RESULTADO: controles ejecutables OK; diferencias documentadas: historica Excel sin cache valido y ES Bodie no coincide.')

if __name__=='__main__':
    if '--solo-caso' in sys.argv:
        esperado=json.loads((Path(__file__).parent/'caso_ficticio'/'esperado.json').read_text())
        cantidad=comparar(caso.calcular(),esperado)
        print('Caso ficticio: %d valores numericos coinciden; sin consultar bibliografia ni red.'%cantidad)
    else:main()
