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

`fetch(url) -> list` hace el GET y lanza una excepción si falla. `ClientePrecios` trata
como falla cualquier respuesta que no sea una lista: la API puede responder HTTP 200 con
un objeto de error. `ahora` es una función
sin argumentos que devuelve un `datetime` con zona horaria; se inyecta en las pruebas.

`Cotizacion`: `ticker`, `ultimo`, `bid`, `ask`, `pct_dia`, `estado`, `consultado_en`.

`estado` es `"vivo"`, `"cache"` o `"sin_dato"`. Ver `PRECIOS.md`. `consultado_en` es el
momento de la consulta que obtuvo ese dato, no la hora del último operado.

```python
fijar_dia_cero(posiciones, cotizaciones, ruta, fecha, forzar=False, mep=None, efectivo=None) -> dict
cargar_efectivo_dia_cero(ruta, efectivo, forzar=False) -> dict
patrimonio_inicial(posiciones, dia_cero) -> PatrimonioInicial
advertencias_precio(lotes, posiciones, cotizaciones) -> list[str]
capturar_historial(cotizaciones, ruta_csv) -> int   # filas agregadas
```

`fijar_dia_cero` escribe el JSON de `FORMATOS.md` de forma atómica y devuelve su contenido.
`efectivo` es un `dict` con `fecha`, `ARS` y `USD`, o `None`. Lanza `ErrorDiaCero` si falta
el precio de alguna posición, si alguna cotización no está en estado `"vivo"`, si el
efectivo es inválido, o si el archivo ya existe y `forzar` es falso.

`cargar_efectivo_dia_cero` reemplaza solo `efectivo` y agrega `efectivo_cargado_en`, sin
tocar cantidades, precios, `mep`, `fecha` ni `fijado_en`. Lanza `ErrorDiaCero` si el archivo
no existe, si el efectivo es inválido, o si ya hay algún saldo cargado y `forzar` es falso.

Un efectivo es inválido si `ARS` o `USD` no son un número finito o `null`. Los negativos y
el cero son válidos; un booleano no. Antes de cargar, una clave ausente equivale a `null`.

`patrimonio_inicial` recibe el contenido de `dia_cero.json` y devuelve un
`PatrimonioInicial`:

- `valuacion_posiciones`: valuación con las cantidades y los precios **guardados** en el día
  cero. Las `posiciones` aportan solo `cotiza_cada`.
- `efectivo_ars`, `efectivo_usd`: los saldos guardados, o `None`.
- `total`: según `DOMINIO.md`, o `None` si hay faltantes.
- `faltantes`: `list[str]`, con `"efectivo ARS"`, `"efectivo USD"` o `"dólar MEP"`.

`advertencias_precio` devuelve un texto por lote que cumple la regla de `DOMINIO.md`, con
ticker y ambos precios. Ignora lotes sin precio y cotizaciones sin `ultimo`.

`capturar_historial` ignora las cotizaciones que no estén en estado `"vivo"`.

## `cartera.dashboard`

```python
generar_html(cliente, resultados, resumen, cotizaciones, niveles, instrumentos,
             efectivo, historial, generado_en, posiciones=None, dia_cero=None, mep=None) -> str
```

`cliente` es un `dict` con el contenido de `perfil.json`. `resultados` es una lista de
`ResultadoPosicion`. `historial` es un `dict[str, list[tuple[datetime, float]]]` por
ticker. Los textos se escapan. El HTML generado no carga scripts, estilos ni fuentes
externos.

`posiciones` es la lista de `Posicion`, `dia_cero` el contenido de `dia_cero.json` o `None`,
y `mep` una `Cotizacion` o `None`. El comando siempre los pasa. Sin `posiciones` el HTML se
genera igual, con los valores embebidos y sin recalcular en vivo.

El HTML incluye sus datos en `<script id="datos-cartera" type="application/json">`, con el
esquema de `docs/DASHBOARD.md`.

### Comando `dashboard`

