"""Referencia didáctica Python 3.9, sólo biblioteca estándar.
Todas las tasas/retornos son decimales. No completa datos faltantes.
ValueError indica dato o dominio inválido; el consumidor debe mostrar «sin dato».
Las funciones no realizan E/S ni modifican sus argumentos.
"""
import math
import random
from statistics import NormalDist


def _serie(x, minimo=1):
    x = list(x)
    if len(x) < minimo or any(v is None or not isinstance(v, (int, float)) or not math.isfinite(v) for v in x):
        raise ValueError('sin dato: serie insuficiente, faltante o no finita')
    return x


def media(x):
    x = _serie(x)
    return math.fsum(x) / len(x)


def retorno_simple(anterior, actual, flujo=0.0):
    _serie([anterior, actual, flujo])
    if anterior <= 0 or actual < 0:
        raise ValueError('precios fuera de dominio')
    return (actual + flujo) / anterior - 1


def retorno_logaritmico(anterior, actual, flujo=0.0):
    r = retorno_simple(anterior, actual, flujo)
    if r <= -1:
        raise ValueError('logaritmo de riqueza no positiva')
    return math.log1p(r)


def retornos(precios, logaritmicos=False):
    precios = _serie(precios, 2)
    funcion = retorno_logaritmico if logaritmicos else retorno_simple
    return [funcion(a, b) for a, b in zip(precios, precios[1:])]


def retornos_calendario(precios, calendario, logaritmicos=False):
    """Dict fecha->precio; calendario de sesiones confirmado; no saltea huecos."""
    f = retorno_logaritmico if logaritmicos else retorno_simple
    salida = {}
    for a, b in zip(calendario, calendario[1:]):
        pa, pb = precios.get(a), precios.get(b)
        salida[b] = None if pa is None or pb is None else f(pa, pb)
    return salida


def varianza(x, grados=1):
    x = _serie(x, grados + 1)
    if grados < 0:
        raise ValueError('grados inválidos')
    m = media(x)
    return math.fsum((v-m)**2 for v in x)/(len(x)-grados)


def volatilidad(x, periodos=252, grados=1):
    if periodos <= 0:
        raise ValueError('periodos inválidos')
    return math.sqrt(varianza(x, grados)*periodos)


def covarianza(x, y, grados=1):
    x, y = _serie(x, grados+1), _serie(y, grados+1)
    if len(x) != len(y) or grados < 0:
        raise ValueError('series no alineadas')
    mx, my = media(x), media(y)
    return math.fsum((a-mx)*(b-my) for a,b in zip(x,y))/(len(x)-grados)


def correlacion(x, y):
    den = math.sqrt(varianza(x)*varianza(y))
    return covarianza(x,y)/den if den > 0 else None


def matriz_covarianzas(series):
    if not series:
        raise ValueError('sin series')
    if len({len(s) for s in series}) != 1:
        raise ValueError('series no alineadas')
    return [[covarianza(a,b) for b in series] for a in series]


def matriz_correlaciones(series):
    matriz_covarianzas(series)
    return [[correlacion(a,b) for b in series] for a in series]


def ewma(retornos_dados, lam=0.94, inicial=None):
    """Varianzas PREVIAS a cada retorno, y pronóstico siguiente al último.
    Convención Excel AJ3=r3²; AJ4 repite r3²; AJ5 usa r4².
    Sin inicial externa, el primer elemento es semilla ex post, no pronóstico real.
    """
    r = _serie(retornos_dados)
    if not 0 < lam < 1:
        raise ValueError('lambda fuera de (0,1)')
    v = r[0]**2 if inicial is None else inicial
    if v < 0 or not math.isfinite(v):
        raise ValueError('semilla inválida')
    previas = []
    for x in r:
        previas.append(v)
        v = lam*v+(1-lam)*x*x
    return {'previas': previas, 'siguiente': v}


