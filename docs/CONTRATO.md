# Contrato de la API

Las pruebas dependen de estos nombres. Paquete en `src/cartera/`.

`Posicion` y `Lote` (en `cartera.punto_partida`), `Cotizacion` (en `cartera.precios`) y
`Evento` (en `cartera.alertas`) tienen que poder crearse con todos sus atributos como
argumentos con nombre; usá `dataclass`.

## `cartera.punto_partida`

```python
class ErrorPuntoPartida(Exception):
    errores: list[str]   # TODOS los problemas encontrados, no solo el primero

cargar_punto_partida(ruta) -> PuntoPartida
```

`PuntoPartida`: `posiciones: list[Posicion]`, `lotes: list[Lote]`.

`Posicion`: `ticker`, `especie`, `tipo`, `cantidad`, `cotiza_cada`.

`Lote`: `ticker`, `cantidad`, `origen`, `fecha` (`date` o `None`), `precio` y `costo`
(`float` o `None`), `nota`.

`origen` es `"extracto"`, `"estimado"` o `"pendiente"`. Ver `FORMATOS.md`.

## `cartera.calculos`

```python
valuacion(cantidad, precio, cotiza_cada) -> float
estado_costo(lotes) -> str
costo_total(lotes) -> Optional[float]
resultado_posicion(posicion, lotes, precio, precio_dia_cero=None) -> ResultadoPosicion
resumen_cartera(resultados) -> ResumenCartera
```

`estado_costo` recibe los lotes de una especie:

| Devuelve | Cuándo |
|---|---|
| `"extracto"` | todos los lotes son de extracto |
| `"estimado"` | todos son estimados |
| `"mixto"` | hay de extracto y estimados, ninguno pendiente |
| `"incompleto"` | hay al menos un lote pendiente |

`costo_total` devuelve `None` si el estado es `"incompleto"`.

`ResultadoPosicion`: `ticker`, `tipo`, `valuacion`, `costo`, `estado_costo`, `resultado`,
`resultado_pct`, `resultado_dia_cero`, `resultado_dia_cero_pct`. Si falta el costo,
`costo`, `resultado` y `resultado_pct` son `None`. Si `precio` es `None`, `valuacion` y
todos los resultados son `None`. Sin `precio_dia_cero`, los dos campos `*_dia_cero*` son
`None`. Los porcentajes son fracciones: `0.10` es 10%.

`ResumenCartera`:

- `valuacion_total`: suma de las valuaciones conocidas.
- `costo_comparable`, `valuacion_comparable`, `resultado_comparable`: solo posiciones
  con costo completo y precio.
- `posiciones_sin_costo`, `posiciones_sin_precio`: `list[str]` de tickers.

## `cartera.precios`

```python
ENDPOINTS = {"cedear": "arg_cedears", "accion": "arg_stocks", "bono": "arg_bonds",
             "letra": "arg_notes", "on": "arg_corp"}

ClientePrecios(fetch, ruta_cache, ahora=None)
  .obtener(posiciones) -> dict[str, Cotizacion]
  .dolar_mep() -> Optional[Cotizacion]
```

`fetch(url) -> list` hace el GET y lanza una excepción si falla. `ahora` es una función
sin argumentos que devuelve un `datetime` con zona horaria; se inyecta en las pruebas.

`Cotizacion`: `ticker`, `ultimo`, `bid`, `ask`, `pct_dia`, `estado`, `consultado_en`.

`estado` es `"vivo"`, `"cache"` o `"sin_dato"`. Ver `PRECIOS.md`. `consultado_en` es el
momento de la consulta que obtuvo ese dato, no la hora del último operado.

```python
fijar_dia_cero(posiciones, cotizaciones, ruta, fecha, forzar=False, mep=None) -> dict
capturar_historial(cotizaciones, ruta_csv) -> int   # filas agregadas
```

`fijar_dia_cero` escribe el JSON de `FORMATOS.md` y devuelve su contenido. Lanza
`ErrorDiaCero` si falta el precio de alguna posición, si alguna cotización no está en
estado `"vivo"`, o si el archivo ya existe y `forzar` es falso. `capturar_historial`
ignora las cotizaciones que no estén en estado `"vivo"`.

## `cartera.dashboard`

```python
generar_html(cliente, resultados, resumen, cotizaciones, niveles, instrumentos,
             efectivo, historial, generado_en) -> str
```

`cliente` es un `dict` con el contenido de `perfil.json`. `resultados` es una lista de
`ResultadoPosicion`. `historial` es un `dict[str, list[tuple[datetime, float]]]` por
ticker. Los textos se escapan. El HTML generado no carga scripts, estilos ni fuentes
externos.

## `cartera.alertas`

```python
en_horario_mercado(ahora) -> bool
evaluar_niveles(cotizaciones, niveles, estado, ahora) -> (list[Evento], dict)
evaluar_vencimientos(instrumentos, estado, hoy, umbrales=(30, 15, 7, 1)) -> (list[Evento], dict)
```

`Evento`: `tipo`, `ticker`, `precio`, `nivel`, `mensaje`. `tipo` es `"take_profit"`,
`"stop_loss"`, `"sin_chequeo"` o `"vencimiento"`. Ambas funciones reciben el estado
anterior como `dict`, no lo mutan y devuelven el nuevo. El estado debe ser serializable
a JSON. Reglas en `DOMINIO.md`.

## `cartera.notificar`

```python
Notificador(canales)       # canales: lista de funciones (titulo, mensaje) -> None
  .enviar(eventos, slug) -> list[str]   # errores de los canales; no lanza excepción
```

Si un canal falla, los demás se intentan igual. Título y mensaje contienen el `slug` y
nunca nombres ni importes de la cartera, solo ticker, tipo de evento y precio.

## `cartera.movimientos`

```python
aplicar_movimientos(lotes, movimientos) -> (list[Lote], list[Realizado])
```

`movimientos`: lista de `dict` con las claves de `FORMATOS.md`, en cualquier orden; se
aplican por fecha. Una compra agrega un lote con `origen="extracto"`. Una venta consume
lotes por FIFO, los más viejos primero, y los lotes sin fecha se consideran los más
viejos. Prorratea el costo del lote parcial. Otros tipos no tocan los lotes.

`Realizado`: `ticker`, `fecha`, `cantidad`, `importe`, `costo`, `resultado`. Si la venta
consumió un lote pendiente, `costo` y `resultado` son `None`.

Lanza `ErrorMovimiento` si se vende más de lo que hay.

## Línea de comandos

```bash
python3 -m cartera --datos RUTA importar --cliente SLUG --archivo EXCEL
python3 -m cartera --datos RUTA estado --cliente SLUG
python3 -m cartera --datos RUTA capturar --cliente SLUG
python3 -m cartera --datos RUTA fijar-dia-cero --cliente SLUG [--fecha AAAA-MM-DD] [--forzar]
python3 -m cartera --datos RUTA dashboard --cliente SLUG
python3 -m cartera --datos RUTA alertas --cliente SLUG
python3 -m cartera --datos RUTA movimiento --cliente SLUG --fecha F --tipo T --ticker X --cantidad N --importe I [--nota N]
```

`--datos` se puede omitir si está definida `CARTERA_DATOS`. Errores de validación:
código de salida distinto de cero, un mensaje por problema y **sin escribir nada**.
