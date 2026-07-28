"""
Bloque de features de ESTADO DE CIELO (precursores de nubosidad, baratos).

- Fracción difusa `kd = dhi / ghi`: sube mucho con nubes (más radiación difusa que
  directa). Es casi un termómetro de nubosidad. Se usa rezagada (estado en τ-1) y su
  tendencia (para captar el cielo cerrándose/abriéndose).
- Depresión del punto de rocío `T − Td`: spread pequeño ⇒ aire casi saturado ⇒
  nubes/niebla probables. Indicador clásico de formación de nubes.

Todo OBSERVADO ⇒ rezagado (`.shift(>=1)`), sin fuga con el target en τ.
"""
from __future__ import annotations
import pandas as pd


def bloque_cielo(df: pd.DataFrame) -> pd.DataFrame:
    out = pd.DataFrame(index=df.index)

    if "dhi" in df.columns and "ghi" in df.columns:
        ghi = df["ghi"]
        kd = (df["dhi"] / ghi.where(ghi > 0)).clip(0, 1)   # fracción difusa; NaN de noche
        out["kd_difusa_lag1"] = kd.shift(1)
        out["kd_difusa_lag2"] = kd.shift(2)
        out["kd_difusa_tend"] = kd.shift(1) - kd.shift(2)  # cielo cerrándose (+) / abriéndose (-)

    if "temperature" in df.columns and "dew_point" in df.columns:
        # Depresión del punto de rocío (T - Td): cercanía a saturación.
        out["dewpoint_depresion_lag1"] = (df["temperature"] - df["dew_point"]).shift(1)

    return out
