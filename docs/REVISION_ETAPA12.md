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
