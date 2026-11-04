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
  su origen, resultado desde la compra y resultado desde el día cero.
- **Totales:** por tipo de activo y general, en pesos y en dólar MEP.
- **Efectivo:** aparte, sin sumarse a las posiciones.
- **Vencimientos:** los próximos 60 días, destacados.
- **Niveles:** distancia al take profit y al stop loss de cada especie.
- **Gráfico por especie:** SVG propio con el historial capturado.
- **Estado de los datos:** hora de la última consulta y aviso visible si los precios
  no están actualizados o vienen del último dato guardado.

Si el navegador no puede consultar la API, muestra los precios embebidos al generar
el archivo, marcados como tales.

Antes de implementar, completar el contrato del tablero para entregarle cantidades,
unidades de cotización y referencias MEP/día cero. Comprobar en el navegador la
actualización, los cálculos y la recuperación ante caída de la fuente.

**Listo cuando** pasa `tests/test_etapa3_*` y Claude lo revisó en el navegador.

## Etapa 4: Alertas

Comparar precios contra take profit y stop loss, avisar vencimientos y dejar
constancia cuando no se pudo chequear. Pensado para una tarea programada.

- Módulos: `cartera.alertas`, `cartera.notificar`.
- Comando: `alertas`.
- Canales: notificación de macOS y Telegram.
- Plantilla de `launchd` en `ops/`, para correr cada 5 minutos. **No la instales.**

**Listo cuando** pasa `tests/test_etapa4_*`.

## Etapa 5: Movimientos

Registrar compras, ventas, rentas, dividendos, depósitos y retiros después del día
cero, con baja de lotes por FIFO y resultado realizado. Conservar el origen real o
estimado de los costos también en las ventas.

Conciliar posiciones y efectivo con la base inicial y los movimientos. El resultado
monetario integral descuenta aportes y suma retiros; los cobros se cuentan una sola
vez. Si faltan datos para la conciliación, se informa "sin dato". La metodología de
rentabilidad porcentual queda pendiente de especificación y revisión, sin asumir que
el resultado monetario dividido por el capital inicial sea suficiente.

- Módulo: `cartera.movimientos`.
- Comando: `movimiento`.

La carga es manual por ahora. El lector de archivos del broker se especifica cuando
haya un archivo de ejemplo: no lo inventes.

**Listo cuando** pasa `tests/test_etapa5_*`.

---

## Fuera de alcance

- Reconstruir posiciones o costos anteriores al día cero.
- Lector de archivos del broker, hasta tener un ejemplo.
- Resultado en dólares **desde la compra**. En esta versión, el resultado en dólar
  MEP se calcula solo desde el día cero.
- Acceso programático al broker, órdenes o ejecución.
- Exposición al cliente final.
- Cálculo impositivo.
