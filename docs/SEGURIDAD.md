# Seguridad: qué hace el código fuera de sí mismo

Para quien revise el repositorio antes de correrlo. Detalla cada conexión, cada programa externo y cada
escritura en disco, para que se pueda comprobar que no hay nada oculto. Todo lo que figura acá se puede
verificar con las búsquedas del final.

## Resumen

- **Lenguaje:** Python 3.9, biblioteca estándar, `openpyxl` y `fixed-income-toolkit`.
  El Toolkit es una dependencia privada, fijada a `v0.2.0` desde GitHub en
  [requirements.txt](../requirements.txt). Sus dependencias de ejecución son la
  biblioteca estándar y `openpyxl`; pytest y herramientas de construcción son de desarrollo.
  La instalación usa las credenciales de Git del usuario; nunca se incluyen en la URL.
  Instalar no consulta índices ni transmite datos de clientes. El código cliente
  importa solo módulos de paquetes declarados del Toolkit.
- **Sin binarios:** el repositorio tiene solo código Python, documentación, y datos de prueba en JSON, CSV,
  Excel, HTML y texto. No hay ejecutables, instaladores, macros ni archivos comprimidos.
- **Sin credenciales:** no hay claves, tokens ni contraseñas. El código no lee ninguna variable de entorno
  salvo `CARTERA_DATOS`, que indica la carpeta de datos.
- **Sin envío de datos:** todas las conexiones son **consultas de lectura** a fuentes públicas de precios e
  índices. Nunca se envían datos de clientes, cantidades ni importes.
- **Pruebas sin red:** las 1027 pruebas usan respuestas guardadas en `fixtures/` y no se conectan a nada.

## Conexiones de red

| Destino | Para qué | Dónde |
|---|---|---|
| `data912.com` | Precios de acciones, CEDEARs, bonos y letras (en vivo e históricos) | `src/cartera/precios.py`, `transporte.py`, `riesgo.py`, y el dashboard desde el navegador (`_dashboard_js.py`) |
| `www.iamc.com.ar` | Cierre diario de renta fija: TIR, duration, cronogramas | `src/cartera/iamc.py`, `tools/iamc_*.py` |
| `api.bcra.gob.ar`, `www.bcra.gob.ar` | Series de CER, TAMAR, tipo de cambio A3500 y encuesta REM | `market_data.providers.bcra` del Toolkit (series), `src/cartera/indices_archivos.py` (descarga y archivos REM), `tools/bcra_extraer.py` (envoltorio) |
| `query1.finance.yahoo.com` | Históricos de los activos subyacentes de algunos CEDEARs, solo para el análisis de riesgo aproximado | `tools/riesgo/analizar_carteras.py` (herramienta aparte, no es parte del programa) |

Todas son pedidos `GET` con `urllib` de la biblioteca estándar, con un tiempo de espera de 10 a 30 segundos.
Las URLs de `schemas.openxmlformats.org` que aparecen en el código son nombres de esquema de Excel, no
conexiones.

La instalación de dependencias consulta GitHub mediante Git/pip para obtener la
versión privada del Toolkit. Esto ocurre al preparar el entorno, separado de las
consultas públicas de ejecución listadas arriba. Los módulos de cálculos del
Toolkit no hacen red ni leen archivos de clientes. Para auditar las conexiones
hay que incluir también el código instalado de `market_data`.

## Programas externos que se ejecutan

| Programa | Para qué | Dónde |
|---|---|---|
| `osascript` (macOS) | Mostrar una notificación de escritorio cuando se dispara una alerta de precio | `src/cartera/notificar.py` |
| Google Chrome sin ventana (`--headless`) | Convertir el informe HTML del cliente en PDF | `src/cartera/informe.py` |

En los dos casos se pasan argumentos como lista, sin pasar por una shell, así que un texto no puede
inyectar comandos. No hay `eval`, `exec` dinámico ni `pickle`.

## Escrituras en disco

Solo dentro de la carpeta de datos indicada con `--datos` (o `CARTERA_DATOS`): bases de clientes, historial
de precios, caché de fuentes, dashboards, informes y exportes Excel. La única excepción es el comando
`informe`, que además deja una copia del PDF en la carpeta de informes que tenga configurada el cliente en su
perfil. El código no modifica nada fuera de esas rutas ni del propio repositorio.

## Cómo verificarlo

```bash
# Todas las direcciones que aparecen en el código
grep -rhoE "https?://[a-zA-Z0-9./_-]+" src tools | sed -E 's#(https?://[^/]+).*#\1#' | sort | uniq -c

# Todas las conexiones, procesos y evaluación dinámica
grep -rnE "urlopen|fetch\(|subprocess|os\.system|eval\(|exec\(|pickle|socket" src tools

# Variables de entorno
grep -rnE "environ|getenv" src tools
```

Para probarlo aislado, alcanza con un entorno virtual nuevo y las pruebas, que no usan la red:

```bash
python3 -m venv /tmp/cartera-venv
/tmp/cartera-venv/bin/pip install -r requirements.txt
PYTHONPATH=src /tmp/cartera-venv/bin/python -m unittest discover -s tests
```
