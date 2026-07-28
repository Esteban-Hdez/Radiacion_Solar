"""
Primer modelo de Fase 3: XGBoost que predice kt(t+1) y debe superar a smart
persistence (skill > 0). Pensado para correr igual en la máquina Ubuntu (GPU) y en
la Mac (CPU, single-node): el device se AUTODETECTA.

- Objetivo interno: MSE sobre kt (sin ponderar por defecto). Se probó ponderar por
  `clearsky^2` para alinear con el RMSE de GHI, pero empeoró RMSE y MAE en test
  (concentra demasiado en el mediodía y generaliza peor). Toggle `ponderar_ghi`
  (default False) por si se quiere reevaluar en multi-nodo.
- Split temporal fijo: train 2020-22, early stopping en val 2023, test 2024. Es un
  walk-forward simple (expanding); el rolling-refit se deja para una fase posterior.
"""
from __future__ import annotations
import os
import subprocess
import numpy as np
import pandas as pd
import xgboost as xgb

from forecasting import config as C
from forecasting import features as F
from forecasting import target as T

# Hiperparámetros de arranque (conservadores; se afinan luego).
PARAMS = dict(
    n_estimators=3000,
    learning_rate=0.03,
    max_depth=6,
    min_child_weight=5.0,
    subsample=0.8,
    colsample_bytree=0.8,
    reg_lambda=1.0,
    objective="reg:squarederror",
    eval_metric="rmse",
    tree_method="hist",
    early_stopping_rounds=50,
)


def detectar_device() -> str:
    """'cuda' si hay GPU NVIDIA disponible, si no 'cpu'. Override con RS_DEVICE."""
    forzado = os.environ.get("RS_DEVICE")
    if forzado:
        return forzado
    try:
        subprocess.run(["nvidia-smi"], capture_output=True, check=True)
        return "cuda"
    except Exception:
        return "cpu"


def _matriz(feat: pd.DataFrame, cols: list[str]):
    """Devuelve (X, y kt, clearsky, ghi_true, fill_flag) solo en horas operativas."""
    s = feat[feat["op"] & feat["kt"].notna()]
    return (s[cols], s["kt"], s["clearsky_ghi_target"], s["ghi_true"], s["fill_flag"])


def entrenar(feat: pd.DataFrame, device: str | None = None,
             ponderar_ghi: bool = False, cols: list[str] | None = None,
             params: dict | None = None
             ) -> tuple[xgb.XGBRegressor, list[str], dict]:
    """Entrena XGBoost sobre train con early stopping en val.

    `cols`: columnas de features a usar (por defecto todas las no-meta del `feat`).
    `params`: hiperparámetros (por defecto `PARAMS`). Permite que cada experimento
    fije su propia configuración sin tocar el default.
    Devuelve (modelo, columnas_features, splits)."""
    device = device or detectar_device()
    cols = cols if cols is not None else F.columnas_features(feat)
    params = {**PARAMS, **(params or {})}
    splits = T.split_temporal(feat)

    Xtr, ytr, cstr, _, _ = _matriz(splits["train"], cols)
    Xval, yval, csval, _, _ = _matriz(splits["val"], cols)

    # float64 obligatorio: clearsky es int16 en el parquet y clearsky² desborda.
    wtr = (cstr.astype("float64") ** 2) if ponderar_ghi else None
    wval = (csval.astype("float64") ** 2) if ponderar_ghi else None

    model = xgb.XGBRegressor(device=device, **params)
    model.fit(Xtr, ytr, sample_weight=wtr,
              eval_set=[(Xval, yval)], sample_weight_eval_set=[wval],
              verbose=False)
    return model, cols, splits


def predecir_ghi(model: xgb.XGBRegressor, feat_split: pd.DataFrame,
                 cols: list[str]) -> pd.DataFrame:
    """Predice kt y reconstruye GHI en las horas operativas de un split.
    Devuelve DataFrame con kt_pred, ghi_pred, ghi_true, fill_flag, clearsky."""
    s = feat_split[feat_split["op"] & feat_split["kt"].notna()].copy()
    kt_pred = np.clip(model.predict(s[cols]), 0.0, C.KT_MAX)
    out = pd.DataFrame(index=s.index)
    out["kt_true"] = s["kt"]
    out["kt_pred"] = kt_pred
    out["clearsky_ghi"] = s["clearsky_ghi_target"]
    out["ghi_true"] = s["ghi_true"]
    out["ghi_pred"] = kt_pred * s["clearsky_ghi_target"]
    out["fill_flag"] = s["fill_flag"]
    # Persistence A en-frame (kt_last_op = último kt operativo). Correcta por nodo y
    # sin reindex (clave para multi-nodo, donde el índice datetime se repite).
    if "kt_last_op" in s.columns:
        out["ghi_persistence"] = (s["kt_last_op"].clip(0, C.KT_MAX)
                                  * s["clearsky_ghi_target"])
    if "nodo_id" in s.columns:
        out["nodo_id"] = s["nodo_id"]
    return out
