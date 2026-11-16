# Prueba de la API del BCRA

`tools/bcra_extraer.py` consulta el catálogo y los históricos públicos de
[Estadísticas Monetarias v4](https://www.bcra.gob.ar/apis-banco-central/).
El [manual](https://www.bcra.gob.ar/archivos/Catalogo/Content/files/pdf/principales-variables-v4.pdf)
documenta los rangos, la paginación y el acceso sin credenciales.

| Serie | ID v4 | Unidad publicada |
| --- | --- | --- |
| CER | 30 | Índice base 02/02/2002 = 1 |
| TAMAR de bancos privados | 44 | Porcentaje nominal anual |
| Tipo de cambio mayorista de referencia, Comunicación A 3500 | 5 | ARS por USD |

Se verificaron los identificadores en el catálogo de la API y se contrastaron
las definiciones con las [principales variables del BCRA](https://www.bcra.gob.ar/principales-variables/).

## Cómo generar una muestra

Desde la carpeta de Cartera, elegí un archivo nuevo fuera del proyecto.

```bash
python3 tools/bcra_extraer.py --desde 2026-09-23 --hasta 2026-09-30 \
  --salida /tmp/bcra-septiembre-2026.json
```

Las fechas del rango son inclusivas. El JSON guarda la fecha de cada observación,
la hora de captura en Argentina, el identificador, la URL, la unidad y las
fechas que informa el catálogo. Los valores se guardan como texto decimal para
conservar los dígitos de la fuente. TAMAR conserva el porcentaje anual publicado.
La hora de captura y la fecha de la observación son campos distintos. La API no
entrega la fecha de publicación de cada observación en el histórico consultado.

Una serie vacía se marca como `sin dato`. Los días sin observación quedan
ausentes. La captura se escribe después de validar las tres series y se conserva
cada archivo previo. El script se ejecuta por separado del dashboard y usa
exclusivamente datos macroeconómicos públicos.

En el piloto D30S6, el A3500 consultado para el **25/09/2026** fue **1.523,9662
ARS/USD**. La [condición de emisión](https://www.argentina.gob.ar/normativa/nacional/resoluci%C3%B3n-13-2026-423892/texto)
define el tercer día hábil previo al pago como fecha de referencia. Esta prueba
documenta el dato publicado. La aplicación de las reglas del título y la
validación del pago quedan para el siguiente paso.
