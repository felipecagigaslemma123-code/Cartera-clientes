# Entrega de etapa 4 para revisión de Claude

Fecha: 04/11/2026. Implementada y verificada por Codex según `PLAN.md`, `CONTRATO.md`,
`DOMINIO.md` y `ALERTAS.md`. Revisión de Claude y validación de Felipe pendientes.
No se inició la etapa 5 ni se hicieron commits.

## Qué se entrega

- `cartera.alertas`: evaluadores puros de niveles y vencimientos, con estados nuevos
  serializables sin mutar los recibidos. Horario argentino, bid o último, rearme
  estricto de más del 1 %, cambio de niveles, avisos únicos de falta de chequeo y
  umbrales de vencimiento 30, 15, 7 y 1 días.
- `cartera.alertas_comando`: corrida completa, bloqueo por cliente, validación de
  niveles, consulta solo de paneles necesarios, control diario y evaluación de
  vencimientos también fuera de horario.
- `cartera.notificar`: mensaje único agregado por canal, continuación tras una falla,
  errores genéricos sin URL, credenciales ni texto original de excepciones. macOS
  usa argumentos separados sin shell; Telegram usa JSON sin formato enriquecido,
  tiempo de espera de diez segundos y recorte explícito a 4.000 caracteres.
- Comando `alertas`, con selección de canales por módulo para permitir reemplazos
  en pruebas. Sin entrega devuelve error; una corrida simultánea termina sin avisar.
- Plantillas de usuario de `launchd`: alertas cada 300 segundos y captura en los 35
  horarios de lunes a viernes entre las 11 y las 17. Tienen argumentos separados,
  marcadores, entorno de código y datos, registros fuera de OneDrive y umask 077.
- Guía manual de preparación e instalación posterior en [ops/README.md](../ops/README.md).
  Es documentación: ninguno de esos pasos se ejecutó durante esta entrega.

## Entrega y persistencia

La corrida guarda el nuevo estado solo si no hay eventos o algún canal aceptó el
mensaje. Si todos fallan, conserva el estado anterior para volver a evaluar en la
siguiente corrida. Un fallo de registro o guardado después de enviar también puede
provocar una repetición posterior: es preferible repetir antes que perder avisos.

Con un canal exitoso alcanza. Por diseño no se reintenta por separado el canal que
falló cuando otro ya entregó; el fallo queda registrado. “Entregado” describe que el
canal no informó error, no que una persona haya leído el mensaje.

`estado_alertas.json`, sus respaldos y `alertas.log` son privados. El estado se
publica atómicamente; el registro se abre solo para agregar. Un estado ilegible o
con estructura inválida se conserva en `estado_alertas.corrupto.json`. Si ya existe
una copia diferente, la nueva recibe fecha, hora y sufijo único, sin pisar la anterior.

El archivo `.alertas.lock` queda vacío y privado dentro de la carpeta del cliente.
No se elimina después de cada corrida, para no crear una carrera entre procesos.
Si otra corrida lo tiene bloqueado, no se consultan precios, no se descubren canales
y no se modifican registros ni estado.

## Decisiones de operación

- Los niveles inválidos no se evalúan parcialmente. Se emite un `sin_chequeo` global
  por día; los vencimientos válidos se evalúan igual. El problema también aparece
  en la salida de cada corrida, aunque el aviso del día ya se haya emitido.
- Un `instrumentos.json` presente pero inválido no se interpreta como ausencia de
  vencimientos (ver la revisión de Claude, al final). Los instrumentos ajenos a las
  posiciones importadas no producen avisos de esta cartera.
- Una falla al guardar la caché se informa, pero no impide evaluar las cotizaciones
  que sí se obtuvieron ni los vencimientos. Los precios que no están vivos no se
  utilizan para disparar niveles.
- La selección de canales se difiere hasta tener eventos; las corridas sin eventos
  no necesitan buscar credenciales.
- Los mensajes los forman los evaluadores con ticker, tipo, precio y detalles del
  control o del vencimiento. No se lee `perfil.json` para generar nombres de cliente
  ni se incorpora el valor de su cartera.

## Pruebas

Entorno: Python 3.9.6 y openpyxl 3.1.5; sin instalar dependencias adicionales.

