# Revisión — Tenencia de letras

05/11/2026 · Implementación de Codex. Revisada por Claude el 11/11/2026: ver al final.

## Actualización del 25/11/2026 — motor instalado

Por decisión de Felipe, el motor deja de ser una copia: `requirements.txt` fija
Fixed Income Toolkit a `v0.2.0` desde GitHub privado, y `letras.py` importa
`financial_engine`. Se elimina `_motor_letras/`, incluido su manifiesto. La
comparación del código previo confirma los mismos cálculos (el único ajuste de
la copia era el import de `day_count`). R006 continúa sin aprobación. El resto
de esta revisión conserva la evidencia histórica de la entrega y de la copia
que existía entonces; ya no describe el mecanismo de instalación vigente.
Ver [separación de renta fija](SEPARACION_RENTA_FIJA.md).

## Entrega

Se agregó un panel de lectura al dashboard, sin calculadora ni formulario, para las posiciones de tipo `letra`: nominales vigentes, vencimiento, días corridos restantes y pago contractual previsto. Cada especie permite desplegar las compras con precio limpio manual por 100 VN, fecha de compra, liquidación, nominales remanentes y rendimiento hasta el vencimiento.

`cartera.letras` usa el mismo FIFO que los movimientos existentes, mediante una fábrica privada opcional que conserva el comportamiento anterior de `aplicar_movimientos`. No reconstruye otra cartera desde los extractos históricos. Se conservan los precios de cada compra ante ventas parciales; una venta total quita la especie del panel. Las cantidades agregadas salen de la posición vigente. Si los lotes no concilian por la tolerancia de importación, se informa la diferencia y no se inventa un lote.

El motor validado de Fixed Income Toolkit se conserva en una copia versionada de tres módulos puros, con manifiesto SHA-256. Solo se adaptó un import relativo. No se modificó el Toolkit ni se incorporaron dependencias. El beneficio es poder ejecutar cartera sin depender de la carpeta sincronizada; la actualización del motor requiere revisar y renovar explícitamente esta copia.

Se mantienen VPV contractual 30/360 Tesoro y rendimiento de compra ACT/365, con Decimal. El contador visible usa la fecha de Argentina y días corridos reales, incluidos sábados, domingos y feriados. Su actualización cada minuto no depende de que funcione la consulta de precios.

El pago previsto no se incorpora al efectivo, la valuación, el resultado integral, el realizado ni el patrimonio inicial. Una letra vencida conserva el aviso de cobro sin confirmar hasta registrar el movimiento correspondiente. La venta anticipada mantiene los cálculos realizados existentes; no se proyecta un precio de venta.

## Entradas y comandos

`instrumentos.json` incorpora los datos contractuales explícitos bajo `letra`: familia, moneda de pago, emisión, TEM de emisión, base nominal del VPV y fuente. No se deducen del ticker. El esquema y ejemplo ficticio están en [LETRAS.md](LETRAS.md).

Se agregaron `letras --cliente SLUG`, para listar referencias, y `precio-letra`, para cargar precio limpio, moneda y liquidación de una compra. El archivo auxiliar `compras_letras.json` queda separado de la base y de los costos netos. Verifica la huella de origen para evitar reasignar precios después de una corrección o reordenamiento. La publicación es atómica y privada, no escribe si no hay cambios y conserva el archivo anterior ante una falla. Un JSON corrupto, una referencia inexistente o un enlace no se sobrescriben.

Sin precio o datos contractuales suficientes se informa el faltante, nunca cero. Una liquidación anterior a la compra, futura o desde el vencimiento se rechaza al cargarla; el panel tampoco calcula rendimiento si la liquidación precede la emisión. El precio manual siempre se expresa por 100 VN; normalizar el VPV desde otra base contractual evita multiplicar el rendimiento por un cambio de unidad. Los pagos y porcentajes se presentan con dos decimales, conservando el cálculo original en el JSON.

## Pruebas

