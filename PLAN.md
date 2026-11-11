# Plan

La cartera arranca de cero en un **día cero**. Lo anterior no se reconstruye: los
costos vienen de un Excel de punto de partida, y los movimientos posteriores se
cargan desde el broker actual.

Cada etapa se hace por separado: Codex implementa, Claude revisa y Felipe valida
los criterios antes de pasar a la siguiente. Las pruebas de una etapa se corren junto
con las anteriores y se acompaña una demostración con datos ficticios.

**Decisión de Felipe del 04/11/2026:** el objetivo es medir el resultado completo de
la cartera desde el día cero, incluyendo movimientos y cobros. La comparación de
precios de una posición se conserva como un indicador separado; no reemplaza ese
resultado completo.

---

## Etapa 1: Punto de partida

Leer el Excel, validarlo, calcular costos y resultados por posición, y guardar una
base inicial verificable. Los precios actuales y el día cero llegan en la etapa 2;
`estado` informa "sin dato" donde todavía no están disponibles.

- Módulos: `cartera.punto_partida`, `cartera.calculos`.
- Comandos: `importar`, `actualizar-costos`, `estado`.
- Base `cartera.json` con versión, fecha de importación, nombre y huella del Excel,
  posiciones y lotes. `importar` no sobrescribe una base existente. Las correcciones
  de costos se hacen con `actualizar-costos`, conservando la versión completa
  anterior en `historial_cartera/` antes del reemplazo atómico. No pueden cambiar las
  especies, tipos, unidades ni cantidades totales; sí sus lotes y costos. Si no hay
  cambios en los datos, no se escribe nada. Los movimientos futuros no modifican
  esta base. Ver `docs/FORMATOS.md`.
- Fechas de compra posteriores a hoy en Argentina se rechazan, indicando hoja, fila
  y ticker; la fecha de hoy se acepta. Aplica a importaciones y correcciones.
- La corrección informa costo y origen anterior/nuevo por especie modificada, y
  advierte sin bloquear si se altera un costo de extracto o se pierde ese origen.

**Listo cuando** pasa `tests/test_etapa1_*`.

## Etapa 2: Precios y día cero

Cliente de data912 con caché y tolerancia a caídas, dólar MEP, captura de historial
propio y fijación del día cero.

El día cero guarda cantidades, precios, dólar MEP y efectivo, de modo que el patrimonio
inicial se pueda reconstruir sin depender de otro archivo. El efectivo se puede cargar
después sin volver a tomar precios. Ver `docs/DOMINIO.md` y `docs/FORMATOS.md`.

- Módulo: `cartera.precios`.
- Comandos: `capturar`, `fijar-dia-cero`, `efectivo-dia-cero`.

Cuando haya cotización, comparar el precio de compra de cada lote con el precio
actual: si es más de cinco veces mayor (`compra > actual × 5`) o menor
(`compra < actual / 5`), mostrar una advertencia con ticker y ambos precios por
posible error de unidad o moneda. No bloquea la carga, no cambia los cálculos ni
el origen del lote.

`actualizar-costos` también advierte cuando un lote estimado vuelve a pendiente, porque
suele indicar que se usó un Excel viejo.

En esta etapa no se calcula el resultado integral: solo se guarda su punto de partida.
El resultado integral en pesos se implementa en la etapa 5, cuando existen los
movimientos. El resultado integral en dólares queda fuera de alcance por ahora.

**Listo cuando** pasa `tests/test_etapa2_*`.

## Etapa 3: Dashboard

HTML autocontenido que se abre sin servidor y actualiza precios en vivo.

- Módulo: `cartera.dashboard`.
- Comando: `dashboard`.

Tiene que mostrar:

- **Por posición:** cantidad, precio, valuación, peso, variación del día, costo y
  su origen, resultado desde la compra y variación de precios desde el día cero.
- **Totales:** por tipo de activo y general, en pesos y en dólar MEP.
- **Efectivo:** aparte, sin sumarse a las posiciones. El actual y el del día cero.
- **Día cero:** fecha, valuación y patrimonio inicial, o qué le falta.
- **Vencimientos:** los próximos 60 días, destacados, y los ya vencidos.
- **Niveles:** distancia al take profit y al stop loss de cada especie.
- **Gráfico por especie:** SVG propio con el historial capturado.
- **Estado de los datos:** hora de la última consulta y aviso visible si los precios
  no están actualizados o vienen del último dato guardado.

Si el navegador no puede consultar la API, muestra los precios embebidos al generar
el archivo, marcados como tales.

**No muestra un resultado completo.** Hasta la etapa 5 no hay movimientos. El lugar del
resultado completo indica "se calcula cuando estén los movimientos". La variación de
precios no se presenta como resultado de la cartera.

Las reglas están en `docs/DASHBOARD.md`.

**Listo cuando** pasa `tests/test_etapa3_*` y Claude comprobó en el navegador la
actualización, los cálculos y la recuperación ante una caída de la fuente.

## Etapa 4: Alertas

Comparar precios contra take profit y stop loss, avisar vencimientos y dejar
constancia cuando no se pudo chequear. La etapa 7 simplificó sus canales.

- Módulos: `cartera.alertas`, `cartera.alertas_comando`, `cartera.notificar`.
- Comando: `alertas`.
- Canal: notificación de macOS.
- Reglas de la corrida y el canal en `docs/ALERTAS.md`.

