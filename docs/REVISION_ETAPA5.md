# Revisión de la Etapa 5

Entrega de Codex: 5 de noviembre de 2026. Implementada únicamente la Etapa 5 de
`PLAN.md`, pendiente de revisión de Claude y validación de Felipe. Se leyeron
`AGENTS.md`, el plan y las reglas de movimientos del contrato, dominio, formatos,
dashboard y alertas antes de implementar.

## Implementación

- `cartera.movimientos`: CSV de nueve columnas, normalización de fecha y números,
  validación conjunta de todas las filas y de la historia completa, fechas posteriores
  al día cero y no futuras en Argentina. Las cargas retroactivas respetan las ventas
  posteriores. La escritura conserva los bytes previos, usa bloqueo de directorio y
  publica un temporal privado mediante reemplazo atómico o creación exclusiva.
- FIFO por fecha, estable para operaciones del mismo día y lotes con igual fecha;
  los lotes sin fecha se consumen primero. Prorratea costos sin modificar las entradas.
  Las compras tienen costo neto en pesos y origen extracto; en USD se convierten con
  el cambio registrado, sin inventar un precio de compra. Las ventas informan su
  costo y resultado en pesos, con origen extracto, estimado, mixto o incompleto.
- Reconstrucción de cantidades desde posiciones de la base más compras menos ventas,
  conservación de metadatos, alta de especies nuevas y eliminación de posiciones
  totalmente vendidas. La base importada no se sobrescribe con tenencias actuales.
- `movimientos_resultados.py`, reexportado por `cartera.movimientos`: efectivo por
  moneda, flujos en pesos, conciliación a la fecha del saldo informado y resultado
  completo. Efectivo inicial desconocido sigue desconocido; se admiten negativos.
  Las conversiones de divisas afectan ambos saldos, sin convertirse en aportes o retiros.
- Patrimonio final menos inicial y aportes, más retiros. Cobros, gastos y ventas se
  computan una sola vez mediante el efectivo. El realizado no se agrega al resultado.
  Un costo pendiente no impide el resultado completo. Los faltantes se conservan como
  tales; USD cero no requiere MEP y una posición vendida no requiere precio actual.
  No se implementó porcentaje integral ni resultado integral en dólares.
- Comando `movimiento`, con fecha y números recibidos como texto para devolver código
  1 ante formatos inválidos, sin escribir. Exige día cero y confirma la tenencia cuando
  corresponde. `estado` informa posiciones actuales, patrimonio inicial con la base,
  efectivo calculado, flujos, realizado y control de efectivo, sin consultar la red.
- `capturar`, `dashboard` y alertas usan la cartera actual. `fijar-dia-cero` conserva
  la base importada y valida movimientos antes de cotizaciones, caché o salida: tampoco
  `--forzar` permite mover la referencia hasta un movimiento o después de él.
- Un CSV inválido hace fallar estado, captura y dashboard sin salidas. En alertas se
  sigue con la base y se entrega un `sin_chequeo` diario, persistido en
  `error_movimientos`. Niveles de especies conocidas vendidas se ignoran con aviso;
  las desconocidas siguen siendo inválidas. También vencimientos usan tenencia actual.

## Dashboard y recálculo en vivo

El comando siempre pasa el resultado integral, los realizados, la conciliación y las
posiciones de la base por separado. La API directa sin integral conserva el recuadro
anterior para mantener compatibilidad. El JSON incluye los campos del contrato,
fechas ISO y `faltantes_fijos`, que permite separar los datos iniciales desconocidos
de los precios o MEP que sí pueden recuperarse en vivo.

El HTML incluye resultado completo, patrimonios, flujos, ventas realizadas con sus
orígenes, total conocido y cantidad excluida, efectivo informado, calculado e inicial,
y conciliación. Una diferencia indica revisar movimientos, manteniendo el efectivo
calculado para el patrimonio final.

JavaScript vuelve a calcular valuación final, conversión del efectivo USD, patrimonio
final y resultado completo en cada ronda de precios y MEP. No suma nuevamente rentas,
dividendos ni realizado. Recupera precios/MEP antes ausentes, conserva el último dato
con su advertencia si falla una consulta y mantiene desconocidos los faltantes fijos.
Una cartera totalmente vendida sigue consultando MEP, con valuación de posiciones cero.
Nuevos movimientos requieren regenerar el archivo; el navegador no lee el CSV local.
Se mantienen JSON escapado, `textContent`, CSP y ausencia de dependencias externas.

