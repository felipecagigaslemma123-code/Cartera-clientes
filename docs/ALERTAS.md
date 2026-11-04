# Alertas

Las reglas de cada alerta están en `DOMINIO.md`. Este documento define cómo corre el comando
y cómo avisa.

## Una corrida de `alertas`

1. **Evita corridas simultáneas.** Si otra está en curso para el mismo cliente, termina con
   código 0 sin escribir ni avisar.
2. **Lee `niveles.json`, `instrumentos.json` y `estado_alertas.json`.** Los faltantes equivalen
   a vacíos.
3. **Dentro del horario de mercado:**
   - Valida los niveles. Si son válidos, consulta precios **solo de las especies con algún nivel**
     y evalúa. Sin niveles, no consulta la red.
   - Agrega el aviso de control del día, si todavía no se envió.
4. **Siempre:** evalúa vencimientos. Fuera de horario solo se hace esto.
5. **Avisa.** Si hay eventos, envía **un único mensaje** con todos.
6. **Registra.** Agrega una línea a `alertas.log` por evento y por canal que falló.
7. **Guarda el estado** de forma atómica, según la regla que sigue.

## Si el aviso no llega

**Es preferible repetir un aviso a perderlo.**

- Hay eventos y **ningún canal** pudo entregarlos: no se guarda el estado nuevo, para que la
  próxima corrida los vuelva a evaluar y avisar. El comando termina con código distinto de cero.
- Al menos un canal pudo: se guarda el estado. El canal que falló queda en `alertas.log`.
- Sin eventos: se guarda el estado y termina con código 0.

## Aviso de control

Una vez por día de mercado, en la primera corrida dentro del horario, se envía un evento de tipo
`control`. Prueba que el sistema está corriendo: si un día no llega, algo se detuvo.

- Con niveles: `"Alertas activas: N especies con niveles."`
- Sin niveles: `"Alertas activas, pero no hay niveles definidos."`

## Niveles inválidos

`niveles.json` es inválido si no es un JSON válido o si, en alguna especie:

- El ticker no está en la cartera.
- Un nivel no es un número positivo o `null`.
- `take_profit` es menor o igual que `stop_loss`, si están los dos.

Con niveles inválidos **no se evalúa ninguno**, y se emite un único evento por día de tipo
`sin_chequeo`, con `ticker` en `None`, que explica el problema. Los vencimientos se evalúan igual.

## Estado

```json
{"esquema_version": 1, "niveles": {}, "vencimientos": {},
 "control": "2026-11-04", "error_niveles": "2026-11-04"}
```

`niveles` y `vencimientos` son los estados que devuelven `evaluar_niveles` y
`evaluar_vencimientos`. Si el archivo es ilegible, se conserva una copia como
`estado_alertas.corrupto.json`, se sigue como si estuviera vacío y se registra en el log: quizá se
repitan avisos, pero no se pierden.

## Canales

`canales_disponibles()` devuelve siempre `canal_macos` y, si hay credenciales, `canal_telegram`.

### macOS

Usa `osascript` con `subprocess.run`, sin shell. El título y el mensaje se pasan como **argumentos**,
nunca dentro del texto del script.

### Telegram

`POST https://api.telegram.org/bot<TOKEN>/sendMessage`, con `urllib`, en JSON, tiempo de espera de 10
segundos, sin `parse_mode`. Un mensaje de más de 4.000 caracteres se recorta e indica que se recortó.
Una respuesta sin `"ok": true` es una falla.

**El token nunca aparece en logs, errores ni salidas.** Todo error del canal se reporta sin la URL y
sin el texto original de la excepción.

### Credenciales

`credencial_telegram()` busca token y chat, en este orden:

1. `TELEGRAM_BOT_TOKEN` y `TELEGRAM_CHAT_ID`.
2. Llavero de macOS, con `security find-generic-password -s cartera-telegram-token -w` y
   `-s cartera-telegram-chat -w`.

Devuelve `(token, chat)` o `None` si falta alguno. Las tareas programadas no heredan las variables de
la terminal, por eso existe el Llavero. No se guardan en ningún archivo.

## Registro

`alertas.log` se abre solo en modo agregar, con permisos de lectura únicamente para el usuario. Cada
línea tiene hora, tipo, ticker y precio o el nombre del canal que falló. Nunca importes, nombres del
cliente ni credenciales.

## Tareas programadas

En `ops/`, dos plantillas de `launchd`. **No las instales.**

- `cartera.alertas.plist.template`: `alertas`, cada 5 minutos, con `StartInterval`.
- `cartera.capturar.plist.template`: `capturar`, de lunes a viernes, a cada hora de 11:00 a 17:00, con
  `StartCalendarInterval`. Alimenta los gráficos del dashboard.

Usan los marcadores `{{PYTHON}}`, `{{PROYECTO}}`, `{{DATOS}}` y `{{CLIENTE}}`, definen `PYTHONPATH` y
`CARTERA_DATOS`, y escriben su salida en una carpeta fuera de OneDrive. No incluyen credenciales.

Agregá `ops/README.md` con los pasos de instalación manual y estas limitaciones:

- Con la Mac apagada o suspendida no hay chequeos. El aviso de control diario permite notarlo.
- macOS puede pedir permiso para que la tarea acceda a la carpeta de OneDrive.
- Los feriados no están contemplados: la fuente puede seguir respondiendo el último precio.