def producto_matriz_vector(matriz, vector):
    n = len(vector)
    if len(matriz) != n or any(len(f) != n for f in matriz):
        raise ValueError('dimensiones incompatibles')
    _serie(vector)
    return [math.fsum(a*b for a,b in zip(_serie(f,n),vector)) for f in matriz]


def riesgo_cartera(pesos, matriz, periodos=252):
    if periodos <= 0:
        raise ValueError('periodos inválidos')
    pesos = _serie(pesos)
    cholesky_semidefinida(matriz)
    mw = producto_matriz_vector(matriz,pesos)
    v = math.fsum(w*x for w,x in zip(pesos,mw))
    if v < -1e-12:
        raise ValueError('varianza negativa: matriz inválida')
    v = max(0.,v)
    s = math.sqrt(v)
    marginal = [x/s for x in mw] if s else [None]*len(pesos)
    componentes = [w*x for w,x in zip(pesos,marginal)] if s else [None]*len(pesos)
    sigmas = [math.sqrt(matriz[i][i]) for i in range(len(pesos))]
    suma = math.fsum(abs(w)*s_i for w,s_i in zip(pesos,sigmas))
    return {'varianza_diaria':v,'vol_diaria':s,'vol_anual':s*math.sqrt(periodos),
            'marginal_diaria':marginal,'componentes_diarias':componentes,
            'componentes_anuales':[x*math.sqrt(periodos) for x in componentes] if s else [None]*len(pesos),
            'fracciones_riesgo':[x/s for x in componentes] if s else [None]*len(pesos),
            'ratio_diversificacion':suma/s if s else None,
            'reduccion_diversificacion':1-s/suma if suma else None}


def concentracion(pesos):
    w = _serie(pesos)
    if any(x < 0 for x in w) or abs(sum(w)-1) > 1e-9:
        raise ValueError('HHI requiere pesos largos que sumen uno')
    h = sum(x*x for x in w)
    return {'herfindahl':h,'numero_efectivo':1/h,'peso_maximo':max(w)}


def retornos_cartera(series, pesos):
    if len(series) != len(pesos):
        raise ValueError('dimensiones incompatibles')
    matriz_covarianzas(series)
    return [sum(w*r for w,r in zip(pesos,fila)) for fila in zip(*series)]


def cobertura(pesos, disponibles):
    if len(pesos) != len(disponibles) or any(w < 0 for w in pesos) or abs(sum(pesos)-1)>1e-9:
        raise ValueError('pesos largos de cartera completa requeridos')
    c = sum(w for w,ok in zip(pesos,disponibles) if ok)
    return {'peso_cubierto':c,'peso_excluido':1-c,
            'pesos_condicionales':[w/c if ok and c else 0 for w,ok in zip(pesos,disponibles)]}


def _beta_incompleta(a,b,x):
    """Beta regularizada; fracción continua de Lentz para Student."""
    def fraccion(a,b,x):
        qab,qap,qam=a+b,a+1,a-1
        c=1.;d=1-qab*x/qap
        if abs(d)<1e-300:d=1e-300
        d=1/d;h=d
        for m in range(1,301):
            aa=m*(b-m)*x/((qam+2*m)*(a+2*m))
            d=1+aa*d;c=1+aa/c
            if abs(d)<1e-300:d=1e-300
            if abs(c)<1e-300:c=1e-300
            d=1/d;h*=d*c
            aa=-(a+m)*(qab+m)*x/((a+2*m)*(qap+2*m))
            d=1+aa*d;c=1+aa/c
            if abs(d)<1e-300:d=1e-300
            if abs(c)<1e-300:c=1e-300
            d=1/d;delta=d*c;h*=delta
            if abs(delta-1)<3e-14:return h
        raise ValueError('beta incompleta no converge')
    if x<=0:return 0.
    if x>=1:return 1.
    bt=math.exp(math.lgamma(a+b)-math.lgamma(a)-math.lgamma(b)+a*math.log(x)+b*math.log1p(-x))
    return bt*fraccion(a,b,x)/a if x<(a+1)/(a+b+2) else 1-bt*fraccion(b,a,1-x)/b


