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

Una fecha cargada sin precio no es un error: el lote sigue pendiente.

## Carpeta de datos

```text
$CARTERA_DATOS/clientes/<slug>/
  perfil.json          lo escribe el asesor
  instrumentos.json    lo escribe el asesor
  niveles.json         lo escribe el asesor
  efectivo.json        lo escribe el asesor
  cartera.json         generado por importar
  dia_cero.json        generado por fijar-dia-cero
  movimientos.csv      generado por movimiento
  historial.csv        generado por capturar
  cache_precios.json   generado
  estado_alertas.json  generado
  alertas.log          generado
  dashboard.html       generado
```

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
{"fecha": "2026-11-04", "fijado_en": "2026-11-04T17:05:00-03:00",
 "precios": {"AAA": 1200.0}, "mep": 1500.0}
```

`mep` es `null` si no se pudo obtener; no impide fijar el día cero.

### `movimientos.csv` y claves de los movimientos

Columnas: `fecha,tipo,ticker,cantidad,importe,nota`.

- `fecha`: `AAAA-MM-DD`, o `date` al pasarlo a `aplicar_movimientos`.
- `tipo`: `compra`, `venta`, `renta`, `dividendo`, `deposito`, `retiro`.
- `cantidad`: siempre positiva; vacía o 0 si no aplica.
- `importe`: siempre positivo, neto en pesos. El tipo define el sentido.

### `historial.csv`

Columnas: `consultado_en,ticker,ultimo,bid,ask`. Solo se agrega.
