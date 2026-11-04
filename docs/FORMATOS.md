# Formatos

## Excel de punto de partida

Ejemplo: `fixtures/punto_partida_demo.xlsx`. Dos hojas; encabezados en la **fila 4** y
datos desde la 5.

### Hoja `Cartera`

Solo se leen estas columnas; las demás son para lectura humana.

| Col | Campo |
|---|---|
| A | Ticker |
| B | Especie |
| C | Tipo: `cedear`, `accion`, `bono`, `on`, `letra` |
| D | Cantidad |
| E | Cotiza cada: 1 o 100 |

Las filas de datos terminan en la fila cuyo ticker es `Total` o está vacío.

### Hoja `Lotes`

| Col | Campo | Uso |
|---|---|---|
| A | Ticker | |
| B | Cantidad | |
| C | Origen | `Extracto` o `A estimar` |
| D | Fecha de compra | la completa el asesor en lotes a estimar |
| E | Cotiza cada | |
| F | Precio de compra | la completa el asesor en lotes a estimar |
| G | Costo total | valor real en lotes de extracto |
| H | Nota | texto libre |

### Cómo interpretar cada lote

Algunas celdas tienen **fórmulas que pueden no tener valor calculado**, porque el archivo
quizá nunca se abrió en Excel. Abrí el libro **sin** `data_only=True` y usá solo los datos
de entrada:

| Origen en Excel | Datos | Resultado |
|---|---|---|
| `Extracto` | G numérico | `origen="extracto"`, `costo=G`, `precio=G / B × E` |
| `A estimar` | F numérico | `origen="estimado"`, `precio=F`, `costo=B × F / E` |
| `A estimar` | F vacía | `origen="pendiente"`, `precio` y `costo` `None` |

Ignorá el contenido de F en lotes de extracto y el de G en lotes a estimar.

### Validaciones

Cada una agrega un error; se informan todos juntos:

- Suma de cantidades de lotes distinta de la cantidad de la especie (tolerancia 0,5).
- Especie sin lotes, o lote de un ticker que no está en `Cartera`.
- Ticker repetido en `Cartera`.
- Tipo desconocido, o `cotiza_cada` que no coincide con el tipo.
- Cantidad menor o igual a cero.
- Lote de `Extracto` sin costo numérico positivo.
- `Origen` desconocido.
- Lote estimado con precio menor o igual a cero.
- Lote estimado con precio pero sin fecha.
- Fecha de compra posterior a hoy, en hora de Argentina, en cualquier lote con
  fecha; el error identifica hoja, fila y ticker. La fecha de hoy se acepta.

Una fecha válida cargada sin precio no es un error: el lote sigue pendiente.

## Carpeta de datos

```text
$CARTERA_DATOS/clientes/<slug>/
  perfil.json          lo escribe el asesor
  instrumentos.json    lo escribe el asesor
  niveles.json         lo escribe el asesor
  efectivo.json        lo escribe el asesor
  cartera.json         generado por importar
  historial_cartera/   versiones completas anteriores a actualizar-costos
  dia_cero.json        generado por fijar-dia-cero
  historial_dia_cero/  versiones completas anteriores del día cero
  movimientos.csv      generado por movimiento
  historial.csv        generado por capturar
  cache_precios.json   generado
  estado_alertas.json  generado
  alertas.log          generado
  dashboard.html       generado
```

### `cartera.json` — base importada (versión 1)

```json
{
  "esquema_version": 1,
  "importado_en": "2026-11-04T14:00:00-03:00",
  "origen": {
    "archivo": "punto_partida_demo.xlsx",
    "sha256": "<huella SHA-256 de los bytes del Excel>"
  },
  "posiciones": [
    {"ticker": "AAA", "especie": "CEDEAR Demo A", "tipo": "cedear", "cantidad": 100.0, "cotiza_cada": 1}
  ],
  "lotes": [
    {"ticker": "AAA", "cantidad": 100.0, "origen": "pendiente", "fecha": null, "precio": null, "costo": null, "nota": "Falta estimar"}
  ]
}
```

