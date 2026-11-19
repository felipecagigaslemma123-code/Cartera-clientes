# Revisión de la Etapa 12 — Informe para el cliente

16 de noviembre de 2026. **Esta etapa no siguió el reparto habitual.** Codex no pudo acceder al proyecto, y
Felipe decidió que Claude especificara e implementara la etapa. Por eso no hubo revisión cruzada: este
documento dice qué se verificó y qué no.

## Qué se hizo

- `src/cartera/informe.py`: `leer_datos_dashboard`, `armar_informe`, `informe_html`, `exportar_pdf` y el comando
  `informe` (`ejecutar_informe`), según `docs/INFORME.md` y `docs/CONTRATO.md`.
- `__main__.py`: subcomando `informe --cliente SLUG [--salida CARPETA] [--pdf]`.
- Pruebas: las 23 de aceptación de `tests/test_etapa12_informe.py`, escritas antes de implementar, y 5 en
  `tests/test_extra_etapa12_revision.py` para los casos que aparecieron con carteras reales.

## Cómo se verificó

| Control | Resultado |
|---|---|
| Pruebas de la etapa y de todo el proyecto | 1000 pruebas, todas aprobadas |
| Lectura y modelo, con una implementación independiente escrita al especificar | Las mismas 13 pruebas pasan con las dos implementaciones |
| Informe de sc contra el prototipo aprobado por Felipe | Mismos importes, pesos, TIR y cobros. Tres hojas A4 sin cortes |
| Informes de fcl y mdm (carteras más largas, sin día cero) | Se generan sin errores. La tenencia ocupa dos páginas y el encabezado de la tabla se repite |
| PDF con Chrome *headless* | Sale con las mismas hojas que la vista de impresión del navegador |

## Ajustes hechos al probar con carteras reales

1. **Letras ajustables repetidas.** En mdm, X29E7 y X30N6 aparecían dos veces: una desde `letras`, sin pago,
   y otra desde el flujo de fondos. Ahora va solo la del flujo.
2. **"$ sin dato".** Sin efectivo cargado, el indicador mostraba el signo de pesos delante de "sin dato".
3. **Gráfico de resultados ilegible.** mdm tiene 39 operaciones y fcl 59. Con más de 14, las barras se
   agrupan por mes y una nota dice cuántas operaciones son.
4. **Numeración de páginas.** El pie decía "1 / 3" aunque una tenencia larga ocupa más de una página impresa.
   Ahora muestra el título de la hoja.
5. **Redondeo.** Los decimales que terminan en 5 redondean hacia arriba, como el prototipo: 14,365 da
   US$ 14,37 y no 14,36.
6. **Rango de TIR.** La marca del rango entre compras era blanca y no se veía fuera de la barra. Ahora es una
   línea gris con topes.

Los cambios 1 a 4 están en la especificación (`docs/INFORME.md`) y los cubren pruebas.

## Qué no se verificó

- **El PDF en otra computadora.** La ruta de Chrome es la estándar de macOS. Sin Chrome, el comando deja el
  HTML y explica cómo imprimirlo.
- **Un informe de mdm o fcl revisado línea por línea.** Solo se controló que se generen y que los totales
  coincidan con su dashboard. Sin día cero, los dos dicen "sin dato" en patrimonio y resultado acumulado.
- **Rentas en pesos de mdm.** El indicador dice $ 0 porque su historial no registra rentas en pesos. Puede ser
  correcto, pero no se revisó contra los extractos.

## Corrección del 17/11/2026: resultado acumulado (versión 1.1)

Al analizar una cartera real con tenencias anteriores al primer extracto apareció un error de la versión 1.0.
El resultado acumulado era patrimonio − aportes + retiros, y esas tenencias entran sin un aporte registrado:
el informe las contaba como ganancia. En esa cartera daba de más por todo su valor de entrada. Lo mismo pasa
con los títulos transferidos desde otro broker. No se veía porque, sin día cero, el patrimonio es "sin dato".

**Nuevo cálculo, aprobado por Felipe:** ganancia realizada + resultado de los movimientos desde el día cero +
resultado de la tenencia actual frente a su costo. Como cada tenencia previa tiene su costo de entrada, lo
ganado antes no cuenta. No necesita el patrimonio ni el día cero. No incluye la variación del dólar sobre el
efectivo en dólares.

