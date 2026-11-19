# Propuesta: tres funcionalidades para Boston

Documento para el área de sistemas. Resume qué hace hoy la herramienta, qué podría aportar a la empresa y qué
haría falta para usarla con todos los clientes. El detalle técnico está en el [mapa del proyecto](MAPA.md); la
revisión de seguridad, en [SEGURIDAD.md](SEGURIDAD.md); y los datos que se le piden a BYMA, en
[PEDIDO_APIS_BYMA.md](PEDIDO_APIS_BYMA.md).

## Punto de partida

La herramienta se desarrolló desde cero, en Python, para seguir la cartera de los clientes que atiende Felipe.
Hoy funciona en una Mac con tres carteras reales y se entregó en 14 etapas, cada una con su especificación,
sus pruebas (1079 en total) y su revisión. No depende de ningún sistema de la empresa: lee los extractos de los
brokers y consulta fuentes públicas.

Son tres funcionalidades que se pueden evaluar por separado:

| | Funcionalidad | Pregunta que responde | Estado |
|---|---|---|---|
| 1 | Calculadoras de renta fija y flujo de fondos | ¿Qué me va a pagar cada título, y a qué tasa lo compré? | Funcionando |
| 2 | Análisis de riesgo | ¿Cuánto riesgo corre la cartera y de dónde viene? | Funcionando, con criterios a confirmar |
| 3 | Ganancia, tenencia e informe al cliente | ¿Cuánto gané, qué tengo y cómo se lo explico al cliente? | Funcionando |

## 1. Calculadoras de renta fija y flujo de fondos

**Qué hace.** Para cada bono, obligación negociable y letra de la cartera arma el cronograma de pagos que
falta cobrar, por cada nominal comprado, separando el capital que vuelve de la ganancia. Calcula la TIR de
compra con el precio realmente pagado.

- **Letras capitalizables** (LECAP, BONCAP): valor al vencimiento y rendimiento con la convención de IAMC.
- **Títulos ajustables:** proyecta los pagos por CER, TAMAR o dólar con las series que publica el BCRA en su
  API y con las expectativas del REM.
- **Bonos y ON:** cronogramas y condiciones del cierre diario de IAMC/BYMA.

**Para qué le sirve a la empresa.** Le muestra al cliente, título por título, qué va a cobrar y cuándo. Ayuda
a comparar opciones de renta fija con la misma vara, incluso entre títulos ajustables.

**Dónde está en el código:** `flujo_fondos.py`, `letras.py`, `_motor_letras/`, `pagos_indexados.py`,
`indices.py`. Especificaciones: [FLUJO_FONDOS.md](FLUJO_FONDOS.md), [LETRAS.md](LETRAS.md),
[PROYECCIONES.md](PROYECCIONES.md), [FUENTE_BCRA.md](FUENTE_BCRA.md), [FUENTE_IAMC.md](FUENTE_IAMC.md).

## 2. Análisis de riesgo

**Qué hace.** Mide el riesgo de cada activo y de la cartera completa con la metodología de la bibliografía de
administración de carteras, comprobada contra sus ejemplos numéricos en `tools/riesgo/`.

- **Renta variable:** volatilidad histórica y EWMA, VaR y pérdida esperada (ES), beta contra el S&P 500 y
  aporte de cada activo al riesgo total. Muestra, por ejemplo, que en una cartera un activo con el 10 % del
  peso explica la mitad del riesgo.
- **Renta fija:** duration modificada y convexidad, con escenarios de suba y baja de tasas de 100 y 200 puntos
  básicos por familia de títulos.
- **Concentración:** por activo, por moneda y por familia.

**Para qué le sirve a la empresa.** Detecta concentraciones que no se ven mirando solo los pesos, y permite
explicarle al cliente cuánto puede perder en un mal día con un criterio común para todas las carteras.

**Qué falta.** Confirmar los criterios (dólar CCL o MEP, tasa libre de riesgo) y, sobre todo, mejores datos
históricos: la fuente actual tiene un solo año y le faltan muchos activos. Es la razón principal del
[pedido de APIs a BYMA](PEDIDO_APIS_BYMA.md).

**Dónde está en el código:** `riesgo.py`, `_riesgo_calculos.py`. Especificación: [RIESGO.md](RIESGO.md) y
[RIESGO_METODOLOGIA.md](RIESGO_METODOLOGIA.md).

## 3. Ganancia, tenencia e informe al cliente

**Qué hace.** Reconstruye desde los extractos de los brokers (hoy Bull Market e InvertirOnline) todo lo que
compró, vendió y cobró el cliente, y calcula la ganancia realizada por FIFO: ventas, rentas, dividendos,
cauciones y amortizaciones (que cuentan como capital devuelto, no como ganancia). Suma la tenencia actual
valuada con precios en vivo.

Con eso genera:

- un **dashboard** para el asesor, que se actualiza solo y avisa cuando un precio toca un nivel;
- un **informe PDF para el cliente**, en lenguaje llano y en tres partes: lo que tiene hoy, lo que ya ganó y
  lo que va a cobrar desde hoy. Se ordenó así porque los clientes confundían cobros futuros con ganancias;
- **descargas en Excel**.

**Para qué le sirve a la empresa.** Un informe claro y uniforme para todos los clientes, hecho con los mismos
números que ve el asesor, sin armarlo a mano.

**Dónde está en el código:** `historial.py`, `movimientos.py`, `precios.py`, `dashboard.py`, `informe.py`.
Especificaciones: [HISTORIAL.md](HISTORIAL.md), [DASHBOARD.md](DASHBOARD.md), [INFORME.md](INFORME.md).

## Qué haría falta para usarlo en la empresa

1. **Fuentes de datos oficiales.** Hoy los precios vienen de data912, que no es oficial. Las APIs de BYMA las
   reemplazarían, pero las tiene que contratar una persona jurídica.
2. **Datos de los clientes desde los sistemas de Boston,** en lugar de los extractos de cada broker. La
   herramienta ya separa el código de los datos: alcanza con una nueva forma de cargarlos.
3. **Dónde corre.** Hoy es una herramienta local de una Mac. Para varios asesores habría que definir si queda
   local o pasa a un servidor interno.
4. **Revisión de sistemas** del código y de su seguridad ([SEGURIDAD.md](SEGURIDAD.md)).

## Próximo desarrollo

Renta variable a futuro: estimaciones de lo que puede rendir la parte de acciones y CEDEARs, para completar
el cuadro de [MAPA.md](MAPA.md).
