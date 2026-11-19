"""Arma el informe interno en Markdown a partir de salida/riesgo.json."""
import json
import sys

d = json.load(open(sys.argv[1]))
NOMBRE = {'fcl': 'Felipe (fcl)', 'mdm': 'Mariano (mdm)', 'sc': 'Sofía (sc)'}


def pct(x, dec=1):
    return '—' if x is None else f'{100 * x:.{dec}f} %'.replace('.', ',')


def num(x, dec=0):
    if x is None:
        return '—'
    s = f'{x:,.{dec}f}'
    return s.replace(',', 'X').replace('.', ',').replace('X', '.')


L = []
L.append('# Análisis de riesgo de las carteras — 18/11/2026\n')
L.append('Uso interno del asesor. Metodología: `codex/docs/RIESGO_METODOLOGIA.md` (Codex, a partir de la bibliografía de '
         'Administración de Carteras; revisada y comprobada por Claude). Posiciones y valuaciones de los tableros '
         'del 18/11 a las 11 h; historia de precios de data912 hasta el 17/11; duration y convexidad del cierre '
         'IAMC/BYMA del 17/11.\n')
L.append('## Cómo leerlo\n')
L.append(f"- **Moneda:** todo el riesgo de mercado se mide en **dólares CCL** (AL30/AL30C del día). CCL del "
         f"{d['clientes']['fcl']['fecha_ccl']}: {num(d['clientes']['fcl']['ccl'], 2)}.")
L.append('- **Volatilidad anual:** cuánto suele moverse el valor en un año, para arriba o para abajo (desvío de '
         'retornos diarios de las últimas 252 ruedas × √252).')
L.append('- **VaR 95 % a un día:** pérdida que, según el modelo normal, se supera en uno de cada veinte días. '
         '**ES 95 %:** pérdida promedio de esos días malos. No son la pérdida máxima.')
L.append('- **Contribución al riesgo:** qué parte de la volatilidad de la cartera explica cada posición. Puede '
         'ser muy distinta de su peso.')
L.append('- **Beta:** cuánto se mueve contra el S&P 500 (1 = igual que el índice). Con R² bajo, la beta dice poco.')
L.append('- **Cobertura:** qué parte del patrimonio tiene historia suficiente para entrar al cálculo. **Lo que '
         'queda afuera no tiene riesgo cero: no se pudo medir.**')
L.append('- **Versión estricta** = solo historia local. **Versión aproximada** = además, los CEDEARs sin historia '
         'local toman la de su subyacente en dólares (Yahoo Finance, ajustado por dividendos). La metodología no '
         'permite presentar la aproximada como historia del CEDEAR: sirve para dimensionar.')
L.append('- **Bonos:** se miden por sensibilidad a la tasa (duration modificada y convexidad de IAMC), con escenarios '
         'de suba y baja de TIR. Es un escenario, no una probabilidad.')
L.append('- **Efectivo:** los tableros no tienen el saldo cargado, así que no entra. Los porcentajes son sobre las posiciones.\n')

