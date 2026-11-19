# Informe para el cliente

Versión 1.2 · 18/11/2026 · Pedido de Felipe para la etapa 12. La 1.1 cambia el cálculo del resultado acumulado
(sección 8): restarle los aportes al patrimonio daba de más en una cartera con tenencias anteriores al primer
extracto. La 1.2 separa, en lo que se va a cobrar, lo que devuelve lo invertido de la ganancia (secciones 5 y
6; etapa 13). La 1.3 ordena el informe en tres partes que dicen a qué momento miran: hoy, hasta hoy y de acá
en adelante (pedido de Felipe del 18/11/2026).

## Qué se busca

Un documento para entregarle al cliente: cómo está compuesta su cartera, cuánto va a cobrar y cuándo, y qué
resultado obtuvo. El dashboard es la herramienta de trabajo del asesor, y el informe es su versión para
presentar: menos datos, más gráficos y ninguna información interna (avisos, estados de consulta, controles).

El 16/11/2026 Claude armó a mano un prototipo con una cartera real y Felipe lo aprobó. Esta etapa convierte ese
prototipo en el comando `informe`, válido para cualquier cliente.

## De dónde salen los datos

Del bloque `datos-cartera` del último `dashboard.html` del cliente. El informe muestra **los mismos números que
el asesor revisó** en el dashboard: no consulta precios, no recalcula el flujo y no lee extractos. Si el
cliente tiene datos nuevos, primero hay que regenerar el dashboard.

Además lee `instrumentos.json`, que define la clase de cada título, y `perfil.json`, con el nombre del cliente
y el del asesor. Los dos archivos son opcionales.

## Comando

```bash
python3 -m cartera --datos RUTA informe --cliente SLUG [--salida CARPETA] [--pdf]
```

- Escribe `informe-AAAA-MM-DD.html`, con la fecha de `generado_en` del dashboard. Por defecto lo guarda en
  `<datos>/clientes/<slug>/informes/` y, con `--salida`, en esa carpeta. La escritura es atómica. Un informe de
  la misma fecha se reemplaza.
- `--pdf` agrega `informe-AAAA-MM-DD.pdf`, generado con Google Chrome en modo *headless*
  (`/Applications/Google Chrome.app/Contents/MacOS/Google Chrome --headless=new --no-pdf-header-footer
  --print-to-pdf=...`). Si Chrome no está instalado, el HTML se escribe igual y el comando termina con un
  error que dice cómo imprimirlo desde el navegador. No se agregan dependencias de Python.
- **Carpeta del cliente** (pedido de Felipe del 18/11/2026): si `perfil.json` tiene `carpeta_informes` (ruta
  absoluta o relativa a la carpeta de datos, por ejemplo `"../Clientes/<carpeta del cliente>/Informes"`), el
  comando genera el PDF aunque no se pida `--pdf` y deja una copia como `Informe de cartera AAAA-MM-DD.pdf`.
  Crea la carpeta si no existe y reemplaza el informe de la misma fecha. Sin Chrome, deja ahí el HTML y
  termina con error. Una ruta vacía o que no es texto es un error y no se escribe nada.
