"""
Reporte del baseline de Fase 2: arma la tabla de métricas de smart persistence por
split × variante × segmento de fill_flag, y la deja lista para CSV y para que la
Fase 3 importe el RMSE de referencia.

Skill del baseline: se mide contra el predictor TONTO de cielo despejado (kt=1, es
decir ghi_pred = clearsky_ghi). Así "skill_vs_clearsky > 0" demuestra que la
persistencia ya aporta sobre suponer siempre cielo despejado. El skill de los
MODELOS de Fase 3 se medirá, en cambio, contra la persistence (columna RMSE aquí).
"""
from __future__ import annotations
import pandas as pd

from forecasting import target as T
from forecasting.eval import metrics as M

VARIANTES = {"A_carryforward": "ghi_pred_A", "B_consecutivos": "ghi_pred_B"}
SEGMENTOS = {
    "global": None,
    "limpio_ff0": lambda ff: ff == 0,
    "rellenado_ff_pos": lambda ff: ff > 0,
}


def tabla_baseline(per: pd.DataFrame) -> pd.DataFrame:
    """DataFrame tidy con n, RMSE, MAE, MBE y skill_vs_clearsky por
    split × variante × segmento. `per` = salida de smart_persistence()."""
    splits = T.split_temporal(per)
    filas = []
    for split, s in splits.items():
        s = s[s["op"]]
        for vname, col in VARIANTES.items():
            for seg, cond in SEGMENTOS.items():
                sub = s if cond is None else s[cond(s["fill_flag"])]
                y, yhat = sub["ghi_true"], sub[col]
                naive = sub["clearsky_ghi"]              # kt = 1
                r = M.rmse(y, yhat)
                filas.append({
                    "split": split, "variante": vname, "segmento": seg,
                    "n": int(pd.concat([y, yhat], axis=1).dropna().shape[0]),
                    "RMSE": r, "MAE": M.mae(y, yhat), "MBE": M.mbe(y, yhat),
                    "skill_vs_clearsky": M.skill(r, M.rmse(y, naive)),
                })
    return pd.DataFrame(filas)


def rmse_referencia(tabla: pd.DataFrame, variante: str = "A_carryforward") -> dict[str, float]:
    """RMSE global de persistence por split para una variante: la referencia que
    los modelos de Fase 3 deben superar (skill_modelo = 1 - RMSE_modelo/este)."""
    g = tabla[(tabla["variante"] == variante) & (tabla["segmento"] == "global")]
    return dict(zip(g["split"], g["RMSE"]))
