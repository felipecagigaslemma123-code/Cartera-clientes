# Fuente IAMC/BYMA — relevamiento y extractor experimental

Versión 1 · Relevamiento 05–06/11/2026 · Cierre relevado: **05/11/2026** · Liquidación: **06/11/2026**.

Este trabajo conserva evidencia pública para revisión. No integra IAMC a `src/cartera`, no cambia fórmulas aprobadas, no habilita nuevos instrumentos ni transforma proyecciones en pagos ciertos. Los precios son **de cierre**, no en vivo. No contiene datos de clientes.

## 1. Adquisición, ubicación y confiabilidad

Fuente principal: [Resumen Diario de Mercado](https://www.iamc.com.ar/informediario/). El HTML contiene un único `<script id="payload" type="application/json">`. Se obtiene con un GET normal, sin login, cookies de sesión ni ejecutar JavaScript. La página interpreta ese JSON para mostrar los paneles.

### Mapa de secciones

| Sección / URL de navegación | Datos en HTML inicial | Carga adicional declarada |
|---|---|---|
| [Renta fija](https://www.iamc.com.ar/informediario/#rf) | `tp`, `on`, `din`: 110 títulos públicos y 255 ON | No para esos tres bloques |
| [Bonos](https://www.iamc.com.ar/informediario/#cbon) | `calc`: 356 instrumentos; metadatos e indicadores en `tp/on.rows` | No |
| [Letras](https://www.iamc.com.ar/informediario/#clet) | 8 filas `tp.rows` con `seg="lec"`, más precios y montos completos en `calc.ins` | No |
| [Caución](https://www.iamc.com.ar/informediario/#ccau) | parámetros, curva e historia en `din.cauc`; metadatos de garantías en `ccau` | `d/ccau.json` para lista de garantías |
| [Metodologías](https://www.iamc.com.ar/informediario/#met) | constante JavaScript `MET`; no está en el JSON | No |
| Variables macro de portada | `macro.vars`, seis observaciones con fecha propia | No |
| [Padrón](https://www.iamc.com.ar/informediario/#ins) | `ins.fecha`, `rows=[]`; resumen anuncia 6.445 símbolos | `d/ins.json` |
| Acciones | 10 vistas previas de 71 especies | `d/acc.json` |
| CEDEARs | 10 vistas previas de 399 especies | `d/ced.json` |
| Opciones | `rows=[]`; resumen anuncia 1.196 series | `d/op.json` |
| Índices | `ibi` parcial | `d/ibi.json` |

Los fragmentos `#rf`, `#cbon`, etc. son navegación dentro del mismo documento; no son APIs ni cierres distintos. `cargarDif(id)` solo hace `fetch` si el ID está en `payload.__dif`. Esas URLs relativas se resuelven bajo `https://www.iamc.com.ar/informediario/` y **no incorporan la fecha**. Los contenidos se regeneran; no deben usarse los nombres de archivo como identificación del cierre.

### Peticiones efectivamente realizadas

Se conservó una adquisición de cada URL distinta durante el día argentino: HTML inicial, `robots.txt` y los seis recursos declarados. Se guardaron cuerpo, URL solicitada/final, fecha de consulta, estado HTTP, cabeceras y SHA-256. El detalle está en [red_observada.json](../fixtures/iamc/2026-11-05/red_observada.json).

**Resultado de los seis diferidos:** `op`, `ced`, `acc`, `ibi`, `ins` y `ccau` devolvieron HTTP 200 con `Content-Type: text/html` y el mismo cuerpo que la portada. No entregaron JSON en esta consulta. Se conservaron como `diferido_<id>.respuesta` y sus metadatos; no se reintentaron, no se adivinaron URLs alternativas y no se completaron filas faltantes. Un 200 por sí solo no prueba disponibilidad.

La red de todas las secciones no se capturó con DevTools/HAR: se verificaron el ruteo del código y respuestas HTTP controladas. Antes de ampliarse el encargo se observaron la portada, el cierre y los campos de Letras en el navegador, y se rechazó Analytics con **No, gracias**. Esa pestaña temporal se cerró al interrumpirse el turno; no se recargó el cierre para repetir la navegación. La calculadora de bonos, caución y los supuestos se relevaron en su código público, sin afirmar una prueba visual interactiva completa.

### Robots, términos y frecuencia

[robots.txt](https://www.iamc.com.ar/robots.txt) también devolvió HTTP 200 con el mismo HTML. No constituye un robots normativo verificable ni una autorización de uso. En el HTML analizado no se encontró licencia abierta, contrato de API, ni permiso explícito de redistribución. Los avisos visibles indican finalidad informativa y consentimiento previo para GA4; no equivalen a una licencia de datos. No se enviaron correos ni formularios.

El extractor no ejecuta scripts ni carga Analytics. Conserva una caché por día argentino y URL; bloquea corridas concurrentes y registra el intento **antes** de consultar. También consume el intento si la descarga falla o el contenido es inválido: no hay reintentos ese día ni opción `--force`. Se debe mantener la misma carpeta de caché entre corridas; moverla o borrarla pierde ese registro. Si un robots válido prohíbe la ruta, se detiene. No se instalaron tareas programadas.

### Históricos

No se identificó un selector ni una API pública documentada para solicitar el documento completo de un cierre anterior. No se probaron parámetros de fecha inventados. Hay historias parciales dentro del cierre: `tp.histi` y `on.histi` incluyen 21 ruedas, del 07/10 al 05/11/2026; sus ejes y huecos se conservan. TP contiene 107 series, 87 de TIR y 20 de TEM; ON 244 de TIR. No son cinco cierres completos con sus flujos históricos. Macro contiene solo el último punto de cada variable; `n_obs` cuenta observaciones del insumo, pero no entrega esa serie.

También se detectaron historias de caución, simultáneas, índices, volúmenes mensuales y dividendos. Sus rangos y límites están en [mapa_fuente.json](../fixtures/iamc/2026-11-05/mapa_fuente.json). Para crear un archivo propio de cierres íntegros hay que conservar las respuestas diarias desde ahora, sin llamar “histórico” al precio actual etiquetado con otra fecha.

## 2. Calculadora de bonos: datos y unidades

Los datos de un instrumento se cruzan por ticker y grupo (`tp`/`on`), conservando tres objetos separados: `calc.ins`, `tp/on.rows` y `cat`. No se deduce la moneda ni la estructura por el sufijo del ticker. Las muestras por bono conservan esos objetos sin redondear ni armonizar sus cronogramas.

### Identificación y condiciones del informe

| Campo crudo | Significado | Unidad / criterio |
|---|---|---|
| `tk`, `g`, `seg` | ticker, grupo y segmento | Texto; `g` distingue TP/ON; `seg` identifica CER, duales, etc. |
| `em`, `de`, `ti`, `sec` | emisor, descripción, tipo y sector | Texto del proveedor, sin corregirlo |
| `ley`, `isin` | ley aplicable e ISIN | Códigos; `ARG`, `NY`, etc. no son monedas |
| `me`, `mp` | moneda de emisión y de pago | `ARS`, `USD`, `MEP`, `CCL`; conservar la categoría recibida |
| `fe`, `fv`, `pc`, `pam` | emisión, vencimiento, próximo cupón y próxima amortización | Fechas ISO; `null` indica ausencia |
| `est`, `idx`, `aj` | estructura, índice y ajuste | Fija, variable, dual; CER/DL, etc. La ausencia de `idx` no convierte un dual en fijo |
| `fc`, `fam`, `cuo` | frecuencia de renta, de amortización y número de cuotas | Texto / cantidad; no tasa |
| `cup`, `ct`, `mg` | cupón, tipo de tasa y margen | Tasas en tanto por uno; `ct` distingue TNA/TEM. No multiplicar un cupón mensual como si fuera anual |
| `mto` | monto emitido | Importe en moneda de emisión; el dato crudo no está en millones |

### Precios e indicadores del informe

| Campo | Significado | Unidad / interpretación |
|---|---|---|
| `pxa` | cierre de la especie negociada | Precio por 100 VN en moneda de negociación; en las muestras principales es ARS |
| `px` | cierre en unidad de valuación/pago | Precio por 100 VN; puede estar convertido. En DL es unidad vinculada, no dólares a cobrar |
| `fx`, `fxr` | conversión y etiqueta del proveedor | ARS por unidad USD/vinculada cuando corresponde; conservar `MEP`, `CCL`, `A3500_BASE_DL`, etc. |
| `ytm` | TIR publicada | **Porcentaje**: `14.3033` significa 14,3033% |
| `dm`, `cx`, `wal` | duration modificada, convexidad, vida media | Años, factor de convexidad y años; no porcentaje. `dml` es duration modificada en días para capitalizables |
| `par`, `cy` | paridad y current yield | Porcentajes: 80,456 significa 80,456%, no factor 80,456 |
| `vt`, `vr`, `ai` | valor técnico, residual e intereses corridos | Importes por 100 VN original, con ajuste que corresponda; VR puede superar 100 en CER |
| `plz` | plazo residual | Días corridos desde la liquidación del cierre |
| `tem`, `tea`, `tna`, `rp` | tasas equivalentes y retorno de período en capitalizables | **Tanto por uno**: `0.015815` es 1,5815%; no tienen la escala de `ytm` |
| `mv` | monto al vencimiento resumido | Importe por 100 VN; puede estar redondeado frente a `calc.ins.f` |
| `tl`, `ttl` | tasa y clase de tasa contractual de capitalizables | Tasa decimal y etiqueta TNA/TEM |
| `p1/p2/pg`, `mv1/mv2`, `tem1/tem2`, `tea1/tea2` | patas del dual, ganadora y resultados por pata | Texto, importes por 100 VN y tasas decimales; no sumar las dos patas |
| `pxd`, `dytm` | variación de precio y de TIR | Porcentaje de precio y puntos básicos de tasa |
| `amo`, `ren` | cronogramas resumidos de amortización y renta | Listas `[fecha ISO, importe por 100 VN]`; no usar como sustituto automático del flujo de calculadora |
| `fxi` | implícitos por especies y sus fechas | `mep/ccl`, `fm/fc`, `po/pd/pc`; no equivalen necesariamente a los índices macro del encabezado |

No confundir un precio convertido de AL30 con el precio efectivamente operado de AL30D o AL30C. El HTML trae precios e implícitos de esas especies y los muestra por separado; algunas notas metodológicas de moneda conservan una explicación anterior que dice que no están disponibles. Para una integración futura hay que validar los campos presentes y su fecha, no elegir silenciosamente entre textos contradictorios.

### Registro de calculadora y flujo completo

| Campo `calc.ins` | Significado | Unidad |
|---|---|---|
| `tk`, `g`, `seg`, `k` | identificación y familia del motor | `fix`, `cer`, `dl`, `var`, `cap`, `capv`; no son tasas |
| `cur` | unidad de los flujos base | `ARS`, `USD`, `DL`; `DL` no es una moneda de cobro ISO |
| `px`, `pxa` | precios completos en unidad de flujo y en ARS | Por 100 VN, con más precisión que las columnas resumidas |
| `fxc`, `fxr` | tipo de cambio usado por el modelo y referencia | Conservar valor y etiqueta; el payload no garantiza fecha individual del A3500 base |
| `liq` | liquidación desde la que se cuentan los plazos | Fecha ISO, distinta del cierre |
| `f[j][0]` | plazo de ese pago | Días corridos desde `liq` |
| `f[j][1]`, `f[j][2]` | amortización y renta base | Importe por 100 VN, en `cur` |
| `f[j][3]` | base de interés variable | Coeficiente del cupón para reproyectar la tasa; no se suma como dinero |
| `ini`, `cv` | inicio del período de cupón y convención de devengamiento | Desplazamiento en días respecto de `liq`; `"30"` indica 30/360 US para el cupón |
| `cal` | diferencia que declara el generador | Puntos básicos; se conserva, pero no se usa para forzar el control de TIR |
| `v` | parámetros de cupón variable | Tasa vigente, margen, fracción devengada y eventual regla fija/variable |
| `c` | capitalizable indexado / dual | `n` meses totales, `me` transcurridos, regla MAX/MIN y `patas` con monto, TEM y margen |

Para los flujos crudos de la calculadora: `fecha = liq + f[j][0] días`, `renta = f[j][2]`, `amortización = f[j][1]`, `total = renta + amortización`. Se conservan también el desplazamiento y la fila original. No se aplicó ajuste adicional de fines de semana o feriados a los pagos. En CER/DL esos son flujos base al índice/tipo de cambio de referencia, no promesas de pesos nominales futuros; las proyecciones nominales requieren los supuestos del usuario.

### Supuestos editables observados en el código

La calculadora permite cambiar precio o tasa objetivo, fecha de liquidación, base ACT/365 o 30/360 US para descontar, moneda/especie, tipo de cambio, nominales, comisión de compra y comisión sobre intereses o intereses más amortización. Precio ingresado se interpreta como **sucio**, igual que el cierre. No copiar a bonos la distinción de precio limpio usada en otro módulo sin revisar esta convención.

En TAMAR/BADLAR se cambia el índice futuro; el cupón en curso combina lo devengado con lo supuesto. En CER se proyecta inflación mensual y se distingue la TIR real de la nominal; el valor inicial puede usar breakeven contra la curva fija. En DL se modifica la devaluación mensual; cero reproduce el cierre a tipo de cambio constante. En duales se proyectan ambas patas y se aplica MAX/MIN. Son reglas relevadas del simulador, no una aprobación del modelo para cartera.

TMVE8 aparece como **dual TAMAR/DL**, con regla MAX y denominación USD/pago ARS; no se lo clasificó como una TAMAR pura. Sus datos crudos incluyen ambas patas. En esta captura la pata ganadora del cierre es TAMAR.

## 3. Control independiente de TIR

Se implementó exclusivamente en `tools/iamc_control_tir.py`, fuera de producción. Resuelve por bisección la tasa que iguala `calc.ins.px` al valor actual de `calc.ins.f`, con año ACT/365, precio sucio, flujos base y comisiones cero. La TIR publicada y `cal` **no participan** en la resolución; solo se comparan después. 1 pb = 0,01 puntos porcentuales.

| Ticker | TIR publicada % | Recalculada % | Diferencia pb | Resultado |
|---|---:|---:|---:|---|
| AL30 | 14.303300 | 14.303282 | -0.001805 | Menor a 1 pb |
| TX26 | — | — | — | Ausente en calculadora, informe y catálogo de este cierre |
| TZXS7 | 5.261800 | 5.261777 | -0.002262 | Menor a 1 pb |
| TMVE8 | 35.215100 | 35.215062 | -0.003796 | Menor a 1 pb |
| YM34O | 8.629600 | 8.629582 | -0.001837 | Menor a 1 pb |

**AL30: diferencia adicional material.** Al repetir el cálculo con el cronograma `amo + ren` del informe, en lugar del flujo de calculadora, resulta **13,482322802%**, frente al 14,3033% publicado: **−82,097720 pb**. Por ejemplo, para 09/01/2028 el informe trae renta 0,18 y la calculadora 0,42 por 100 VN. Se conservaron ambos sin corregirlos. La coincidencia de TIR de la calculadora no valida el otro cronograma ni las condiciones contractuales del título.

**TX26:** no está en ninguno de los tres árboles de este cierre. Su muestra lo informa expresamente; no se sustituyó por otro BONCER ni por una observación de otra fecha. Por ello el control pedido pudo completarse para **4 de 5** instrumentos, no para cinco.

Resultado numérico completo, fechas, cada pago y control cruzado: [control_tir.json](../fixtures/iamc/2026-11-05/control_tir.json). La tolerancia se aplicó al valor no redondeado. La prueba no certifica pagos efectivos ni aprueba la metodología para producción.

## 4. Calculadora de Letras

Fuente: [Letras](https://www.iamc.com.ar/informediario/#clet). Tiene modo libre y por instrumento, precio desde TEM o TEM desde precio, liquidación, vencimiento, precio de negociación, valor final, comisión ingresada como TNA y tipo de cambio opcional para breakeven. Precios y valor final deben compartir base nominal. La UI por instrumento toma precio y valor final completos de `calc.ins` cuando están disponibles; `tp.rows.mv` es un resumen redondeado.

| Campo | Ruta | Unidad |
|---|---|---|
| Precio | `tp.rows.pxa/px`; completo en `calc.ins.pxa/px` | ARS por 100 VN en estas dos muestras |
| Vencimiento / liquidación | `tp.rows.fv`, `tp.fecha_liq` | Fechas ISO |
| Valor final | `tp.rows.mv`; completo en `calc.ins.f[0][1]` para `k=cap` | ARS por 100 VN |
| TEM, TEA, TNA del informe | `tp.rows.tem/tea/tna` | Tasas decimales, multiplicar por 100 solo para presentar |
| Tasa contractual | `tp.rows.tl`, `ttl` | Tasa decimal y etiqueta, distinta del rendimiento de compra |
| Días | `plz`, o diferencia de fechas elegidas | Corridos, no días hábiles |

| Ticker | Tipo fuente | Vencimiento | Precio | Valor final completo | TEM informe % | TEA informe % | TNA informe % |
|---|---|---|---:|---:|---:|---:|---:|
| S30N6 | LETRA | 2026-11-30 | 128.29 | 129.888227 | 1.5815 | 20.7188 | 18.9779 |
| T30A7 | BONO | 2027-04-30 | 139.2 | 157.341021 | 2.1521 | 29.1117 | 25.8248 |

**Convenciones distintas, reconocidas por la fuente:** la calculadora de Letras usa `TEM = (Pvto/costo)^(30/días) − 1` sobre días corridos; el informe usa mes de `365/12` días. La propia tarjeta metodológica lo explica. TEA de esa calculadora capitaliza doce meses de 30 días; no tiene por qué coincidir con la TEA ACT/365 del informe. No se cambió el motor aprobado del Toolkit para hacerlo coincidir con otra convención. Tampoco se confundió ese cociente sobre días corridos con el algoritmo contractual de VPV 30/360 del Tesoro.

## 5. Caución

Fuente: [Caución](https://www.iamc.com.ar/informediario/#ccau). La fórmula usa interés simple, `I=C×TNA×n/365`, con días **corridos**. Los días **hábiles** sirven para seleccionar la referencia de mercado y para el calendario; no reemplazan a `n` en el interés.

La comisión es una TNA prorrateada, con mínimo opcional y base capital o monto final. Derechos y administración usan base elegible y `min(n,90)/90`. La UI propone derechos 0,045%, IVA 21%, IVA sobre comisión/gastos activado y sobre derechos desactivado; al elegir tomadora propone administración 0,045%. Son defaults de la herramienta, no una comprobación de su vigencia impositiva. Permite mínimo, gastos fijos, IVA sobre intereses y cobro inicial o al vencimiento. La TNA/TEA neta o CFT se obtiene de los desembolsos/cobros reales de cada punta, no restando porcentajes a la TNA bruta.

La referencia por plazo está en `din.cauc.curva[moneda]`: `p` hábiles, `pc` corridos, `v` VWAP TNA en porcentaje, `c` última TNA, `a/lo/hi` apertura/mínimo/máximo, `m/vn` montos y `n` número de operaciones; `vt` es vencimiento. El selector usa `v`, no `c`. El detalle completo se conserva en `muestras_extractor/mercado_dinero.json`.

**Límite observado:** falta el plazo 1 en la curva ARS. El código elige la primera fila como fallback (`CC_ON`): 4 hábiles / 6 corridos, VWAP 29,6155%, aunque el plazo inicial de la operación sea un día. No debe interpretarse como una tasa overnight comprobada ni como tasa pactada del cliente. La UI permite cargar la tasa manual.

La lista de aforos/garantías está diferida; anuncia 1.951 especies, 1.076 FCI y 658 precios. Su petición devolvió HTML, por lo que no se validaron aforos individuales ni cobertura real. [caucion_metodologia.json](../fixtures/iamc/2026-11-05/caucion_metodologia.json) conserva defaults, expresiones y ubicaciones exactas.

### Curva de caución observada por plazo

Valores crudos del cierre 05/11/2026. La calculadora selecciona la **VWAP**, expresada como TNA porcentual; no interpola automáticamente los plazos sin observación. La columna última es otra medida y puede diferir mucho de la VWAP. En ARS, plazo 4, la última aparece como 190%, dato que se conserva y requiere revisión antes de usarlo.

| Moneda | Hábiles (`p`) | Corridos (`pc`) | VWAP TNA % (`v`) | Última TNA % (`c`) | Vencimiento (`vt`) |
|---|---:|---:|---:|---:|---|
| ARS | 4 | 6 | 29.6155 | 190.0 | 2026-11-11 |
| ARS | 5 | 7 | 23.8056 | 45.0 | 2026-11-12 |
| ARS | 6 | 8 | 23.2438 | 28.0 | 2026-11-13 |
| ARS | 7 | 11 | 23.613 | 30.0 | 2026-11-16 |
| ARS | 8 | 12 | 23.0048 | 29.0 | 2026-11-17 |
| ARS | 9 | 13 | 23.4457 | 24.0 | 2026-11-18 |
| ARS | 10 | 14 | 24.0173 | 30.9 | 2026-11-19 |
| ARS | 11 | 15 | 24.4183 | 30.0 | 2026-11-20 |
| ARS | 13 | 19 | 23.6163 | 23.7 | 2026-11-24 |
| ARS | 14 | 20 | 22.6103 | 22.6 | 2026-11-25 |
| ARS | 15 | 21 | 22.2318 | 24.7 | 2026-11-26 |
| ARS | 16 | 22 | 23.3857 | 25.0 | 2026-11-27 |
| ARS | 17 | 25 | 23.8127 | 30.0 | 2026-11-30 |
| ARS | 18 | 26 | 22.0562 | 30.0 | 2026-12-01 |
| ARS | 19 | 27 | 24.3805 | 28.2 | 2026-12-02 |
| ARS | 20 | 28 | 23.9872 | 26.2 | 2026-12-03 |
| ARS | 21 | 29 | 25.4388 | 30.0 | 2026-12-04 |
| ARS | 24 | 34 | 24.5163 | 24.5 | 2026-12-09 |
| ARS | 25 | 35 | 24.7189 | 29.0 | 2026-12-10 |
| ARS | 26 | 36 | 21.3157 | 21.0 | 2026-12-11 |
| ARS | 30 | 42 | 20.6639 | 23.5 | 2026-12-17 |
| ARS | 32 | 46 | 20.3 | 20.3 | 2026-12-21 |
| ARS | 39 | 55 | 30.0 | 30.0 | 2026-12-30 |
| ARS | 64 | 90 | 20.0 | 20.0 | 2027-02-03 |
| USD | 4 | 6 | 2.013 | 0.5 | 2026-11-11 |
| USD | 5 | 7 | 1.59 | 1.0 | 2026-11-12 |
| USD | 6 | 8 | 1.8792 | 1.3 | 2026-11-13 |
| USD | 7 | 11 | 1.5658 | 2.5 | 2026-11-16 |
| USD | 8 | 12 | 2.8929 | 3.0 | 2026-11-17 |
| USD | 9 | 13 | 2.0961 | 2.7 | 2026-11-18 |
| USD | 10 | 14 | 1.6289 | 1.2 | 2026-11-19 |
| USD | 13 | 19 | 2.2146 | 2.4 | 2026-11-24 |
| USD | 16 | 22 | 2.0 | 2.0 | 2026-11-27 |
| USD | 17 | 25 | 2.0513 | 2.2 | 2026-11-30 |
| USD | 20 | 28 | 1.994 | 2.0 | 2026-12-03 |
| USD | 21 | 29 | 1.8314 | 2.0 | 2026-12-04 |
| USD | 25 | 35 | 2.5 | 2.5 | 2026-12-10 |
| USD | 31 | 43 | 2.6082 | 2.6 | 2026-12-18 |
| USD | 64 | 90 | 2.75 | 2.75 | 2027-02-03 |
| USD | 86 | 120 | 3.0005 | 3.0 | 2027-03-05 |
| EXT | 5 | 7 | 4.9374 | 2.5 | 2026-11-12 |

`EXT` conserva la categoría de cable que trae el bloque; no se mezcló con USD local. Las fechas y el plazo de la curva son referencias de esa rueda, no la tasa pactada ni el vencimiento de una nueva operación.

## 6. Variables macro y padrón

### Macro

`macro.vars` conserva fecha individual (`f`), fecha anterior (`fp`), valor (`v`), unidad (`u`), variación (`dv`), clase de variación (`dlt`) y conteo de observaciones (`n_obs`). La única procedencia explícita del bloque es **`Insumos.xlsx`**; el encabezado identifica BYMA, pero el HTML no entrega una URL upstream por serie. No se afirmó haber descargado directamente del BCRA ni del proveedor de EMBI.

| Variable | Valor observado | Fecha | Unidad del nivel | Variación |
|---|---:|---|---|---|
| Índice Dólar BYMA | 1571.18 | 2026-11-05 | ARS/USD, índice BYMA | -0.63 pct vs 2026-11-04 |
| Índice Dólar CCL | 1666.27 | 2026-11-05 | ARS/USD, índice CCL | -0.77 pct vs 2026-11-04 |
| Dólar A3500 | 1545.4 | 2026-11-05 | ARS/USD, A3500 | -0.2 pct vs 2026-11-04 |
| TAMAR | 23.56 | 2026-11-04 | % TNA | -0.44 pp vs 2026-11-03 |
| CER | 865.4229 | 2026-11-05 | Coeficiente de índice | 0.06 pct vs 2026-11-04 |
| Riesgo país · EMBI+ | 852.0 | 2026-11-04 | Puntos básicos | 21.0 pb vs 2026-11-03 |

`pct` es variación porcentual, `pp` puntos porcentuales y `pb` puntos básicos. No se estampa la fecha máxima 05/11 sobre TAMAR o EMBI, que corresponden al 04/11. Tampoco se igualan el índice macro, el implícito de un bono y el A3500 base de un DL. Por ejemplo, TMVE8 trae `fxc=1490.8431` con `fxr=A3500_BASE_DL`, mientras la macro A3500 es 1545,40. Falta identificar plenamente la fecha y construcción de esa base antes de usarla como evidencia suficiente para R006.

### Padrón

Se conserva `padron.json` con la porción inicial y su marcador diferido, y la respuesta HTTP cruda fallida. El catálogo `cat` sí aporta 835 instrumentos de los informes y permite recuperar ISIN/código de caja en las muestras presentes, pero no reemplaza el padrón completo de 6.445 símbolos ni garantiza la rueda.

El código publica este esquema posicional para `ins.rows`, que aquí no se pudo poblar:

| Índice | Campo | Interpretación |
|---:|---|---|
| 0–3 | `tk`, `de`, `ca`, `em` | ticker, descripción, categoría, emisor |
| 4 | `mo` | 0 pesos; 1 dólares; 2 cable |
| 5–6 | ISIN, código de caja | Identificadores, conservar como texto y no convertir `eid` de BYMA en código de caja |
| 7–8 | vencimiento, valor nominal | Fecha y valor nominal declarado; no precio |
| 9 | plazo | 1 CI; 2 24 hs; 3 ambos |
| 10–12 | estado, clase, rueda | Estado crudo; clase 0 variable/1 fija; rueda 0 concurrencia/1 bloque |
| 13 | enlace al informe | `grupo|ticker|rol|segmento` |

Moneda y rueda deben provenir de esos campos, nunca de letras finales del ticker. El catálogo alternativo usa `tk`, `i` para ISIN, `c` para código de caja, `ed/ec` para alias, `md/mp` para denominación/pago y `mn` cuando declara moneda de negociación.

## 7. Uso y archivos entregados

Las copias HTTP están en `fixtures/iamc/2026-11-05/`. `informediario.html` es el original íntegro; los archivos de muestra son subobjetos extraídos de ese original, no respuestas de una API individual por ticker. `*.http.json` conserva la adquisición; los demás JSON indican su procedencia. Nunca se cambió el original para hacer coincidir resultados.

- `cierres/2026-11-05.json`: JSON diario, con cierre/liquidación, calculadoras, macro, catálogo, porción de padrón, informes, caución y trazabilidad.
- `2026-11-05/muestras_extractor/bonos/`: AL30, TZXS7, TMVE8 y YM34O; TX26 tiene archivo de ausencia explícita.
- `2026-11-05/muestras_extractor/letras/`: S30N6 y T30A7, con informe y registro de calculadora completos.
- `2026-11-05/control_tir.json`: comparación y flujos fechados de los cuatro disponibles, ausencia de TX26 y control cruzado del informe.
- `2026-11-05/metodologias.json` y `metodologias_texto.txt`: expresiones matemáticas copiadas literalmente, con fragmento de origen, líneas y hash; no se ejecuta el JavaScript.
- `2026-11-05/red_observada.json`: URLs, respuestas, ruteo y límite de la observación de navegador.
- `2026-11-05/mapa_fuente.json`: completitud, macro, padrón e históricos.

### Reprocesar el cierre conservado sin descargar

Desde la raíz del proyecto, con Python 3.9:

```bash
~/.venvs/cartera/bin/python -B tools/iamc_extraer.py --html fixtures/iamc/2026-11-05/informediario.html --salida fixtures/iamc/cierres --muestras fixtures/iamc/2026-11-05/muestras_extractor
~/.venvs/cartera/bin/python -B tools/iamc_control_tir.py --html fixtures/iamc/2026-11-05/informediario.html --salida fixtures/iamc/2026-11-05/control_tir.json
```

### Descargar un cierre diario cuando corresponda

```bash
~/.venvs/cartera/bin/python -B tools/iamc_extraer.py --cache fixtures/iamc --salida fixtures/iamc/cierres
```

El modo online revisa robots y consulta solo el HTML inicial; no pretende descargar ni completar los diferidos. La caché del 05/11/2026 ya está preparada: una ejecución con ese día la usa sin red. Al ejecutarse en otro día argentino el modo online puede hacer una adquisición nueva; para revisar esta entrega sin descargar debe usarse `--html`. La fecha del JSON de salida es la **fecha de cierre interna**, no la fecha del reloj ni del nombre del archivo. Un cambio de estructura, duplicados o datos no finitos termina con error; no se publica un cierre vacío como válido. Los faltantes explícitos se conservan y advierten.

Se puede extraer nuevamente la metodología con `tools/iamc_metodologias.py --help`; esa herramienta solo lee un HTML local. El control de TIR y el extractor de fórmulas son auxiliares de investigación, no motores financieros aprobados ni dependencias de cartera.

## 8. Límites y decisión para una integración posterior

Antes de integrar hay que resolver: disponibilidad de los diferidos en el despliegue real, discrepancia de flujos de AL30, ausencia de TX26 en esta muestra, procedencia/fecha del FX base DL y revisión de las convenciones que difieren entre informe y calculadora. No hay prueba de una API estable ni de cierres históricos completos bajo demanda.

La extracción de datos presentes es reproducible, pero no valida las condiciones contractuales de todos los instrumentos. R006 y los demás gates conservan su estado. No se modificó ningún archivo de producción, prueba original, fixture anterior o documento preexistente durante este encargo; no se hicieron commits.

## 9. Fórmulas literales de la fuente

Las expresiones siguientes provienen de [Metodologías](https://www.iamc.com.ar/informediario/#met), secciones Renta Fija y Calculadoras. Se conserva la notación original; `_{...}` y `^{...}` representan subíndices y exponentes del HTML. La línea corresponde a `fixtures/iamc/2026-11-05/informediario.html`. Los JSON adjuntos conservan también el HTML de cada expresión y su fragmento literal.

Estas tarjetas no forman una convención única: el motor de bonos por defecto descuenta ACT/365; el devengamiento puede usar 30/360 US; el glosario de RF contiene una TNA simple 360, y Letras usa mensualización de 30 días. No se combinaron ni corrigieron para fingir equivalencia.

### Renta Fija

- **Precios y valuación · Precio teórico** (línea 9269): `P(y) = Σ_{t=1..n} CF_{t} / (1+y)^{τ_{t}}`
- **Precios y valuación · Precio sucio** (línea 9273): `Precio_{sucio} = Precio_{cierre}`
- **Precios y valuación · Precio limpio** (línea 9277): `Precio_{limpio} = Precio_{sucio} − Intereses_{corridos}`
- **Precios y valuación · Intereses corridos** (línea 9281): `IC = Cupón_{periodo} × (τ_{dev} / τ_{periodo})`
- **Precios y valuación · Valor técnico** (línea 9285): `Valor_{técnico} = Capital_{residual,aj} + Intereses_{corridos,aj}`
- **Precios y valuación · Paridad** (línea 9289): `Paridad = (Precio_{sucio} / Valor_{técnico}) × 100`
- **Rendimientos · TIR — Tasa Interna de Retorno** (línea 9295): `Precio_{sucio} = Σ_{t=1..n} CF_{t} / (1+TIR)^{τ_{t}}`
- **Rendimientos · Current Yield** (línea 9299): `Current Yield = Cupón_{anual} / Precio_{sucio}`
- **Rendimientos · TNA** (línea 9303): `TNA = Rendimiento_{periodo} × (360 / Días_{30/360})`
- **Rendimientos · TEA** (línea 9307): `TEA = (1 + Rendimiento_{periodo})^{1/τ} − 1`
- **Rendimientos · TEM** (línea 9311): `TEM = (1 + TEA)^{1/12} − 1`
- **Rendimientos · Convención de días** (línea 9315): `τ_{t} = Días(Liquidación, Flujo_{t}) / Base`
- **Duration, convexity y sensibilidad · Duration Macaulay** (línea 9321): `D_{Mac} = Σ τ_{t} · PV(CF_{t}) / Σ PV(CF_{t})`
- **Duration, convexity y sensibilidad · Duration Modificada** (línea 9325): `D_{Mod} = D_{Mac} / (1 + TIR)`
- **Duration, convexity y sensibilidad · Duration Modificada en días** (línea 9329): `DM_{días} = D_{Mod} × Base`
- **Duration, convexity y sensibilidad · Convexity** (línea 9333): `CX = Σ [ CF_{t}·τ_{t}(τ_{t}+1) / (1+TIR)^{τ_{t}+2} ] / Precio_{sucio}`
- **Duration, convexity y sensibilidad · Sensibilidad por Duration** (línea 9337): `ΔP ≈ −Precio_{sucio} × D_{Mod} × Δy`
- **Duration, convexity y sensibilidad · Sensibilidad con Convexity** (línea 9341): `ΔP ≈ −P_{sucio} D_{Mod} Δy + ½ P_{sucio} CX (Δy)²`
- **Estructura y liquidez · WAL — Weighted Average Life** (línea 9347): `WAL = Σ τ_{t} · Amort_{t} / Σ Amort_{t}`
- **Estructura y liquidez · ADTV — Average Daily Trading Value** (línea 9351): `ADTV_{n} = (1/n) Σ_{i=0..n−1} VolumenEfectivo_{t−i}`
- **Curva del panel · Ajuste cuadrático** (línea 9357): `y(x) = a + b·x + c·x^{2}`
- **Curva del panel · Spread contra la curva** (línea 9361): `Spread_{pb} = ( TIR_{ref} − y(x_{ref}) ) × 100`
- **Ajustes de capital · Factor de ajuste CER** (línea 9367): `FA_{CER,t} = CER_{t−ℓ} / CER_{base}`
- **Ajustes de capital · Factor Dollar Linked** (línea 9371): `FA_{DL,t} = A3500_{t−ℓ} / A3500_{base}`
- **Ajustes de capital · Flujo técnico vs flujo ajustado** (línea 9375): `FlujoTotal_{t} = (InterésCash_{t} + AmortTec_{t}) × FA_{t}`
- **Ajustes de capital · Capitalización de intereses** (línea 9379): `Cap_{t} = InterésBruto_{t} × p_{t}^{cap}`

### Calculadoras: bonos, letras y caución

- **Calculadora de Bonos — flujos y valuación · Flujo de fondos** (línea 9660): `CF_{t} = Amort_{t} + Capital vivo_{t} × Tasa_{t} × τ_{periodo}`
- **Calculadora de Bonos — flujos y valuación · TIR desde el precio** (línea 9667): `P = Σ CF_{t} / (1+TIR)^{d_{t}/365}`
- **Calculadora de Bonos — flujos y valuación · Fecha de liquidación** (línea 9672): `P = Σ_{t > X} CF_{t} / (1+TIR)^{(d_{t} − d_{X})/365}`
- **Calculadora de Bonos — flujos y valuación · Base de días** (línea 9681): `τ_{Act/365} = días corridos / 365 · τ_{30/360} = días 30/360 / 360`
- **Calculadora de Bonos — flujos y valuación · Precio desde la tasa** (línea 9692): `TIR = (1+TEM)^{12} − 1 · TEM = TNA / 12`
- **Calculadora de Bonos — flujos y valuación · Duration, convexity y paridad** (línea 9696): `D_{Mod} = D_{Mac}/(1+TIR) · C = Σ τ(τ+1) CF (1+TIR)^{−(τ+2)} / P`
- **Calculadora de Bonos — flujos y valuación · Moneda de compra y especie** (línea 9700): `P_{USD} = P_{ARS} / TC`
- **Calculadora de Bonos — flujos y valuación · Comisión de compra** (línea 9708): `P_{pagado} = P × (1 + c) · TIR_{neta} : P_{pagado} = Σ CF_{t} / (1+TIR_{neta})^{d_{t}/365}`
- **Calculadora de Bonos — flujos y valuación · Comisión sobre los pagos** (línea 9715): `CF^{neto}_{t} = Amort_{t} × (1 − k·a) + Int_{t} × (1 − k)`
- **Calculadora de Bonos — flujos y valuación · Diferencia contra el cierre** (línea 9721): `Δ TIR = TIR − TIR_{cierre} · Δ Precio = P / P_{cierre} − 1`
- **Calculadora de Bonos — supuestos · Cupones TAMAR y BADLAR** (línea 9727): `Tasa_{cupón} = Índice_{futuro} + Margen`
- **Calculadora de Bonos — supuestos · Capitalizables TAMAR** (línea 9733): `TEM = (1 + TNA × 32/365)^{365/384} − 1`
- **Calculadora de Bonos — supuestos · Bonos CER** (línea 9739): `CF^{nominal}_{t} = CF^{real}_{t} × (1+π)^{d_{t}/(365/12)}`
- **Calculadora de Bonos — supuestos · Dollar linked** (línea 9745): `CF^{ARS}_{t} = CF_{t} × (1+δ)^{d_{t}/(365/12)}`
- **Calculadora de Bonos — supuestos · Duales** (línea 9749): `M = máx(M_{pata 1}, M_{pata 2})`
- **Tabla general de títulos públicos · Plazo** (línea 9766): `CI = rueda del cierre · 24 hs = día hábil siguiente`
- **Tabla general de títulos públicos · TNA sobre plazo y equivalentes** (línea 9770): `TNA_{s/plazo} = (CF/P − 1) × 365/d · TNA_{n} = ((1+TIR)^{n/365} − 1) × 365/n`
- **Tabla general de títulos públicos · Duales: pata** (línea 9775): `TIR_{pata} = (M_{pata}/P)^{365/d} − 1`
- **Calculadora de Letras · TEM** (línea 9780): `TEM = (P_{vto} / costo)^{30/días} − 1`
- **Calculadora de Letras · TEA y TNA** (línea 9785): `TEA = (1+TEM)^{12} − 1 · TNA = TEM × 12`
- **Calculadora de Letras · Comisiones** (línea 9787): `costo = P_{neg} × (1 + TNA_{com} × días/365)`
- **Calculadora de Letras · Precio desde la TEM** (línea 9790): `P_{neg} = P_{vto} / (1+TEM)^{días/30} / (1 + TNA_{com} × días/365)`
- **Calculadora de Letras · TC breakeven** (línea 9792): `TC_{BE} = TC_{neg} × P_{vto} / costo`
- **Calculadora de Caución · Interés** (línea 9800): `I = C × TNA × n / 365`
- **Calculadora de Caución · Comisión del agente** (línea 9804): `Com = máx(B_{c} × TNA_{com} × n / 365 ; mínimo)`
- **Calculadora de Caución · Derechos de mercado** (línea 9807): `D = B_{d} × d × mín(n ; 90) / 90`
- **Calculadora de Caución · Impuestos** (línea 9811): `G = Com + D + A + Of + IVA`
- **Calculadora de Caución · Tasa neta y costo financiero** (línea 9814): `TNA_{neta} = (F_{1} − F_{0}) / F_{0} × 365 / n · TEA = (F_{1}/F_{0})^{365/n} − 1`
- **Calculadora de Caución · Garantía** (línea 9818): `VA = Σ Q × P / L × TC × aforo · Cobertura = VA / (C + I)`

Los campos de las fórmulas de tasas se expresan en tanto por uno salvo las columnas que declaran porcentaje o puntos básicos. Por ejemplo, el spread de la tarjeta del panel usa tasas del eje en porcentaje y multiplica por 100 para obtener pb; el control de este relevamiento usa tasas decimales y multiplica por 10.000. Los supuestos de inflación/devaluación de las proyecciones son mensuales. Las expresiones y sus variables se deben revisar en conjunto antes de trasladarlas a un motor.

## 10. Verificación técnica

Se agregaron 44 pruebas sintéticas para los tres auxiliares: caché y concurrencia, fallos sin reintento, contenido diferido/incompleto, tipos y JSON, origen de muestras, comparación independiente de tasas, discrepancia de cronogramas, extracción literal sin ejecutar expresiones, y protección de los archivos originales. Las comprobaciones con datos públicos del cierre son las registradas por separado, no casos ficticios mezclados en producción.

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src:tests ~/.venvs/cartera/bin/python -m unittest discover -s tests -p 'test_extra_iamc*'
```

Resultado de esta suite: **44 aprobadas**. También pasaron las suites completas: **338 pruebas de etapas y 484 adicionales, 822 en total**. La advertencia preexistente de openpyxl sobre un título de hoja largo no produjo fallos. El manifiesto de integridad de fixtures se entrega como `fixtures/iamc/MANIFIESTO.json`.
