# Revisión — Etapa 11: proyección de títulos ajustables

16/11/2026 · Implementación de Codex (parche `cartera_etapa11.patch`), revisada y corregida por Claude.

## Entrega

`cartera.indices` (series del BCRA, REM y curvas de CER, A3500 y TAMAR), `cartera.indices_archivos`
(comando `indices`, intento automático desde el dashboard, `feriados.json`, `supuestos_manual.json` y
estimación semanal guardada) y `cartera.pagos_indexados` (pagos CER, dólar linked, TAMAR con cupones,
capitalizables TAMAR y duales). `tools/bcra_extraer.py` pasó a usar el módulo de `src`. Codex llevó la
especificación a la versión 1.1: el REM releva el promedio del A3500 en los días hábiles del mes, y el CER se
pide hasta el 15 del mes siguiente.

## Controles

- El parche aplica limpio sobre el repositorio. Pasan las 18 pruebas de `test_etapa11_indices` y la suite
  completa.
- Las fórmulas de cada familia coinciden con la especificación. El primer cupón TAMAR usa la tasa vigente de
  IAMC; los siguientes, el promedio de la TAMAR del período corrido por el rezago más el margen.
- Prueba con copias de los datos reales, con contratos de prueba que **no son los contractuales**:
  - TZV28 (dólar linked): 31 VN cobran ARS 76.328 el 30/06/2028, estimado con el REM de octubre
    (A3500 de unos 2.462). Coherente con el camino del REM extendido.
  - X30N6 (LECER, vence 30/11/2026): pago **definitivo**, porque la referencia (16/11) ya está publicada.
    Supera la base de IAMC en 0,19 %, que son los tres días de CER entre el 13/11 y el 16/11.
  - X29E7 (LECER): estimado, con "CER publicado hasta 2026-12-15".

## Correcciones de Claude

1. **Base del A3500 de IAMC.** El parche tomaba el A3500 del día del cierre. IAMC usa el de su bloque macro,
   que puede ser anterior: el cierre del 12/11 usó el del 11/11 (1.547,9128 contra 1.544,4320 del 12/11).
   Con ese error, los pagos dólar linked y la pata dólar de los duales se desviaban hasta un 0,2 %. Ahora se
   usa el A3500 del BCRA en la fecha que informa IAMC (`_fecha_a3500_iamc`). Se comprobó en los cinco
   cierres archivados: coincide en todos.
2. **Letras CER y dólar linked.** Quedaban fuera del flujo, porque solo se procesaban bonos y ON, aunque son
   el caso principal del pedido (X29E7 y X30N6). Ahora una `letra` con `iamc.indice` sigue el flujo indexado
   y su precio se carga con `precio-bono`. Era un hueco de la especificación.
3. **TIR real CER.** El precio se deflactaba con el CER de la liquidación y los pagos con el de su referencia
   contractual, 10 días hábiles antes: la TIR real quedaba sesgada. Ahora el precio usa la referencia de la
   liquidación.

Pruebas nuevas en `tests/test_extra_etapa11_revision.py`. La del A3500 falla si se quita la corrección.

## Límites conocidos

- El promedio de la TAMAR de un cupón usa días corridos, completando fines de semana y feriados con el
  último dato publicado.
- El panel de letras sigue mostrando las LECER sin `iamc.indice` como pendientes.

## Pendiente de Felipe

- Cargar en `instrumentos.json` el bloque `iamc.indice` de cada título ajustable con datos del contrato:
  CER inicial y rezago de X29E7, X30N6 y TZXM7, y rezago de TZV28, con su fuente.
- Cargar los precios de compra con `precio-bono`.
- Escribir `<datos>/feriados.json` con 2026, 2027 y 2028.
- Correr `indices` en la carpeta de datos real (hasta ahora solo se corrió en una copia).

## Datos de contrato preparados por Codex (16/11/2026)

Codex dejó `instrumentos.json` y `feriados.json` en `Fixed Income Toolkit/examples/etapa11`. Revisión:

- **CER iniciales:** los tres coinciden exactamente con la API del BCRA en las fechas citadas. Las fechas
  salen de las resoluciones: emisión de X29E7 el 14/08/2026 (CER del 31/07), X30N6 el 15/12/2025 (CER del
  28/11, con el feriado del 08/12) y TZXM7 el 20/05/2024 (CER del 06/05).
- **Contra IAMC:** X29E7 y X30N6 reproducen el flujo de IAMC sin diferencia en los cinco cierres guardados.
  **TZXM7 no:** IAMC usa el CER del 03/05/2024 (357,5665), que da un pago 1,05 % menor que el del 06/05
  (361,3176) de la resolución. Queda abierto: hace falta una tercera fuente (agente de cálculo o ficha del
  título) antes de informar ese pago.
