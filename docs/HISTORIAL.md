# Rendimiento realizado

Responde cuánto se ganó o se perdió con lo ya vendido y cobrado, sin contar el dinero que el cliente
puso o sacó. Es un cálculo aparte del resultado desde el día cero: no lo reemplaza ni se suma a él.

## Archivos, en la carpeta del cliente

```text
extractos/*.xlsx        cuentas corrientes del broker, en cualquier cantidad y con períodos superpuestos
ajustes_historial.csv   lo que no está en los extractos; opcional
cierres.json            especies cuyo pago final las cierra; opcional, lista de tickers
mep_diario.csv          fecha,mep; opcional, lo genera historial --actualizar-mep
realizado.csv           salida: una fila por venta o cierre
```

## Extractos

Primera hoja, encabezado exacto en la primera fila:

```text
Liquida, Operado, Comprobante, Numero, Cantidad, Especie, Precio, Importe, Saldo, Referencia
```

- **Moneda:** sale del título de la hoja. `DOLARES` indica USD, incluso `DOLARES CABLE`, que además se
  informa como cuenta `CABLE`. `PESOS` indica ARS. Si no se puede determinar, el archivo es inválido.
- **Fecha:** la de `Operado`.
- **Duplicados:** dos renglones iguales en `moneda`, `cuenta`, `Operado`, `Comprobante`, `Numero`, `Especie`
  e `Importe` son el mismo. El mismo `Numero` con otro importe no es un duplicado.
- **Saldo:** si dentro de un mismo archivo un `Saldo` no coincide con el anterior más el `Importe`, con
  tolerancia de 1, se agrega un aviso con archivo y fila. No frena el cálculo.

## Clasificación de cada renglón

| Comprobante | Clase | Tratamiento |
|---|---|---|
| `COMPRA NORMAL`, `COMPRA TRADING`, `COMPRA PARIDAD` | `compra` | Lote nuevo |
| `VENTA`, `VENTA TRADING` | `venta` | Consume lotes por FIFO |
| `RENTA Y AMORTIZ` de especie en `cierres.json` | `cierre` | Cierra la posición |
| `RENTA Y AMORTIZ` de otra especie | `renta` | Ingreso |
| `DIVIDENDOS` | `dividendo` | Ingreso, con su signo |
| `RETENCION` | `retencion` | Se muestra aparte, con su signo |
| `COMPRA CAUCION CONTADO` + `VENTA CAUCION TERMINO` | `caucion_colocada` | Ingreso: suma de las dos patas |
| `VENTA CAUCION CONTADO` + `COMPRA CAUCION TERMINO` | `caucion_tomada` | Costo: suma de las dos patas |
| `SUSCRIPCION FCI`, `LIQUIDACION RESCATE FCI` | `fci` | Suma de los importes |
| `CREDITO DERMERC-`, `N C ARANCELES` | `gastos` | Con su signo |
| `RECIBO DE COBRO` | `aporte` | Dinero del cliente, **no es ganancia** |
| `ORDEN DE PAGO` | `retiro` | Dinero del cliente, **no es ganancia** |
| `NOTA DE CREDITO U$S`, `NOTA DE DEBITOS U$S` con referencia `CONV CABLE A ME` | `conversion` | Traspaso interno, no cuenta |
| Cualquier otro | `sin_clasificar` | **No se suma.** Se lista completo para revisar |

Las patas de una caución se agrupan por moneda, clase y `Operado`, que es la misma fecha en las dos patas.
No se emparejan una a una, porque una pata de contado puede tener dos de término. Un grupo sin alguna de
las dos patas no se suma y genera un aviso con sus números, porque solo contiene capital.

## Orden y lotes

Se procesa por fecha. Dentro de un mismo día: primero compras, ajustes incluidos, y después ventas y
cierres, en orden de `Numero`. Los lotes se consumen por FIFO y los de la misma fecha, en orden de creación.

- **Compra:** origen `extracto`, costo igual al importe absoluto.
- **Venta sin lotes suficientes:** no es un error, porque puede faltar un extracto. El resultado es "sin
  dato", con la cantidad faltante en `cantidad_sin_lote`. Nunca se inventa un costo.
- **Cierre:** todos los pagos de esa especie en esa fecha forman un solo cierre, por toda la cantidad abierta.
  Sin lotes abiertos, resultado "sin dato".

## Ajustes

`ajustes_historial.csv` tiene las columnas de `movimientos.csv`. Admite `compra`, `venta`, `renta`,
`dividendo` y `gasto`; cualquier otro tipo es inválido.

Sirve para lo que los extractos no muestran: una compra en dólares sin extracto, una venta posterior
al último extracto y **la entrada de títulos desde otro broker**, que se carga como `compra` a su precio
del día de la transferencia. Sus lotes tienen origen `estimado`. Lo ganado antes de esa fecha en el otro
broker no se evalúa.

## Valor en pesos

Lo que está en ARS vale su importe. Lo que está en USD se muestra en dólares y se convierte con el MEP de
ese día, o `tc` en un ajuste. Sin MEP de ese día se usa el último anterior de hasta 5 días corridos; si no
hay, ese valor en pesos es "sin dato" y se agrega un aviso. Una venta con costo o importe sin valor en pesos
tiene resultado "sin dato".

`historial --actualizar-mep` guarda `mep_diario.csv` a partir de `/historical/bonds/AL30` y
`/historical/bonds/AL30D`: cierre de AL30 dividido por cierre de AL30D, en las fechas que tengan los dos.

## Resultado

```text
total conocido = realizado con costo + dividendos + retenciones + rentas
               + caución colocada + caución tomada + FCI + gastos
```

- **Aportes y retiros:** se informan, nunca entran en el total.
- **Sin dato:** el total suma solo lo conocido e indica cuántas ventas y valores quedaron afuera. Nunca se
  presenta como completo si falta algo. `sin_clasificar` también se indica.
- **Origen:** el realizado se desglosa en `extracto` y en lo que incluye estimaciones.
- **Monedas:** cada ingreso se informa en ARS, en USD y en su equivalente en pesos.
- **Sin porcentaje:** no se publica una rentabilidad porcentual.

## Cartera derivada

Los lotes abiertos se comparan por especie contra las posiciones de la base. Se informan las diferencias de
cantidad, con tolerancia de 0,5. Esta etapa **no modifica la base** ni el cálculo del resultado desde el día
cero. Un costo derivado distinto del de la base se informa, no se corrige.

## Salidas

- `historial`: imprime ingresos, aportes y retiros, realizado por especie, total, avisos, renglones sin
  clasificar y diferencias con la base. Escribe `realizado.csv`, solo para el usuario. Sin `extractos/`, o con
  un archivo inválido, termina con error y no escribe nada.
- `dashboard`: si existe `extractos/`, agrega `id="rendimiento-realizado"` y `historial` en `datos-cartera`.
  Si el cálculo falla, el dashboard se genera igual, con un aviso. Sin `extractos/`, no muestra la sección.
