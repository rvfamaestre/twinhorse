"""API del dashboard: sirve la línea y calcula predicciones al momento. Desde la raíz del repo:

    python -m backend.api        # http://localhost:8000; el frontend (npm run dev) la usa por /api

GET  /api/line               el JSON que pinta el 3D (frontend/public/mock/line_state.mock.json)
GET  /api/forecast/options   series, métricas, días y modelos disponibles
POST /api/forecast           predicción de una serie con la ventana de contexto y el horizonte pedidos
GET  /api/estimate?day=      motores previstos para un día con lo que se sabía la víspera (modo «Ahora»)
"""

import hashlib
import json
import threading
import time
from contextlib import asynccontextmanager
from functools import lru_cache
from pathlib import Path

import numpy as np
import pandas as pd
from fastapi import FastAPI, HTTPException
from fastapi import Request as HttpRequest
from fastapi.responses import Response
from pydantic import BaseModel, Field

from forecast import series
from forecast.model import QUANTILE_COLS, LastValue, Mean, Request, TimesFM, fill_gaps

ROOT = Path(__file__).resolve().parents[1]
LINE_STATE = ROOT / "frontend" / "public" / "mock" / "line_state.mock.json"
MAX_HORIZON = 20  # cuatro semanas laborables
MIN_CONTEXT = 3
METRICS = {
    "tap_h": {"label": "Parada propia", "unit": "h"},
    "des_h": {"label": "Sin piezas", "unit": "h"},
    "sat_h": {"label": "Bloqueada", "unit": "h"},
    series.LINE_METRIC: {"label": "Piezas", "unit": "piezas"},
}
MODELS = {"timesfm": "TimesFM 3.0", "media": "Media", "ultimo_valor": "Último valor"}

_predict_lock = threading.Lock()  # un modelo, una predicción cada vez
_timesfm = {"ready": False, "error": None}


def _line() -> str:
    return json.loads(LINE_STATE.read_text(encoding="utf-8"))["meta"]["line"]


@lru_cache(maxsize=None)
def panel() -> series.Panel:
    return series.load_line(_line())


def _warm_up() -> None:
    """Carga TimesFM al arrancar (unos segundos desde la caché) para que la primera predicción sea rápida."""
    try:
        TimesFM()._load()
        _timesfm["ready"] = True
    except Exception as exc:  # sin timesfm instalado la API sigue con las referencias
        _timesfm["error"] = str(exc)


@asynccontextmanager
async def _lifespan(_: FastAPI):
    panel()
    threading.Thread(target=_warm_up, daemon=True).start()
    yield


app = FastAPI(title="LOSSIA", docs_url="/api/docs", openapi_url="/api/openapi.json", lifespan=_lifespan)


@app.get("/api/line")
def line(request: HttpRequest) -> Response:
    if not LINE_STATE.exists():
        raise HTTPException(404, "Falta el JSON de la línea: python frontend/scripts/build_mock.py")
    body = LINE_STATE.read_bytes()
    etag = '"' + hashlib.sha1(body).hexdigest()[:16] + '"'
    headers = {"ETag": etag, "Cache-Control": "no-cache"}
    if request.headers.get("if-none-match") == etag:
        return Response(status_code=304, headers=headers)
    return Response(body, media_type="application/json", headers=headers)


@app.get("/api/forecast/options")
def options() -> dict:
    p = panel()
    stations = [{"id": op, "label": op, "metrics": series.STATION_METRICS} for op in p.series("tap_h")]
    return {
        "line": p.line,
        "series": [{"id": series.LINE_ID, "label": "Línea completa", "metrics": [series.LINE_METRIC]}] + stations,
        "metrics": [{"id": k, **v} for k, v in METRICS.items()],
        "dates": [d.strftime("%Y-%m-%d") for d in p.dates],
        "models": [{"id": k, "label": v, "ready": k != "timesfm" or _timesfm["ready"]} for k, v in MODELS.items()],
        "limits": {"min_context": MIN_CONTEXT, "max_horizon": MAX_HORIZON},
        "quantiles": QUANTILE_COLS,
    }


class ForecastIn(BaseModel):
    series: str
    metric: str
    context: int = Field(ge=MIN_CONTEXT, description="días productivos de historia que ve el modelo")
    horizon: int = Field(ge=1, le=MAX_HORIZON, description="días productivos a predecir")
    origin: str | None = Field(None, description="último día de contexto (AAAA-MM-DD); por defecto, el último con datos")
    model: str = "timesfm"


def _num(v: float) -> float | None:
    return None if v is None or not np.isfinite(v) else round(float(v), 4)


