# Riesgo de la cartera (Etapa 14)

**Pedido de Felipe del 18/11/2026:** medir el riesgo de cada activo y de la cartera completa con lo que se
enseña en Administración de Carteras, y tenerlo como una salida más de la herramienta.

La metodología completa, con fórmulas, citas y comprobaciones, está en
[RIESGO_METODOLOGIA.md](RIESGO_METODOLOGIA.md). Este documento fija **qué** se implementa en esta etapa y con qué
criterios. Donde no dice otra cosa, vale la metodología. Las funciones de referencia comprobadas están en
`tools/riesgo/riesgo_ref.py`: copiá o adaptá lo que necesites a `src/cartera/`, pero `src` no puede importar
`tools`.

Es una salida **interna del asesor**. No va en el informe del cliente.

## Fuentes

| Dato | Fuente | Para qué |
|---|---|---|
| Posiciones y valuaciones | bloque `datos-cartera` del último `dashboard.html` | pesos y montos |
| Precios diarios | `https://data912.com/historical/{cedears\|stocks\|bonds}/{ticker}` | retornos |
| Dólar CCL y calendario | históricos de `AL30` y `AL30C` | moneda de medición y ruedas |
| Mercado | histórico del CEDEAR `SPY` | beta |
| Duration, convexidad, TIR, pagos | último `iamc/cierres/AAAA-MM-DD.json` con fecha ≤ la del dashboard, bloques `informes.titulos_publicos.rows` e `informes.on.rows` | renta fija |

El histórico de data912 es una lista de `{"date", "o", "h", "l", "c", "v", "dr", "sa"}`. Se usa `c` (cierre,
sin ajuste por dividendos) solo en las ruedas con `v > 0`. Si no tiene el ticker responde **HTTP 200** con
`{"Error": "..."}`. No tiene letras ni ON: los `endpoint` `arg_notes` y `arg_corp` no se consultan.

No se usa ninguna otra fuente. En particular, **no** se completa un CEDEAR sin historia con su subyacente: queda
pendiente de una decisión de Felipe.

## Criterios (los de la metodología)

| Parámetro | Valor |
|---|---|
| Moneda de medición | USD CCL. CCL de cada rueda = cierre `AL30` / cierre `AL30C` |
| Ruedas | fechas con negocio en `AL30` **y** en `AL30C` |
| Retorno | simple, en USD CCL: `(P_t / CCL_t) / (P_{t−1} / CCL_{t−1}) − 1`, solo entre ruedas consecutivas con precio en las dos |
| Ventana | últimas 252 ruedas (retornos); mínimo 126 válidos y cobertura ≥ 95 % |
| Volatilidad | desvío muestral (n − 1) × √252 |
| EWMA | λ = 0,94 sobre retornos logarítmicos del último tramo sin huecos de la ventana, semilla = primer retorno al cuadrado; pronóstico siguiente al último retorno, anualizado con √252; mínimo 60 retornos |
| VaR y ES | normales, 95 %, una rueda, media cero, sobre el valor en USD CCL |
| Beta | regresión contra el `SPY` en las mismas ruedas, mínimo 126 pares |
| VaR histórico de la cartera | últimas 504 ruedas, mínimo 250 filas comunes, cuantil empírico inverso y ES fraccional |
| Escenarios de tasa | −200, −100, +100, +200 pb con `dm` y `cx` de IAMC: `V × (−dm × Δy + ½ × cx × Δy²)` |

Los parámetros viven en `PARAMETROS` y se copian en la salida.

## Retornos que no se usan

Un retorno se reemplaza por `None` (y no entra en ningún cálculo) cuando:

1. Falta el precio de alguna de las dos ruedas o la rueda no tuvo negocio.
2. **Pago de un bono, letra u ON:** la rueda está entre 1 día después y 6 días antes de una fecha de pago
   contractual. Las fechas pasadas salen de `pc` (próximo pago) restando el período de `fc` (`Mensual`,
   `Trimestral`, `Semestral`, `Anual`) hasta antes de `fe` (emisión) o de la primera rueda. Así el corte de cupón
   no aparece como una pérdida.
3. **Evento conocido:** está en `EVENTOS_CONOCIDOS`. Por ahora, `("SPY", "2026-05-29")`: cambio de ratio 3:1.
4. **Salto sin evento:** el precio en pesos se movió más de 25 % en una rueda. Puede ser un cambio de ratio o un
   error de la fuente; no se corrige: se excluye.

Los casos 2 a 4 quedan listados en `excluidos` del activo (solo los de la ventana), con fecha y motivo.
**Nunca** se rellena un hueco, se arrastra un precio ni se usa un cero.

## Estado de la historia de cada activo

| `estado` | Cuándo | `motivo` |
|---|---|---|
| `suficiente` | ≥ 126 retornos válidos y cobertura ≥ 95 % en la ventana | `None` |
| `insuficiente` | no llega a eso | `"N retornos válidos de M ruedas"` |
| `sin_serie` | data912 respondió `{"Error": ...}` u otro formato | `"data912 no tiene su historia"` |
| `sin_serie` | no se pudo consultar (error de red sin copia guardada) | `"no se pudo consultar data912"` |
| `sin_fuente` | `endpoint` sin histórico (`arg_notes`, `arg_corp`, otros) | `"data912 no tiene histórico de letras ni ON"` |

