# Instrucciones para Codex

Construís `cartera`, una herramienta interna de seguimiento de carteras de
clientes para un asesor del mercado de capitales argentino. Corre local en una
Mac. No opera, no da órdenes y no la usa el cliente final.

## Reparto del trabajo

- **Codex** implementa, una etapa de `PLAN.md` por vez.
- **Claude** escribió esta especificación y revisa cada etapa contra los datos
  reales del cliente, a los que Codex no tiene acceso.
- **Felipe**, el asesor, decide alcance y criterios.

## Antes de escribir código

Leé en este orden:

1. `PLAN.md`: etapas y criterios de "listo".
2. `docs/CONTRATO.md`: la API pública que las pruebas esperan.
3. `docs/DOMINIO.md`: convenciones de cálculo. Sin esto los números salen mal.
4. `docs/FORMATOS.md`: archivos de entrada y de salida.
5. `docs/PRECIOS.md`: la fuente de precios y sus límites.
6. `docs/DASHBOARD.md`: reglas de la pantalla, para la etapa 3.

## Cómo trabajar

- Hacé **una sola etapa** y frená. Al terminar, informá: qué hiciste, el resultado
  de las pruebas y cualquier duda o desvío respecto de la especificación.
- Una etapa está lista cuando pasan sus pruebas y las de las etapas anteriores:

  ```bash
  PYTHONPATH=src python3 -m unittest discover -s tests -p 'test_etapa1*' -v
  ```

- **No modifiques `tests/`, `fixtures/` ni `docs/` para hacer pasar una prueba.**
  Si creés que una prueba o la especificación están mal, frená y explicá por qué.
  Podés agregar pruebas propias en archivos nuevos, `tests/test_extra_*.py`.
- No agregues funciones fuera de la etapa en curso.
- No hagas commits ni instales nada global salvo que te lo pidan.

## Restricciones técnicas

- Python **3.9**: nada de `match`, ni `X | Y` en anotaciones evaluadas en ejecución.
- Solo biblioteca estándar más `openpyxl`. Si necesitás otra dependencia, preguntá.
- Entorno virtual **fuera de esta carpeta**, que está en OneDrive:
  `~/.venvs/cartera`.
- Código e identificadores en español, como en `docs/CONTRATO.md`.
- El dashboard es un único HTML sin CDN ni dependencias externas: lo único remoto
  que consulta es la API de precios.

## Datos y privacidad

- **Esta carpeta no contiene ni debe contener datos reales de clientes.** Trabajá
  solo con `fixtures/`.
- Los datos reales viven fuera, en la ruta de `--datos` o de la variable de entorno
  `CARTERA_DATOS`. No busques ni abras nada fuera de esta carpeta.
- Nunca escribas salidas dentro de esta carpeta salvo en carpetas temporales de
  prueba. Las salidas van a la ruta de datos.
- Las credenciales, como el token de Telegram, se leen de variables de entorno. Nunca
  se guardan en un archivo ni se muestran en logs.
- Los avisos por Telegram identifican al cliente por su `slug`, sin nombre ni importes.

## Reglas de negocio que no se negocian

- **Nunca inventar un dato faltante.** Sin costo, se muestra "falta estimar". Sin
  precio, se muestra "sin dato". Jamás un cero.
- **Distinguir siempre lo observado de lo estimado.** Un costo estimado se ve como
  estimado en toda salida.
- **Un silencio no puede parecer un "todo en orden".** Si no se pudo chequear, se dice.
- **El efectivo no se suma a las posiciones** como si fuera una más.
- **Nada de acceso al broker** con credenciales del cliente ni scraping.
