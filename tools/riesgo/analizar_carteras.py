"""Análisis de riesgo de las carteras reales con la metodología RIESGO.md (Codex, 18/11/2026).

Uso: python3 analizar.py <carpeta privado> <carpeta salida>
No escribe en privado. Usa riesgo_ref.py (referencia comprobada) copiado junto a este archivo.
"""
import datetime as dt
import json
import math
import os
import re
import sys
import time
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import riesgo_ref as R  # noqa: E402

PRIVADO, SALIDA = sys.argv[1], sys.argv[2]
CACHE = os.path.join(SALIDA, 'cache_data912')
os.makedirs(CACHE, exist_ok=True)
CLIENTES = ['fcl', 'mdm', 'sc']
CIERRE_IAMC = os.path.join(PRIVADO, 'iamc', 'cierres', '2026-11-17.json')

VENTANA = 252          # sesiones para vol, covarianzas, beta, VaR normal
MINIMO = 126           # retornos válidos mínimos
COBERTURA_MIN = 0.95
VENTANA_COLA = 504     # VaR/ES histórico
MINIMO_COLA = 250
CONF = 0.95
SALTO = 0.25           # |retorno| mayor: posible evento corporativo no reconciliado
EVENTOS_CONOCIDOS = {('SPY', '2026-05-29'): 'cambio de ratio 3:1'}
SEGMENTO = {'arg_cedears': 'cedears', 'arg_stocks': 'stocks', 'arg_bonds': 'bonds'}
MESES_FC = {'Mensual': 1, 'Trimestral': 3, 'Semestral': 6, 'Anual': 12}


def historico(segmento, ticker):
    ruta = os.path.join(CACHE, f'{segmento}_{ticker}.json')
    if os.path.exists(ruta):
        return json.load(open(ruta))
    url = f'https://data912.com/historical/{segmento}/{ticker}'
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'cartera-riesgo/1.0'})
        with urllib.request.urlopen(req, timeout=30) as r:
            d = json.load(r)
    except Exception as e:  # sin fuente: sin dato
        d = {'Error': f'{type(e).__name__}: {e}'}
    json.dump(d, open(ruta, 'w'))
    time.sleep(0.6)
    return d


def cierres(d):
    """fecha -> cierre, solo ruedas con negocio (v>0)."""
    if not isinstance(d, list):
        return None
    return {x['date']: x['c'] for x in d if x.get('c') and x.get('v', 0) > 0}


def dashboard(slug):
    h = open(os.path.join(PRIVADO, 'clientes', slug, 'dashboard.html')).read()
    return json.loads(re.search(r'<script[^>]*id="datos-cartera"[^>]*>(.*?)</script>', h, re.S).group(1))


def restar_meses(fecha, meses):
    a, m = fecha.year, fecha.month - meses
    while m <= 0:
        m += 12
        a -= 1
    dia = min(fecha.day, [31, 29 if a % 4 == 0 else 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31][m - 1])
    return dt.date(a, m, dia)


def pagos_pasados(fila, desde):
    """Fechas contractuales de pago anteriores, desde el próximo cupón hacia atrás."""
    if not fila or not fila.get('pc') or fila.get('fc') not in MESES_FC:
        return []
    paso = MESES_FC[fila['fc']]
    f = dt.date.fromisoformat(fila['pc'])
    emision = dt.date.fromisoformat(fila['fe']) if fila.get('fe') else desde
    out = []
    k = 1
    while True:
        p = restar_meses(f, paso * k)
        if p < max(desde, emision):
            break
        out.append(p)
        k += 1
    return out


# ---------- datos comunes ----------
iamc = json.load(open(CIERRE_IAMC))
filas = {}
for g in ('titulos_publicos', 'on'):
    for r in iamc['informes'][g]['rows']:
        filas[r['tk']] = r
embi = iamc['informes']['titulos_publicos'].get('embi')

al30, al30c = cierres(historico('bonds', 'AL30')), cierres(historico('bonds', 'AL30C'))
sesiones = sorted(set(al30) & set(al30c))          # ruedas confirmadas por los dos
ccl = {f: al30[f] / al30c[f] for f in sesiones}
spy = cierres(historico('cedears', 'SPY'))


