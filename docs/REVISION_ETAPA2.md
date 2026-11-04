# Entrega de etapa 2 para revisión de Claude

Fecha: 04/11/2026. Implementada por Codex; revisión de Claude y validación de Felipe
pendientes. Se conserva el trabajo de la etapa 1. No se inició la etapa 3 ni se
hicieron commits.

## Qué se entrega

- Cliente de precios por panel de data912, con una llamada por panel necesario,
  validación de respuestas y caché local. Una falla no impide consultar otros paneles.
- Referencia dólar MEP: `mark` de AL30, registrada como ticker `MEP` en el historial.
  Si falta, se informa "sin dato" y no se inventa un valor.
- Historial propio en CSV que agrega solo cotizaciones vivas. Los datos de caché
  conservan la hora de su consulta original y no se registran como observaciones nuevas.
- Comandos `capturar`, `fijar-dia-cero` y `efectivo-dia-cero`, con la validación de la
  base y de los argumentos antes de consultar o escribir cuando hay un error de entrada.
- Foto de día cero en esquema 2: cantidades, precios, MEP y efectivo. Su guardado es
  atómico; no reemplaza una referencia existente sin `--forzar`.
- Carga tardía de efectivo, con saldos negativos o cero válidos, sin consultar la red
  ni volver a tomar precios. Completarla solo cambia el efectivo y su hora de carga.
- Patrimonio inicial en pesos y sus faltantes. Se calculan las posiciones con las
  cantidades y precios guardados; los costos no intervienen.
- Advertencias de precios de compra mayores a cinco veces el actual o menores a su
  quinta parte, con ticker y ambos precios. No bloquean ni cambian cálculos u orígenes.
- Advertencia de `actualizar-costos` cuando una estimación vuelve a pendiente.
- `estado` sigue sin consultar la red y muestra también la referencia inicial si existe.

La guía de uso está en [README.md](../README.md). El contrato y las convenciones se
mantienen en [CONTRATO.md](CONTRATO.md), [DOMINIO.md](DOMINIO.md) y
[FORMATOS.md](FORMATOS.md).

## Verificación de Codex

Entorno aislado: `~/.venvs/cartera`, Python 3.9.6, openpyxl 3.1.5. Desde la raíz:

```bash
PYTHONPATH=src ~/.venvs/cartera/bin/python -m unittest discover -s tests -p 'test_etapa1*' -v
PYTHONPATH=src ~/.venvs/cartera/bin/python -m unittest discover -s tests -p 'test_etapa2*' -v
PYTHONPATH=src ~/.venvs/cartera/bin/python -m unittest discover -s tests -p 'test_extra*' -v
```

Resultado: **64 pruebas originales de etapas 1 y 2 y 129 adicionales, todas pasan**.
Las pruebas originales y los fixtures se conservan sin cambios.

Las comprobaciones cubren caída de paneles, respuestas HTTP 200 con objeto de error,
precios inválidos, caché y su fecha original, límites de cinco veces, captura de MEP,
foto completa, efectivo faltante o deudor, carga tardía sin red, errores sin escritura,
protección frente a sobrescrituras y regresiones de la etapa 1. Las pruebas de comandos
usan respuestas ficticias en lugar de red. También se cubren escrituras simultáneas
de caché, lectura acotada del historial al crecer, transporte con tiempo de espera,
errores de rango antes de guardar efectivo y fallas de caché después de guardar una
captura o un día cero.

Se comprobó la conectividad de los seis paneles públicos requeridos de data912:
respondieron HTTP 200, con una única fila AL30 en MEP y las claves esperadas. La
documentación consultada se identificaba como v9.12.18. Esta comprobación de la fuente
pública no utilizó ni envió datos de clientes.
Además, el adaptador implementado obtuvo estado vivo para el panel de bonos y la
referencia MEP en una comprobación pública con AL30 y una carpeta temporal.

