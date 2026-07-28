"""
Métricas de evaluación del pronóstico, reutilizables por cualquier modelo.

Todas operan sobre GHI reconstruido [W/m²] (o sobre kt si se prefiere) y SOLO
sobre las horas que se le pasen (el llamador filtra a operativas). Convención de
signo del sesgo: MBE = mean(pred - obs) → positivo = sobreestima.

`skill` es el forecast skill score: 1 - RMSE_modelo / RMSE_ref. Con ref = smart
persistence, skill > 0 significa "mejor que persistence" (la meta del proyecto).
"""
from __future__ import annotations
import numpy as np
import pandas as pd


def _limpiar(y: pd.Series, yhat: pd.Series) -> tuple[np.ndarray, np.ndarray]:
    """Alinea y descarta pares con NaN en cualquiera de las dos series."""
    d = pd.concat([y.rename("y"), yhat.rename("yhat")], axis=1).dropna()
    return d["y"].to_numpy(), d["yhat"].to_numpy()


def rmse(y: pd.Series, yhat: pd.Series) -> float:
    a, b = _limpiar(y, yhat)
    return float(np.sqrt(np.mean((b - a) ** 2))) if len(a) else np.nan


def mae(y: pd.Series, yhat: pd.Series) -> float:
    a, b = _limpiar(y, yhat)
    return float(np.mean(np.abs(b - a))) if len(a) else np.nan


def mbe(y: pd.Series, yhat: pd.Series) -> float:
    """Mean Bias Error = mean(pred - obs). Positivo = sobreestima."""
    a, b = _limpiar(y, yhat)
    return float(np.mean(b - a)) if len(a) else np.nan


def r2(y: pd.Series, yhat: pd.Series) -> float:
    """Coeficiente de determinación R² = 1 - SS_res/SS_tot. 1 = perfecto;
    0 = igual que predecir la media; <0 = peor que la media."""
    a, b = _limpiar(y, yhat)
    if len(a) < 2:
        return np.nan
    ss_tot = np.sum((a - a.mean()) ** 2)
    if ss_tot == 0:
        return np.nan
    return float(1.0 - np.sum((a - b) ** 2) / ss_tot)


def skill(rmse_modelo: float, rmse_ref: float) -> float:
    """Forecast skill score vs una referencia. 1 = perfecto, 0 = igual que ref."""
    if rmse_ref is None or not np.isfinite(rmse_ref) or rmse_ref == 0:
        return np.nan
    return 1.0 - rmse_modelo / rmse_ref


def evaluar(y: pd.Series, yhat: pd.Series,
            fill_flag: pd.Series | None = None,
            rmse_ref: float | None = None) -> pd.DataFrame:
    """Tabla de métricas: fila global y, si se da fill_flag, segmentada.

    Segmentos: 'limpio' (fill_flag == 0) y 'rellenado' (fill_flag > 0). El segmento
    se define por el fill_flag de la HORA OBJETIVO. Devuelve n, RMSE, MAE, MBE y
    (si hay rmse_ref) el skill de cada fila.
    """
    filas = []

    def _fila(nombre: str, yy: pd.Series, hh: pd.Series) -> dict:
        r = rmse(yy, hh)
        d = {"segmento": nombre, "n": int(pd.concat([yy, hh], axis=1).dropna().shape[0]),
             "RMSE": r, "MAE": mae(yy, hh), "MBE": mbe(yy, hh), "R2": r2(yy, hh)}
        if rmse_ref is not None:
            d["skill_vs_ref"] = skill(r, rmse_ref)
        return d

    filas.append(_fila("global", y, yhat))
    if fill_flag is not None:
        limpio = fill_flag == 0
        filas.append(_fila("limpio (ff=0)", y[limpio], yhat[limpio]))
        filas.append(_fila("rellenado (ff>0)", y[~limpio], yhat[~limpio]))
    return pd.DataFrame(filas)
