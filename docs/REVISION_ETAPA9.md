# Revisión de la Etapa 9 — Flujo de fondos

Revisión de Claude: 11 de noviembre de 2026, sobre la implementación de Codex del 7 de noviembre
(`cartera.iamc`, `cartera.flujo_fondos`, comandos `iamc`, `bonos`, `precio-bono` y `flujo --revisar`,
sección del dashboard y hoja de Excel). Codex no dejó informe de entrega ni pruebas propias de la etapa.

**Resultado: aprobada con tres correcciones**, hechas en esta revisión. Los cálculos coinciden con IAMC.

## Qué se controló

Cierres reales de IAMC del 05/11 y del 06/11/2026 (este último bajado el 11/11 con el comando `iamc`)
y una cartera ficticia con AL30, YM34O, un bono CER, un bono sin vincular y una LECAP.

| Control | Resultado |
|---|---|
| TIR de compra al precio de cierre | AL30 14,3033 % e YM34O 8,6296 % (cierre 05/11); YM34O 8,61 % (cierre 06/11). Igual a la publicada |
| TIR con otro precio, contra la calculadora de IAMC en el navegador | AL30 a 55: 10,3514 % contra 10,35 %. YM34O a 95: 10,1465 % contra 10,15 %. Factores de descuento iguales al sexto decimal |
| Flujo en dólares por pago | Idéntico al de la calculadora para 10.000 VN de AL30 y 5.000 VN de YM34O; cobro total 6.592,00 y 7.722,50 |
| TIR publicada de todo el cierre del 06/11 | 246 instrumentos de tasa fija: 239 dentro de 1 pb; máximo 8,3 pb (RZABO, PUC2O, CH24D, MIC6O, YM40O, CWC6O, AO29) |
| Compra en pesos con `--tc` | 81.100 ARS a 1.571,20 da 51,6166 USD por 100 VN |
| Venta parcial posterior | Baja los nominales por FIFO y el flujo de la posición |
| Movimiento `amortizacion` | No cambia nominales ni lotes; sube el efectivo; se compara junto con la renta |
| Cobro en pesos de un pago en dólares | Se convierte con su `tc` y se marca "Conversión aplicada" |
| CER, dual, sin vincular y ausente en IAMC | Se listan como pendientes, sin importes |
| Validaciones de `precio-bono` | Rechaza moneda distinta sin `--tc`, liquidación futura, familia no habilitada y especie sin vincular |
| Pantalla | Revisada en el navegador con fecha real y con fecha simulada (20/01/2027) para ver el control de cobros |
| Excel | Hoja "Flujo de fondos" con los mismos valores que la pantalla; abierta en Microsoft Excel y con openpyxl |

## Correcciones hechas

1. **Falsos "cobro no registrado" antes del día cero.** Con el cronograma manual del prospecto, el control
   listaba todos los pagos desde la emisión como "cobro no registrado", con teórico "sin dato", incluso de
   años en que el cliente no tenía el título. Ahora el control empieza en el día cero: un pago anterior
   solo figura si está en los extractos, y la pantalla dice desde qué fecha se controla.
2. **"sin dato" donde no hay pagos.** El calendario mostraba "sin dato" en las monedas sin pagos del mes.
   Ahora muestra una raya; "sin dato" queda para un importe que no se pudo calcular.
3. **Compra el día del pago.** El teórico contaba los nominales comprados el mismo día del pago, que no
   cobran ese cupón, y descontaba los vendidos ese día, que sí lo cobran. Ahora usa los nominales al cierre
   del día anterior.

También: la pantalla muestra la fecha del cálculo, el aviso de amortización manual explica qué revisar, y
se agregaron el README, `FORMATOS.md` y 15 pruebas en `tests/test_extra_flujo_revision.py`. La
especificación pasó a la versión 1.1 con estas tres reglas.

## Cierre automático desde `dashboard`

