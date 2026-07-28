"""Tests del multi-horizonte: construcción operativa, target desplazado y no-fuga."""
import numpy as np
import pandas as pd

from forecasting import multihorizonte as MH
from forecasting import target as T
from forecasting.features import nubes as N


def _serie_op(serie_sintetica):
    op = N.ajustar_opacidad(serie_sintetica)
    return MH._serie_operativa(serie_sintetica, op)


def test_solo_horas_operativas(serie_sintetica):
    O = _serie_op(serie_sintetica)
    op = T.mascara_operativa(serie_sintetica)
    assert len(O) == int(op.sum())               # solo operativas


def test_target_es_h_operativas_adelante(serie_sintetica):
    O = _serie_op(serie_sintetica).reset_index(drop=True)
    ktmap = pd.Series(O["kt"].to_numpy(), index=O["datetime"].to_numpy())
    feat = MH._construir_nodo(O, (1, 5))
    # kt_now = kt en el base; kt(target) = kt en el objetivo (alineado por datetime).
    for h in (1, 5):
        sub = feat[feat["horizonte"] == h]
        assert np.allclose(sub["kt_now"], sub["datetime_base"].map(ktmap))
        assert np.allclose(sub["kt"], sub["datetime_target"].map(ktmap))


def test_persistencia_es_kt_now(serie_sintetica):
    O = _serie_op(serie_sintetica).reset_index(drop=True)
    feat = MH._construir_nodo(O, (3,))
    assert np.allclose(feat["kt_last_op"], feat["kt_now"])   # persistencia = kt(t)


def test_horizonte_y_gap_son_features(serie_sintetica):
    O = _serie_op(serie_sintetica).reset_index(drop=True)
    feat = MH._construir_nodo(O, (1, 2, 3))
    cols = MH.columnas_features(feat)
    assert "horizonte" in cols and "gap_horas" in cols
    # el target/kt y las columnas de desglose NO son features
    for m in ["kt", "ghi_true", "clearsky_ghi_target", "hora_target", "nodo_id"]:
        assert m not in cols


def test_deterministas_del_objetivo(serie_sintetica):
    """clearsky_ghi (feature determinista) es el del objetivo τ_h, no el del base."""
    O = _serie_op(serie_sintetica).reset_index(drop=True)
    csmap = pd.Series(O["clearsky_ghi"].to_numpy(), index=O["datetime"].to_numpy())
    feat = MH._construir_nodo(O, (4,))
    assert np.allclose(feat["clearsky_ghi"], feat["datetime_target"].map(csmap))
