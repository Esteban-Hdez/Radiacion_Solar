"""
Evaluación segmentada por RÉGIMEN de cielo, para hacer VISIBLE dónde aporta el
modelo. El skill global está diluido por miles de horas fáciles (cielo despejado);
lo que importa son los episodios nublados/variables.

Se clasifica cada hora operativa por dos ejes independientes:

- Régimen de nubosidad (según el kt OBSERVADO en τ):
    despejado  kt >= 0.7
    parcial    0.3 <= kt < 0.7   (nubosidad intermitente/transición: lo más difícil)
    cubierto   kt < 0.3
- Régimen de rampa (magnitud del cambio |kt(τ) - kt_operativo_previo|):
    suave / moderada / fuerte

Y se reporta RMSE del modelo y de persistence + skill por bin. Usar el kt observado
para binear la evaluación es correcto (no es feature del modelo; solo etiqueta a
posteriori para diagnóstico).
"""
from __future__ import annotations
import numpy as np
import pandas as pd

from forecasting.eval import metrics as M

# Umbrales de kt para el régimen de nubosidad.
BINS_KT = [-np.inf, 0.3, 0.7, np.inf]
ETIQ_KT = ["cubierto (kt<0.3)", "parcial (0.3-0.7)", "despejado (kt>=0.7)"]
# Umbrales de |Δkt| para el régimen de rampa.
BINS_RAMPA = [-np.inf, 0.1, 0.25, np.inf]
ETIQ_RAMPA = ["rampa suave (<0.1)", "rampa moderada (0.1-0.25)", "rampa fuerte (>0.25)"]


def clasificar_nubosidad(kt: pd.Series) -> pd.Series:
    return pd.cut(kt, bins=BINS_KT, labels=ETIQ_KT)


def clasificar_rampa(kt_true: pd.Series) -> pd.Series:
    """|kt(τ) - kt operativo previo|, sobre la serie de horas operativas (ordenada)."""
    dkt = (kt_true - kt_true.shift(1)).abs()
    return pd.cut(dkt, bins=BINS_RAMPA, labels=ETIQ_RAMPA)


def _tabla(y, ghi_mod, ghi_ref, grupos, nombre_col):
    filas = []
    for etiqueta in grupos.cat.categories:
        m = grupos == etiqueta
        if not m.any():
            continue
        r_mod = M.rmse(y[m], ghi_mod[m])
        r_ref = M.rmse(y[m], ghi_ref[m])
        filas.append({
            nombre_col: etiqueta, "n": int(m.sum()),
            "RMSE_modelo": r_mod, "RMSE_persistence": r_ref,
            "MAE_modelo": M.mae(y[m], ghi_mod[m]),
            "R2_modelo": M.r2(y[m], ghi_mod[m]),
            "skill": M.skill(r_mod, r_ref),
        })
    return pd.DataFrame(filas)


def metricas_por_regimen(pred_modelo: pd.DataFrame,
                         ghi_pred_ref: pd.Series | None = None) -> dict:
    """`pred_modelo`: salida de xgb.predecir_ghi (con kt_true/ghi_true/ghi_pred).
    `ghi_pred_ref`: GHI de persistence alineable por índice; si None, usa la columna
    `ghi_persistence` de `pred_modelo` (multi-nodo).

    Devuelve {'nubosidad': df, 'rampa': df} con métricas por bin. La rampa se calcula
    POR NODO (con `nodo_id` si está presente) para no cruzar nodos con el shift.
    """
    d = pred_modelo.copy()
    d["ghi_ref"] = (ghi_pred_ref.reindex(d.index) if ghi_pred_ref is not None
                    else d["ghi_persistence"])
    d = d.dropna(subset=["ghi_true", "ghi_pred", "ghi_ref", "kt_true"]).sort_index()

    dkt = (d.groupby("nodo_id")["kt_true"].diff().abs() if "nodo_id" in d.columns
           else d["kt_true"].diff().abs())
    rampa = pd.cut(dkt, bins=BINS_RAMPA, labels=ETIQ_RAMPA)

    y, ghi_mod, ghi_ref = d["ghi_true"], d["ghi_pred"], d["ghi_ref"]
    return {
        "nubosidad": _tabla(y, ghi_mod, ghi_ref, clasificar_nubosidad(d["kt_true"]),
                            "regimen_nubosidad"),
        "rampa": _tabla(y, ghi_mod, ghi_ref, rampa, "regimen_rampa"),
    }
