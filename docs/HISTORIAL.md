# Rendimiento realizado

Responde cuánto se ganó o se perdió con lo ya vendido y cobrado, sin contar el dinero que el cliente
puso o sacó. Es un cálculo aparte del resultado desde el día cero: no lo reemplaza ni se suma a él.

## Archivos, en la carpeta del cliente

```text
extractos/*.xlsx, *.xls cuentas corrientes del broker, en cualquier cantidad y con períodos superpuestos
especies.json           nombre y tipo de cada especie; solo para derivar-base
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

## Extractos de InvertirOnline

Archivo `.xls` de "Operaciones históricas". **No es un Excel:** es una página HTML con una tabla. Se lee con
`html.parser`, en UTF-8, convirtiendo las entidades (`Dep&#243;sito`). Un `.xls` que no contenga esa tabla es
inválido. `extractos/` admite `.xlsx`, que se lee con `leer_extracto`, y `.xls`, con `leer_extracto_iol`.

Encabezado exacto, 14 columnas; las celdas se limpian de etiquetas y de espacios repetidos:

```text
Nro. de Mov., Nro. de Boleto, Tipo Mov., Concert., Liquid., Est, Cant. titulos, Precio, Comis., Iva Com.,
Otros Imp., Monto, Observaciones, Tipo Cuenta
```

- **Filas:** solo cuentan las de `Est` igual a `Terminada`. Las demás se ignoran.
- **Números:** punto de miles y coma decimal (`-413.228,38`, `1581,7106`, `305`).
- **Fecha:** `Concert.`, con formato `dd/mm/aa`, del siglo XXI.
- **Cuenta:** `Inversion Argentina Pesos` es ARS, cuenta `PESOS`; `Inversion Argentina Dolares` es USD, cuenta
  `DOLARES`. Otra cuenta hace inválido el archivo.
- **Importe:** `Monto`, con su signo. Ya incluye comisiones e impuestos. `saldo` es `None`: no hay control de saldo.
- **Número:** `Nro. de Mov.`. **Referencia:** el texto original de `Tipo Mov.`.
- **Especie:** lo que está entre paréntesis en `Tipo Mov.`, sin el sufijo ` US$`. Sin paréntesis, vacía.

`Tipo Mov.` se traduce a un `comprobante` propio. Lo que no figura en la tabla conserva su texto original y
queda `sin_clasificar`.

| `Tipo Mov.` | `comprobante` | `cantidad` | Clase |
|---|---|---|---|
| `Compra(X)` | `IOL COMPRA` | positiva | `compra` |
| `Venta(X)` | `IOL VENTA` | negativa | `venta` |
| Fila en pesos de una operación en dólares | `IOL IMPUESTO` | 0 | `gastos` |
| `Pago de Renta(X)`, monto ≥ 0 | `IOL RENTA` | 0 | `renta` |
| `Pago de Dividendos(X)`, monto ≥ 0 | `IOL DIVIDENDO` | 0 | `dividendo` |
| `Pago de Renta` o `Pago de Dividendos`, monto < 0 | `IOL GASTO DE COBRO` | 0 | `gastos` |
| `Pago de Amortización(X)` | `IOL AMORTIZACION` | la del archivo, ≤ 0 | ver abajo |
| `Depósito de Fondos…` | `IOL DEPOSITO` | 0 | `aporte` |
| `Extracción de Fondos…` | `IOL EXTRACCION` | 0 | `retiro` |
| `Suscripción FCI(X)`, `Rescate FCI(X)` | `IOL SUSCRIPCION FCI`, `IOL RESCATE FCI` | 0 | `fci` |
| `Caución(…)` | `IOL CAUCION` | 0 | ver abajo |
| `Liquidación de Caución` | `IOL LIQUIDACION CAUCION` | 0 | ver abajo |
| `Crédito` | `IOL CREDITO` | 0 | `gastos`, con su signo |

**Operación en dólares.** Una compra o venta en dólares ocupa dos filas con el mismo `Nro. de Mov.`: la de la
cuenta en dólares es la operación, y la de la cuenta en pesos solo trae un impuesto cobrado en pesos, con la
misma cantidad repetida. La cantidad se cuenta **una sola vez**: la fila en pesos sale como `IOL IMPUESTO`, con
cantidad 0. La especie de las dos filas pierde la `D` final, que solo indica que cotiza en dólares (`AE38D` es
`AE38`). Cualquier otra repetición de `Nro. de Mov.` entre compras o ventas hace inválido el archivo.

**Gasto de cobro.** Una renta o un dividendo en dólares llega con otra fila en pesos, de monto negativo, que es
su comisión. Va a `gastos`, no a `renta`, para que los cobros queden limpios.

**Amortización.** Las filas `IOL AMORTIZACION` se agrupan por especie y fecha, aunque estén en cuentas distintas:

- Si alguna trae cantidad negativa, es un **cierre** por esa cantidad, no por toda la posición abierta. El importe
  es la suma de las filas del grupo, cada una en pesos. Consume lotes por FIFO, como una venta, y si no alcanzan
  el resultado es "sin dato". No hace falta `cierres.json`.
- Si ninguna trae cantidad, es una devolución parcial de capital: los nominales no bajan y se suma como `renta`.

