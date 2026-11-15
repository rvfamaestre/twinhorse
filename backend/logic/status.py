"""Estado de cada máquina en un periodo: por qué se para."""

import pandas as pd

from . import schema as s
from .config import LogicConfig

OUT_OF_SERVICE = "fuera_servicio"
UNRELIABLE = "dato_no_fiable"
OK = "ok"
SLOW = "lenta"                       # casi no se para, pero su ciclo pasa del objetivo
# Nombres oficiales del reto (diapositiva 4)
OWN = "parada_propia"                # TAP: la máquina se para sola
INDUCED_PREV = "desabastecimiento"   # DES: le faltan piezas de la anterior
INDUCED_NEXT = "saturacion"          # SAT: la siguiente no le acepta la pieza

STATUSES = (OUT_OF_SERVICE, UNRELIABLE, OK, SLOW, OWN, INDUCED_PREV, INDUCED_NEXT)
EXCLUDED = (OUT_OF_SERVICE, UNRELIABLE)

# Para la leyenda del dashboard: etiqueta y familia. DES y SAT forman la parada inducida (TAI).
STATUS_INFO = {
    OUT_OF_SERVICE: ("Fuera de servicio", "excluida"),
    UNRELIABLE: ("Dato no fiable", "excluida"),
    OK: ("Cumple Dp y Tcy", "ok"),
    SLOW: ("Tcy por encima del objetivo", "ciclo"),
    OWN: ("Parada propia (TAP)", "parada_propia"),
    INDUCED_PREV: ("Desabastecimiento (DES)", "parada_inducida"),
    INDUCED_NEXT: ("Saturación (SAT)", "parada_inducida"),
}

# Tipos de stops/classify.py (claves de su TIPOS) que son una pérdida → estado oficial.
# Sus microparada y parada_larga son subtipos de la parada propia. Su "ok" usa otro umbral
# y su error_registro incluye el contador roto, así que esos no tienen equivalencia directa.
STOP_TYPE_TO_STATUS = {
    "microparada": OWN,
    "parada_larga": OWN,
    "desabastecimiento": INDUCED_PREV,
    "saturacion": INDUCED_NEXT,
}

_LOSS_STATUS = {s.TAP: OWN, s.DES: INDUCED_PREV, s.SAT: INDUCED_NEXT}


def exclusion_from_flags(flags: tuple[str, ...], config: LogicConfig) -> str | None:
    """Estado de exclusión que imponen los flags de la limpieza, o None si la fila vale."""
    if config.flag_out_of_service in flags:
        return OUT_OF_SERVICE
    if config.flag_unreliable in flags:
        return UNRELIABLE
    return None


def classify(df: pd.DataFrame, config: LogicConfig) -> pd.Series:
    """Estado de cada fila, por este orden:

    1. La exclusión de la columna `exclusion` (fuera_servicio o dato_no_fiable).
    2. Si Dp >= dp_min y TAI / TR <= tai_max, apenas pierde tiempo por paradas:
       ok si además Tcy <= tcy_max (o no se puede medir), lenta si no.
    3. Si no, la mayor de las tres pérdidas: TAP → parada_propia,
       DES → desabastecimiento, SAT → saturacion. En empate gana TAP, después DES.

    Necesita las columnas de `kpis.add_kpis` y la columna `exclusion`.
    """
    targets = df[s.LINE].map(config.targets)
    few_stops = (df["dp"] >= targets.map(lambda t: t.dp_min)) & (
        df["tai_share"] <= targets.map(lambda t: t.tai_max)
    )
    slow = df["tcy_cmin"] > targets.map(lambda t: t.tcy_max_cmin)
    worst = df[[s.TAP, s.DES, s.SAT]].idxmax(axis=1).map(_LOSS_STATUS)
    status = worst.where(~few_stops, OK).where(~(few_stops & slow), SLOW)
    return df["exclusion"].where(df["exclusion"].notna(), status)
