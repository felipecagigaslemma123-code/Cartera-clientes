# Proyección de títulos ajustables: CER, TAMAR y dólar linked

Versión 1.2 · 16/11/2026 · Especificación aprobada por Felipe para la etapa 11.
La 1.1 (Codex) documentó el tipo de cambio mensual del REM y la captura anticipada del CER. La 1.2 (revisión de
Claude) fija la base del A3500 de IAMC y suma las letras CER y dólar linked al flujo.

## Qué se busca

Sumar al flujo de fondos ([FLUJO_FONDOS.md](FLUJO_FONDOS.md)) los títulos cuyo pago depende de un índice:
CER, TAMAR, A3500 (dólar linked) y los duales. El pago se calcula con el **dato publicado por el BCRA**
mientras exista y, más adelante, con la **mediana del REM**. Cada importe dice qué parte es dato y qué
parte es estimación.

No hace falta actualizar todos los días: los datos del BCRA se renuevan una vez por semana y el REM una vez
por mes, cuando sale. Un pago cercano suele estar casi definido: el CER se publica con un mes de adelanto
y un dólar linked fija su tipo de cambio tres días hábiles antes.

## Hechos verificados (13/11/2026)

Con el cierre de IAMC del 05 al 12/11, la API del BCRA y el REM de octubre:

- **API del BCRA** (Estadísticas Monetarias v4, sin credenciales): CER (id 30), TAMAR privados TNA
  (id 44) y A3500 (id 5) coinciden con IAMC: CER 865,4229 el 05/11, TAMAR 23,5625 el 04/11 y A3500
  1.545,3974 el 05/11. `tools/bcra_extraer.py` funciona y sus pruebas pasan.
- **El CER se publica hasta el día 15 del mes siguiente.** Entre el 16 de un mes y el 15 del siguiente,
  crece a tasa diaria constante y acumula exactamente la inflación de dos meses antes. Del 16/10 al 15/11
  subió 1,9% (IPC de septiembre) y del 16/11 al 15/12, 2,2% (IPC de octubre).
- **Huecos en la API:** no hay A3500 ni TAMAR del 06, 09 y 10/11/2026, aunque fueron días hábiles. IAMC
  repitió el A3500 del 05/11 en esos cierres. El cálculo no puede suponer que todo día hábil tiene dato.
- **El REM no tiene API.** Es un Excel mensual:
  `https://www.bcra.gob.ar/archivos/Pdfs/PublicacionesEstadisticas/informes/relevamiento-expectativas-mercado-tablas-AAAA-MM.xlsx`,
  enlazado desde `https://www.bcra.gob.ar/relevamiento-expectativas-mercado-rem/`. Hoja `Cuadros de
  resultados`. Trae medianas mensuales de IPC (7 meses, desde el mes relevado), TAMAR TNA % (6 meses,
  desde el siguiente) y tipo de cambio $/USD (6 meses), más los valores a 12 y 24 meses y por año.
- **El REM se equivoca:** esperaba 1,8% de inflación para octubre y fue 2,2%. Por eso se muestra siempre
  el origen de cada dato.
- **Cómo arma IAMC cada familia** (`calculadora_bonos.ins`):
  - `dl`: `f` es el pago por 100 VN en unidades de `fxc`, que es el A3500 inicial del título. `f × fxc`
    es el pago en pesos al **último A3500 publicado**: TZV28 del 12/11, 110,967584 × 1.394,9234 / 100 =
    1.547,9128, el A3500 del 11/11.
  - `cer`: `f` es el pago al CER del día de IAMC, pero la fecha de ese CER **no se pudo deducir**: entre
    los cierres del 05 y del 12/11 el flujo de X29E7 y TZXS7 avanzó cinco días de CER en siete corridos.
    Por eso no se usa el flujo de IAMC como base del CER (ver más abajo).
  - `var` (TAMAR): `f[j][3]` es la base del cupón, y `renta = f[j][3] × v.vig` en todos los cupones
    (BAF27: 2,638887 = 8,333333 × 0,3166664). IAMC proyecta la tasa vigente constante.
  - `capv` con una pata TAMAR (TMF27): pago único `mv = c.patas[0].mv`, con TEM constante
    `c.patas[0].tem` en los `n − me` meses que faltan. La TEM sale de la TNA con
    `TEM = (1 + (TAMAR + m) × 32/365)^(365/384) − 1`.
  - Duales (TMVE8): dos patas en unidades de `fxc`. Pata TAMAR: `100 × Π(1 + TEM)` sobre `n` meses. Pata
    dólar: `100 × A3500 / fxc` (sin devaluación futura). Pago en pesos = `fxc × máx(patas)` por 100 VN.
  - `cap` son LECAP/BONCAP de tasa fija: ya las cubre el panel de letras. No son ajustables.

## Datos que se guardan

Todo en la carpeta de datos, compartida por los clientes (no contiene datos de ninguno):

