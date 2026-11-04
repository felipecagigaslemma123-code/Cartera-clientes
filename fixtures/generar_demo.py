"""Genera punto_partida_demo.xlsx. Todos los datos son inventados.

Las celdas con fórmula quedan sin valor calculado, igual que en un archivo que
nunca se abrió en Excel. El importador tiene que tolerarlo.
"""
import datetime as dt
from pathlib import Path

from openpyxl import Workbook

CARTERA = [
    ("AAA", "CEDEAR Demo A", "cedear", 100, 1, 1200),
    ("BBB", "CEDEAR Demo B", "cedear", 50, 1, 1100),
    ("CCC", "Accion Demo C", "accion", 10, 1, 2500),
    ("BOND1", "Bono Demo", "bono", 1000, 100, 160000),
    ("NOTE1", "Letra Demo", "letra", 200000, 100, 110),
    ("ONX", "ON Demo", "on", 500, 100, 150000),
]

# ticker, cantidad, origen, fecha, cotiza, precio (solo a estimar), costo (solo extracto), nota
LOTES = [
    ("AAA", 60, "Extracto", dt.datetime(2026, 3, 10), 1, None, 60600.00, ""),
    ("AAA", 40, "Extracto", dt.datetime(2026, 4, 10), 1, None, 44000.00, ""),
    ("BBB", 30, "Extracto", dt.datetime(2026, 5, 5), 1, None, 33000.00, ""),
    ("BBB", 20, "A estimar", dt.datetime(2025, 6, 1), 1, 900.0, None, "Estimado"),
    ("CCC", 10, "A estimar", dt.datetime(2025, 1, 15), 1, 2000.0, None, "Estimado"),
    ("BOND1", 1000, "A estimar", None, 100, None, None, "Falta la fecha"),
    ("NOTE1", 200000, "Extracto", dt.datetime(2026, 9, 1), 100, None, 210000.00, ""),
    ("ONX", 300, "Extracto", dt.datetime(2026, 4, 22), 100, None, 450000.00, ""),
    ("ONX", 200, "A estimar", None, 100, None, None, "Falta la fecha"),
]


def generar(destino):
    libro = Workbook()
    cartera = libro.active
    cartera.title = "Cartera"
    lotes = libro.create_sheet("Lotes")

    cartera["A1"] = "Punto de partida de demostracion"
    for columna, titulo in enumerate(
        ["Ticker", "Especie", "Tipo", "Cantidad", "Cotiza cada", "Precio de hoy", "Valuacion"], 1
    ):
        cartera.cell(4, columna, titulo)
    for fila, (ticker, especie, tipo, cantidad, cotiza, precio) in enumerate(CARTERA, 5):
        cartera.cell(fila, 1, ticker)
        cartera.cell(fila, 2, especie)
        cartera.cell(fila, 3, tipo)
        cartera.cell(fila, 4, cantidad)
        cartera.cell(fila, 5, cotiza)
        cartera.cell(fila, 6, precio)
        cartera.cell(fila, 7, f"=D{fila}*F{fila}/E{fila}")
    total = 5 + len(CARTERA)
    cartera.cell(total, 1, "Total")
    cartera.cell(total, 7, f"=SUM(G5:G{total - 1})")

    lotes["A1"] = "Lotes de compra"
    for columna, titulo in enumerate(
        ["Ticker", "Cantidad", "Origen", "Fecha", "Cotiza cada", "Precio", "Costo", "Nota"], 1
    ):
        lotes.cell(4, columna, titulo)
    for fila, (ticker, cantidad, origen, fecha, cotiza, precio, costo, nota) in enumerate(LOTES, 5):
        lotes.cell(fila, 1, ticker)
        lotes.cell(fila, 2, cantidad)
        lotes.cell(fila, 3, origen)
        lotes.cell(fila, 4, fecha)
        lotes.cell(fila, 5, cotiza)
        lotes.cell(fila, 8, nota)
        if origen == "Extracto":
            lotes.cell(fila, 6, f"=G{fila}/B{fila}*E{fila}")
            lotes.cell(fila, 7, costo)
        else:
            lotes.cell(fila, 6, precio)
            lotes.cell(fila, 7, f'=IF(F{fila}="","",B{fila}*F{fila}/E{fila})')
    libro.save(destino)


if __name__ == "__main__":
    generar(Path(__file__).with_name("punto_partida_demo.xlsx"))
