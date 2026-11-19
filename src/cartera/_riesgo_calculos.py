"""Fórmulas puras de riesgo, adaptadas de tools/riesgo/riesgo_ref.py.

Referencia comprobada del 18/11/2026; convenciones y citas en
docs/RIESGO_METODOLOGIA.md. No completa observaciones ni realiza E/S.
"""

import math
from statistics import NormalDist


def _serie(x, minimo=1):
    x = list(x)
    if len(x) < minimo or any(v is None or not isinstance(v, (int, float)) or not math.isfinite(v) for v in x):
        raise ValueError('sin dato: serie insuficiente, faltante o no finita')
    return x


def media(x):
    x = _serie(x)
    return math.fsum(x) / len(x)


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
