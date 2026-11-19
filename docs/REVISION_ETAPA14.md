# Revisión de la Etapa 14: riesgo de la cartera

Revisión de Claude del 18/11/2026.

## Cómo se hizo

1. Codex leyó la bibliografía de Administración de Carteras y escribió `RIESGO_METODOLOGIA.md` con su
   comprobación (`tools/riesgo/`). Claude repitió la comprobación: los 2.383 valores del caso ficticio coinciden y
   los cotejos con los Excel y los libros dan lo mismo.
2. Claude analizó las tres carteras reales con esa metodología (`tools/riesgo/analizar_carteras.py`), escribió
   `RIESGO.md`, el contrato, el fixture y `tests/test_etapa14_riesgo.py`. Validó las pruebas con una implementación
   de referencia propia: pasan con ella y fallan sin ella.
3. Codex implementó `src/cartera/riesgo.py`, `src/cartera/_riesgo_calculos.py`, el comando `riesgo` y
   `tests/test_extra_riesgo.py` sobre una copia del repositorio. Claude trajo solo esos archivos.

## Resultado

- Suite completa: 1.079 pruebas; fallan solo `test_etapa10_iol.EnElHistorial.test_amortizacion_sin_baja_es_renta`
  y `test_los_cobros_no_incluyen_el_gasto`, que ya fallaban antes por cambios sin commitear del historial.
- Con las carteras reales (fcl, mdm, sc), el comando da **exactamente** los mismos 83 valores que el análisis del
  18/11, versión estricta (volatilidades, VaR, ES, beta, cobertura, Herfindahl y escenarios de tasa). Primero se
  probó con copias de los datos y los históricos guardados; después, con red sobre `privado`.
- El reporte HTML se revisó en Chrome: secciones completas, formato argentino y "sin dato" con su motivo.

## Lo que agregó Codex además de la especificación

- Valida el bloque del dashboard: tickers, duplicados, valuaciones y fecha.
- Descarta precios posteriores a la fecha del tablero y fechas duplicadas con precios distintos.
- Sin convexidad en IAMC, los escenarios de esa familia quedan sin dato con un aviso.
- Escribe en forma atómica y no deja nada a medias si falla. Guarda las copias de data912 solo si el comando
  termina bien.

Todo es coherente con la regla de no inventar datos.

## Pendiente de Felipe

- Moneda de medición: CCL (actual) o MEP.
- Tasa libre de riesgo, para sumar Sharpe y Sortino.
- Si se completa un CEDEAR sin historia local con su subyacente (versión "aproximada" del análisis del 18/11).
- Si el riesgo se muestra en el dashboard o en el informe del cliente.