def p_student_bilateral(t, grados):
    if grados <= 0:raise ValueError('grados inválidos')
    return _beta_incompleta(grados/2,0.5,grados/(grados+t*t))


def cuantil_student(probabilidad, grados):
    if not 0.5 < probabilidad < 1 or grados<=0:raise ValueError('cuantil inválido')
    bajo,alto=0.,1.
    while p_student_bilateral(alto,grados)>2*(1-probabilidad):alto*=2
    for _ in range(100):
        medio=(bajo+alto)/2
        if p_student_bilateral(medio,grados)>2*(1-probabilidad):bajo=medio
        else:alto=medio
    return (bajo+alto)/2


def modelo_indice(activo, mercado, libre=None, beta_nula=1., confianza=0.95):
    a,m = _serie(activo,3),_serie(mercado,3)
    rf = [0.]*len(a) if libre is None else _serie(libre,3)
    if len(a)!=len(m) or len(a)!=len(rf):raise ValueError('series no alineadas')
    y=[v-f for v,f in zip(a,rf)];x=[v-f for v,f in zip(m,rf)]
    vx=varianza(x)
    if vx<=0:raise ValueError('mercado constante')
    b=covarianza(x,y)/vx;alfa=media(y)-b*media(x)
    e=[yi-alfa-b*xi for xi,yi in zip(x,y)]
    sse=sum(v*v for v in e);sst=sum((v-media(y))**2 for v in y)
    ve=sse/(len(x)-1);s2=sse/(len(x)-2)
    se=math.sqrt(s2/((len(x)-1)*vx))
    sea=math.sqrt(s2*(1/len(x)+media(x)**2/((len(x)-1)*vx)))
    crit=cuantil_student((1+confianza)/2,len(x)-2)
    def prueba(valor,error):
        if error==0:return {'t':None,'p':0. if valor else 1.}
        t=valor/error;return {'t':t,'p':p_student_bilateral(t,len(x)-2)}
    return {'beta':b,'alfa_periodica':alfa,'r_cuadrado':1-sse/sst if sst else None,
            'var_sistematica':b*b*vx,'var_especifica_muestral':ve,
            'var_residual_regresion':s2,'error_beta':se,'error_alfa':sea,
            'intervalo_beta':[b-crit*se,b+crit*se],
            'prueba_beta':prueba(b-beta_nula,se),'prueba_alfa':prueba(alfa,sea),
            'grados':len(x)-2}


def cuantiles_perdidas(perdidas, confianza=0.95, metodo='inversa'):
    """VaR pérdida firmada; ES integral de la cola, con peso fraccional."""
    x=sorted(_serie(perdidas));n=len(x)
    if not 0<confianza<1:raise ValueError('confianza inválida')
    if metodo=='inversa':v=x[max(0,math.ceil(n*confianza)-1)]
    elif metodo=='lineal':
        h=(n-1)*confianza;i=int(h);f=h-i
        v=x[i]*(1-f)+x[min(i+1,n-1)]*f
    else:raise ValueError('método desconocido')
    cola=(1-confianza)*n;k=int(math.floor(cola+1e-12));f=cola-k
    if f<0:f=0.
    es=(sum(x[n-k:])+(f*x[n-k-1] if f else 0))/cola
    return {'var':v,'es':es,'observaciones_cola':cola}


def var_es_historico(r, confianza=0.95, valor=1., metodo='inversa'):
    return cuantiles_perdidas([-valor*x for x in _serie(r)],confianza,metodo)


