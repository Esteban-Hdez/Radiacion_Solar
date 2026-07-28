"""
Bloque de features de VOLATILIDAD / RAMPAS (experimento 1).

Objetivo: darle al modelo señal de "estoy en un régimen inestable" — que es donde
persistence y el XGBoost base fallan (nubes intermitentes, rampas de kt). Todo se
deriva de kt REZAGADO (`.shift(>=1)`), así que no hay fuga.

- Lags extra de kt (4-6 h + 48 h) para ver un arco más largo del pasado reciente.
- Rampas: diferencias de kt entre horas contiguas (Δkt) = cuánto/ cómo cambia.
- Volatilidad: desviación estándar y rango de kt en las últimas 3/6 h operativas.
  `kt_volat_*` alto ⇒ nubosidad intermitente reciente ⇒ hora difícil.

Se calcula sobre la serie horaria contigua de UN nodo. Se usa `kt_op` (kt solo en
horas operativas) para que las rolling no mezclen ceros nocturnos; `min_periods`
permite ventanas parciales (p.ej. primeras horas de la mañana).
"""
from __future__ import annotations
import pandas as pd

from forecasting import target as T

LAGS_KT_EXTRA = [4, 5, 6, 48]          # complementan los del bloque base (1,2,3,24)
VENTANAS_VOLAT = [3, 6]                 # horas operativas hacia atrás


def bloque_volatilidad(df: pd.DataFrame) -> pd.DataFrame:
    op = T.mascara_operativa(df)
    kt = T.calcular_kt(df)
    kt_op = kt.where(op)
    kt_prev = kt_op.shift(1)               # último kt operativo conocido (sin fuga)
    out = pd.DataFrame(index=df.index)

    # Lags extra (arco largo del pasado).
    for L in LAGS_KT_EXTRA:
        out[f"kt_lag{L}"] = kt.shift(L)

    # Rampas recientes (cambio de kt entre horas contiguas conocidas).
    out["kt_ramp1"] = kt.shift(1) - kt.shift(2)
    out["kt_ramp2"] = kt.shift(2) - kt.shift(3)
    out["kt_ramp_abs1"] = out["kt_ramp1"].abs()

    # Volatilidad reciente (std, rango, media) sobre kt operativo.
    for w in VENTANAS_VOLAT:
        mp = max(2, w // 2)
        roll = kt_prev.rolling(w, min_periods=mp)
        out[f"kt_std_{w}"] = roll.std()
        out[f"kt_mean_{w}"] = roll.mean()
        out[f"kt_rango_{w}"] = roll.max() - roll.min()
    return out
