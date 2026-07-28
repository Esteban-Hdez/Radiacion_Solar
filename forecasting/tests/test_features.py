"""Tests de features: anti-leakage y composición de bloques."""
import numpy as np

from forecasting import features as F
from forecasting import target as T


def test_no_leakage_observadas_crudas_en_tau(serie_sintetica):
    """Ninguna feature debe ser la observada CRUDA en τ (ghi/dni/dhi ni sus UV)."""
    feat = F.construir(serie_sintetica, ("base", "volatilidad", "nocturno"))
    cols = F.columnas_features(feat)
    prohibidas = {"ghi", "dni", "dhi", "ghi_uv_280_400", "ghi_uv_295_385"}
    assert prohibidas.isdisjoint(cols)


def test_lags_son_pasado(serie_sintetica):
    """kt_lag1(τ) debe igualar kt(τ-1): mira estrictamente hacia atrás (sin fuga)."""
    feat = F.construir(serie_sintetica, ("base",))
    kt = T.calcular_kt(serie_sintetica)
    # Comparar en filas sin NaN por el shift.
    comp = feat["kt_lag1"].dropna()
    assert np.allclose(comp.values, kt.shift(1).loc[comp.index].values, equal_nan=True)


def test_meta_no_entra_como_feature(serie_sintetica):
    feat = F.construir(serie_sintetica, ("base",))
    cols = F.columnas_features(feat)
    assert set(F.META_COLS).isdisjoint(cols)


def test_composicion_bloques_es_aditiva(serie_sintetica):
    base = F.columnas_features(F.construir(serie_sintetica, ("base",)))
    full = F.columnas_features(F.construir(serie_sintetica, ("base", "nocturno")))
    assert set(base).issubset(full) and len(full) > len(base)


def test_bloque_desconocido_falla(serie_sintetica):
    import pytest
    with pytest.raises(ValueError):
        F.construir(serie_sintetica, ("noexiste",))