def var_es_normal(mu, sigma, confianza=0.95, horizonte=1, valor=1.):
    if sigma<0 or horizonte<=0 or not 0<confianza<1 or valor<0:raise ValueError('parámetros inválidos')
    z=NormalDist().inv_cdf(confianza);s=sigma*math.sqrt(horizonte);m=mu*horizonte
    return {'var':valor*(z*s-m),'es':valor*(s*math.exp(-z*z/2)/math.sqrt(2*math.pi)/(1-confianza)-m)}


def momentos(x):
    x=_serie(x,3);m=media(x);v=varianza(x,0)
    if v==0:raise ValueError('serie constante')
    asim=media([(a-m)**3 for a in x])/v**1.5
    exceso=media([(a-m)**4 for a in x])/v**2-3
    jb=len(x)/6*(asim**2+exceso**2/4)
    return {'asimetria':asim,'curtosis_exceso':exceso,'jarque_bera':jb,'p_asintotico':math.exp(-jb/2)}


def var_cornish_fisher(r, confianza=0.95, valor=1.):
    x=_serie(r,4);mom=momentos(x);s=mom['asimetria'];k=mom['curtosis_exceso']
    z=NormalDist().inv_cdf(1-confianza)
    zc=z+(z*z-1)*s/6+(z**3-3*z)*k/24-(2*z**3-5*z)*s*s/36
    return -valor*(media(x)+zc*volatilidad(x,1))


def retornos_horizonte(r, horizonte=10):
    x=_serie(r,horizonte)
    if not isinstance(horizonte,int) or horizonte<1:raise ValueError('horizonte inválido')
    return [math.prod(1+v for v in x[i:i+horizonte])-1 for i in range(len(x)-horizonte+1)]


def cholesky_semidefinida(matriz, tolerancia=1e-12):
    n=len(matriz)
    if n==0 or any(len(f)!=n for f in matriz):raise ValueError('matriz no cuadrada')
    l=[[0.]*n for _ in range(n)]
    for i in range(n):
        for j in range(i+1):
            if abs(matriz[i][j]-matriz[j][i])>tolerancia:raise ValueError('matriz no simétrica')
            s=matriz[i][j]-sum(l[i][k]*l[j][k] for k in range(j))
            if i==j:
                if s < -tolerancia:raise ValueError('matriz no semidefinida positiva')
                l[i][j]=math.sqrt(max(0.,s))
            elif l[j][j]>0:l[i][j]=s/l[j][j]
            elif abs(s)>tolerancia:raise ValueError('matriz no semidefinida positiva')
    return l


def monte_carlo(medias, matriz, pesos, confianza=0.95, horizonte=1, simulaciones=10000, semilla=1729, valor=1.):
    """Normal multivariada ADITIVA de retornos/P&L; no motor de precios."""
    if horizonte<=0 or simulaciones<2 or len(medias)!=len(pesos):raise ValueError('parámetros inválidos')
    l=cholesky_semidefinida(matriz);n=len(pesos)
    if len(l)!=n:raise ValueError('dimensiones incompatibles')
    generador=random.Random(semilla);perdidas=[]
    for _ in range(simulaciones):
        z=[generador.gauss(0,1) for _ in range(n)]
        r=[medias[i]*horizonte+math.sqrt(horizonte)*sum(l[i][j]*z[j] for j in range(i+1)) for i in range(n)]
        perdidas.append(-valor*sum(w*x for w,x in zip(pesos,r)))
    return cuantiles_perdidas(perdidas,confianza)


def drawdown(riqueza):
    x=_serie(riqueza)
    if any(v<=0 for v in x):raise ValueError('riqueza no positiva')
    pico=x[0];ip=0;peor=0.;inicio=fin=0;serie=[]
    for i,v in enumerate(x):
        if v>pico:pico=v;ip=i
        d=v/pico-1;serie.append(d)
        if d<peor:peor=d;inicio=ip;fin=i
    recuperacion=next((i for i in range(fin+1,len(x)) if x[i]>=x[inicio]),None) if peor<0 else 0
    return {'maxima_caida':-peor,'serie_firmada':serie,'pico':inicio,'valle':fin,'recuperacion':recuperacion}


