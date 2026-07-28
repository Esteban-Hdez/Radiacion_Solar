"""
Métricas de pronóstico PROBABILÍSTICO (experimento 4).

Sobre el GHI reconstruido por cuantil:
- `pinball`: pérdida cuantílica (proper scoring). Media sobre cuantiles = calidad
  global del pronóstico probabilístico.
- `cobertura`: fracción de observaciones dentro de la banda [P_bajo, P_alto]. Para
  P10-P90 el objetivo nominal es 0.80. Menor ⇒ banda demasiado estrecha (exceso de
  confianza); mayor ⇒ demasiado ancha.
- `anchura` (sharpness): ancho medio de la banda en W/m². Se quiere lo más estrecha
  posible SIN perder cobertura.

Segmentado por régimen, la banda debe ENSANCHARSE en nublado/variable: es donde el
modelo (correctamente) declara más incertidumbre.
"""
from __future__ import annotations
import numpy as np
import pandas as pd

from forecasting.eval import regimen as REG


def pinball(y: pd.Series, q_pred: pd.Series, alpha: float) -> float:
    d = (y - q_pred).to_numpy()
    return float(np.mean(np.maximum(alpha * d, (alpha - 1) * d)))


def _cols_cuantiles(pred: pd.DataFrame) -> list[float]:
    alphas = []
    for c in pred.columns:
        if c.startswith("ghi_p") and c[5:].isdigit():
            alphas.append(int(c[5:]) / 100)
    return sorted(alphas)


def metricas_intervalo(pred: pd.DataFrame, alpha_bajo: float = 0.1,
                       alpha_alto: float = 0.9) -> pd.DataFrame:
    """Fila única con pinball medio, cobertura y anchura de la banda (GHI)."""
    alphas = _cols_cuantiles(pred)
    y = pred["ghi_true"]
    pin = np.mean([pinball(y, pred[f"ghi_p{int(a*100):02d}"], a) for a in alphas])
    lo = pred[f"ghi_p{int(alpha_bajo*100):02d}"]
    hi = pred[f"ghi_p{int(alpha_alto*100):02d}"]
    dentro = ((y >= lo) & (y <= hi))
    nominal = alpha_alto - alpha_bajo
    return pd.DataFrame([{
        "n": len(pred), "pinball_medio": pin,
        f"cobertura_{int(nominal*100)}": float(dentro.mean()),
        "cobertura_nominal": nominal,
        "anchura_media": float((hi - lo).mean()),
    }])


def metricas_intervalo_por_regimen(pred: pd.DataFrame, alpha_bajo: float = 0.1,
                                   alpha_alto: float = 0.9) -> pd.DataFrame:
    """Cobertura y anchura por régimen de nubosidad (la banda debe ensancharse en
    cielo cubierto/variable)."""
    d = pred.copy()
    d["_reg"] = REG.clasificar_nubosidad(d["kt_true"])
    lo = d[f"ghi_p{int(alpha_bajo*100):02d}"]
    hi = d[f"ghi_p{int(alpha_alto*100):02d}"]
    d["_dentro"] = (d["ghi_true"] >= lo) & (d["ghi_true"] <= hi)
    d["_ancho"] = hi - lo
    filas = []
    for etiqueta in d["_reg"].cat.categories:
        m = d["_reg"] == etiqueta
        if not m.any():
            continue
        filas.append({
            "regimen_nubosidad": etiqueta, "n": int(m.sum()),
            "cobertura": float(d.loc[m, "_dentro"].mean()),
            "anchura_media": float(d.loc[m, "_ancho"].mean()),
        })
    return pd.DataFrame(filas)
