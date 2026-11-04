# Dashboard

Un único HTML que se abre con doble clic, sin servidor. Es una herramienta de trabajo:
priorizá que se lea rápido y que los números sean confiables. Tiene que funcionar en una
pantalla angosta sin desplazamiento horizontal de la página; la tabla puede desplazarse
dentro de su propio contenedor.

## Datos embebidos

`<script id="datos-cartera" type="application/json">` contiene:

```json
{
  "generado_en": "2026-11-04T17:05:00-03:00",
  "posiciones": [
    {
      "ticker": "BOND1", "especie": "Bono Demo", "tipo": "bono",
      "cantidad": 1000.0, "cotiza_cada": 100, "endpoint": "arg_bonds",
      "costo": null, "estado_costo": "incompleto",
      "ultimo": 160000.0, "bid": 159000.0, "ask": 161000.0, "pct_dia": 1.5,
      "estado": "vivo", "consultado_en": "2026-11-04T17:05:00-03:00",
      "valuacion": 1600000.0, "precio_dia_cero": 150000.0,
      "take_profit": null, "stop_loss": 150000.0, "vencimiento": "2026-11-22"
    }
  ],
  "vencimientos": [{"ticker": "BOND1", "vencimiento": "2026-11-22", "dias": 18, "vencida": false}],
  "dia_cero": {
    "fecha": "2026-11-04", "mep": 1500.0, "valuacion_posiciones": 1720000.0,
    "efectivo": {"fecha": "2026-11-04", "ARS": -1000.0, "USD": 10.0},
    "patrimonio_inicial": 1734000.0, "faltantes": []
  },
  "mep": {"ultimo": 1500.0, "estado": "vivo", "consultado_en": "2026-11-04T17:05:00-03:00"},
  "efectivo": {"fecha": "2026-11-04", "ARS": 1000.0, "USD": 10.0}
}
```

- Un dato faltante es `null`, nunca 0.
- Sin día cero, `dia_cero` es `null`. Sin `mep`, `mep` es `null`.
- `vencimientos` incluye especies que vencen dentro de los próximos 60 días, inclusive, y
  las ya vencidas, contando desde `generado_en` en hora de Argentina. Está ordenado por fecha.
- **El JSON no puede cortar el script.** Reemplazá `<` por `<` al embeberlo: un nombre
  de especie que contenga `</script>` no debe romper la página.

## Actualización en vivo

Al abrir la página y cada 60 segundos:

1. Consulta **una vez** cada panel que usan las posiciones, más `/live/mep`. Nunca pide especie
   por especie. No inicia una ronda si la anterior no terminó. Corta cada consulta a los 15
   segundos.
2. Una respuesta que no sea una lista, una especie ausente o un `c` que no sea positivo es
   una falla **de esa especie**: las demás siguen.
3. Un `px_bid` o `px_ask` de 0 se trata como faltante.
4. Recalcula con las mismas fórmulas de `DOMINIO.md`, usando `cantidad` y `cotiza_cada`.

La página no guarda nada en el navegador.

## Estados de cada precio

Cada fila muestra uno de estos estados, con palabras y sin depender solo del color:

| Estado | Cuándo | Qué muestra |
|---|---|---|
| En vivo | La última consulta trajo un precio válido | Precio y valuación |
| Último dato | Falló, pero hay un precio anterior | Ese precio, con la hora de su consulta |
| Sin dato | Nunca hubo un precio | "sin dato"; no entra en totales |

Un precio embebido al generar el archivo se muestra como **Último dato** hasta que una consulta
lo confirme, salvo que su `estado` sea `sin_dato`.

Arriba de todo se muestra la hora de la **última consulta**, nunca como hora del último
operado. Si falló toda la ronda, o la última exitosa tiene más de 5 minutos, aparece un aviso
visible. También aparece si el archivo se generó otro día: las posiciones pueden haber cambiado.

## Cálculos en pantalla

| Columna | Regla |
|---|---|
| Valuación | `cantidad × último / cotiza_cada` |
| Peso | Valuación / total de valuaciones conocidas |
| Resultado desde la compra | Solo con costo completo; si no, "falta estimar" |
| Variación de precios desde el día cero | Con la misma cantidad; "sin dato" sin día cero |
| Distancia al nivel | `nivel / referencia − 1`, con `bid` como referencia o `último` si no hay |

- **Origen del costo:** `extracto`, `estimado`, `mixto` (se muestra como "incluye estimado") o
  "falta estimar". Un costo que incluye estimaciones nunca se ve igual que uno de extracto.
- **Totales:** suman solo valores conocidos. Si falta alguna especie, indican cuántas. El resultado
  total desde la compra indica sobre qué parte de la cartera se calcula.
- **Dólar MEP:** los totales en dólares se dividen por el MEP actual. Sin MEP, "sin dato". La variación
  desde el día cero usa `valuación_hoy / mep_hoy − valuación_día_cero / mep_día_cero`.
- **Efectivo:** el actual y el del día cero se muestran aparte, con su fecha. No se suman a las
  posiciones ni entran en los pesos.
- **Resultado completo:** un recuadro indica "se calcula cuando estén los movimientos". No muestres
  un número ahí, ni llames "resultado de la cartera" a la variación de precios.
- **Formato:** punto de miles y coma decimal, también en lo recalculado en el navegador.

## Vencimientos

Los que vencen en 60 días o menos se destacan arriba, con días restantes recalculados con la fecha
del navegador. Una especie ya vencida se marca "vencida": si la fuente deja de cotizarla, se explica
por qué.

## Gráfico

Un SVG por especie, generado en Python con `historial`. Con menos de dos puntos, indica "sin historial
suficiente". El gráfico no se actualiza en vivo y aclara que muestra el historial capturado.

## Seguridad

- Todo texto se inserta como texto: en Python, escapado; en JavaScript, con `textContent`. Nada de
  `innerHTML` con datos.
- Incluí esta política:

  ```html
  <meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline'; script-src 'unsafe-inline'; connect-src https://data912.com; img-src data:">
  ```

- El archivo contiene datos del cliente y se guarda solo en la ruta de datos, con permisos de lectura
  únicamente para el usuario.
