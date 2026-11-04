# Plan

La cartera arranca de cero en un **día cero**. Lo anterior no se reconstruye: los
costos vienen de un Excel de punto de partida, y los movimientos posteriores se
cargan desde el broker actual.

Cada etapa se hace por separado y queda revisada antes de pasar a la siguiente.

---

## Etapa 1: Punto de partida

Leer el Excel, validarlo, calcular costos y resultados, y guardar la cartera.

- Módulos: `cartera.punto_partida`, `cartera.calculos`.
- Comandos: `importar`, `estado`.

**Listo cuando** pasa `tests/test_etapa1_*`.

## Etapa 2: Precios y día cero

Cliente de data912 con caché y tolerancia a caídas, dólar MEP, captura de historial
propio y fijación del día cero.

- Módulo: `cartera.precios`.
- Comandos: `capturar`, `fijar-dia-cero`.

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
cero, con baja de lotes por FIFO y resultado realizado.

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
