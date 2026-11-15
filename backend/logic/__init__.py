"""Lógica de paradas del reto LOSSIA: por qué se para cada máquina y cuál frena la línea.

    from backend.logic import analyze, load_clean
    analysis = analyze(load_clean("data/processed"))   # la limpieza de Rol 1
    analysis.totals        # una fila por máquina, con estado, índice y frase
    analysis.to_dict()     # salida jerárquica para el dashboard
"""

from .config import LogicConfig, Targets
from .loaders import (
    flag_non_productive_days,
    from_clean,
    load_clean,
    load_raw,
    read_table,
    to_logic_input,
)
from .pipeline import Analysis, analyze

__all__ = [
    "Analysis",
    "LogicConfig",
    "Targets",
    "analyze",
    "flag_non_productive_days",
    "from_clean",
    "load_clean",
    "load_raw",
    "read_table",
    "to_logic_input",
]
