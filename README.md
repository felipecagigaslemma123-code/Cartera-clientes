# cartera

Seguimiento interno de carteras de clientes, local en una Mac. Instrucciones para el
desarrollo en [AGENTS.md](AGENTS.md) y etapas en [PLAN.md](PLAN.md).

El objetivo aprobado es medir el resultado completo desde el día cero, incorporando
movimientos y cobros. El desarrollo se entrega por etapas: Codex implementa, Claude
revisa y Felipe valida los criterios. Están implementadas la base inicial, los precios,
el día cero, el dashboard, las alertas, los movimientos y el resultado completo en pesos.
La etapa 6 agrega el rendimiento realizado histórico a partir de extractos, separado
del seguimiento desde el día cero.

## Preparar el entorno

Desde la raíz de esta carpeta, con Python 3.9:

```bash
python3 -m venv ~/.venvs/cartera
~/.venvs/cartera/bin/pip install -r requirements.txt
```

El entorno queda fuera de OneDrive. El paquete se usa con `PYTHONPATH=src`.

## Demostración de la etapa 1

Usar únicamente el Excel ficticio y una carpeta temporal de datos:

```bash
datos_demo="$(mktemp -d)"
PYTHONPATH=src ~/.venvs/cartera/bin/python -m cartera --datos "$datos_demo" importar --cliente demo --archivo fixtures/punto_partida_demo.xlsx
PYTHONPATH=src ~/.venvs/cartera/bin/python -m cartera --datos "$datos_demo" estado --cliente demo
```

`--datos` también puede reemplazarse por la variable de entorno `CARTERA_DATOS`.
La importación guarda `clientes/demo/cartera.json` dentro de esa ruta. Valida todos
los problemas juntos y rechaza sobrescribir una base existente. `estado` distingue
costos de extracto, estimados y pendientes; sin precios actuales muestra "sin dato".
Los datos guardados se describen en [FORMATOS.md](docs/FORMATOS.md).

Los tickers de ese Excel son ficticios: sirven para importar y comprobar el estado,
pero no se espera encontrarlos en los paneles reales de precios. Las demostraciones
de cotizaciones usan respuestas ficticias dentro de las pruebas, sin acceder a la red.

## Corregir costos conservando el historial

Corregí una copia del Excel de punto de partida y ejecutá:

```bash
PYTHONPATH=src ~/.venvs/cartera/bin/python -m cartera --datos RUTA actualizar-costos --cliente SLUG --archivo EXCEL
```

La base debe existir. Se validan todas las filas y se mantienen exactamente las
especies, tipos, unidades de cotización y cantidades totales de la cartera; pueden
cambiar los lotes, sus fechas, precios, costos, orígenes y notas. Antes del reemplazo
atómico, la versión anterior completa se guarda en `clientes/SLUG/historial_cartera/`
con fecha, hora y nombre único. Si no cambia ningún dato, informa que no hay cambios y no
escribe nada. `importar` sigue rechazando una base existente.

Si falla el reemplazo después de guardar el respaldo, la base anterior queda intacta
y el respaldo permanece; su presencia no significa que la corrección se completó.

La salida detalla el costo y origen anterior y nuevo por especie modificada. Una
alteración de un costo de extracto o de ese origen genera una advertencia sin
bloquear. Al no haber identificadores de lote, esa detección es conservadora y
también advierte ante reasignaciones ambiguas entre extractos y otros lotes.
Reordenar filas o corregir únicamente una nota de extracto no genera el aviso.
Si un costo estimado vuelve a pendiente, también se advierte para detectar una
estimación perdida al usar una copia vieja del Excel.

Ambos comandos rechazan fechas de compra posteriores a hoy en Argentina, indicando
hoja, fila y ticker; la fecha de hoy se acepta. Las demostraciones y correcciones de
prueba deben usar únicamente datos ficticios y una carpeta temporal de datos.

## Precios, historial y día cero

