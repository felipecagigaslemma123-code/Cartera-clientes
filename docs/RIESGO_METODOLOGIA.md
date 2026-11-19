# Metodología de riesgo para `cartera`

Versión de referencia: 18 de noviembre de 2026. Destino: implementación posterior en Python 3.9. Este trabajo no modifica ni implementa la herramienta productiva. Los números del caso de prueba son enteramente ficticios.

> Nota de Claude (18/11/2026): los archivos que este documento cita como `verificacion/` están en `tools/riesgo/`. `comprobar.py` necesita una copia de la bibliografía de la materia en `bibliografia/`, junto a la carpeta de trabajo; el caso ficticio se comprueba sin ella. data912 sí respondió desde fuera del entorno de Codex: el histórico trae `date, o, h, l, c, v, dr, sa` (cierre sin ajuste por dividendos; `dr` = c/c anterior − 1), con un solo año para varios CEDEARs y sin GLD, SLV, PEP, AO28, TZXM7, BPOB7, BAM27 ni TZV28.

## 1. Contrato de implementación y procedencia

La unidad de análisis es el **retorno total de una inversión, expresado en una misma moneda y durante el mismo intervalo**. El riesgo de la cartera depende de sus covarianzas; sumar volatilidades o VaR individuales no calcula su riesgo conjunto. Una sensibilidad contractual de bonos tampoco reemplaza una distribución de pérdidas.

**Regla obligatoria del encargo:** nunca inventar una observación. No interpolar, no arrastrar el último precio, no convertir una ausencia en cero, no sustituir un activo por otro sin identificarlo. Mostrar `sin dato`, motivo, fecha, observaciones utilizadas, activos excluidos y peso excluido. Una cotización repetida efectivamente observada y un precio que se arrastró para llenar un hueco son situaciones diferentes.

Las decisiones identificadas como **propuesta** son criterios operativos de esta entrega: no se atribuyen a los libros. Las fórmulas derivadas se identifican como tales. Las fuentes se citan mediante los códigos siguientes; todas las páginas PDF son ordinales desde 1, incluso las portadas. En las clases, página PDF y diapositiva coinciden salvo que se indique lo contrario.

| Código | Archivo en `bibliografia/` | Localizadores utilizados |
|---|---|---|
| C01 | `clases admin carteras/Clase 01_ Intro_2025.pdf` | diap. 5–6, 9, 13, 16, 19–21: retornos, frecuencia, riesgo e informes |
| C06 | `clases admin carteras/Clase 06_Construcción de Carteras_2025.pdf` | construcción y diversificación; complemento conceptual de C07 |
| C07 | `clases admin carteras/Clase 07_Cómo calcular la CAL_CML y Markovitz_2025 (2).pdf` | diap. 3–4, 10, 16, 32–40: covarianza, logaritmos, estimación y alternativas |
| C08 | `clases admin carteras/Clase 08_Index Models y CAPM_2025 (1).pdf` | diap. 9–13, 24–29, 38–45, 49–53: regresión, descomposición, CAPM y límites |
| C09 | `clases admin carteras/Clase 09_Multifactor models_2025 (1).pdf` | diap. 3–6: inflación, tasas y factores adicionales |
| C13 | `clases admin carteras/Clase 13_ PERFORMANCE y NUEVA GENERACIÓN DE PRODUCTOS (1).pdf` | diap. 4–9: Sharpe, Treynor, Jensen, information ratio y Sortino |
| BKM | `Investments 10th edition_Bodie_Keane_Marcus.pdf` | cap. 5, PDF 146–196; especialmente PDF 162/p.133, 168–169/pp.139–140, 184/p.155; cap. 7–11; cap.14–16, especialmente PDF 549–550/pp.520–521 y 555–556/pp.526–527; cap.24 PDF 870–872/pp.841–843 |
| FI | `libros/CFA 2025 Level I - FI, Derivatives.pdf` | PDF 88–101: reinversión y duration; 103–117: convexidad, curvas y key rates; 118–120: crédito |
| FIII | `CFA level III, Formulas..pdf` | PDF 3–4: factores y contribuciones; PDF 9: desempeño y drawdown. Es una hoja de fórmulas incluida en la carpeta, no evidencia de autoría oficial del CFA Institute |
| VAR | `Resumen_VAR_Riesgo_Baja.pdf` | PDF 1: riesgo a la baja, normalidad, VaR, Cornish–Fisher y ES |
| RC | `Resumen_Construccion_de_Carteras_Detallado.pdf` | PDF 1–2: media, covarianza, diversificación, Sharpe |
| VOL | `Estimando volatilidades.xlsx` | hojas `MA`, `EWMA`, `GARCH (1,1) SP500`; referencias exactas en §3 y §12 |
| BET | `EJERCICIOS 1:10/Clase 08_Testeando betas_2025.xlsm` | `Base`, `R - Rf` C9:D68, D5:D6; `Test CAPM` B3:D32 y G4:G5 |
| MARK | `EJERCICIOS 1:10/Clase 08_Markovitz no short sales_2025.xlsm` | `Caso 0_con short sales` B3:E6, B11:B14, B18 |
| IM | `Resumen_Index_Model_vs_Markowitz.xlsx` | hojas `Resumen teórico`, `Fórmulas`; B7:B8 y B5:B8 respectivamente |
| QIA | `A - Quantitative Investment Analysis - R A Defusco, D W Mcleavey, J E Pinto  D E Runkle (CFA Institute) - 2004 [1932495088].pdf` | escaneo; páginas seleccionadas inspeccionadas visualmente, detalladas en §13 |
| TS | `thinkstats.pdf` | PDF 25: varianza poblacional/muestral; apoyo estadístico, no convención de mercado |
| HRP | `2016_Hierarchical-Risk-Parity-portfolio_SSRN-id2708678.pdf` | PDF 3–5, 10–12: inestabilidad de covarianzas, correlación y evaluación fuera de muestra |
| SM8/SM9 | `ejercicios/SMChap008.doc`, `ejercicios/SMChap009.doc` | capítulo 8 problema 1: residuos correlacionados; capítulo 9 problemas 2–5: beta y CAPM. La conversión de ecuaciones incrustadas es incompleta |

### 1.1 Parámetros predeterminados

**Todos los umbrales de suficiencia y las ventanas de esta tabla son propuestas**, salvo el λ y la anualización explícitos de VOL. Son configurables, deben registrarse junto a cada resultado y requieren validación posterior con las carteras reales.

| Parámetro | Recomendación inicial | Motivo / procedencia |
|---|---|---|
| Moneda principal | USD obtenido por CCL; vista complementaria ARS | propuesta; separar poder de compra en dólares y riesgo nominal en pesos (§9) |
| Retorno para cartera, covarianzas y VaR | simple total | agregación exacta por valor; C01 diap.5 y BKM cap.5 |
| Retorno para reproducir VOL/BET | logarítmico | VOL `AH3:AH1280`, BET `R - Rf`; C07 diap.32 |
| Año estadístico | 252 sesiones diarias; 52 semanas o 12 meses | VOL `AL4=AK4*SQRT(252)`; C01 diap.6 admite 251/252 y otras bases |
| Volatilidad/covarianza histórica | últimas 252 sesiones esperadas; mínimo 126 retornos válidos | propuesta de horizonte reciente; mínimo técnico de varianza: 2 |
| Cobertura temporal | al menos 95% de retornos esperados de la ventana | propuesta; publicar numerador/denominador. No extender arbitrariamente el pasado para disimular huecos |
| Beta diario | 252 sesiones, mínimo 126 pares alineados | propuesta; control mensual de 60 meses cuando exista historia. BET usa 60 observaciones mensuales |
| EWMA | λ=0,94, media cero, semilla primer retorno al cuadrado; mínimo 60 retornos consecutivos para uso operativo | λ y semilla de VOL; mínimo y uso operativo: propuesta |
| VaR/ES diario | confianza 95%, horizonte 1 sesión; μ=0 en normal | propuesta de reporte; 95% aparece en BKM PDF168. μ=0 evita presentar media histórica ruidosa como pronóstico |
| Históricos de cola | ventana 504 sesiones, mínimo 250 retornos completos y al menos 10 observaciones efectivas de cola | propuesta; 250 a 95% da 12,5 observaciones en cola; 99% necesita al menos 1000 para llegar a 10 |
| VaR a mayor plazo | adicional 10 sesiones, con retornos de ese horizonte; raíz del tiempo sólo comparador normal | propuesta y límites BKM PDF184 |
| Grados de libertad | n−1 para var/cov; n−2 para error de regresión con intercepto y un factor | BKM PDF162; QIA, sección regresión (§13) |
| Tests | bilateral 5%; IC de beta al 95%; H0 beta=1 y alfa=0, beta=0 opcional | propuesta de hipótesis operativas; modelo C08, inferencia QIA |
| Sensibilidad de bonos | choques paralelos ±100/±200 pb; agregar ±50 pb y ejemplo +10 pb | ±100/±200: propuesta; FI PDF104–106 usa ±50; BKM PDF556 usa +200 y +10 |
| Diferencias finitas | choque 1 pb, comparar además 10 pb | propuesta numérica; FI PDF97–99 y 112 |
| Liquidez | 20 sesiones; participación de salida 10% del monto diario | propuesta, sin atribuir estos valores a la bibliografía |
| Monte Carlo | 10.000 simulaciones, semilla 1729; normal multivariada aditiva | propuesta demostrativa, no motor productivo de valuación |

No confundir mínimo matemático con suficiencia operativa: con dos retornos se obtiene un desvío, pero no se habilita un informe de riesgo. El caso ficticio usa 260 retornos y una ventana de prueba completa; no alcanza la ventana recomendada de 504 para estimación de cola en producción, aunque supera el mínimo de 250.

## 2. Datos, calendario y retornos

### 2.1 Precios y retornos totales

Definiciones (C01 diap.5–6, 9; BKM cap.5):

- `r_t = (P_t + D_t) / P_(t−1) − 1`, retorno simple. `D_t` incluye dividendos, cupones y amortizaciones cobrados por la posición que existía al comienzo del intervalo. Precio de bono: **sucio**, con intereses corridos, expresado sobre una base de nominal consistente antes/después de amortizar.
- `l_t = ln(1+r_t)`. Sin pagos, `l_t=ln(P_t/P_(t−1))`.
- Retorno acumulado de varios períodos: `R = producto_t(1+r_t) − 1`; log acumulado: `L=suma_t l_t`. **Nunca** promediar retornos diarios para obtener el retorno realizado mensual.
- Media aritmética diaria `mu = suma r_t/n`. Su anualización `N*mu` es un resumen aritmético bajo supuestos de estabilidad, no rentabilidad efectivamente ganada.
- Rentabilidad anual compuesta de una serie completa y regular: `G_anual = [producto(1+r_t)]^(N/n)−1`. No utilizar `n` como tiempo transcurrido si se eliminaron huecos. Para una trayectoria con fechas reales usar su duración efectiva; sin trayectoria completa, `sin dato` de rentabilidad realizada.

**Datos y unidades:** dos valuaciones comparables consecutivas, pagos y ajustes corporativos; salida decimal por intervalo, `0,01=1%`. Pesos monetarios y flujos deben ser de la misma moneda. Con precio inicial no positivo, pago desconocido, denominador inconsistente o dato faltante: `sin dato`. El simple admite pérdida de 100%; el log no existe si `1+r<=0`. La referencia `riqueza`/drawdown exige riqueza positiva; una quiebra a cero debe informarse explícitamente como pérdida de 100% fuera de esa función.

No sumar dividendos a un cierre ya ajustado por dividendos. Ante splits, canjes, cambios de ratio o amortización, ajustar con un evento **conocido**, no con una corrección deducida de un salto grande. Si el proveedor sólo ofrece cierre sin pagos, etiquetar `retorno de precio`, no `retorno total`; no tratar una baja por cupón como pérdida económica. **Propuesta:** bloquear métricas de retorno total si un evento es conocido y no se puede reconstruir; un retorno de precio puede quedar sólo como diagnóstico claramente separado.

### 2.2 Calendarios, feriados, inactividad y huecos

**Propuesta operativa que aplica la regla del encargo:**

