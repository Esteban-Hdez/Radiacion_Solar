"""Tests de las features espaciales de advección (multi-nodo)."""
import numpy as np
import pandas as pd

from forecasting import features as F


def _grid_3x3(serie):
    """Bloque sintético de 9 nodos en malla 3×3 (formato largo, como cargar_bloque),
    cada nodo con un kt distinto para poder verificar el vecindario."""
    partes = []
    nodo = 0
    for i in range(3):          # lat
        for j in range(3):      # lon
            d = serie.reset_index().copy()
            d["nodo_id"] = nodo
            # ghi escalado por nodo -> kt distinto por nodo.
            factor = 0.5 + 0.05 * nodo
            d["ghi"] = (d["clearsky_ghi"] * factor).round().clip(upper=d["clearsky_ghi"]).astype("int16")
            d["latitude"] = 23.0 + 0.04 * i
            d["longitude"] = -99.0 + 0.04 * j
            partes.append(d)
            nodo += 1
    return pd.concat(partes, ignore_index=True)


def test_features_espaciales_presentes_y_son_features(serie_sintetica):
    bloque = _grid_3x3(serie_sintetica)
    feat = F.construir_bloque(bloque, ("base", "viento", "adveccion"))
    esp = ["kt_vecinos_mean", "kt_vecinos_std", "kt_grad_x", "kt_grad_y", "kt_adveccion"]
    assert all(c in feat.columns for c in esp)
    assert all(c in F.columnas_features(feat) for c in esp)   # son features, no meta


def test_no_leakage_espacial_primera_hora(serie_sintetica):
    """Las features espaciales usan kt de vecinos en τ-1: la 1ª hora es NaN."""
    bloque = _grid_3x3(serie_sintetica)
    feat = F.construir_bloque(bloque, ("base", "viento", "adveccion"))
    primeras = feat.groupby("nodo_id").head(1)
    assert primeras["kt_vecinos_mean"].isna().all()


def test_upwind_features_presentes_y_sin_fuga(serie_sintetica):
    bloque = _grid_3x3(serie_sintetica)
    feat = F.construir_bloque(
        bloque, ("base", "viento", "nubes", "adveccion", "adveccion_upwind"))
    nuevas = ["kt_upwind", "kt_vecinos_mean_r2", "cloud_op_vecinos_mean"]
    assert all(c in F.columnas_features(feat) for c in nuevas)
    assert feat.groupby("nodo_id").head(1)["kt_upwind"].isna().all()   # τ-1 -> 1ª NaN


def test_offsets_radio_conteo():
    from forecasting.features.adveccion import _offsets_radio
    assert len(_offsets_radio(1)) == 8       # 3×3 - centro
    assert len(_offsets_radio(2)) == 24      # 5×5 - centro
    assert len(_offsets_radio(3)) == 48      # 7×7 - centro


def test_bloque_r23_incluye_r3(serie_sintetica):
    bloque = _grid_3x3(serie_sintetica)
    feat = F.construir_bloque(
        bloque, ("base", "viento", "nubes", "adveccion_upwind_r23"))
    cols = F.columnas_features(feat)
    assert "kt_vecinos_mean_r2" in cols and "kt_vecinos_mean_r3" in cols


def test_upwind_viento_cero_es_kt_propio(serie_sintetica):
    """Con viento 0 no hay desplazamiento: kt_upwind = kt del propio nodo en τ-1
    (= kt_lag1)."""
    bloque = _grid_3x3(serie_sintetica)
    bloque["wind_speed"] = 0.0                       # sin viento -> origen = el nodo
    feat = F.construir_bloque(
        bloque, ("base", "viento", "nubes", "adveccion", "adveccion_upwind"))
    comp = feat[["kt_upwind", "kt_lag1"]].dropna()
    assert np.allclose(comp["kt_upwind"], comp["kt_lag1"])


def test_vecinos_mean_correcto_nodo_central(serie_sintetica):
    """kt_vecinos_mean del nodo central (4) = media de los 8 vecinos en τ-1."""
    bloque = _grid_3x3(serie_sintetica)
    feat = F.construir_bloque(bloque, ("base", "viento", "adveccion"))
    # kt por nodo en formato ancho, en τ-1.
    K = feat.reset_index().pivot(index="datetime", columns="nodo_id", values="kt")
    Kprev = K.shift(1)
    vecinos = [0, 1, 2, 3, 5, 6, 7, 8]         # todos menos el central (4)
    esperado = Kprev[vecinos].mean(axis=1)
    obtenido = feat[feat.nodo_id == 4]["kt_vecinos_mean"]
    comp = pd.concat([esperado.rename("e"), obtenido.rename("o")], axis=1).dropna()
    assert np.allclose(comp["e"], comp["o"])
