"""Modelos de prediccion con una interfaz comun.

Todos reciben una lista de peticiones (una serie con sus covariables) y devuelven, para cada
una, los deciles p10 a p90 en cada paso del horizonte: un array (n, 9, horizonte). Asi TimesFM
y las referencias simples se comparan con las mismas metricas, banda incluida. Las metricas
usan p10, p50 y p90; el resto de deciles sirve para dibujar la banda en degradado.
"""

from dataclasses import dataclass

import numpy as np

QUANTILES = (0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9)
QUANTILE_COLS = [f"p{round(100 * q)}" for q in QUANTILES]  # p10, p20, ..., p90


@dataclass
class Request:
    context: np.ndarray  # (T,) sin huecos
    past_cov: np.ndarray | None = None  # (C, T): solo se conoce en el pasado
    future_cov: np.ndarray | None = None  # (C, T + horizonte): se conoce de antemano


def fill_gaps(x: np.ndarray) -> np.ndarray | None:
    """Rellena huecos por interpolacion lineal (y bordes con el valor mas cercano). None si no hay datos."""
    x = np.asarray(x, dtype=float)
    ok = ~np.isnan(x)
    if not ok.any():
        return None
    idx = np.arange(len(x))
    return np.interp(idx, idx[ok], x[ok])


def _empirical_band(center: np.ndarray, spread: np.ndarray, horizon: int, grow: bool) -> np.ndarray:
    """Deciles alrededor de un centro (p50), con la dispersion vista en el contexto."""
    q = np.asarray(QUANTILES)
    offsets = np.quantile(spread, q) if len(spread) else np.zeros(len(q))
    # p50 es el centro; por debajo no se pasa de el y por encima tampoco, asi no se cruzan.
    offsets = np.where(q < 0.5, np.minimum(offsets, 0), np.where(q > 0.5, np.maximum(offsets, 0), 0.0))
    steps = np.sqrt(np.arange(1, horizon + 1)) if grow else np.ones(horizon)
    band = center + offsets[:, None] * steps[None, :]
    return np.clip(band, 0, None)  # horas y piezas no son negativas


class LastValue:
    """Manana igual que hoy. La banda sale de los cambios de un dia a otro del contexto."""

    name = "ultimo_valor"

    def predict(self, reqs: list[Request], horizon: int) -> np.ndarray:
        return np.stack([_empirical_band(r.context[-1], np.diff(r.context), horizon, grow=True) for r in reqs])


class Mean:
    """Manana como la media. La banda sale de lo que se separa cada dia de esa media."""

    name = "media"

    def predict(self, reqs: list[Request], horizon: int) -> np.ndarray:
        return np.stack([_empirical_band(r.context.mean(), r.context - r.context.mean(), horizon, grow=False)
                         for r in reqs])


class TimesFM:
    """TimesFM 3.0 en CPU. El modelo se carga una vez y se reutiliza (4 s desde la cache)."""

    _model = None

    def __init__(self, name: str = "timesfm", checkpoint: str = "google/timesfm-3.0-pytorch",
                 device: str = "cpu", batch_size: int = 64):
        self.name, self.checkpoint, self.device, self.batch_size = name, checkpoint, device, batch_size

    def _load(self):
        if TimesFM._model is None:
            from timesfm3 import TimesFM3Forecaster  # import aqui: el resto funciona sin timesfm

            TimesFM._model = TimesFM3Forecaster.from_pretrained(
                self.checkpoint, device=self.device, per_core_batch_size=self.batch_size)
        return TimesFM._model

    @staticmethod
    def _same_shape(covs: list[np.ndarray | None], widths: list[int]) -> list[np.ndarray | None]:
        """Si alguna serie trae covariables, las que no traen reciben ceros con los mismos canales.

        timesfm 3.0.2 junta la salida de todos los lotes antes de quitar los canales de
        covariables, y falla si unos lotes traen covariables y otros no. Dentro de un lote ya
        rellena con ceros; aqui se hace igual para todos.
        """
        ref = next((c for c in covs if c is not None), None)
        if ref is None:
            return covs
        return [c if c is not None else np.zeros((ref.shape[0], w), dtype=np.float32) for c, w in zip(covs, widths)]

    def predict(self, reqs: list[Request], horizon: int) -> np.ndarray:
        model = self._load()
        levels = list(model.config.quantiles)
        cols = [levels.index(q) for q in QUANTILES]
        lens = [len(r.context) for r in reqs]
        outs = model.predict_batch(
            contexts=[r.context for r in reqs],
            horizon=horizon,
            past_only_covariates=self._same_shape([r.past_cov for r in reqs], lens),
            past_future_covariates=self._same_shape([r.future_cov for r in reqs], [n + horizon for n in lens]),
            return_quantiles=True,
            make_positive=True,
        )
        return np.stack([np.asarray(o.quantiles)[:horizon, cols].T for o in outs])