1. Ordenar fechas, validar números finitos, moneda, zona horaria, fecha de concertación y condición de liquidación. Unificar el plazo de liquidación; no unir contado inmediato con otro plazo como si fuera un mismo cierre.
2. Duplicados idénticos: conservar uno, registrar el descarte. Duplicados conflictivos: invalidar la fecha hasta resolverlos.
3. Trabajar sobre un calendario de sesiones **confirmado** del mercado local para los precios locales. Sábados, domingos y feriados confirmados no son observaciones faltantes; no se les agrega precio ni retorno cero. Un intervalo entre dos sesiones consecutivas puede cruzar varios días corridos y sigue siendo un retorno de sesión.
4. Sesión abierta sin operación: conservar la ausencia como `sin dato`; cero volumen conocido significa falta de negocio, no precio cero. Si hay cierre indicativo o arrastrado, conservarlo como dato de valuación con su estado, pero excluirlo de la serie de precios negociados para medir riesgo.
5. Si falta el precio de una sesión esperada, son inválidos **ambos** retornos que lo necesitan. El próximo precio disponible no produce un retorno diario contra el último precio viejo. Un retorno observado de varios días puede mostrarse como tal, sin mezclarlo con diarios ni dividirlo por el número de días para inventar retornos.
6. Para covarianzas, beta y VaR histórico de cartera, construir primero retornos de **exactamente los mismos extremos temporales** y después hacer intersección completa. No alcanza con coincidir en la fecha final.
7. Calendarios de EE.UU. y Argentina difieren. Para un CEDEAR en ARS, usar sus sesiones locales. Para estudiar factores externos, usar intervalos cuyos extremos tengan cotizaciones verificadas de ambos mercados y cierres temporalmente comparables. No arrastrar S&P en un feriado estadounidense. Alinear cierres para evitar usar un precio conocido después del cierre local; si no es posible, el modelo de factores queda `sin dato` o se trabaja con retornos semanales de extremos reales.
8. Para semanales/mensuales, elegir de antemano el cierre de sesión de cada período. La regla no autoriza usar un precio viejo por un hueco en la sesión elegida. C07 diap.4 sugiere semanales/mensuales por ruido diario; **propuesta:** emplearlos como diagnóstico de robustez, no cambiar silenciosamente de frecuencia.

Las estadísticas históricas pueden usar retornos válidos aislados dentro de una ventana si se publican huecos y cumplen el umbral de cobertura; eso no crea una trayectoria de riqueza. Para drawdown e historia de performance exigir trayectoria completa. EWMA exige tramo consecutivo: un hueco rompe la recursión y obliga a reiniciar/calentar con datos observados; no aplicar λ repetidas veces sobre retornos inexistentes. Las funciones matemáticas rechazan `None`; el adaptador de calendario decide explícitamente qué fechas entran.

## 3. Volatilidad histórica y EWMA

### 3.1 Volatilidad histórica

Dispersión de retornos, en ambas direcciones; no representa una pérdida máxima.

`mu = (1/n) suma r_t`

`s² = suma (r_t−mu)² / (n−1)`; `s=sqrt(s²)`; `s_anual=s*sqrt(N)`.

**Entradas:** retornos simples totales para el riesgo monetario; logarítmicos para reproducir la cátedra. **Parámetros:** N=252, ventana 252, mínimo operativo 126, cobertura 95% (§1.1). **Unidades:** `s` en retorno por sesión; `s²` en retorno²; anualización de varianza `N*s²`. Para semanas/meses usar 52/12 y mantener todos los componentes en la misma frecuencia. **No calculable:** menos de dos retornos, datos inválidos o intervalos heterogéneos; no publicable si incumple mínimos operativos. Una serie conocida y constante tiene s=0, pero no prueba ausencia de riesgo de crédito, devaluación o liquidez.

**Diferencia de fuentes:** C01 diap.16 muestra denominador N en una definición descriptiva. BKM PDF162/p.133 presenta primero n, luego corrige a n−1 para estimar varianza poblacional; TS PDF25 también distingue ambos usos; QIA PDF140/p.132 presenta la varianza muestral con n−1. Se recomienda **n−1** para estimación histórica. El desvío resultante no es estrictamente un estimador insesgado del desvío poblacional: la corrección hace insesgada la varianza. VOL utiliza `STDEV.S`, aunque su rango de entrada está vacío (§12).

La regla de raíz del tiempo requiere retornos no autocorrelacionados y varianza estable. Inflación, crisis, precios poco líquidos y saltos pueden violarla. No usar 365 para volatilidad de cierres bursátiles porque un contrato devengue con base 365. C01 diap.6 menciona 360/365, pero VOL fija 252; se recomienda 252 para las series bursátiles y respetar aparte el cómputo contractual de días de cada bono.

### 3.2 EWMA de VOL, con el índice temporal exacto

Pronóstico de varianza condicional, con mayor peso en la observación reciente:

`v_(t+1) = lambda*v_t + (1−lambda)*l_t²`; `sigma_(t+1)=sqrt(v_(t+1))`.

Se asume media condicional cero; no restar la media histórica si se busca reproducir VOL. λ=0,94 procede de `GARCH (1,1) SP500!AN2`. No se encontró otra λ completada en la hoja llamada `EWMA`.

**Convención comprobada:** `AH3=ln(AG3/AG2)`, `AI3=AH3²`, `AJ3=AI3` (semilla). `AJ4=.94*AJ3+.06*AI3`; `AJ5=.94*AJ4+.06*AI4`; `AK=sqrt(AJ)`; `AL=AK*sqrt(252)`. Por tanto, `AJ1280` es la varianza **previa al retorno de la fila 1280**, no el pronóstico posterior a incorporarlo. El pronóstico siguiente es `.94*AJ1280+.06*AH1280²`.

**Entradas:** precios positivos consecutivos, retornos log, λ y semilla. **Defaults y datos insuficientes:** semilla primer log al cuadrado; el primer valor es una inicialización ex post, no un pronóstico ex ante. **Propuesta:** mínimo de 60 retornos consecutivos antes de usarlo; guardar fecha de inicio y semilla. Una semilla externa conocida puede suministrarse explícitamente. Un hueco no admite actualización ficticia. **Unidades/anualización:** varianza diaria, `sqrt(252*v)` anual. No tratar `lambda` como tasa ni elevarla a 252 para anualizar el riesgo. Función: `ewma`, que devuelve `previas` y `siguiente`.

EWMA reacciona a shocks, pero no contempla por sí mismo riesgo de default ni genera una reversión a una varianza de largo plazo. La hoja también trae GARCH: no se propone calibrarlo para esta versión, por la estimación adicional y los datos insuficientes de varios instrumentos.

## 4. Riesgo conjunto, diversificación y concentración

Fuentes: C07 diap.3–4, 32–40; RC PDF1; FIII PDF4; HRP PDF3–5. Las contribuciones son derivadas algebraicas de `sqrt(w'Σw)` y coinciden con el esquema marginal de FIII.

### 4.1 Matrices y varianza de cartera

Para n filas comunes y k activos:

`S_ij = suma_t [(r_it−mu_i)*(r_jt−mu_j)] / (n−1)`.

`rho_ij = S_ij / sqrt(S_ii*S_jj)`.

`V = suma_i V_i`; `w_i=V_i/V`; `r_pt=suma_i w_i*r_it` para pesos al inicio del intervalo.

`var_p = w' S w = suma_i suma_j w_i*w_j*S_ij`; `sigma_p=sqrt(var_p)`.

**Entradas:** valuaciones actuales comparables para pesos, matriz de retornos alineados de idéntica moneda/frecuencia; propuesta 252 sesiones y al menos 126 filas comunes con cobertura temporal ≥95%. Retener exactamente las mismas filas para todos los pares. La eliminación por pares puede producir matrices no semidefinidas positivas; no usarla para la cartera. **Unidades:** covarianzas en retorno² por sesión, correlación sin unidad entre −1 y 1, sigma decimal por sesión. **Anualización:** `S_anual=252*S`, `sigma_anual=sqrt(252)*sigma`. **Sin dato:** cartera de valor cero, instrumentos sin valuación actual, matriz incompleta o sin suficiente intersección. Una correlación con efectivo constante es indefinida (`null`), aunque su covarianza sea cero; no rellenarla con 0 ni 1.

Validar simetría, diagonal no negativa y semidefinición positiva con tolerancia numérica. Una matriz singular puede medir riesgo de pesos dados; no hace falta invertirla. El chequeo Cholesky de referencia admite ceros. No corregir una matriz arbitrariamente para que pase. HRP advierte sobre estimación inestable y largos históricos no estacionarios: aporta esa advertencia, no una medida nueva necesaria para este encargo. No implementar un optimizador HRP para medir una cartera existente.

**Pesos actuales:** el riesgo prospectivo histórico aplica los pesos de hoy a shocks históricos. Si se construye una serie `suma w_hoy*r_t` para drawdown, llamarla “cartera hipotética con pesos actuales y rebalanceo diario”. La performance real requiere posiciones, pagos, aportes/retiros y pesos históricos; no puede recuperarse con una foto actual.

### 4.2 Contribuciones al riesgo

Sea `q=S*w`:

`MCR_i = d(sigma_p)/d(w_i) = q_i/sigma_p`.

`CR_i = w_i*MCR_i`; `suma CR_i = sigma_p`; `fraccion_i=CR_i/sigma_p`.

Equivalencia FIII: `beta_i,p = Cov(r_i,r_p)/var_p`; `MCR_i=beta_i,p*sigma_p`.

**Parámetros y entradas:** mismos de la matriz; pesos fijos, derivada sin imponer que la suma de pesos siga en 1 al mover un peso. Una sustitución de efectivo por otro activo necesita especificar cómo se financia. **Unidades:** marginal en retorno por unidad de peso; componente en retorno, o puntos porcentuales de volatilidad; fracción sin unidad. Multiplicar MCR y CR diarios por `sqrt(252)` para anualizarlos. No multiplicar por el patrimonio salvo que se quiera una medida de dispersión monetaria. **Sin dato:** sigma_p=0 o matriz no válida. Un componente negativo es posible: describe cobertura, no un error; las fracciones pueden ser negativas y otras superar 100%.

### 4.3 Diversificación

**Propuesta de indicadores derivados:** para posiciones largas, `sigma_sin_div=suma w_i*sigma_i`; `DR=sigma_sin_div/sigma_p`; `reduccion=1−sigma_p/sigma_sin_div`. La base sin diversificación supone correlación +1 con esas volatilidades. Para libros con cortos, la función usa `suma |w_i|*sigma_i`, que es una cota de exposición bruta, no una cartera larga equivalente.

Entradas iguales a §4.1. DR y reducción no tienen unidad y no se anualizan; ambos requieren denominador positivo. No comparar DR entre monedas o ventanas distintas. Una correlación menor que 1 **puede** mejorar una combinación; agregar un activo no reduce necesariamente el riesgo si cambia la asignación o agrega apalancamiento. El resumen RC PDF1 dice que correlación cero implica independencia: eso sólo vale bajo hipótesis adicionales, por ejemplo normalidad conjunta; aquí se interpreta como ausencia de relación lineal.

### 4.4 Concentración por patrimonio

**Propuesta, no fórmula hallada en la cátedra:** `HHI=suma w_i²`; `numero_efectivo=1/HHI`; `peso_maximo=max(w_i)`. Para k pesos iguales, HHI=1/k. Incluye efectivo y activos sin historia porque mide patrimonio, no volatilidad estimada. Agregar también pesos por emisor, grupo económico, país, moneda y factor con clasificaciones verificadas; no duplicar un mismo riesgo por contar dos especies del mismo bono como emisores distintos.

Datos: valores actuales de toda la cartera, posiciones largas, pesos sumando 1. Sin anualización, unidades adimensionales; mostrar HHI entre 0 y 1, no alternar con la escala 0–10.000. Si hay valores faltantes o patrimonio no válido: sin dato de HHI total. Si hay cortos: no aplicar este HHI como si fuera largo; diseñar exposición neta/bruta por separado. HHI bajo no implica baja correlación ni bajo riesgo.

## 5. Modelo de índice, CAPM y pruebas

### 5.1 Estimación y descomposición

C08 diap.9–13, 38–45; IM `Fórmulas!B2:B8`; BKM cap.8–9; SM8 problema 1. Definir `x_t=r_Mt−rf_t`, `y_t=r_it−rf_t` y estimar con intercepto:

`y_t = alfa + beta*x_t + e_t`.

`beta=Cov(x,y)/Var(x)`; `alfa=media(y)−beta*media(x)`.

`SSE=suma e_t²`; `SST=suma (y_t−media(y))²`; `R²=1−SSE/SST`.

`var_sist=beta²*Var(x)`; `var_especifica=SSE/(n−1)`.

Con el mismo n−1, `Var(y)=var_sist+var_especifica`. Para inferencia usar **otra** cantidad: `s_e²=SSE/(n−2)`. No sumar esa estimación con n−2 al componente sistemático con n−1 esperando una identidad exacta. IM `Fórmulas!B8`, que recupera sigma desde R², requiere que las varianzas tengan convenciones compatibles; es indefinida en R²=1.

**Unidades:** beta/R² sin unidad; alfa retorno por período; varianzas retorno². Beta y R² no se anualizan. Alfa anual aritmética `N*alfa`, varianzas `N*var`; no interpretar alfa histórica como rentabilidad prometida. **Entradas:** series de activo/mercado/rf con mismos extremos, moneda, frecuencia y tipo de retorno; defaults §1.1. **Sin dato:** n<3, Var(x)=0, faltantes; R² indefinido si SST=0. Un activo puede no tener beta calculable y aun así tener volatilidad o duration calculables.

