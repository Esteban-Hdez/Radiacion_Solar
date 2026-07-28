"""
XGBoost CUANTÍLICO para kt(t+1) — experimento 4.

En días nublados/variables un pronóstico puntual siempre falla porque el kt es de
alta varianza. Lo útil es una BANDA de incertidumbre: predecir varios cuantiles
(P10/P50/P90) y reconstruir GHI por cuantil. Así se cuantifica "qué tan seguros
estamos", que se ensancha justo en los episodios difíciles.

Usa `objective=reg:quantileerror` con `quantile_alpha` multi-cuantil (un solo modelo
con salida por cuantil). Los cuantiles se ordenan tras predecir para evitar cruces
(P10<=P50<=P90). El P50 sirve además como pronóstico puntual para comparar con el
resto de experimentos.
"""
from __future__ import annotations
import numpy as np
import pandas as pd
import xgboost as xgb

from forecasting import config as C
from forecasting import features as F
from forecasting import target as T
from forecasting.models.xgb import detectar_device, _matriz

# Hiperparámetros base para el objetivo cuantílico (sin eval_metric rmse).
# base_score=0.5 es CLAVE: la mediana de kt es ~1.0 (domina el cielo despejado) y
# `reg:quantileerror` inicializa base_score en el cuantil empírico; sin fijarlo, el
# P50 colapsa a la constante 1.0 (best_iteration=0). 0.5 (centro de kt∈[0,1]) lo evita.
PARAMS_CUANTIL = dict(
    n_estimators=3000,
    learning_rate=0.03,
    max_depth=6,
    min_child_weight=5.0,
    subsample=0.8,
    colsample_bytree=0.8,
    reg_lambda=1.0,
    objective="reg:quantileerror",
    tree_method="hist",
    base_score=0.5,
    early_stopping_rounds=50,
)


def entrenar_cuantilico(feat: pd.DataFrame, cuantiles=(0.1, 0.5, 0.9),
                        cols: list[str] | None = None, params: dict | None = None,
                        device: str | None = None):
    """Entrena un XGBoost multi-cuantil. Devuelve (modelo, cols, splits, cuantiles)."""
    device = device or detectar_device()
    cols = cols if cols is not None else F.columnas_features(feat)
    alphas = np.asarray(sorted(cuantiles), dtype=float)
    params = {**PARAMS_CUANTIL, **(params or {})}
    splits = T.split_temporal(feat)

    Xtr, ytr, *_ = _matriz(splits["train"], cols)
    Xval, yval, *_ = _matriz(splits["val"], cols)

    model = xgb.XGBRegressor(device=device, quantile_alpha=alphas, **params)
    model.fit(Xtr, ytr, eval_set=[(Xval, yval)], verbose=False)
    return model, cols, splits, tuple(alphas)


def _nombre(alpha: float) -> str:
    return f"p{int(round(alpha * 100)):02d}"


def predecir_cuantiles(model, feat_split: pd.DataFrame, cols: list[str],
                       cuantiles) -> pd.DataFrame:
    """Predice cada cuantil de kt y reconstruye GHI por cuantil (ordenados, sin
    cruces). Incluye `kt_pred`/`ghi_pred` = mediana (para comparar como puntual)."""
    s = feat_split[feat_split["op"] & feat_split["kt"].notna()].copy()
    alphas = sorted(cuantiles)
    pred = np.clip(model.predict(s[cols]), 0.0, C.KT_MAX)      # (n, n_cuantiles)
    if pred.ndim == 1:                                          # un solo cuantil
        pred = pred[:, None]
    pred = np.sort(pred, axis=1)                                # evita cruces

    cs = s["clearsky_ghi_target"].to_numpy()
    out = pd.DataFrame(index=s.index)
    out["kt_true"] = s["kt"]
    out["ghi_true"] = s["ghi_true"]
    out["clearsky_ghi"] = s["clearsky_ghi_target"]
    out["fill_flag"] = s["fill_flag"]
    for j, a in enumerate(alphas):
        out[f"kt_{_nombre(a)}"] = pred[:, j]
        out[f"ghi_{_nombre(a)}"] = pred[:, j] * cs
    # Mediana como pronóstico puntual (si 0.5 no está, usa el cuantil central).
    a_med = 0.5 if 0.5 in alphas else alphas[len(alphas) // 2]
    out["kt_pred"] = out[f"kt_{_nombre(a_med)}"]
    out["ghi_pred"] = out[f"ghi_{_nombre(a_med)}"]
    return out