`dashboard` exige una base importada. Consulta precios y dólar MEP una vez, actualiza la
caché, lee los demás archivos del cliente y escribe `dashboard.html` de forma atómica.
Muestra la ruta del archivo y cada especie sin precio vivo.

- No agrega filas a `historial.csv`: eso lo hace `capturar`.
- Termina con código 0 aunque la fuente esté caída, porque el archivo se genera igual y
  queda marcado.
- `perfil.json`, `niveles.json`, `instrumentos.json`, `efectivo.json`, `dia_cero.json` e
  `historial.csv` son opcionales. Si faltan, se muestra "sin dato" o "sin fijar". Sin
  perfil, se identifica al cliente por su `slug`.
- En `historial.csv` usa solo las últimas 500 filas de cada ticker y no muestra el ticker
  `MEP` como una posición.

## `cartera.alertas`

```python
en_horario_mercado(ahora) -> bool
evaluar_niveles(cotizaciones, niveles, estado, ahora) -> (list[Evento], dict)
evaluar_vencimientos(instrumentos, estado, hoy, umbrales=(30, 15, 7, 1)) -> (list[Evento], dict)
```

`Evento`: `tipo`, `ticker`, `precio`, `nivel`, `mensaje`. `tipo` es `"take_profit"`,
`"stop_loss"`, `"sin_chequeo"`, `"vencimiento"` o `"control"`. Ambas funciones reciben el estado
anterior como `dict`, no lo mutan y devuelven el nuevo. El estado debe ser serializable
a JSON. Reglas en `DOMINIO.md`.

## `cartera.notificar`

```python
Notificador(canales)       # canales: lista de funciones (titulo, mensaje) -> None
  .enviar(eventos, slug) -> list[str]   # errores de los canales; no lanza excepción
canal_macos(titulo, mensaje) -> None
canales_disponibles() -> list
```

`enviar` manda **un único mensaje por llamada** con todos los eventos, y un error por cada
canal que falló. Sin eventos, no envía nada. Si un canal falla, los demás se intentan igual.
Título y mensaje contienen el `slug` y nunca nombres ni importes de la cartera, solo ticker,
tipo de evento y precio. Los errores no incluyen el texto original de la excepción. El módulo
usa `subprocess.run` y `urlopen` importados de forma que las pruebas los puedan reemplazar:
`cartera.notificar.subprocess.run` y `cartera.notificar.urlopen`.

## `cartera.alertas_comando`

```python
correr_alertas(carpeta, punto, slug, fetch, canales, ahora) -> dict
```

Hace una corrida completa según `docs/ALERTAS.md`. `carpeta` es la del cliente y `punto` la base
cargada. Devuelve `eventos`, `errores`, `entregado` (`True` si no había eventos o si algún canal los
entregó) y `evaluo_niveles`.

`ahora_argentina()` devuelve la hora actual con zona horaria de Argentina.

El comando `alertas` llama a `cartera.notificar.canales_disponibles()` y a
`cartera.alertas_comando.ahora_argentina()` por su módulo, para poder reemplazarlos en las pruebas,
y usa `consultar_json` como `fetch`. Termina con código distinto de cero
si `entregado` es falso.

## `cartera.movimientos`

```python
aplicar_movimientos(lotes, movimientos) -> (list[Lote], list[Realizado])
```

`movimientos`: lista de `dict` con las claves de `FORMATOS.md`, en cualquier orden; se
aplican por fecha, de forma estable. `moneda`, `tc` y `tipo_activo` pueden faltar. Una compra
agrega un lote con `origen="extracto"`. Una venta consume lotes por FIFO, los más viejos
primero, y los lotes sin fecha se consideran los más viejos. Prorratea el costo del lote
parcial. Otros tipos no tocan los lotes. No modifica lo recibido.

`Realizado`: `ticker`, `fecha`, `cantidad`, `importe`, `costo`, `resultado`, `origen_costo`.
`importe` está en pesos. Si la venta consumió un lote pendiente, `costo` y `resultado` son
`None` y `origen_costo` es `"incompleto"`.