CAPM como relación de equilibrio: `E(r_i)=rf+beta_i*[E(r_M)−rf]`. No identifica la volatilidad total ni sirve como sustituto de datos de un bono sin historia. Beta de una cartera: `beta_p=suma w_i*beta_i` sólo si todas se estimaron contra el mismo mercado, muestra, rf y convención; en la implementación es preferible regresar directamente la serie de cartera. No promediar una beta contra Merval con otra contra S&P.

### 5.2 Qué mercado usar — propuesta argentina

- Acciones argentinas: S&P Merval, idealmente retorno total en la moneda de medición. Si sólo existe índice de precio, identificarlo y no comparar un alfa de retorno total como si ambas series incluyeran los mismos dividendos.
- CEDEARs: para sensibilidad de negocio, subyacente y S&P 500 en USD; para riesgo de la posición local, CEDEAR y S&P convertido a la moneda seleccionada, más CCL como factor separado. Un CEDEAR sectorial o de otro país puede necesitar otro índice; SPY no representa todo subyacente.
- Cartera mixta: benchmark compuesto con política de pesos conocida o modelo de factores; no forzar una única beta Merval a bonos CER, efectivo USD y CEDEARs. Si los índices no están disponibles en las fuentes autorizadas, beta `sin dato`. El CEDEAR SPY puede ser proxy negociado del benchmark **local**, pero agrega tracking, ratio y liquidez; no sustituye silenciosamente al S&P 500 USD.

La elección de Merval/S&P y los proxies es **propuesta**; C08 utiliza S&P 500 como ejemplo, no resuelve CEDEARs ni la conversión argentina.

### 5.3 Test individual de beta y alfa

Bajo OLS con intercepto, errores independientes/homocedásticos y normalidad para el test exacto:

`Sxx=suma (x_t−media(x))²`; `SE_beta=sqrt([SSE/(n−2)]/Sxx)`.

`t_beta=(beta−beta_0)/SE_beta`; `df=n−2`; `p=2*[1−F_Student(|t|,df)]`.

`IC95_beta=beta ± t_(0,975,df)*SE_beta`.

`SE_alfa=sqrt([SSE/(n−2)]*[1/n+media(x)²/Sxx])`; `t_alfa=alfa/SE_alfa`.

**Defaults propuestos:** beta_0=1 (riesgo parecido al índice); prueba adicional beta_0=0 (exposición detectable), alfa_0=0, 5% bilateral. n mínimo matemático 3; operativo 126 diarios o análisis separado con 60 meses. Sin SE válido o con colinealidad: no afirmar significación. Con ajuste exacto, la referencia devuelve t=null y p=0 si la diferencia es distinta de cero, p=1 si es cero: es un caso degenerado, no evidencia estadística fuerte. Beta no significativa **no** significa riesgo cero.

QIA cap.8, PDF413–414/pp.405–406, respalda el uso de Student para pendientes (§13); PDF411/p.403 distingue SSE/(n−2) de la varianza muestral con n−1. Con heterocedasticidad, serialidad o precios estancados, esos p e IC son orientativos; **propuesta:** advertencia visible y revisión con retornos semanales/mensuales. No etiquetarlos “robustos”: la referencia no implementa HAC/Newey–West.

### 5.4 Reproducción de la clase 08 y segunda pasada CAPM

BET contiene 60 retornos mensuales logarítmicos de Alcoa y S&P. `R - Rf!D5=SLOPE(D9:D68,C9:C68)` da beta 1,902798383662 y `D6` alfa mensual 0,000370710470. La planilla resta **$B$9**, una rf fija, incluso en las filas siguientes; esto se conserva en la reproducción, pero la implementación propuesta debe usar rf_t observada y correctamente convertida cuando varía. Logaritmos y rf deben compartir convención; restar una tasa simple a un log es sólo aproximación. Para estimación nueva se recomienda simple−simple o log−log.

La hoja `Test CAPM` hace además una segunda regresión transversal: `media_exceso_i = gamma_0 + gamma_1*beta_i + u_i` con los 30 activos. Sus valores guardados son `G4=0,000717588957` y `G5=−0,001972438252`. Ambos se reproducen en `comprobar.py`. Contrastarla con gamma_0=0 y gamma_1=prima de mercado requiere considerar que las betas son estimadas y hay errores correlacionados entre activos. La pendiente negativa del ejercicio no autoriza concluir que desapareció el riesgo sistemático; C08 diap.49–53 desarrolla las limitaciones del proxy de mercado y las pruebas de CAPM.

### 5.5 Factores múltiples

C09 diap.3–6 permite sumar inflación, tasas y otros riesgos. Fórmula general `y_t=alfa+suma beta_j*f_jt+e_t`; `Var(y)=b'Cov(f)b+Var(e)` cuando los residuos son ortogonales a los factores. OLS `coef=(X'X)^−1 X'y`, con columna inicial de unos; varianza residual para inferencia `SSE/(n−k−1)`. La referencia resuelve el sistema por eliminación con pivoteo, no forma una inversa explícita.

**Propuesta para Argentina:** factores subyacente/mercado, CCL, cambios de tasas reales/nominales y spread soberano, sólo si hay series observadas alineadas. Coeficientes tienen unidades que dependen del factor: no mezclar cambios de tasas en pb con decimales. Mínimo matemático n>k+1 y rango completo; operativo mantener holgura respecto de la cantidad de factores. Sin datos de un factor o con factores colineales, no completar con una sensibilidad inventada. La referencia estima coeficientes y varianza residual; no presenta inferencia robusta multifactor.

## 6. VaR, ES, normalidad y drawdown

### 6.1 Signos, horizonte y confianza

Definir la pérdida `L=−V*r`, con V patrimonio actual en moneda de medición. VaR y ES se expresan como pérdida firmada: positivos indican pérdida, negativos una ganancia incluso en el cuantil o cola. No aplicar `abs()` ni truncar a cero en las cuentas. Para el cliente se puede acompañar de “el umbral resultó una ganancia”, conservando el valor original.

`VaR_c=inf{l: P(L<=l)>=c}`. ES es el promedio de la peor fracción `1−c` de pérdidas, con fracción exacta de probabilidad en el borde. No es una pérdida máxima ni un límite de lo que se puede perder. La expresión “pérdida esperada” se reserva aquí a **ES de cola**; la pérdida esperada crediticia de §7.5 es otra medida.

**Defaults:** c=0,95, h=1 sesión, moneda explícita. Sin anualización: VaR/ES siempre deben llevar horizonte. En porcentaje usar V=1; en dinero multiplicar por la exposición. Nivel 99% no es “mejor” si apenas existen observaciones de cola. Fuentes: VAR PDF1, BKM PDF168–170/pp.139–141.

### 6.2 VaR y ES paramétricos normales

Si el retorno agregado se aproxima por normal:

`mu_h=h*mu`; `sigma_h=sqrt(h)*sigma`; `z=Phi^−1(c)`.

`VaR_c=V*(z*sigma_h−mu_h)`.

`ES_c=V*[sigma_h*phi(z)/(1−c)−mu_h]`.

Phi y phi son CDF y densidad normal estándar. Para 95%, z≈1,644853627; no redondear a 1,65 en código. VAR escribe el VaR con cuantil inferior negativo; BKM PDF168 escribe el retorno de cola, también firmado como retorno. Las expresiones anteriores cambian el signo para informar pérdida. La fórmula de ES normal es **derivación por integración de la normal truncada** a partir de esa distribución; no copiar como tal la nota de BKM PDF169, que trabaja con otra transformación de retornos.

**Entradas:** media y sigma a la misma frecuencia, V, c, h. **Propuesta:** μ=0 para riesgo diario prospectivo; para reproducción bibliográfica usar la media exigida por el ejercicio y registrarla. Sigma histórica de simples; EWMA log debe acompañar una simulación/transformación de log a retorno si se busca un precio exacto. No insertar sigma log en el modelo simple sin etiquetarlo aproximación.

**Cartera:** `sigma_p=sqrt(w'Σw)`, `mu_p=w'mu`; usar esas cantidades en la fórmula. No sumar VaR individuales ni suponer independencia. La dependencia de cola real puede exceder la representada por correlaciones constantes.

**Sin dato:** sigma desconocida, parámetros inválidos, pesos/covarianzas incompletos o mínimos no alcanzados. Una sigma cero conocida da fórmula válida; no elimina riesgos no capturados. **Escalado:** `sqrt(h)` sólo para varianza acumulada aditiva bajo no autocorrelación y parámetros estables (BKM PDF184). Con μ≠0 el VaR completo no escala por raíz: la media escala por h. Para simples compuestos es una aproximación; crisis, autocorrelación, volatilidad condicional y opciones la pueden invalidar.

### 6.3 VaR y ES históricos, percentiles y empates

Aplicar cada fila de retornos conjuntos al **mismo** vector de pesos actuales: `r_pt=suma w_i*r_it`; obtener pérdidas `L_t=−V*r_pt`. Ordenar crecientemente `L_(1)...L_(n)`.

**Propuesta principal:** VaR empírico inverso `VaR_c=L_(ceil(n*c))` (índices desde 1). Es el cuantil de la distribución empírica uniforme. Para ES, ordenar pérdidas decrecientes `D_1>=...>=D_n`, definir `q=n*(1−c)`, `k=floor(q)`, `f=q−k`, y calcular:

`ES_c=[suma_(j=1..k) D_j + f*D_(k+1)] / q`.

Si f=0, no agregar otra observación. Si q<1, ES toma la peor pérdida; aun así no supera el mínimo operativo de 10 observaciones. Esta integración fraccional incluye exactamente la masa de cola, incluso con empates. Promediar sólo `L>VaR` puede producir una cola vacía o sesgada; no usarlo como definición computacional.

**Alternativas reproducibles:** `metodo='lineal'` interpola pérdidas con `h=(n−1)*c`, equivalente a un percentil lineal habitual; cambiarlo altera VaR, no la distribución empírica usada para ES. BKM PDF168 usa otra interpolación de retornos ordenados: `a=n*(1−c)`, interpolar entre posiciones floor(a) y ceil(a), desde 1. `var_es_cola_bodie` implementa exactamente esa convención, a partir de la cola publicada sin fabricar los otros 79 retornos. La elección del cuantil debe viajar con el resultado.

**Datos/defaults:** 504 sesiones esperadas; mínimo 250 filas comunes, cobertura ≥95%, cola efectiva ≥10, c=95%. **Unidades:** porcentaje o dinero; no anualizar. **Sin dato:** exposición o filas inválidas, historia insuficiente. No rellenar un activo faltante dentro de una fila con 0. Para h>1, construir `r_(t,h)=producto_(j=0..h−1)(1+r_(t+j))−1` sobre tramos completos. Ventanas solapadas aportan escenarios pero no observaciones independientes; publicar ambas limitaciones. El caso de prueba usa un rebalanceo diario hipotético; un buy-and-hold real exige revaluar cantidades y flujos.

### 6.4 Normalidad y Cornish–Fisher: diagnóstico interno

VAR PDF1 y BKM PDF167–169 presentan asimetría, curtosis y riesgo de cola. Para que la implementación sea inequívoca, la referencia usa momentos descriptivos sin corrección de sesgo:

`m_j=(1/n)*suma(r−media(r))^j`; `S=m_3/m_2^(3/2)`; `K=m_4/m_2²−3` (exceso, normal=0).

`JB=n/6*[S²+K²/4]`; p asintótica para chi² con 2 df `p=exp(−JB/2)`. La fórmula de JB es una **especificación estadística de esta propuesta** para operacionalizar el test nombrado en VAR, que no la desarrolla. La referencia no usa los estimadores ajustados de Excel `SKEW`/`KURT`.

Para `z=Phi^−1(1−c)`:

`z_CF=z+(z²−1)S/6+(z³−3z)K/24−(2z³−5z)S²/36`.

`VaR_CF=−V*[mu+z_CF*s]`.

El resumen VAR menciona Cornish–Fisher sin desarrollar esa expansión; se ofrece como **propuesta de implementación**, no como ecuación transcrita de ese PDF. No se adopta su afirmación de que siempre es más preciso: puede dar cuantiles no monótonos y resultados inestables. No derivar ES por sustitución del cuantil en la fórmula normal.

Entradas: serie regular suficiente; mínimos matemáticos 3 para momentos y 4 para CF en la referencia; **propuesta operativa:** al menos 250 observaciones, uso interno y sin escalado de S/K/JB a otros horizontes. Un test que no rechaza normalidad no la demuestra. Con varianza cero, momentos/CF `sin dato`. No usar este diagnóstico para suprimir el VaR histórico o los escenarios.