```
<datos>/indices/bcra/<AAAA-MM-DD>.json     captura de tools/bcra_extraer.py, ahora en src
<datos>/indices/rem/<AAAA-MM>.xlsx          Excel original del REM, sin modificar
<datos>/feriados.json                       lo escribe Felipe: {"2026": ["2026-11-23", ...]}
<datos>/supuestos_manual.json               opcional, lo escribe Felipe
```

- El extractor del BCRA pasa a `src/cartera/indices.py` con las mismas validaciones. Comando `indices`:
  captura las tres series desde el 01/01 del año anterior. Para A3500 y TAMAR pide hasta hoy y para
  CER pide hasta el 15 del mes siguiente, conservando únicamente las observaciones devueltas por
  el BCRA. Baja el REM del último mes publicado si no está guardado. Se conservan todas las capturas
  y todos los REM.
- El comando `dashboard` intenta `indices` solo si la última captura del BCRA tiene más de 7 días o si
  pasó el día 10 del mes y falta el REM del mes anterior. Un intento por día. Una falla no frena el
  dashboard; se usa lo guardado y se avisa la fecha.
- El REM se busca primero por la URL con el mes; si no existe, en los enlaces de la página. No se inventan
  otras direcciones.
- `supuestos_manual.json` reemplaza al REM para los meses que indica, y figura con origen `manual`:

  ```json
  {"nota": "Escenario de Felipe", "inflacion": {"2027-01": "0.025"},
   "tamar": {"2027-03": "0.28"}, "a3500": {"2027-03": "1750"}}
  ```

  Inflación y TAMAR en tanto por uno; A3500 en $/USD. Nunca reemplaza un dato publicado.
- Días hábiles: lunes a viernes, menos `feriados.json`. Si falta el año, se calcula igual y se avisa
  "días hábiles sin feriados de AAAA".

## Curvas proyectadas

Todas devuelven `(valor, origen)`, con `origen` `publicado`, `proyectado` (REM) o `manual`.

### Inflación mensual (desde el REM)

1. Meses con mediana explícita: esa mediana.
2. Resto de los 12 meses siguientes al mes relevado: una tasa mensual constante tal que los 12 meses
   acumulen el dato "próx. 12 meses".
3. Meses 13 a 24: la tasa mensual equivalente al dato "próx. 24 meses", que es la inflación interanual
   de ese segundo año.
4. Después: la tasa de los meses 13 a 24.

### CER

- Hasta el último día publicado, el valor publicado. Un día sin dato anterior al último toma el anterior
  publicado.
- Después, para un día del período que va del 16 del mes `m + 1` al 15 del mes `m + 2`, el CER crece a
  la inflación del mes `m`, repartida en forma geométrica por día corrido:
  `CER(t) = CER(15 de m+1) × (1 + π_m)^(días desde el 15 / días del período)`.
- Si el último dato publicado no cae un día 15, el resto de ese período sigue con la tasa diaria de los
  dos últimos días publicados.

### A3500

