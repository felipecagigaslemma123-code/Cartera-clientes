# Flujo de fondos por cliente

Versión 1.1 · 11/11/2026 · Especificación de Claude, aprobada por Felipe para la etapa 9. La 1.1 precisa el
control de cobros y el calendario después de la revisión ([REVISION_ETAPA9.md](REVISION_ETAPA9.md)).

## Qué se busca

Para cada cliente, mostrar **cuánto va a cobrar, cuándo y en qué moneda** por sus bonos, obligaciones
negociables y letras, y **cuánto gana a vencimiento con el precio al que compró**. Este resultado no
depende del precio de mercado de hoy: depende de los nominales que tiene, del precio que pagó y del
cronograma de pagos del título.

Es un panel de lectura del dashboard. No modifica la valuación, el efectivo, el resultado completo, el
realizado ni el día cero. No es una promesa de pago: el título puede no pagar y las fechas pueden
correrse por feriados.

Se supone que el cliente **conserva los nominales hasta el vencimiento**. Una venta posterior reduce los
nominales por FIFO y, desde ese momento, el flujo de esos nominales deja de mostrarse.

## Alcance de la etapa 9

| Familia | Qué se hace |
|---|---|
| Tasa fija (`k = "fix"` en IAMC): bonos y ON en USD, y el único caso en ARS | Flujo completo, TIR de compra y resultado a vencimiento |
| Letras LECAP/BONCAP ya habilitadas en [LETRAS.md](LETRAS.md) | Su pago previsto entra al calendario consolidado; se sigue usando el motor existente |
| CER, TAMAR/BADLAR (`var`), dólar linked (`dl`), capitalizables variables y duales (`cap`, `capv`) | Se listan con la leyenda "proyección pendiente: requiere supuestos". **No se muestran importes** |

CER, TAMAR, dólar linked y duales se proyectan desde la etapa 11, con datos del BCRA y el REM: ver
[PROYECCIONES.md](PROYECCIONES.md). Las familias `cap` son LECAP/BONCAP de tasa fija y las cubre el panel
de letras.

## Fuente de los cronogramas: IAMC

Se usa el JSON diario que genera `tools/iamc_extraer.py` (ver [FUENTE_IAMC.md](FUENTE_IAMC.md)), en su
bloque `calculadora_bonos.ins`.

- **Los pagos se toman siempre de `calc.ins.f`, nunca de `amo`/`ren` del informe.** En el cierre del
  05/11/2026, `ren` de AL30 ignora la suba del cupón a 1,75% desde el 09/07/2027 (trae 0,18 en lugar de
  0,42 para el 09/01/2028). La calculadora es correcta.
- Fecha de cada pago: `liq + f[j][0]` días corridos. Amortización: `f[j][1]`. Renta: `f[j][2]`. Ambas
  son **por 100 nominales originales**, en la unidad `cur` (`USD` o `ARS` para `fix`).
- La moneda de cobro se toma de `cur` y la plaza de la referencia `fxr` del mismo registro (`MEP` o
  `CCL`). Se muestra, por ejemplo, "USD (MEP)" o "USD (cable)". No se deduce del sufijo del ticker.
- Un instrumento ausente en el cierre se informa como "sin cronograma en IAMC al <fecha>", nunca se
  completa con otro cierre ni con otro instrumento. Ejemplo: TX26 en el cierre del 05/11.

### Descarga y archivo de cierres

El extractor pasa a `src/cartera/iamc.py` y suma el comando `iamc`, que guarda el cierre en
`<datos>/iamc/cierres/<fecha_cierre>.json`. Se mantienen sus reglas de caché, de un intento por día y de
robots que ya figuran en [FUENTE_IAMC.md](FUENTE_IAMC.md). La carpeta es compartida por todos los
clientes: no contiene datos de ninguno. `iamc --html RUTA` procesa un HTML guardado sin usar la red.

**Hay que conservar todos los cierres.** Son la única forma de tener los pagos anteriores a hoy, porque
IAMC solo publica los pagos que faltan a partir de la liquidación del día.

**Decisión de Felipe del 11/11/2026:** el comando `dashboard` intenta guardar el cierre publicado antes
de generar la pantalla, para no depender de acordarse de correr `iamc`.

- Solo lo hace si la carpeta de datos ya tiene algún cierre guardado. Una carpeta que nunca usó IAMC no
  empieza a consultarlo sola: el primer cierre se guarda con `iamc`.