### 6.5 Monte Carlo

C01 diap.7 menciona Monte Carlo; FIII PDF4 lo vincula a horizonte; QIA cap.5, PDF274/p.266, desarrolla simulación y su uso explícito en VaR (§13). HRP utiliza Monte Carlo para comparar asignaciones, no como ejemplo de VaR de una cartera argentina.

**Propuesta demostrativa explícita:** factorización semidefinida `Σ=A*A'`, normales independientes `z~N(0,I)`, retorno aditivo simulado `r*=h*mu+sqrt(h)*A*z`, pérdida `L*=−V*w'r*`. Calcular VaR/ES empíricos de esas pérdidas con el método de §6.3. 10.000 simulaciones, semilla 1729. Debería aproximar el VaR/ES normal de §6.2; no añade colas pesadas por sí mismo.

Entradas: medias, matriz completa, pesos y exposición; sin matriz semidefinida positiva, sin parámetros o con huecos: `sin dato`. Horizonte en sesiones, sin anualización. El modelo aditivo puede generar retornos menores que −100%; por eso es una aproximación de P&L y no un motor general de precios. Para bonos variables u opciones, la producción necesitaría simulación de factores y revaluación de flujos/curvas. Este trabajo entrega el comparador normal, no presenta esa revaluación avanzada como ya implementada. No usar simulación para completar una serie histórica faltante. El valor `esperado.json` fija también el generador estándar de Python para regresión; tolerancias estadísticas contra normal se evalúan aparte.

### 6.6 Máxima caída

FIII PDF9: medir caída desde un máximo previo en una trayectoria de riqueza total sin aportes/retiros:

`W_t=W_(t−1)*(1+r_t)`; `H_t=max_(s<=t) W_s`; `dd_t=W_t/H_t−1`; `MDD=−min_t(dd_t)`.

Mostrar caída positiva en %, fechas de pico/valle y fecha de recuperación si existe. Si no recuperó, indicarlo; no inventar fecha futura. La duración de caída es el tiempo entre el pico y recuperación observada, o duración transcurrida si sigue abierta. La referencia devuelve posiciones de la serie, que el adaptador convierte a fechas y días corridos/sesiones con unidad explícita.

**Defaults propuestos:** trayectoria completa disponible; mostrar también la de los últimos 252 retornos completos si existe. No anualiza. Sin trayectoria completa, flujos externos no depurados o riqueza no positiva: `sin dato` de esa función. No encadenar solamente los retornos válidos a través de huecos: ocultaría caídas desconocidas. El MDD de una serie de precio sin dividendos se etiqueta como tal.

## 7. Desempeño ajustado por riesgo

C13 diap.4–9; FIII PDF9; BKM PDF169/p.140 y cap.24. Estas medidas requieren **performance observada** de la inversión o una serie hipotética identificada. Para todo el bloque: mismas fechas, moneda y frecuencia; ventana propuesta 252 retornos, mínimo 126, cobertura ≥95%; para un informe de performance/drawdown se exige además una trayectoria completa y depurar flujos externos. Los ratios no sustituyen datos de posiciones históricas.

Definir `a_t=r_pt−rf_t`, `b_t` objetivo mínimo por período (MAR), `d_t=r_pt−r_Bt`; `N=252`; `sigma_p=sd(r_p)`; `sigma_B=sd(r_B)`; `TE=sd(d)`. Se utiliza desvío del retorno de cartera en Sharpe, como C13, no desvío de a_t; con rf variable son convenciones distintas.

| Medida | Fórmula exacta de reporte anual | Unidad / sin dato |
|---|---|---|
| Sharpe | `S=sqrt(N)*media(a)/sigma_p` | ratio; sigma_p=0 o rf faltante: sin dato |
| Desvío a la baja | `DD=sqrt[(1/n)*suma min(r_pt−b_t,0)²]`; anual `sqrt(N)*DD` | retorno; necesita objetivo conocido |
| Sortino propuesto | `sqrt(N)*media(r_p−b)/DD` | ratio; DD=0: sin dato, no infinito favorable |
| Treynor | `N*media(a)/beta_p` | retorno anual por unidad beta; propuesta: no publicar para beta<=0 o beta sin estimación fiable |
| Jensen | `N*[media(r_p−rf)−beta_p*media(r_M−rf)] = N*alfa` | retorno anual aritmético; exige mismo modelo/benchmark |
| Tracking error | `sqrt(N)*sd(r_p−r_B)` | retorno anual |
| Information ratio contra benchmark | `sqrt(N)*media(r_p−r_B)/TE` | ratio; TE=0: sin dato |
| Appraisal ratio | `sqrt(N)*alfa/sqrt(SSE/(n−1))` | ratio; riesgo residual=0: sin dato |
| Retorno ajustado a riesgo de mercado | `R_aj= N*media(rf)+S*[sqrt(N)*sigma_B]` | retorno anual aritmético; requiere sigma_p y benchmark |
| M² diferencial, convención BKM | `M²=R_aj−N*media(r_B)` | puntos de retorno anual; BKM PDF870–871/pp.841–842 |

En el código `m_cuadrado` guarda R_aj y `m_cuadrado_diferencial` guarda **el M² diferencial de BKM**. Conservar esos nombres del oráculo, pero el informe debe titularlos para evitar confusión. Estos índices usan anualizaciones aritméticas compatibles con sus fórmulas; no elevar Sharpe/Sortino al cuadrado ni componer alfa como rentabilidad segura. La raíz de N es descriptiva bajo independencia/estabilidad y es cuestionable si hay autocorrelación.

**Discrepancia Sortino:** BKM PDF169 define el desvío condicionado a retornos por debajo de rf: `DD_cond=sqrt[suma min(r−b,0)²/n_negativos]`. VAR PDF1 describe además desvío estándar de retornos negativos, que resta una media de ese subconjunto y es otra medida. C13 diap.8 menciona SSD sin fijar denominador; FIII usa MAR. **Propuesta:** DD con denominador n, que incorpora frecuencia de pérdidas, objetivo por defecto rf. Reportar por separado `sortino_condicional_bodie` sólo para reproducir esa convención, sin mezclar rankings. Si no hay negativos, ambos ratios quedan sin dato por denominador nulo; DD no condicionado sí vale 0.

**Discrepancia information ratio:** C13 diap.7 e IM llaman así a `alfa/sigma_residual`; BKM cap.24 también usa ese nombre. FIII PDF9 distingue information ratio contra benchmark de appraisal ratio. **Propuesta:** usar esta última distinción en la interfaz; mostrar el antiguo nombre de cátedra en la documentación de equivalencias, nunca dos fórmulas bajo una misma etiqueta.

### 7.1 Tasa libre de riesgo — propuesta para que Felipe elija

La bibliografía utiliza una rf abstracta o Treasury bills, pero no prescribe una tasa local de caución o una LECAP como libre de todo riesgo. No hay una tasa numérica universal predeterminada en esta entrega: debe seleccionarse una **serie con fecha, moneda, plazo y convención**. Si falta, Sharpe/Treynor/Jensen quedan `sin dato`; no adoptar 0 por omisión. El cero de la referencia en algunos cálculos sólo significa que ya se suministraron excesos o un escenario μ=0 declarado.

- En USD: propuesta de referencia, Treasury bill de corto plazo de EE.UU., comparable al horizonte y convertido a tasa efectiva diaria. No usar AL30/ON USD: incluyen crédito. Si no hay acceso autorizado a esa serie, Felipe puede cargarla como input explícito; no se buscó una fuente con credenciales.
- En ARS: propuesta práctica, caución colocadora corta con datos reales y plazo identificado, rotulada **proxy local**, con riesgo operativo/contraparte y de reinversión. Como sensibilidad alternativa, letra soberana corta elegida por Felipe, identificando riesgo soberano. No llamarla tasa libre de riesgo estricta ni extrapolar una TIR de largo plazo.
- En unidad USD por CCL/MEP: usar referencia USD. Convertir retornos ARS a esa unidad antes de restarla; no restar una tasa ARS de un retorno en USD.

Conversión: si se conoce tasa efectiva anual E, `rf_periodica=(1+E)^(1/N)−1`. Si la fuente informa tasa nominal j capitalizable m veces, `E=(1+j/m)^m−1`; si es cupón simple con base contractual, usar días/base y documentar ese devengamiento. No dividir una efectiva anual por 252 como igualdad exacta. Para OLS log usar `ln(1+rf_simple)`. Fuentes de capitalización: BKM PDF151–153 y QIA cap.1; elección local **propuesta**.

## 8. Renta fija: flujos, duration, convexidad y factores

### 8.1 Convenciones antes de calcular

Datos obligatorios: especie y moneda de denominación/pago, fecha de valuación y liquidación, precio limpio/sucio, interés corrido, nominal residual, amortizaciones, cupones, fechas, frecuencia, base de días, TIR y convención de capitalización, indexación y opciones. La calculadora IAMC/BYMA es una fuente disponible según el encargo; guardar la captura/exportación y su fecha. No se presume haber consultado sus datos en vivo ni que su campo `duration` sea Macaulay o modificada: comprobar el rótulo/documentación.

Una TIR no permite recuperar por sí sola todos los flujos. No convertir “años hasta vencimiento” en duration para un bono con cupones. Con flujos desconocidos o cláusula variable no documentada: duration/convexidad de flujos fijos `sin dato`. Si la calculadora entrega una duration sin flujos, puede mostrarse como dato externo **con tipo y convención confirmados**, sin inventar la convexidad.

### 8.2 Fórmulas para flujos deterministas, incluso amortizables

BKM PDF549–550/pp.520–521 y PDF555–556/pp.526–527; FI PDF96–109. Sea t_j el tiempo en años **según la convención de valuación**, CF_j el flujo, m cupones/capitalizaciones por año y y una **TIR nominal anual convertible m veces**:

`PV_j=CF_j/(1+y/m)^(m*t_j)`; `P_sucio=suma PV_j`.

`D_Mac=suma t_j*PV_j/P_sucio`.

`D_mod=D_Mac/(1+y/m)`.

`C = [suma t_j*(t_j+1/m)*PV_j] / [P_sucio*(1+y/m)²]`.

`DV01=P_posicion*D_mod*0,0001`, magnitud de la pérdida aproximada por suba de 1 pb.

`DeltaP/P ≈ −D_mod*Delta_y + 0,5*C*(Delta_y)²`.

**Unidades:** P moneda por el nominal de los flujos; D años; C años²; DV01 moneda de la posición por pb; Delta_y decimal anual (100 pb=0,01; 200 pb=0,02). No anualizar D con sqrt(252). Si se empieza con períodos, dividir D por m y C por m² para expresarlos en años/años². BKM ejemplo16.1 trabaja D_mod en semestres: no confundir su 3,591 períodos con 3,591 años; equivale a aproximadamente 1,79546 años.

**Defaults:** no imponer m=2 a todos los activos. La función matemática tiene m=2 como ejemplo de los bonos semestrales de BKM; el adaptador **debe** enviar el m y la convención de cada instrumento. Para una letra descuento con un flujo, Macaulay es su plazo, pero D_mod depende de la tasa y su capitalización. Si la TIR es efectiva anual, usar m=1 en el descuento correspondiente o convertirla a la nominal compatible. Un contrato con descuento simple puede requerir otro precio; no aplicar esta fórmula como si toda tasa publicada fuera compuesta.

**Sin dato:** precio/nominal no reconciliados, y/m<=−1, fecha de flujo vencida no depurada, flujos faltantes o m inválido. En la referencia t>0 y CF>=0. Día de cupón, interés corrido y ex cupón requieren una definición de liquidación antes de enviar los flujos. La función asume los tiempos ya calculados; no trae un motor de calendarios/day count. Los tiempos fraccionales admiten descuento compuesto fraccional; instrumentos con reglas diferentes necesitan su precio contractual exacto.

### 8.3 Diferencias finitas y duración de curva

`D_ef=(P_baja−P_suba)/(2*P_0*delta)`.

`C_ef=(P_baja+P_suba−2*P_0)/(P_0*delta²)`.

`DV01_central=(P_baja−P_suba)/(2*delta)*0,0001`.

Si se desplaza la **TIR manteniendo flujos fijos**, se aproxima duration modificada/convexidad. Si se desplaza la **curva de referencia y se revalúan flujos/opciones según el modelo**, se mide duration/convexidad efectiva (FI PDF111–114). No son intercambiables. Datos: P0 y dos precios modelados con todos los demás supuestos definidos; default numérico delta=1 pb, comparador a 10 pb (**propuesta**). Un precio modelado de escenario no es una observación histórica inventada; debe rotularse como tal. Sin motor de revaluación o datos de opciones: sensibilidad efectiva `sin dato`.