| Control con los dashboards reales | Resultado |
|---|---|
| Cartera con tenencias previas, sin día cero | Antes "sin dato" (y de más al cargar el día cero); ahora coincide con un cálculo independiente por patrimonio, capital inicial y aportes, con $ 58 de diferencia por conversiones de dólares |
| Cartera con historia completa y día cero | Antes y ahora difieren en $ 1.767 sobre $ 512.405 (0,3 %): la variación del dólar sobre el efectivo y conversiones |
| Cartera con una operación del historial sin resultado | Ahora "sin dato", con el motivo. Antes la ganancia realizada se mostraba como completa: ahora aclara que suma lo conocido |

Además, la nota dice el resultado de la tenencia con palabras ("una pérdida de $ …") en lugar de un monto con
signo negativo, y el signo pesos no se separa del número al cortar el renglón. Con doce años de cobros en
dólares y 59 operaciones, la hoja de flujo se pasaba 8 píxeles y las aclaraciones quedaban solas en una quinta
página: el gráfico de cobros por año pasó de 160 a 150 de alto y los renglones de próximos cobros, de 5 a 4
píxeles de margen. Pruebas nuevas en `tests/test_extra_informe_acumulado.py`; se actualizó la que esperaba la
fórmula anterior en `tests/test_etapa12_informe.py`. Suite: 1010 pruebas, todas aprobadas.

Sigue pendiente: Bull informa juntas renta y amortización, así que en una cartera con amortizaciones parciales
"Rentas cobradas" incluye capital devuelto. El resultado acumulado no cambia: esa parte se compensa con la
tenencia.

## Versión 1.3 del 18/11/2026: hoy, hasta hoy y de acá en adelante

Felipe mostró el informe a una clienta sin experiencia y no distinguió los cobros futuros de las ganancias
pasadas: leyó el "29" de 2026 en los cobros en dólares por año (dos rentas que todavía no cobró) como lo cobrado
en el año. En la misma hoja convivían el futuro y el pasado, y "Rentas cobradas" mostraba $ 124.432 mientras la
nota decía $ 202.678 (una cifra solo en pesos y la otra con los dólares convertidos).

Cambios, implementados por Claude con el pedido de Felipe:

- Tres partes en orden, cada una con su etiqueta de tiempo y una frase de qué muestra: **1. Tu cartera hoy**
  (Hoy), **2. Lo que ya ganaste** (Hasta hoy) y **3. Lo que vas a cobrar** (De acá en adelante, "Todavía no los
  cobraste"). La primera hoja abre con un resumen de las tres partes y su número principal.
- Lo pasado se lee como una cuenta: ganancia ya cobrada ± suba o baja de lo que todavía tenés = resultado total
  hasta hoy, con un desglose que suma exacto (antes las ventas de lotes estimados quedaban fuera de la nota).
- Lo futuro empieza por los próximos cobros. "Cobros por título" pasa a "Cobros futuros por título" y el gráfico
  anual dice "No incluye lo que ya cobraste" y marca el año en curso "desde hoy".
- Textos de vos y en lenguaje llano; la tabla de títulos dice "Desde la compra"; los CEDEARs se nombran en la
  frase de los dólares; glosario al final con solo las palabras de esa cartera.
- La tabla de títulos va en su propia hoja y la de cobros futuros no parte el título en tres renglones.
- Ajuste del mismo día, pedido de Felipe al ver el resumen: la parte 3 pasa a llamarse **Lo que vas a ganar
  desde hoy** y su tarjeta muestra la ganancia que falta cobrar en cada moneda, no el total a cobrar, que incluye
  lo invertido y se leía como ganancia. Una moneda sin la separación dice "sin dato" y una que depende de un
  índice proyectado, "incluye estimados".

Con los dashboards reales, cada hoja entra en un A4 salvo la tabla de títulos de las carteras de 20 y 28
posiciones, que ocupa dos páginas. Pruebas nuevas en `tests/test_extra_informe_lectura.py`; se adaptaron las que
buscaban los textos anteriores. Suite: 1045 pruebas, todas aprobadas.

Sigue pendiente: Bull informa juntas renta y amortización. En una cartera con amortizaciones parciales, "Rentas"
incluye capital devuelto y el renglón dice "intereses": la ganancia ya cobrada da de más y la baja de lo que
todavía se tiene, en la misma medida. El resultado total no cambia.