- **TZV28:** la Resolución Conjunta 16/2026 fija el A3500 del tercer día hábil previo al pago; rezago 3.
- **Feriados 2026:** coinciden con los días hábiles sin A3500 del BCRA. El 06/11 tampoco tiene A3500 pero hubo
  cierre de mercado; está bien que no figure. Confirma además que el 09 y 10/11 fueron feriados, lo que
  explica el avance del CER en los cierres de IAMC. Los de 2027 y 2028 siguen las reglas de traslado, pero
  pueden faltar puentes que todavía no se decretaron.

**Corrección 4: control del CER inicial.** El control aceptaba cualquier CER de las dos últimas semanas con 0,5 %
de margen, y dejaba pasar el error de TZXM7. Ahora compara con el CER de la liquidación menos el rezago, con
tolerancia de 1 pb, y deja un solo aviso por título con los valores. Pruebas en
`tests/test_extra_etapa11_revision.py`.

Prueba de carga completa en una copia de los datos: X30N6 cobra ARS 2.760.521 el 30/11, **definitivo**
(referencia 13/11, con el feriado del 23/11); X29E7 ARS 32.361.982, estimado; TZV28 ARS 76.328, estimado;
TZXM7 muestra el aviso. Faltan los precios de compra y el `instrumentos.json` de la cartera propia.

## Carga de precios de las letras CER (16/11/2026)

Con el OK de Felipe se cargaron con `precio-bono` las compras de X30N6 (125,0897, liquidación 03/09/2026) y
X29E7 (102,3645, liquidación 21/09/2026), tomadas del extracto en pesos de Bull (importe / nominales × 100).
Al hacerlo aparecieron tres errores más, corregidos con pruebas en `tests/test_extra_etapa11_revision.py`:

5. **`precio-bono` rechazaba los títulos ajustables** con el mensaje de la etapa 9 ("requiere supuestos").
   Ahora acepta los que tienen `iamc.indice`, valida la liquidación contra la fecha cruda del último pago de
   IAMC y exige precio en pesos.
6. **TIR "sin dato" en compras anteriores al primer cierre guardado.** La regla de la etapa 9 supone que en
   ese tramo pudo haber cupones. Un título ajustable de pago único sin renta (LECER, BONCER cero cupón,
   LELINK, capitalizable) no tiene pagos antes del vencimiento: ahora se toma como completo. Un título con
   cupones sigue pidiendo los pagos del tramo.
7. **El tablero se rompía** al mostrar la primera TIR de un título ajustable: el texto "(estimada, ARS)" se
   sumaba a una tupla. Habría impedido generar el dashboard de Mariano. Ahora la TIR anotada va como texto
   en pantalla y en Excel. Además, la TIR solo figura "estimada" si algún pago usa el REM o un supuesto
   manual: la de X30N6, con el CER ya publicado, es definitiva.

Resultado en una copia de los datos: X30N6, TIR 24,31 % en pesos (real 0,24 %), definitiva; X29E7, 25,47 %
estimada (real 0,33 %). Los tres tableros se generan sin errores.

## Cupones TAMAR: BAM27 y RVS1O (16/11/2026)

Codex juntó los avisos de pago oficiales (MAE y CNV) de los seis servicios de cada título y la definición
contractual de la tasa. Con esos datos se controló la fórmula del motor.

**Corrección 8: ventana del promedio.** Se probaron los 12 cupones pagados contra la TAMAR del BCRA:

| Fórmula | Cupones que coinciden al diezmilésimo |
|---|---|
| Contrato: días hábiles con dato de `[inicio − rezago, pago − rezago)` | 12 de 12 |
| Motor anterior: días corridos de `(inicio − rezago, pago − rezago]`, arrastrando el último dato | 0 de 12 (desvío de hasta 0,19 por 100 VN) |

Para que coincidan BAM27 dic-2025 y mar-2026, el 24/12/2025 tiene que contar como no hábil. Ese día el
BCRA no publicó TAMAR, y tampoco el 31/12.

**Corrección 9: cupón en curso.** El motor tomaba la tasa vigente de IAMC (`v.vig`) para el próximo cupón y
lo marcaba "definitivo". Al 13/11, esa tasa daba 4,55 (BAM27) y 2,20 (RVS1O) por 100 VN; con el contrato
salen 3,69 y 1,77. Ahora el cupón en curso se calcula con la ventana del contrato desde el último pago de
`pagos_manuales`. Sin esos pagos queda la tasa de IAMC.

**Agregado: piso.** `indice.piso` opcional; RVS1O tiene piso de 0 %.

Cuatro pruebas nuevas en `tests/test_extra_etapa11_revision.py` (`VentanaTamar`). Pasan las 972.

**Cobros de control.** Los importes oficiales superan lo acreditado por Bull: BAM27 57,1865 contra 57,0895
por 100 VN (−0,17 %) y RVS1O 28,3402 contra 28,2952 (−0,16 %). Los avisos no muestran deducciones. Lo más
probable es un arancel del agente de custodia. El flujo usa el importe oficial.
