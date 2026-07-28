"""Tests del target kt, máscara operativa y reconstrucción de GHI."""
import numpy as np

from forecasting import target as T
from forecasting import config as C


def test_kt_en_rango_y_nan_de_noche(serie_sintetica):
    kt = T.calcular_kt(serie_sintetica)
    op = T.mascara_operativa(serie_sintetica)
    # kt acotado a [0, KT_MAX] donde está definido.
    assert kt[op].between(0, C.KT_MAX).all()
    # De noche (clearsky==0) kt es NaN (división indefinida).
    assert kt[~op].isna().all()


def test_mascara_operativa_definicion(serie_sintetica):
    op = T.mascara_operativa(serie_sintetica)
    esperado = ((serie_sintetica[C.COL_CLEARSKY] > C.CLEARSKY_MIN)
                & (serie_sintetica[C.COL_ZENITH] < C.ZENITH_MAX))
    assert op.equals(esperado)


def test_reconstruccion_ghi_identidad(serie_sintetica):
    # kt * clearsky debe recuperar el ghi observado en horas operativas.
    kt = T.calcular_kt(serie_sintetica)
    op = T.mascara_operativa(serie_sintetica)
    ghi_rec = T.reconstruir_ghi(kt, serie_sintetica[C.COL_CLEARSKY])
    dif = (ghi_rec[op] - serie_sintetica["ghi"][op]).abs()
    # Tolerancia por el clip de kt a 1 (si ghi>clearsky por redondeo).
    assert (dif <= 1.0).mean() > 0.99


def test_split_temporal_sin_solape(serie_sintetica):
    kt = T.calcular_kt(serie_sintetica).to_frame("kt")
    sp = T.split_temporal(kt)
    # Aquí la serie es 2020 -> todo cae en train; val/test vacíos, sin solape.
    idx_all = set().union(*[set(v.index) for v in sp.values()])
    assert sum(len(v) for v in sp.values()) == len(idx_all)
