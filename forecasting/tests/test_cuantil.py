"""Tests del pronóstico cuantílico: pérdida pinball, orden de cuantiles y métricas
de intervalo."""
import numpy as np
import pandas as pd

from forecasting.eval import cuantil as Q


def test_pinball_simetrico_en_mediana():
    y = pd.Series([0.0, 10.0, -10.0])
    # Para alpha=0.5 el pinball es 0.5*|error|.
    yhat = pd.Series([1.0, 9.0, -9.0])
    assert np.isclose(Q.pinball(y, yhat, 0.5), 0.5 * np.mean(np.abs(y - yhat)))


def test_pinball_penaliza_asimetrico():
    y = pd.Series([10.0])
    # Cuantil alto (0.9): subestimar (yhat<y) penaliza más que sobrestimar.
    sub = Q.pinball(y, pd.Series([8.0]), 0.9)
    sob = Q.pinball(y, pd.Series([12.0]), 0.9)
    assert sub > sob


def _pred_sintetica(n=200, seed=0):
    rng = np.random.default_rng(seed)
    idx = pd.date_range("2024-06-01", periods=n, freq="h")
    cs = 800.0
    kt_true = np.clip(0.7 + 0.2 * rng.standard_normal(n), 0, 1)
    p50 = np.clip(kt_true + 0.02 * rng.standard_normal(n), 0, 1)
    return pd.DataFrame({
        "kt_true": kt_true, "ghi_true": kt_true * cs, "clearsky_ghi": cs,
        "fill_flag": 0,
        "kt_p10": p50 - 0.1, "ghi_p10": (p50 - 0.1) * cs,
        "kt_p50": p50, "ghi_p50": p50 * cs,
        "kt_p90": p50 + 0.1, "ghi_p90": (p50 + 0.1) * cs,
        "kt_pred": p50, "ghi_pred": p50 * cs,
    }, index=idx)


def test_metricas_intervalo_columnas():
    pred = _pred_sintetica()
    tab = Q.metricas_intervalo(pred)
    assert {"n", "pinball_medio", "cobertura_80", "anchura_media"}.issubset(tab.columns)
    fila = tab.iloc[0]
    assert 0 <= fila["cobertura_80"] <= 1
    assert fila["anchura_media"] > 0


def test_intervalo_por_regimen_no_vacio():
    pred = _pred_sintetica()
    tab = Q.metricas_intervalo_por_regimen(pred)
    assert not tab.empty
    assert {"regimen_nubosidad", "cobertura", "anchura_media"}.issubset(tab.columns)