Los siguientes comandos requieren una base importada. `RUTA` y `SLUG` son
marcadores para la carpeta de datos y el cliente elegidos por el asesor:

```bash
PYTHONPATH=src ~/.venvs/cartera/bin/python -m cartera --datos RUTA capturar --cliente SLUG
PYTHONPATH=src ~/.venvs/cartera/bin/python -m cartera --datos RUTA fijar-dia-cero --cliente SLUG
PYTHONPATH=src ~/.venvs/cartera/bin/python -m cartera --datos RUTA estado --cliente SLUG
```

`capturar` consulta una vez cada panel necesario de data912 y el dólar MEP de AL30.
Agrega solo cotizaciones vivas a `historial.csv`, incluido el dólar con ticker `MEP`.
Informa cuántas filas guardó y qué especies quedaron con caché o sin dato; si no
obtuvo ninguna cotización viva, termina con error. Una falla de un panel no impide
usar los demás. La caché conserva la fecha de la consulta que originó cada dato.

`fijar-dia-cero` guarda una foto en `dia_cero.json`, esquema 2: cantidades, precios,
dólar MEP y efectivo. Exige un precio vivo para cada posición; los costos pendientes
no lo impiden. Lee `efectivo.json` si existe y deja `null` en los saldos desconocidos.
Si falta el MEP, lo informa y guarda `null`. No reemplaza una foto existente sin
`--forzar`, que vuelve a tomar la referencia. `--fecha AAAA-MM-DD` usa por defecto
el día de Argentina y no admite fechas futuras; los precios son los consultados al
ejecutar el comando, no una reconstrucción histórica de esa fecha.

Si todavía no se conocen los saldos, se pueden completar después:

```bash
PYTHONPATH=src ~/.venvs/cartera/bin/python -m cartera --datos RUTA efectivo-dia-cero --cliente SLUG --ars=-1000 --usd=0
```

El ejemplo muestra saldos ficticios: los negativos y el cero son válidos. Este
comando no consulta la red ni modifica precios o cantidades. La fecha del efectivo
es por defecto la del día cero y admite `--fecha AAAA-MM-DD`. Si ya había algún saldo
cargado, requiere `--forzar` para reemplazarlo.

El patrimonio inicial suma la valuación guardada, efectivo ARS y efectivo USD
convertido a MEP. Si falta un saldo, muestra "sin dato" e identifica el faltante.
El MEP solo es necesario cuando el saldo USD es distinto de cero. El efectivo se
presenta aparte de las posiciones. `estado` sigue sin consultar precios por la red;
si hay una foto, también muestra la fecha y el patrimonio inicial o sus faltantes.
Las unidades de cotización se toman de las posiciones de la base importada; las
cantidades y precios se toman de la foto, aunque las tenencias posteriores cambien.

Cuando un precio de compra supera cinco veces el actual o es menor a su quinta
parte, se advierte con ticker y ambos precios por posible error de unidad o moneda.
Los límites exactos no avisan. Este control no bloquea ni cambia cálculos u orígenes.

La aplicación registra la hora de consulta; la fuente no informa la del último
operado. Un dato marcado
como vivo indica una respuesta válida de la API, sin garantizar la antigüedad de la
última operación. data912 es una fuente no oficial; sus límites y el tratamiento
de caídas se detallan en [PRECIOS.md](docs/PRECIOS.md).

La referencia inicial se conserva independiente de las tenencias actuales. La etapa 5
la usa para el resultado completo en pesos; el resultado integral en dólares y un
porcentaje integral continúan fuera de alcance.

## Movimientos y resultado completo

Primero debe existir un día cero. Esta plantilla usa una compra ficticia: reemplazá
`RUTA`, `SLUG` y `AAAA-MM-DD` por los valores correspondientes. Los números usan punto
decimal, sin miles:

```bash
PYTHONPATH=src ~/.venvs/cartera/bin/python -m cartera --datos RUTA movimiento --cliente SLUG --fecha AAAA-MM-DD --tipo compra --ticker NUE --cantidad 10 --importe 4000 --tipo-activo cedear --nota "Ejemplo ficticio"
```

La fecha debe ser posterior al día cero y no futura en Argentina. Se admiten `compra`,
`venta`, `renta`, `dividendo`, `deposito`, `retiro`, `gasto`, `compra_usd` y `venta_usd`.
`importe` siempre es el neto positivo de la operación; no se reconstruye multiplicando
cantidad por precio. La moneda predeterminada es ARS. Para USD se agregan
`--moneda USD --tc N`, con el cambio en pesos por dólar; ARS no admite `--tc`.
Las conversiones `compra_usd` y `venta_usd` expresan el importe en dólares.

Compras y ventas requieren ticker y cantidad positiva. Rentas y dividendos requieren
una especie conocida; un gasto puede identificarla. Aportes, retiros y conversiones
no llevan ticker. Una primera compra de una especie nueva requiere `--tipo-activo`
(`cedear`, `accion`, `bono`, `on` o `letra`); una recompra conserva el tipo conocido.
La confirmación informa la tenencia actual cuando hay una especie.

Se guarda `clientes/SLUG/movimientos.csv`, con las nueve columnas de
[FORMATOS.md](docs/FORMATOS.md). Conserva el orden de carga y los bytes anteriores;
para calcular se ordena por fecha, respetando el orden de carga cuando coinciden.
Cada carga valida el historial completo bajo bloqueo y publica un archivo privado
atómicamente. Una carga retroactiva que vuelve inválida una venta posterior se rechaza
sin cambiar el archivo. Las correcciones manuales también se validan al leerlo.

Las ventas consumen los lotes más viejos por FIFO, incluidos primero los sin fecha,
y prorratean su costo. El realizado distingue extracto, estimado, mixto e incompleto;
si consumió algún costo pendiente, esa venta queda sin costo ni resultado conocido.
Las cantidades actuales salen de la base más compras menos ventas: no se modifica
`cartera.json`. `estado`, `capturar`, `dashboard` y `alertas` usan esa cartera actual.
Fijar el día cero y calcular el patrimonio inicial usan siempre la base importada,
incluso si una especie ya se vendió. `fijar-dia-cero` rechaza, aun con `--forzar`,
un historial inválido o movimientos iguales o anteriores a la nueva referencia,
antes de consultar precios o escribir salidas.

El efectivo calculado parte de los saldos del día cero, aplica cada movimiento en su
moneda y admite negativos. Un saldo inicial desconocido sigue siendo desconocido.
Se compara contra `efectivo.json` a la fecha informada, incluyendo solo los movimientos
hasta ese día, con tolerancia inclusiva de 1 ARS y 0,01 USD. Una diferencia muestra
"no concilia" y pide revisar movimientos; el resultado usa el efectivo calculado.

El resultado completo es patrimonio final menos patrimonio inicial y aportes, más
retiros. El patrimonio final suma las posiciones actuales y el efectivo calculado,
con USD convertido al MEP actual. Rentas, dividendos, gastos y ventas ya impactaron
el efectivo: no se suman otra vez. No depende de conocer los costos. Si falta un
saldo, la referencia inicial, un precio necesario o el MEP necesario, muestra
"sin dato" y los faltantes; un saldo USD cero no necesita MEP.

Un `movimientos.csv` inválido hace fallar `estado`, `capturar` y `dashboard` sin escribir salidas.
En alertas se conserva la continuidad con la base importada y se avisa una vez por día
que no se pudo reconstruir la cartera actual. Los niveles de especies conocidas ya
vendidas se ignoran con aviso, sin desactivar los demás.

## Rendimiento realizado histórico

La etapa 6 responde cuánto se ganó o perdió con lo ya vendido y cobrado desde que el
cliente opera con el asesor. Es un cálculo independiente: no se suma al resultado
desde el día cero ni modifica `cartera.json`, `dia_cero.json` o `movimientos.csv`.
Requiere una base importada para comparar las tenencias, pero no requiere día cero.