- Si el dashboard tiene más de 3 días, el comando lo avisa por consola con la antigüedad ("el dashboard tiene
  9 días") y escribe el informe igual.
- Errores: si falta el dashboard o su bloque de datos, el comando termina con código distinto de cero, un
  mensaje claro y **sin escribir nada**.

## Contenido

Pedido de Felipe del 18/11/2026: una clienta sin experiencia leyó los cobros futuros como ganancias pasadas (el
"US$ 29" de 2026 eran dos rentas que todavía no había cobrado). El informe va en **tres partes**, en este orden,
y cada una dice a qué momento mira:

| Parte | Etiqueta | Qué responde |
|---|---|---|
| 1. Tu cartera hoy | Hoy | Qué tenés y cuánto vale |
| 2. Lo que ya ganaste | Hasta hoy | El resultado desde que empezaste a invertir |
| 3. Lo que vas a ganar desde hoy | De acá en adelante | Los pagos que van a hacer tus bonos y letras, que todavía no cobraste, y cuánto de eso es ganancia |

Al final, aclaraciones y glosario. Una parte sin datos no se muestra ni se numera: sin `historial` no hay parte 2
y la de cobros pasa a ser la 2; sin renta fija no hay parte de cobros. Una sección sin datos no deja un recuadro
vacío.

Cada parte empieza con un encabezado: la etiqueta en un recuadro, "N. Título" y una frase que dice qué muestra.
La parte 3 dice "**Todavía no los cobraste**", en negrita.

### Lenguaje

- Se le habla al cliente de vos ("tenés", "ganaste", "vas a cobrar").
- Cada número dice qué es con una frase debajo. Los títulos de lo futuro dicen que es futuro ("Cobros futuros por
  título", "Total a cobrar desde hoy").
- Un importe negativo en pesos lleva el signo antes del símbolo ("−$ 1.234"). En las notas, un resultado se dice
  con palabras ("una pérdida de $ 1.234") y el signo pesos no se separa del número.

### Hoja 1: resumen y tu cartera hoy

- Encabezado con el nombre del asesor (`perfil.asesor`), "Informe de cartera" y la fecha. Abajo, el nombre del
  cliente (`perfil.nombre` o `datos.cliente.nombre`) y una línea con la fecha y el dólar MEP de valuación.
- **Este informe en tres partes** (o dos): una tarjeta por parte, con su etiqueta, "N. Título", el número
  principal con su rótulo y una frase. Números: patrimonio total (o invertido en títulos si no hay patrimonio),
  resultado total hasta hoy y **la ganancia que falta cobrar en cada moneda** (`a_ganar`: total a cobrar menos lo
  que devuelve lo invertido), cada moneda en su renglón, sin sumarlas. No se muestra el total a cobrar: incluye
  lo invertido y el cliente lo leía como ganancia (pedido de Felipe del 18/11/2026). Una moneda sin la separación
  dice "sin dato"; una que depende de un índice proyectado agrega "incluye estimados".
- Encabezado de la parte 1 y tres indicadores, cada uno con una frase:
  - **Patrimonio total** = `integral.patrimonio_final` ("todo lo que tenés en la cuenta"), con su equivalente en
    dólares al MEP. Si no hay dato, dice "sin dato".
  - **Invertido en títulos**: la suma de las valuaciones ("lo que valen hoy tus títulos") y su peso en el
    patrimonio.
  - **Efectivo disponible**: el de `integral.efectivo` ("plata en la cuenta, sin invertir"), con pesos y dólares
    por separado. Un saldo faltante dice "sin dato", sin signo de moneda.

#### Composición

Un gráfico de dona con su leyenda: clase, peso y valuación. La clase sale de los datos y nunca del ticker:

| Condición (se toma la primera que se cumple) | Clase |
|---|---|
| `instrumentos[t].iamc.indice.tipo` = `A3500` o `DUAL` | Dólar linked |
| `instrumentos[t].iamc.indice.tipo` = `CER` | Ajustables por CER |
| `instrumentos[t].iamc.indice.tipo` = `TAMAR` | Tasa variable TAMAR |
| `tipo` = `letra` | Letras y BONCAP en pesos |
| `tipo` = `on` y el flujo cobra en USD | Obligaciones negociables en dólares |
| `tipo` = `bono` y el flujo cobra en USD | Bonos en dólares |
| `tipo` = `bono` u `on` y el flujo cobra en ARS | Bonos en pesos |
| `tipo` = `cedear` | CEDEARs |
| `tipo` = `accion` | Acciones |
| Cualquier otro caso, o renta fija sin flujo | Otros títulos |

El flujo cobra en USD cuando la posición de `flujo_fondos.posiciones` tiene `moneda` `USD`. Las clases se
ordenan por valuación, de mayor a menor, y a igual valuación por nombre.

Debajo de la dona va una frase: "**N % de tu cartera está en títulos que pagan en dólares**". N es el peso de
las dos clases en dólares. Si hay CEDEARs, se agrega "Los CEDEARs (M %) cotizan en pesos, pero su precio sigue
al dólar.": sin esa frase, una cartera con mayoría de CEDEARs parecía estar en pesos. Sin ninguna de las dos
condiciones no hay recuadro.

### Hoja 2: tu cartera hoy, título por título

Tabla con título (ticker en negrita y descripción abajo), cantidad, precio, valuación, peso, "Desde la compra"
y vencimiento.

- Descripción: la `especie`. En una letra se usa "<familia> dd/mm/aaaa", con la familia y el vencimiento del
  bloque `letras`.
- "Desde la compra" = `resultado / costo`. Si falta el costo, "—". Una nota aclara que es la variación frente a
  lo pagado, en pesos, que es una ganancia o pérdida **en papel** hasta que se vende o vence, y que **no incluye
  las rentas cobradas**.
- Orden: por clase (en el orden de la composición) y, dentro de cada clase, por valuación.

### Hoja 3: lo que ya ganaste (hasta hoy)

Solo si existe `historial`. Primero, una cuenta que se lee de izquierda a derecha:

> **Ganancia ya cobrada** + (o −) **Suba (o baja) de lo que todavía tenés** = **Resultado total hasta hoy**

- **Ganancia ya cobrada** = `historial.total_conocido` + resultado desde el día cero ("en ventas, vencimientos,
  rentas y dividendos"). Si el historial tiene operaciones sin resultado (`ventas_sin_dato`, `valores_sin_dato` o
  `cantidad_sin_clasificar` mayores que cero), aclara que suma solo lo conocido y cuántas faltan.
- **Suba o baja de lo que todavía tenés**: la suma de `posiciones[].resultado` ("lo que valen hoy tus títulos
  frente a lo que pagaste; todavía no es plata cobrada"). Se muestra sin signo: el rótulo dice "Suba" o "Baja" y
  el operador cambia a "−".
- **Resultado total hasta hoy**: el resultado acumulado, con la definición de abajo.

Debajo, **De dónde sale la ganancia ya cobrada**, un desglose que suma exactamente ese total:

| Renglón | Valor | Frase |
|---|---|---|
| Ventas y vencimientos | `realizado_extracto + realizado_estimado` | lo recibido al vender o al vencer, menos lo pagado |
| Rentas | `ingresos.renta.equivalente_ars` | intereses de los bonos; si hubo cobros en dólares, cuántos y que se convirtieron al MEP del día de cada cobro |
| Dividendos, cauciones y otros | ganancia realizada − ventas − rentas | dividendos, cauciones y fondos, menos gastos e impuestos |
| Desde el <día cero> | resultado desde el día cero | solo si no es cero: ventas y cobros registrados después del último extracto |

**Resultado acumulado** (versión 1.1) = ganancia realizada + resultado desde el día cero + resultado de la
tenencia actual:

- Resultado desde el día cero: la suma de `realizados[].resultado` (ventas registradas como movimientos) más
  `integral.rentas`, `integral.dividendos` e `integral.amortizaciones`, menos `integral.gastos`. Sin movimientos
  es cero.
- Resultado de la tenencia actual: la suma de `posiciones[].resultado`, valuación menos costo.

No usa el patrimonio ni los aportes. Una tenencia anterior al primer extracto o un título transferido desde
otro broker entra en la cartera sin un aporte registrado, pero con su costo de entrada: restar los aportes al
patrimonio la contaba como ganancia. Por eso tampoco necesita el día cero. No incluye la variación del dólar
sobre el efectivo en dólares.

Es "sin dato", con el motivo en la nota, si falta la ganancia realizada, si el historial tiene operaciones sin
resultado, si a una posición le falta el resultado (costo o precio) o si una venta desde el día cero no tiene
resultado. Supone que el historial llega hasta el día cero y lo posterior está en los movimientos: si un mismo
período figura en los dos, se cuenta dos veces.

Después, **Ganancia o pérdida en lo que vendiste o venció**: barras con el resultado de cada operación de
`historial.realizados`, ordenadas por fecha. Las positivas van hacia arriba en un color y las negativas hacia abajo
en otro. Cada barra lleva el ticker y el mes. Con más de 14 operaciones, una barra por mes con la suma del
resultado, solo con el mes, y la nota dice cuántas operaciones son: con 40 barras no se lee nada. Una nota explica
que cada barra compara lo recibido al vender o al vencer con lo pagado y que no incluye rentas ni dividendos.

Al final, una nota explica el resultado total con palabras ("la ganancia ya cobrada más una pérdida de $ 1.234
en lo que todavía tenés") o qué falta si es "sin dato", y aclara que los importes son **pesos nominales sin
ajuste por inflación**.

### Hoja 4: lo que vas a ganar desde hoy (de acá en adelante)

Encabezado de la parte 3, "Lo que vas a ganar desde hoy": los pagos desde hoy hasta el vencimiento; una parte
devuelve lo invertido y el resto es ganancia; todavía no se cobraron y dependen de que cada emisor pague.

#### Próximos cobros

Lista con los próximos siete eventos posteriores a la fecha del informe: fecha, título, concepto ("Renta",
"Renta y amortización" o "Vencimiento") e importe con su moneda. Un pago estimado dice "estimado". Un pago
que amortiza agrega entre paréntesis cuánto es ganancia ("Vencimiento ($ 53.744 de ganancia)"): el resto
devuelve lo invertido. Una renta sola no lleva el paréntesis: es toda ganancia, salvo unos centavos de
intereses corridos de una compra reciente.

- Sale de los pagos `proyectado` de cada posición del flujo y de los vencimientos de las letras.
- Concepto: "Vencimiento" si la fecha es el `vencimiento` de la posición (o, si la posición no lo tiene, si
  es el último pago de su lista) y en las letras; si no, "Renta y amortización" cuando amortiza y "Renta"
  cuando no.
- Orden: por fecha y, a igual fecha, por ticker.

Una nota explica los conceptos: renta (intereses), amortización (devuelve una parte de lo invertido),
vencimiento (el último pago), qué es el paréntesis de ganancia y qué significa "estimado".

#### Rendimiento al precio de compra

Barras horizontales con la TIR de cada título del flujo de fondos y la TEA de cada letra.

- Si el título tiene varias compras, se muestra la TIR **promedio ponderada por la inversión** (`inversion` de
  cada compra, en la moneda de cobro) y una marca con el rango entre la mínima y la máxima. En las letras, el
  peso es `cantidad_restante × precio` y la tasa es `tea`.
- Las compras sin TIR (`tir` nulo) no entran al promedio. Si ninguna tiene TIR, el título figura con "sin
  dato".
- La TIR es **estimada** si alguna compra tiene `tir_estimada`. La barra se dibuja más clara y la etiqueta dice
  "estimada".
- Color según la moneda de cobro: dólares en un color y pesos en otro.
- Orden (vale también para la tabla de la sección 5): primero los que cobran en dólares y después los de
  pesos; dentro de cada grupo, en el orden de la tenencia.
- Nota en lenguaje llano: es la tasa anual que se gana si se mantiene el título hasta el vencimiento, según el
  precio de compra, y no cambia con el precio de hoy; la de un bono en dólares es en dólares, la de una letra o
  un bono en pesos es en pesos, y "estimada" depende de lo que esperan los analistas que consulta el BCRA.

### Hoja 5: lo que vas a ganar desde hoy, título por título

#### Cobros futuros por título

Tabla con título (cantidad de compras y moneda de cobro abajo, en un renglón), próximo pago (fecha y monto),
**total a cobrar desde hoy** hasta el vencimiento, **cuánto de eso devuelve lo invertido**, **cuánto es ganancia** y TIR. Debajo, un
indicador por moneda con el **total a cobrar**, sumado solo dentro de cada moneda: `ARS`, `USD MEP` y
`USD cable` van en indicadores separados. **Nunca se suman monedas.** Cada indicador lleva una barra con las
dos partes y el texto "X devuelve lo invertido · Y de ganancia".

- Lo que devuelve lo invertido de un título del flujo: `capital_pendiente` (docs/FLUJO_FONDOS.md, "Capital
  que vuelve y ganancia"); la ganancia, `ganancia_pendiente`. De una letra: Σ `cantidad_restante × precio /
  100` de sus lotes, y la ganancia es el pago menos eso; sin dato si los lotes no suman la cantidad de la
  letra.
- Si a un título de una moneda le falta la separación, el indicador de esa moneda no la muestra (no se
  completa con una parte).
- Una nota explica que no todo es ganancia: una parte devuelve lo pagado al comprar, incluidos los intereses
  corridos, y la ganancia son los intereses y la diferencia por comprar bajo la par (en un ajustable, también
  el ajuste por el índice).

- Total a cobrar de un título del flujo: `total_proyectado`. De una letra: `pago_vencimiento`.
- Una letra ajustable (LECER, LELINK) aparece tanto en `letras` como en `flujo_fondos`: se toma solo la del
  flujo, que tiene el pago proyectado.
- Próximo pago de un título del flujo: `proximo_pago`. De una letra: el vencimiento.

#### Cobros futuros en dólares, año por año

Barras por año con los cobros en dólares de `flujo_fondos.calendario`, una barra por moneda (MEP y cable,
juntas pero sin apilarse) y el valor arriba de cada una. Cada barra se parte en dos tonos: abajo, en el color
de la moneda, lo que devuelve lo invertido; arriba, en verde, la ganancia (`cobros_por_anio_capital`: suma
del capital de los pagos de ese año y moneda). Si a algún pago de ese año y moneda le falta la separación,
la barra va de un solo color. La leyenda suma "Ganancia" solo si alguna barra está partida. Los pesos se informan en el indicador de la
sección 5, no en este gráfico, porque su escala lo aplastaría.

- El año en curso lleva "desde hoy" debajo del año: solo suma lo que falta cobrar.
- La nota dice, en negrita, que **no incluye lo que ya se cobró**, y, si el año en curso tiene cobros en dólares,
  "AAAA muestra solo lo que falta cobrar desde el <fecha del informe>".

### Hoja 6: aclaraciones y palabras que usamos

Aclaraciones, texto fijo: los cobros futuros salen de las condiciones de emisión y suponen mantener los títulos
hasta el vencimiento, sujetos al pago del emisor; los dólares no se convierten ni se suman a los pesos; la
valuación es la del último precio de la fecha del informe; el informe **no constituye una recomendación de
inversión**.

**Palabras que usamos**: un glosario con solo las palabras que aparecen en esa cartera.

| Término | Cuándo aparece |
|---|---|
| Renta, Amortización, Vencimiento, TIR, Nominales | Hay renta fija |
| Dólar MEP | Siempre |
| Dólar cable | Algún título cobra en dólar cable |
| CEDEAR | Clase CEDEARs |
| Obligación negociable | Clase Obligaciones negociables en dólares |
| LECAP y BONCAP | Clase Letras y BONCAP en pesos |
| CER, TAMAR, Dólar linked | Clase Ajustables por CER, Tasa variable TAMAR o Dólar linked |
| Ganancia ya cobrada, Ganancia o pérdida en papel | Hay historial |

## Diseño

- Un único HTML **sin recursos externos**: sin CDN, fuentes web, imágenes remotas ni JavaScript. Los gráficos
  son SVG en línea, generados en Python.
- Pensado para imprimir en **A4 vertical**: `@page {size: A4; margin: 0}` y una hoja por bloque (1: resumen, tu
  cartera hoy y composición; 2: tus títulos; 3: lo que ya ganaste; 4: próximos cobros y rendimiento; 5: cobros
  futuros por título y por año; 6: aclaraciones y glosario). Pie de página con el nombre del asesor, "Uso exclusivo del cliente" y el título de la hoja. No se numeran
  las páginas: una tenencia larga ocupa más de una página impresa y el número quedaría mal.
- Las reglas para pantallas angostas van dentro de `@media screen`. Si no, Chrome las aplica al imprimir
  (210 mm ≈ 794 px) y desarma la grilla: es lo que pasó en el prototipo.
- Fondo blanco, un color principal oscuro para los dólares y los títulos, un segundo color para los pesos y
  los resultados positivos, y uno cálido para los negativos.
- Números en formato argentino ("1.234.567,89"), porcentajes con coma y fechas cortas en español ("16 nov
  2026"). Importes en pesos sin decimales y en dólares con dos.
- Una cartera con muchas posiciones puede ocupar más hojas. Ninguna fila se parte entre páginas
  (`break-inside: avoid`).
- El texto se escapa siempre: especies, nombres y tickers vienen de archivos.

## Privacidad

El informe tiene el nombre y los datos del cliente, así que se guarda en la carpeta de datos, nunca en el
repositorio. El código no tiene nombres de clientes. Las pruebas usan `fixtures/informe/`, que es ficticia.
