# cartera

Seguimiento interno de carteras de clientes. Instrucciones para el desarrollo en
[AGENTS.md](AGENTS.md) y etapas en [PLAN.md](PLAN.md).

## Preparar el entorno

```bash
python3 -m venv ~/.venvs/cartera
~/.venvs/cartera/bin/pip install -r requirements.txt
```

## Correr las pruebas

```bash
PYTHONPATH=src ~/.venvs/cartera/bin/python -m unittest discover -s tests -v
```

Esta carpeta no contiene datos reales de clientes.