def serie_usd(ticker, precios, tipo):
    """Retornos simples en USD CCL por sesión (None = sin dato) y eventos excluidos."""
    excl = []
    pagos = []
    if tipo in ('bono', 'on', 'letra'):
        pagos = pagos_pasados(filas.get(ticker), dt.date.fromisoformat(sesiones[0]))
    out = {}
    for a, b in zip(sesiones, sesiones[1:]):
        if a not in precios or b not in precios:
            out[b] = None
            continue
        r = (precios[b] / ccl[b]) / (precios[a] / ccl[a]) - 1
        fb = dt.date.fromisoformat(b)
        pago = next((p for p in pagos if -1 <= (p - fb).days <= 6), None)
        if pago:
            out[b] = None
            excl.append((b, f'rueda cercana al pago del {pago.isoformat()}'))
            continue
        if (ticker, b) in EVENTOS_CONOCIDOS:
            out[b] = None
            excl.append((b, EVENTOS_CONOCIDOS[(ticker, b)]))
            continue
        ra = precios[b] / precios[a] - 1
        if abs(ra) > SALTO:
            out[b] = None
            excl.append((b, f'salto de {ra:+.0%} en pesos sin evento reconciliado'))
            continue
        out[b] = r
    return out, excl


ret_spy, excl_spy = serie_usd('SPY', spy, 'cedear')


def ventana(ret, n):
    fechas = sorted(ret)[-n:]
    return fechas, [ret[f] for f in fechas]


def ultimo_tramo(valores):
    tramo = []
    for v in valores:
        tramo = [] if v is None else tramo + [v]
    return tramo


def analizar_activo(p):
    tk, tipo = p['ticker'], p['tipo']
    res = {'ticker': tk, 'tipo': tipo, 'valor_ars': p['valuacion'], 'estado_precio': p['estado']}
    fila = filas.get(tk)
    if fila:
        res['iamc'] = {k: fila.get(k) for k in ('ytm', 'dm', 'cx', 'adtv', 'est', 'aj', 'idx', 'me', 'fv', 'ley')}
    seg = SEGMENTO.get(p['endpoint'])
    if not seg:
        res['historia'] = 'sin dato: data912 no tiene histórico de letras ni ON'
        return res, None
    d = historico(seg, tk)
    precios = cierres(d)
    if precios is None:
        res['historia'] = f"sin dato: data912 respondió {str(d)[:80]}"
        return res, None
    ret, excl = serie_usd(tk, precios, tipo)
    res['excluidos'] = excl
    fechas, vals = ventana(ret, VENTANA)
    validos = [v for v in vals if v is not None]
    res['n'] = len(validos)
    res['cobertura_temporal'] = len(validos) / len(vals)
    if len(validos) < MINIMO or res['cobertura_temporal'] < COBERTURA_MIN:
        res['historia'] = (f'insuficiente: {len(validos)} retornos válidos de {len(vals)} ruedas '
                           f'({res["cobertura_temporal"]:.0%})')
        return res, ret
    res['historia'] = 'suficiente'
    res['vol_anual'] = R.volatilidad(validos)
    tramo = ultimo_tramo([math.log(1 + v) if v is not None else None for v in vals])
    if len(tramo) >= 60:
        e = R.ewma(tramo)
        res['ewma_anual'] = math.sqrt(252 * e['siguiente'])
        res['ewma_n'] = len(tramo)
    valor_usd = p['valuacion'] / ccl[sesiones[-1]]
    res['valor_usd'] = valor_usd
    vn = R.var_es_normal(0, R.volatilidad(validos, 1), CONF, 1, valor_usd)
    res['var95_usd'], res['es95_usd'] = vn['var'], vn['es']
    pares = [(ret[f], ret_spy.get(f)) for f in fechas if ret[f] is not None and ret_spy.get(f) is not None]
    if len(pares) >= MINIMO:
        m = R.modelo_indice([a for a, _ in pares], [b for _, b in pares])
        res['beta_spy'] = m['beta']
        res['r2_spy'] = m['r_cuadrado']
        res['beta_ic95'] = m['intervalo_beta']
        res['beta_n'] = len(pares)
    return res, ret


def escenarios_tasa(bonos):
    """P&L aproximado D+C por familia de curva con dm/cx de IAMC."""
    familias = {}
    for b in bonos:
        f = b.get('iamc') or {}
        if f.get('dm') is None:
            continue
        aj = f.get('aj') or 'No'
        fam = {'CER': 'CER (tasa real)', 'DL': 'dólar linked'}.get(aj)
        if not fam:
            fam = 'TAMAR' if f.get('idx') == 'TAMAR' else ('USD' if f.get('me') == 'USD' else 'ARS tasa fija')
        familias.setdefault(fam, []).append(b)
    out = {}
    for fam, lista in familias.items():
        v = sum(b['valor_ars'] for b in lista)
        dm = sum(b['valor_ars'] * b['iamc']['dm'] for b in lista) / v
        cx = sum(b['valor_ars'] * (b['iamc']['cx'] or 0) for b in lista) / v
        esc = {}
        for pb in (-200, -100, 100, 200):
            dy = pb / 10000
            esc[pb] = sum(b['valor_ars'] * (-b['iamc']['dm'] * dy + 0.5 * (b['iamc']['cx'] or 0) * dy * dy)
                          for b in lista)
        out[fam] = {'tickers': [b['ticker'] for b in lista], 'valor_ars': v, 'dm': dm, 'cx': cx,
                    'dv01_ars': v * dm * 0.0001, 'escenarios_ars': esc}
    return out