Decisión de Felipe del 11/11/2026, implementada por Claude en `cartera.iamc.guardar_cierre_del_dia`:

- Solo actúa si la carpeta de datos ya tiene algún cierre guardado; así las pruebas y una carpeta nueva no
  consultan IAMC por su cuenta.
- Un intento por día; las demás corridas leen la caché. Espera hasta 10 segundos por consulta.
- Una falla no impide el dashboard: se informa en la salida del comando y en la sección Flujo de fondos, y
  consume el intento de ese día.
- Probado con la caché real del 11/11: la primera corrida guardó el cierre del 06/11 y la segunda no
  consultó ni anunció nada. Siete pruebas en `tests/test_extra_iamc_dashboard.py`.

**Pruebas: 860, todas aprobadas** (354 de etapas y 506 adicionales).

## Límites que conviene conocer

- **Compras anteriores al primer cierre guardado (05/11/2026).** Sin `pagos_manuales` se ven los pagos
  futuros, pero la TIR y el resultado a vencimiento quedan "sin dato". Es el caso de toda cartera existente:
  hay que cargar, por título, los pagos del prospecto entre la compra y el 05/11/2026.
- **Aviso de amortización manual.** Si solo se cargan esos pagos y no el prospecto completo, aparece el
  aviso de que la amortización no suma 100. No frena el cálculo.
- **Un cierre que no se guarda no se recupera.** Felipe no usa tareas programadas. Desde el 11/11/2026 el
  comando `dashboard` intenta guardar el cierre publicado (ver "Cierre automático"). Un día hábil sin
  generar ningún dashboard sigue siendo un cierre perdido.
- **Títulos que salen de IAMC antes de vencer.** TX26 vencía el 09/11/2026 y ya no figuraba el 05/11. El
  último pago de un título puede desaparecer del calendario unos días antes; se informa como "sin cronograma
  en IAMC".
- **Cobro registrado fuera de la ventana de 10 días.** Queda como "cobro no registrado" y el movimiento no
  se asocia a ningún pago.
- **Feriados.** IAMC no corre las fechas por feriados y cartera tampoco; solo se avisa el fin de semana.
- **`robots.txt` de IAMC** devuelve la portada en HTML. El extractor lo informa en cada corrida y no lo
  toma como permiso.

## Pendiente de Felipe

- Aprobar las tres correcciones y la versión 1.1 de la especificación.
- Definir el archivo de supuestos para CER, TAMAR, dólar linked y duales (etapa siguiente).

## Seguimiento de Codex (12/11/2026), revisado el 16/11/2026

Cambios sin commitear en `flujo_fondos.py`, `iamc.py` y `README.md`, con 6 pruebas nuevas en
`tests/test_extra_etapa9_seguimiento.py`. **Aprobados sin correcciones.**

- El control de cobros solo se arma para pagos desde el día cero. Coincide con la versión 1.1.
- Una posición vendida conserva los pagos que cobró antes de la venta, aunque ya no tenga nominales.
- Una letra que vence hoy figura como "debería haberse cobrado", con los nominales del día anterior. Una
  letra que venció antes del día cero no entra al calendario.
- `iamc`: se rechaza un cierre cuya liquidación es anterior a la fecha de cierre, y el dashboard no
  reemplaza un cierre ya archivado de la misma fecha. La publicación usa un enlace duro; se comprobó que
  funciona en la carpeta de OneDrive.

Controles: pasan las 929 pruebas existentes (la única falla es `test_etapa11_indices`, que espera la etapa
11 sin implementar). Con copias de las tres carteras reales, el flujo de fondos con y sin estos cambios es
idéntico: ninguna tiene día cero, y las posiciones cerradas sin pagos siguen sin mostrarse.

Cierres de IAMC: el 16/11 se archivó el del 13/11. Se perdieron los del 09 y 10/11. Cada cierre queda
publicado hasta el siguiente: el del 16/11 se guarda con cualquier dashboard generado entre ese cierre y el
del 17/11.