Lanza `ErrorMovimiento` (subclase de `ValueError`) si se vende más de lo que hay.

```python
leer_movimientos(ruta) -> list[dict]
validar_movimientos(punto, movimientos, fecha_dia_cero, hoy) -> None
agregar_movimiento(ruta, punto, movimiento, fecha_dia_cero, hoy) -> dict
cartera_actual(punto, movimientos) -> (PuntoPartida, list[Realizado])
saldos_efectivo(efectivo, movimientos, hasta=None) -> dict
flujos(movimientos) -> Flujos
conciliar_efectivo(dia_cero, movimientos, efectivo) -> Conciliacion
resultado_integral(posiciones_base, dia_cero, posiciones_actuales, movimientos, precios, mep) -> ResultadoIntegral
```

- `leer_movimientos`: `[]` si no existe el archivo. Devuelve `fecha` como `date`, `cantidad` e
  `importe` como `float`, `moneda` normalizada, `tc` como `float` o `None`, y `ticker`,
  `tipo_activo` y `nota` como texto. Un formato inválido lanza `ErrorMovimiento` con la fila.
- `validar_movimientos`: aplica las reglas de `DOMINIO.md` y el historial completo, y lanza
  `ErrorMovimiento`, con todos los problemas. Con `fecha_dia_cero=None` no compara contra el día cero.
- `agregar_movimiento`: valida el historial con el movimiento nuevo y recién entonces agrega la fila,
  bajo un bloqueo. Si falla, no escribe nada. Devuelve el movimiento normalizado.
- `cartera_actual`: devuelve un `PuntoPartida` con posiciones y lotes actuales, sin modificar `punto`.
- `saldos_efectivo`: `efectivo` es un `dict` con `ARS` y `USD`. Devuelve `{"ARS": ..., "USD": ...}`, con
  `None` donde el saldo inicial es `None`. `hasta` limita a los movimientos de esa fecha o anteriores.
- `Flujos`: `aportes`, `retiros`, `rentas`, `amortizaciones`, `dividendos`, `gastos`, en pesos.
  `amortizaciones` se agrega en la etapa 9 y entra al resultado integral igual que `rentas`.
- `Conciliacion`: `estado` (`"concilia"`, `"no_concilia"`, `"sin_control"`), `fecha`, `diferencias`
  (`dict` por moneda, solo con las comparadas).
- `ResultadoIntegral`: `patrimonio_inicial`, `valuacion_final`, `efectivo_ars`, `efectivo_usd`,
  `patrimonio_final`, `flujos`, `total`, `faltantes` (`list[str]`). Lo que no se conoce es `None`.
- `precios`: `dict` de ticker a número o `None`. `mep`: número o `None`. `dia_cero`: el `dict` guardado
  o `None`.

### Integración con los demás comandos

| Usa | Comandos |
|---|---|
| Cartera actual | `estado`, `capturar`, `dashboard`, `alertas` |
| Base importada | `importar`, `actualizar-costos`, `fijar-dia-cero`, `patrimonio_inicial` |

- `fijar-dia-cero` se rechaza, incluso con `--forzar`, si algún movimiento tiene fecha igual o anterior
  a la nueva, o si el archivo es inválido.
- `generar_html` suma los parámetros opcionales `posiciones_base`, `integral`, `realizados` y
  `conciliacion`. Sin `integral`, conserva el recuadro actual. `crear_dashboard` siempre pasa `integral`.
- `crear_dashboard`, `capturar` y `estado` terminan con error si `movimientos.csv` es inválido, sin
  escribir salidas. `correr_alertas` nunca se frena por eso: ver `ALERTAS.md`.