- Vale la misma regla de un intento por día. Las demás corridas del día leen la caché, sin otra consulta.
- Si falla, el dashboard se genera igual con el último cierre guardado, y el motivo se informa en la
  salida del comando y en la sección Flujo de fondos. Una falla consume el intento de ese día.
- Espera como máximo 10 segundos por consulta.

La página HTML no consulta IAMC: usa el último cierre guardado al generarla. Si tiene más de 7 días
corridos, se muestra un aviso con su fecha.

### Identificación del instrumento

En `instrumentos.json` se agrega, por especie, el bloque explícito `iamc`:

```json
{"BOND1": {"vencimiento": "2030-07-09", "iamc": {"ticker": "AL30", "grupo": "tp"}}}
```

`grupo` es `tp` u `on`. Sin este bloque, la especie aparece como "sin vincular con IAMC". No se busca por
el ticker de la cartera (`AL30D`, `AL30C` y `AL30` son la misma especie con distinta moneda de
negociación, pero eso lo decide el asesor). Si el vencimiento cargado no coincide con la fecha del último
pago de IAMC, se muestra una advertencia sin frenar el cálculo.

## Cronograma de cada instrumento

Para una compra con liquidación `L`, se necesitan **todos los pagos con fecha mayor que `L`**:

1. **Regla única:** para cada fecha de pago se usa el importe del **cierre guardado más reciente cuya
   liquidación sea anterior a esa fecha**. Así, los pagos futuros salen del último cierre, y un pago ya
   ocurrido sale del último cierre que todavía lo traía.
2. Las fechas de pago se toman de la unión de esos cierres. Un pago que figura en un cierre viejo pero
   desaparece de uno posterior anterior a su fecha se informa como advertencia (posible
   reprogramación) y no se cuenta, porque el cierre más reciente ya no lo trae.
3. **Cronograma manual:** si la liquidación de la compra es anterior al cierre guardado más antiguo,
   los pagos que caen entre ambas fechas no figuran en ningún cierre. Para esos se usa el bloque opcional
   `iamc.pagos_manuales` de `instrumentos.json`, con la fuente:

   ```json
   "iamc": {"ticker": "AL30", "grupo": "tp",
            "pagos_manuales": {"fuente": "Prospecto, decreto 676/2020",
                               "pagos": [["2026-07-09", "8", "0.27"]]}}
   ```

   Se espera el cronograma completo del prospecto: si hay `pagos_manuales`, el tramo anterior al cierre
   más antiguo se considera cubierto por ellos.
   Cada pago tiene fecha, amortización y renta por 100 VN originales, como texto decimal. Si una fecha
   también figura en un cierre de IAMC y la diferencia supera 0,01 en amortización o en renta, se muestra
   una advertencia con los dos valores. Para el cálculo se usa el valor de IAMC.
4. Si después de esto falta algún pago entre `L` y hoy, la compra muestra los pagos futuros, pero la
   **TIR y el resultado a vencimiento quedan "sin dato: faltan pagos entre <fecha> y <fecha>"**. Nunca se
   calcula una TIR solo con los pagos futuros.

Cada pago guarda su origen: `iamc <fecha_cierre>` o `manual`.

### Controles del cronograma

- Si la suma de amortizaciones desde la emisión no da 100, no se frena nada: falta la parte anterior.
  Pero si se cuenta con el cronograma completo (cierres + manual) y la suma difiere de 100 en más de
  0,01, se muestra una advertencia.
- Los flujos base de familias no habilitadas no se usan aunque estén presentes.

## Precio de compra

Igual que en letras: el costo importado incluye gastos y puede estar convertido a pesos, así que **no se
deduce el precio de `costo / cantidad`**. Se carga a mano para cada compra:

```
precio-bono --cliente SLUG --referencia movimiento:3 --precio 51.62 --moneda USD --liquidacion 2026-11-06
```

- Las referencias son las mismas que lista `letras` (`base:N` y `movimiento:N`). El comando `bonos
  --cliente SLUG` lista las compras de especies de tipo `bono` y `on`.
- El precio es **sucio, por 100 VN originales**, igual que en la calculadora de IAMC.
- La moneda del precio debe ser la de los flujos (`cur`). Si el cliente pagó en otra moneda (por ejemplo
  AL30 en pesos), se agrega `--tc` con los pesos por dólar de esa operación. Se guardan el precio y el tc
  originales, y el precio en la moneda de los flujos es `precio / tc`. Sin `tc`, se rechaza.