En `clientes/SLUG/`, preparar:

```text
extractos/*.xlsx          cuentas corrientes, con períodos que pueden superponerse
ajustes_historial.csv     opcional: compras, ventas, rentas, dividendos y gastos faltantes
cierres.json              opcional: lista de tickers cuyo pago final cierra la posición
mep_diario.csv            opcional: fecha,mep
```

Se lee la primera hoja de cada Excel. El título debe identificar PESOS o DOLARES;
DOLARES CABLE se conserva como cuenta CABLE. Encabezado exacto de la primera fila:

```text
Liquida,Operado,Comprobante,Numero,Cantidad,Especie,Precio,Importe,Saldo,Referencia
```

Las reglas y comprobantes admitidos están en [HISTORIAL.md](docs/HISTORIAL.md).
Los períodos superpuestos se consolidan por la identidad especificada del renglón;
un mismo número con otro importe se conserva. Si el saldo no cierra con el anterior
más el importe, se avisa con archivo y fila, sin frenar el cálculo.

```bash
PYTHONPATH=src ~/.venvs/cartera/bin/python -m cartera --datos RUTA historial --cliente SLUG
PYTHONPATH=src ~/.venvs/cartera/bin/python -m cartera --datos RUTA historial --cliente SLUG --actualizar-mep
```

El primer comando usa solo los archivos locales. `--actualizar-mep` consulta los
históricos de AL30 y AL30D, calcula su cociente de cierres en las fechas comunes y
actualiza `mep_diario.csv`, conservando los días anteriores ya disponibles. Para USD
se usa el MEP del día o el último anterior de hasta cinco días corridos; un ajuste
puede indicar su propio `tc`. Sin cambio utilizable, el equivalente en pesos queda
"sin dato", con aviso. Los ajustes USD sin `tc` usan la misma búsqueda histórica.

Compras y ajustes de compra crean lotes; ventas y cierres consumen FIFO. Los ajustes
se identifican como estimados. Una transferencia desde otro broker se carga como
compra al valor de entrada de ese día: no se calcula lo ganado antes de llegar.
Si una venta excede los lotes disponibles, se informa la cantidad sin lote y su
resultado queda desconocido. Los pagos de cierre de una especie en una fecha se
agrupan para cerrar toda la cantidad abierta.

Dividendos, retenciones, rentas, cauciones completas, FCI y gastos conservan sus
signos. Las cauciones se agrupan por moneda, clase y fecha; una pata sin contraparte
se excluye con aviso, sin sumar su capital. Aportes y retiros se informan aparte y
no son ganancia. Las conversiones internas especificadas tampoco forman resultado.

El informe muestra los ingresos en ARS, USD y equivalente en pesos, realizado por
especie y origen del costo, total **conocido**, faltantes y diferencias de cantidad
y costo contra la base. Si falta parte del equivalente de una clase, ese equivalente
se muestra desconocido; el total conserva los demás valores individuales conocidos.
No se publica un porcentaje. Todo comprobante desconocido o vacío se lista completo,
con archivo y fila, y no se suma. No se lo omite ni se lo clasifica por parecido.

Se escribe `realizado.csv`, una fila por venta o cierre, con permisos `600`; las
celdas numéricas desconocidas quedan vacías. Las salidas se preparan completas antes
de reemplazarlas. Si falla un reemplazo posterior, se intenta restaurar lo ya
publicado; las corridas concurrentes se serializan. Sin extractos o ante un archivo
inválido, termina con error sin cambiar salidas. No corrige la base automáticamente.

Demostración ficticia cubierta por las pruebas: aporte de 5.000, compra de 10 AAA
por 1.000, venta total por 1.500 y dividendo de 70 producen un total conocido de
**570 ARS** (500 de venta más 70 de dividendo). El aporte queda afuera. La comparación
con la base demo informa las diferencias de tenencias correspondientes.