- `correr_alertas` conserva su firma: recibe la base y aplica los movimientos adentro.
- `datos-cartera` suma `integral`, `realizados` y `conciliacion`. `integral` tiene `total`,
  `patrimonio_inicial`, `patrimonio_final`, `valuacion_final`, `efectivo` (`ARS`, `USD`), `aportes`,
  `retiros`, `rentas`, `dividendos`, `gastos`, `faltantes` y `faltantes_fijos`: los que no dependen del
  precio ni del MEP actuales, para que el navegador recalcule el resto. `realizados` lista los campos de
  `Realizado`, con la fecha en ISO, y `conciliacion` los de `Conciliacion`.
- El comando `movimiento` recibe los números y la fecha como texto y los valida: un dato mal escrito,
  como `1.234,56`, termina con un mensaje y código 1, sin escribir nada. Al guardar, confirma el
  movimiento e informa la tenencia de la especie, si corresponde.
- `estado` muestra las posiciones actuales, el patrimonio inicial, el efectivo calculado por moneda, los
  flujos y el realizado.

## `cartera.flujo_fondos`

Etapa 9. Reglas en `docs/FLUJO_FONDOS.md`.

```python
Pago(fecha: date, amortizacion: Decimal, renta: Decimal, origen: str)
Cronograma(ticker, grupo, familia, moneda, plaza, habilitado, fecha_cierre, liquidacion, pagos)
CronogramaCompra(pagos, completo, faltante_desde, faltante_hasta, advertencias)

cronograma_iamc(cierre, ticker, grupo) -> Cronograma | None
cronograma_compra(cierres, ticker, grupo, liquidacion, pagos_manuales=None) -> CronogramaCompra
tir_compra(precio, liquidacion, pagos) -> Decimal | None
```

- `cierre`: el `dict` del JSON diario de IAMC. `cierres`: lista de esos `dict`, en cualquier orden.
- `cronograma_iamc`: busca `ticker` y `grupo` en `calculadora_bonos.ins`. `None` si no está. `familia` es
  `k`, `moneda` es `cur`, `plaza` es `fxr`; `habilitado` es verdadero solo para `k == "fix"`. `pagos`
  sale de `f`, en orden de fecha, por 100 VN originales, con `origen = "iamc <fecha_cierre>"`; si no está
  habilitado, `pagos` es `[]`. `fecha_cierre` y `liquidacion` son `date`.
- `cronograma_compra`: pagos con fecha posterior a `liquidacion`, según la regla única del documento.
  `pagos_manuales`: lista de `(fecha, amortizacion, renta)` o `None`; sus pagos tienen
  `origen = "manual"`. `completo` es falso si quedan pagos sin cubrir; en ese caso `faltante_desde` y
  `faltante_hasta` acotan el hueco. `advertencias`: `list[str]`.
- `tir_compra`: tanto por uno, ACT/365, con los pagos de fecha posterior a `liquidacion`. `precio` sucio
  por 100 VN en la moneda de los flujos. `None` si no hay pagos o no hay solución en `(-0,99; 10)`.
- Los importes son `Decimal`, convertidos desde el texto del número (`Decimal(str(x))`), para que 0.42
  sea exactamente `Decimal("0.42")`. Ninguna función modifica lo recibido.
- Etapa 13, en `datos-cartera.flujo_fondos`: cada compra suma `intereses_corridos`, `ganancia_precio`,
  `intereses` y, si el inicio del cupón se supuso, `intereses_corridos_estimados`; sin separación,
  `motivo_capital`. Cada pago de la compra suma `capital` y `ganancia`. Cada posición suma
  `capital_pendiente` y `ganancia_pendiente` (o `None`). Importes como texto, igual que los demás.

## `cartera.indices`

Etapa 11. Reglas en `docs/PROYECCIONES.md`.

```python
Rem(mes, ipc, ipc_12m, ipc_24m, tamar, tamar_12m, tc, tc_12m)
Valor(valor: Decimal, origen: str)        # "publicado", "proyectado" o "manual"

leer_rem(ruta) -> Rem
serie_bcra(captura, clave) -> dict[date, Decimal]
inflacion_mensual(rem, hasta) -> dict[date, Decimal]
indice_cer(publicado, inflacion, fecha) -> Valor
indice_a3500(publicado, rem, fecha) -> Valor
tamar_diaria(publicado, rem, fecha) -> Valor
tem_tamar(tna, margen) -> Decimal
proyectar_capitalizable(mv, tem, n, me, tems) -> Decimal
```