- Archivo `compras_bonos.json`, con el mismo esquema, huella y reglas de escritura atómica que
  `compras_letras.json`, más el campo opcional `tc`. Se reutiliza ese código, no se duplica.
- Validaciones: la liquidación no puede ser anterior a la compra, posterior a hoy en Argentina ni igual
  o posterior al último pago.

Sin precio, la compra aparece como "falta precio de compra" y no tiene TIR ni resultado. Sus pagos
futuros sí se muestran, porque dependen solo de los nominales.

## Amortizaciones parciales: cambia la regla de movimientos

Hasta ahora [DOMINIO.md](DOMINIO.md) indica cargar una amortización como `venta`. Eso resta nominales,
pero los cronogramas están calculados sobre **100 nominales originales**: el cliente conserva sus
nominales y lo que baja es el valor residual. Si se cuentan las dos cosas, la amortización se descuenta
dos veces.

Regla nueva:

| Tipo | Especie | Cantidad | Efectivo | Para el resultado integral |
|---|---|---|---|---|
| `amortizacion` | obligatoria | no | sube | se desglosa, como `renta` |

- Una amortización parcial se carga como `amortizacion`. **No cambia la cantidad ni los lotes.**
- El pago final de un título se sigue cargando como `venta` de todos los nominales, porque cierra la
  posición.
- Solo admite especies de tipo `bono`, `on` o `letra` ya conocidas.
- En el realizado, las amortizaciones de un título se muestran junto a su venta final, porque el
  realizado de esa venta por sí sola subestima el resultado. No se cambia el cálculo del realizado.
- En el historial de la etapa 6, `RENTA Y AMORTIZ` sigue llegando como un solo importe. Se mantiene su
  clasificación y en el control de cobros se compara contra renta + amortización del mismo día.
- **Migración:** el comando `flujo --cliente SLUG --revisar` lista las `venta` de bonos u ON cuya nota
  contenga "amortiz" (sin distinguir mayúsculas ni acentos) y que no cierren la posición. No las cambia:
  Felipe decide cómo corregirlas.

## Cálculos

Para cada compra con nominales vigentes `N` (los remanentes del lote después de FIFO):

```text
pago_t           = (amortizacion_t + renta_t) × N / 100          en la moneda de los flujos
inversion        = precio_flujo × N / 100
total_a_cobrar   = Σ pago_t  con fecha > liquidacion de la compra
resultado_vto    = total_a_cobrar − inversion                     nominal, sin descontar
TIR_compra       : precio_flujo = Σ (amort_t + renta_t) / (1 + TIR)^(dias_t / 365)
```

- `dias_t` son días corridos desde la liquidación de la compra hasta la fecha contractual del pago
  (ACT/365, precio sucio), igual que IAMC. La TIR se resuelve sobre los flujos **por 100 VN**, sin `N`.
- Con `Decimal` en los importes. La TIR se resuelve por bisección con tolerancia de precio menor a
  `1e-10`. Si no hay solución en `(-0,99; 10)`, es "sin dato".
- Si la compra fue parcialmente vendida, se usan los nominales remanentes; la TIR no cambia.
- **Sin gastos ni comisiones**, como el rendimiento de letras. Se aclara en pantalla.
- `resultado_vto` es una suma nominal de dinero a cobrar en distintas fechas. Se presenta con esa
  aclaración, no como ganancia actual.

### Capital que vuelve y ganancia

Pedido de Felipe del 18/11/2026 (etapa 13). Lo que se cobra de un bono no es todo ganancia: una parte
devuelve lo que se pagó al comprarlo. Para cada compra con precio, en la moneda de los flujos y con sus
nominales `N`:

```text
corrido          = renta del primer pago posterior a la liquidación × días desde el pago anterior hasta
                   la liquidación / días del período                      (intereses corridos pagados)
capital_limpio   = inversion − corrido × N / 100
amortizaciones   = Σ amortizacion_t × N / 100
ganancia_precio  = amortizaciones − capital_limpio      comprar bajo la par (o sobre: negativa) y,
                                                        en un ajustable, el ajuste por el índice
intereses        = Σ renta_t × N / 100 − corrido × N / 100
resultado_vto    = ganancia_precio + intereses          (igual que antes)
```

- **Por pago:** `capital_t = capital_limpio × amortizacion_t / Σ amortizacion`, y el primer pago suma además
  el corrido. `ganancia_t = pago_t − capital_t`. La suma de los `capital_t` es exactamente la inversión.
