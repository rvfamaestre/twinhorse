"""Tests de forecast/ con la linea inventada de test_pipeline. No descargan TimesFM.

El test que si usa TimesFM se activa con RUN_TIMESFM=1 (necesita los 1,3 GB de pesos).
"""

import json
import os

import numpy as np
import pandas as pd
import pytest

from forecast import backtest, run_forecast, series
from forecast.model import QUANTILES, LastValue, Mean, Request, TimesFM
from tests.test_pipeline import LINE, synthetic_line


@pytest.fixture
def files(tmp_path):
    data, config = synthetic_line()
    data.to_csv(tmp_path / "datos.csv", index=False)
    config.to_csv(tmp_path / "config.csv", index=False)
    return tmp_path


@pytest.fixture
def panel(files):
    return series.load_line(LINE, files / "datos.csv", files / "config.csv", lines_dir=files)


def test_calendar_marks_days_around_a_stop():
    off = {pd.Timestamp("2026-03-09")}  # lunes sin produccion
    cal = series.calendar(pd.to_datetime(["2026-03-06", "2026-03-10", "2026-03-11"]), off)
    assert cal["vispera_parada"].tolist() == [1.0, 0.0, 0.0]  # el viernes antes
    assert cal["tras_parada"].tolist() == [0.0, 1.0, 0.0]  # el martes despues
    assert cal["dia_semana"].tolist() == [4.0, 1.0, 2.0]


def test_future_dates_skip_weekends_and_stops():
    days = series.future_dates(pd.Timestamp("2026-03-06"), 3, {pd.Timestamp("2026-03-09")})
    assert [d.strftime("%m-%d") for d in days] == ["03-10", "03-11", "03-12"]


def test_panel_uses_only_reliable_stations(panel):
    assert set(panel.series("tap_h")) == {"A1", "A4", "A5", "A6", "A7", "A8"}  # A2 y A3 excluidas
    assert panel.series("npr") == [series.LINE_ID]
    assert len(panel.dates) == 5
    assert panel.neighbours["A4"] == ("A1", "A5")


def test_baselines_give_ordered_nonnegative_bands():
    reqs = [Request(np.array([1.0, 2.0, 0.5, 3.0])), Request(np.array([0.0, 0.0, 0.1, 0.0]))]
    for model in (LastValue(), Mean()):
        q = model.predict(reqs, 3)
        assert q.shape == (2, len(QUANTILES), 3)
        assert (q >= 0).all() and (np.diff(q, axis=1) >= 0).all()


def test_timesfm_covariates_padded_to_same_shape():
    covs = TimesFM._same_shape([None, np.ones((2, 4)), None], [4, 4, 4])
    assert [c.shape for c in covs] == [(2, 4)] * 3
    assert covs[0].sum() == 0


def test_backtest_scores_and_simplest_wins_ties(panel):
    variants = backtest.default_variants(use_timesfm=False)
    preds = backtest.run(panel, variants)
    assert set(preds["escenario"]) == {"semana", "dia"}
    scores = backtest.score(preds)
    assert {"mae", "cobertura", "gana", "mejora"} <= set(scores.columns)
    tie = pd.DataFrame({"escenario": "semana", "metrica": "tap_h", "modelo": ["media", "timesfm"],
                        "mae": [1.0, 0.995]})
    assert backtest.best_variants(tie, ["media", "timesfm"]) == {"tap_h": "media"}


def test_predict_writes_csv_and_json(files):
    out = files / "out"
    run_forecast.main(["predict", "--line", LINE, "--data", str(files / "datos.csv"),
                       "--config", str(files / "config.csv"), "--lines-dir", str(files),
                       "--out", str(out), "--figures", str(files / "fig"), "--sin-timesfm", "--horizon", "2"])
    fc = pd.read_csv(out / LINE / "forecasts.csv")
    assert list(fc.columns) == ["op", "fecha", "metrica", "p10", "p50", "p90", "modelo"]
    assert fc["fecha"].nunique() == 2
    payload = json.loads((out / LINE / "forecast.json").read_text(encoding="utf-8"))
    assert {"metric", "modelo", "days", "p10", "p50", "p90"} <= set(payload["A4"][0])
    assert (out / LINE / "BACKTEST.md").exists()


@pytest.mark.skipif(os.environ.get("RUN_TIMESFM") != "1", reason="pon RUN_TIMESFM=1 para probar TimesFM real")
def test_timesfm_runs_on_cpu():
    q = TimesFM().predict([Request(np.sin(np.arange(20) / 3) + 2, future_cov=np.zeros((1, 23)))], 3)
    assert q.shape == (1, len(QUANTILES), 3)
