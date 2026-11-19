"""Regeneración explícita del patrón sintético y del oráculo de referencia."""
import csv,datetime,json,math
from pathlib import Path
import caso

def generar():
    sal=Path(__file__).parent/'caso_ficticio';sal.mkdir(exist_ok=True)
    nombres=['ACC_A','CED_B','ACC_C','BONO_FIJO','BONO_CERO','EFECTIVO']
    cfg={'naturaleza':'100% sintética; no son cotizaciones de mercado',
         'moneda':'USD_CCL ficticio','periodos_anio':252,'confianza':0.95,'lambda':0.94,
         'retornos':'simples, excepto EWMA que usa logaritmos','media_VaR_normal':0.,
         'politica_pesos':'constantes, rebalanceo diario hipotético; no performance real',
         'tipo_precios':'series sintéticas de retorno total ajustado; bonos escalados a precio sucio contractual al corte',
         'orden_activos':nombres,'pesos':[.2,.2,.15,.2,.15,.1],'valor_cartera':100000.,
         'bonos':{'BONO_FIJO':{'flujo':{'nominal':100,'cupon':.08,'anios':3,'frecuencia':2},'tir':.10},
                  'BONO_CERO':{'flujo':{'nominal':100,'cupon':0.,'anios':2,'frecuencia':1},'tir':.10}}}
    (sal/'parametros.json').write_text(json.dumps(cfg,indent=2,ensure_ascii=False)+'\n')
    fecha=datetime.date(2024,1,2);fechas=[]
    while len(fechas)<261:
        if fecha.weekday()<5:fechas.append(fecha.isoformat())
        fecha+=datetime.timedelta(days=1)
    p=[100.,80.,120.,95.,85.,1.];merc=100.;ccl=1000.;ipc=100.;precios=[];factores=[]
    for t,d in enumerate(fechas):
        if t:
            rm=.0003+.009*math.sin(t*.71)+.004*math.cos(t*.17)
            fx=.0008+.003*math.cos(t*.31)
            rs=[1.1*rm+.004*math.sin(t*1.9),.8*rm+.003*math.cos(t*1.3),
                -.35*rm+.006*math.sin(t*.43),.0002-.0018*math.cos(t*.27)+.0006*math.sin(t*.91),
                .00015-.0025*math.cos(t*.27),0.]
            p=[v*(1+x) for v,x in zip(p,rs)];merc*=1+rm;ccl*=1+fx;ipc*=1+.001
        precios.append([d]+[format(v,'.17g') for v in p])
        factores.append([d,format(merc,'.17g'),format(ccl,'.17g'),format(ipc,'.17g'),'0.00005'])
    # Anclar bonos al precio sucio de los flujos del corte. El escalado de toda
    # la serie preserva sus retornos; las series son precios ajustados sintéticos.
    for nombre,datos in cfg['bonos'].items():
        j=nombres.index(nombre)+1
        flujos=caso.r.flujos_fijos(**datos['flujo'])
        precio_corte=caso.r.bono(flujos,datos['tir'],datos['flujo']['frecuencia'])['precio_sucio']
        escala=precio_corte/float(precios[-1][j])
        for fila in precios:fila[j]=format(float(fila[j])*escala,'.17g')
        precios[-1][j]=format(precio_corte,'.17g')
    for nombre,cabecera,filas in [('precios.csv',['fecha']+nombres,precios),('factores.csv',['fecha','mercado','ccl','ipc','libre_diaria'],factores)]:
        with (sal/nombre).open('w',newline='') as f:w=csv.writer(f);w.writerow(cabecera);w.writerows(filas)
    esperado=caso.calcular(sal)
    (sal/'esperado.json').write_text(json.dumps(esperado,indent=2,ensure_ascii=False,allow_nan=False)+'\n')
    print('Caso generado: 261 precios, 260 retornos, 6 activos; esperado.json guardado.')

if __name__=='__main__':generar()
