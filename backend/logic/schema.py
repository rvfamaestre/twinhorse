"""Columnas de entrada de la lógica de paradas.

Una fila por máquina y día. La limpieza (Rol 1) entrega este formato; mientras
tanto, `loaders.load_raw` lo construye a partir de los CSV en bruto.
"""

# Identificación y jerarquía
PLANT = "Planta"        # opcional: si falta, se deduce del prefijo de la línea
LINE = "Linea"
OP = "Operacion"
ORDER = "Orden_OP"
GROUP = "Grupo"         # opcional: solo el grupo principal forma la cadena y el ranking
PARALLEL = "Paralelo"   # opcional: grupo en paralelo, "ST2376+ST-2375"
SEGMENT = "Tramo"       # opcional: cada tramo es una cadena en serie aparte
DAY = "day"             # fecha ISO, "2026-09-29"
FLAGS = "flags"         # opcional: lista de flags de la limpieza (o texto "a;b")

# Tiempos (horas) y contadores
TBF = "TBF"   # buen funcionamiento
TAP = "TAP"   # parada propia
DES = "DES"   # desabastecimiento: le faltan piezas de la anterior
SAT = "SAT"   # saturación: la siguiente no le acepta la pieza
NAP = "NAP"   # número de paradas propias
NPR = "NPR"   # piezas reales producidas

HOURS = [TBF, TAP, DES, SAT]
COUNTS = [NAP, NPR]
REQUIRED = [LINE, OP, ORDER, DAY, *HOURS, *COUNTS]


def as_flags(value) -> tuple[str, ...]:
    """Normaliza los flags de una fila: lista, array (parquet), texto "a;b" o vacío."""
    if value is None or (isinstance(value, float) and value != value):
        return ()
    if isinstance(value, str):
        value = value.split(";")
    return tuple(sorted({str(f).strip() for f in value if str(f).strip()}))