- `Rem.mes`: primer día del mes relevado. `ipc`, `tamar` y `tc`: `dict` de primer día de mes a valor, solo
  los meses con mediana explícita. IPC y TAMAR en tanto por uno (1,7 % es `Decimal("0.017")`); `tc` en $/USD.
  Los `*_12m` y `ipc_24m` son las medianas de "próx. 12 meses" y "próx. 24 meses", en la misma unidad.
  Números del Excel convertidos con `Decimal(str(x))` y recién después divididos por 100.
- `serie_bcra`: `captura` es el `dict` que guarda el comando `indices` (mismo formato que
  `tools/bcra_extraer.py`). `clave`: `cer`, `a3500` o `tamar_tna`; TAMAR se devuelve en tanto por uno.
- `inflacion_mensual`: desde el mes relevado hasta `hasta` (primer día de mes), inclusive.
- `indice_cer`, `indice_a3500`, `tamar_diaria`: valor de la curva de `PROYECCIONES.md` para `fecha`. Un día
  sin dato anterior al último publicado devuelve el publicado anterior, con origen `publicado`.
- `tem_tamar`: `(1 + (tna + margen) × 32/365)^(365/384) − 1`.
- `proyectar_capitalizable`: `mv × Π ((1 + tems[k]) / (1 + tem))^(e_k)` sobre `n − me` meses; `tems` tiene
  al menos `ceil(n − me)` valores.
- Cálculos con `Decimal` y precisión de 50 dígitos. Ninguna función modifica lo recibido.

## `cartera.historial`

```python
leer_extracto(ruta) -> list[dict]
consolidar(filas) -> (list[dict], list[str])
clasificar(fila, cierres) -> str
leer_ajustes(ruta) -> list[dict]
leer_mep(ruta) -> dict[date, float]
construir_historial(filas, ajustes=(), cierres=(), mep=None) -> Historial
conciliar_tenencias(lotes, posiciones) -> dict
correr_historial(carpeta, punto, fetch=None, actualizar_mep=False) -> Historial
```

Lanzan `ErrorHistorial` (subclase de `ValueError`) ante un archivo inválido.

- `leer_extracto`: cada fila tiene `moneda` (`ARS`, `USD`), `cuenta` (`PESOS`, `DOLARES`, `CABLE`), `operado`
  (`date`), `comprobante`, `numero`, `cantidad`, `especie` (texto, vacío si no hay), `importe`, `saldo`,
  `referencia`, `archivo` y `fila`.
- `consolidar`: quita duplicados y devuelve también los avisos de saldo.
- `conciliar_tenencias`: `{ticker: {"derivada": n, "base": n, "diferencia": n}}`, solo con las diferencias que
  superan la tolerancia.

Etapa 10:

```python
leer_extracto_iol(ruta) -> list[dict]                       # cartera.historial; mismas claves que leer_extracto
derivar_base(datos, slug, reemplazar=False) -> (PuntoPartida, dict)   # cartera.almacenamiento
```

`derivar_base` devuelve lo mismo que `importar_cartera` y lanza `ErrorCartera` o `ErrorHistorial`, sin escribir nada.
`clasificar` devuelve `amortizacion` para `IOL AMORTIZACION`; `construir_historial` la resuelve como cierre o renta.

`Historial`:

- `realizados`: lista de `RealizadoHistorico`: `ticker`, `fecha`, `cantidad`, `cantidad_sin_lote`, `importe_ars`,
  `costo_ars`, `resultado_ars`, `origen_costo`, `clase` (`venta`, `cierre`).
- `ingresos`: `dict` de clase (`dividendo`, `retencion`, `renta`, `caucion_colocada`, `caucion_tomada`, `fci`,
  `gastos`, `compensacion`) a `{"ARS": n, "USD": n, "equivalente_ars": n}`. Las clases sin datos valen cero.
