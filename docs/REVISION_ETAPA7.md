# Revisión de la Etapa 7

Entrega de Codex: 5 de noviembre de 2026. Implementada únicamente “Alertas con el
dashboard abierto” de `PLAN.md`, pendiente de revisión de Claude. Antes de empezar
se leyeron `AGENTS.md`, el plan, “Alertas de niveles” de `docs/DASHBOARD.md`,
`docs/ALERTAS.md` y las reglas de niveles y horario de `docs/DOMINIO.md`.

## Implementación

- Retirados de `cartera.notificar` el canal de Telegram, las credenciales, las
  consultas al Llavero y el transporte HTTP. `canales_disponibles()` devuelve
  únicamente `[canal_macos]`, sin procesos ni lecturas de configuración al obtenerlo.
  Se conserva el mensaje agregado y la entrega macOS con argumentos separados,
  sin shell ni detalles de excepciones en los errores.
- `__main__.py` ya obtenía los canales a través del módulo; no necesitó cambios.
  El comando `alertas` conserva su uso manual, estado, vencimientos y reintentos.
- Eliminada toda la carpeta `ops/`, incluidas sus plantillas y guía, y todas sus
  referencias del README. No se instalaron ni ejecutaron tareas del sistema.
- Consultas del dashboard al abrir, con el botón y cada 300.000 ms. El aviso por
  antigüedad usa más de 660.000 ms desde el último éxito; una ronda que falla por
  completo sigue avisando inmediatamente. Se conservan el tiempo máximo de
  15 segundos por consulta y la prevención de rondas simultáneas.
- Panel superior `alertas-panel`, con los cinco identificadores pedidos, explicación
  de que funciona con la página abierta y estados iniciales no vacíos. Los estados
  distinguen sin niveles, sin chequear, fuera de horario y chequeado con fecha,
  hora y cantidad; los precios no vivos quedan listados como no chequeados.
- Evaluación únicamente al finalizar una ronda, de lunes a viernes, 11:00 incluido
  y 17:00 excluido en Argentina. No depende de la zona horaria del sistema. Usa bid
  positivo, o último si no hay bid, exclusivamente en estado vivo; los datos
  embebidos, la caché y una ronda fuera de horario no disparan ni rearman eventos.
- Estado en memoria por especie y lado, con un aviso por evento y rearme al regresar
  más del 1 % dentro del nivel, o cambiar el valor del nivel. Las líneas se agregan
  con hora y quedan hasta cerrar o recargar; el título acumula el número de alertas.
- Tono con `AudioContext` sin archivos y una notificación del sistema por ronda con
  todas las líneas, cuando hay permiso. El título usa solo el slug, nunca el nombre
  del cliente. Los fallos de ambos efectos quedan aislados del cálculo y el panel.
- El botón de activación inicia el sonido dentro del gesto del usuario y solicita
  permiso. Indica activas, bloqueadas, no disponibles o sin activar; cuando no hay
  notificaciones, aclara que los avisos quedan en pantalla. El estado se refresca
  si el permiso cambia mientras la página permanece abierta. Se distingue un fallo
  al pedir permiso de un fallo de entrega y se reconoce una entrega recuperada.

Se mantienen la CSP existente, `textContent`, el JSON escapado, las dependencias
locales y el estado exclusivamente en memoria. No se usa almacenamiento del navegador.
Las funciones del resultado completo, las posiciones y el historial realizado no
recibieron cambios de cálculo.

## Validación y precisión

La validación anterior de `niveles.json` del dashboard solo comprobaba los números.
Ahora comparte las reglas con el comando manual: rechaza claves mal escritas,
tickers desconocidos y take profit menor o igual al stop loss antes de consultar
precios o modificar salidas. Un nivel de especie conocida totalmente vendida se
ignora con aviso, conservando los demás. Los errores mantienen ticker y campo,
como exigen las pruebas previas. Esto evita dos disparos opuestos o un falso “sin niveles”.

La comparación de rearme evita el redondeo binario de multiplicar directamente por
0,99 o 1,01. Se convierte la representación decimal del número a coeficiente y
exponente y se compara exactamente con `BigInt`: 100 por referencia contra 99 o
101 por nivel. No se agrega una tolerancia que pueda comerse un regreso válido.
Se cubrieron en particular TP 0,27 con borde 0,2673 y SL 0,21 con borde 0,2121:
ambos son exactamente 1 % y no rearman; un regreso apenas mayor sí lo hace.

