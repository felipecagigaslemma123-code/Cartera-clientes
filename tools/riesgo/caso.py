"""Lee únicamente los CSV y parámetros sintéticos y calcula resultados."""
import csv
import json
from pathlib import Path
import riesgo_ref as r


def calcular(carpeta=None):
    carpeta=Path(carpeta or Path(__file__).parent/'caso_ficticio')
    cfg=json.loads((carpeta/'parametros.json').read_text())
    with (carpeta/'precios.csv').open() as f:filas=list(csv.DictReader(f))
    with (carpeta/'factores.csv').open() as f:factores=list(csv.DictReader(f))
    nombres=cfg['orden_activos'];pesos=cfg['pesos'];valor=cfg['valor_cartera']
    precios={k:[float(f[k]) for f in filas] for k in nombres}
    series=[r.retornos(precios[k]) for k in nombres]
    mercado=r.retornos([float(f['mercado']) for f in factores])
    ccl=r.retornos([float(f['ccl']) for f in factores])
    libre=[float(f['libre_diaria']) for f in factores[1:]]
    cov=r.matriz_covarianzas(series);rp=r.retornos_cartera(series,pesos)
    activos={}
    for i,k in enumerate(nombres):
        s=series[i];logs=r.retornos(precios[k],True);ew=r.ewma(logs)
        activos[k]={'n':len(s),'media_diaria':r.media(s),'vol_diaria':r.volatilidad(s,1),
                    'vol_anual':r.volatilidad(s),'vol_log_anual':r.volatilidad(logs),
                    'ewma_var_siguiente':ew['siguiente'],'ewma_vol_anual':(ew['siguiente']*252)**0.5,
                    'var_es_normal':r.var_es_normal(0,r.volatilidad(s,1),valor=valor*pesos[i]),
                    'var_es_historico':r.var_es_historico(s,valor=valor*pesos[i]),
                    'drawdown':r.drawdown(precios[k])}
        if i<5:
            activos[k]['indice']=r.modelo_indice(s,mercado,libre)
            activos[k]['desempeno']=r.desempeno(s,libre,mercado)
            activos[k]['momentos']=r.momentos(s)
            activos[k]['var_cornish_fisher']=r.var_cornish_fisher(s,valor=valor*pesos[i])
    riesgo=r.riesgo_cartera(pesos,cov)
    cartera={'riesgo':riesgo,'concentracion':r.concentracion(pesos),'indice':r.modelo_indice(rp,mercado,libre),
             'var_es_normal':r.var_es_normal(0,riesgo['vol_diaria'],valor=valor),
             'var_es_historico':r.var_es_historico(rp,valor=valor),
             'var_es_historico_10_sesiones':r.var_es_historico(r.retornos_horizonte(rp,10),valor=valor),
             'var_es_normal_10_sesiones':r.var_es_normal(0,riesgo['vol_diaria'],horizonte=10,valor=valor),
             'monte_carlo':r.monte_carlo([0]*len(pesos),cov,pesos,valor=valor),
             'desempeno':r.desempeno(rp,libre,mercado),'drawdown':r.drawdown(r.riqueza(rp)),
             'cobertura':r.cobertura(pesos,[True]*6),
             'ejemplo_exclusion_bono_2':r.cobertura(pesos,[True,True,True,True,False,True])}
    bonos={}
    for nombre,cfgbono in cfg['bonos'].items():
        flujos=r.flujos_fijos(**cfgbono['flujo']);tir=cfgbono['tir'];freq=cfgbono['flujo']['frecuencia']
        med=r.bono(flujos,tir,freq)
        menos=r.bono(flujos,tir-0.0001,freq)['precio_sucio'];mas=r.bono(flujos,tir+0.0001,freq)['precio_sucio']
        bonos[nombre]={'flujos':flujos,'medidas':med,'sensibilidad_numerica':r.sensibilidad_efectiva(med['precio_sucio'],menos,mas),
                      'escenarios':r.escenarios_bono(flujos,tir,freq)}
    vals=[valor*pesos[nombres.index(k)] for k in bonos]
    cartera['sensibilidades_bonos']=r.sensibilidades_cartera(vals,[v['medidas']['modificada_anios'] for v in bonos.values()],[v['medidas']['convexidad_anios2'] for v in bonos.values()])
    cartera['escenarios_tasa_importe']=[]
    for j in range(6):
        cartera['escenarios_tasa_importe'].append({'cambio_pb':list(bonos.values())[0]['escenarios'][j]['cambio_pb'],
          'pnl_exacto':sum(v*b['escenarios'][j]['retorno_exacto'] for v,b in zip(vals,bonos.values())),
          'pnl_aproximado':sum(v*b['escenarios'][j]['retorno_aproximado'] for v,b in zip(vals,bonos.values()))})
    varios={'anual_compuesto':r.retorno_anual_compuesto(rp),'capm':r.retorno_capm(.05,1.2,.1),'beta_ponderada':r.beta_cartera([.6,.4],[1.2,.8]),'varianza_factores':r.varianza_factores([1.2,.8],[[.04,.01],[.01,.09]],.01),'cupon_variable':r.cupon_variable(100,.3,30),'cedear_precio':r.precio_cedear(100,1000,10),'cedear_retorno':r.retorno_factores(.1,.2),
            'valor_en_usd':r.convertir_moneda(100000,1000),'retorno_real':r.retorno_real(.2,.1),
            'cer_capital':r.capital_ajustado(100,130,100),'perdida_crediticia':r.perdida_crediticia(100000,.03,.75),
            'spread_pb':r.spread_pb(.04,.025),'tasa_diaria_10pct':r.tasa_periodica(.1),
            'tasa_efectiva_nominal_10pct_semestre':r.tasa_nominal_a_efectiva(.1,2),
            'reinversion':r.valor_reinvertido([(1,10),(2,110)],2,.05),
            'precio_curva':r.precio_curva([(1,10),(2,110)],[.1,.1]),
            'liquidez':r.liquidez(100000,[1000000,2000000,0,1000000]),
            'modelo_dos_factores':r.modelo_factores(series[1],[mercado,ccl])}
    return {'convenciones':cfg,'activos':activos,'covarianzas_diarias':cov,'correlaciones':r.matriz_correlaciones(series),'cartera':cartera,'bonos':bonos,'otros':varios}