# ---------- aproximación con subyacente (rotulada; no es historia local) ----------
SUBYACENTE = {'PETR3': 'PBR', 'BA.C': 'BAC', 'BRKB': 'BRK-B'}


def yahoo(simbolo):
    ruta = os.path.join(CACHE, f'yahoo_{simbolo}.json')
    if not os.path.exists(ruta):
        url = f'https://query1.finance.yahoo.com/v8/finance/chart/{simbolo}?range=3y&interval=1d'
        try:
            req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
            with urllib.request.urlopen(req, timeout=30) as r:
                d = json.load(r)
        except Exception as e:
            d = {'Error': f'{type(e).__name__}: {e}'}
        json.dump(d, open(ruta, 'w'))
        time.sleep(0.6)
    d = json.load(open(ruta))
    try:
        res = d['chart']['result'][0]
        fechas = [dt.datetime.utcfromtimestamp(t).date().isoformat() for t in res['timestamp']]
        adj = res['indicators']['adjclose'][0]['adjclose']
        return {f: p for f, p in zip(fechas, adj) if p}
    except Exception:
        return None


def serie_subyacente(ticker):
    """Retornos USD del subyacente (cierre ajustado por dividendos) entre ruedas argentinas consecutivas
    que también tienen cierre en EE.UU. Si alguna punta falta, sin dato."""
    precios = yahoo(SUBYACENTE.get(ticker, ticker))
    if not precios:
        return None
    out = {}
    for a, b in zip(sesiones, sesiones[1:]):
        out[b] = precios[b] / precios[a] - 1 if a in precios and b in precios else None
    return out


