"""Tests de métricas y clasificación por régimen."""
import numpy as np
import pandas as pd

from forecasting.eval import metrics as M
from forecasting.eval import regimen as REG


def test_metricas_perfectas():
    y = pd.Series([0.0, 100.0, 500.0, 900.0])
    assert M.rmse(y, y) == 0.0
    assert M.mae(y, y) == 0.0
    assert M.mbe(y, y) == 0.0
    assert M.r2(y, y) == 1.0


def test_mbe_signo():
    y = pd.Series([100.0, 200.0])
    yhat = y + 10          # sobreestima
    assert M.mbe(y, yhat) == 10.0


def test_skill_definicion():
    # modelo con la mitad de RMSE que la referencia -> skill 0.5.
    assert M.skill(50.0, 100.0) == 0.5
    assert np.isnan(M.skill(50.0, 0.0))


def test_clasificar_nubosidad_bins():
    kt = pd.Series([0.1, 0.5, 0.9])
    etiquetas = REG.clasificar_nubosidad(kt).astype(str).tolist()
    assert etiquetas == ["cubierto (kt<0.3)", "parcial (0.3-0.7)", "despejado (kt>=0.7)"]


def test_r2_negativo_si_peor_que_media():
    y = pd.Series([1.0, 2.0, 3.0, 4.0])
    yhat = pd.Series([4.0, 3.0, 2.0, 1.0])   # anti-correlacionado
    assert M.r2(y, yhat) < 0
