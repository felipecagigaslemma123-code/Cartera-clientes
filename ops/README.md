# Operación manual: alertas y captura

Esta entrega incluye plantillas; **no instala ni inicia tareas**. Los pasos de esta
página son para una instalación manual posterior, una vez revisados por Claude y
aprobados por Felipe. Activar `alertas` habilita avisos reales por los canales
configurados. Las pruebas de desarrollo reemplazan todos esos canales.

## Preparación y marcadores

Se trata de LaunchAgents del usuario que abre sesión en macOS. Cada cliente usa sus
propias dos etiquetas y sus propios archivos. No se necesita una tarea del sistema
ni ejecutar como administrador.

- `{{PYTHON}}`: ruta absoluta a `~/.venvs/cartera/bin/python`, expandida con el nombre
  de usuario. No poner `~` literal en la plantilla final.
- `{{PROYECTO}}`: ruta absoluta de este código. `PYTHONPATH` apunta a su `src`.
- `{{DATOS}}`: carpeta de datos elegida por el asesor, fuera del código.
- `{{CLIENTE}}`: slug de cliente, sin nombre ni importe de cartera. Viaja en cada aviso.
- `{{LOGS}}`: carpeta absoluta de registro **fuera de OneDrive**, por ejemplo la
  carpeta `Library/Logs/cartera` del usuario.

`launchd` no interpreta shell en `ProgramArguments` ni expande `~`. Las rutas con
espacios deben seguir siendo un único elemento de la lista de argumentos. No
pegues credenciales en las plantillas ni en sus variables de entorno.

El calendario de captura usa la zona horaria local de la Mac; comprobar que
corresponda a Buenos Aires antes de activarlo. La evaluación de niveles convierte
siempre la hora a Argentina.

La plantilla de alertas corre cada 300 segundos; fuera del horario de mercado
solo evalúa vencimientos. La captura corre de lunes a viernes a las 11, 12, 13, 14,
15, 16 y 17 horas, para alimentar el historial y los gráficos. Las dos plantillas
usan permisos privados de creación (`Umask` 077), no se ejecutan al cargarlas y no
usan `KeepAlive`.

## Crear copias finales, sin activar

Antes de seguir: validar una base importada y los archivos `niveles.json` e
`instrumentos.json`. Preparar manualmente una carpeta privada de registros fuera
de OneDrive y la carpeta `Library/LaunchAgents` del usuario.

Para sustituir los marcadores, leer cada plantilla con `plistlib.loads`, recorrer
sus valores de texto y reemplazar los cinco marcadores. Guardar después con
`plistlib.dumps`: así una ruta con `&` o espacios queda correctamente escapada en
XML. No hacer reemplazos de texto sin reserializar el plist.

Los nombres de salida pueden ser:

```text
~/Library/LaunchAgents/ar.cartera.CLIENTE.alertas.plist
~/Library/LaunchAgents/ar.cartera.CLIENTE.capturar.plist
```

Revisar las rutas absolutas finales, que no queden marcadores `{{...}}` y que
`StandardOutPath` y `StandardErrorPath` estén fuera de OneDrive. Restringir a 600
las dos copias finales y a 700 la carpeta privada de registros. Comprobar la sintaxis
con `plutil -lint RUTA_AL_PLIST` antes de cargar nada.

## Canales y credenciales

Siempre está disponible el canal de macOS. Telegram se agrega solo si hay un par
completo de token y chat: primero se busca en el entorno y, si no está completo,
se busca el par en el Llavero. No se mezclan fuentes parciales.

Las tareas programadas no heredan las variables de la terminal. Si el asesor ya
cuenta con un bot y un chat autorizados, los guarda en el Llavero con estos dos
comandos. Con `-w` al final, cada uno pide el valor por teclado y no lo deja en el
historial de la terminal:

```bash
security add-generic-password -a "$USER" -s cartera-telegram-token -w
```

```bash
security add-generic-password -a "$USER" -s cartera-telegram-chat -w
```

No crearlos a mano en **Acceso a Llaveros**: macOS podría pedir un permiso que nadie
responde en una tarea programada, y Telegram quedaría afuera sin dejar rastro. Los
valores nunca van en archivos del proyecto, plist o registros. No se incluye
creación de bots ni se ejecutan escrituras o lecturas reales del Llavero durante
esta entrega. Sin credenciales de Telegram, se utiliza únicamente macOS.

Antes de habilitar la tarea, revisar con Felipe los canales deseados y los permisos
de notificaciones de macOS. Un proceso que termina sin error significa que el canal
aceptó la solicitud; no demuestra que la persona haya visto el aviso.

## Activación y retirada: solo manuales

Una vez revisadas las copias finales, se pueden cargar por separado desde la sesión
local del usuario. Los siguientes son ejemplos de comandos **no ejecutados por Codex**:

```bash
launchctl bootstrap "gui/$(id -u)" RUTA_ABSOLUTA_AL_PLIST
launchctl print "gui/$(id -u)/ETIQUETA_DEL_PLIST"
```

La etiqueta es el valor `Label` de la copia final, por ejemplo
`ar.cartera.cliente-demo.alertas`. Para retirar una tarea ya cargada:

```bash
launchctl bootout "gui/$(id -u)" RUTA_ABSOLUTA_AL_PLIST
```

Repetir los pasos para la segunda tarea solo si también se desea habilitarla. No
lanzar una prueba de `alertas` con canales reales como comprobación automática:
puede enviar el aviso de control o alertas de niveles y vencimientos.

## Qué revisar en los registros

Cada corrida mantiene un archivo privado `.alertas.lock` vacío para excluir otra
corrida del mismo cliente. No debe borrarse mientras se está usando el programa.
Una corrida omitida por ese bloqueo no avisa ni modifica el estado.

`alertas.log`, dentro de la carpeta del cliente, agrega hora, tipo, ticker y precio,
o el canal que falló. No guarda nombres del cliente, importes de cartera ni secretos.
El estado se publica de forma atómica. Si todos los canales fallan, no se confirma el
estado nuevo y la siguiente corrida vuelve a intentar. Si algún canal entrega, se
confirma; esto puede dejar un canal fallido registrado sin repetir el aviso por los
que ya funcionaron.

Un estado ilegible se respalda en `estado_alertas.corrupto.json`; si ya había otra
copia diferente, se conserva con un sufijo único. Se reinicia la evaluación y pueden
repetirse avisos. Revisar ese caso manualmente antes de borrar copias.

El evento de control se envía una vez por día, en la primera corrida dentro del
horario de mercado. Dice cuántas especies tienen niveles, o que no hay niveles.
Si no llega un día esperado, revisar las tareas y los registros: no asumir que todo
está en orden. Los errores de canales se muestran sin el texto original del error.

## Límites operativos

- Con la Mac apagada o suspendida **no hay chequeos** ni avisos en tiempo real.
  El control diario ayuda a detectar la ausencia de corridas.
- macOS puede requerir permisos para que un proceso de fondo acceda a OneDrive.
  Un archivo no descargado o inaccesible puede impedir la corrida.
- Los feriados no están contemplados; la fuente puede responder el último precio.
  `vivo` identifica una consulta válida, no la fecha del último operado.
- Los niveles usan el bid o, si falta, el último operado. Una cotización de caché
  no dispara niveles; se informa que no pudo chequearse.
- Ni las entregas reales de macOS/Telegram, ni los permisos del Llavero, ni el
  comportamiento de `launchd` con suspensión o cierre de sesión se verificaron
  en esta entrega. Las plantillas no están instaladas.