## Verificación

Se ejecutaron con Python 3.9 del entorno existente y `PYTHONPATH=src`:

```bash
PYTHONPATH=src ~/.venvs/cartera/bin/python -m unittest discover -s tests -p 'test_etapa*'
PYTHONPATH=src ~/.venvs/cartera/bin/python -m unittest discover -s tests -p 'test_extra*'
```

| Grupo | Pruebas | Resultado |
|---|---:|---|
| Etapas 1 a 5 | 248 | OK |
| Adicionales | 292 | OK |
| Total | 540 | OK |

Las 56 pruebas nuevas están en `test_extra_movimientos.py` (24),
`test_extra_resultado_integral.py` (10), `test_extra_dashboard_integral.py` (12) y
`test_extra_etapa5_integracion.py` (10). Cubren fechas y formatos, FIFO y orígenes,
monedas y conversiones, datos ausentes, conciliación inclusiva, recuperación de
precios/MEP, cálculo sin doble conteo, ventas completas, uso de base para patrimonio
y fijación de referencia, historia retroactiva, concurrencia, fallos de publicación
y comandos sin consultas ni escrituras ante CSV inválido.

Nueve pruebas nuevas ejecutan el script real del dashboard con JavaScriptCore y un
DOM y red ficticios: primera y segunda ronda con precios y MEP distintos, recuperación
de faltantes, caída posterior, efectivo desconocido, USD cero y cartera totalmente
vendida. No son una verificación visual en un navegador real.

Se comprobó mediante huellas que los 45 archivos originales protegidos (pruebas,
fixtures, especificaciones y sus instrucciones) quedaron intactos. No se modificaron
pruebas anteriores ni documentación normativa para pasar pruebas. `git diff --check`
no informa problemas. Se utilizaron exclusivamente datos ficticios y canales
reemplazados; no hubo consultas reales de precios, avisos, acceso a credenciales,
instalación de tareas ni commits.

## Límites, dudas y criterios de borde

No se detectaron contradicciones que exigieran alterar pruebas o especificaciones.
La separación interna del módulo monetario mantiene la API pública indicada.
`ResultadoIntegral` agrega `faltantes_fijos` con valor predeterminado para soportar
el contrato del JSON y su recálculo sin romper los campos previos.

Cuando una base tiene una diferencia tolerada entre cantidad nominal y suma de
lotes, las cantidades actuales conservan la nominal de la base. Esa tolerancia no
autoriza vender más que la tenencia nominal ni más que los lotes disponibles; no se
ajusta ni inventa una cantidad. Se cubre como caso de borde adicional. Los acumulados
fuera del rango finito se rechazan o se muestran como sin dato, sin publicar infinitos.

La revisión visual quedó para Claude por decisión de Felipe: el navegador integrado
había bloqueado la apertura de archivos locales en la Etapa 3. No se intentó eludir
ese bloqueo. Siguen sin comprobarse doble clic en el HTML, diseño en pantalla angosta,
aplicación real de CSP/CORS y consultas, refrescos y recuperación contra data912 desde
un navegador. La lógica de recálculo se probó con simulaciones; esos controles reales
requieren la revisión pendiente. Tampoco se comprobaron avisos reales ni importación
de movimientos desde un broker, que continúa fuera de este alcance.

El trabajo se detuvo al completar esta etapa.

## Revisión de Claude

Probada con una copia de los datos reales, precios reales de data912, movimientos y efectivo de prueba,
y canales simulados; las copias se borraron al terminar. El efectivo y el resultado completo coincidieron
con una cuenta a mano. En el navegador, servido desde `127.0.0.1`, el resultado se recalculó bien con
precio y MEP modificados, conservó el último dato ante una caída de la fuente y se recuperó al volver.

Se corrigió un defecto: una línea en blanco en `movimientos.csv` invalidaba el archivo completo. Ahora se
ignora. Total tras la revisión: **541 pruebas aprobadas** (248 de etapas y 293 adicionales).

Siguen sin verificar el aspecto en pantalla, el doble clic en el archivo y los avisos reales.