def riqueza(r, inicial=1.):
    x=_serie(r);v=inicial;sal=[v]
    for a in x:
        if a<=-1:raise ValueError('riqueza no positiva')
        v*=1+a;sal.append(v)
    return sal


def tasa_periodica(efectiva_anual, periodos=252):
    if efectiva_anual<=-1 or periodos<=0:raise ValueError('tasa fuera de dominio')
    return math.expm1(math.log1p(efectiva_anual)/periodos)


def tasa_nominal_a_efectiva(nominal, frecuencia):
    if frecuencia<=0 or nominal/frecuencia<=-1:raise ValueError('tasa fuera de dominio')
    return (1+nominal/frecuencia)**frecuencia-1


def desempeno(r, libre, mercado, objetivo=None, periodos=252):
    r,rf,m=_serie(r,3),_serie(libre,3),_serie(mercado,3)
    b=rf if objetivo is None else _serie(objetivo,3)
    if len({len(r),len(rf),len(m),len(b)})!=1:raise ValueError('series no alineadas')
    exceso=[a-f for a,f in zip(r,rf)];activo=[a-f for a,f in zip(r,m)]
    desvio=volatilidad(r,1);te=volatilidad(activo,1)
    negativos=[min(0,a-f) for a,f in zip(r,b)]
    dd=math.sqrt(media([x*x for x in negativos]))
    nneg=sum(x<0 for x in negativos)
    cond=math.sqrt(sum(x*x for x in negativos)/nneg) if nneg else None
    reg=modelo_indice(r,m,rf);beta=reg['beta'];smerc=volatilidad(m,periodos)
    sharpe=media(exceso)*math.sqrt(periodos)/desvio if desvio else None
    return {'sharpe':sharpe,'sortino':media([a-f for a,f in zip(r,b)])*math.sqrt(periodos)/dd if dd else None,
            'sortino_condicional_bodie':media([a-f for a,f in zip(r,b)])*math.sqrt(periodos)/cond if cond else None,
            'desvio_baja_diario':dd,'tracking_error_anual':te*math.sqrt(periodos),
            'treynor_anual':media(exceso)*periodos/beta if beta>0 else None,
            'jensen_anual':reg['alfa_periodica']*periodos,
            'informacion':media(activo)*math.sqrt(periodos)/te if te else None,
            'appraisal':reg['alfa_periodica']*math.sqrt(periodos)/math.sqrt(reg['var_especifica_muestral']) if reg['var_especifica_muestral']>0 else None,
            'm_cuadrado':media(rf)*periodos+sharpe*smerc if sharpe is not None else None,
            'm_cuadrado_diferencial':media(rf)*periodos+sharpe*smerc-media(m)*periodos if sharpe is not None else None}


def bono(flujos, tir, frecuencia=2):
    """flujos=(tiempo en años, importe), precio sucio; TIR nominal anual."""
    if frecuencia<=0 or 1+tir/frecuencia<=0 or not flujos:raise ValueError('bono fuera de dominio')
    if any(t<=0 or c<0 or not math.isfinite(t+c) for t,c in flujos):raise ValueError('flujos inválidos')
    base=1+tir/frecuencia
    pv=[c/base**(frecuencia*t) for t,c in flujos];p=sum(pv)
    if p<=0:raise ValueError('precio no positivo')
    d=sum(t*v for (t,c),v in zip(flujos,pv))/p
    conv=sum(t*(t+1/frecuencia)*v for (t,c),v in zip(flujos,pv))/(p*base*base)
    return {'precio_sucio':p,'macaulay_anios':d,'modificada_anios':d/base,'convexidad_anios2':conv,'dv01_por_nominal_flujos':p*d/base*0.0001}


