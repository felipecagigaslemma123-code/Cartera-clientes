# Pedido de APIs de BYMA

**Para:** Elio (sistemas, Boston) · **De:** Felipe · **Fecha:** 19/11/2026
**Estado:** consulta por confirmar. Todavía no hay credenciales ni una prueba con acceso autorizado.

## Por qué se piden a través de la empresa

Las ocho APIs figuran en el catálogo de BYMA como **«No requiere homologación»**: no hace falta la
certificación técnica previa. Pero BYMA ofrece Market Data por API **solo a personas jurídicas**, con
condiciones comerciales por producto. Felipe no puede pedirlas a su nombre: tiene que habilitarlas Boston.
[Catálogo técnico de BYMA](https://www.byma.com.ar/byma-apis) ·
[Planes y requisitos de Market Data](https://www.byma.com.ar/productos/productos-de-datos/market-data/apis)

## APIs pedidas

| API de BYMA | Prioridad | Para qué | Funcionalidad ([PROPUESTA.md](PROPUESTA.md)) |
|---|---|---|---|
| **End of Day (EOD)** | Piloto | Cierres de letras, bonos y ON, para contrastarlos con otras fuentes y alimentar el tablero. Su historia sirve también para el riesgo | 1 y 2 |
| **BYMA Primarias Placements** | Piloto | Próximas licitaciones e historial de colocaciones, con datos de la emisión y enlaces a documentos | 1 |
| **Delay20** | Segunda etapa | Cotizaciones durante la rueda, con 20 minutos de demora | 3 |
| **Índices** | Segunda etapa | Referencias de mercado para el tablero, empezando por el índice de caución | 1 y 2 |
| **Índice Dólar BYMA** | Segunda etapa | Dólar BYMA y CCL con la identificación oficial | 2 y 3 |
| **Market Data Instruments** | Segunda etapa | Maestro de renta fija: vincular cada instrumento con sus cotizaciones | 1 |
| **Market Data News** | Complementaria | Hechos relevantes, avisos, balances y prospectos de emisores | 1 |
| **Economic Indicators** | Complementaria | Ver si agrega algo a la API del BCRA para los resúmenes macro, solo series económicas | 1 |

**Fuera del pedido:** BYMA Primarias Agentes (gestión de ofertas), Clearing Risk y Market Fees.

Para **Índices** y **Economic Indicators**, la ficha técnica muestra la etiqueta de agente miembro: hay que
confirmar si están disponibles para Boston.

## Qué hay que confirmar con BYMA o en la empresa

1. Qué productos tiene habilitados Boston.
2. Si se puede autorizar una aplicación con **permisos de solo lectura** para probar EOD y Placements.
3. En qué entorno está permitido usarlas.
4. Qué condiciones hay para **guardar los datos** y para **incluirlos en informes a clientes**.
5. Si el tema lo lleva otra persona, quién.

## Consulta para Elio

> Hola, Elio. ¿Cómo estás? Estoy evaluando qué datos de BYMA podemos conectar a una herramienta de renta fija.
> Para una primera prueba me interesan **End of Day**, para precios de cierre, y **BYMA Primarias
> Placements**, para seguimiento de emisiones y licitaciones.
>
> También quisiera saber si tienen habilitadas Delay20, Índices, Índice Dólar BYMA, Market Data Instruments,
> Market Data News y Economic Indicators, para evaluar cuáles sumaría después. En el catálogo de BYMA estas
> APIs figuran sin homologación.
>
> ¿Podés confirmar qué productos están disponibles y si se puede habilitar un acceso de solo lectura para probar
> las dos primeras? Si corresponde, también me serviría saber en qué entorno está permitido usarlas y si hay
> condiciones para guardar datos o incluirlos en informes. Si esto lo lleva otra persona, ¿me indicás con quién
> verlo? Gracias.

## Qué datos le faltan hoy a esta herramienta

| Dato | Lo usa | Hoy | API que lo resolvería |
|---|---|---|---|
| Cierres históricos de varios años | Riesgo ([RIESGO.md](RIESGO.md)) | data912: un año, desde el 12/11/2025, y sin letras, ON, AO28, TZXM7, BPOB7, BAM27, TZV28, GLD, SLV, PEP, CVS, WDC, MP, OXY, B, SHEL, XLV ni PETR3 | EOD |
| Precio del día de fuente oficial | Tenencia, dashboard, alertas | data912, no oficial | Delay20 o EOD |
| Condiciones de cada título de renta fija | Flujo de fondos ([FLUJO_FONDOS.md](FLUJO_FONDOS.md)) | Cierre de IAMC y algunos cronogramas cargados a mano | Market Data Instruments |
| Dólar CCL oficial | Riesgo de CEDEARs, valuación en dólares | Calculado con AL30 y AL30C | Índice Dólar BYMA |

BYMA Data abierto (`open.bymadata.com.ar`) publica series sin registro, pero el 18/11/2026 no respondió desde
la Mac de Felipe. Si responde desde la red de la empresa, sirve como prueba previa
([ENCARGO_BYMADATA.md](ENCARGO_BYMADATA.md)).

## Punto de partida técnico

El cliente de las APIs de BYMA **no está en este repositorio**: está en el *Fixed Income Toolkit*, el proyecto
de renta fija de Felipe del que salió el motor de letras de esta herramienta (`src/cartera/_motor_letras/`).
Ahí hay:

- un cliente de solo lectura con las consultas iniciales de cada API (`src/market_data/providers/byma.py`) y su
  contrato con los manuales oficiales (`docs/providers/byma_provider_contract.md`);
- un comando para probar cada consulta cuando haya acceso (`tools/smoke_byma.py`);
- pruebas con respuestas simuladas, que pasan (`tests/test_byma_provider.py`).

El endpoint de EOD respondió **401** a una consulta sin credenciales, como se esperaba. Falta la prueba con
acceso autorizado y revisar respuestas reales antes de integrarlas.

## Piloto mínimo, cuando haya acceso

- **EOD:** una rueda y un instrumento identificados sin ambigüedad. Antes de comparar precios, cotejar fecha,
  moneda, plazo, segmento y base de cotización; distinguir precio de cierre de último operado.
- **Placements:** una colocación conocida, verificando estado, fechas y enlaces contra la publicación oficial
  de [BYMA Primarias](https://www.byma.com.ar/productos/productos-financieros/primarias/colocaciones).

## Cómo se integrarían

Como las fuentes actuales: un módulo de lectura aparte, respuestas guardadas en `fixtures/` para las pruebas y
la clave fuera del repositorio, en una variable de entorno o en el llavero del sistema. **Nunca se sube una
clave a GitHub.** Cualquier cálculo financiero nuevo pasa por el proceso de especificación, pruebas y revisión
del proyecto ([AGENTS.md](../AGENTS.md)).