```bash
PYTHONPATH=src ~/.venvs/cartera/bin/python -m unittest discover -s tests -p 'test_etapa1*' -v
PYTHONPATH=src ~/.venvs/cartera/bin/python -m unittest discover -s tests -p 'test_etapa2*' -v
PYTHONPATH=src ~/.venvs/cartera/bin/python -m unittest discover -s tests -p 'test_etapa3*' -v
PYTHONPATH=src ~/.venvs/cartera/bin/python -m unittest discover -s tests -p 'test_etapa4*' -v
PYTHONPATH=src ~/.venvs/cartera/bin/python -m unittest discover -s tests -p 'test_extra*' -v
```

**378 pruebas aprobadas**, sin omisiones:

- Etapa 1: 28.
- Etapa 2: 36.
- Etapa 3: 30.
- Etapa 4: 56.
- Adicionales: 228.

Esta entrega agregó 45 pruebas en nuevos archivos `test_extra_*`: 16 de evaluación,
14 de canales, 5 de plantillas y 10 de integridad de la corrida. Las pruebas previas
y los fixtures se conservaron sin cambios.

Se comprobaron límites horarios y umbrales, histéresis exacta, cambios de nivel y
vencimiento, falta de precios vivos, estados sin mutaciones, entregas agregadas,
fallas parciales y totales, reintentos sin confirmar el estado, bloqueo de otra
corrida, recuperación de estados corruptos, publicación atómica y permisos privados.
También se verificó que las fallas simuladas con un secreto ficticio no lo expongan
en mensajes de error, salidas ni registro de eventos.

Las pruebas de los canales reemplazaron `subprocess.run`, `urlopen`, el entorno y
las respuestas del Llavero con valores ficticios. Las pruebas de comandos usaron
canales y precios simulados. No se enviaron notificaciones reales de macOS ni
mensajes reales de Telegram; no se crearon bots y no se leyó ni escribió el Llavero real.

## Lo no verificado

Por el alcance autorizado, no se comprobó:

- Entrega real, permisos o presentación de notificaciones de macOS.
- Validez de un token o chat real, acceso al Llavero, ni recepción real en Telegram.
- Instalación o ejecución real de LaunchAgents, permisos de OneDrive bajo `launchd`,
  comportamiento con suspensión o cierre de sesión, ni disponibilidad de la red al despertar.
- Calendario de feriados ni antigüedad del último operado que ofrece la fuente.

Las plantillas se parsearon con `plistlib` y se verificaron sus argumentos, horarios,
marcadores y rutas ficticias de registros. Esto no sustituye su revisión e instalación
manual posterior. No hay tareas programadas activadas por esta entrega.

## Revisión solicitada a Claude

1. Revisar la semántica de rearme, cambios de niveles, vencimientos y control diario.
2. Confirmar que los niveles inválidos y la falta de precios nunca parezcan un
   chequeo exitoso, sin multiplicar el mismo aviso durante el día.
3. Revisar el protocolo de confirmación de estado y la repetición después de fallas.
4. Revisar la privacidad de mensajes, errores, registros y copias de estado corrupto.
5. Revisar las plantillas y los pasos manuales de `ops/` antes de cualquier activación.

No avanzar a movimientos hasta completar la revisión y la validación de esta etapa.

## Revisión de Claude

Probada con una copia de los datos reales, precios reales de data912 y canales simulados;
la copia se borró al terminar. Se corrigió:

1. Un `instrumentos.json` inválido frenaba toda la corrida, incluidos los niveles, sin avisar.
   Ahora los niveles se evalúan y se emite un `sin_chequeo` por día. Un error de lectura de
   `niveles.json` o `instrumentos.json` se trata igual.
2. Una clave mal escrita en `niveles.json` dejaba la especie sin control. Ahora invalida el archivo.
3. Mensajes: una línea por evento, con precio y nivel, y fechas en formato argentino.
4. La guía de `ops/` carga las credenciales con `security`, para evitar un permiso sin respuesta
   en una tarea programada.
5. El `slug` real contenía el nombre del cliente y viaja en cada aviso: se cambió fuera de este
   repositorio y `ALERTAS.md` lo prohíbe.

Total tras la revisión: **386 pruebas aprobadas** (236 adicionales). Dos pruebas de
`test_extra_notificar.py` fijaban el formato anterior: una se ajustó y otra pasó a
`test_extra_revision_alertas.py`.

Siguen sin verificar la entrega real por macOS y Telegram, el Llavero y las tareas programadas.