def analizar_cliente(slug):
    d = dashboard(slug)
    pos = [p for p in d['posiciones'] if p.get('valuacion')]
    sin_valor = [p['ticker'] for p in d['posiciones'] if not p.get('valuacion')]
    total = sum(p['valuacion'] for p in pos)
    activos, series = [], {}
    for p in pos:
        a, r = analizar_activo(p)
        a['peso'] = p['valuacion'] / total
        activos.append(a)
        if a.get('historia') == 'suficiente':
            series[p['ticker']] = r
    pesos = {a['ticker']: a['peso'] for a in activos}
    conc = R.concentracion([a['peso'] for a in activos])
    # cartera cubierta: intersección completa de la ventana
    inc = list(series)
    cobertura = sum(pesos[t] for t in inc)
    fechas = sorted(set.intersection(*[set(series[t]) for t in inc]))[-VENTANA:]
    filas_ok = [f for f in fechas if all(series[t][f] is not None for t in inc)]
    res = {'cliente': slug, 'fecha_tablero': d['generado_en'], 'total_ars': total,
           'ccl': ccl[sesiones[-1]], 'fecha_ccl': sesiones[-1], 'sin_valor': sin_valor,
           'efectivo': d.get('efectivo'), 'activos': activos,
           'hhi': conc, 'cobertura_patrimonial': cobertura, 'incluidos': inc,
           'excluidos': [(a['ticker'], a['peso'], a.get('historia')) for a in activos if a['ticker'] not in inc]}
    res['filas_comunes'] = len(filas_ok)
    res['filas_ventana'] = len(fechas)
    if len(filas_ok) >= MINIMO:
        mat = R.matriz_covarianzas([[series[t][f] for f in filas_ok] for t in inc])
        w = [pesos[t] for t in inc]
        wn = [x / cobertura for x in w]
        rc = R.riesgo_cartera(wn, mat)
        res['vol_anual_cubierta'] = rc['vol_anual']
        res['ratio_diversificacion'] = rc['ratio_diversificacion']
        res['reduccion_diversificacion'] = rc['reduccion_diversificacion']
        res['contribuciones'] = sorted(zip(inc, rc['fracciones_riesgo'], rc['componentes_anuales']),
                                       key=lambda x: -x[1])
        v_cub = total * cobertura / ccl[sesiones[-1]]
        res['valor_cubierto_usd'] = v_cub
        vn = R.var_es_normal(0, rc['vol_diaria'], CONF, 1, v_cub)
        res['var95_normal_usd'], res['es95_normal_usd'] = vn['var'], vn['es']
        corr = R.matriz_correlaciones([[series[t][f] for f in filas_ok] for t in inc])
        pares = [(inc[i], inc[j], corr[i][j]) for i in range(len(inc)) for j in range(i + 1, len(inc))
                 if corr[i][j] is not None]
        res['corr_media'] = sum(c for _, _, c in pares) / len(pares) if pares else None
        res['corr_max'] = sorted(pares, key=lambda x: -x[2])[:3]
        rp = [sum(series[t][f] * x for t, x in zip(inc, wn)) for f in filas_ok]
        pm = [(r_, ret_spy.get(f)) for r_, f in zip(rp, filas_ok) if ret_spy.get(f) is not None]
        if len(pm) >= MINIMO:
            m = R.modelo_indice([a for a, _ in pm], [b for _, b in pm])
            res['beta_cartera_spy'], res['r2_cartera_spy'] = m['beta'], m['r_cuadrado']
        res['peor_dia_cubierta'] = min(zip(rp, filas_ok))
    # VaR/ES histórico con ventana larga
    fl = sorted(set.intersection(*[set(series[t]) for t in inc]))[-VENTANA_COLA:]
    fl_ok = [f for f in fl if all(series[t][f] is not None for t in inc)]
    res['filas_cola'] = len(fl_ok)
    if len(fl_ok) >= MINIMO_COLA:
        wn = [pesos[t] / cobertura for t in inc]
        rp = [sum(series[t][f] * x for t, x in zip(inc, wn)) for f in fl_ok]
        h = R.var_es_historico(rp, CONF, res.get('valor_cubierto_usd', total * cobertura / ccl[sesiones[-1]]))
        res['var95_hist_usd'], res['es95_hist_usd'] = h['var'], h['es']
    bonos = [a for a in activos if a['tipo'] in ('bono', 'on', 'letra')]
    res['renta_fija'] = escenarios_tasa(bonos)
    # versión aproximada: CEDEARs sin historia local con su subyacente en USD
    aprox = dict(series)
    sustitutos = []
    for a in activos:
        if a['tipo'] == 'cedear' and a['ticker'] not in series:
            s = serie_subyacente(a['ticker'])
            if s:
                f, v = ventana(s, VENTANA)
                val = [x for x in v if x is not None]
                if len(val) >= MINIMO and len(val) / len(v) >= COBERTURA_MIN:
                    aprox[a['ticker']] = s
                    a['aprox_vol_anual'] = R.volatilidad(val)
                    spy_us = serie_subyacente('SPY')
                    pares = [(s[x], spy_us.get(x)) for x in f if s[x] is not None and spy_us.get(x) is not None]
                    if len(pares) >= MINIMO:
                        a['aprox_beta_spy'] = R.modelo_indice([p for p, _ in pares], [q for _, q in pares])['beta']
                    sustitutos.append((a['ticker'], SUBYACENTE.get(a['ticker'], a['ticker'])))
    if sustitutos:
        inc2 = list(aprox)
        cob2 = sum(pesos[t] for t in inc2)
        f2 = sorted(set.intersection(*[set(aprox[t]) for t in inc2]))[-VENTANA:]
        ok2 = [f for f in f2 if all(aprox[t][f] is not None for t in inc2)]
        if len(ok2) >= MINIMO:
            mat = R.matriz_covarianzas([[aprox[t][f] for f in ok2] for t in inc2])
            wn = [pesos[t] / cob2 for t in inc2]
            rc = R.riesgo_cartera(wn, mat)
            v2 = total * cob2 / ccl[sesiones[-1]]
            vn = R.var_es_normal(0, rc['vol_diaria'], CONF, 1, v2)
            rp = [sum(aprox[t][f] * x for t, x in zip(inc2, wn)) for f in ok2]
            pm = [(r_, ret_spy.get(f)) for r_, f in zip(rp, ok2) if ret_spy.get(f) is not None]
            res['aproximada'] = {
                'sustitutos': sustitutos, 'cobertura_patrimonial': cob2, 'filas': len(ok2),
                'vol_anual': rc['vol_anual'], 'valor_usd': v2, 'var95_usd': vn['var'], 'es95_usd': vn['es'],
                'ratio_diversificacion': rc['ratio_diversificacion'],
                'contribuciones': sorted(zip(inc2, rc['fracciones_riesgo']), key=lambda x: -x[1]),
                'beta_spy': R.modelo_indice([a for a, _ in pm], [b for _, b in pm])['beta'] if len(pm) >= MINIMO else None,
                'peor_dia': min(zip(rp, ok2))}
    return res


if __name__ == '__main__':
    salida = {'generado_en': dt.datetime.now().isoformat(timespec='seconds'),
              'cierre_iamc': '2026-11-17', 'embi': embi,
              'sesiones': [sesiones[0], sesiones[-1], len(sesiones)],
              'spy_excluidos': excl_spy, 'clientes': {}}
    for c in CLIENTES:
        salida['clientes'][c] = analizar_cliente(c)
    json.dump(salida, open(os.path.join(SALIDA, 'riesgo.json'), 'w'), ensure_ascii=False, indent=1, default=str)
    print('ok', os.path.join(SALIDA, 'riesgo.json'))
