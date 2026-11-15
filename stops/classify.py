"""Clasifica cada estacion y dia productivo por el tipo de parada que domina. Sin modelo.

Reglas en orden de prioridad; la primera que se cumple decide el tipo:

1. error_registro  la estacion no registra nada (sin_datos) o esta fuera de servicio.
2. sensor          mas paradas propias que piezas con un contador creible
                   (flag sensor_sospechoso del EDA: NAP > NPR).
3. error_registro  contador de piezas roto o doble.
4. Si las perdidas TAP + DES + SAT llegan a PERDIDA_MIN_H, manda la mayor:
                   SAT -> saturacion, DES -> desabastecimiento,
                   TAP -> microparada (menos de MICRO_S s por parada) o parada_larga.
5. ok              dia sin perdidas relevantes.

Las filas con mas horas que el tiempo requerido (tr_mayor) o con menos (tr_menor) se
clasifican con las horas ya reescaladas por el EDA y quedan marcadas en `marcas`.

Los subconjuntos (bloque "subconjunto") salen de `subassemblies` en lines/<linea>.json.

Uso, desde la raiz del repo:
    python stops/classify.py --line VLL_MONTAJE_L5
Escribe data/processed/<linea>/stops.csv y stops_resumen.csv.
"""

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from backend.pipeline.settings import LINES_DIR, load_settings, num, read_line_file  # noqa: E402

PROCESSED = ROOT / "data" / "processed"

# Nombres de los tipos. Los usa backend/logic/status.py: cambiar solo los valores de la derecha.
TIPOS = {
    "error_registro": "error_registro",
    "sensor": "sensor",
    "saturacion": "saturacion",
    "desabastecimiento": "desabastecimiento",
    "microparada": "microparada",
    "parada_larga": "parada_larga",
    "ok": "ok",
}

MICRO_S = 60.0  # una parada propia mas corta que esto es una microparada (s)
PERDIDA_MIN_H = 1.0  # por debajo de estas horas perdidas (TAP + DES + SAT) el dia es ok

PERDIDAS = ["tap_h", "des_h", "sat_h"]
MARCAS = ["tr_mayor", "tr_menor"]


def load_clean(line: str, processed: Path = PROCESSED) -> pd.DataFrame:
    """Filas de clean.csv de los dias productivos."""
    df = pd.read_csv(processed / line / "clean.csv", parse_dates=["fecha"])
    return df[~df["no_productivo"]].reset_index(drop=True)


def bloque(df: pd.DataFrame, line: str, lines_dir: Path = LINES_DIR) -> pd.Series:
    """linea, subconjunto o manipulador (fuera del flujo segun LineSettings)."""
    subs = read_line_file(line, lines_dir).get("subassemblies", [])
    missing = set(subs) - set(df["Operacion"])
    if missing:
        raise ValueError(f"Subconjuntos que no estan en los datos: {sorted(missing)}")
    out = pd.Series("linea", index=df.index)
    out[df["Operacion"].isin(subs)] = "subconjunto"
    out[df["grupo"] == "fuera_flujo"] = "manipulador"
    return out


def seconds_per_stop(df: pd.DataFrame) -> pd.Series:
    """Duracion media de una parada propia en segundos. NaN si no hay paradas contadas."""
    return 3600 * df["tap_h"] / df["NAP"].replace(0, np.nan)


# --- Reglas: cada una devuelve una mascara booleana sobre las filas ---------------------

def rule_sin_registro(df: pd.DataFrame) -> pd.Series:
    return df["sin_datos"] | df["fuera_servicio"]


def rule_sensor(df: pd.DataFrame) -> pd.Series:
    return df["sensor_sospechoso"]


def rule_contador(df: pd.DataFrame) -> pd.Series:
    return df["contador_roto"] | df["contador_doble"]


def rule_con_perdidas(df: pd.DataFrame) -> pd.Series:
    return df[PERDIDAS].sum(axis=1) >= PERDIDA_MIN_H


def dominant_loss(df: pd.DataFrame) -> pd.Series:
    """Perdida mayor del dia. En empate gana TAP, luego DES (orden de PERDIDAS)."""
    return df[PERDIDAS].idxmax(axis=1)


# --- Clasificacion ------------------------------------------------------------------------

