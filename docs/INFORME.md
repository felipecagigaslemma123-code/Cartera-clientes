# Informe para el cliente

Versión 1.0 · 16/11/2026 · Pedido de Felipe para la etapa 12.

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
- Si el dashboard tiene más de 3 días, el comando lo avisa por consola con la antigüedad ("el dashboard tiene
  9 días") y escribe el informe igual.
- Errores: si falta el dashboard o su bloque de datos, el comando termina con código distinto de cero, un
  mensaje claro y **sin escribir nada**.

## Contenido

Las secciones van en este orden. Una sección sin datos no se muestra: no queda un recuadro vacío.

### 1. Resumen

- Encabezado con el nombre del asesor (`perfil.asesor`), "Informe de cartera" y la fecha. Abajo, el nombre del
  cliente (`perfil.nombre` o `datos.cliente.nombre`) y una línea con la fecha y el dólar MEP de valuación.
- Tres indicadores:
  - **Patrimonio total** = `integral.patrimonio_final`, con su equivalente en dólares al MEP. Si no hay dato,
    dice "sin dato".
  - **Invertido en títulos**: la suma de las valuaciones y su peso en el patrimonio.
  - **Efectivo**: el de `integral.efectivo`, con pesos y dólares por separado. Un saldo faltante dice "sin dato", sin
    signo de moneda.

### 2. Composición

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

Debajo de la dona va una frase: "**N % de la cartera está en títulos que pagan en dólares**". N es el peso de
las dos clases en dólares. La frase no se muestra si N es cero.

### 3. Tenencia

Tabla con título (ticker en negrita y descripción abajo), cantidad, precio, valuación, peso, "Vs. compra" y
vencimiento.

- Descripción: la `especie`. En una letra se usa "<familia> dd/mm/aaaa", con la familia y el vencimiento del
  bloque `letras`.
- "Vs. compra" = `resultado / costo`. Si falta el costo, "—". Una nota aclara que es la variación de precio en
  pesos y **no incluye las rentas cobradas**.
- Orden: por clase (en el orden de la composición) y, dentro de cada clase, por valuación.

### 4. Rendimiento al precio de compra

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
- Nota: la tasa de un bono en dólares está expresada en dólares, la de una letra es efectiva anual en pesos y
  un título ajustable depende de supuestos del REM del BCRA.

### 5. Cobros por título

Tabla con título (y su cantidad de compras), moneda de cobro, fecha y monto del próximo pago, total a cobrar
hasta el vencimiento y TIR. Debajo, un indicador por moneda con el **total a cobrar**, sumado solo dentro de
cada moneda: `ARS`, `USD MEP` y `USD cable` van en indicadores separados. **Nunca se suman monedas.**

- Total a cobrar de un título del flujo: `total_proyectado`. De una letra: `pago_vencimiento`.
- Una letra ajustable (LECER, LELINK) aparece tanto en `letras` como en `flujo_fondos`: se toma solo la del
  flujo, que tiene el pago proyectado.
- Próximo pago de un título del flujo: `proximo_pago`. De una letra: el vencimiento.

### 6. Próximos cobros

Lista con los próximos siete eventos posteriores a la fecha del informe: fecha, título, concepto ("Renta",
"Renta y amortización" o "Vencimiento") e importe con su moneda. Un pago estimado dice "estimado".

- Sale de los pagos `proyectado` de cada posición del flujo y de los vencimientos de las letras.
- Concepto: "Vencimiento" si la fecha es el `vencimiento` de la posición (o, si la posición no lo tiene, si
  es el último pago de su lista) y en las letras; si no, "Renta y amortización" cuando amortiza y "Renta"
  cuando no.
- Orden: por fecha y, a igual fecha, por ticker.

### 7. Cobros por año

Barras por año con los cobros en dólares de `flujo_fondos.calendario`, una barra por moneda (MEP y cable,
juntas pero sin apilarse) y el valor arriba de cada una. Los pesos se informan en el indicador de la
sección 5, no en este gráfico, porque su escala lo aplastaría.

### 8. Resultados desde el inicio

Solo si existe `historial`. Tres indicadores:

- **Ganancia realizada** = `historial.total_conocido`.
- **Rentas cobradas**: pesos y dólares de `ingresos.renta`, por separado.
- **Resultado acumulado** = patrimonio total − `aportes.equivalente_ars` + `retiros.equivalente_ars`. Si falta
  el patrimonio, "sin dato".

Debajo, barras con el resultado de cada operación de `historial.realizados`, ordenadas por fecha. Las positivas
van hacia arriba en un color y las negativas hacia abajo en otro. Cada barra lleva el ticker y el mes. Con más de
14 operaciones, una barra por mes con la suma del resultado, solo con el mes, y una nota con la cantidad de
operaciones: con 40 barras no se lee nada.

Nota con el desglose: ventas y vencimientos (`realizado_extracto`), rentas (`ingresos.renta.equivalente_ars`) y
otros (cauciones, FCI y dividendos, netos de gastos). Aclara que los importes son **pesos nominales sin ajuste
por inflación**.

### 9. Aclaraciones

Texto fijo: los cobros futuros salen de las condiciones de emisión y suponen mantener los títulos hasta el
vencimiento, sujetos al pago del emisor; los dólares no se convierten ni se suman a los pesos; la valuación es
la del último precio de la fecha del informe; el informe **no constituye una recomendación de inversión**.

## Diseño

- Un único HTML **sin recursos externos**: sin CDN, fuentes web, imágenes remotas ni JavaScript. Los gráficos
  son SVG en línea, generados en Python.
- Pensado para imprimir en **A4 vertical**: `@page {size: A4; margin: 0}` y una hoja por bloque (1: resumen,
  composición y tenencia; 2: rendimiento y cobros por título; 3: próximos cobros, cobros por año, resultados y
  aclaraciones). Pie de página con el nombre del asesor, "Uso exclusivo del cliente" y el título de la hoja. No se numeran
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
