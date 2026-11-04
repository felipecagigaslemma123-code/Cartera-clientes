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

### Correcciones y fechas de compra

`actualizar-costos` permite corregir los lotes de la base sin perder versiones
anteriores. Conserva exactamente las posiciones, especies, tipos, unidades de
cotización y cantidades totales importadas. Los lotes, sus fechas, precios, costos,
orígenes y notas pueden cambiar, respetando las validaciones y la tolerancia de
cantidades de 0,5 por especie. La comparación de la cantidad total contra la base
es exacta: esa tolerancia no habilita cambiarla.

Una fecha de compra posterior a hoy, en `America/Argentina/Buenos_Aires`, es inválida
en `importar` y `actualizar-costos`. La fecha de hoy se acepta. El error identifica
la hoja `Lotes`, la fila y el ticker; se valida cualquier fecha de compra presente,
tanto en lotes de extracto como en estimados o pendientes.

La corrección muestra el costo y origen anterior y nuevo por especie modificada.
Si cambia el costo de un lote de extracto o pasa a otro origen, se emite una
advertencia clara sin impedir la corrección. Los lotes no tienen identificador
estable: se advierte de forma conservadora cuando no se pueden conservar los
extractos previos por su combinación de cantidad, fecha y costo. También se advierte
ante cambios simultáneos entre extractos y otros lotes que puedan ocultar una
reasignación de origen. Ese criterio conservador puede avisar ante ciertas ediciones
de notas ambiguas. Reordenar filas o cambiar únicamente una nota de extracto no
provoca esa advertencia. Las versiones completas quedan en el historial para revisar
la modificación.

### Control de precios previsto para la etapa 2

Cuando haya cotización actual y precio de compra conocido, si el precio del lote es
más de cinco veces mayor o menor que el actual, se muestra una advertencia con el
ticker y ambos precios por posible error de unidad o moneda:

```text
precio_compra > precio_actual × 5  o  precio_compra < precio_actual / 5
```

Los límites exactos de cinco veces no disparan el aviso. Sin ambos precios no se
hace esta comparación. La advertencia no bloquea la carga, no modifica ningún
cálculo y el lote conserva su origen. Este control no se implementa en la etapa 1;
su prueba se incorpora cuando se implemente la etapa 2.

## Resultados por posición y resultado completo

Los indicadores por posición se mantienen:

| Resultado | Fórmula | Depende de estimaciones |
|---|---|---|
| Desde la compra | valuación − costo | Sí, si hay costos estimados |
| Comparación de precios desde el día cero | valuación − valuación de la misma cantidad con el precio del día cero | No |

`resultado_posicion` calcula estos indicadores. La comparación de precios usa la
cantidad recibida y no incorpora compras, ventas, aportes ni cobros. No debe
presentarse como resultado integral cuando cambian las tenencias.

**Criterio aprobado por Felipe el 04/11/2026:** el objetivo principal es el resultado
completo de la cartera desde el día cero. En pesos:

```text
resultado_integral_ars = patrimonio_final − patrimonio_inicial − aportes + retiros
```

El patrimonio comprende las posiciones valuadas y el efectivo. El efectivo se muestra
siempre aparte de las posiciones, aunque sí interviene en esta conciliación. Las
compras y ventas intercambian posiciones y efectivo; no son aportes ni retiros. Las
rentas y dividendos aumentan el efectivo y se muestran desglosados, sin sumarlos otra
vez si ya están incluidos en el patrimonio final. Los importes netos de los movimientos
incluyen los gastos aplicables.

La base importada y sus versiones de costos se conservan; las tenencias posteriores
se reconstruyen aplicando movimientos sobre ella. Para el resultado integral hace
falta una referencia del día cero que conserve cantidades, precios y saldos de
efectivo. Si falta algún dato
necesario, se informa "sin dato" y qué falta; no se completa con ceros ni se presenta
una suma parcial como resultado completo.

La comparación estática en dólar MEP es:

```text
comparacion_usd = valuacion_hoy / mep_hoy − valuacion_dia_cero / mep_dia_cero
```

Solo es una comparación de valuaciones desde el día cero. Antes de implementar el
resultado integral en dólares, hay que especificar con Claude la conversión histórica
de aportes, retiros y demás flujos. La metodología de rentabilidad porcentual con
movimientos también queda pendiente de revisión; no se publica un porcentaje integral
hasta definirla. Estas ampliaciones corresponden a las etapas posteriores, no a la
etapa 1.

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
