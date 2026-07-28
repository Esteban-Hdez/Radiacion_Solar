"""
Baseline obligatorio: smart persistence en el espacio de kt.

Predice kt(t+1) = kt(t) y reconstruye GHI como kt_pred * clearsky_ghi(t+1). Es la
referencia que todo modelo debe superar (skill > 0).

Dos variantes, por la discontinuidad noche→mañana (la 1ª hora operativa del día no
tiene hora-reloj anterior operativa):

- A (carry-forward): usa el ÚLTIMO kt operativo observado, aunque sea de la tarde
  anterior. Cubre todas las horas operativas → es el baseline de la tarea completa
  y da el RMSE de referencia para el skill.
- B (pares consecutivos): usa kt(t-1) solo si t-1 también es operativa; descarta la
  1ª hora de cada mañana. Es la persistencia de 1 h "pura" (diagnóstico).

Todo se construye sobre la malla horaria CONTIGUA (sin shuffle): así `shift(1)` es
siempre "una hora antes" de reloj y no hay fuga temporal.
"""
from __future__ import annotations
import pandas as pd

from forecasting import config as C
from forecasting import target as T


def smart_persistence(df: pd.DataFrame) -> pd.DataFrame:
    """Construye predicciones de persistence sobre la serie horaria contigua.

    `df` debe tener índice datetime horario contiguo y las columnas ghi/clearsky/
    zenith/fill_flag. Devuelve un DataFrame alineado al índice con:

      op            : hora objetivo operativa (donde tiene sentido evaluar)
      kt_true       : kt observado en la hora objetivo
      ghi_true      : ghi observado en la hora objetivo
      clearsky_ghi  : clearsky de la hora objetivo (para reconstruir)
      fill_flag     : fill_flag de la hora objetivo (para segmentar)
      kt_pred_A / ghi_pred_A : variante carry-forward
      kt_pred_B / ghi_pred_B : variante pares consecutivos (NaN si t-1 no operativa)

    La evaluación de cada variante se hace donde `op` y el `*_pred_*` no son NaN.
    """
    op = T.mascara_operativa(df)
    kt = T.calcular_kt(df)
    kt_op = kt.where(op)               # kt solo en horas operativas; NaN si no

    # Variante A: arrastra el último kt operativo (salta la noche) y desplaza 1 h.
    kt_pred_A = kt_op.ffill().shift(1)
    # Variante B: kt de la hora anterior SOLO si esa hora fue operativa.
    kt_pred_B = kt_op.shift(1)

    cs = df[C.COL_CLEARSKY]
    out = pd.DataFrame(index=df.index)
    out["op"] = op
    out["kt_true"] = kt.where(op)
    out["ghi_true"] = df[C.COL_GHI].where(op)
    out["clearsky_ghi"] = cs
    out["fill_flag"] = df["fill_flag"]
    out["kt_pred_A"] = kt_pred_A.where(op)
    out["kt_pred_B"] = kt_pred_B.where(op)
    out["ghi_pred_A"] = T.reconstruir_ghi(out["kt_pred_A"], cs)
    out["ghi_pred_B"] = T.reconstruir_ghi(out["kt_pred_B"], cs)
    return out