**Listo cuando** pasa `tests/test_etapa4_*`.

## Etapa 5: Movimientos

Registrar compras, ventas, rentas, dividendos, depósitos, retiros, gastos y cambios de
moneda después del día cero, con baja de lotes por FIFO y resultado realizado. Conservar
el origen real o estimado de los costos también en las ventas.

Reconstruir posiciones y efectivo a partir de la base y los movimientos, y controlar el
efectivo calculado contra `efectivo.json`. El resultado monetario integral en pesos
descuenta aportes y suma retiros; los cobros se cuentan una sola vez. Si faltan datos,
se informa "sin dato" y qué falta. La metodología de rentabilidad porcentual queda
pendiente de especificación y revisión, sin asumir que el resultado monetario dividido
por el capital inicial sea suficiente.

`estado`, `capturar`, `dashboard` y `alertas` pasan a usar la cartera actual. El
dashboard muestra el resultado completo, el realizado y el efectivo calculado. Reglas en
`docs/DOMINIO.md`, `docs/FORMATOS.md`, `docs/CONTRATO.md`, `docs/DASHBOARD.md` y `docs/ALERTAS.md`.

- Módulo: `cartera.movimientos`.
- Comando: `movimiento`.

La carga es manual. Leer los extractos del broker corresponde a la etapa 6.

**Listo cuando** pasa `tests/test_etapa5_*` y Claude comprobó en el navegador el recálculo del
resultado completo con precios en vivo.

## Etapa 6: Rendimiento realizado

**Decisión de Felipe del 05/11/2026:** además del seguimiento desde el día cero, quiere saber cuánto
ganó o perdió con lo ya vendido y cobrado, desde que el cliente opera con él. Se construye primero lo
realizado, y de esos mismos movimientos nace la cartera actual, que se controla contra la base.

Leer los extractos de cuenta corriente del broker, clasificar cada renglón, calcular el resultado por
venta y los ingresos (dividendos, rentas, cauciones, gastos), separados del dinero que entró o salió, y
derivar los lotes abiertos. Lo operado en otro broker antes de llegar no se evalúa: entra a su precio del
día de la transferencia. Reglas en `docs/HISTORIAL.md`.

- Módulo: `cartera.historial`.
- Comando: `historial`.
- El dashboard suma una sección con este resultado.

**Listo cuando** pasa `tests/test_etapa6_*`.

## Etapa 7: Alertas con el dashboard abierto

**Decisión de Felipe del 05/11/2026:** no usa Telegram ni quiere tareas programadas. Entra cada tanto,
actualiza con el botón, y las alertas de niveles funcionan mientras tenga el dashboard abierto.

- Sacar Telegram y sus credenciales de `cartera.notificar`, y borrar `ops/`. El comando `alertas` queda
  para correrlo a mano, con el canal de macOS.
- La página se actualiza al abrirse, con el botón y cada 5 minutos.
- La página evalúa los niveles y avisa con un cartel, un sonido y, si el navegador lo permite, una
  notificación del sistema. Reglas en `docs/DASHBOARD.md`.

**Listo cuando** pasa `tests/test_etapa7_*` y Claude comprobó el aviso en el navegador.

---

## Etapa 8: Descarga en Excel

**Pedido de Felipe del 05/11/2026:** poder bajar la cartera en Excel desde el dashboard.

- Botón en el encabezado que genera un `.xlsx` real en el navegador, con los mismos valores que muestra la
  pantalla en ese momento, sin consultar la red ni agregar dependencias. Reglas en `docs/DASHBOARD.md`.

**Listo cuando** pasa `tests/test_etapa8_*` y Claude abrió en Excel un archivo bajado del dashboard con datos reales.

## Etapa 9: Flujo de fondos por cliente

**Pedido de Felipe del 07/11/2026:** que cada cliente vea qué va a cobrar por su renta fija, cuándo y en qué
moneda, y cuánto gana a vencimiento con el precio al que compró, sin depender del precio de hoy.

- Fuente: cierres diarios de IAMC (`docs/FUENTE_IAMC.md`), guardados en `<datos>/iamc/cierres/`.
  **Decisión de Felipe del 11/11/2026:** el comando `dashboard` intenta guardar el cierre del día.
- Habilitado: tasa fija (`fix`) y las letras ya habilitadas. CER, TAMAR, dólar linked y duales solo se
  listan como pendientes.
- Nuevo tipo de movimiento `amortizacion`: no cambia los nominales.
- Módulos: `cartera.iamc`, `cartera.flujo_fondos`.
- Comandos: `iamc`, `bonos`, `precio-bono`, `flujo --revisar`.
- Sección **Flujo de fondos** del dashboard y hoja del mismo nombre en el Excel.

Reglas en `docs/FLUJO_FONDOS.md`, `docs/DOMINIO.md` y `docs/CONTRATO.md`.

**Listo cuando** pasa `tests/test_etapa9_*` y Claude comprobó en el navegador el flujo de una cartera de
prueba con AL30 e YM34O contra la calculadora de IAMC.

---

## Fuera de alcance

- Evaluar lo operado en otro broker antes de la llegada del cliente.
- Resultado en dólares **desde la compra**. En esta versión, el resultado en dólar
  MEP se calcula solo desde el día cero.
- Acceso programático al broker, órdenes o ejecución.
- Exposición al cliente final.
- Cálculo impositivo.
