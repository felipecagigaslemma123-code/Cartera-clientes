# cartera

Seguimiento interno de carteras de clientes, local en una Mac. Instrucciones para el
desarrollo en [AGENTS.md](AGENTS.md) y etapas en [PLAN.md](PLAN.md).

El objetivo aprobado es medir el resultado completo desde el día cero, incorporando
movimientos y cobros. El desarrollo se entrega por etapas: Codex implementa, Claude
revisa y Felipe valida los criterios. La etapa 1 prepara la base inicial; precios,
tablero, alertas y movimientos corresponden a las siguientes.

## Preparar el entorno

Desde la raíz de esta carpeta, con Python 3.9:

```bash
python3 -m venv ~/.venvs/cartera
~/.venvs/cartera/bin/pip install -r requirements.txt
```

El entorno queda fuera de OneDrive. El paquete se usa con `PYTHONPATH=src`.

## Demostración de la etapa 1

Usar únicamente el Excel ficticio y una carpeta temporal de datos:

```bash
datos_demo="$(mktemp -d)"
PYTHONPATH=src ~/.venvs/cartera/bin/python -m cartera --datos "$datos_demo" importar --cliente demo --archivo fixtures/punto_partida_demo.xlsx
PYTHONPATH=src ~/.venvs/cartera/bin/python -m cartera --datos "$datos_demo" estado --cliente demo
```

`--datos` también puede reemplazarse por la variable de entorno `CARTERA_DATOS`.
La importación guarda `clientes/demo/cartera.json` dentro de esa ruta. Valida todos
los problemas juntos y rechaza sobrescribir una base existente. `estado` distingue
costos de extracto, estimados y pendientes; sin precios actuales muestra "sin dato".
Los datos guardados se describen en [FORMATOS.md](docs/FORMATOS.md).

## Corregir costos conservando el historial

Corregí una copia del Excel de punto de partida y ejecutá:

```bash
PYTHONPATH=src ~/.venvs/cartera/bin/python -m cartera --datos RUTA actualizar-costos --cliente SLUG --archivo EXCEL
```

La base debe existir. Se validan todas las filas y se mantienen exactamente las
especies, tipos, unidades de cotización y cantidades totales de la cartera; pueden
cambiar los lotes, sus fechas, precios, costos, orígenes y notas. Antes del reemplazo
atómico, la versión anterior completa se guarda en `clientes/SLUG/historial_cartera/`
con fecha, hora y nombre único. Si no cambia ningún dato, informa que no hay cambios y no
escribe nada. `importar` sigue rechazando una base existente.

Si falla el reemplazo después de guardar el respaldo, la base anterior queda intacta
y el respaldo permanece; su presencia no significa que la corrección se completó.

La salida detalla el costo y origen anterior y nuevo por especie modificada. Una
alteración de un costo de extracto o de ese origen genera una advertencia sin
bloquear. Al no haber identificadores de lote, esa detección es conservadora y
también advierte ante reasignaciones ambiguas entre extractos y otros lotes.
Reordenar filas o corregir únicamente una nota de extracto no genera el aviso.

Ambos comandos rechazan fechas de compra posteriores a hoy en Argentina, indicando
hoja, fila y ticker; la fecha de hoy se acepta. Las demostraciones y correcciones de
prueba deben usar únicamente datos ficticios y una carpeta temporal de datos.

## Verificación por etapa

Para verificar la primera etapa y las comprobaciones adicionales:

```bash
PYTHONPATH=src ~/.venvs/cartera/bin/python -m unittest discover -s tests -p 'test_etapa1*' -v
PYTHONPATH=src ~/.venvs/cartera/bin/python -m unittest discover -s tests -p 'test_extra*' -v
```

La ejecución de todas las pruebas será apropiada al completar sus módulos:

```bash
PYTHONPATH=src ~/.venvs/cartera/bin/python -m unittest discover -s tests -v
```

Claude revisó los cálculos de la etapa 1 y los aprobó. Esta corrección incorpora la
actualización de costos con historial y el rechazo de fechas futuras. Pasan las 28
pruebas originales y 73 adicionales; la evidencia se registra en
[entrega y revisión](docs/REVISION_ETAPA1.md). Todavía no se
avanzó a la etapa 2: el control de precios por una diferencia mayor a cinco veces
queda especificado, con implementación y pruebas reservadas para esa etapa.
Las decisiones abiertas de las etapas posteriores figuran en el plan y el contrato.

Esta carpeta no contiene datos reales de clientes. Las salidas se guardan en la ruta
de datos, separada del código; las demostraciones y pruebas usan datos ficticios.