- Hasta el último publicado: el publicado, o el anterior si el día no tiene dato.
- Después: interpolación geométrica entre el último publicado y cada mediana mensual del REM, ubicada el
  día 15 de su mes. El REM releva el promedio simple del A3500 en los días hábiles del mes, según las
  [consideraciones del BCRA](https://www.bcra.gob.ar/archivos/Pdfs/PublicacionesEstadisticas/informes/consideraciones-relevamiento-expectativas-mercado.pdf).
  El día 15 es el punto de interpolación elegido para representar ese promedio en la curva.
  Luego, el valor a 12 meses en el día 15 del mes relevado + 12. Más allá, el mismo ritmo
  geométrico del último tramo.
- Las medianas mensuales cuyo día 15 es anterior o igual al último publicado se ignoran.

### TAMAR

- Hasta el último publicado: el publicado, o el anterior si el día no tiene dato.
- Después: la mediana del REM del mes. Entre el último mes explícito y el valor a 12 meses (ubicado en el
  mes relevado + 12), interpolación lineal por mes. Más allá, constante.

## Pagos de cada familia

Los datos contractuales van en `instrumentos.json`, en el bloque `iamc`, con la fuente. Nada se deduce del
ticker.

**Letras CER y dólar linked.** Una posición de tipo `letra` (LECER, LELINK) con bloque `iamc.indice` sigue
este flujo, no el panel de letras: entra al calendario con su pago proyectado y su precio de compra se carga
con `precio-bono` (`bonos --cliente SLUG` la lista). Sin `iamc.indice` sigue como pendiente en el panel.

### CER

```json
"iamc": {"ticker": "CER_DEMO", "grupo": "tp",
         "indice": {"tipo": "CER", "valor_inicial": "500.0", "rezago_habiles": 10,
                    "fuente": "Condiciones ficticias para demostración"}}
```

- Flujo real por 100 VN: para títulos de un solo pago, 100 (o el que diga la fuente). Con cupones, se
  cargan como `pagos_reales` (fecha, amortización y renta reales por 100 VN), con el mismo formato que
  `pagos_manuales`.
- `pago = flujo_real × CER(fecha_pago − rezago_habiles días hábiles) / valor_inicial`.
- **Control contra IAMC:** IAMC expresa el flujo CER al CER de la liquidación del cierre menos el rezago
  contractual (verificado sin diferencia con X29E7 y X30N6 en cinco cierres). Por eso
  `f / flujo_real × valor_inicial` debe coincidir con ese CER publicado dentro de 1 pb. Si no, se avisa
  "revisar valor inicial del CER", con los dos valores y la fecha. No se corrige solo.

### Dólar linked

```json
"indice": {"tipo": "A3500", "rezago_habiles": 3, "fuente": "Resolución conjunta 13/2026, art. 5"}
```

- `pago en pesos = flujo_dolar × A3500(fecha_pago − rezago_habiles días hábiles)`, donde
  `flujo_dolar = f × fxc / A3500_IAMC`. `A3500_IAMC` es el A3500 publicado por el BCRA en la fecha que
  informa el bloque macro del cierre (`macro.vars`, `k = "a3500"`, campo `f`), que puede ser anterior a la
  fecha del cierre: el cierre del 12/11/2026 usó el del 11/11. Lo mismo vale para la pata dólar de los
  duales. Para
  un título de un solo pago queda `100 × A3500(ref)`.
- `valor_inicial` es opcional; si está y difiere de `fxc` en más de 0,0001, se avisa.
- Se cobra en pesos: el calendario lo suma en ARS.

### TAMAR con cupones (`var`)

```json
"indice": {"tipo": "TAMAR", "rezago_habiles": 10, "fuente": "..."}
```

- Amortización: la de IAMC.
- Primer cupón (el período ya empezó): `renta = f[j][3] × v.vig`, como IAMC. Se marca `publicado`.
- Cupones siguientes: `renta = f[j][3] × (promedio de TAMAR diaria + v.m)`, con el promedio de los días
  corridos del período del cupón corrido `rezago_habiles` días hábiles hacia atrás. Inicio del período:
  la fecha del pago anterior.
- Si `v.idx` no es `TAMAR` (por ejemplo, BADLAR), queda "proyección pendiente: índice sin fuente".

### Capitalizables TAMAR (`capv` con una pata TAMAR)

- `pago = mv × Π_k ((1 + TEM_k) / (1 + tem))^(e_k)` sobre los `n − me` meses que faltan, con `e_k = 1`
  salvo la última fracción. `TEM_k = tem_tamar(TAMAR del mes k, m)`; el mes k es el mes calendario de la
  liquidación del cierre + k − 1.
- Con TAMAR constante igual a la implícita, reproduce `mv` de IAMC.

### Duales TAMAR / dólar

- Pata TAMAR: como el capitalizable, en unidades de `fxc`.
- Pata dólar: `mv_dolar × A3500(ref) / A3500_IAMC`, con la referencia del dólar linked.
- `pago en pesos = fxc × máx(pata TAMAR, pata dólar)`, o `mín` si `c.regla` es `MIN`. Se muestra qué
  pata gana y por cuánto.

## Qué se muestra

- Cada pago dice **"definitivo"** si todos los índices que usa están publicados, o **"estimado"** con el
  origen: "REM octubre 2026" o "supuesto manual". Un pago estimado nunca parece seguro.
- El pago CER estimado indica hasta qué fecha se usa CER publicado. Si la fecha de referencia del
  bono está cubierta por la publicación, el pago usa el dato oficial aunque esa fecha sea futura.
- En los títulos con índice, la TIR de compra es nominal en pesos y figura como estimada. En los CER se
  agrega la TIR real (flujos reales contra el precio deflactado por el CER de la referencia contractual de la liquidación, con el mismo rezago que los pagos).
- **Estado de los índices:** fecha de la última captura del BCRA, último dato de cada serie, mes del REM
  y huecos detectados en días hábiles.
- **Estimación anterior:** cada vez que se genera el dashboard, si pasaron 7 días desde la anterior, se
  guarda `<datos>/clientes/<slug>/proyecciones/<AAAA-MM-DD>.json` con cada pago proyectado. Cuando un
  pago se cobra, se muestra la última estimación guardada antes del pago junto al cobro registrado.
- El calendario sigue sin sumar monedas. Los pagos dólar linked y duales van en ARS.

## Reglas que no se negocian

- Nada de lo estimado se presenta como dato. Si falta el REM o el índice, se dice qué falta; nunca cero.
- Un dato publicado nunca se reemplaza por una estimación ni por un supuesto manual.
- No se usa el flujo `cer` de IAMC como base de cálculo; solo como control.
- No se completan huecos de la API con interpolaciones presentadas como dato publicado.
