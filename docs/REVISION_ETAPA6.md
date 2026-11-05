# Revisión de la Etapa 6

Entrega de Codex: 5 de noviembre de 2026. Se implementó únicamente “Rendimiento
realizado” de `PLAN.md`. Se leyeron `AGENTS.md`, el plan, `docs/HISTORIAL.md` y la
sección `cartera.historial` de `docs/CONTRATO.md` antes de comenzar. Queda para
revisión de Claude y validación de Felipe.

## Implementación

La API pública de `cartera.historial` expone `ErrorHistorial`, los lectores,
`consolidar`, `clasificar`, `construir_historial`, `conciliar_tenencias`,
`correr_historial`, `Historial` y `RealizadoHistorico`. La lectura y el cálculo se
separaron internamente en `_historial_lectura.py` y `_historial_calculos.py`.

- Lectura de la primera hoja de cada extracto XLSX, con encabezado exacto. Moneda
  y cuenta salen del título; no se adivinan si es ambiguo. Se conservan archivo,
  fila y los campos del renglón, incluidos Liquida y Precio, sin evaluar fórmulas.
  Los formatos inválidos se informan con contexto y no producen salidas.
- Deduplicación por moneda, cuenta, Operado, Comprobante, Numero, Especie e Importe.
  El control de Saldo usa el orden físico de cada archivo antes de deduplicar y
  tolerancia inclusiva de 1; una diferencia genera aviso sin bloquear.
- Clasificación explícita de los comprobantes especificados. Todo otro comprobante,
  incluido el vacío, queda en `sin_clasificar` y se lista completo en consola y HTML.
  No entra en el total. Las marcas adicionales de un renglón no pueden cambiar
  su clasificación o procedencia.
- Orden cronológico, compras antes de ventas y cierres del mismo día, luego número
  de comprobante. FIFO por orden de creación de lotes; prorrateo de costos y
  conservación de origen. Una venta sin suficientes lotes consume los conocidos,
  informa `cantidad_sin_lote` y deja desconocidos costo y resultado de esa venta.
  No toma compras futuras para cubrirla ni inventa costos.
- Cierres agrupados por especie y fecha, con todos sus pagos y toda la cantidad
  abierta. Un cierre sin lotes queda sin resultado conocido. Los pagos del cierre
  no se agregan también como renta.
- Ajustes con las nueve columnas de movimientos y solo los cinco tipos admitidos.
  Las compras por ajuste son estimadas, incluida una transferencia desde otro
  broker al valor de entrada; no se evalúa su rendimiento anterior.
- Conversión USD con MEP diario o el último anterior de hasta cinco días corridos,
  inclusivo; un ajuste puede usar su propio cambio. Si falta, se conserva el importe
  en dólares y se indica el equivalente desconocido, con aviso.
- Ingresos por clase y moneda, con sus signos. Cauciones agrupadas por moneda,
  clase y fecha, admitiendo varias patas de término; sin ambas patas se excluye
  el capital con aviso y números de comprobante. Aportes y retiros se informan
  aparte y las conversiones internas especificadas no cuentan como resultado.
- Total conocido de resultados e ingresos individuales conocidos, con ventas y
  valores excluidos y renglones sin clasificar visibles. Si falta una conversión
  dentro de una clase, su equivalente agregado queda desconocido, pero sus otros
  ingresos conocidos siguen participando del total. Se desglosa realizado de
  extracto y realizado que incluye estimaciones. No hay porcentaje.
- Lotes abiertos comparados contra la base por cantidad (tolerancia inclusiva 0,5)
  y costo. Las diferencias se informan; ninguna corrige la base.

## Comando y archivos

`historial --cliente SLUG` usa archivos locales, sin consultas de precios.
`--actualizar-mep` consulta exclusivamente los históricos de AL30 y AL30D mediante
la función `fetch`, calcula cierre AL30 / cierre AL30D en las fechas comunes y
actualiza el MEP diario. Las respuestas inválidas fallan sin publicar salidas.

Se escribe `realizado.csv`, con los nueve campos de `RealizadoHistorico`, fechas ISO
y celdas vacías donde el número es desconocido. Las salidas llevan permisos `600`.
Se validan los archivos y la semántica antes de consultar o publicar; no se reemplaza
una salida ante un extracto o auxiliar inválido. La carga regular no escribe MEP.

Los temporales y respaldos privados se preparan antes de reemplazar. Un fallo durante
el segundo reemplazo restaura la salida ya publicada, o su ausencia si no existía.
Un bloqueo de directorio evita intercalar dos corridas sin crear archivos de bloqueo.
Los temporales se limpian. Si la propia restauración también fallara, el error
identifica el respaldo privado conservado para revisión; no se simula éxito.

## Separación respecto del día cero y pantalla

El historial no usa ni cambia `movimientos.csv`, `dia_cero.json` ni `cartera.json`.
El comando puede funcionar sin día cero e incluso si esos dos archivos opcionales
no son interpretables: no pertenecen a este cálculo. Las cantidades y costos de
la base solo se leen para comparación.

El dashboard conserva las posiciones y el resultado desde el día cero existentes.
Si hay `extractos/`, agrega `id="rendimiento-realizado"` y el objeto `historial` de
`datos-cartera`, con los campos del contrato y detalles para revisar desconocidos y
diferencias. La sección muestra desgloses, origen, faltantes, avisos y cada campo de
cada renglón sin clasificar, escapado para HTML y con fechas ISO en JSON.