Si existe `extractos/`, `dashboard` agrega “Rendimiento realizado histórico”, con
sus desgloses, avisos y todos los renglones sin clasificar. Si el cálculo falla,
genera el resto del tablero con un aviso; sin carpeta, no agrega la sección.
Generar el dashboard no escribe `realizado.csv` ni actualiza el MEP diario. La sección
es histórica: precios y MEP en vivo siguen afectando solo los indicadores anteriores.
Para incorporar nuevos extractos o ajustes hay que volver a generar el HTML.

## Dashboard local

Para generar la pantalla a partir de una base importada y sus movimientos:

```bash
PYTHONPATH=src ~/.venvs/cartera/bin/python -m cartera --datos RUTA dashboard --cliente SLUG
```

El comando muestra la ruta de `clientes/SLUG/dashboard.html`. El archivo está pensado
para abrirse con doble clic, sin servidor: contiene su HTML, estilos, gráficos SVG y
script, sin dependencias externas. Se publica de forma atómica y con permisos `600`,
para que solo lo lea o modifique su usuario. Contiene datos de la cartera y debe
permanecer en su carpeta de datos.

Muestra posiciones, cantidades, valuaciones y pesos, costos y su origen, resultados
desde la compra, variación de precios desde el día cero, totales por tipo y en dólar
MEP, niveles, vencimientos y gráficos del historial capturado. El efectivo informado,
el calculado y el inicial aparecen aparte, con su fecha y su control; no se suman a
las posiciones ni a los pesos. El día cero conserva la referencia de valuación y
patrimonio inicial o sus faltantes.

Incluye el resultado completo en ARS, sus patrimonios y flujos, y las ventas realizadas
con el origen de su costo y el número de ventas excluidas por costo incompleto.
La variación de precios y el resultado desde la compra siguen como indicadores
separados. Los costos mixtos se identifican como “incluye estimado”.

Al abrirse y cada 60 segundos, la página consulta una vez cada panel necesario y el
MEP. Con cada ronda recalcula también el resultado completo, usando los nuevos precios
y MEP, el efectivo calculado y los flujos embebidos. Puede recuperar un resultado
antes faltante si aparece el precio o MEP necesario; los faltantes del día cero o
efectivo no se completan con cero. Para incorporar movimientos nuevos hay que volver
a generar el HTML. Cada consulta tiene un máximo de 15 segundos y las rondas no se solapan. La hora
mostrada es la de consulta, nunca la del último operado. Los precios embebidos se
muestran como “Último dato” hasta que una consulta los confirme. Si falla una especie,
conserva su último precio y su hora; si nunca tuvo precio, muestra “sin dato”. Aparecen
avisos si falla la ronda, falta una consulta exitosa reciente o el archivo es de otro
día. La página no guarda datos en el navegador.

Los archivos opcionales ausentes se muestran como faltantes o “sin fijar”. Los gráficos
usan solo las últimas 500 observaciones de cada especie y no se actualizan en vivo.
Las filas inválidas del historial de precios (`historial.csv`) se omiten con un aviso visible. `dashboard` no agrega
filas a `historial.csv`; para capturarlas se usa `capturar`. Si la fuente está caída,
el HTML se genera igual y queda marcado con caché o “sin dato”.

Los textos y el JSON embebido se escapan para que no puedan cortar el script. El HTML
incluye una política CSP que limita las conexiones a data912. Las pruebas comprueban
esa inclusión y la construcción segura; su aplicación efectiva en un navegador real
sigue pendiente de la revisión visual de Claude, junto con el diseño en pantalla
angosta y las consultas desde un archivo local. Ver [REVISION_ETAPA3.md](docs/REVISION_ETAPA3.md).

## Alertas y operación manual

El comando operativo de la etapa 4 es:

```bash
PYTHONPATH=src ~/.venvs/cartera/bin/python -m cartera --datos RUTA alertas --cliente SLUG
```

