# Dominio

## Unidad de cotización

| Tipo | Cotiza por | Cálculo |
|---|---|---|
| `cedear`, `accion` | unidad | cantidad × precio |
| `bono`, `on`, `letra` | cada 100 de valor nominal | cantidad × precio / 100 |

Confundir esto infla o achica una valuación 100 veces. El importador rechaza una
combinación de tipo y `cotiza_cada` que no coincida con esta tabla.

No deduzcas el tipo de activo a partir del ticker ni de la categoría del broker. Por
ejemplo, el broker lista algunos CEDEARs como "Acciones". El tipo viene del Excel.

## Costo

- Los costos de **extracto** son reales: importe neto pagado, con gastos adentro. Por
  eso costo / cantidad no es el precio de mercado de ese día.
- Los costos **estimados** salen de la fecha de compra y del precio de ese día. Son
  aproximaciones que el asesor corregirá; toda salida debe mostrarlos como estimados.
- Sin costo completo no se informa resultado de esa especie. Un costo parcial no se usa
  para calcular un resultado parcial.
- El importe de cada lote de extracto viene ya calculado: **no recalcules** el costo con
  precio × cantidad.

## Dos resultados

| Resultado | Fórmula | Depende de estimaciones |
|---|---|---|
| Desde la compra | valuación − costo | Sí, si hay costos estimados |
| Desde el día cero | valuación − valuación con el precio del día cero | No |

El resultado desde el día cero es el indicador principal de seguimiento.

El resultado en dólar MEP se calcula solo desde el día cero:

```text
resultado_usd = valuacion_hoy / mep_hoy − valuacion_dia_cero / mep_dia_cero
```

Valuación no es retorno total: rentas y dividendos cobrados no están en el precio. Se
registran como movimientos y se muestran aparte.

## Vencimientos

El vencimiento de cada especie viene de `instrumentos.json`. **No lo deduzcas del
ticker:** los prefijos no son una regla confiable.

## Alertas de niveles

Los niveles son **precios absolutos**, en la misma unidad en que cotiza la especie. Un
nivel `null` significa que no hay alerta de ese lado.

**Precio de referencia:** el `bid`, porque es a lo que se podría vender. Si no hay `bid`,
se usa `ultimo`, y si tampoco hay, la especie no se pudo chequear.

| Evento | Se dispara cuando |
|---|---|
| `take_profit` | referencia ≥ nivel |
| `stop_loss` | referencia ≤ nivel |

**Una vez por evento.** Después de dispararse, no se repite. Se rearma recién cuando la
referencia vuelve más de 1% adentro del nivel: por debajo de `nivel × 0,99` en take profit
o por encima de `nivel × 1,01` en stop loss. Si cambia el valor del nivel, también se
rearma.

**Si no se pudo chequear.** Una cotización que no está en estado `"vivo"` no dispara
niveles, porque el dato puede ser viejo. Se emite un único `sin_chequeo` por especie y por
día (`ticker` y `precio` pueden ser `None`; si fallan muchas, un evento por cada una).
Solo se consideran especies que tienen algún nivel definido.

## Horario de mercado

Lunes a viernes de 11:00 a 17:00, hora de Argentina (`America/Argentina/Buenos_Aires`),
con 11:00 incluido y 17:00 excluido. El comando `alertas` no evalúa niveles fuera de ese
horario, pero sí vencimientos. Los feriados no están contemplados en esta versión.

## Alertas de vencimiento

Para cada umbral (30, 15, 7 y 1 días), se avisa una vez cuando faltan esa cantidad de días
o menos, y solo el umbral más cercano alcanzado. Un umbral ya avisado no se repite. Una
especie ya vencida, o sin vencimiento, no genera evento.

## Dólar MEP

Referencia: el campo `mark` de `AL30` en `/live/mep`, y `ultimo` es ese valor en la
`Cotizacion`. Si no se puede obtener, el dashboard muestra los totales en dólares como
"sin dato".

## Formato

Importes al estilo argentino en las salidas: punto de miles, coma decimal.
