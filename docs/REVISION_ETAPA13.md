# Revisión de la Etapa 13 — Capital que vuelve y ganancia

18 de noviembre de 2026. Igual que la etapa 12, la especificó e implementó Claude (Codex sigue sin acceso al
proyecto), así que no hubo revisión cruzada.

## El pedido

Felipe vio que en el informe de una cliente figuraban unos US$ 3.000 a cobrar por un bono, como si todo
fuera ganancia, cuando la mayor parte devuelve lo que se pagó al comprarlo. Pidió separar el capital de la
ganancia, y la ganancia entre la compra bajo la par y los intereses.

## Qué se hizo

- `flujo_fondos._separar_capital` e `_intereses_corridos`: por compra, intereses corridos, ganancia por
  precio e intereses; por pago, capital y ganancia. `_capital_pendiente`: lo mismo por posición, solo para lo
  que falta cobrar.
- Dashboard (y su Excel): "Devuelve capital" y "Ganancia" en la tarjeta y en los pagos de cada compra; "Por
  precio" y "Por intereses" en cada compra, con una nota sobre los intereses corridos.
- Informe: columnas "Devuelve lo invertido" y "Ganancia" en Cobros por título; en cada total por moneda, una
  barra con las dos partes; en los próximos cobros que amortizan, cuánto devuelve lo invertido.
- Reglas en `docs/FLUJO_FONDOS.md`, `docs/INFORME.md` 1.2, `docs/CONTRATO.md` y `PLAN.md`. Pruebas en
  `tests/test_extra_capital_ganancia.py`; la fixture `fixtures/informe/` suma la separación.

## Decisiones

1. **Intereses corridos.** El precio de compra es sucio: incluye los intereses devengados desde el último
   cupón, que el primer cupón devuelve. Se cuentan como capital que vuelve, no como ganancia. Sin esto, en un
   bono semestral la ganancia por precio se subestimaba y los intereses se sobrestimaban hasta en un cupón
   entero (AE38 comprado tres días antes del pago).
2. **Capital por amortización.** Lo invertido vuelve en proporción a los nominales que amortiza cada pago. En
   un bono de una sola amortización, todo vuelve al vencimiento.
3. **Ajustables.** En un CER o dólar linked, la "ganancia por precio" incluye el ajuste por el índice. El
   informe lo aclara en la nota.
4. **Una renta sola no se detalla** en los próximos cobros, aunque devuelva unos centavos de intereses
   corridos de una compra reciente: confundía más de lo que aclaraba.

## Controles con las carteras reales

| Control | Resultado |
|---|---|
| Lo que devuelve cada compra suma su inversión | 34 compras de las tres carteras, diferencia máxima 5·10⁻²⁴ |
| `ganancia_precio + intereses = resultado_vto` | En todas las compras |
| Ejemplo del pedido | AO28 de sc: de US$ 3.219,68 a cobrar, US$ 2.637,87 devuelven lo invertido y US$ 581,81 son ganancia |
| Informe de sc | Tres hojas A4, con la separación en pesos, dólar MEP y dólar cable |
| Pruebas | 1021, todas aprobadas |

## Límites

- **Inicio del cupón supuesto.** Cuando el cronograma cargado empieza después de la compra, el período se
  supone igual al siguiente (12 de las 34 compras). Si el bono cambió la frecuencia de pago en ese tramo, el
  corrido sale mal, aunque el total no cambia.
- **Convención de días.** El corrido es lineal en días corridos, no la del prospecto (30/360, real/365). La
  diferencia es de días de un cupón y solo pasa importe entre capital e intereses.
- **Lo ya cobrado no se muestra separado en el informe:** el informe habla de lo que falta cobrar. El
  dashboard sí muestra la separación de los pagos pasados de cada compra.