Si falla el historial, el resto del dashboard se genera con aviso. Sin `extractos/`
no agrega sección ni objeto. Generar HTML no escribe CSV realizado ni MEP diario.
La nueva sección permanece histórica: no se recalcula con cotizaciones en vivo y no
se suma al resultado desde el día cero. El JavaScript anterior quedó intacto.

## Demostración ficticia

Las pruebas originales generan un extracto con aporte 5.000 ARS, compra de 10 AAA por
1.000, venta de las 10 por 1.500 y dividendo de 70. Se informa:

| Concepto | ARS |
|---|---:|
| Realizado FIFO | 500 |
| Dividendos | 70 |
| Total conocido | 570 |
| Aporte, fuera del resultado | 5.000 |

La comparación con la base ficticia informa sus diferencias; no la sobrescribe.
Otra comprobación coloca un renglón desconocido de 900.000 junto a un dividendo de 7:
el total conocido es 7 y el renglón de 900.000 se lista completo, sin sumar.

## Pruebas ejecutadas

Se usó Python 3.9 del entorno existente, con `PYTHONPATH=src` y sin escribir bytecode.

```bash
PYTHONPATH=src ~/.venvs/cartera/bin/python -m unittest discover -s tests -p 'test_etapa*'
PYTHONPATH=src ~/.venvs/cartera/bin/python -m unittest discover -s tests -p 'test_extra*'
```

| Grupo | Pruebas | Resultado |
|---|---:|---|
| Etapas 1 a 6 | 299 | OK |
| Adicionales | 371 | OK |
| Total | 670 | OK |

Se agregaron 78 pruebas: 21 en `test_extra_historial_lectura.py`, 30 en
`test_extra_historial_calculos.py`, 10 en `test_extra_historial_dashboard.py` y 17 en
`test_extra_historial_integracion.py`. Cubren los formatos y el orden, preservación
de identificadores, desconocidos y comprobantes vacíos, FIFO, cierres multimoneda,
conversiones y faltantes, cauciones incompletas, ingresos parcialmente conocidos,
conciliación, escape, independencia del día cero, validación sin escrituras,
permisos, restauración de salidas y concurrencia.

Las pruebas originales emiten una advertencia de openpyxl por un título ficticio de
hoja de más de 31 caracteres; no hay fallos ni pruebas omitidas. No se modificó esa
prueba ni se ocultó la advertencia. `git diff --check` no informa problemas.
Se comprobaron mediante huellas los 52 archivos originales protegidos: pruebas,
fixtures, documentación normativa, instrucciones y revisiones anteriores sin cambios.
Solo se agregó esta revisión y se actualizó el README como se solicitó.

## Criterios de borde, dudas y límites

No se detectaron contradicciones que requirieran modificar pruebas o especificaciones.
Se aplicaron estos criterios compatibles con el contrato:

- `Numero` funciona como identificador: conserva enteros textuales sin pérdida de
  precisión, texto alfanumérico, números fraccionarios finitos y vacío; no se usa
  para inferir la clase. Orden numérico cuando corresponde y texto determinista.
- Un ajuste USD con `tc` lo usa; sin él busca MEP histórico. Esto no cambia la regla
  de moneda de los movimientos manuales de la Etapa 5.
- La actualización MEP conserva los días previamente disponibles y reemplaza las
  fechas comunes devueltas por la fuente. Nunca usa un precio de fecha futura para
  completar un día anterior. Solo las cotizaciones válidas participan del cociente.
- Un cierre conjunto ocupa el lugar del menor número de sus comprobantes. Los
  ajustes sin número conservan su orden de carga después de comprobantes numerados.
- En el historial, origen incompleto se muestra como “sin dato”: un costo en pesos
  desconocido puede deberse al MEP faltante y no necesariamente a algo que haya que estimar.

La actualización MEP se probó exclusivamente con respuestas ficticias `date`/`c`.
No se verificaron el formato, la cobertura ni la disponibilidad actuales del servicio
real, ni extractos reales del broker; esa revisión corresponde a Claude. Se probaron
los fallos de preparación, publicación y restauración normal, sin simular un corte
de energía o la terminación abrupta del proceso entre dos reemplazos. Cada reemplazo
es atómico, pero no se promete una transacción ante un corte del sistema.

No se verificó visualmente la nueva sección en un navegador real. Continúa la decisión
de Felipe de dejar esa revisión para Claude tras el bloqueo anterior de archivos
locales del navegador integrado. El HTML y JSON se comprobaron con datos ficticios;
no se intentó eludir ese bloqueo. Tampoco se verificaron avisos reales: no se enviaron,
no se accedió a credenciales y no se instalaron tareas programadas.

No se hicieron commits. El trabajo se detuvo al completar la Etapa 6.

## Revisión de Claude

Probada con una copia de los extractos reales, en una carpeta privada fuera de este repositorio. Las
cantidades derivadas cierran contra la base en las 20 especies; solo sobran MTCGO y VSCWO, cuya salida
no está en los extractos disponibles. Los importes coinciden con un cálculo independiente.

Se corrigió:

1. El lector rechazaba extractos reales: algunos archivos declaran un rango menor al que contienen, y el
   modo de solo lectura de openpyxl lo respeta. Ahora se abre en modo normal. Se agregó una prueba.
2. Las diferencias de costo avisaban por errores de redondeo. Ahora la tolerancia es de 1 peso.
3. Decisión de Felipe: `NOTA DE CREDITO EO` es un ingreso, en la clase `compensacion`.
4. Se documentó y se probó el orden de las compras dentro de un mismo día.

Falta el aspecto en pantalla de la sección y los extractos en dólares de 2026.
