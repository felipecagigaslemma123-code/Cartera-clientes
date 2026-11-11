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

Si un lote pasa de `estimado` a `pendiente`, también se emite una advertencia sin impedir
la corrección, porque suele indicar que se usó un Excel viejo y se perdió una estimación.

### Control de precios de la etapa 2

Cuando haya cotización actual y precio de compra conocido, si el precio del lote es
más de cinco veces mayor o menor que el actual, se muestra una advertencia con el
ticker y ambos precios por posible error de unidad o moneda:

```text
precio_compra > precio_actual × 5  o  precio_compra < precio_actual / 5
```

Los límites exactos de cinco veces no disparan el aviso. Sin ambos precios no se
hace esta comparación. La advertencia no bloquea la carga, no modifica ningún
cálculo y el lote conserva su origen.

## Día cero y patrimonio inicial

El día cero es el punto de partida del resultado completo. Guarda una foto autosuficiente:
cantidades, precios, dólar MEP y efectivo. Los costos no intervienen: un costo pendiente
no impide fijarlo, y corregir costos después no lo altera.

```text
patrimonio_inicial_ars = valuación de las posiciones + efectivo ARS + efectivo USD × MEP
```

- **Efectivo negativo:** es válido. Un saldo deudor existe y resta del patrimonio.
- **Efectivo en cero:** es un dato. No es lo mismo que un saldo faltante (`null`).
- **Saldo faltante:** el patrimonio inicial es "sin dato" y se informa qué falta. Nunca se
  completa con cero.
- **Dólar MEP:** solo es necesario si el efectivo en dólares es distinto de cero.
- **Cauciones abiertas:** el asesor las incluye en el efectivo en pesos, por su capital. La
  tenencia del broker puede mostrarlas así, mientras el saldo del extracto no las incluye.
- **Efectivo tardío:** el día cero se puede fijar sin efectivo y cargarlo después. Cargarlo
  no vuelve a tomar precios.
- **Fecha del efectivo:** no puede ser futura. Si falta o difiere de la del día cero, se advierte
  sin bloquear, porque el saldo podría no corresponder a ese día.
- **Volver a fijar:** con `--forzar`, la versión anterior siempre queda en el historial. Si no se
  recibe efectivo nuevo, se conserva el ya cargado: volver a tomar precios no borra un saldo.

Los precios del día cero son el último operado al momento de fijarlo. Conviene hacerlo con
el mercado cerrado, para que sean los de cierre, pero no es obligatorio.

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

## Movimientos

Se cargan a mano, con el comando `movimiento`, después del día cero. La base importada no cambia:
las tenencias actuales salen de aplicar los movimientos sobre ella.

| Tipo | Especie | Cantidad | Efectivo | Para el resultado integral |
|---|---|---|---|---|
| `compra` | obligatoria | obligatoria | baja | intercambio |
| `venta` | obligatoria | obligatoria | sube | intercambio |
| `renta` | obligatoria | no | sube | se desglosa |
| `amortizacion` | obligatoria | no | sube | se desglosa |
| `dividendo` | obligatoria | no | sube | se desglosa |
| `deposito` | no | no | sube | aporte |
| `retiro` | no | no | baja | retiro |
| `gasto` | opcional | no | baja | se desglosa |
| `compra_usd` | no | no | sube USD, baja ARS | intercambio |
| `venta_usd` | no | no | baja USD, sube ARS | intercambio |

- **Fecha:** la de concertación. Tiene que ser posterior al día cero, no futura en Argentina. Hasta
  que liquide, el saldo del broker puede diferir del calculado.
- **Importe:** positivo, neto y con gastos adentro, en la moneda del movimiento. No se recalcula con
  precio × cantidad.
- **Moneda:** `ARS` o `USD`; sin indicarla es `ARS`. En USD, `tc` es obligatorio: los pesos que vale
  cada dólar ese día. En ARS, `tc` no se admite. `compra_usd` y `venta_usd` son siempre en USD: el
  importe son los dólares y `tc` el cambio efectivo, de modo que `importe × tc` sean los pesos.
- **Valor en pesos:** `importe`, o `importe × tc` en USD. Se usa para el costo de un lote y para
  aportes, retiros, rentas, dividendos, gastos y ventas.
- **Amortización parcial:** se carga como `amortizacion` (etapa 9). No cambia la cantidad ni los lotes:
  los nominales se conservan y baja el valor residual. Ver `docs/FLUJO_FONDOS.md`.
- **Vencimiento (pago final):** se carga como `venta` de todos los nominales, con una nota. Cambios de ratio, canjes y
  cambios de ticker están fuera de alcance: no los aproximes.

### Tenencias y lotes

- Una compra agrega un lote `extracto`, con `costo` igual al valor en pesos y `precio` en `None`.
- Una venta consume lotes por FIFO. Los lotes sin fecha son los más viejos, y se respeta el orden de
  carga dentro de una misma fecha. Se rechaza vender más de lo que hay en lotes.
- La cantidad de una posición es la base más compras menos ventas. En cero, deja de ser una posición.
- La primera compra de una especie que no está en la base necesita `tipo_activo`. Su unidad sale de
  la tabla de unidades y su nombre es el ticker. Si la especie ya existe, un `tipo_activo` distinto
  se rechaza.
- `amortizacion` solo admite especies conocidas de tipo `bono`, `on` o `letra`.
- `renta`, `dividendo` y `gasto` solo admiten especies conocidas: de la base o compradas antes.

### Resultado realizado

Una venta genera un `Realizado`, con su costo por lotes y `origen_costo`: `extracto`, `estimado`,
`mixto` o `incompleto`. Si consumió un lote pendiente, costo y resultado son "sin dato", nunca un
resultado parcial. El total realizado suma solo lo que tiene costo, e indica cuántas ventas quedan
afuera. Es informativo: **no se suma al resultado integral**, que ya lo incluye en el efectivo.

### Efectivo calculado y conciliación

El efectivo calculado es el del día cero más los movimientos, por moneda. Puede ser negativo. Un saldo
inicial `null` deja esa moneda "sin dato", nunca cero.

`efectivo.json` es el control: se compara con el saldo calculado **a su `fecha`**, moneda por moneda.
Tolerancia: 1 peso y 0,01 dólar. La diferencia es informado − calculado.

| Estado | Cuándo |
|---|---|
| `concilia` | Se comparó al menos una moneda y ninguna supera la tolerancia. |
| `no_concilia` | Alguna moneda supera la tolerancia. |
| `sin_control` | No hay fecha, es anterior al día cero o no se pudo comparar ninguna moneda. |

El resultado integral usa siempre el saldo calculado. Si no concilia, se sigue mostrando, con un aviso
visible y la diferencia: probablemente falte cargar un movimiento.

### Resultado integral en pesos

```text
patrimonio_final = valuación actual + efectivo ARS + efectivo USD × MEP actual
resultado_integral = patrimonio_final − patrimonio_inicial − aportes + retiros
```

No depende de los costos, así que las estimaciones no lo afectan. Si falta algo, `total` es "sin dato"
y se lista qué falta: día cero, datos de `patrimonio_inicial`, efectivo, precio de una posición actual,
o MEP actual con saldo en dólares distinto de cero. Con saldo en dólares cero, el MEP no hace falta.
El resultado incluye la diferencia de cambio de los dólares. No se publica un porcentaje integral.

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