## Demostración ficticia y pruebas

Con AAA y take profit 1.200, un bid vivo de 1.299 agrega
“AAA take profit: precio 1.299,00, nivel 1.200,00”, incrementa el título y genera
una notificación simulada. Repetir la ronda no duplica el evento. Volver por debajo
de 1.188 y después superar el nivel genera el siguiente aviso; el borde exacto
no rearma. Una falla de red conserva el último precio pero no dispara alertas,
y el estado indica que AAA no se pudo chequear.

Se ejecutaron los comandos pedidos con el entorno Python 3.9 existente y sin
escribir bytecode:

```bash
PYTHONPATH=src ~/.venvs/cartera/bin/python -m unittest discover -s tests -p 'test_etapa*'
PYTHONPATH=src ~/.venvs/cartera/bin/python -m unittest discover -s tests -p 'test_extra*'
```

| Grupo | Pruebas | Resultado |
|---|---:|---|
| Etapas 1 a 7 | 316 | OK |
| Adicionales | 388 | OK |
| Total | 704 | OK |

Se agregaron 29 pruebas en archivos nuevos:

- `test_extra_alertas_navegador.py`: 20 casos de horario argentino con reloj del
  sistema distinto, rearme TP y SL estricto y decimal, fallos parciales, antes de
  la primera respuesta, permisos y recuperación, tono agregado, ausencia o falla
  de audio, umbral exacto de 11 minutos, sin solape y memoria durante la sesión.
- `test_extra_canal_macos_etapa7.py`: 4 casos de descubrimiento sin procesos,
  entrega agrupada, error privado y tiempo de espera sin reintento interno.
- `test_extra_niveles_dashboard_etapa7.py`: 5 casos de niveles invertidos o iguales,
  ticker desconocido, clave mal escrita y especie vendida, con integridad de
  archivos y sin consultas cuando hay error.

El script real se ejecutó con JavaScriptCore y DOM, red, reloj, notificaciones y
audio ficticios. Pasan también las 22 pruebas originales de alertas del navegador
junto con las de cálculo y refresco de las etapas anteriores. No se emitieron avisos
ni sonidos reales. La advertencia existente de openpyxl por un título ficticio de
hoja de más de 31 caracteres sigue visible; no causa fallos ni pruebas omitidas.

Se comprobaron por huellas los originales protegidos de pruebas, fixtures,
especificaciones, instrucciones y revisiones anteriores: quedaron intactos. Solo
se agregaron pruebas propias, esta revisión y los cambios solicitados en README.
`git diff --check` no informa problemas. No se hicieron commits.

## Dudas, desvíos y verificación pendiente

No se detectaron contradicciones que requirieran modificar pruebas o especificaciones.
La validación común y la comparación decimal completan las reglas ya especificadas.
No se amplió el trabajo a otra etapa ni se alteraron la base importada o el día cero.

Quedan sin verificar en un navegador real:

- El diseño del panel y su lectura en pantalla angosta.
- El permiso desde un archivo local, su concesión o bloqueo real, cambios externos
  de permiso y la apariencia y agrupación efectiva de las notificaciones del sistema.
- La activación del audio por gesto, el tono y las restricciones de reproducción.
- La cadencia real con la pestaña en segundo plano, la Mac suspendida o temporizadores
  limitados por el navegador; no se promete que ese entorno ejecute cada ronda puntualmente.
- La compatibilidad del navegador de uso con las APIs empleadas, incluido `BigInt`,
  y la aplicación efectiva de CSP/CORS y consultas reales de data912.

La lógica de esos casos se comprobó con simulaciones; su verificación visual y de
permisos queda para Claude, conforme a la decisión previa de Felipe. No se intentó
eludir el bloqueo de archivos locales del navegador integrado. No se utilizaron
datos reales, credenciales ni servicios de mensajería en esta entrega.

El trabajo se detuvo al completar la Etapa 7.

## Revisión de Claude

Probada en el navegador integrado con precios reales, en horario de mercado y con niveles ficticios: las
alertas se dispararon una sola vez, el título y el estado se actualizaron, y la especie dentro de sus
niveles no avisó. Se ajustó: el panel pasó debajo del encabezado y el botón hace sonar un tono de confirmación.

Sin verificar: la notificación del sistema (bloqueada en ese navegador), el sonido real y el archivo
abierto con doble clic. Quedan para la prueba de Felipe.
