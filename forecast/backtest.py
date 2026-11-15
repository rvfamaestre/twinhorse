"""Backtest: cada variante predice dias que ya conocemos y se mide cuanto falla.

Dos escenarios:
- semana: con todo lo anterior a la ultima semana, predecir esa semana entera de golpe;
- dia: para cada dia de esa semana, predecir solo ese dia con todo lo anterior (a un dia vista).
"""

from dataclasses import dataclass

import numpy as np
import pandas as pd

from .model import QUANTILE_COLS, LastValue, Mean, Request, TimesFM, fill_gaps
from .series import LINE_METRIC, STATION_METRICS, Panel, calendar

BASELINES = ["ultimo_valor", "media"]


@dataclass(frozen=True)
class Variant:
    name: str
    model: object
    calendar: bool = False  # dia de la semana, tras parada, vispera de parada (conocidas a futuro)
    neighbours: bool = False  # TAP de la vecina como covariable pasada (DES <- anterior, SAT <- siguiente)


def default_variants(use_timesfm: bool = True) -> list[Variant]:
    out = [Variant("ultimo_valor", LastValue()), Variant("media", Mean())]
    if use_timesfm:
        out += [Variant("timesfm", TimesFM()),
                Variant("timesfm_calendario", TimesFM(), calendar=True),
                Variant("timesfm_vecinas", TimesFM(), calendar=True, neighbours=True)]
    return out


def week_split(dates: pd.DatetimeIndex) -> tuple[pd.DatetimeIndex, pd.DatetimeIndex]:
    """Contexto = todo menos la ultima semana ISO; prueba = la ultima semana.

    Si la ultima semana tiene menos de 3 dias o deja menos de 5 de contexto, se usa el ultimo 20 %.
    """
    week = dates.isocalendar().week.to_numpy()
    test = dates[week == week[-1]]
    if len(test) < 3 or len(dates) - len(test) < 5:
        test = dates[-max(1, round(0.2 * len(dates))):]
    return dates[: len(dates) - len(test)], test


def _neighbour_metric(metric: str) -> int | None:
    return {"des_h": 0, "sat_h": 1}.get(metric)  # 0 = anterior, 1 = siguiente


def build_requests(panel: Panel, metric: str, ctx: pd.DatetimeIndex, target: pd.DatetimeIndex,
                   variant: Variant, extra_off=()) -> list[tuple[str, Request]]:
    """Una peticion por serie de la metrica, con las covariables que pide la variante."""
    cal = None
    if variant.calendar:
        cal = calendar(ctx.append(target), set(panel.off_dates) | set(extra_off))[
            ["dia_semana", "tras_parada", "vispera_parada"]].to_numpy().T
    table = panel.values[metric]
    out = []
    for sid in table.columns:
        context = fill_gaps(table.loc[ctx, sid].to_numpy())
        if context is None:
            continue
        past = None
        side = _neighbour_metric(metric)
        if variant.neighbours and side is not None:
            nb = panel.neighbours.get(sid, (None, None))[side]
            if nb is not None:
                cov = fill_gaps(panel.values["tap_h"].loc[ctx, nb].to_numpy())
                past = None if cov is None else cov[None, :]
        out.append((sid, Request(context=context, past_cov=past, future_cov=cal)))
    return out


def forecast(panel: Panel, variant: Variant, ctx: pd.DatetimeIndex, target: pd.DatetimeIndex,
             metrics=None, extra_off=()) -> pd.DataFrame:
    """Predice `target` desde `ctx` para todas las series de las metricas pedidas, en una sola llamada."""
    metrics = metrics or STATION_METRICS + [LINE_METRIC]
    keys, reqs = [], []
    for m in metrics:
        for sid, r in build_requests(panel, m, ctx, target, variant, extra_off):
            keys.append((sid, m))
            reqs.append(r)
    if not reqs:
        return pd.DataFrame(columns=["serie", "metrica", "fecha", "paso", "modelo", *QUANTILE_COLS])
    q = variant.model.predict(reqs, len(target))  # (n, deciles, h)
    rows = [{"serie": sid, "metrica": m, "fecha": d, "paso": k + 1, "modelo": variant.name,
             **{c: q[i, j, k] for j, c in enumerate(QUANTILE_COLS)}}
            for i, (sid, m) in enumerate(keys) for k, d in enumerate(target)]
    return pd.DataFrame(rows)