- `aportes`, `retiros`: el mismo formato.
- `lotes`: lotes abiertos, como `Lote`, con costo en pesos o `None`.
- `total_conocido`, `realizado_extracto`, `realizado_estimado`: números.
- `ventas_sin_dato`, `valores_sin_dato`: enteros.
- `sin_clasificar`: filas completas. `avisos`: textos.

`datos-cartera` suma `historial`: `total_conocido`, `ingresos`, `aportes`, `retiros`, `realizados`,
`ventas_sin_dato`, `valores_sin_dato`, `cantidad_sin_clasificar` y `avisos`.

## `cartera.informe`

Etapa 12. Reglas en [INFORME.md](INFORME.md).

```python
class ErrorInforme(ValueError): ...

leer_datos_dashboard(ruta) -> dict
armar_informe(datos, instrumentos=None, perfil=None, cantidad_cobros=7) -> dict
informe_html(modelo) -> str
exportar_pdf(ruta_html, ruta_pdf, navegador=None) -> Path
```

- `leer_datos_dashboard` devuelve el JSON del bloque `datos-cartera`. Si falta el archivo, el bloque o el
  JSON es inválido, lanza `ErrorInforme`.
- `armar_informe` es pura: no lee archivos ni consulta la red. Los importes, pesos y tasas son `Decimal`
  (convertidos con `Decimal(str(x))`); un dato faltante es `None`. Devuelve:

  | Clave | Contenido |
  |---|---|
  | `cliente`, `asesor` | textos; `asesor` puede ser `None` |
  | `fecha` | `date` de `generado_en` |
  | `mep` | dólar MEP del dashboard |
  | `patrimonio` | `integral.patrimonio_final` o `None` |
  | `invertido` | suma de valuaciones |
  | `efectivo` | `{"ARS": ..., "USD": ...}` o `None` |
  | `composicion` | lista de `{"clase", "valuacion", "peso", "tickers"}`, por valuación descendente |
  | `peso_dolares` | peso de las clases que cobran en dólares |
  | `tenencia` | lista de `{"ticker", "descripcion", "clase", "cantidad", "precio", "valuacion", "peso", "vs_compra", "vencimiento"}` |
  | `rendimientos` | lista de `{"ticker", "moneda", "tir", "tir_min", "tir_max", "estimada", "compras", "proximo_pago", "total_a_cobrar", "capital", "ganancia"}`; `proximo_pago` es `{"fecha", "importe"}` |
  | `a_cobrar` | `{moneda: total}` solo con las monedas presentes (`ARS`, `USD MEP`, `USD cable`) |
  | `a_cobrar_capital` | `{moneda: lo que devuelve lo invertido}` con las mismas monedas; `None` si a algún título de esa moneda le falta la separación |
  | `proximos_cobros` | lista de `{"fecha", "ticker", "concepto", "moneda", "importe", "capital", "estimado"}` |
  | `cobros_por_anio_capital` | `{"AAAA": {moneda: capital}}` de los pagos futuros; `None` en una moneda si a algún pago de ese año le falta la separación |
  | `cobros_por_anio` | `{"AAAA": {moneda: total}}` con todas las monedas del calendario |
  | `resultados` | `None` sin `historial`; si no, `{"ganancia_realizada", "ventas", "rentas_ars", "rentas_usd", "rentas_equivalente", "otros", "aportes", "retiros", "tenencia", "desde_dia_cero", "incompletos", "faltantes", "acumulado", "operaciones"}`. `tenencia` es la suma de `posiciones[].resultado` (`None` si alguna falta); `desde_dia_cero`, el resultado de los movimientos posteriores al día cero; `incompletos`, la cantidad de operaciones del historial sin resultado; `faltantes`, la lista de textos que explican por qué `acumulado` es `None`; `operaciones` = lista de `{"ticker", "fecha", "resultado"}` por fecha |

  Fechas como `date`. Pesos y tasas en tanto por uno.