Key rate duration: aplicar la misma fórmula de D_ef a precios obtenidos perturbando un solo nodo de curva, manteniendo los demás. **Propuesta:** nodos 1, 2, 5 y 10 años si hay curva y flujos; no extrapolar nodos inexistentes. `P_curva=suma CF_j/(1+z_j)^t_j` usa tasas spot **efectivas anuales**, a diferencia de y nominal de §8.2. La referencia `precio_curva` permite precios base/choque con tasas por flujo suministradas; no estima ni interpola una curva faltante. Las key rates no se anualizan; se expresan en años por nodo. Fuente conceptual: FI PDF114–115.

### 8.4 Escenarios y agregación

**Propuesta:** revaluación exacta de cada flujo fijo bajo cambios de TIR −200, −100, −50, +50, +100 y +200 pb. Agregar +10 pb para reproducir BKM PDF556. Mostrar precio inicial, exacto de escenario, P&L exacto y aproximación D+C, con su diferencia. La referencia entrega los seis escenarios principales; el +10 se obtiene pasando `cambios=(0.001,)`. FI PDF104–106 aporta ±50 pb; BKM ejemplo16.2 aporta +200/+10 pb. Un choque es escenario, no una probabilidad ni una predicción.

`D_port=suma (V_i/V_bonos)*D_i`; `C_port=suma (V_i/V_bonos)*C_i`; `DV01_total=suma V_i*D_i*0,0001` para el mismo tipo de shock. **Entradas:** valores sucios actuales, sensibilidades homogéneas y moneda común. **Unidades:** años, años² y moneda/pb; no anualizar. Identificar si el denominador es sólo bonos o patrimonio total. Para shock paralelo, `P&L≈suma V_i*[−D_i*dy+0,5*C_i*dy²]`; la revaluación exacta suma P&L individuales. Sin valor/sensibilidad de un bono, mostrar cobertura del escenario y excluirlo nominalmente, no atribuirle DV01=0. No promediar D de tasas reales CER y nominales ARS bajo un shock único sin declarar qué curvas se movieron.

Para curvas no paralelas o spreads que reaccionan en forma diferente, el promedio de D es insuficiente (FI PDF107–109). **Propuesta:** además de paralelos, escenarios de aplanamiento/empinamiento con choques por nodo definidos por Felipe cuando se disponga de curvas. No calcularlos desde una única TIR.

### 8.5 Crédito, spread y reinversión

FI PDF118–120; BKM cap.14–16:

- **Pérdida esperada crediticia:** `EL=EAD*PD*(1−recupero)`. EAD en dinero; PD y recupero entre 0 y 1; horizonte de PD explícito, propuesta un año cuando hay estimación anual confiable. Sin PD/recupero observados o estimados con un modelo validado: EL `sin dato`. No deducir PD exacta de la TIR ni dividir PD anual por 252 como igualdad. La fórmula no se confunde con ES de mercado.
- **Spread simple:** `spread_pb=(y_bono−y_referencia)*10.000`, sólo si moneda, plazo y convenciones son comparables. Es un diferencial de tasas, no una varianza anualizable. FI PDF120 aproxima spread de crédito por PD*LGD en un ejemplo; no es identidad para bonos argentinos, donde también influyen liquidez, impuestos, legislación y riesgo de transferencia.
- **Sensibilidad al spread:** `DeltaP/P≈−D_spread*Delta_spread`, derivada parcial de precio respecto del spread con curva base fija. Puede calcularse con `sensibilidad_efectiva` revaluando ±delta de spread. Igualar D_spread con D_mod sólo como aproximación declarada para flujos fijos y traslación uniforme del rendimiento. **Propuesta:** escenarios de ampliación +100/+300/+500 pb cuando se disponga de curva/spread; no sumar esos choques a la volatilidad como si fueran desvíos estadísticos.
- **Default/restructuración:** además de spread, mostrar un recupero de escenario y `perdida=EAD*(1−recupero)`; corresponde a `perdida_crediticia` con PD=1. **Propuesta:** recuperos hipotéticos de 25%, 50%, 75%, claramente no estimaciones. No computar una pérdida esperada mezclando escenarios sin probabilidades.
- **Reinversión:** cobrar cupones antes del horizonte obliga a decidir a qué tasa se reinvierten. Para una tasa efectiva anual g y pagos anteriores a H: `FV_H=suma CF_j*(1+g)^(H−t_j)`. Un precio de venta de un bono aún no vencido en H se debe añadir como flujo terminal observado/modelado identificado; no está implícito en los cupones. Fuente FI PDF88–90. Sin tasa/horizonte/flujos no hay medida; no anualizar FV. La TIR de compra sólo se realiza manteniendo los supuestos adecuados sobre pagos/reinversión.

Macaulay vincula riesgo de precio y de reinversión: inmunizar requiere valor presente de activos/pasivos y duraciones compatibles, con rebalanceo y supuestos de curva. No basta “mantener hasta vencimiento” para eliminar inflación, default o costo de oportunidad (BKM PDF568–571, cap.16).

### 8.6 Tratamiento por familia argentina — propuesta salvo conceptos generales citados

| Familia | Qué medir y qué factor falta si sólo se calcula duration |
|---|---|
| Soberano USD fijo, AL29/AL30/AE38 | flujos contractuales en USD, amortización y residual; D/C/DV01 de USD; escenarios de tasas USD, spread soberano, crédito y FX de la moneda de reporte. Una especie negociada en ARS no convierte sus pagos a tasa fija en ARS |
| LECAP/BONCAP fija | descuento/capitalización y flujos según contrato de la especie; curva nominal ARS, refinanciación e inflación. No asumir que toda letra tiene cupón semestral o la misma tasa nominal |
| CER, TZXM7/X29E7 | capital actualizado `N_t=N_base*CER_referencia(t)/CER_base`; flujos en unidades CER y tasa **real**; D_real, escenario de tasa real, trayectoria CER y rezago de referencia. CER indexa capital; no es equivalente a cupón flotante que resetea una tasa corta. La duration real puede seguir siendo larga |
| Dólar linked, TZV28 | capital/pagos sujetos al tipo de cambio oficial **contractual** y su rezago; sensibilidad al rendimiento de la estructura y factor oficial. No equivale a poseer dólar billete, MEP o CCL. En unidad CCL, la brecha oficial/CCL importa |
| TAMAR, BAM27 u ON TAMAR | cupón con tasa de referencia más margen, período observado, promedio y base de días **según prospecto**. `cupon=capital*(tasa_nominal+margen)*dias/base` sólo si esa es la cláusula de interés simple. Si capitaliza, tiene pisos/techos u otra regla, usar la contractual. Sensibilidades separadas: tasa proyectada de cupones, descuento y spread |
| ON fija/variable | esquema anterior según cupón, más crédito del emisor, ley, garantías, opciones de rescate y liquidez. No inferir condición TAMAR por el nombre sin documentación |
| Efectivo/caución | efectivo de misma moneda y sin rendimiento tiene retorno nominal local 0 **conocido por contrato/contabilidad**, no por rellenar un precio faltante; moneda extranjera conserva FX. Caución devenga según contrato y horizonte, con riesgo de reinversión/operativo y disponibilidad; no extrapolar una tasa actual a una historia inexistente |

FI PDF100 explica que la duration de un flotante cercano a par puede aproximarse por el tiempo hasta el próximo reset. **No aplicar automáticamente ese resultado a CER ni a todo instrumento TAMAR:** supone cupones que resetean a mercado, sin topes relevantes ni variación fuerte de spread. Para variables, proyectar flujos bajo escenarios de referencia y descontar con la curva elegida, recalculando índices y rezagos. Sin cláusulas, fixing histórico y proyecciones identificadas, la sensibilidad de índice queda `sin dato`, aunque IAMC muestre una duration. Este documento no afirma conocer los prospectos vigentes de esos tickers: los nombres provienen del encargo.

## 9. Decisiones explícitas sobre Argentina

La bibliografía desarrolla riesgo de monedas, inflación y factores en general (C09 diap.3–6; FIII PDF3; BKM cap.5), pero **no resuelve las convenciones de CCL/MEP, ratios CEDEAR, CER ni TAMAR argentinos**. Todo lo específico de esta sección es **propuesta, no bibliografía**.

### 9.1 Moneda de medición

Adoptar USD por CCL como vista principal cuando el objetivo patrimonial sea dólar transferible/inversión internacional; agregar ARS para obligaciones y consumos locales. Si el objetivo del cliente es dólar local, Felipe puede elegir MEP como principal. No alternar MEP y CCL entre activos para obtener precios “más convenientes”. No llamar a esta unidad “USD billete libre de fricciones”: es valuación convertida al tipo elegido.

Para tipo de cambio `X_t` ARS por USD, `V_USD,t=V_ARS,t/X_t`; retorno convertido `1+r_USD=(1+r_ARS)/(1+r_X)`, cuando los valores/pagos se convierten correctamente en cada fecha. Es un cálculo por fecha, no dividir la volatilidad ARS por el CCL de hoy. Pesos de cartera y escenarios monetarios también se calculan después de convertir todas las valuaciones. Si existe cotización directa de una especie en USD con liquidez y plazo comparable, elegir una sola política de valuación por instrumento y registrar diferencias con la conversión, sin contar las dos especies como posiciones económicas independientes.

Con CCL/MEP faltante, no hay retorno convertido para ese intervalo; puede seguir existiendo retorno ARS. No derivar CCL desde el mismo CEDEAR cuya beta o volatilidad cambiaria se intenta explicar sin advertir circularidad. Priorizar una serie cambiaria independiente y documentada que Felipe suministre si no está en los conectores disponibles.

### 9.2 CEDEAR: precio, ratio y riesgo cambiario

Identidad teórica aproximada, con ratio definido como **cantidad de certificados por acción subyacente**:

`P_CEDEAR,ARS≈P_subyacente,USD*CCL/ratio`.

`1+r_CEDEAR,ARS≈(1+r_subyacente,USD)*(1+r_CCL)*(ratio_anterior/ratio_actual)`.

Con ratio constante: `r_CEDEAR≈r_suby+r_CCL+r_suby*r_CCL`; en logs, `l_CEDEAR≈l_suby+l_CCL−Delta ln(ratio)`. Cotizaciones locales pueden apartarse por liquidez, horarios y costos; igualdad teórica no autoriza fabricar el precio local ausente. El factor de ratio representa una equivalencia por certificado: un cambio corporativo debe reconciliar también cantidades y derechos para calcular retorno económico, evitando un salto artificial.

Medir, si hay datos, riesgo de subyacente y CCL conjuntamente; no sumar sus sigmas. La suma en logs permite aplicar `varianza_factores([1,1],Cov_factores,0)` como descomposición teórica; los residuos de negociación local se estiman sólo con precios observados. Una cartera medida en USD por CCL elimina la conversión mecánica CCL de esa identidad, pero no todos los riesgos económicos o de negociación.

### 9.3 Inflación, CER, liquidez y país

- **Retorno real:** `r_real=(1+r_nominal)/(1+inflacion_del_intervalo)−1`. En ARS responde al poder de compra local. No restar inflación anual a retorno diario. IPC mensual publicado no proporciona una trayectoria diaria observada; mostrar retorno real mensual con extremos y disponibilidad compatibles. No usar datos publicados después del corte como si se conocieran antes. CER diario observado sigue su propia regla/rezago, no se reemplaza con IPC contemporáneo.
- **CER:** además de tasa real y volatilidad de mercado, estrés del índice contractual y su rezago. `capital_ajustado` sólo realiza una indexación a partir de dos índices suministrados; no proyecta inflación ni determina qué fixing corresponde a un bono.
- **Liquidez:** monto diario negociado en moneda comparable; no confundir volumen en títulos con monto monetario. `ADV20=media(monto_sesion)` sobre 20 sesiones confirmadas; sesiones conocidas sin negocio aportan 0 volumen, ausencias desconocidas no. `dias_liquidacion=valor_posicion/(participacion*ADV20)`, participación propuesta 10%. Unidad: sesiones teóricas; no anualizar. Informar fracción de sesiones sin negocio; si ADV=0, plazo indefinido/no liquidable bajo ese supuesto. Sin volumen o con ventana incompleta: sin dato de esa medida, no liquidez “alta”. Si hay bid/ask, mostrar spread observado, sin inferirlo de OHLC. La estimación de salida supone mercado estable, no garantiza ejecución y no reduce la sigma estimada para compensar iliquidez.
- **Riesgo país:** exposición por emisor soberano/sector y sensibilidad de spreads cuando existan curvas; no sumar un número de riesgo país en pb a una volatilidad en %. Un indicador externo de riesgo país puede ser un factor con serie temporal, fecha y metodología; sin ese dato, informar exposición soberana y escenarios identificados, no generar un indicador. País también afecta acciones/ON: una lista de bonos no representa toda la exposición argentina. Crédito soberano conceptual: FI PDF119–120; aplicación y choques locales: propuesta.