**Caución.** Las dos filas comparten `Nro. de Mov.` y tienen fechas distintas: se agrupan por moneda y número, y
se suman. La fecha del ingreso es la de la liquidación. Si `IOL CAUCION` es negativa es `caucion_colocada`; si
es positiva, `caucion_tomada`. Un grupo sin alguna de las dos filas no se suma y genera un aviso.

`cobros` incluye las rentas y las filas de amortización con importe, no los gastos de cobro.

## Clasificación de cada renglón

| Comprobante | Clase | Tratamiento |
|---|---|---|
| `COMPRA NORMAL`, `COMPRA TRADING`, `COMPRA PARIDAD`, `COMPRA CABLE` | `compra` | Lote nuevo |
| `VENTA`, `VENTA TRADING`, `VENTA PARIDAD`, `VENTA CABLE` | `venta` | Consume lotes por FIFO |
| `RENTA Y AMORTIZ` de especie en `cierres.json` | `cierre` | Cierra la posición |
| `RENTA Y AMORTIZ` de otra especie | `renta` | Ingreso |
| `DIVIDENDOS` | `dividendo` | Ingreso, con su signo |
| `RETENCION` | `retencion` | Se muestra aparte, con su signo |
| `COMPRA CAUCION CONTADO` + `VENTA CAUCION TERMINO` | `caucion_colocada` | Ingreso: suma de las dos patas |
| `VENTA CAUCION CONTADO` + `COMPRA CAUCION TERMINO` | `caucion_tomada` | Costo: suma de las dos patas |
| `SUSCRIPCION FCI`, `LIQUIDACION RESCATE FCI` | `fci` | Suma de los importes |
| `CREDITO DERMERC-`, `N C ARANCELES` | `gastos` | Con su signo |
| `NOTA DE CREDITO EO` | `compensacion` | Ingreso: lo que el broker devolvió por un error operativo |
| `RECIBO DE COBRO` | `aporte` | Dinero del cliente, **no es ganancia** |
| `ORDEN DE PAGO` | `retiro` | Dinero del cliente, **no es ganancia** |
| `NOTA DE CREDITO U$S`, `NOTA DE DEBITOS U$S` con referencia `CONV CABLE A ME` | `conversion` | Traspaso interno, no cuenta |
| Cualquier otro | `sin_clasificar` | **No se suma.** Se lista completo para revisar |

Las patas de una caución se agrupan por moneda, clase y `Operado`, que es la misma fecha en las dos patas.
No se emparejan una a una, porque una pata de contado puede tener dos de término. Un grupo sin alguna de
las dos patas no se suma y genera un aviso con sus números, porque solo contiene capital.

## Orden y lotes

Se procesa por fecha. Dentro de un mismo día: primero las compras del extracto, después las de ajustes,
y al final ventas y cierres, en orden de `Numero`. Los lotes se consumen por FIFO y los de la misma fecha, en orden de creación.

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
del día de la transferencia. Sus lotes tienen origen `estimado`, y una venta por ajuste sobre lotes de
extracto tiene origen `mixto`, porque su importe no sale de un extracto. Lo ganado antes de esa fecha en el otro
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
               + caución colocada + caución tomada + FCI + gastos + compensaciones
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
cero. Un costo derivado que difiere del de la base en más de 1 peso se informa, no se corrige.

## Base derivada

`derivar-base` arma `cartera.json` cuando la historia de movimientos está completa, sin Excel de punto de partida.
Usa los mismos archivos que `historial` y además `especies.json` ([FORMATOS.md](FORMATOS.md)).

- **Posiciones:** una por especie con lotes abiertos; la cantidad es la suma de sus lotes. `especie` y `tipo`
  salen de `especies.json`, y `cotiza_cada`, del tipo.
- **Lotes:** los lotes abiertos del historial, en su orden, con su fecha y su origen. `precio` es
  `costo / cantidad × cotiza_cada`. Un lote sin costo en pesos queda `pendiente`, sin precio ni costo.
- **`origen`** de la base: `archivo` es `extractos`, y `sha256`, la huella de los nombres y bytes de los archivos
  de `extractos/`, en orden de nombre.

No escribe nada, y termina con error, si:

- alguna venta o cierre no tiene lotes suficientes: la historia está incompleta. Lista especie y cantidad.
- hay un renglón `sin_clasificar` con cantidad distinta de cero: puede ser una entrada o salida de títulos.
- una especie con lotes abiertos no figura en `especies.json`, o su tipo no es válido. Lista todas.
- no queda ningún lote abierto.
- ya existe `cartera.json`. Con `--reemplazar` guarda la versión anterior en `historial_cartera/` y escribe la
  nueva, salvo que exista `dia_cero.json` o `movimientos.csv` tenga movimientos: ahí los movimientos posteriores
  se contarían dos veces.

Los renglones `sin_clasificar` sin cantidad y los avisos del historial no frenan: se muestran.
Después de `derivar-base`, `historial` no informa diferencias de cantidad ni de costo.

## Salidas

- `historial`: imprime ingresos, aportes y retiros, realizado por especie, total, avisos, renglones sin
  clasificar y diferencias con la base. Escribe `realizado.csv`, solo para el usuario. Sin `extractos/`, o con
  un archivo inválido, termina con error y no escribe nada.
- `dashboard`: si existe `extractos/`, agrega `id="rendimiento-realizado"` y `historial` en `datos-cartera`.
  Si el cálculo falla, el dashboard se genera igual, con un aviso. Sin `extractos/`, no muestra la sección.
