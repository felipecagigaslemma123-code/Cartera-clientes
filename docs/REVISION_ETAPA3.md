# Entrega de etapa 3 para revisión de Claude

Fecha: 04/11/2026. Implementada por Codex siguiendo `PLAN.md`, `CONTRATO.md` y
`DASHBOARD.md`. La revisión de Claude y la validación de Felipe siguen pendientes.
No se inició la etapa 4 ni se hicieron commits.

## Qué se entrega

- `cartera.dashboard.generar_html`, con los datos embebidos del contrato y una vista
  legible sin dependencias externas. El JSON escapa `<` como `\u003c`, de modo que un
  texto que contenga `</script>` no cierre el bloque de datos.
- Comando `dashboard`: exige una base, consulta los paneles y el MEP, lee los archivos
  opcionales del cliente y publica `dashboard.html` atómicamente con permisos `600`.
  No agrega filas al historial. Si cae la fuente, genera el archivo con los datos
  guardados o los faltantes marcados y termina normalmente.
- Posiciones con cantidad, precio, valuación, peso, variación diaria, costo y origen,
  resultado desde la compra, variación de precios desde el día cero y distancia a
  niveles. Los costos estimados o mixtos se distinguen de los de extracto.
- Totales por tipo y general, en pesos y MEP, con cantidad de precios faltantes y
  cobertura explícita de los resultados calculables desde la compra.
- Efectivo actual y del día cero separados de posiciones y pesos. Referencia inicial
  con valuación, patrimonio o los datos que le faltan.
- Vencimientos a 60 días inclusive y especies ya vencidas. Gráficos SVG estáticos de
  las últimas 500 observaciones por especie, con aviso si no hay historial suficiente.
- Actualización al abrir y cada 60 segundos: una consulta por panel y MEP, máximo de
  15 segundos por consulta y protección contra rondas solapadas. Usa datos anteriores
  sin renovar su hora si una consulta falla.
- Estados con palabras: “En vivo”, “Último dato” y “Sin dato”. Los embebidos se muestran
  como último dato hasta confirmarse. Se avisa ante una ronda fallida, más de cinco
  minutos sin éxito o un archivo generado otro día.
- Inserción de textos escapados en Python y con `textContent` en JavaScript, CSP
  incluida y ningún almacenamiento de datos en el navegador.

Los archivos opcionales ausentes no se rellenan con ceros. Un historial con filas
inválidas las omite y deja un aviso; no se modifica ese archivo. Los archivos JSON
presentes pero inválidos se informan como error para evitar una pantalla engañosa.

## Alcance de los indicadores

No se calcula ni se muestra un resultado completo. Su recuadro contiene únicamente
“se calcula cuando estén los movimientos”; eso corresponde a la etapa 5. La variación
de precios conserva su nombre y no se presenta como el resultado económico completo.
Los importes del efectivo no se agregan a las valuaciones de posiciones ni a los pesos.

El modo de la API sin `posiciones` sigue siendo válido: conserva los valores embebidos,
pero no consulta ni recalcula precios en vivo porque faltan cantidades o unidades.

## Verificación de Codex

Entorno: Python 3.9.6, openpyxl 3.1.5 y JavaScriptCore del sistema para ejecutar las
pruebas del script, sin instalar dependencias adicionales.

```bash
PYTHONPATH=src ~/.venvs/cartera/bin/python -m unittest discover -s tests -p 'test_etapa1*' -v
PYTHONPATH=src ~/.venvs/cartera/bin/python -m unittest discover -s tests -p 'test_etapa2*' -v
PYTHONPATH=src ~/.venvs/cartera/bin/python -m unittest discover -s tests -p 'test_etapa3*' -v
PYTHONPATH=src ~/.venvs/cartera/bin/python -m unittest discover -s tests -p 'test_extra*' -v
```

Resultado acumulado: **272 pruebas aprobadas** al entregar (277 tras la revisión de Claude), sin omisiones:

- `test_etapa1*`: 28.
- `test_etapa2*`: 36.
- `test_etapa3*`: 30.
- `test_extra*`: 178.

Las 30 pruebas nuevas de esta entrega se agregaron en archivos `test_extra_*`; se
incluyen en ese total junto con las comprobaciones de las entregas anteriores.

Se agregaron pruebas `test_extra_*` del renderizado, de los comandos y del JavaScript.
Las siete pruebas del script se ejecutaron con JavaScriptCore y DOM/red ficticios:
validan cálculos por 100, MEP y efectivo excluido; fallas parciales y posteriores;
conservación de valores y horas; consultas por panel; rondas sin solapamiento y timeout;
modo estático, fechas, vencimientos y horas faltantes. Ese DOM simulado no equivale
a probar la página dentro de un navegador real.

Las pruebas existentes y los fixtures se conservaron sin cambios. Todos los datos
utilizados en pruebas y demostraciones son ficticios. No se consultaron archivos
reales de clientes.

## Lo que no se pudo verificar en el navegador

La herramienta de navegador disponible bloqueó el acceso al HTML local mediante
`file://`. Se dejó la comprobación visual para Claude y no se intentaron rutas
alternativas para eludir ese bloqueo.

Por eso no se verificaron en un navegador real:

- Apertura del archivo con doble clic, disposición de la página en pantallas anchas
  y angostas, y desplazamiento horizontal limitado al contenedor de la tabla.
- Consultas reales desde el origen de archivo, permisos CORS y aplicación efectiva
  de la CSP incluida.
- Consola sin errores, cambios visibles tras una ronda de 60 segundos y recuperación
  visual ante la caída total o parcial de la fuente.
- Presentación final de los gráficos SVG, textos largos y avisos en el navegador.

Las pruebas de JavaScript y del HTML comprueban comportamiento y estructura de forma
controlada; no permiten afirmar esas comprobaciones visuales ni de seguridad del
navegador como realizadas.

## Revisión solicitada a Claude

1. Generar el HTML con datos ficticios y abrirlo con doble clic. Revisar el diseño en
   pantalla ancha y angosta y la legibilidad de importes, estados, notas y gráficos.
2. Comprobar consultas por panel y MEP, el origen local/CORS, la consola y la CSP.
3. Comprobar actualización a 60 segundos, ausencia de rondas solapadas y recuperación
   frente a fallas, conservando datos y horas anteriores correctamente marcados.
4. Contrastar los cálculos de cantidades, nominales por 100, costos estimados,
   comparables y MEP, manteniendo el efectivo separado y el resultado completo vacío.
5. Revisar vencimientos, datos faltantes y el caso de archivo generado otro día.

No avanzar a alertas hasta completar la revisión y la validación de esta etapa.

## Revisión de Claude

Aprobada con retoques hechos por Claude. Se comprobó en el navegador con precios reales y
una copia de los datos reales, fuera del repositorio: actualización, cálculos, caída total
y parcial, recuperación, rondas sin solapamiento, avisos y pantalla angosta.

- La columna del ticker queda fija al desplazar la tabla.
- Fechas y horas en formato argentino, con hora de Argentina y singular para "1 día".
- Se quitaron las demostraciones temporales de `tmp/`, que no debían quedar en el repositorio.

Queda para Felipe comprobar la apertura con doble clic en su navegador. El ciclo de 60
segundos sin intervención se revisó en el código, sin esperar a que se disparara solo.