`importado_en` tiene zona horaria de Argentina y registra la importación, no la fecha
de compra ni el día cero. `origen.archivo` guarda solo el nombre del archivo, sin su
ruta; `sha256` es la huella hexadecimal de 64 caracteres de sus bytes. Las fechas de
lotes se guardan como `AAAA-MM-DD` o `null`; los demás campos conservan el significado
de `cartera.punto_partida`. Los importes desconocidos se guardan como `null`.

La base se escribe únicamente después de validar todo el Excel. Si `cartera.json` ya
existe, `importar` falla sin modificarlo; no tiene opción `--forzar`. Para corregir
costos se usa `actualizar-costos`, que exige esa base y conserva el conjunto de
tickers, especie, tipo, `cotiza_cada` y cantidad total de cada posición. Los lotes
pueden cambiar siempre que sigan cerrando con la cantidad de la especie.

Antes de reemplazar atómicamente la base, se guardan todos los bytes de la versión
anterior en `historial_cartera/cartera_FECHA_HORA_uuid.json`. Fecha y hora corresponden
a Argentina; el sufijo único evita pisar versiones incluso en correcciones seguidas.
Si falla el respaldo o el reemplazo, la base anterior queda intacta. Si el respaldo
ya se publicó cuando falla el reemplazo, permanece completo; no confirma que la
actualización haya finalizado. El esquema sigue en versión 1; se conservan los
campos adicionales de la raíz y de `origen`, sin admitir campos desconocidos en
los registros de posiciones y lotes. Se
actualizan `importado_en`, el nombre y la huella del archivo nuevo.

Si no cambia ningún dato interpretado, no se crea historial ni se modifica la base,
aunque cambien el nombre del Excel, sus metadatos o el orden de filas. La detección
compara posiciones y lotes, conservando sus repeticiones. Los movimientos futuros
no sobrescriben esta base: se aplican sobre ella para reconstruir el estado.

En la etapa 1, `estado` lee exclusivamente esta base. No interpreta costos como
precios actuales ni consulta precios; donde corresponda muestra "sin dato".

### `perfil.json`

```json
{"slug": "cliente-demo", "nombre": "Cliente Demo", "asesor": "Asesor Demo",
 "moneda_base": "ARS",
 "cuentas": [{"broker": "Broker Demo", "comitente": "000000", "estado": "activa"}]}
```

### `instrumentos.json`

Solo especies con vencimiento:

```json
{"BOND1": {"vencimiento": "2027-10-31"}}
```

### `niveles.json`

```json
{"AAA": {"take_profit": 1500.0, "stop_loss": 900.0},
 "BOND1": {"take_profit": null, "stop_loss": 150000.0}}
```

### `efectivo.json`

```json
{"fecha": "2026-11-04", "ARS": 1000.0, "USD": 10.0, "nota": ""}
```

`fecha`, `ARS` y `USD` pueden ser `null` hasta que el asesor los cargue. En ese caso se
muestra "sin dato", nunca cero.

### `dia_cero.json`

```json
{"esquema_version": 2,
 "fecha": "2026-11-04", "fijado_en": "2026-11-04T17:05:00-03:00",
 "cantidades": {"AAA": 100.0},
 "precios": {"AAA": 1200.0},
 "mep": 1500.0,
 "efectivo": {"fecha": "2026-11-04", "ARS": -1000.0, "USD": 10.0}}
```

`mep` es `null` si no se pudo obtener; no impide fijar el día cero. Dentro de `efectivo`,
`fecha`, `ARS` y `USD` pueden ser `null`. Si no se recibió efectivo, las tres claves se guardan
en `null`. Los saldos faltantes bloquean el patrimonio inicial, sin impedir los demás
indicadores. Al cargar el efectivo después, se agrega `efectivo_cargado_en` en la raíz, con
zona horaria.

### `movimientos.csv` y claves de los movimientos

Columnas: `fecha,tipo,ticker,cantidad,importe,nota`.

- `fecha`: `AAAA-MM-DD`, o `date` al pasarlo a `aplicar_movimientos`.
- `tipo`: `compra`, `venta`, `renta`, `dividendo`, `deposito`, `retiro`.
- `cantidad`: siempre positiva; vacía o 0 si no aplica.
- `importe`: siempre positivo, neto en pesos. El tipo define el sentido.

### `historial.csv`

Columnas: `consultado_en,ticker,ultimo,bid,ask`. Solo se agrega.
