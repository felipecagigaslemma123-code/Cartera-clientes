# Entrega

Leer primero [RIESGO.md](RIESGO.md): metodología, citas, decisiones argentinas, datos, algoritmos, resultados ejecutados y límites.

Ejecutar desde la carpeta del encargo:

```sh
python3 -B entrega/verificacion/comprobar.py
```

Para probar sólo el caso, sin necesitar los originales de bibliografía:

```sh
python3 -B entrega/verificacion/comprobar.py --solo-caso
```

Python3.9, sólo biblioteca estándar. El control completo lee los Excel originales como ZIP/XML; no necesita openpyxl. `riesgo_ref.py` contiene las fórmulas puras; `caso.py` lee los CSV. El oráculo está en [esperado.json](verificacion/caso_ficticio/esperado.json) y sus controles independientes en [COMPROBACION_MANUAL.md](verificacion/caso_ficticio/COMPROBACION_MANUAL.md).

`generar_caso.py` está para regeneración explícita de los datos ficticios. No usarlo antes de cada prueba: sustituiría el resultado esperado. Los mínimos de historia, metadatos, calendarios y estados `sin dato` son parte del contrato de RIESGO.md, que el consumidor debe aplicar antes de publicar las operaciones algebraicas.

La salida completa se conserva en [salida.txt](verificacion/salida.txt). Hay coincidencias numéricas y diferencias bibliográficas explícitas: histórico de VOL sin resultado guardado válido; ES de Bodie inconsistente con su cola impresa; matriz de covarianzas inválida en otra clase. data912 respondió403; no se verificó su esquema ni largo. No se modificaron originales ni se implementó `cartera`.

El inventario y alcance por archivo están en `fuentes/`. Los scripts `extraer.py`, `buscar_fuentes.py`, `ocr.swift` y `consultar_data.py` registran el procedimiento de investigación; los tres primeros son auxiliares de extracción/renderizado, no dependencias de la verificación. `extraer.py` requiere pypdf y openpyxl si se vuelve a ejecutar; los scripts de verificación no. El intento OCR de Apple Vision falló, y las páginas críticas escaneadas se revisaron visualmente.
