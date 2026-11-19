# Encargo para Codex: series históricas de BYMA Data

Relevamiento, sin integrar a `src/cartera` todavía, como se hizo con IAMC (`docs/FUENTE_IAMC.md`).

## Contexto

La etapa 14 (`docs/RIESGO.md`) mide el riesgo con históricos de data912, que no tiene:

- letras ni ON;
- GLD, SLV, PEP, CVS, WDC, MP, OXY, B, SHEL, XLV ni PETR3;
- AO28, TZXM7, BPOB7, BAM27 ni TZV28;
- más de un año de MU, JPM, NVDA, BRKB, ABEV y otros.

BYMA Data abierto (`https://open.bymadata.com.ar/#/dashboard`) publica series históricas.

El 18/11/2026 el servidor no aceptó conexiones desde la Mac de Felipe: no respondió el puerto 443, ni por
terminal ni por navegador. byma.com.ar, IAMC y data912 sí respondían. Puede ser un bloqueo por VPN o por red.

## Qué hacer

1. **Conexión.** Verificar si conecta y, si no, por qué.
2. **API detrás del tablero.** Identificar cómo se piden las series históricas: URL, parámetros, formato del
   símbolo (por ejemplo `AL30 24HS`) y plazo de liquidación. No inventar parámetros: documentar solo lo
   observado.
3. **Cobertura.** Probar con los tickers de la lista de arriba, más AL30, AL30C, AL30D y SPY:
   - si cada uno existe;
   - primera y última fecha;
   - campos (apertura, máximo, mínimo, cierre, volumen, monto);
   - si el cierre está ajustado por dividendos o cambios de ratio.
4. **Comparación con data912.** Comparar con data912 para AL30, AL30C y SPY en las mismas fechas.
5. **Entregables:**
   - `docs/FUENTE_BYMADATA.md` con todo lo anterior;
   - muestras en `fixtures/bymadata/`;
   - un extractor en `tools/bymadata_extraer.py`, fuera de `src`.

Reglas de `AGENTS.md`. Nada de credenciales ni scraping que viole los términos del sitio. Si pide registro,
frenar y avisar.
