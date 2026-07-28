"""
Comparación modelo vs baseline sobre EL MISMO conjunto de horas (comparación justa).

Alinea las predicciones de GHI del modelo con las de smart persistence (variante A,
la referencia) por índice temporal, y calcula por segmento de fill_flag el RMSE de
cada uno y el forecast skill del modelo: skill = 1 - RMSE_modelo / RMSE_persistence.
skill > 0 ⇒ el modelo supera al baseline (meta del proyecto).
"""
from __future__ import annotations
import pandas as pd

from forecasting.eval import metrics as M

_SEGMENTOS = {
    "global": None,
    "limpio_ff0": lambda ff: ff == 0,
    "rellenado_ff_pos": lambda ff: ff > 0,
}


def comparar(pred_modelo: pd.DataFrame, ghi_pred_ref: pd.Series | None = None,
             nombre: str = "xgboost") -> pd.DataFrame:
    """`pred_modelo`: salida de xgb.predecir_ghi (índice τ, con ghi_true/ghi_pred/
    fill_flag). `ghi_pred_ref`: GHI de persistence A alineable por índice; si es None,
    usa la columna `ghi_persistence` ya presente en `pred_modelo` (correcta por nodo y
    sin reindex, necesaria en multi-nodo).

    Devuelve tabla por segmento con RMSE de ambos, MAE/MBE del modelo y skill.
    """
    df = pred_modelo.copy()
    if ghi_pred_ref is not None:
        df["ghi_ref"] = ghi_pred_ref.reindex(df.index)
    else:
        df["ghi_ref"] = df["ghi_persistence"]
    df = df.dropna(subset=["ghi_true", "ghi_pred", "ghi_ref"])

    filas = []
    for seg, cond in _SEGMENTOS.items():
        sub = df if cond is None else df[cond(df["fill_flag"])]
        r_mod = M.rmse(sub["ghi_true"], sub["ghi_pred"])
        r_ref = M.rmse(sub["ghi_true"], sub["ghi_ref"])
        filas.append({
            "segmento": seg, "n": len(sub),
            "RMSE_persistence": r_ref,
            f"RMSE_{nombre}": r_mod,
            f"MAE_{nombre}": M.mae(sub["ghi_true"], sub["ghi_pred"]),
            f"MBE_{nombre}": M.mbe(sub["ghi_true"], sub["ghi_pred"]),
            "R2_persistence": M.r2(sub["ghi_true"], sub["ghi_ref"]),
            f"R2_{nombre}": M.r2(sub["ghi_true"], sub["ghi_pred"]),
            "skill": M.skill(r_mod, r_ref),
        })
    return pd.DataFrame(filas)