- `informe_html` arma el documento completo de [INFORME.md](INFORME.md).
- `exportar_pdf` usa Chrome *headless*. Si `navegador` es `None`, busca la ruta estándar de macOS. Si no lo
  encuentra o Chrome falla, lanza `ErrorInforme` y no deja un PDF a medias.
- Para las pruebas, el módulo expone `_NAVEGADOR` (ruta por defecto de Chrome, que usan `exportar_pdf` y el
  comando) y `_hoy()` (fecha de Argentina, que usa el comando para la antigüedad del dashboard).

## Línea de comandos

```bash
python3 -m cartera --datos RUTA importar --cliente SLUG --archivo EXCEL
python3 -m cartera --datos RUTA actualizar-costos --cliente SLUG --archivo EXCEL
python3 -m cartera --datos RUTA estado --cliente SLUG
python3 -m cartera --datos RUTA capturar --cliente SLUG
python3 -m cartera --datos RUTA fijar-dia-cero --cliente SLUG [--fecha AAAA-MM-DD] [--forzar]
python3 -m cartera --datos RUTA efectivo-dia-cero --cliente SLUG --ars N --usd N [--fecha AAAA-MM-DD] [--forzar]
python3 -m cartera --datos RUTA dashboard --cliente SLUG
python3 -m cartera --datos RUTA alertas --cliente SLUG
python3 -m cartera --datos RUTA historial --cliente SLUG [--actualizar-mep]
python3 -m cartera --datos RUTA derivar-base --cliente SLUG [--reemplazar]
python3 -m cartera --datos RUTA movimiento --cliente SLUG --fecha AAAA-MM-DD --tipo TIPO --importe N [--ticker T] [--cantidad N] [--moneda ARS|USD] [--tc N] [--tipo-activo TIPO] [--nota TEXTO]
python3 -m cartera --datos RUTA movimiento --cliente SLUG --fecha F --tipo T --ticker X --cantidad N --importe I [--nota N]
python3 -m cartera --datos RUTA informe --cliente SLUG [--salida CARPETA] [--pdf]
```

`--datos` se puede omitir si está definida `CARTERA_DATOS`. Errores de validación:
código de salida distinto de cero, un mensaje por problema y **sin escribir nada**.

### Comandos de la etapa 2

Los tres exigen una base importada. Las consultas reales usan `urllib` con un tiempo de
espera y un `User-Agent` genérico, sin datos del cliente ni del usuario.

`capturar` consulta precios y dólar MEP, y agrega a `historial.csv` las cotizaciones vivas.
El dólar MEP se guarda con el ticker `MEP`. Muestra cuántas filas agregó, lista cada especie
que no está en estado `"vivo"` y las advertencias de `advertencias_precio`. Si ninguna
cotización está viva, termina con código de salida distinto de cero.

`fijar-dia-cero` consulta precios y dólar MEP, lee `efectivo.json` si existe y escribe
`dia_cero.json`. `--fecha` tiene por defecto el día de hoy en Argentina y no puede ser futura.
Tampoco se acepta un `efectivo.json` con fecha futura. Con `--forzar`, la versión anterior queda
en `historial_dia_cero/` y, si `efectivo.json` no trae saldos, se conserva el efectivo ya cargado.
Al terminar muestra la valuación, el patrimonio inicial o qué le falta, y las advertencias
de precios. Si `mep` queda en `null`, lo informa.

`efectivo-dia-cero` carga los saldos en un día cero ya fijado, sin consultar precios. Acepta
negativos (`--ars=-44656.61`) y `--fecha` tiene por defecto la del día cero y no puede ser futura.
Con `--forzar`, la versión anterior queda en `historial_dia_cero/`.

Si hay saldos y su fecha falta o difiere de la del día cero, estos comandos y `estado` muestran una
`ADVERTENCIA`, sin bloquear.

`estado` sigue sin consultar la red. Si existe un día cero, también muestra su fecha y el
patrimonio inicial, o qué le falta.

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