def flujos_fijos(nominal, cupon, anios, frecuencia=2):
    n=round(anios*frecuencia)
    if n<1 or abs(n-anios*frecuencia)>1e-9:raise ValueError('períodos no enteros')
    return [(i/frecuencia,nominal*cupon/frecuencia+(nominal if i==n else 0)) for i in range(1,n+1)]


def cambio_precio(duration, convexidad, cambio_tasa):
    return -duration*cambio_tasa+0.5*convexidad*cambio_tasa*cambio_tasa


def escenarios_bono(flujos, tir, frecuencia=2, cambios=(-0.02,-0.01,-0.005,0.005,0.01,0.02)):
    base=bono(flujos,tir,frecuencia);p=base['precio_sucio'];sal=[]
    for dy in cambios:
        nuevo=bono(flujos,tir+dy,frecuencia)['precio_sucio']
        aprox=cambio_precio(base['modificada_anios'],base['convexidad_anios2'],dy)
        sal.append({'cambio_pb':dy*10000,'precio_exacto':nuevo,'retorno_exacto':nuevo/p-1,'retorno_aproximado':aprox,'error_aprox':aprox-(nuevo/p-1)})
    return sal


def sensibilidad_efectiva(precio, precio_baja, precio_suba, choque=0.0001):
    if precio<=0 or choque<=0:raise ValueError('sensibilidad inválida')
    return {'duration':(precio_baja-precio_suba)/(2*precio*choque),
            'convexidad':(precio_baja+precio_suba-2*precio)/(precio*choque*choque),
            'dv01':(precio_baja-precio_suba)/(2*choque)*0.0001}


def sensibilidades_cartera(valores, duraciones, convexidades):
    if len({len(valores),len(duraciones),len(convexidades)})!=1:raise ValueError('dimensiones incompatibles')
    v=sum(_serie(valores));_serie(duraciones);_serie(convexidades)
    if v<=0:raise ValueError('valor inválido')
    return {'duration':sum(x*d for x,d in zip(valores,duraciones))/v,
            'convexidad':sum(x*c for x,c in zip(valores,convexidades))/v,
            'dv01':sum(x*d for x,d in zip(valores,duraciones))*0.0001}


def precio_curva(flujos, tasas_efectivas):
    if len(flujos)!=len(tasas_efectivas):raise ValueError('dimensiones incompatibles')
    return sum(c/(1+y)**t for (t,c),y in zip(flujos,tasas_efectivas))


def perdida_crediticia(exposicion, probabilidad, recupero):
    if exposicion<0 or not 0<=probabilidad<=1 or not 0<=recupero<=1:raise ValueError('crédito inválido')
    return exposicion*probabilidad*(1-recupero)


def spread_pb(tir, referencia):
    return (tir-referencia)*10000


def valor_reinvertido(flujos, horizonte, tasa_reinversion):
    if any(t>horizonte for t,c in flujos) or tasa_reinversion<=-1:raise ValueError('reinversión inválida')
    return sum(c*(1+tasa_reinversion)**(horizonte-t) for t,c in flujos)


def precio_cedear(subyacente, ccl, ratio):
    if min(subyacente,ccl,ratio)<=0:raise ValueError('CEDEAR fuera de dominio')
    return subyacente*ccl/ratio


def retorno_factores(retorno_subyacente, retorno_cambio, ratio_anterior=1., ratio_actual=1.):
    if min(ratio_anterior,ratio_actual)<=0:raise ValueError('ratio inválido')
    return (1+retorno_subyacente)*(1+retorno_cambio)*ratio_anterior/ratio_actual-1


def convertir_moneda(valor_pesos, cambio):
    if cambio<=0:raise ValueError('tipo de cambio inválido')
    return valor_pesos/cambio


def retorno_real(nominal, inflacion):
    if inflacion<=-1:raise ValueError('inflación fuera de dominio')
    return (1+nominal)/(1+inflacion)-1


