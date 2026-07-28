"""
Fixtures compartidas. `serie_sintetica` genera una serie horaria contigua de varios
días con un ciclo diurno de clearsky y noches, sin depender de datos en disco, para
que los tests corran rápido y de forma determinista.
"""
from __future__ import annotations
import numpy as np
import pandas as pd
import pytest


@pytest.fixture
def serie_sintetica() -> pd.DataFrame:
    idx = pd.date_range("2020-06-01", periods=24 * 20, freq="h")  # 20 días
    hora = idx.hour
    # Clearsky con forma de "campana" diurna (0 de noche), pico al mediodía.
    ang = np.clip(np.sin((hora - 6) / 12 * np.pi), 0, None)
    clearsky = (1000 * ang).round().astype("int16")
    zenith = np.where(clearsky > 0, 30.0, 120.0)          # <85 de día, >85 de noche
    rng = np.random.default_rng(0)
    kt_real = np.clip(0.8 + 0.15 * rng.standard_normal(len(idx)), 0.05, 1.0)
    ghi = (clearsky * kt_real).round().astype("int16")
    df = pd.DataFrame({
        "ghi": ghi, "dni": ghi, "dhi": (ghi * 0.25).round().astype("int16"),
        "clearsky_ghi": clearsky,
        "clearsky_dni": clearsky, "clearsky_dhi": (clearsky * 0.3).round().astype("int16"),
        "solar_zenith_angle": zenith,
        "fill_flag": np.where(rng.random(len(idx)) < 0.1, 50, 0).astype("int16"),
        "cloud_type": rng.integers(0, 10, len(idx)).astype("int16"),
        "cloud_fill_flag": 0,
        "temperature": 25 + 5 * np.sin(hora / 24 * 2 * np.pi),
        "dew_point": 15.0, "relative_humidity": 60.0, "pressure": 1013.0,
        "precipitable_water": 2.0, "wind_speed": 3.0, "wind_direction": 180.0,
        "surface_albedo": 0.2, "aerosol_optical_depth": 0.1, "alpha": 1.0,
        "asymmetry": 0.6, "ssa": 0.9, "ozone": 0.3,
        "latitude": 23.7, "longitude": -99.1, "msnm": 320.0, "nodo_id": 1736,
    }, index=idx)
    df.index.name = "datetime"
    return df
