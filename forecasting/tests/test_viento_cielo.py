"""Tests de los bloques de features viento (componentes) y cielo (difusa, rocío)."""
import numpy as np

from forecasting.features.viento import bloque_viento
from forecasting.features.cielo import bloque_cielo


def test_componentes_viento_convencion(serie_sintetica):
    """u/v deben seguir u=-VV·sin(DV), v=-VV·cos(DV) con el viento de τ-1."""
    feat = bloque_viento(serie_sintetica)
    vv = serie_sintetica["wind_speed"].shift(1)
    dv = np.deg2rad(serie_sintetica["wind_direction"].shift(1))
    assert np.allclose(feat["wind_u_lag1"].dropna(),
                       (-vv * np.sin(dv)).dropna())
    assert np.allclose(feat["wind_v_lag1"].dropna(),
                       (-vv * np.cos(dv)).dropna())


def test_direccion_continua_acotada(serie_sintetica):
    feat = bloque_viento(serie_sintetica)
    assert feat["wind_dir_sin_lag1"].dropna().between(-1, 1).all()
    assert feat["wind_dir_cos_lag1"].dropna().between(-1, 1).all()


def test_viento_es_pasado(serie_sintetica):
    """La 1ª fila no tiene viento de τ-1 (shift) -> NaN (sin fuga)."""
    feat = bloque_viento(serie_sintetica)
    assert feat.iloc[0].isna().all()


def test_fraccion_difusa_rango_y_lag(serie_sintetica):
    feat = bloque_cielo(serie_sintetica)
    assert feat["kd_difusa_lag1"].dropna().between(0, 1).all()
    # kd_difusa_lag1(i) = (dhi/ghi)(i-1) donde ghi>0.
    kd = (serie_sintetica["dhi"] / serie_sintetica["ghi"].where(serie_sintetica["ghi"] > 0)).clip(0, 1)
    assert np.allclose(feat["kd_difusa_lag1"].dropna(), kd.shift(1).dropna())


def test_depresion_rocio(serie_sintetica):
    feat = bloque_cielo(serie_sintetica)
    esperado = (serie_sintetica["temperature"] - serie_sintetica["dew_point"]).shift(1)
    assert np.allclose(feat["dewpoint_depresion_lag1"].dropna(), esperado.dropna())
