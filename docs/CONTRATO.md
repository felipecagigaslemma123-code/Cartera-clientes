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

Los campos `*_dia_cero*` comparan precios para la cantidad recibida; no representan el
resultado integral con movimientos aprobado por Felipe. Ese cálculo requiere el
patrimonio inicial, las tenencias posteriores, el efectivo y los flujos externos,
y se especificará antes de implementarlo. La API de la etapa 1 se conserva.

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

**Pendiente antes de etapa 3:** completar las entradas del tablero para incluir
cantidades, unidades de cotización y referencias MEP/día cero. La firma actual no
contiene toda la información necesaria para las salidas de `PLAN.md`.

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

**Pendiente antes de etapa 5:** ampliar de forma compatible el resultado realizado
para conservar el origen real o estimado de los costos vendidos. Completar el
contrato de conciliación patrimonial y flujos, y revisar la metodología porcentual
y la conversión histórica a MEP con Claude. Las pruebas actuales de lotes por sí
solas no validan el resultado integral.

## Línea de comandos

```bash
python3 -m cartera --datos RUTA importar --cliente SLUG --archivo EXCEL
python3 -m cartera --datos RUTA actualizar-costos --cliente SLUG --archivo EXCEL
python3 -m cartera --datos RUTA estado --cliente SLUG
python3 -m cartera --datos RUTA capturar --cliente SLUG
python3 -m cartera --datos RUTA fijar-dia-cero --cliente SLUG [--fecha AAAA-MM-DD] [--forzar]
python3 -m cartera --datos RUTA dashboard --cliente SLUG
python3 -m cartera --datos RUTA alertas --cliente SLUG
python3 -m cartera --datos RUTA movimiento --cliente SLUG --fecha F --tipo T --ticker X --cantidad N --importe I [--nota N]
```

`--datos` se puede omitir si está definida `CARTERA_DATOS`. Errores de validación:
código de salida distinto de cero, un mensaje por problema y **sin escribir nada**.

### Persistencia y comandos de la etapa 1

`importar` valida el libro completo antes de escribir la base `cartera.json` descrita
en `FORMATOS.md`. Guarda versión de esquema, fecha de importación y huella del Excel,
además de posiciones y lotes. Rechaza una base ya existente sin sobrescribirla; no
admite `--forzar`. Los movimientos futuros no modifican esta base inicial.

`actualizar-costos` exige una base existente y valida el Excel completo con las
mismas reglas de `importar`, incluidas las fechas futuras. Si cambia el conjunto de
tickers, el nombre de alguna especie, su tipo, `cotiza_cada` o su cantidad total,
falla sin escribir nada. Las cantidades totales deben ser iguales a las de la base,
sin aplicar la tolerancia de cierre de lotes a esa comparación.

Puede cambiar los lotes, fechas, precios, costos, orígenes y notas. Antes del
reemplazo atómico de `cartera.json`, conserva la versión anterior completa en
`historial_cartera/`, con nombre de fecha, hora y sufijo único; nunca pisa una
versión previa. Si falla el respaldo o el reemplazo, la base anterior queda intacta.
Si el respaldo ya estaba publicado cuando falla el reemplazo, permanece completo;
su existencia no confirma que la actualización haya finalizado.
Se mantienen `esquema_version=1` y los campos adicionales de la raíz y de `origen`;
`importado_en` y `origen` se actualizan con la nueva importación.

Si los datos interpretados no cambian, informa que no hay cambios y no escribe archivos
ni modifica metadatos. El orden de posiciones y lotes no cuenta como cambio, ni
los cambios en celdas que el importador ignora. Una corrección efectiva muestra por
especie modificada el costo anterior/nuevo y ambos estados de origen.

Si un lote de extracto cambia de costo o de origen, se advierte sin bloquear. Al no
haber identificadores estables de lotes, la comprobación es conservadora: verifica
que se conserven sus combinaciones de cantidad, fecha y costo. También advierte
ante cambios simultáneos entre extractos y otros lotes que puedan ocultar una
reasignación de origen, incluso si se mantienen los costos totales. Esto puede
generar avisos ante ciertas ediciones de notas ambiguas. Reordenar filas o cambiar
únicamente una nota de extracto no dispara este aviso.

En ambos comandos, una fecha de compra posterior a hoy en Argentina es un error
que indica hoja, fila y ticker. La fecha de hoy se acepta.

`SLUG` comienza con letra o número y contiene solo letras ASCII, números, guiones
o guiones bajos. La ruta de datos queda fuera del proyecto; los enlaces de carpetas
de clientes no pueden desviar la lectura ni la escritura fuera de esa ruta.

`estado` lee la base importada y muestra cantidades, costos y su origen. En esta
etapa no consulta precios ni toma el costo como precio; indica "sin dato" para la
valuación y los resultados que todavía no pueden calcularse. El resto de los
comandos pertenece a las etapas siguientes.
