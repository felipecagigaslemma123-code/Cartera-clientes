# Tenencia de letras en el dashboard

Versión 1.1 · 25/11/2026 (original: 05/11/2026). Pedido de Felipe: panel de lectura, sin calculadora ni formularios.

## Alcance y fuentes

El panel usa la base importada más los movimientos posteriores al día cero y su FIFO. Las letras aparecen automáticamente por su tipo explícito `letra`; nunca se deduce familia, moneda o vencimiento del ticker. Los nominales vendidos dejan de integrar el pago previsto. Una letra vencida no se considera cobrada hasta registrar el movimiento correspondiente.

Se instala **Fixed Income Toolkit 0.2.0** desde el repositorio privado de GitHub,
con versión fija en `requirements.txt`. `cartera.letras` importa de `financial_engine`
las funciones `calculate_maturity_value` (R001) y `calculate_letra_yield` (R002–R004).
Se eliminó `_motor_letras/` y su manifiesto de copia. El panel conserva su alcance
LECAP/BONCAP en pesos; R006 sigue sin aprobación. Cambios futuros del motor requieren
revisar y actualizar explícitamente la dependencia fija. No cambian fórmulas ni números.

El VPV contractual conserva la capitalización y el 30/360 adaptado del Tesoro del Toolkit. El rendimiento de compra usa el precio limpio manual y los días corridos reales desde su liquidación hasta vencimiento (ACT/365). La TEM de emisión es contractual: no se confunde con el rendimiento del comprador. Los gastos quedan en los costos patrimoniales existentes; el rendimiento indicativo del panel no los incluye. El HTML presenta el pago y el rendimiento con dos decimales (redondeo HALF_EVEN solo de presentación); el cálculo y el JSON conservan sus decimales originales. Precio de compra y nominales conservan los decimales informados.

El contador visible es vencimiento menos **hoy en Argentina**, en días corridos, incluidos fines de semana y feriados. Se actualiza cada minuto con la página abierta, aun sin conexión; el navegador puede demorar temporizadores de pestañas suspendidas. No se infiere T+1 ni un calendario de feriados: se carga la liquidación real.

El pago esperado es cantidad vigente / base nominal × VPV. Se muestra aparte: no modifica la valuación a precios de mercado, el efectivo, el resultado completo, el realizado ni el día cero. No calcula el precio ni el resultado de una venta anticipada; esa venta conserva el tratamiento existente.

Un bono capitalizable (BONCAP) también se carga con tipo `letra`, aunque el mercado lo liste como bono: su precio se busca en el panel de letras y, si no está, en el de bonos ([PRECIOS.md](PRECIOS.md)).

## Datos contractuales manuales

En `instrumentos.json`, sin cambiar su vencimiento existente:

```json
{
  "LETRA_DEMO": {
    "vencimiento": "2027-06-30",
    "letra": {
      "familia": "LECAP",
      "moneda_pago": "ARS",
      "fecha_emision": "2026-06-30",
      "tem_emision": "0.02",
      "base_nominal": "100",
      "fuente": "Condiciones contractuales ficticias para demostración"
    }
  }
}
```

Todos los números financieros se escriben con punto decimal y sin separador de miles. `0.02` significa 2% mensual. `base_nominal` declara la base del VPV contractual; no se inventa un valor por defecto. El precio manual de compra siempre se carga **por 100 nominales**, como cotizan las letras en cartera. Para el rendimiento se convierte el VPV a esa misma base de 100. Cambiar únicamente la base de expresión del contrato no cambia el rendimiento ni el pago. Emisión, vencimiento, familia y fuente deben corresponder al contrato de esa especie. Si faltan datos, se informa qué falta; nunca se usa cero como reemplazo.

## Precio de cada compra

No se extrae un precio limpio de `costo / cantidad`: el costo importado incluye gastos y los movimientos USD se convierten a ARS. El precio limpio **por cada 100 nominales** se carga aparte, sin modificar la base ni el CSV de nueve columnas. La moneda del precio se declara y nunca se infiere del importe neto.

`letras --cliente SLUG` lista las referencias de compra y su cantidad remanente. `precio-letra --cliente SLUG --referencia base:1 --precio 110.50 --moneda ARS --liquidacion 2026-07-01` asocia el precio a una compra concreta. Para movimientos se usa, por ejemplo, `movimiento:3`. Los índices comienzan en 1: lotes originales de la base o filas de datos leídas de movimientos (incluidos otros tipos de movimiento).

El archivo generado `compras_letras.json` usa `esquema_version=1` y una lista `compras` con `referencia`, `huella`, `precio`, `moneda` y `fecha_liquidacion`. La huella verifica el registro fuente completo. Si se corrige o reordena la fuente y deja de coincidir, el precio no se reasocia: se avisa y se vuelve a cargar explícitamente. Las referencias totalmente vendidas se conservan; no se muestran como tenencia actual. Al corregir un precio se reemplaza atómicamente el archivo; una falla no altera el anterior.

Compras sin precio siguen visibles como pendientes. La liquidación no puede ser anterior a la compra ni futura respecto de hoy en Argentina; para el rendimiento debe ser anterior al vencimiento y no preceder la emisión contractual. No se promedia el precio de varias compras: se muestran sus detalles y rendimientos separados. Si los lotes y la posición tienen una diferencia por la tolerancia de importación, se muestra esa diferencia y el pago agregado usa la posición vigente, sin inventar un lote.

## Dólar linked

Felipe identificó **D30S6** como ejemplo, no como dato de cliente. La resolución conjunta 13/2026, artículo 5, establece emisión 16/03/2026, vencimiento 30/09/2026, cero cupón y pago en ARS al A3500 del tercer día hábil anterior a la amortización: https://www.argentina.gob.ar/normativa/nacional/resoluci%C3%B3n-13-2026-423892/texto

La investigación R006 del Toolkit continúa `Implementation Approved: No`. El panel admite familia `LELINK` y moneda de pago `ARS` **solo para identificarla y listar datos**, con aviso de cálculo pendiente de validación. No publica VPV, pago ni rendimiento para esa familia. No transforma el MEP ni el dólar actual en un tipo de cambio de pago. Tampoco se habilitan letras pagaderas en dólares, CER o TAMAR usando la fórmula de LECAP.

## Compatibilidad

Sin cambios al esquema de cartera importada, a los movimientos existentes, a las pruebas originales, a los fixtures ni a la política de seguridad del HTML. El panel funciona sin fuentes remotas adicionales. La descarga Excel existente mantiene sus hojas: esta ampliación es de pantalla, no agrega una hoja financiera nueva.
