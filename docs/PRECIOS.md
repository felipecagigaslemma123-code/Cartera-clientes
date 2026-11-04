# Fuente de precios: data912

Verificado el 04/11/2026. Gratuita y sin API key. Refresco de unos 20 segundos, límite de
120 pedidos por minuto.

**Es un servicio no oficial.** Su documentación se presenta como un proyecto educativo y
hobby que puede dejar de funcionar. Por eso la fuente queda aislada en `cartera.precios`:
cambiarla no debe tocar el resto del código.

## Paneles

Una sola llamada trae todo el panel. **Nunca pidas especie por especie.**

```text
GET https://data912.com/live/arg_cedears
GET https://data912.com/live/arg_stocks
GET https://data912.com/live/arg_bonds
GET https://data912.com/live/arg_notes
GET https://data912.com/live/arg_corp
```

Cada uno devuelve una lista:

```json
{"symbol": "AAA", "q_bid": 10.0, "px_bid": 1190.0, "px_ask": 1210.0, "q_ask": 5.0,
 "v": 1000.0, "q_op": 20.0, "c": 1200.0, "pct_change": 1.5}
```

`c` es el último operado, `pct_change` viene en puntos porcentuales: `1.5` es 1,5%.

## Dólar MEP

```text
GET https://data912.com/live/mep
```

```json
{"ticker": "AL30", "bid": 1500.0, "ask": 1502.0, "close": 1500.0, "mark": 1501.0,
 "panel": "bonds"}
```

## Historial

```text
GET https://data912.com/historical/cedears/{ticker}
GET https://data912.com/historical/stocks/{ticker}
GET https://data912.com/historical/bonds/{ticker}
```

No cubre todo: letras y obligaciones negociables no tienen endpoint, y hay CEDEARs sin
historial. Cuando no tiene un ticker, responde **HTTP 200** con `{"Error": "..."}`. Por eso
el gráfico del dashboard usa el `historial.csv` propio.

## Comportamiento requerido

**La API no informa la hora del último operado.** Lo único que se puede mostrar es la hora
de consulta; nunca la presentes como hora del último precio.

`ClientePrecios.obtener` funciona así:

1. Agrupa las posiciones por endpoint y llama **una sola vez** a cada uno que necesita.
2. Para cada posición:

| Situación | `estado` | `ultimo`, `bid`, `ask` | `consultado_en` |
|---|---|---|---|
| Está en el panel con `c` positivo | `vivo` | los del panel | ahora |
| Falló, falta o `c` es 0 o nulo, con caché | `cache` | los de la caché | el del dato guardado |
| Falló, falta o `c` es 0 o nulo, sin caché | `sin_dato` | `None` | ahora |

3. Un `bid` o `ask` de 0 se convierte en `None`.
4. Solo los datos `vivo` actualizan la caché en disco. La caché se guarda por ticker, en
   JSON, y una caché ilegible o inexistente se trata como vacía.
5. La falla de un endpoint no afecta a los demás.

**El navegador puede consultar la API desde un archivo local:** responde con
`access-control-allow-origin` para el origen `null`. Probá de todas formas el caso en que
falla, y usá los precios embebidos.

**Una especie con poco volumen** puede tener un último operado fuera de la punta. Por eso
las alertas usan `bid`.