def _actuals(panel: Panel) -> pd.DataFrame:
    parts = [t.stack(future_stack=True).rename("real").rename_axis(["fecha", "serie"]).reset_index().assign(metrica=m)
             for m, t in panel.values.items()]
    return pd.concat(parts, ignore_index=True)


def run(panel: Panel, variants: list[Variant]) -> pd.DataFrame:
    """Predicciones de todas las variantes en los dos escenarios, con el valor real al lado."""
    ctx, test = week_split(panel.dates)
    preds = []
    for v in variants:
        preds.append(forecast(panel, v, ctx, test).assign(escenario="semana"))
        for d in test:
            before = panel.dates[panel.dates < d]
            preds.append(forecast(panel, v, before, pd.DatetimeIndex([d])).assign(escenario="dia"))
    out = pd.concat(preds, ignore_index=True).merge(_actuals(panel), on=["fecha", "serie", "metrica"], how="left")
    return out.dropna(subset=["real"])


def score(preds: pd.DataFrame) -> pd.DataFrame:
    """Por escenario, metrica y modelo: error medio, cobertura de la banda y cuantas series gana.

    mae: error absoluto medio de la mediana (en las unidades de la metrica).
    cobertura: fraccion de dias reales dentro de p10-p90 (lo ideal es 0,8).
    gana: fraccion de series en que el modelo falla menos que las dos referencias.
    """
    p = preds.assign(err=(preds["p50"] - preds["real"]).abs(),
                     dentro=(preds["real"] >= preds["p10"]) & (preds["real"] <= preds["p90"]))
    per_series = p.groupby(["escenario", "metrica", "modelo", "serie"])["err"].mean().unstack("modelo")
    best_base = per_series[[b for b in BASELINES if b in per_series]].min(axis=1)
    wins = per_series.lt(best_base, axis=0).groupby(level=["escenario", "metrica"]).mean()

    out = p.groupby(["escenario", "metrica", "modelo"]).agg(
        mae=("err", "mean"), cobertura=("dentro", "mean"), series=("serie", "nunique")).reset_index()
    out["gana"] = [np.nan if r.modelo in BASELINES else wins.loc[(r.escenario, r.metrica), r.modelo]
                   for r in out.itertuples()]
    # mejora: cuanto menos falla que la mejor referencia (0,1 = un 10 % menos de error).
    base = (out[out["modelo"].isin(BASELINES)].groupby(["escenario", "metrica"])["mae"].min()
            .rename("mae_ref").reset_index())
    out = out.merge(base, on=["escenario", "metrica"], how="left")
    out["mejora"] = 1 - out["mae"] / out.pop("mae_ref")
    return out


def best_variants(scores: pd.DataFrame, order: list[str], escenario: str = "semana",
                  tolerance: float = 0.01) -> dict[str, str]:
    """La variante con menos error por metrica.

    Si varias fallan dentro de un `tolerance` (1 %) de la mejor, gana la que va antes en `order`,
    que es la mas simple: una mejora de milesimas no justifica un modelo mas complicado.
    """
    s = scores[scores["escenario"] == escenario].copy()
    s["rango"] = s["modelo"].map({m: i for i, m in enumerate(order)})
    best = {}
    for metric, g in s.groupby("metrica"):
        close = g[g["mae"] <= g["mae"].min() * (1 + tolerance)]
        best[metric] = close.sort_values("rango").iloc[0]["modelo"]
    return best
