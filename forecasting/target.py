"""
Target del pronóstico y utilidades derivadas, en un solo lugar para que todo el
pipeline (baseline, XGBoost, …) las use igual y sin duplicar reglas.

Decisiones (ver `config.py` y README):
- Target = kt = ghi / clearsky_ghi, recortado a [0, KT_MAX]. Solo se define donde
  clearsky_ghi > 0.
- Horas OPERATIVAS = clearsky_ghi > CLEARSKY_MIN y solar_zenith_angle < ZENITH_MAX.
  Las noches nunca son target.
- El GHI se reconstruye como kt * clearsky_ghi (nunca se predice GHI crudo).
- La partición es temporal por años (sin shuffle), definida en config.
"""
from __future__ import annotations
import pandas as pd

from forecasting import config as C


def calcular_kt(df: pd.DataFrame) -> pd.Series:
    """kt = clip(ghi / clearsky_ghi, 0, KT_MAX). NaN donde clearsky_ghi <= 0."""
    cs = df[C.COL_CLEARSKY]
    kt = df[C.COL_GHI] / cs.where(cs > 0)
    return kt.clip(lower=0.0, upper=C.KT_MAX)


def mascara_operativa(df: pd.DataFrame) -> pd.Series:
    """True en horas operativas: clearsky_ghi > CLEARSKY_MIN y zenith < ZENITH_MAX."""
    return (df[C.COL_CLEARSKY] > C.CLEARSKY_MIN) & (df[C.COL_ZENITH] < C.ZENITH_MAX)


def reconstruir_ghi(kt: pd.Series, clearsky: pd.Series) -> pd.Series:
    """GHI [W/m²] = kt * clearsky_ghi."""
    return kt * clearsky


def split_temporal(df: pd.DataFrame) -> dict[str, pd.DataFrame]:
    """Parte por años según config: train 2020-22 / val 2023 / test 2024.

    Requiere índice datetime. No hace shuffle. Filas fuera de los años definidos
    (p.ej. 2017) se descartan.
    """
    year = df.index.year
    return {
        "train": df[year.isin(C.ANIOS_TRAIN)],
        "val": df[year.isin(C.ANIOS_VAL)],
        "test": df[year.isin(C.ANIOS_TEST)],
    }
