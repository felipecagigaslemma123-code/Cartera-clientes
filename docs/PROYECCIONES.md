# Proyecciones: operación en Cartera

Versión 1.4 · 25/11/2026. Las fórmulas y su validación viven en Fixed Income Toolkit
0.2.0, aprobado por Felipe. Cartera conserva los datos por cliente y su operación.

- [CER: investigación R-010](https://github.com/felipecagigaslemma123-code/Fixed-Income-Toolkit/blob/separacion-renta-fija/docs/research/010_cer_projection.md).
- [TAMAR: ventana, cupón en curso y piso, R-011](https://github.com/felipecagigaslemma123-code/Fixed-Income-Toolkit/blob/separacion-renta-fija/docs/research/011_tamar_projection.md).
- [A3500 para flujos de bonos dólar linked, R-012](https://github.com/felipecagigaslemma123-code/Fixed-Income-Toolkit/blob/separacion-renta-fija/docs/research/012_a3500_bond_projection.md).
- [API y compatibilidad](https://github.com/felipecagigaslemma123-code/Fixed-Income-Toolkit/blob/separacion-renta-fija/docs/migration_0_2_0.md).

Los enlaces describen el contenido preparado en la rama `separacion-renta-fija`;
este encargo no publica la rama ni crea el tag. R-006 sigue sin aprobación.

## Cuándo y dónde se guardan los datos

Todo se guarda bajo `--datos` o `CARTERA_DATOS`:

```text
indices/bcra/AAAA-MM-DD.json       capturas compartidas, conservadas sin sobrescribir
indices/rem/AAAA-MM.xlsx          Excel original del REM, sin modificar
feriados.json                    calendario que carga Felipe por año
supuestos_manual.json            escenarios opcionales con nota y tasas en tanto por uno
clientes/SLUG/proyecciones/AAAA-MM-DD.json   estimaciones semanales por cliente
```

El comando `indices` consulta desde el 1 de enero del año anterior: A3500/TAMAR
hasta hoy y CER hasta el 15 del mes siguiente; guarda solo lo publicado.
Descarga el último REM si falta. El dashboard intenta actualizar si la captura
tiene más de siete días o, después del día 10, falta el REM del mes anterior:
un intento por día. Ante una falla usa lo guardado y muestra su fecha y el aviso.
El REM se busca por su URL mensual y, si no existe, en los enlaces oficiales.

`instrumentos.json` conserva el vínculo `iamc.indice` y sus datos contractuales:
tipo, fuente, rezago, valor inicial, pagos reales y piso cuando corresponda.
Los `pagos_manuales` del prospecto aportan el inicio del cupón TAMAR en curso.
Sin ellos se conserva el fallback IAMC con su aviso metodológico en R-011.
Los supuestos manuales reemplazan estimaciones, nunca valores publicados.
Si falta un año de feriados se conserva el aviso correspondiente.

Las letras CER/dólar linked con contrato `iamc.indice` siguen el flujo indexado y
cargan su precio mediante `precio-bono`; las demás conservan el panel de letras.
Cada pago mantiene su origen definitivo/estimado, y los pagos en pesos van a ARS.
La TIR por compra, el control de cobros y la separación capital/ganancia siguen
en el flujo del cliente. Al generar un dashboard se conserva una estimación cada
siete días y, al cobrar, se muestra la última anterior al pago. Reglas del flujo:
[FLUJO_FONDOS.md](FLUJO_FONDOS.md); contratos: [CONTRATO.md](CONTRATO.md).
