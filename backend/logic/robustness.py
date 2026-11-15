"""Pruebas de robustez: ¿cambia la conclusión si cambia una decisión de limpieza o de topología?

Cada escenario cambia una sola cosa respecto al base y lo recalcula todo:
- sin reescalar: las filas de más de 22 h, con sus horas originales.
- tiempo que falta = parada propia / falta de piezas / bloqueo: en las filas
  cortas, el hueco hasta el tiempo requerido se suma entero a esa pérdida. Es el
  peor caso de cada lectura del tiempo sin registrar.
- cada hipótesis de tramos de lines/<Linea>.json ("hipotesis_tramos").

    python -m backend.logic.robustness --clean data/processed --out data/processed/logic/robustez.md
"""

import argparse
from dataclasses import replace
from pathlib import Path

import pandas as pd

from . import schema as s
from .config import LogicConfig, load_line_files
from .loaders import from_clean, read_clean
from .penalty import rankings
from .pipeline import analyze

BASE = "base"


def fill_missing_time(df: pd.DataFrame, into: str, config: LogicConfig) -> pd.DataFrame:
    """Suma a la columna `into` lo que le falta a cada fila corta para llegar al tiempo requerido."""
    out = df.copy()
    required = out[s.LINE].map(lambda line: config.targets(line).required_h)
    recorded = out[s.HOURS].sum(axis=1)
    gap = (required - recorded).where((recorded > 0) & (recorded < required), 0.0)
    out[into] = out[into] + gap
    return out


def scenarios(
    clean: pd.DataFrame, files: dict[str, dict], config: LogicConfig
) -> dict[str, tuple[pd.DataFrame, LogicConfig]]:
    """Escenario → (entrada de la lógica, configuración)."""
    base = from_clean(clean, config)
    out = {
        BASE: (base, config),
        "sin reescalar a 22 h": (from_clean(clean, config, rescaled=False), config),
    }
    for col, loss in [(s.TAP, "parada propia"), (s.DES, "falta de piezas"), (s.SAT, "bloqueo")]:
        out[f"tiempo que falta = {loss}"] = (fill_missing_time(base, col, config), config)
    for line, f in files.items():
        for name, segments in f.get("hipotesis_tramos", {}).items():
            segments_by_line = {**config.segments_by_line, line: segments}
            out[f"tramos: {name}"] = (base, replace(config, segments_by_line=segments_by_line))
    return out


def compare(clean: pd.DataFrame, files: dict[str, dict], config: LogicConfig, top: int = 3) -> pd.DataFrame:
    """Una fila por escenario y línea, con su top y cómo queda el primero del base."""
    rows = []
    for name, (data, cfg) in scenarios(clean, files, config).items():
        analysis = analyze(data, cfg)
        totals = analysis.totals.set_index([s.LINE, s.OP])
        for line, ranks in rankings(analysis.totals, cfg.main_group).items():
            rows.append(
                {
                    "escenario": name,
                    "linea": line,
                    "penalizacion": ranks["penalizacion"][:top],
                    "frena_linea": ranks["frena_linea"][:top],
                    "totals": totals.loc[line],
                }
            )
    out = pd.DataFrame(rows)
    base = out[out["escenario"] == BASE].set_index("linea")
    out["leader"] = out["linea"].map(base["penalizacion"].str[0])
    out["leader_rank"] = [_leader(r, "rank") for r in out.itertuples()]
    out["leader_days"] = [_leader(r, "bottleneck_days") for r in out.itertuples()]
    same = [
        "sí, mismo orden" if p == base.loc[l, "penalizacion"]
        else "sí, otro orden" if set(p) == set(base.loc[l, "penalizacion"])
        else "no"
        for p, l in zip(out["penalizacion"], out["linea"])
    ]
    out["same_top"] = same
    base_days = base["totals"].map(lambda t: t["bottleneck_days"])
    out["changed_days"] = [_changes(r.totals["bottleneck_days"], base_days[r.linea]) for r in out.itertuples()]
    return out.drop(columns="totals")


def _changes(days: pd.Series, base_days: pd.Series, top: int = 4) -> str:
    """Las máquinas cuyos días frenando la línea más cambian respecto al base."""
    both = pd.DataFrame({"base": base_days, "now": days}).fillna(0).astype(int)
    both["diff"] = (both["now"] - both["base"]).abs()
    moved = both[both["diff"] > 0].sort_values(["diff", "base"], ascending=False).head(top)
    return ", ".join(f"{op} ({r.base} → {r.now} d)" for op, r in moved.iterrows()) or "ninguna"


def _leader(row, col: str):
    if row.leader not in row.totals.index or pd.isna(row.totals.loc[row.leader, col]):
        return None
    return int(row.totals.loc[row.leader, col])


def report(result: pd.DataFrame, top: int) -> str:
    """Informe en Markdown, una tabla por línea. Va tal cual a una diapositiva."""
    parts = ["# Robustez de la lógica de paradas", ""]
    for line, r in result.groupby("linea", sort=True):
        leader = r["leader"].iloc[0]
        n = len(r)
        kept = (r["same_top"] != "no").sum()
        first = (r["leader_rank"] == 1).sum()
        parts += [
            f"## {line}",
            "",
            f"El top {top} de penalización es el mismo en {kept} de {n} escenarios, y {leader} "
            f"sale primera en {first} de {n}.",
            "",
            f"| Escenario | Top {top} penalización | Top {top} frena la línea | {leader}: puesto · días que frena "
            f"| ¿Mismo top {top}? | Más cambian sus días frenando |",
            "| --- | --- | --- | --- | --- | --- |",
        ]
        for x in r.itertuples():
            leader_cell = "fuera del ranking" if x.leader_rank is None else f"{x.leader_rank}.º · {x.leader_days} d"
            changes = "—" if x.escenario == BASE else x.changed_days
            parts.append(
                f"| {x.escenario} | {', '.join(x.penalizacion)} | {', '.join(x.frena_linea)} | {leader_cell} "
                f"| {x.same_top} | {changes} |"
            )
        parts.append("")
    return "\n".join(parts)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="python -m backend.logic.robustness", description=__doc__.splitlines()[0])
    parser.add_argument("--clean", required=True, help="clean.csv de Rol 1, o la carpeta data/processed")
    parser.add_argument("--top", type=int, default=3)
    parser.add_argument("--out", type=Path, help="escribe el informe en este Markdown")
    args = parser.parse_args(argv)

    files = load_line_files()
    config = LogicConfig.from_line_files(files)
    text = report(compare(read_clean(args.clean), files, config, args.top), args.top)
    print(text)
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(text, encoding="utf-8")


if __name__ == "__main__":
    main()