- **Pago anterior:** la fecha de pago más cercana anterior o igual a la liquidación en el cronograma del
  título. Si no está (cronogramas manuales que empiezan después de la compra), se supone que el período
  mide lo mismo que el siguiente y se marca `intereses_corridos_estimados`.
- Lineal en días corridos: no reproduce la convención de cada prospecto (30/360, real/365). El error es una
  fracción del cupón y solo mueve importe entre capital e intereses: el total no cambia.
- Sin dato (`motivo_capital`) si el título no amortiza o no se puede ubicar el inicio del cupón.
- **Por posición:** `capital_pendiente` = suma del capital de los pagos `proyectado` de sus compras, y
  `ganancia_pendiente` = `total_proyectado − capital_pendiente`. Sin dato si alguna compra no tiene la
  separación o si los lotes no suman los nominales de la posición.
- Dashboard: "Devuelve capital" y "Ganancia" en la tarjeta de la posición y en los pagos de cada compra;
  "Por precio" y "Por intereses" en cada compra, con una nota sobre los intereses corridos. El Excel los
  recibe en las mismas tablas.

### Lo cobrado y lo por cobrar

- Pagos con fecha contractual menor o igual a hoy: **"debería haberse cobrado"**.
- Pagos posteriores a hoy: **"proyectado"**.
- **Control de cobros**, por especie y por fecha de pago: importe teórico (pago × nominales que había al
  cierre del día anterior a la fecha de pago; una compra o una venta de ese mismo día no lo cambia, porque
  el título ya negocia sin ese cupón) contra la suma de `renta` y `amortizacion` cargadas para esa especie entre la
  fecha de pago y 10 días corridos después. Se muestra la diferencia; puede deberse a retenciones, gastos
  o a que todavía no se cargó. Si no hay ningún movimiento en esa ventana: "cobro no registrado". Nunca se
  da por cobrado un pago sin movimiento.
- Los movimientos en ARS de un pago en USD se comparan convertidos con su `tc` y se marcan como tales.
- **El control empieza en el día cero.** Antes no se conocen los nominales. Un pago anterior al día cero
  solo se lista si figura en los extractos de la etapa 6, sin importe teórico, y no entra al calendario.
  Sin registro no se lista: no es un "cobro no registrado". La pantalla aclara desde qué fecha se controla.

### Fechas hábiles

La TIR usa la fecha contractual. En pantalla, un pago que cae sábado o domingo muestra además "se cobra
el lunes dd/mm". No hay calendario de feriados: se aclara una sola vez que la fecha puede correrse por
un feriado.

## Pantalla

Nueva sección **Flujo de fondos** del dashboard, después de la de letras.

1. **Calendario consolidado por mes**, una columna por moneda (ARS, USD MEP, USD cable). Separa
   "debería haberse cobrado" de "proyectado". **Nunca suma monedas distintas** ni convierte a pesos.
   Incluye el pago previsto de las letras ya habilitadas. Una moneda sin pagos en el mes muestra una
   raya; "sin dato" queda para un importe que no se pudo calcular.
2. **Por especie:** nominales, moneda de cobro, próximo pago (fecha e importe), total proyectado y
   cantidad de pagos restantes. Se despliega:
3. **Por compra:** fecha, liquidación, nominales remanentes, precio pagado (y tc si corresponde),
   inversión, total a cobrar, resultado a vencimiento, TIR de compra y origen de cada pago. Y la tabla de
   pagos con fecha, renta, amortización, total y estado.
4. **Especies no habilitadas:** ticker y motivo ("proyección pendiente: requiere supuestos", "sin
   vincular con IAMC", "sin cronograma en IAMC al <fecha>").
5. **Estado de la fuente:** fecha del cierre de IAMC usado, antigüedad, fecha del cálculo y advertencias.

La sección no se actualiza con los precios en vivo: no depende de ellos. Los importes se muestran con
dos decimales y la TIR con dos decimales en porcentaje; el JSON embebido conserva los valores completos.

La descarga en Excel suma la hoja **Flujo de fondos** con el calendario y el detalle por compra, con los
mismos valores que la pantalla.

## Reglas que no se negocian

- Sin precio, sin cronograma completo o sin vínculo con IAMC se dice qué falta. Nunca un cero.
- Lo proyectado se ve siempre como proyectado. Un pago vencido sin movimiento no es un pago cobrado.
- No se suman monedas distintas ni se convierte un flujo en dólares a pesos.
- Nada de esto entra al efectivo, al patrimonio ni al resultado completo.
- Ninguna familia fuera de `fix` muestra importes en esta etapa.