@app.post("/api/forecast")
def forecast(req: ForecastIn) -> dict:
    p = panel()
    if req.metric not in p.values:
        raise HTTPException(422, f"Métrica desconocida: {req.metric}")
    table = p.values[req.metric]
    if req.series not in table.columns:
        raise HTTPException(422, f"{req.series} no tiene serie de {METRICS[req.metric]['label'].lower()}")
    if req.model not in MODELS:
        raise HTTPException(422, f"Modelo desconocido: {req.model}")
    if req.model == "timesfm" and not _timesfm["ready"]:
        raise HTTPException(503, "TimesFM aún se está cargando" if _timesfm["error"] is None else f"TimesFM no está disponible: {_timesfm['error']}")

    dates = p.dates
    origin = pd.Timestamp(req.origin) if req.origin else dates[-1]
    if origin not in dates:
        raise HTTPException(422, f"{origin:%d/%m} no es un día productivo con datos")
    i = dates.get_loc(origin)
    if req.context > i + 1:
        raise HTTPException(422, f"Hasta el {origin:%d/%m} solo hay {i + 1} días de historia")

    ctx_dates = dates[i - req.context + 1: i + 1]
    ctx = table[req.series].reindex(ctx_dates).to_numpy(float)
    filled = fill_gaps(ctx)
    if filled is None:
        raise HTTPException(422, "La serie no tiene datos válidos en esa ventana")
    known = dates[i + 1: i + 1 + req.horizon]
    rest = req.horizon - len(known)
    target = known.append(series.future_dates(known[-1] if len(known) else origin, rest, p.off_dates)) if rest else known

    model = {"timesfm": TimesFM, "media": Mean, "ultimo_valor": LastValue}[req.model]()
    start = time.perf_counter()
    with _predict_lock:
        q = model.predict([Request(context=filled)], req.horizon)[0]  # (deciles, horizonte)
    elapsed = time.perf_counter() - start

    actual = table[req.series].reindex(target).to_numpy(float)
    seen = np.isfinite(actual)
    inside = seen & (actual >= q[0]) & (actual <= q[-1])
    return {
        "series": req.series,
        "metric": req.metric,
        "model": req.model,
        "model_label": MODELS[req.model],
        "context": {"dates": [d.strftime("%Y-%m-%d") for d in ctx_dates], "values": [_num(v) for v in ctx]},
        "forecast": {"dates": [d.strftime("%Y-%m-%d") for d in target],
                     **{c: [_num(v) for v in q[k]] for k, c in enumerate(QUANTILE_COLS)}},
        "actual": [_num(v) for v in actual],
        "inside_80": int(inside.sum()),
        "known": int(seen.sum()),
        "elapsed_ms": round(1000 * elapsed),
    }


# ---------------------------------------------------------------- estimación del día

LINE_COVARIATES = {"tap_linea": "tap_h", "des_linea": "des_h", "sat_linea": "sat_h"}


def _line_total(p: series.Panel, metric: str, dates: pd.DatetimeIndex) -> np.ndarray | None:
    """Horas de toda la línea cada día: la suma de las estaciones con dato válido."""
    return fill_gaps(p.values[metric].reindex(dates).sum(axis=1, min_count=1).to_numpy(float))


@lru_cache(maxsize=64)
def _estimate(day: str, use_timesfm: bool) -> dict:
    p = panel()
    target = pd.Timestamp(day)
    ctx = p.dates[: p.dates.get_loc(target)]  # solo lo que se sabía la víspera
    y = fill_gaps(p.values[series.LINE_METRIC][series.LINE_ID].reindex(ctx).to_numpy(float))
    if y is None:
        raise HTTPException(422, "No hay piezas de la línea antes de ese día")

    # Lo que puede influir. Se conoce de antemano: el calendario del día (día de la semana, si es
    # el primero tras una parada o la víspera de una). Solo del pasado: cuánto se paró la línea
    # (parada propia, sin piezas y bloqueada) cada día anterior. La propia serie de motores también cuenta.
    cal = series.calendar(ctx.append(pd.DatetimeIndex([target])), p.off_dates)[series.CALENDAR_COLS]
    past = [_line_total(p, m, ctx) for m in LINE_COVARIATES.values()]
    past_ok = all(c is not None for c in past)
    req = Request(context=y, past_cov=np.stack(past) if past_ok else None, future_cov=cal.to_numpy(float).T)

    model = TimesFM() if use_timesfm else Mean()
    start = time.perf_counter()
    with _predict_lock:
        q = model.predict([req if use_timesfm else Request(context=y)], 1)[0][:, 0]
    elapsed = time.perf_counter() - start
    reference = Mean().predict([Request(context=y)], 1)[0][:, 0]
    actual = p.values[series.LINE_METRIC][series.LINE_ID].get(target)

    today = cal.iloc[-1]
    factors = [
        {"id": "dia_semana", "value": int(today["dia_semana"])},
        {"id": "tras_parada", "value": bool(today["tras_parada"])},
        {"id": "vispera_parada", "value": bool(today["vispera_parada"])},
        {"id": "motores_previos", "value": _num(y[-1]), "mean": _num(y.mean()), "unit": "piezas"},
    ]
    if past_ok:
        factors += [{"id": k, "value": _num(c[-1]), "mean": _num(c.mean()), "unit": "h"} for k, c in zip(LINE_COVARIATES, past)]
    return {
        "day": target.strftime("%Y-%m-%d"),
        "context_days": len(ctx),
        "model": "timesfm" if use_timesfm else "media",
        "model_label": MODELS["timesfm" if use_timesfm else "media"],
        "covariates": use_timesfm,
        "deciles": {c: _num(v) for c, v in zip(QUANTILE_COLS, q)},
        "reference": {"model": "media", "p50": _num(reference[4])},
        "actual": _num(actual) if actual is not None and np.isfinite(actual) else None,
        "factors": factors,
        "elapsed_ms": round(1000 * elapsed),
    }


@app.get("/api/estimate")
def estimate(day: str | None = None) -> dict:
    """Motores previstos para un día con lo que se sabía la víspera: TimesFM con covariables.

    Es lo que enseña el dashboard en el modo «Ahora»: el día que se está viendo aún no ha
    terminado, así que su total se estima. Si TimesFM aún se carga, sale la media de los días anteriores.
    """
    p = panel()
    target = pd.Timestamp(day) if day else p.dates[-1]
    if target not in p.dates:
        raise HTTPException(422, f"{target:%d/%m} no es un día productivo con datos")
    if p.dates.get_loc(target) < MIN_CONTEXT:
        raise HTTPException(422, f"Antes del {target:%d/%m} hay menos de {MIN_CONTEXT} días con datos")
    return _estimate(target.strftime("%Y-%m-%d"), bool(_timesfm["ready"]))


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=8000)