def _loss_type(dom: pd.Series, secs: pd.Series) -> pd.Series:
    by_loss = dom.map({"sat_h": TIPOS["saturacion"], "des_h": TIPOS["desabastecimiento"]})
    # TAP sin paradas contadas (NAP = 0) cuenta como parada larga: no son microparadas.
    own = np.where(secs < MICRO_S, TIPOS["microparada"], TIPOS["parada_larga"])
    return by_loss.where(dom != "tap_h", pd.Series(own, index=dom.index))


def _reason(df: pd.DataFrame, tipo: pd.Series, secs: pd.Series) -> pd.Series:
    """Frase corta con el dato que decide el tipo."""
    perdida = df[PERDIDAS].sum(axis=1)
    out = []
    for i, t in tipo.items():
        r = df.loc[i]
        if t == TIPOS["error_registro"]:
            causes = [c.replace("_", " ") for c in
                      ["sin_datos", "fuera_servicio", "contador_roto", "contador_doble"] if r[c]]
            out.append(", ".join(causes))
        elif t == TIPOS["sensor"]:
            out.append(f"NAP {int(r['NAP'])} > NPR {int(r['NPR'])}")
        elif t == TIPOS["ok"]:
            out.append(f"{num(perdida[i])} h perdidas, menos de {num(PERDIDA_MIN_H)} h")
        else:
            col = {TIPOS["saturacion"]: "sat_h", TIPOS["desabastecimiento"]: "des_h"}.get(t, "tap_h")
            txt = f"{col[:3].upper()} {num(r[col])} h de {num(perdida[i])} h perdidas"
            if col == "tap_h":
                txt += ", sin paradas contadas" if np.isnan(secs[i]) else f", {num(round(secs[i]))} s por parada"
            out.append(txt)
    return pd.Series(out, index=tipo.index)


def classify(df: pd.DataFrame, line: str) -> pd.DataFrame:
    """Una fila por estacion y dia productivo con su tipo y el motivo."""
    if df["no_productivo"].any():
        raise ValueError("classify() espera solo dias productivos")
    secs = seconds_per_stop(df)
    loss = _loss_type(dominant_loss(df), secs)

    tipo = pd.Series(TIPOS["ok"], index=df.index)
    # De menor a mayor prioridad: cada regla pisa a las anteriores.
    tipo[rule_con_perdidas(df)] = loss
    tipo[rule_contador(df)] = TIPOS["error_registro"]
    tipo[rule_sensor(df)] = TIPOS["sensor"]
    tipo[rule_sin_registro(df)] = TIPOS["error_registro"]

    marcas = df[MARCAS].apply(lambda r: ",".join(c for c in MARCAS if r[c]), axis=1)
    return pd.DataFrame({
        "op": df["Operacion"], "fecha": df["fecha"].dt.strftime("%Y-%m-%d"), "orden": df["Orden_OP"],
        "bloque": bloque(df, line), "tipo": tipo, "motivo": _reason(df, tipo, secs),
        "tap_h": df["tap_h"].round(3), "des_h": df["des_h"].round(3), "sat_h": df["sat_h"].round(3),
        "NAP": df["NAP"], "s_por_parada": secs.round(1), "marcas": marcas,
    }).sort_values(["fecha", "orden"]).reset_index(drop=True)


def summary(stops: pd.DataFrame) -> pd.DataFrame:
    """Dias de cada tipo por estacion y el tipo mas frecuente."""
    counts = pd.crosstab(stops["op"], stops["tipo"]).reindex(columns=list(TIPOS.values()), fill_value=0)
    meta = stops.groupby("op")[["orden", "bloque"]].first()
    out = meta.join(counts)
    out["tipo_principal"] = counts.idxmax(axis=1)
    return out.sort_values("orden")


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("--line", default="VLL_MONTAJE_L5")
    args = p.parse_args()

    df = load_clean(args.line)
    load_settings(args.line, df)  # valida lines/<linea>.json contra los datos
    stops = classify(df, args.line)
    res = summary(stops)
    out = PROCESSED / args.line
    stops.to_csv(out / "stops.csv", index=False)
    res.to_csv(out / "stops_resumen.csv")
    print(f"{len(stops)} estacion-dia, {stops['op'].nunique()} estaciones, {stops['fecha'].nunique()} dias")
    print(stops["tipo"].value_counts().to_string())
    print(f"Escrito {out / 'stops.csv'} y stops_resumen.csv")


if __name__ == "__main__":
    main()