for slug, r in d['clientes'].items():
    L.append(f"## {NOMBRE[slug]}\n")
    usd = r['total_ars'] / r['ccl']
    conc = r['hhi']
    L.append(f"Posiciones: **$ {num(r['total_ars'])}** (USD CCL {num(usd)}), {len(r['activos'])} especies. "
             f"Concentración: la mayor posición pesa {pct(conc['peso_maximo'])}; equivale a "
             f"{num(conc['numero_efectivo'], 1)} posiciones iguales (Herfindahl {num(conc['herfindahl'], 3)}).\n")
    L.append('| | Estricta | Aproximada |')
    L.append('|---|---:|---:|')
    a = r.get('aproximada') or {}
    L.append(f"| Patrimonio medido | {pct(r['cobertura_patrimonial'])} | {pct(a.get('cobertura_patrimonial')) if a else 'igual'} |")
    L.append(f"| Volatilidad anual | {pct(r.get('vol_anual_cubierta'))} | {pct(a.get('vol_anual')) if a else '—'} |")
    L.append(f"| VaR 95 % un día (USD) | {num(r.get('var95_normal_usd'))} | {num(a.get('var95_usd')) if a else '—'} |")
    L.append(f"| ES 95 % un día (USD) | {num(r.get('es95_normal_usd'))} | {num(a.get('es95_usd')) if a else '—'} |")
    L.append(f"| Beta contra S&P 500 | {num(r.get('beta_cartera_spy'), 2)} | {num(a.get('beta_spy'), 2) if a else '—'} |")
    L.append(f"| Diversificación (riesgo sin / con correlaciones) | {num(r.get('ratio_diversificacion'), 2)} | "
             f"{num(a.get('ratio_diversificacion'), 2) if a else '—'} |")
    pe = r.get('peor_dia_cubierta')
    L.append(f"| Peor día del último año (parte medida) | {pct(pe[0]) + ' el ' + pe[1] if pe else '—'} | "
             f"{pct(a['peor_dia'][0]) + ' el ' + a['peor_dia'][1] if a else '—'} |")
    L.append('')
    L.append(f"VaR y ES sobre el valor medido ({pct(r['cobertura_patrimonial'])} en la estricta). VaR histórico: "
             f"**sin dato**: hay {r['filas_cola']} ruedas comunes y el mínimo es 250 (data912 tiene un solo año de "
             f"varios CEDEARs).\n")
    contrib = a.get('contribuciones') if a else [(t, f) for t, f, _ in r.get('contribuciones', [])]
    pesos = {x['ticker']: x['peso'] for x in r['activos']}
    tot_cob = a.get('cobertura_patrimonial') if a else r['cobertura_patrimonial']
    L.append(f"**Quién explica el riesgo** ({'aproximada' if a else 'estricta'}), peso dentro de lo medido "
             f"contra parte del riesgo:\n")
    L.append('| Especie | Peso | Riesgo |')
    L.append('|---|---:|---:|')
    for t, f in contrib[:6]:
        L.append(f'| {t} | {pct(pesos[t] / tot_cob)} | {pct(f)} |')
    L.append('')
    L.append('**Por especie** (USD CCL, últimas 252 ruedas):\n')
    L.append('| Especie | Tipo | Peso | Vol. anual | EWMA | Beta S&P (R²) | VaR 95 % 1d USD | Nota |')
    L.append('|---|---|---:|---:|---:|---|---:|---|')
    for x in sorted(r['activos'], key=lambda x: -x['peso']):
        nota = ''
        if x.get('historia') != 'suficiente':
            nota = x.get('historia', '')
            if 'aprox_vol_anual' in x:
                nota = f"sin historia local; subyacente {dict(a['sustitutos']).get(x['ticker'], x['ticker'])}: vol {pct(x['aprox_vol_anual'])}, beta {num(x.get('aprox_beta_spy'), 2)}"
            elif 'Nahh' in nota:
                nota = 'data912 no tiene su historia'
        beta = f"{num(x.get('beta_spy'), 2)} ({num(x.get('r2_spy'), 2)})" if x.get('beta_spy') is not None else '—'
        L.append(f"| {x['ticker']} | {x['tipo']} | {pct(x['peso'])} | {pct(x.get('vol_anual'))} | "
                 f"{pct(x.get('ewma_anual'))} | {beta} | {num(x.get('var95_usd'))} | {nota} |")
    L.append('')
    if r['renta_fija']:
        L.append('**Renta fija: sensibilidad a la tasa** (aproximación duration + convexidad, en pesos; '
                 'cada familia con su propia curva):\n')
        L.append('| Familia | Especies | Valor $ | Duration mod. | DV01 $ | −100 pb | +100 pb | +200 pb |')
        L.append('|---|---|---:|---:|---:|---:|---:|---:|')
        for fam, f in r['renta_fija'].items():
            e = f['escenarios_ars']
            L.append(f"| {fam} | {', '.join(f['tickers'])} | {num(f['valor_ars'])} | {num(f['dm'], 2)} | "
                     f"{num(f['dv01_ars'])} | {num(e['-100'])} | {num(e['100'])} | {num(e['200'])} |")
        L.append('')
    L.append(f"Fuera del cálculo estadístico, en la versión {'aproximada' if a else 'estricta'}: " + ', '.join(
        f"{t} ({pct(pesos[t])})" for t in pesos if t not in [c for c, _ in contrib]) + '.\n')

L.append('## Límites de este análisis\n')
L.append('- Pesos de hoy aplicados a la historia del último año: es el riesgo de la cartera **actual**, no el que '
         'el cliente tuvo en el año.')
L.append('- Bonos con historia en data912 (AE38, AL29): retorno de precio sin sumar cupones; se excluyen las ruedas '
         'cercanas a cada pago contractual para que el corte de cupón no parezca una pérdida.')
L.append('- Se excluyeron saltos de más de 25 % en un día sin evento conocido (cambios de ratio de CEDEARs, '
         'errores de la fuente). El cambio de ratio de SPY del 29/05/2026 está identificado.')
L.append('- La duration de CER, TAMAR y dólar linked mide la tasa real o el margen, no el riesgo del índice '
         '(inflación, TAMAR, oficial). Esos riesgos no están cuantificados acá.')
L.append('- No se calcularon Sharpe, Sortino ni Treynor: falta elegir la tasa libre de riesgo.')
L.append('- La versión aproximada mezcla cierres de EE.UU. (16 h de Nueva York) con cierres locales (17 h de Buenos '
         'Aires): las correlaciones entre ambos grupos pueden quedar subestimadas.')
L.append('- Riesgo de crédito (default, reestructuración) y riesgo país: no hay probabilidades de default '
         f"cargadas. EMBI del cierre IAMC: {num(d['embi'])} pb.")
print('\n'.join(L))
