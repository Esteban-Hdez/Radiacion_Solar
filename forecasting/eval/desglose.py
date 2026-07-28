"""
Desglose rico de métricas para el multi-horizonte. Sobre una tabla de predicciones
(columnas: ghi_true, ghi_pred, ghi_persistence, kt_true, horizonte, hora_target,
mes_target, nodo_id, fill_flag) calcula, por grupo, RMSE del modelo y de persistence,
skill, MAE, MBE y R² — y además cortes globales, por horizonte, hora, mes, nodo,
régimen de nubosidad y fill_flag, con resúmenes de RANGO (min/media/max).
"""
from __future__ import annotations
import numpy as np
import pandas as pd

from forecasting.eval import metrics as M
from forecasting.eval import regimen as REG


def _fila(g: pd.DataFrame) -> dict:
    r_mod = M.rmse(g["ghi_true"], g["ghi_pred"])
    r_ref = M.rmse(g["ghi_true"], g["ghi_persistence"])
    return {"n": len(g), "RMSE_modelo": r_mod, "RMSE_persistence": r_ref,
            "MAE_modelo": M.mae(g["ghi_true"], g["ghi_pred"]),
            "MBE_modelo": M.mbe(g["ghi_true"], g["ghi_pred"]),
            "R2_modelo": M.r2(g["ghi_true"], g["ghi_pred"]),
            "skill": M.skill(r_mod, r_ref)}


def global_(pred: pd.DataFrame) -> pd.DataFrame:
    return pd.DataFrame([{"grupo": "global", **_fila(pred)}])


def por(pred: pd.DataFrame, col: str) -> pd.DataFrame:
    filas = [{col: k, **_fila(g)} for k, g in pred.groupby(col)]
    return pd.DataFrame(filas).sort_values(col).reset_index(drop=True)


def por_regimen(pred: pd.DataFrame) -> pd.DataFrame:
    reg = REG.clasificar_nubosidad(pred["kt_true"])
    filas = []
    for etiqueta in reg.cat.categories:
        g = pred[reg == etiqueta]
        if len(g):
            filas.append({"regimen_nubosidad": etiqueta, **_fila(g)})
    return pd.DataFrame(filas)


def por_fillflag(pred: pd.DataFrame) -> pd.DataFrame:
    seg = np.where(pred["fill_flag"] > 0, "rellenado_ff_pos", "limpio_ff0")
    filas = [{"segmento": s, **_fila(pred[seg == s])} for s in np.unique(seg)]
    return pd.DataFrame(filas)


def rangos(tabla: pd.DataFrame, col_grupo: str, metrica: str = "skill") -> dict:
    """Resumen de RANGO de una métrica a lo largo de un desglose (min/media/max)."""
    s = tabla[metrica]
    return {"por": col_grupo, "metrica": metrica, "min": float(s.min()),
            "media": float(s.mean()), "max": float(s.max()),
            "argmin": tabla.loc[s.idxmin(), col_grupo],
            "argmax": tabla.loc[s.idxmax(), col_grupo]}


def desglose_completo(pred: pd.DataFrame) -> dict:
    """Todos los cortes en un dict de DataFrames + un resumen de rangos."""
    d = {
        "global": global_(pred),
        "horizonte": por(pred, "horizonte"),
        "hora": por(pred, "hora_target"),
        "mes": por(pred, "mes_target"),
        "nodo": por(pred, "nodo_id"),
        "regimen": por_regimen(pred),
        "fill_flag": por_fillflag(pred),
    }
    d["rangos"] = pd.DataFrame([
        rangos(d["horizonte"], "horizonte"),
        rangos(d["hora"], "hora_target"),
        rangos(d["mes"], "mes_target"),
        rangos(d["nodo"], "nodo_id"),
    ])
    return d


def heatmap_hora_horizonte(pred: pd.DataFrame, valor: str = "skill") -> pd.DataFrame:
    """Matriz hora_target × horizonte de una métrica (para heatmap)."""
    filas = [{"hora_target": hk, "horizonte": hz, **_fila(g)}
             for (hk, hz), g in pred.groupby(["hora_target", "horizonte"])]
    t = pd.DataFrame(filas)
    return t.pivot(index="hora_target", columns="horizonte", values=valor)