Solo los `suficiente` tienen volatilidad, EWMA, VaR, beta y entran a la cartera.

## Cartera

- **Pesos:** valuación / suma de valuaciones de las posiciones **con** valuación. Una posición sin valuación
  queda afuera de todo, con un aviso `"TICKER: sin valuación; queda fuera de pesos y cálculos."`. El efectivo no
  entra (el dashboard no lo trae completo).
- **Concentración:** Herfindahl, número efectivo y peso máximo, sobre todas las posiciones valuadas, tengan o no
  historia.
- **Riesgo estadístico:** solo con los activos `suficiente`. `cobertura_patrimonial` = suma de sus pesos. Se usan
  las ruedas de la ventana donde **todos** tienen retorno, con los pesos normalizados (peso / cobertura). Con menos
  de 126 filas comunes, `estado = "sin_dato"` y el motivo. El valor medido es `total × cobertura / CCL`.
- **Lo que queda afuera no tiene riesgo cero.** La salida lista cada excluido con su peso y su motivo.
- **Contribuciones:** fracción de la volatilidad de la cartera que explica cada activo (puede ser negativa), de
  mayor a menor.
- **Peor día:** el menor retorno de la cartera medida en esas filas, con su fecha.

## Renta fija

Para cada bono, letra u ON con fila en el cierre IAMC y `dm` no nulo: `familia`, `dm`, `cx`, `tir` (= `ytm`) y
`dv01_ars = valor × dm × 0,0001`. Sin fila o sin `dm`: aviso `"TICKER: sin duration en el cierre IAMC."`. Sin
cierre: un aviso general.

Familia, en este orden de prioridad: `aj == "CER"` → `CER`; `aj == "DL"` → `dólar linked`; `idx == "TAMAR"` →
`TAMAR`; `me == "USD"` → `USD`; si no, `ARS tasa fija`. Cada familia se agrega por separado (cada una tiene su
propia curva), en el orden `USD`, `ARS tasa fija`, `CER`, `TAMAR`, `dólar linked`. `dm` y `cx` de la familia son
promedios ponderados por valor. Los escenarios suman los de cada título.

La duration de CER, TAMAR y dólar linked mide la tasa real o el margen, **no** el riesgo del índice: el reporte lo
tiene que decir.

## Reporte HTML

`riesgo_html(modelo)` devuelve un documento completo, sin recursos externos (nada de `http`, CDN ni fuentes
remotas), en español, con números en formato argentino (`1.234,5`; porcentajes con un decimal y coma).
Secciones, en este orden:

1. Encabezado: cliente, fecha del tablero, fecha de los datos, moneda y CCL, y los parámetros principales.
2. **Cómo leerlo:** qué son volatilidad, VaR, ES, contribución, beta y cobertura, en una línea cada uno, y que lo
   excluido no tiene riesgo cero.
3. Cartera: patrimonio medido, volatilidad, VaR y ES (USD), beta (R²), diversificación, peor día, VaR histórico;
   concentración. Con `sin_dato`, el motivo.
4. Quién explica el riesgo: ticker, peso dentro de lo medido y fracción del riesgo.
5. Por especie: ticker, tipo, peso, volatilidad, EWMA, beta (R²), VaR 95 % USD y, si no tiene historia
   suficiente, el motivo. Con los excluidos por evento o pago.
6. Renta fija: una fila por familia con valor, duration, DV01 y los escenarios, más la advertencia sobre
   CER, TAMAR y dólar linked.
7. Fuera del cálculo y avisos.

Un dato faltante se muestra como **"sin dato"**, nunca como `0`.

## Comando

```bash
python3 -m cartera --datos RUTA riesgo --cliente SLUG [--sin-red]
```

1. Lee `clientes/SLUG/dashboard.html` (bloque `datos-cartera`).
2. Busca el último cierre IAMC con fecha ≤ la del dashboard. Si no hay, sigue sin renta fija.
3. Pide los históricos de `historicos_necesarios(datos)` a través de una **copia guardada** en
   `cache/data912/historicos/SEGMENTO_TICKER.json` = `{"consultado_en": ISO 8601, "respuesta": ...}`:
   - Sin `--sin-red`: si la copia es de hoy (hora de Argentina), se usa; si no, se consulta y se reemplaza. Si la
     consulta falla y hay copia vieja, se usa la copia con un aviso; si no hay copia, el valor es `None`.
   - Con `--sin-red`: solo las copias; lo que falta es `None`.
   - Entre consultas, una pausa de 0,5 s (límite de data912: 120 por minuto).
4. Escribe `clientes/SLUG/riesgo/riesgo-AAAA-MM-DD.json` (el modelo, con `json.dump(..., ensure_ascii=False)`) y
   `riesgo-AAAA-MM-DD.html`, con la fecha del dashboard. Si existen, los reemplaza.
5. Imprime las rutas, la cobertura, la volatilidad y el VaR, y un renglón por aviso.

Errores (código distinto de cero, mensaje, **sin escribir nada**): cliente sin dashboard, bloque inválido, o sin
historia de `AL30`/`AL30C`.

## Fuera de esta etapa

- Mostrarlo en el dashboard o en el informe del cliente.
- Completar CEDEARs sin historia con el subyacente.
- Sharpe, Sortino, Treynor y Jensen: falta elegir la tasa libre de riesgo.
- Riesgo del índice (CER, TAMAR, oficial), crédito y liquidez.
