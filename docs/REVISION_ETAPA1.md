# Entrega de etapa 1 para revisión de Claude

Fecha: 04/11/2026. Claude revisó la primera entrega y confirmó que los cálculos están
bien. Esta entrega atiende sus correcciones de costos con historial y fechas
futuras. La verificación de esta corrección y su revisión final se registran abajo.
No se inició la etapa 2 ni se hicieron commits.

## Qué se entrega

- Importador del Excel con errores agrupados por hoja, fila y ticker. Lee datos de
  entrada sin depender del cálculo de fórmulas y conserva los costos de extracto.
- Cálculos por unidad y por 100 nominales, con costos reales, estimados, mixtos o
  incompletos; los datos faltantes no se convierten en cero.
- Comandos `importar`, `actualizar-costos` y `estado`, con `--datos` o
  `CARTERA_DATOS`.
- Base inicial versionada: cantidades, lotes, fechas, origen de costos y huella del
  Excel validado. `importar` conserva el rechazo de una base existente. La corrección
  de costos guarda la versión anterior completa y reemplaza la base atómicamente.
- Rechazo de fechas futuras en ambos comandos, con hoy calculado en Argentina y
  error por hoja, fila y ticker. La fecha de hoy se acepta.
- Especificación actualizada con la decisión de Felipe de medir el resultado
  completo con movimientos, conservando la revisión por etapas.

La guía de uso y la demostración ficticia están en [README.md](../README.md).

## Verificación de Codex

Entorno aislado: `~/.venvs/cartera`, Python 3.9.6, openpyxl 3.1.5.

```bash
PYTHONPATH=src ~/.venvs/cartera/bin/python -m unittest discover -s tests -p 'test_etapa1*' -v
PYTHONPATH=src ~/.venvs/cartera/bin/python -m unittest discover -s tests -p 'test_extra*' -v
```

Resultado de esta corrección: **28 pruebas originales y 73 adicionales, todas
pasan** con el mismo entorno. Se incorporaron 31 casos sobre
actualización con historial, cantidad distinta sin escritura, base inexistente,
Excel sin cambios, actualizaciones seguidas, fechas futura/de hoy, ambigüedades de
origen y fallas al escribir o publicar el historial o reemplazar la base. Se probó
también una colisión forzada de nombres históricos sin sobrescribir una versión.
Las pruebas originales y los fixtures se conservan sin cambios.

La demostración importó y volvió a leer las seis posiciones y los nueve lotes del
Excel ficticio. En la demostración de correcciones se actualizó el costo de BBB
de $51.000 a $52.000, conservando el origen mixto y el respaldo anterior. Repetir
el mismo Excel informó que no había cambios y mantuvo una sola versión histórica.
No se consultaron ni incorporaron datos reales de clientes. Las
pruebas de etapas 2 a 5 requieren módulos todavía no implementados.

## Criterios de esta entrega

- `estado` no consulta precios ni toma el costo como precio: informa "sin dato"
  para valuación y resultados actuales. El Excel solo aporta las columnas de
  entrada especificadas, no sus columnas humanas de precios actuales.
- `cartera.json` es la base de importación; no es la captura del día cero, que se
  prepara en la etapa 2. `importar` rechaza una base existente; `actualizar-costos`
  permite corregir lotes manteniendo las posiciones y sus cantidades totales.
- Antes de cada corrección efectiva se conservan los bytes completos de la base
  anterior en `historial_cartera/`, con fecha, hora y sufijo único. La base se
  reemplaza atómicamente; si falla la operación, la versión anterior queda intacta.
  Un respaldo publicado antes de un fallo del reemplazo permanece y no acredita
  por sí solo que la corrección haya finalizado.
  Una corrección sin cambios de datos no crea archivos ni modifica metadatos.
- La corrección informa costo anterior, nuevo y estados de origen por especie
  modificada; advierte sin bloquear si no puede conservar los lotes de extracto
  por cantidad, fecha y costo, o si detecta una reasignación ambigua entre extractos
  y otros lotes. Reordenamientos o la corrección aislada de una nota de extracto
  no avisan; ciertas ediciones simultáneas de notas sí pueden advertir.
- Se conserva el esquema 1 y los campos adicionales de la raíz y de `origen`;
  `importado_en` y `origen` corresponden al nuevo Excel cuando hay cambios.
- La comparación estática por precio del día cero sigue disponible en cálculos
  como indicador por posición; no representa el resultado integral con flujos.
- El total de valuaciones de la API suma solo valores conocidos. Las listas de
  posiciones sin costo y sin precio son independientes y pueden superponerse.

## Revisión solicitada a Claude

1. Comprobar columnas, fechas, nominales y criterio de costos contra el formato real,
   manteniendo los archivos de clientes fuera de este repositorio.
2. Revisar que la tolerancia de cantidades de 0,5 definida en la especificación sea
   adecuada para los activos utilizados. No se cambió ese criterio.
3. Revisar el nuevo procedimiento de corrección con historial, el reemplazo atómico,
   los avisos de alteración de extractos y los casos sin cambios ni escritura.
4. Antes de etapa 2, completar la referencia inicial con cantidades y efectivo.
   Antes de etapas 3 y 5, completar los datos del tablero y la conciliación de flujos,
   incluidos costos estimados vendidos, rentabilidad porcentual y conversión MEP.

El control de precios de la etapa 2 queda especificado en `PLAN.md` y `DOMINIO.md`:
si el precio de compra es mayor a cinco veces el actual o menor a su quinta parte,
se advierte con ticker y ambos precios por posible error de unidad o moneda. No
bloquea, recalcula ni cambia el origen del lote. No se implementó ese control ni
se añadió su prueba a la etapa 2 en esta entrega.

La revisión independiente de Codex complementa las pruebas; no sustituye esta
revisión de Claude ni la validación de Felipe.
