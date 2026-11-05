# cartera

Seguimiento interno de carteras de clientes, local en una Mac. Instrucciones para el
desarrollo en [AGENTS.md](AGENTS.md) y etapas en [PLAN.md](PLAN.md).

El objetivo aprobado es medir el resultado completo desde el día cero, incorporando
movimientos y cobros. El desarrollo se entrega por etapas: Codex implementa, Claude
revisa y Felipe valida los criterios. Están implementadas la base inicial, los precios,
el día cero, el dashboard y las alertas. Los movimientos corresponden a la etapa 5,
que todavía no se inició.

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

Esta etapa conserva el patrimonio inicial; no calcula el resultado integral con
movimientos. Ese resultado en pesos corresponde a la etapa 5. El resultado integral
en dólares continúa fuera de alcance.

## Dashboard local

Para generar la pantalla de la etapa 3 a partir de una base importada:

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
MEP, niveles, vencimientos y gráficos del historial capturado. El efectivo actual y
el inicial aparecen aparte, con su fecha; no se suman a las posiciones ni a los pesos.
El día cero conserva la referencia de valuación y patrimonio inicial o sus faltantes.

**No calcula un resultado completo.** Ese recuadro indica “se calcula cuando estén
los movimientos”. La variación de precios es un indicador separado y el resultado
desde la compra explica qué posiciones tienen costo completo y precio comparable.
Los costos mixtos se identifican como “incluye estimado”.

Al abrirse y cada 60 segundos, la página consulta una vez cada panel necesario y el
MEP. Cada consulta tiene un máximo de 15 segundos y las rondas no se solapan. La hora
mostrada es la de consulta, nunca la del último operado. Los precios embebidos se
muestran como “Último dato” hasta que una consulta los confirme. Si falla una especie,
conserva su último precio y su hora; si nunca tuvo precio, muestra “sin dato”. Aparecen
avisos si falla la ronda, falta una consulta exitosa reciente o el archivo es de otro
día. La página no guarda datos en el navegador.

Los archivos opcionales ausentes se muestran como faltantes o “sin fijar”. Los gráficos
usan solo las últimas 500 observaciones de cada especie y no se actualizan en vivo.
Las filas inválidas del historial se omiten con un aviso visible. `dashboard` no agrega
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

Para verificar las cuatro etapas y las comprobaciones adicionales:

```bash
PYTHONPATH=src ~/.venvs/cartera/bin/python -m unittest discover -s tests -p 'test_etapa1*' -v
PYTHONPATH=src ~/.venvs/cartera/bin/python -m unittest discover -s tests -p 'test_etapa2*' -v
PYTHONPATH=src ~/.venvs/cartera/bin/python -m unittest discover -s tests -p 'test_etapa3*' -v
PYTHONPATH=src ~/.venvs/cartera/bin/python -m unittest discover -s tests -p 'test_etapa4*' -v
PYTHONPATH=src ~/.venvs/cartera/bin/python -m unittest discover -s tests -p 'test_extra*' -v
```

La ejecución de todas las pruebas será apropiada al completar sus módulos:

```bash
PYTHONPATH=src ~/.venvs/cartera/bin/python -m unittest discover -s tests -v
```

Claude revisó las etapas anteriores; sus entregas históricas están en
[REVISION_ETAPA1.md](docs/REVISION_ETAPA1.md) y [REVISION_ETAPA2.md](docs/REVISION_ETAPA2.md).
La revisión del dashboard se documenta en [REVISION_ETAPA3.md](docs/REVISION_ETAPA3.md).
La etapa 4 está implementada y revisada por Claude; falta comprobar los avisos reales. Pasan
las 386 pruebas acumuladas: 28 de etapa 1, 36 de etapa 2, 30 de etapa 3, 56 de etapa 4 y 236
adicionales.
Los resultados y límites de la verificación de alertas están en
[REVISION_ETAPA4.md](docs/REVISION_ETAPA4.md). No se inició la etapa 5 ni se hicieron
commits. Las decisiones abiertas figuran en el plan y el contrato.

Esta carpeta no contiene datos reales de clientes. Las salidas se guardan en la ruta
de datos, separada del código; las demostraciones y pruebas usan datos ficticios.
