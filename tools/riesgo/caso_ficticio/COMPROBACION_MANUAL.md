# Controles independientes del caso ficticio

Datos 100% sintéticos. Ninguna observación representa un activo de mercado.

1. **Concentración:** los pesos de `parametros.json` son 0,20; 0,20; 0,15; 0,20; 0,15; 0,10. Sumar sus cuadrados da `3*0,04+2*0,0225+0,01=0,175`. El número efectivo es `40/7=5,714285714286`. Se compara con `cartera.concentracion` en `esperado.json`.
2. **Bono cero, sin usar la rutina general de flujos:** por nominal100, dos años y tasa anual10%, precio `100/(11/10)^2=10000/121=82,644628099174`. Macaulay2 años; modificada `20/11=1,818181818182`; convexidad `600/121=4,958677685950`. DV01 `20/1331=0,015026296018`. Para +100pb, el precio exacto es `1000000/12321=81,162243324406`; retorno `12100/12321−1=−0,0179368557747`. Se compara con `bonos.BONO_CERO`, escenario `cambio_pb=100`.
3. **CEDEAR teórico auxiliar:** subyacente100, CCL1000, ratio10: precio10000 ARS. Después subyacente110, CCL1200, ratio10: precio13200. Retorno `13200/10000−1=0,32`, incluidos 2 puntos porcentuales de interacción. Se compara con `otros.cedear_retorno`.
4. **Control de varianza ajeno al patrón generador:** retornos −0,02;0;+0,02, media0, suma de cuadrados0,0008. Con n−1=2, varianza0,0004 y desvío0,02. Con semilla EWMA0,0004, λ0,94 y retorno0,01, siguiente varianza0,000382. Se ejecutan como controles independientes en `comprobar.py`.

Los precios son series sintéticas de retorno total ajustado. Las series de bonos se escalan para que su último valor coincida con el precio sucio de sus flujos/TIR al corte; no se calibró una trayectoria de tasas histórica ni se agregan cupones otra vez. Las fechas son sesiones ficticias de lunes a viernes; no representan feriados argentinos. El patrimonio100000 es una escala de análisis; los precios de las columnas no implican que se tenga una unidad de cada activo.

El caso aplica pesos constantes: la serie hipotética supone rebalanceo diario, no buy-and-hold. `precios.csv` está en USD por CCL ficticio, incluso CED_B. `factores.csv` contiene mercado, CCL, IPC y rf ficticios; no hay consultas de mercado.

No regenerar `esperado.json` al probar una implementación nueva: conservarlo y comparar sus resultados. Las diferencias flotantes se aceptan con rtol1e−10 y atol1e−12 para este caso en precisión doble. Monte Carlo fija semilla1729, generador `random.Random` y 10000 muestras; un generador diferente debe compararse con tolerancia estadística, no exigir identidad bit a bit.