Este comando puede enviar avisos reales por los canales configurados: no es una
simulación. Durante esta entrega se comprobó exclusivamente con canales ficticios.

Dentro del horario argentino de mercado, valida los niveles y consulta solo los
paneles de las especies con algún take profit o stop loss. Usa el bid y, si falta,
el último operado; las cotizaciones de caché no disparan niveles. El aviso se rearma
al volver más de un 1 % dentro del nivel o al cambiar ese nivel. No se repite mientras
sigue disparado. Siempre se evalúan los vencimientos, incluso fuera de horario.

La primera corrida dentro del horario envía un control diario: indica cuántas
especies tienen niveles o que no hay niveles definidos. Un archivo de niveles
inválido produce un aviso único de falta de chequeo, sin impedir los vencimientos, y un
`instrumentos.json` inválido hace lo mismo sin impedir los niveles.
Los datos de precios faltantes también quedan identificados; no se presentan como
un chequeo exitoso.

Se agrupan todos los eventos de una corrida en un mensaje por canal. Si falla un
canal, se intentan los demás. Si ninguno entrega, no se confirma el estado nuevo y
la próxima corrida vuelve a intentar; el comando termina con error. Si alguno
entrega, se confirma el estado y el fallo del otro queda en el registro.

El estado se guarda de forma atómica. Un archivo ilegible se conserva como copia
privada y se evalúa desde un estado vacío, aunque puedan repetirse avisos. El registro
`alertas.log` solo agrega líneas, con permisos privados, sin nombres de clientes,
importes de cartera ni credenciales. Un bloqueo por cliente evita corridas simultáneas;
no se descubren canales en una corrida omitida o sin eventos nuevos.

Las plantillas para alertas cada cinco minutos y captura de lunes a viernes de 11 a
17 están en `ops/`. **No están instaladas ni activadas.** La guía de preparación,
marcadores, instalación manual posterior y límites está en [ops/README.md](ops/README.md).
No se crearon bots ni se utilizaron credenciales reales en la verificación.

## Verificación por etapa

Para verificar las seis etapas y las comprobaciones adicionales:

```bash
PYTHONPATH=src ~/.venvs/cartera/bin/python -m unittest discover -s tests -p 'test_etapa*' -v
PYTHONPATH=src ~/.venvs/cartera/bin/python -m unittest discover -s tests -p 'test_extra*' -v
```

También se puede ejecutar la suite completa:

```bash
PYTHONPATH=src ~/.venvs/cartera/bin/python -m unittest discover -s tests -v
```

Claude revisó las etapas anteriores; sus entregas históricas están en
[REVISION_ETAPA1.md](docs/REVISION_ETAPA1.md) y [REVISION_ETAPA2.md](docs/REVISION_ETAPA2.md).
La revisión del dashboard se documenta en [REVISION_ETAPA3.md](docs/REVISION_ETAPA3.md).
La etapa 4 está implementada y revisada por Claude; sus resultados y límites están en
[REVISION_ETAPA4.md](docs/REVISION_ETAPA4.md). La etapa 5 está implementada y revisada por
Claude; su detalle está en [REVISION_ETAPA5.md](docs/REVISION_ETAPA5.md).
La etapa 6 está implementada y revisada por Claude: pasan **300 pruebas de etapas y
373 adicionales, 673 en total**. Codex agregó 78 pruebas sin modificar las existentes ni los fixtures; la revisión ajustó dos por la clase de compensaciones. El alcance, los criterios de borde y los controles pendientes están
en [REVISION_ETAPA6.md](docs/REVISION_ETAPA6.md). No se hicieron commits ni se instalaron
tareas programadas. Las decisiones abiertas figuran en el plan y el contrato.

Esta carpeta no contiene datos reales de clientes. Las salidas se guardan en la ruta
de datos, separada del código; las demostraciones y pruebas usan datos ficticios.