Los tickers del Excel de demostración son ficticios; no se presentan como una cartera
que pueda cotizarse contra los paneles reales. La demostración de los comandos se
verifica con esos datos y respuestas simuladas. No se incorporaron datos reales al
repositorio.

La demostración ficticia agregó siete filas al historial (seis especies y MEP), fijó
el día cero con valuación de posiciones de $2.770.000 y mostró el patrimonio como
faltante hasta cargar efectivo. Al completar ARS -1.000 y USD 0, mostró patrimonio
inicial de $2.769.000 sin volver a consultar precios.

## Criterios y límites

- `consultado_en` es la hora de consulta, nunca la del último operado. La API no da
  esa hora; la aplicación registra la consulta con su reloj. El estado vivo no
  permite asegurar cuán reciente fue la última operación.
- data912 es una fuente no oficial. Una respuesta inválida, una especie ausente o
  un precio no positivo llevan a caché o "sin dato", según lo disponible.
- Fijar el día cero exige precios vivos para todas las posiciones. El MEP puede
  faltar y el efectivo puede completarse después. Un costo pendiente no lo impide.
- El efectivo se conserva aparte de las posiciones. Un saldo desconocido no equivale
  a cero. El MEP se necesita para el patrimonio solo si el saldo USD es distinto de cero.
- El patrimonio inicial es una referencia, no el resultado integral de la cartera.
  El resultado con movimientos en pesos corresponde a la etapa 5; el resultado
  integral en dólares sigue fuera de alcance.
- Conforme al contrato, las posiciones de la base aportan la unidad de cotización;
  las cantidades y precios usados son los guardados en la foto. La base se conserva
  para mantener esa referencia de unidades, aunque luego cambien las tenencias.
- La fecha elegida para el día cero no reconstruye precios históricos: se guardan
  los precios recibidos al fijarlo. El comando rechaza fechas futuras en Argentina.
- `estado` no valúa la cartera con cotizaciones actuales; muestra su base y la foto
  inicial guardada. El tablero todavía no está implementado.
- Si el historial se guardó pero falló su caché, se informa lo guardado y el comando
  termina con error. Si el día cero ya se guardó y solo falla la caché, se avisa sin
  declarar fallida la fijación. No se consultan precios para completar efectivo.
- La caché serializa su lectura, fusión y publicación con un bloqueo de la carpeta.
  El historial agrega filas bajo bloqueo y lee solo el encabezado y el último byte,
  sin releer todas las observaciones previas en cada captura.

## Revisión solicitada a Claude

1. Revisar la correspondencia entre categorías y unidades de los paneles y las del
   Excel, manteniendo los datos reales fuera del repositorio.
2. Confirmar la foto de cantidades y precios, el patrimonio con saldos negativos o
   faltantes y el procedimiento de carga tardía del efectivo.
3. Revisar los avisos de posible unidad/moneda y de estimaciones perdidas, sin
   correcciones automáticas del origen o de los importes.
4. Comprobar el tratamiento de caché, caída parcial de la fuente y falta de MEP,
   junto con la distinción entre hora de consulta y hora del último operado.
5. Antes de la etapa 3, completar las entradas del tablero según el contrato y
   revisar su funcionamiento en el navegador. No avanzar automáticamente de etapa.

La revisión independiente de Codex y las pruebas no sustituyen la revisión de
Claude ni la validación de Felipe.

## Revisión de Claude

Aprobada con dos correcciones hechas por Claude, y probada con precios reales y una copia
de los datos reales, fuera del repositorio:

- `fijar-dia-cero --forzar` y el reemplazo de efectivo guardan la versión anterior en
  `historial_dia_cero/`. Al volver a fijar sin saldos nuevos, se conserva el efectivo cargado.
- Una fecha de efectivo futura se rechaza. Si falta o difiere de la del día cero, se advierte.

Pasan 212 pruebas: 28 de etapa 1, 36 de etapa 2 y 148 adicionales.