Ejecutadas con Python 3.9 del entorno de cartera, sin datos ni canales reales:

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src:tests ~/.venvs/cartera/bin/python -m unittest discover -s tests -p 'test_etapa*'
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src:tests ~/.venvs/cartera/bin/python -m unittest discover -s tests -p 'test_extra*'
```

Resultado: **338 pruebas de etapas y 440 adicionales, 778 en total, todas aprobadas**. Las 52 nuevas están en `test_extra_letras_calculos.py` (32), `test_extra_letras_archivos.py` (11) y `test_extra_letras_dashboard.py` (9). Se verificó que las pruebas originales, los fixtures y los documentos preexistentes conservan sus huellas.

Cobertura nueva: cálculos aprobados y rendimiento negativo, ACT/365 frente a 30/360, febrero bisiesto, cambio de fecha argentina, fines de semana, hoy y vencidas; compras y ventas por FIFO, datos faltantes, costos distintos del precio limpio, referencias modificadas, invariancia de unidades, rechazo de fechas incoherentes, separación patrimonial, persistencia y fallas atómicas, JSON corrupto/enlaces, HTML escapado y CSP sin cambios. El JavaScript se ejecutó en un motor local con DOM, reloj y red simulados; se probó medianoche argentina con una zona de navegador diferente.

La suite de etapas emite la advertencia preexistente de openpyxl por un título de hoja de más de 31 caracteres en una prueba; no hubo errores ni pruebas omitidas en estas corridas.

Se generó una demostración temporal ficticia en `/private/tmp/cartera-letras-demo.html`: 1.000 VN, TEM contractual 2%, precio 110 por 100 VN, vencimiento 01/06/2027; al 05/11/2026 muestra 208 días corridos, pago previsto 1.268,24 ARS y rendimiento de compra 15,29%. No se abrió en un navegador real ni se envió ningún aviso.

## Pendientes y límites

- **Dólar linked:** Felipe indicó D30S6 como ejemplo. Se verificaron sus condiciones en la resolución conjunta 13/2026, artículo 5, pero R006 del Toolkit continúa sin validación y sin aprobación para producción. La familia `LELINK` se lista con precio y vencimiento, y un aviso claro de cálculo pendiente; no se publica pago ni rendimiento. Para habilitarla falta completar la validación y aprobación de R006, incluyendo la unidad del precio y el tipo de cambio aplicable. No se usó MEP ni se supuso un cambio futuro. Esta parte solicitada queda pendiente.
- No se habilitan CER, TAMAR ni letras pagaderas en USD con la metodología de LECAP.
- No se verificó la presentación, el despliegue táctil, los temporizadores en una pestaña suspendida ni el comportamiento de un archivo local en un navegador real. La revisión visual queda para Claude, conforme a la elección previa de Felipe.
- No se comprobó con datos reales ni con nuevas consultas reales de precios. Los contratos y precios manuales deben ser revisados por el asesor; no se cargó D30S6 en ninguna cartera de cliente.
- La descarga Excel conserva sus hojas existentes; el panel nuevo no agrega una hoja.
- El archivo de precios manuales tiene reemplazo atómico, sin un historial de versiones propio. La conservación histórica de los costos importados sigue igual.

No se hicieron commits, no se instalaron tareas programadas, no se leyeron credenciales y no se enviaron notificaciones reales.

## Revisión de Claude — 11/11/2026

**Resultado: aprobada, sin cambios de código.**

- **Pago al vencimiento contra IAMC.** El motor reproduce el monto al vencimiento (`mv`) que publica IAMC
  para las ocho letras del cierre del 06/11/2026 (S13N6, S26F7, S29E7, S30N6, T15E7, T30A7, T30J7 y T31Y7),
  al cuarto decimal.
- **Motor copiado.** Las huellas de los tres módulos coinciden con las del manifiesto.
- **Navegador.** Panel revisado con una cartera ficticia: 1.000.000 VN de S26F7 muestran 107 días corridos
  y un pago de 1.083.676,20 ARS; una compra a 100,90 muestra un rendimiento de 7,40 % hasta el vencimiento.
  El contador usa la fecha de Argentina.
- **Calendario.** El pago previsto de la letra entra al calendario del flujo de fondos en la columna ARS.

Sigue pendiente lo que ya estaba fuera de alcance: dólar linked (R006 sin aprobar) y letras en CER, TAMAR
o dólares.
