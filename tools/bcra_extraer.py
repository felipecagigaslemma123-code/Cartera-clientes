#!/usr/bin/env python3
"""Descarga una muestra de CER, TAMAR privada TNA y A3500 del BCRA."""

from pathlib import Path
import sys

from market_data.providers.bcra import BCRAError as ErrorBCRA, URL, SERIES, extract as extraer
from market_data.bcra_cli import main as _main


def main(argumentos=None, *, fetch=None):
    return _main(argumentos, fetch=fetch, project_root=Path(__file__).resolve().parents[1])


if __name__ == "__main__":
    sys.exit(main())
