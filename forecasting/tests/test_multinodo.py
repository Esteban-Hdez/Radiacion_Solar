"""Tests del ensamblado multi-nodo de features y de la persistencia en-frame."""
import numpy as np
import pandas as pd

from forecasting import features as F
from forecasting import target as T


def _bloque_sintetico(serie, nodos=(10, 20, 30)):
    """Replica la serie sintética en varios nodos con desplazamientos, en formato
    largo (como `cargar_bloque`): columnas datetime + nodo_id + variables."""
    partes = []
    for i, n in enumerate(nodos):
        d = serie.reset_index().copy()
        d["nodo_id"] = n
        d["ghi"] = (d["ghi"] * (1 + 0.05 * i)).clip(upper=d["clearsky_ghi"]).astype("int16")
        d["latitude"] = 23.7 + 0.04 * i
        partes.append(d)
    return pd.concat(partes, ignore_index=True)


def test_construir_bloque_tiene_nodo_id_meta(serie_sintetica):
    bloque = _bloque_sintetico(serie_sintetica)
    feat = F.construir_bloque(bloque, ("base", "nocturno"))
    assert "nodo_id" in feat.columns
    # nodo_id es META: no entra como feature.
    assert "nodo_id" not in F.columnas_features(feat)
    assert feat["nodo_id"].nunique() == 3


def test_no_leakage_entre_nodos(serie_sintetica):
    """El kt_lag1 de la 1ª fila de cada nodo debe ser NaN (no toma el kt del nodo
    anterior en el concatenado)."""
    bloque = _bloque_sintetico(serie_sintetica)
    feat = F.construir_bloque(bloque, ("base",))
    primeras = feat.groupby("nodo_id").head(1)
    assert primeras["kt_lag1"].isna().all()


def test_persistencia_en_frame_por_nodo(serie_sintetica):
    """ghi_persistence (kt_last_op) debe reconstruirse por nodo sin cruzar nodos."""
    from forecasting.models import xgb as MX
    bloque = _bloque_sintetico(serie_sintetica)
    feat = F.construir_bloque(bloque, ("base",))
    # Entrena un modelo mínimo para poder predecir (pocos árboles).
    model, cols, splits = MX.entrenar(feat, params={"n_estimators": 10})
    pred = MX.predecir_ghi(model, feat, cols)
    assert "ghi_persistence" in pred.columns and "nodo_id" in pred.columns
    assert pred["nodo_id"].nunique() == 3


def test_comparar_usa_persistencia_en_frame(serie_sintetica):
    from forecasting.eval import comparar as CMP
    from forecasting.models import xgb as MX
    bloque = _bloque_sintetico(serie_sintetica)
    feat = F.construir_bloque(bloque, ("base",))
    model, cols, splits = MX.entrenar(feat, params={"n_estimators": 10})
    pred = MX.predecir_ghi(model, feat, cols)
    tab = CMP.comparar(pred, None, nombre="m")   # ref None -> usa ghi_persistence
    assert (tab["segmento"] == "global").any()
    assert "skill" in tab.columns