def capital_ajustado(nominal, indice_actual, indice_base):
    if min(indice_actual,indice_base)<=0:raise ValueError('índice inválido')
    return nominal*indice_actual/indice_base


def liquidez(valor_posicion, montos_diarios, participacion=0.1):
    x=_serie(montos_diarios)
    if any(a<0 for a in x) or valor_posicion<0 or not 0<participacion<=1:raise ValueError('liquidez inválida')
    prom=media(x)
    return {'monto_medio':prom,'dias_liquidacion':valor_posicion/(participacion*prom) if prom>0 else None,
            'fraccion_sesiones_sin_negocio':sum(a==0 for a in x)/len(x)}


def resolver_lineal(matriz, vector):
    n=len(vector);a=[list(f)+[v] for f,v in zip(matriz,vector)]
    if len(a)!=n or any(len(f)!=n+1 for f in a):raise ValueError('dimensiones incompatibles')
    for i in range(n):
        k=max(range(i,n),key=lambda j:abs(a[j][i]));a[i],a[k]=a[k],a[i]
        if abs(a[i][i])<1e-14:raise ValueError('modelo singular')
        p=a[i][i];a[i]=[v/p for v in a[i]]
        for j in range(n):
            if j!=i:
                f=a[j][i];a[j]=[x-f*y for x,y in zip(a[j],a[i])]
    return [f[-1] for f in a]


def modelo_factores(activo, factores):
    y=_serie(activo);factores=[_serie(f) for f in factores]
    if any(len(f)!=len(y) for f in factores) or len(y)<=len(factores)+1:raise ValueError('muestra insuficiente')
    x=[[1.]+list(f) for f in zip(*factores)];k=len(factores)+1
    xx=[[sum(f[i]*f[j] for f in x) for j in range(k)] for i in range(k)]
    xy=[sum(f[i]*v for f,v in zip(x,y)) for i in range(k)]
    coef=resolver_lineal(xx,xy);e=[v-sum(a*b for a,b in zip(coef,f)) for f,v in zip(x,y)]
    return {'alfa':coef[0],'betas':coef[1:],'var_residual':sum(a*a for a in e)/(len(y)-k)}


def var_es_cola_bodie(inferiores, n_total, probabilidad_cola=0.05):
    """Cuantil tipo n*p de Bodie p.139, sin completar la muestra desconocida.
    inferiores: suficientes retornos menores ordenables; NO inventa el resto.
    """
    x=sorted(_serie(inferiores));h=n_total*probabilidad_cola;k=int(math.floor(h));f=h-k
    if not 0<probabilidad_cola<1 or h<1 or len(x)<k+(1 if f else 0):raise ValueError('cola insuficiente')
    q=x[k-1]*(1-f)+(x[k]*f if f else 0)
    es=-(sum(x[:k])+(f*x[k] if f else 0))/h
    return {'var':-q,'es':es}


def retorno_anual_compuesto(r, periodos=252):
    x=_serie(r)
    if any(a<=-1 for a in x) or periodos<=0:raise ValueError('retorno compuesto fuera de dominio')
    return math.expm1(sum(math.log1p(a) for a in x)*periodos/len(x))


def retorno_capm(libre, beta, retorno_mercado):
    return libre+beta*(retorno_mercado-libre)


def beta_cartera(pesos, betas):
    if len(pesos)!=len(betas):raise ValueError('dimensiones incompatibles')
    return sum(w*b for w,b in zip(_serie(pesos),_serie(betas)))


def varianza_factores(betas, matriz_factores, var_especifica):
    if var_especifica<0:raise ValueError('varianza específica negativa')
    mb=producto_matriz_vector(matriz_factores,betas)
    return sum(b*x for b,x in zip(betas,mb))+var_especifica


def cupon_variable(capital, tasa_nominal, dias, base=365, margen=0.):
    if capital<0 or dias<0 or base<=0:raise ValueError('cupón fuera de dominio')
    return capital*(tasa_nominal+margen)*dias/base
