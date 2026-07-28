"""
Bloque de features BASE (feature-set del experimento fase 3) + construcción de las
columnas META. Respeta el anti-leakage de `config.py`: la fila se indexa por la HORA
OBJETIVO τ (= t+1) y solo entran:

- DETERMINISTAS / known-future en τ (`clearsky_*`, `solar_zenith_angle`, calendario).
- ESTÁTICAS del nodo (lat/lon/msnm).
- OBSERVADAS REZAGADAS (solo hasta τ-1, siempre con `.shift(>=1)`).

Nunca la observada cruda en τ (el ghi en τ es casi el target). Los `kt_lag*` son NaN
en las noches; XGBoost los maneja de forma nativa.

Cada "bloque" es una función `(df) -> DataFrame` de columnas, para poder COMPONER
feature-sets versionados (ver `builder.py`). `construir_meta` es común a todos.
"""
from __future__ import annotations
import numpy as np
import pandas as pd

from forecasting import config as C
from forecasting import target as T

# Rezagos de kt del bloque base: 1-3 h (persistencia reciente) + 24 h (día anterior).
LAGS_KT = [1, 2, 3, 24]
LAG_OBSERVADAS = 1

# Columnas META (no entran al modelo): target, máscara y auxiliares de evaluación.
# `nodo_id` es meta (identifica el nodo para eval multi-nodo); el nodo se DESCRIBE al
# modelo con lat/lon/msnm, nunca con el id.
META_COLS = ["kt", "op", "clearsky_ghi_target", "ghi_true", "fill_flag", "nodo_id"]


def construir_meta(df: pd.DataFrame) -> pd.DataFrame:
    """Columnas meta comunes a todos los feature-sets (target + evaluación)."""
    op = T.mascara_operativa(df)
    kt = T.calcular_kt(df)
    out = pd.DataFrame(index=df.index)
    out["kt"] = kt.where(op)                       # target: kt en τ (solo operativas)
    out["op"] = op
    out["clearsky_ghi_target"] = df[C.COL_CLEARSKY]    # para reconstruir GHI en τ
    out["ghi_true"] = df[C.COL_GHI].where(op)
    out["fill_flag"] = df["fill_flag"]                 # de τ, para segmentar métricas
    return out


def bloque_base(df: pd.DataFrame) -> pd.DataFrame:
    """Feature-set base (35 features del experimento fase 3)."""
    op = T.mascara_operativa(df)
    kt = T.calcular_kt(df)
    kt_op = kt.where(op)
    idx = df.index
    out = pd.DataFrame(index=idx)

    # --- Deterministas known-future en τ ---
    for c in C.DETERMINISTAS:
        out[c] = df[c]
    out["hour"] = idx.hour
    out["doy"] = idx.dayofyear
    out["month"] = idx.month
    out["sin_hour"] = np.sin(2 * np.pi * idx.hour / 24)
    out["cos_hour"] = np.cos(2 * np.pi * idx.hour / 24)
    out["sin_doy"] = np.sin(2 * np.pi * idx.dayofyear / 365.25)
    out["cos_doy"] = np.cos(2 * np.pi * idx.dayofyear / 365.25)

    # --- Estáticas del nodo ---
    for c in C.ESTATICAS:
        if c in df.columns:
            out[c] = df[c]

    # --- Observadas rezagadas (solo hasta τ-1) ---
    out["kt_last_op"] = kt_op.ffill().shift(1)         # = predicción persistence A
    for L in LAGS_KT:
        out[f"kt_lag{L}"] = kt.shift(L)                # NaN en noches (ok para XGBoost)

    observadas_lag = (C.OBSERVADAS_METEO + C.OBSERVADAS_AEROSOL
                      + ["cloud_type", "cloud_fill_flag", "fill_flag"])
    for c in observadas_lag:
        if c in df.columns:
            out[f"{c}_lag{LAG_OBSERVADAS}"] = df[c].shift(LAG_OBSERVADAS)

    # Se excluyen a propósito ghi/dni/dhi crudos en τ (fuga) y las UV (≈ f(ghi)).
    return out