## 10. Entradas requeridas y conectores disponibles

### 10.1 Inventario por tipo de activo

Todos requieren identificador económico/especie, posición, precio actual con fecha/moneda/base, moneda de denominación/pago, plazo de liquidación y fuente. Un faltante de valuación actual impide calcular patrimonio total y pesos totales fiables; no equivale a activo de peso cero.

| Tipo | Serie para riesgo de mercado | Inputs adicionales de factores/valuación | Qué informar si falta historia |
|---|---|---|---|
| CEDEAR | cierres locales negociados y eventos/pagos, calendario local | ratio y cambios fechados, subyacente USD, índice USD, CCL; volumen y moneda | riesgo local si alcanza; factores ausentes sin dato; no sintetizar una historia local con la identidad |
| Acción argentina | cierre ajustado o precios+dividendos/splits, volumen | Merval, CCL/MEP si se mide en USD, rf compatible | mantener peso en concentración; excluir de matriz con motivo |
| Soberano USD | precio sucio homogéneo, cupones/amortizaciones, especies/plazos | flujo futuro, TIR, curva USD y spread, residual; FX | sin historia: D/C/escenarios pueden existir si el contrato/valuación están completos |
| Fija ARS/LECAP/BONCAP | precio sucio/valor comparable y pagos | convención contractual, cronograma, capitalización, curva nominal, IPC para real | sin precios: riesgo histórico sin dato; escenarios de tasa por contrato si completos |
| CER | precio/pagos ajustados, CER observado contractual | base de indexación, rezagos, flujos reales, curva real, IPC mensual | separar ausencia de historia de ausencia de flujos/índice |
| Dólar linked | precio/pagos y tipo oficial de referencia del contrato | fechas/fixing/base, curva de descuento, CCL/MEP de reporte | sin factor oficial no estimar su sensibilidad por reemplazo con CCL |
| TAMAR soberano/ON | precio/pagos y fixing TAMAR observado | regla de cupón, margen, promedio/rezago, topes/pisos, proyección explícita y curva de descuento/spread | sensibilidad incompleta si falta fixing/contrato; no asignar D=tiempo al reset por defecto |
| ON fija | precio sucio, volumen, pagos y eventos | prospecto, flujos, crédito, garantías, opciones/ley, curva/spread | IAMC/prospecto o carga explícita si disponibles; sin ellos, sin dato |
| Efectivo ARS/USD | saldo conocido y FX cuando corresponda; no necesita precio bursátil diario de 1 | moneda, restricciones y rendimiento efectivo | cero riesgo nominal sólo en su propia moneda y sobre saldo cierto; FX sigue requiriendo datos |
| Caución | contrato, devengamiento y movimientos | tasa/base/plazo, renovaciones observadas, disponibilidad; FX si aplica | no usar una sucesión de renovaciones hipotéticas como historia real |

TIR, duration, precio y flujo de IAMC/BYMA se conservan como snapshot con hora, fecha de liquidación, base de nominal y tipo de duration. Reconciliar precio sucio calculado con calculadora antes de usar sensibilidades. Si no coincide, mostrar diferencia y convenciones pendientes; no ajustar flujos para forzar coincidencia.

### 10.2 data912: qué se verificó y qué queda pendiente

El encargo identifica estos endpoints y limita su cobertura:

- [Histórico GGAL, acciones](https://data912.com/historical/stocks/GGAL).
- [Histórico SPY, CEDEAR](https://data912.com/historical/cedears/SPY).
- [Histórico AL30, bonos](https://data912.com/historical/bonds/AL30).

Las consultas directas realizadas el 18/11/2026 devolvieron **HTTP 403 Forbidden en los tres**, y también en un ticker inexistente de control. El navegador de búsqueda reconoció AL30 como `application/json` pero no devolvió su cuerpo. **No se pudo verificar el esquema real, nombres de campos, primera/última fecha ni longitud.** No hay una serie de mercado descargada y no se afirma que esos endpoints estén vacíos. Evidencia de las cuatro consultas: `fuentes/data912_resumen.json`; script `consultar_data.py`. No se necesitaron credenciales.

Según información aportada por el encargo, no hay letras ni ON en ese histórico y algunos CEDEARs ausentes responden HTTP 200 con un objeto `{"Error": ...}`. Esto es **dato del encargo, no constatación de las respuestas de esta ejecución**.

**Contrato de adaptación propuesto (no descripción verificada del JSON):**

1. Registrar URL, instante UTC, HTTP, cuerpo bruto y versión de parser. Manejar timeout y 403/429/5xx como falta de fuente; no convertir error en serie vacía válida.
2. Validar el JSON: un objeto de error aunque HTTP=200 es `sin dato`; una lista vacía tampoco es una historia de retornos cero. Admitir solamente la estructura identificada realmente; no adivinar claves ni la unidad de `volume`.
3. Normalizar internamente a `fecha,precio,moneda,ajustado,volumen_titulos,monto_operado,estado_precio,fuente`, permitiendo campos ausentes explícitos. Esa es la estructura de la herramienta propuesta, no un esquema atribuido a data912.
4. Medir cantidad de precios válidos, retornos consecutivos, primera/última fecha, cobertura por ventana, duplicados y antigüedad; validar que cierre sea ajustado o incorporar eventos. Precio y pagos en la misma unidad de nominal.
5. Si no hay calendario confirmado o metadatos de ajuste, no afirmar completitud ni retorno total. Para índices, tipos de cambio, rf y prospectos que estas rutas no proporcionen, pedir insumos de otra fuente autorizada o carga explícita; sin ellos, las medidas correspondientes quedan sin dato.

## 11. Algoritmos y salida al cliente

### 11.1 Análisis de un activo

1. Identificar instrumento, familia, moneda, contrato y posición. Validar precio actual/antigüedad; si falta, valor y peso actuales sin dato.
2. Elegir unidad de medición común y fecha de corte; conservar también moneda de denominación y de pago. Convertir cada valuación y cada flujo con el FX de su fecha, si existe.
3. Descargar/cargar precios, pagos, eventos, volumen y calendarios; validar respuesta de proveedor. Conservar trazabilidad y no modificar originales.
4. Reconstruir retorno total de cada par de sesiones consecutivas. Marcar faltantes y anomalías sin borrarlos silenciosamente; no winsorizar caídas reales para que baje el riesgo.
5. Cortar ventanas por sesiones esperadas y contar retornos válidos. Si no alcanza mínimo/cobertura, emitir cada métrica afectada como sin dato con n y motivo. Retener valoración y concentración si son conocidas.
6. Calcular histórico simple y, como comparador de cátedra, log; anualizar explícitamente. EWMA sobre el tramo válido consecutivo, semilla y calentamiento registrados.
7. Elegir índice/rf/factores coherentes; alinear intervalos y calcular beta/alfa/R², componentes y tests. Si falta benchmark, no cancelar volatilidad propia.
8. Calcular VaR/ES normales e históricos según ventanas y colas; mostrar horizonte, confianza, μ, método de cuantil y muestra. Agregar drawdown sólo sobre trayectoria completa. CF/normalidad quedan internos.
9. Calcular desempeño sólo con serie de performance correcta y rf/benchmark disponibles; no presentar la volatilidad como rendimiento ni el alfa estimado como promesa.
10. Para renta fija, cargar flujos/convenciones y reconciliar precio; D/C/DV01 y escenarios. Separar curvas, índice, spread y crédito. Sin historia de precios puede haber sensibilidad contractual; no convertirla en volatilidad histórica.
11. Medir liquidez si hay monto/volumen verificables. Devolver valores, unidades, parámetros, período, cobertura, fuentes, fecha de cálculo y limitaciones por métrica.

### 11.2 Análisis de cartera

1. Valuar posiciones completas en moneda/fecha común, reconciliar cantidades/residuales y calcular pesos. Si falta valor actual de alguna posición, **no existe un porcentaje total fiable**: informar patrimonio conocido y valor pendiente, sin asignarle cero.
2. Mostrar concentración de toda la cartera valuada, incluso activos sin historia.
3. Preparar series homogéneas por activo. Efectivo constante sólo si se conoce contablemente y está en la moneda de medición; USD en ARS y ARS en USD requieren su FX.
4. Seleccionar universo que cumple mínimos y después intersección completa de intervalos; publicar n común y cobertura. No calcular cada par con una muestra distinta.
5. Si algún activo queda fuera por falta de historia, listar nombre, motivo, valor y **peso original**. Si todo el resto pasa, `cobertura=sum w_incluidos`. Si falla la intersección, no excluir activos arbitrariamente hasta “hacer funcionar” el modelo; registrar el problema y, si se presenta un subconjunto, identificar exactamente el criterio/selección.
6. **No informar un riesgo numérico de cartera total con activos sin historia.** Puede mostrarse un análisis parcial con pesos originales (suma menor que 1), que es riesgo/P&L de posiciones cubiertas, sin atribuir cero riesgo económico a las faltantes. Y/o un subconjunto normalizado `w_cond=w_i/cobertura`, rotulado “cartera cubierta normalizada”, distinto del total. Mostrar los dos denominadores. No repartir su riesgo a la parte excluida.
7. Ejemplo: bono faltante de 15%, cobertura 85%; pesos cubiertos originales se conservan. La normalizada divide cada peso incluido por 0,85. “Volatilidad del 85% cubierto” no significa que la cartera total tenga esa volatilidad ni que la normalizada esté acotando el riesgo total: las covarianzas con el excluido son desconocidas.
8. Con cobertura completa y muestra suficiente: estimar matriz, validar PSD, calcular sigma, contribuciones y diversificación. No invertir Σ para medir una cartera ya dada.
9. VaR/ES normal usando w'Σw; histórico aplicando pesos actuales a cada fila común. Construir drawdown hipotético sólo si hay tramo completo. Regresar beta de cartera contra benchmark coherente; no mezclar betas de distintos mercados.
10. Agregar D/C/DV01 y escenarios por curva/moneda/índice con cobertura propia de renta fija, independiente de la cobertura de retornos. Sumar P&L de escenarios simultáneos sin duplicar el mismo shock como tasa y spread a la vez.
11. Generar reporte de cliente y vista del asesor. Mantener un resultado estructurado: `valor`, `unidad`, `moneda`, `horizonte`, `confianza`, `ventana`, `n`, `cobertura_temporal`, `cobertura_patrimonial`, `metodo`, `parametros`, `fuente`, `estado`, `motivo`. `null` significa sin dato; 0 significa un cero conocido.

### 11.3 Qué mostrar

**Propuesta de informe al cliente**, pocas medidas con explicación en lenguaje común:

- Moneda, fecha, valor y cobertura; advertencia principal si quedó algo sin medir.
- Volatilidad anual histórica: “variación habitual estimada, hacia arriba y abajo”.
- Pérdida de referencia VaR 95% a una sesión y ES correspondiente: “umbral que se supera aproximadamente en el 5% de escenarios del modelo y promedio de esa cola”; el modelo no garantiza frecuencias futuras ni pérdida máxima.
- Máxima caída observada de una trayectoria identificada y período; no mostrar drawdown ficticio como experiencia del cliente.
- Concentración por principales posiciones/emisores y monedas, más un escenario entendible de tasas/FX si es relevante. La cantidad de líneas puede adaptarse; no ocultar la exclusión por historia insuficiente.

**Vista interna del asesor:** simple/log, EWMA, matrices y n común, contribuciones firmadas, DR/HHI, beta/alfa/R²/tests, factores, todas las medidas de desempeño con convención de rf/MAR, VaR normal/histórico/CF/MC y diagnósticos, duración real/nominal/efectiva, convexidad, DV01 por curva, spread/default/reinversión, liquidez y trazabilidad. Sharpe puede aparecer al cliente en una comparación homogénea; Treynor y alfa no se proponen como titulares. C01 diap.19–21 y C13 orientan la comunicación/perfil; la selección concreta de medidas es propuesta.

## 12. Comprobación reproducible y caso ficticio

### 12.1 Archivos y ejecución

- `verificacion/riesgo_ref.py`: funciones matemáticas puras, nombres en español, Python 3.9, sólo biblioteca estándar. No conecta fuentes, no cambia datos y no implementa `cartera`.
- `verificacion/leer_excel.py`: lector de celdas/cachés con `zipfile` y XML; no requiere Excel ni `openpyxl`, no recalcula ni modifica los libros.
- `verificacion/comprobar.py`: contrasta fuentes, realiza controles aritméticos independientes y compara el caso contra su JSON guardado. Una diferencia bibliográfica conocida se imprime como discrepancia; no se fuerza a coincidir.
- `verificacion/caso.py`: calcula todos los resultados del caso a partir de los CSV y parámetros.
- `verificacion/generar_caso.py`: regenera explícitamente los datos ficticios y `esperado.json`. **No ejecutarlo como paso rutinario de aceptación:** sobrescribir el oráculo con la implementación bajo prueba ocultaría errores.
- `verificacion/caso_ficticio/precios.csv`, `factores.csv`, `parametros.json`, `esperado.json`: entradas y resultados. `COMPROBACION_MANUAL.md` explica cálculos independientes.
- `verificacion/salida.txt`: salida real de esta ejecución.

Desde esta carpeta:

```sh
python3 -B entrega/verificacion/comprobar.py
```

La biblioteca no exige `numpy`, `openpyxl` ni SciPy. Las funciones lanzan `ValueError` en entradas fuera de dominio; correlación y algunos ratios devuelven `None` cuando el denominador es cero. El consumidor transforma esos casos en `sin dato` **con motivo**. Antes de llamar a las funciones tiene que aplicar los mínimos de muestra, calendarios y etiquetas de este documento: una función algebraica no decide por sí sola si una historia es publicable.

### 12.2 Correspondencia entre fórmulas y funciones

| Bloque de la metodología | Funciones de `riesgo_ref.py` |
|---|---|
| HPR, log, agregación y calendarios | `retorno_simple`, `retorno_logaritmico`, `retornos`, `retornos_calendario`, `riqueza`, `retorno_anual_compuesto` |
| Estimación y matrices | `media`, `varianza`, `volatilidad`, `covarianza`, `correlacion`, `matriz_covarianzas`, `matriz_correlaciones`, `cholesky_semidefinida` |
| EWMA | `ewma` |
| Riesgo de cartera y cobertura | `producto_matriz_vector`, `retornos_cartera`, `riesgo_cartera`, `concentracion`, `cobertura` |
| Regresión, CAPM y factores | `modelo_indice`, `retorno_capm`, `beta_cartera`, `p_student_bilateral`, `cuantil_student`, `modelo_factores`, `varianza_factores`, `resolver_lineal` |
| Cola, diagnóstico y horizonte | `var_es_normal`, `var_es_historico`, `cuantiles_perdidas`, `var_es_cola_bodie`, `momentos`, `var_cornish_fisher`, `retornos_horizonte`, `monte_carlo` |
| Caídas y desempeño | `drawdown`, `desempeno`, `tasa_periodica`, `tasa_nominal_a_efectiva` |
| Bonos y escenarios | `flujos_fijos`, `bono`, `cambio_precio`, `escenarios_bono`, `sensibilidad_efectiva`, `sensibilidades_cartera`, `precio_curva` |
| Crédito, spread y reinversión | `perdida_crediticia`, `spread_pb`, `valor_reinvertido` |
| Moneda, índices y liquidez | `precio_cedear`, `retorno_factores`, `convertir_moneda`, `retorno_real`, `capital_ajustado`, `cupon_variable`, `liquidez` |

El cálculo de key rates y duration de spread usa `precio_curva`/precios suministrados y `sensibilidad_efectiva`: se deben enviar curvas perturbadas por nodo/factor, no sólo sus nombres. El motor contractual de CER/TAMAR, day count, flujos reales de clientes y selección de benchmarks es trabajo futuro de la herramienta; aquí se fijan los inputs y las operaciones a realizar, sin afirmar que los conectores o contratos ya estén implementados.

### 12.3 Resultados y diferencias de bibliografía

1. **VOL histórico:** `MA!C3:C243` y las celdas destinadas a las volatilidades no están completas; `MA!J1` guarda 0 observaciones. De sus precios sí se reconstruyen 241 logs y volatilidad anual 69,8152632892%. En `GARCH (1,1) SP500`, `L21` tiene `STDEV.S(D3:D1280)*SQRT(252)` pero D está vacío y la caché guarda `#DIV/0!`. Recalculando sobre los logs observables `AH3:AH1280`, el histórico es 24,6811507296% anual, verificado también con `statistics.stdev`. **No hay una volatilidad histórica válida guardada con la cual afirmar coincidencia.** No se editó ni “arregló” el original para crear esa coincidencia.
2. **VOL EWMA:** los 1.278 valores previos de AJ se reproducen, diferencia máxima 4,34e−19. `AL1280` es 20,7206403605% anual; pronóstico posterior al último retorno: varianza 0,000161127754821. Usar este pronóstico como si fuera `AJ1280` produciría una diferencia por índice temporal, no por λ.
3. **Beta:** BET Alcoa beta 1,902798383662, diferencia alrededor de 7e−16; alfa mensual 0,000370710470. IC95 beta [1,501620001; 2,303976766], t contra 1=4,504597925; p≈0,000032699. Se reproducen también intercepto y pendiente de la segunda pasada CAPM.
4. **Markowitz:** MARK `Caso 0_con short sales!B18`, sigma 0,319075946659; varianza 0,101809459736. Es una matriz/ejercicio con frecuencia propia, **no** una volatilidad diaria para multiplicar por sqrt(252). La función usa `periodos=1` en ese cotejo.
5. **VaR BKM:** con la cola impresa y n=84, VaR de pérdida 25,558%, consistente por redondeo con 25,56%. **ES BKM no coincide:** `(45,64+41,03+33,49+25,69+0,2*25,03)/4,2 = 35,9180952381%`, frente a 35,94% en PDF169/p.140. Diferencia −0,0219047619 puntos porcentuales (−2,19047619 pb). Se inspeccionaron visualmente las páginas PDF168–169 para descartar un error de extracción en esos cinco valores. No se conoce la causa en los datos originales del autor: la cuenta con los datos impresos es inconsistente con el resultado publicado.
6. **Bonos BKM:** precio del bono 8%, 2 años, semestral, TIR10%=964,540494958 por VN1000; Macaulay=1,88522950687 años, contra 964,540 y 1,8852 publicados. Bono 8%, 30 años, anual: D_mod=11,2577833431 y C=212,432547085, frente a 11,26/212,4; precio a TIR10%=811,461710660, frente a 811,46. Son diferencias compatibles con el redondeo mostrado.
7. **FI:** bono 11%, 5 años, anual, TIR15%: precio=86,591379608, C=16,9163584303; PDF104 da 16,915 usando pesos/convexidades intermedias redondeados. Con los pesos y términos redondeados impresos se obtiene 16,9152037, que explica esa diferencia de aproximación. Revaluación a 14,5%=88,1272117593 contra 88,12721 publicado. No redondear flujos/pesos antes de calcular.
8. **QIA:** PDF414/p.406 usa beta 1,5, error estándar 0,2, 62 observaciones y 60 df: t=2,5; crítico tabulado≈2 e intervalo [1,10;1,90]. La referencia usa Student sin redondeo de tabla y reproduce esos resultados a la precisión publicada.
9. **Resumen VAR y CSV:** el resumen no fija el nivel de confianza de sus ES aproximados de Global Macro≈2,9% y Equity Market Neutral≈3,6%. Con `hedgefundindices.csv` completo (263 retornos mensuales en %), una **reconstrucción inferida**, c=99%, percentil lineal y promedio de los 3 retornos que superan el umbral, da 2,933333% y 3,61%. Eso explica plausiblemente sus números, pero no prueba su procedimiento. Nuestro ES fraccional al 99% da 2,9760076% y 3,8210266%: diferencia de convención de cola con sólo 2,63 observaciones efectivas. Al 95% se obtienen otros números; no usar los aproximados del resumen como validación de un ES95. Se muestra la distinción en la salida.
10. **Matriz inválida en otra clase:** `Clase 1 estimacion de prob.pdf`, diap.48–52, tiene `Var2=0,004%`, `Var3=0,800%`, `Cov23=0,560%`. Eso implica `rho23=9,899494937>1`: no es una matriz de covarianzas válida. La imagen de la diapositiva confirma los porcentajes. El supuesto VaR diversificado de 82.840 mayor que la suma de VaR normales individuales de 64.055 no es evidencia de un “beneficio negativo” de diversificación normal: esos inputs violan la consistencia de covarianzas. La referencia rechaza la matriz, en vez de copiar ese riesgo como resultado válido. La misma clase aporta definiciones útiles en diap.7–12, 18, 23, 27 y 31; el signo de ES de diap.23 debe reconciliarse con si se informa retorno o pérdida.
11. **Otras fórmulas de repaso con errores:** en `Ejercicios para parcial/Formulas parcial.xlsx`, hoja `tasas de interes`, `B19` usa una potencia `1+t` en vez de `1/t` para una tasa anual equivalente; `N19=LOG(1+N17)` usa base 10 en vez de LN para continua; `R19=EXP(R17-1)+1` no es `EXP(R17)-1`. No se trasladan esas celdas a la metodología. Las conversiones correctas están en §2/§7.1 y en BKM. Esto refuerza la prioridad de definiciones consistentes sobre copiar sin validar una celda de un apunte.

### 12.4 Caso sintético y control manual

El caso incluye 261 valuaciones y 260 retornos, tres posiciones de renta variable (`ACC_A`, `CED_B`, `ACC_C`), dos bonos (`BONO_FIJO`, `BONO_CERO`) y efectivo. Sus fechas son un **calendario ficticio de lunes a viernes**, no el calendario bursátil argentino real. Precios de `CED_B` están ya expresados en USD por CCL; sus series auxiliares no son cotizaciones reales. Las trayectorias son series sintéticas de retorno total ajustado; las de bonos se escalan para que el último valor coincida con el precio sucio de sus flujos/TIR al corte. No se afirma que esas trayectorias provengan de una curva observada; no se agregan cupones pasados otra vez a una serie ya ajustada.

Pesos: 20%, 20%, 15%, 20%, 15%, 10%; valor inicial de análisis 100.000 unidades USD por CCL ficticio; se emplean pesos constantes y rebalanceo diario hipotético. Los precios sirven para calcular retornos; para crear posiciones monetarias en una aplicación real deben inferirse cantidades a partir de las valuaciones y del patrimonio elegido, sin suponer que una unidad de cada CSV equivale a esos pesos.

Resultados destacados para control de implementación:

| Resultado | Valor de referencia |
|---|---:|
| Volatilidad diaria cartera | 0,252874910489% |
| Volatilidad anual cartera | 4,014264755774% |
| Beta cartera al mercado sintético | 0,324587535739 |
| VaR normal 95%, una sesión, μ=0, dinero | 415,942213683311 |
| ES normal del mismo modelo | 521,608316563520 |
| VaR histórico 95%, cuantil inverso, dinero | 374,835070611773 |
| ES histórico fraccional, dinero | 435,716472731301 |
| HHI | 0,175 |
| DR | 1,631548093498 |
| Contribución anual de ACC_C | −0,287577728303 puntos porcentuales |

La contribución negativa de ACC_C es intencional: comprueba que el código conserve el signo de coberturas. La correlación de efectivo constante es null, aunque su covarianza y componente de volatilidad sean cero. El caso de exclusión de BONO_CERO conserva su peso original de 15% y muestra 85% cubierto.

**Control manual 1, del caso:** `HHI=3*(0,20²)+2*(0,15²)+0,10²=0,175`, número efectivo `1/0,175=5,714285714286`.

**Control manual 2, del bono cero del caso:** VN100, vencimiento dos años y tasa anual10%; `P=100/1,1²=82,644628099174`, `D_Mac=2`, `D_mod=2/1,1=1,818181818182`, `C=2*3/1,1²=4,958677685950`, `DV01=P*D_mod*0,0001=0,015026296018` por ese VN. El escenario +100 pb se comprueba directamente con `100/1,11²`, sin usar duration para el precio exacto.

Controles independientes adicionales: varianza de [−2%,0,+2%]=0,0004 con n−1; EWMA con semilla0,0004 y retorno1%=0,94*0,0004+0,06*0,0001=0,000382; CEDEAR con subyacente+10%, CCL+20%, ratio constante: `1,10*1,20−1=32%`. La salida comprueba Euler (suma de contribuciones=sigma), tratamiento de huecos y aproximación Monte Carlo frente a la normal. Un oráculo generado por la misma biblioteca sirve para regresión, **no es por sí solo prueba independiente de corrección**: por eso se agregan fuentes y controles manuales.

### 12.5 Salida ejecutada

La palabra `fuente` en la fila de `statistics.stdev` significa comparador independiente de biblioteca estándar, no un valor válido guardado en el Excel. En las filas manuales significa resultado aritmético independiente. Las diferencias de fuentes conocidas se conservan.

```text
Excel: retorno log AH1280 | ref=-0.00403170423037 | fuente=-0.00403170423037 | diferencia=+0
Historica SP500: ref vs statistics.stdev*sqrt(252) | ref=0.246811507296 | fuente=0.246811507296 | diferencia=-2.77556e-17
Historica MA reconstruida: n=241; vol anual=0.698152632892; MA!C3:C243 VACIO; MA!J1=0; no hay resultado fuente.
Diferencia de fuente: GARCH!L21 guarda #DIV/0!; apunta a D3:D1280 vacio. Historica reconstruida, no igualdad bibliografica.
Excel: EWMA previa AJ1280 | ref=0.000170374974979 | fuente=0.000170374974979 | diferencia=+0
Excel: EWMA anual AL1280 | ref=0.207206403605 | fuente=0.207206403605 | diferencia=-2.77556e-17
Excel: max diferencia 1278 varianzas EWMA = 4.33681e-19; pronostico siguiente=0.000161127754821
Clase 08: beta Alcoa R - Rf!D5 | ref=1.90279838366 | fuente=1.90279838366 | diferencia=-6.66134e-16
Clase 08: alfa Alcoa R - Rf!D6 | ref=0.000370710470133 | fuente=0.000370710470133 | diferencia=+4.33681e-19
Beta Alcoa: IC95=[1.501620001, 2.303976766]; t H0 beta=1: 4.504597925; p=0.000032699
Clase 08 segunda pasada: pendiente G5 | ref=-0.00197243825245 | fuente=-0.00197243825245 | diferencia=+4.33681e-19
Clase 08 segunda pasada: intercepto G4 | ref=0.000717588956774 | fuente=0.000717588956774 | diferencia=-4.33681e-19
Markowitz: sigma B18 | ref=0.319075946659 | fuente=0.319075946659 | diferencia=+0
Markowitz: varianza B18^2 | ref=0.101809459736 | fuente=0.101809459736 | diferencia=-1.38778e-17
Bodie PDF168 p139: VaR vs 25.56% redondeado | ref=0.25558 | fuente=0.2556 | diferencia=-2e-05
Bodie PDF169 p140: ES ref=0.359180952381 | fuente=.3594 | diferencia=-0.000219047619 (NO COINCIDE; se conserva discrepancia)
ES Bodie: aritmetica independiente | ref=0.359180952381 | fuente=0.359180952381 | diferencia=-5.55112e-17
Bodie PDF550: precio bono 2 anios | ref=964.540494958 | fuente=964.54 | diferencia=+0.000494958
Bodie PDF549: Macaulay 2 anios | ref=1.88522950687 | fuente=1.8852 | diferencia=+2.95069e-05
Bodie PDF556: duration modificada 30 anios | ref=11.2577833431 | fuente=11.26 | diferencia=-0.00221666
Bodie PDF556: convexidad 30 anios | ref=212.432547085 | fuente=212.4 | diferencia=+0.0325471
Bodie PDF556: precio TIR 10% | ref=811.46171066 | fuente=811.46 | diferencia=+0.00171066
CFA FI PDF104: convexidad | ref=16.9163584303 | fuente=16.915 | diferencia=+0.00135843
CFA FI PDF104: precio | ref=86.591379608 | fuente=86.59138 | diferencia=-3.92046e-07
CFA FI PDF105: precio TIR 14.5% | ref=88.1272117593 | fuente=88.12721 | diferencia=+1.75935e-06
CFA FI PDF120: perdida esperada % | ref=0.0075 | fuente=0.0075 | diferencia=+0
Clase 1 estimacion prob PDF52: matriz RECHAZADA; rho23=9.899494937 >1 (error de fuente, no se corrige).
Resumen VAR (inferencia c=99%): Global Macro ES umbral=0.029333333 vs publicado aprox 0.029; ES fraccional=0.029760076
Resumen VAR (inferencia c=99%): Equity Market Neutral ES umbral=0.036100000 vs publicado aprox 0.036; ES fraccional=0.038210266
MANUAL 1: varianza [-2%,0,2%] | ref=0.0004 | fuente=0.0004 | diferencia=+0
MANUAL 1: EWMA .94*.0004+.06*.0001 | ref=0.000382 | fuente=0.000382 | diferencia=-5.42101e-20
MANUAL 2: precio cero | ref=82.6446280992 | fuente=82.6446280992 | diferencia=-1.42109e-14
MANUAL 2: duration cero | ref=1.81818181818 | fuente=1.81818181818 | diferencia=+0
MANUAL 2: convexidad cero | ref=4.95867768595 | fuente=4.95867768595 | diferencia=-8.88178e-16
MANUAL caso: HHI | ref=0.175 | fuente=0.175 | diferencia=+2.77556e-17
MANUAL caso: bono cero DV01 | ref=0.015026296018 | fuente=0.015026296018 | diferencia=-3.46945e-18
MANUAL caso: CEDEAR +10% suby +20% CCL | ref=0.32 | fuente=0.32 | diferencia=+5.55112e-17
QIA PDF414 p406: t critico df60 | ref=2.00029782201 | fuente=2 | diferencia=+0.000297822
QIA PDF414 p406: IC inferior beta | ref=1.0999404356 | fuente=1.1 | diferencia=-5.95644e-05
QIA PDF414 p406: estadistico beta | ref=2.5 | fuente=2.5 | diferencia=+0
Student bilateral t=1 df=1 | ref=0.5 | fuente=0.5 | diferencia=+7.77156e-16
Student cuantil 97.5% df=10 | ref=2.22813885199 | fuente=2.22813885196 | diferencia=+2.13354e-11
VaR/ES cola fraccional [1,2,3,4], c=.625 | ref=3.66666666667 | fuente=3.66666666667 | diferencia=+0
Euler: suma componentes = sigma | ref=0.00252874910489 | fuente=0.00252874910489 | diferencia=+0
Caso CSV vs esperado.json: 2383 valores numericos coinciden (rtol=1e-10, atol=1e-12).
Controles de huecos, correlacion indefinida, drawdown, Euler, PSD y Monte Carlo: OK.
RESULTADO: controles ejecutables OK; diferencias documentadas: historica Excel sin cache valido y ES Bodie no coincide.
```

## 13. Alcance real de lectura y límites

Se inventariaron los **61 archivos** de `bibliografia/`, incluyendo duplicados. `fuentes/inventario.json` registra nombre, tamaño y SHA-256 de cada original; `fuentes/LECTURA.md` describe el tratamiento de todos. Se revisaron las fuentes prioritarias por temas y ejemplos, sin afirmar una lectura lineal íntegra de cada página de los libros de 1.080 y 730 páginas ni de todas las soluciones.

- Se extrajo el texto de los PDF y documentos, y fórmulas y valores guardados de todos los Excel. Se estudiaron los núcleos de retornos/covarianza/CAPM/factores/performance de las clases presentes: 01, 02, 05, 06, 07, 08, 09, 10, 12, 13. **Las clases 03, 04 y 11 no están en la carpeta**; no se simula haberlas leído.
- BKM: revisión focal de capítulos 5–11 y 14–16, más desempeño de cap.24. Los .doc suministrados corresponden a capítulos 5–13 y 27; **no hay soluciones .doc de 14–16**. Se validaron renta fija con los ejemplos resueltos del propio BKM y FI; no se adjudica una solución de bonos a un .doc inexistente.
- QIA: el PDF es esencialmente escaneado. La extracción textual no permite leer el cuerpo. El intento de OCR local con Apple Vision falló (`nilError`), pero se renderizaron páginas y se inspeccionaron visualmente: índice PDF4–7, PDF10/p.2 sobre tasas, PDF140/p.132 sobre varianza muestral, PDF143/p.135 sobre dispersión, PDF274/p.266 sobre Monte Carlo/VaR, PDF409/p.401, PDF411/p.403 y PDF413–414/pp.405–406 sobre regresión y Student. **No se pudo completar una lectura textual/OCR integral de QIA**. Sus páginas seleccionadas sí respaldan los puntos citados; el resto no se da por leído.
- Algunas clases y FIII contienen fórmulas como imágenes; el texto extraído es parcial. Las fórmulas de esta entrega se contrastaron con definiciones legibles de BKM/FI, libros de cálculo y ejemplos comprobados. No se atribuye a una diapositiva una cifra ilegible por reconstrucción imaginada.
- Los .doc se convirtieron a texto con `textutil`; varias ecuaciones OLE aparecen como `EMBED Equation.DSMT4`/`QUOTE` y no se pudieron recuperar completas. Se usó el contenido legible de soluciones como apoyo, sin inventar las ecuaciones ausentes.
- `Practica ADMIN CARTERAS.xlsx` es un ejercicio corto de beta/pesos, no una matriz de riesgo completa. Los resúmenes Index Model, el gráfico y los dos `INDEX MODELO_ 5 ACTIVOS Y RF` sirven de contraste de modelos; el test numérico de Markowitz usa una matriz completa con pesos y resultado guardado en MARK. Los CSV de fondos/portfolios son material de ejercicios, no cotizaciones actuales de clientes; `sample_prices.csv` no tiene fechas.
- Los artículos macro, el comentario de bancos centrales, RMG 2018, links de ML, capítulos de comportamiento/eficiencia y el PDF de contabilidad de nombre numérico se revisaron para alcance/contexto. No se los utiliza para fijar λ, ventanas, PD ni parámetros argentinos. Los resultados de mercados de Egipto/Túnez de un artículo no son una calibración de betas locales. RMG es comentario histórico de tasas, no una fuente de tasas vigentes.
- data912 no entregó una serie verificable por las restricciones HTTP descritas; IAMC/BYMA se documenta como fuente de inputs indicada por el encargo, sin inventar una consulta ni sus valores actuales. No se usaron otras fuentes con credenciales.

El alcance numérico verificable queda explícito: EWMA, beta/segunda pasada, Markowitz, VaR/ES de ejercicios, bonos, Student y caso sintético. Permanecen diferencias de convenciones (simples/log, n/n−1, IR/appraisal, Sortino, cuantiles), errores de apuntes y la inconsistencia ES BKM detallados arriba. La volatilidad histórica del Excel se reconstruyó y comprobó por otra vía, **sin un resultado fuente válido para cotejarla**.

## Decisiones para Felipe

Estas decisiones quedan abiertas para la implementación. Las recomendaciones permiten avanzar con configuración explícita, sin completar datos ni atribuir a la bibliografía una preferencia personal.

| Decisión | Recomendación |
|---|---|
| Moneda patrimonial | USD por CCL como vista principal; ARS complementario. Elegir MEP si el objetivo del cliente es dólar local; fijar una política única y fuente por fecha |
| Objetivo real | IPC mensual para poder de compra ARS; CER sólo con su referencia contractual y rezago. No generar inflación diaria desde IPC |
| Tasa USD | T-bill corto con serie y conversión conocidas; hasta disponer del input, ratios con rf sin dato |
| Tasa ARS | caución corta como proxy explícito; alternativa de letra soberana corta con riesgo de crédito identificado. No usar una TIR cualquiera como rf |
| Ventanas | riesgo reciente 252 sesiones, control semanal/mensual; colas 504. Mantener mínimos y cobertura publicados, aceptando que pueden impedir mostrar una métrica |
| Tipo de retorno | simple total para dinero/cartera/VaR; log para réplica académica/EWMA y descomposición cambiaria. Etiquetar cualquier retorno de precio sin pagos |
| Anualización y estimador | 252 y n−1 para estadística bursátil; bases de días y capitalización contractuales aparte |
| EWMA | λ0,94 y semilla del Excel; 60 retornos de calentamiento consecutivo; publicar también volatilidad histórica |
| VaR/ES | 95% y una sesión, μ normal=0; ES histórico fraccional y cuantil empírico inverso; 10 sesiones como complemento con límites del escalado |
| Mínimos / cobertura | 95% temporal; no mostrar riesgo de cartera total con activos excluidos. Mostrar universo, pesos originales y subconjunto normalizado si aporta |
| Beta y benchmark | Merval para acciones locales; S&P USD/subyacente y FX para CEDEARs; benchmark compuesto o factores para la cartera mixta. No promediar betas incompatibles |
| Tests | bilateral5%, beta contra1 y alfa contra0; IC con Student clásico, advertencia si los supuestos no son razonables |
| Desempeño | Sortino con n y MAR=rf; conservar comparador condicionado BKM. Distinguir IR de benchmark y appraisal de alfa/residual; M² como diferencial |
| Bonos | D/C/DV01 según flujo y convención verificados; paralelos ±100/±200 más ±50; índice, tasa real/nominal y spread por separado |
| Crédito y liquidez | no fijar PD/recupero sin fuente/modelo; escenarios hipotéticos explícitos. Liquidez20 sesiones/participación10% como estimación inicial configurable |
| Informe al cliente | moneda/cobertura, volatilidad, VaR+ES, caída observada y concentración; un escenario relevante. Diagnóstico y detalle de modelos para el asesor |

Se entrega una metodología implementable con referencia y pruebas ejecutadas, un caso sintético reproducible y las diferencias documentadas. Quedaron sin lectura integral el cuerpo escaneado de QIA y las ecuaciones OLE no recuperables; tampoco pudo verificarse el JSON/largo de data912 por HTTP403. Los originales no fueron modificados y no se implementó la herramienta productiva.
