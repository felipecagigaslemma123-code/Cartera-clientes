# BCRA y REM: archivos en Cartera

Actualizado el 25/11/2026. El proveedor de series públicas, sus validaciones,
el guardado de capturas y el lector del REM pertenecen a `fixed-income-toolkit`
0.2.0 (`market_data.providers.bcra`). Las proyecciones y la evidencia del
13/11/2026 se documentan en las investigaciones del Toolkit:
[CER R-010](https://github.com/felipecagigaslemma123-code/Fixed-Income-Toolkit/blob/separacion-renta-fija/docs/research/010_cer_projection.md),
[TAMAR R-011](https://github.com/felipecagigaslemma123-code/Fixed-Income-Toolkit/blob/separacion-renta-fija/docs/research/011_tamar_projection.md) y
[A3500 R-012](https://github.com/felipecagigaslemma123-code/Fixed-Income-Toolkit/blob/separacion-renta-fija/docs/research/012_a3500_bond_projection.md).
La rama todavía debe publicarse; este traslado no crea tags ni hace push.

Cartera mantiene `indices_archivos.py`: decide cuándo actualizar y selecciona
las capturas y Excel del REM bajo `--datos`, sin enviar datos de clientes.
La organización, periodicidad, fallos y supuestos están en
[PROYECCIONES.md](PROYECCIONES.md).

El comando de muestra conserva sus opciones y mensajes; es un envoltorio del
CLI instalado del Toolkit:

```bash
PYTHONPATH=src python tools/bcra_extraer.py --desde 2026-09-24 --hasta 2026-09-30 --salida /tmp/bcra-muestra.json
```

Requiere un archivo nuevo fuera del proyecto y conserva capturas anteriores.
No se rellenan observaciones ausentes ni se escribe una captura parcial.
