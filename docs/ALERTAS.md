# Alertas

Este documento describe el comando `alertas`, que se corre a mano. Las alertas del uso diario, con el
dashboard abierto, están en `DASHBOARD.md`.

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

`niveles.json` también es inválido si una especie tiene una clave distinta de `take_profit` y
`stop_loss`: un nombre mal escrito no puede dejar una especie sin control sin que se note.

## Vencimientos inválidos

Si `instrumentos.json` no es un JSON válido o tiene una fecha inválida, **los niveles se evalúan
igual** y se emite, dentro o fuera de horario, un único evento por día de tipo `sin_chequeo`, con
`ticker` en `None`. Se conserva el estado anterior de vencimientos. Lo mismo vale si `niveles.json`
o `instrumentos.json` no se pueden leer.

## Movimientos

Los niveles, los vencimientos y sus especies salen de la cartera actual. Un nivel de una especie
conocida que ya se vendió toda se **ignora** y se indica en `avisos`: vender una especie no puede
apagar las demás alertas.

Si `movimientos.csv` es inválido, **la corrida sigue** con la base importada y emite un único
`sin_chequeo` por día, con `ticker` en `None`. Se registra en `error_movimientos`, dentro del estado.

## Mensajes

Una línea por evento, con el texto de `mensaje`:

- `ABEV take profit: precio 13.880, nivel 13.500.`
- `DNC3O vence el 22/11/2026: faltan 18 días.`

## Estado

```json
{"esquema_version": 1, "niveles": {}, "vencimientos": {},
 "control": "2026-11-04", "error_niveles": "2026-11-04", "error_instrumentos": null}
```

`niveles` y `vencimientos` son los estados que devuelven `evaluar_niveles` y
`evaluar_vencimientos`. Si el archivo es ilegible, se conserva una copia como
`estado_alertas.corrupto.json`, se sigue como si estuviera vacío y se registra en el log: quizá se
repitan avisos, pero no se pierden.

## Canales

`canales_disponibles()` devuelve `[canal_macos]`.

### macOS

Usa `osascript` con `subprocess.run`, sin shell. El título y el mensaje se pasan como **argumentos**,
nunca dentro del texto del script.

## Registro

`alertas.log` se abre solo en modo agregar, con permisos de lectura únicamente para el usuario. Cada
línea tiene hora, tipo, ticker y precio o el nombre del canal que falló. Nunca importes ni nombres del
cliente.
