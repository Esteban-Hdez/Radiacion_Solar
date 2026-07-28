"""Tests del bloque de nubes: encoding de opacidad (anti-fuga) y fracción nublada."""
import numpy as np
import pandas as pd

from forecasting import config as C
from forecasting import features as F
from forecasting import target as T
from forecasting.features import nubes as N


def test_encoding_solo_usa_train(serie_sintetica):
    """El encoding se ajusta solo con años de train (no toca val/test)."""
    op = N.ajustar_opacidad(serie_sintetica)
    kt = T.calcular_kt(serie_sintetica); msk = T.mascara_operativa(serie_sintetica)
    tr = serie_sintetica.index.year.isin(C.ANIOS_TRAIN) & msk & kt.notna()
    esperado = kt[tr].groupby(serie_sintetica["cloud_type"][tr]).mean()
    for code, val in esperado.items():
        assert np.isclose(op[int(code)], val)
    assert "_global_" in op


def test_categoria_no_vista_usa_global(serie_sintetica):
    """Un cloud_type ausente del encoding cae a la media global."""
    op = {0: 0.99, "_global_": 0.5}          # solo conoce el tipo 0
    feat = N.bloque_nubes(serie_sintetica, op)
    ct = serie_sintetica["cloud_type"]
    # score instantáneo (antes del shift): tipos !=0 -> global 0.5
    esperado = ct.map({0: 0.99}).mask(ct.notna() & ct.ne(0), 0.5)
    assert np.allclose(feat["cloud_op_lag1"].dropna(),
                       esperado.shift(1).dropna())


def test_frac_nublado_correcta(serie_sintetica):
    op = N.ajustar_opacidad(serie_sintetica)
    feat = N.bloque_nubes(serie_sintetica, op)
    nublado = (serie_sintetica["cloud_type"] > 0).astype(float)
    esperado = nublado.shift(1).rolling(12, min_periods=6).mean()
    comp = pd.concat([feat["frac_nublado_12h"].rename("o"),
                      esperado.rename("e")], axis=1).dropna()
    assert np.allclose(comp["o"], comp["e"])
    assert feat["frac_nublado_12h"].dropna().between(0, 1).all()


def test_nubes_via_construir_y_no_leakage(serie_sintetica):
    feat = F.construir(serie_sintetica, ("base", "nubes"))
    for c in ["cloud_op_lag1", "cloud_op_media_12h", "frac_nublado_12h"]:
        assert c in F.columnas_features(feat)
    # 1ª fila NaN (rezago) -> sin fuga.
    assert pd.isna(feat.iloc[0]["cloud_op_lag1"])
    # el encoding queda accesible como artefacto.
    assert "opacidad_cloud" in feat.attrs
