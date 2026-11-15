"""Regla de las flechas (Kuo, Lim y Meerkov, 1996): qué máquina frena la línea.

Cada tramo de cada línea es una cadena: sus máquinas del grupo principal con
dato válido, ordenadas por Orden_OP (sin tramos declarados, la línea entera es
un solo tramo). Las excluidas se saltan y sus vecinas pasan a ser contiguas. Un grupo en paralelo es un solo nodo: la media de sus máquinas,
en la posición de la primera. Para cada par consecutivo (a, b), con SAT y
DES en cuota del tiempo requerido (no del registrado, para no repartir el
tiempo que falta en una fila corta):

    SAT de a > DES de b  →  flecha "→": a se bloquea más de lo que b espera,
                             el problema está aguas abajo
    SAT de a < DES de b  →  flecha "←": el problema está aguas arriba

Una máquina frena la línea si las flechas convergen en ella (→ por la
izquierda y ← por la derecha). Como en el método original, la primera y la
última también pueden: basta el lado que existe. Si hay varias, manda la
severidad:

    S_i = (SAT_ant - DES_i) + (DES_sig - SAT_i)
"""

import numpy as np
import pandas as pd

from . import schema as s
from .config import LogicConfig

RIGHT = "→"
LEFT = "←"
TIE = "="
REQUIRED_TIME = "required_time_h"  # tiempo requerido de la fila: 22 h un día, 22 h × días un acumulado
_EPS = 1e-9  # tolerancia numérica para decidir el sentido de una flecha


def arrow_rule(
    df: pd.DataFrame, period: str, config: LogicConfig
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Aplica la regla en cada línea, tramo y periodo.

    `period` es la columna que separa los periodos (un día, o un acumulado).
    Necesita `exclusion`, `Paralelo`, `Tramo` y `required_time_h`.

    Devuelve (máquinas, flechas):
    - máquinas: una fila por máquina de la cadena, con el nodo al que
      pertenece, sus vecinas, si frena la línea, su severidad y las horas que
      hace perder a cada vecina (SAT de la anterior y DES de la siguiente,
      solo si frena la línea). En un grupo en paralelo, esas horas se reparten
      a partes iguales entre sus máquinas.
    - flechas: una fila por par de nodos consecutivos, con su sentido y a qué
      nodo apunta. Un grupo en paralelo aparece con su nombre, "ST2376+ST-2375".
    """
    keys = [s.LINE, period, s.SEGMENT]
    in_chain = df["exclusion"].isna() & (df[s.GROUP] == config.main_group)
    rows = df.loc[in_chain, [*keys, s.OP, s.ORDER, s.PARALLEL, s.SAT, s.DES, REQUIRED_TIME]].copy()
    rows["node"] = rows[s.PARALLEL].where(rows[s.PARALLEL].notna(), rows[s.OP])
    rows["sat_share"] = rows[s.SAT] / rows[REQUIRED_TIME]
    rows["des_share"] = rows[s.DES] / rows[REQUIRED_TIME]
    chain = (
        rows.groupby([*keys, "node"], as_index=False)
        .agg(
            **{s.ORDER: (s.ORDER, "min"), s.SAT: (s.SAT, "mean"), s.DES: (s.DES, "mean")},
            sat_share=("sat_share", "mean"),
            des_share=("des_share", "mean"),
            members=(s.OP, "size"),
        )
        .sort_values([*keys, s.ORDER, "node"])
        .reset_index(drop=True)
    )
    g = chain.groupby(keys, sort=False)
    prev_sat_share = g["sat_share"].shift(1)
    next_des_share = g["des_share"].shift(-1)

    nodes = chain[[*keys, "node", "members"]].copy()
    nodes["prev_op"] = g["node"].shift(1)
    nodes["next_op"] = g["node"].shift(-1)
    left = prev_sat_share - chain["des_share"]    # > 0: la flecha de la izquierda apunta a i
    right = next_des_share - chain["sat_share"]   # > 0: la flecha de la derecha apunta a i
    is_bn = (nodes["prev_op"].isna() | (left > _EPS)) & (nodes["next_op"].isna() | (right > _EPS))
    nodes["is_bottleneck"] = is_bn
    nodes["severity"] = (left.fillna(0) + right.fillna(0)).where(is_bn)
    nodes["induced_on_prev_h"] = g[s.SAT].shift(1).where(is_bn, 0.0).fillna(0.0)
    nodes["induced_on_next_h"] = g[s.DES].shift(-1).where(is_bn, 0.0).fillna(0.0)

    machines = rows[[*keys, s.OP, "node"]].merge(nodes, on=[*keys, "node"])
    for col in ("induced_on_prev_h", "induced_on_next_h"):
        machines[col] = machines[col] / machines["members"]

    has_next = nodes["next_op"].notna()
    arrows = pd.DataFrame(
        {
            s.LINE: chain[s.LINE],
            period: chain[period],
            s.SEGMENT: chain[s.SEGMENT],
            "from": chain["node"],
            "to": nodes["next_op"],
            "sat_share_from": chain["sat_share"],
            "des_share_to": next_des_share,
        }
    )[has_next].reset_index(drop=True)
    diff = arrows["sat_share_from"] - arrows["des_share_to"]
    arrows["direction"] = np.select([diff > _EPS, diff < -_EPS], [RIGHT, LEFT], TIE)
    arrows["points_to"] = np.select(
        [diff > _EPS, diff < -_EPS], [arrows["to"], arrows["from"]], None
    )
    return machines.drop(columns=["node", "members"]), arrows
