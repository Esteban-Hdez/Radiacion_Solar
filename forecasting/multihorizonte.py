"""
Pronóstico MULTI-HORIZONTE t+1 … t+H en HORAS OPERATIVAS (día-adelante).

Diseño DIRECTO (un solo modelo, horizonte como feature):
- Se trabaja sobre la serie SOLO operativa de cada nodo (noches fuera). El horizonte h
  = h-ésima hora operativa futura, así el target `kt(τ_h)` siempre está definido.
- Cada ejemplo es (tiempo base t, horizonte h) -> target kt en τ_h. Features:
  * OBSERVADAS ancladas en el base t (estado "ahora": kt reciente, meteo, viento en
    componentes, opacidad de nube, difusa…). Conocidas en t.
  * DETERMINISTAS known-future en el objetivo τ_h (clearsky_*, zenith, calendario).
  * HORIZONTE h y el hueco de reloj `gap_horas` (τ_h - t), que varía por cruzar noches.
- Persistence de referencia por horizonte = kt(t) (último kt operativo), igual para toda h;
  se degrada al alejarse -> el skill del modelo crece con el horizonte.

Anti-leakage por construcción: las observadas usan datos ≤ t; el target y las
deterministas son de τ_h (futuro, pero known-future para las deterministas).

El resultado tiene el mismo contrato META que el pipeline t+1 (`kt`, `op`,
`clearsky_ghi_target`, `ghi_true`, `fill_flag`, `kt_last_op`=persistencia, `nodo_id`)
para reutilizar `models.xgb.entrenar/predecir_ghi`, más columnas de desglose
(`horizonte`, `hora_target`, `mes_target`).
"""
from __future__ import annotations
import numpy as np
import pandas as pd

from forecasting import config as C
from forecasting import target as T
from forecasting.data.loaders import cargar_bloque, serie_contigua_nodo
from forecasting.features import nubes as _nubes

HORIZONTES = tuple(range(1, 25))          # t+1 … t+24 horas operativas

_METEO = ["temperature", "dew_point", "relative_humidity", "pressure", "precipitable_water"]
_AERO = ["aerosol_optical_depth", "ozone"]
# Observadas ancladas en el base t (estado "ahora").
_OBS_NOW = (_METEO + _AERO + ["wind_u", "wind_v", "kd_difusa",
                              "dewpoint_depresion", "cloud_op", "cloud_type"])
_DET = ["clearsky_ghi", "clearsky_dni", "clearsky_dhi", "solar_zenith_angle"]
_ESTATICAS = ["latitude", "longitude", "msnm"]

# Columnas META (no entran al modelo).
_META = ["kt", "op", "clearsky_ghi_target", "ghi_true", "fill_flag", "kt_last_op",
         "nodo_id", "datetime_target", "hora_target", "mes_target"]


def columnas_features(feat: pd.DataFrame) -> list[str]:
    return [c for c in feat.columns if c not in _META]


def _serie_operativa(df_nodo: pd.DataFrame, opacidad: dict) -> pd.DataFrame:
    """Serie SOLO operativa de un nodo, con derivadas de estado (viento en componentes,
    difusa, opacidad de nube, depresión de rocío)."""
    op = T.mascara_operativa(df_nodo)
    kt = T.calcular_kt(df_nodo)
    O = df_nodo[op].copy()
    O["kt"] = kt[op]
    mapa = {int(k): v for k, v in opacidad.items() if k != "_global_"}
    O["cloud_op"] = O["cloud_type"].map(mapa).fillna(opacidad["_global_"])
    O["kd_difusa"] = (O["dhi"] / O["ghi"].where(O["ghi"] > 0)).clip(0, 1)
    O["dewpoint_depresion"] = O["temperature"] - O["dew_point"]
    dv = np.deg2rad(O["wind_direction"])
    O["wind_u"] = -O["wind_speed"] * np.sin(dv)
    O["wind_v"] = -O["wind_speed"] * np.cos(dv)
    return O.reset_index().rename(columns={"index": "datetime"}).sort_values("datetime")


def _construir_nodo(O: pd.DataFrame, horizontes) -> pd.DataFrame:
    """Ejemplos (base, horizonte) de un nodo."""
    O = O.reset_index(drop=True)
    ts = O["datetime"]

    base = pd.DataFrame(index=O.index)
    base["kt_now"] = O["kt"]
    for L in (1, 2, 3):
        base[f"kt_lag{L}"] = O["kt"].shift(L)              # horas OPERATIVAS atrás
    base["kt_ramp1"] = O["kt"] - O["kt"].shift(1)
    base["kt_std3"] = O["kt"].rolling(3).std()
    for c in _OBS_NOW:
        base[f"{c}_now"] = O[c].to_numpy()
    for c in _ESTATICAS:
        base[c] = O[c].to_numpy()

    filas = []
    for h in horizontes:
        tg = ts.shift(-h)
        d = base.copy()
        for c in _DET:                                     # deterministas en τ_h
            d[c] = O[c].shift(-h).to_numpy()
        d["hour"] = tg.dt.hour.to_numpy()
        d["doy"] = tg.dt.dayofyear.to_numpy()
        d["month"] = tg.dt.month.to_numpy()
        d["sin_hour"] = np.sin(2 * np.pi * d["hour"] / 24)
        d["cos_hour"] = np.cos(2 * np.pi * d["hour"] / 24)
        d["sin_doy"] = np.sin(2 * np.pi * d["doy"] / 365.25)
        d["cos_doy"] = np.cos(2 * np.pi * d["doy"] / 365.25)
        d["horizonte"] = h
        d["gap_horas"] = (tg - ts).dt.total_seconds().to_numpy() / 3600
        # target + meta
        d["kt"] = O["kt"].shift(-h).to_numpy()
        d["op"] = True
        d["clearsky_ghi_target"] = O["clearsky_ghi"].shift(-h).to_numpy()
        d["ghi_true"] = O["ghi"].shift(-h).to_numpy()
        d["fill_flag"] = O["fill_flag"].shift(-h).to_numpy()
        d["kt_last_op"] = O["kt"].to_numpy()               # persistencia = kt(t)
        d["nodo_id"] = O["nodo_id"].iloc[0]
        d["datetime_base"] = ts.to_numpy()
        d["datetime_target"] = tg.to_numpy()
        d["hora_target"] = (d["hour"] - 6) % 24            # hora LOCAL (UTC-6) para desglose
        d["mes_target"] = d["month"]
        filas.append(d)

    todo = pd.concat(filas, ignore_index=True)
    return todo.dropna(subset=["kt", "clearsky_ghi_target", "kt_lag3"])


def construir(nodos, horizontes=HORIZONTES, anios=None) -> pd.DataFrame:
    """Matriz multi-horizonte de un bloque de nodos. Índice = tiempo base (para el
    split temporal). Casts numéricos a float32 para memoria."""
    bloque = cargar_bloque(list(nodos), anios)
    opacidad = _nubes.ajustar_opacidad_largo(bloque)
    partes = []
    for _, g in bloque.groupby("nodo_id", sort=True):
        O = _serie_operativa(serie_contigua_nodo(g), opacidad)
        partes.append(_construir_nodo(O, horizontes))
    feat = pd.concat(partes, ignore_index=True).set_index("datetime_base")
    feat.index.name = "datetime"
    # float32 en las features numéricas (no en las meta datetime).
    fcols = columnas_features(feat)
    feat[fcols] = feat[fcols].astype("float32")
    return feat


def ejecutar(nodos, horizontes=HORIZONTES, exp_id="exp08_multihorizonte",
             version="v1", params=None) -> dict:
    """Construye, entrena y evalúa multi-horizonte; guarda artefactos y desgloses en
    Results/<region>/forecast/experiments/<exp_id>/<version>/."""
    import json
    import os
    from forecasting.models import xgb as MX
    from forecasting.eval import desglose as D

    d = os.path.join(C.DIR_EXPERIMENTS, exp_id, version)
    os.makedirs(d, exist_ok=True)
    feat = construir(nodos, horizontes)
    cols = columnas_features(feat)
    model, cols, splits = MX.entrenar(feat, cols=cols, params=params)
    pred = predecir(model, splits["test"], cols)

    dd = D.desglose_completo(pred)
    for k, v in dd.items():
        v.to_csv(os.path.join(d, f"desglose_{k}.csv"), index=False)
    D.heatmap_hora_horizonte(pred).to_csv(os.path.join(d, "heatmap_hora_horizonte.csv"))
    (pd.Series(model.feature_importances_, index=cols).sort_values(ascending=False)
     .rename("gain").to_csv(os.path.join(d, "feature_importance.csv")))
    model.save_model(os.path.join(d, "model.json"))
    pred.to_parquet(os.path.join(d, "predictions_test.parquet"))
    with open(os.path.join(d, "config.json"), "w") as f:
        json.dump({"exp_id": exp_id, "version": version, "modelo": "xgboost_multihorizonte",
                   "n_nodos": len(list(nodos)), "nodos": list(map(int, nodos)),
                   "horizontes": list(horizontes), "n_features": len(cols),
                   "best_iteration": int(model.best_iteration)}, f, indent=2)
    return {"feat": feat, "model": model, "pred": pred, "desglose": dd, "dir": d}


def predecir(model, feat_split: pd.DataFrame, cols) -> pd.DataFrame:
    """Predicción rica para el desglose (incluye horizonte/hora/mes/nodo/fill)."""
    s = feat_split
    kt_pred = np.clip(model.predict(s[cols]), 0.0, C.KT_MAX)
    cs = s["clearsky_ghi_target"]
    out = pd.DataFrame(index=s.index)
    out["kt_true"] = s["kt"].to_numpy()
    out["kt_pred"] = kt_pred
    out["ghi_true"] = s["ghi_true"].to_numpy()
    out["ghi_pred"] = kt_pred * cs.to_numpy()
    out["ghi_persistence"] = np.clip(s["kt_last_op"], 0, C.KT_MAX).to_numpy() * cs.to_numpy()
    out["fill_flag"] = s["fill_flag"].to_numpy()
    out["nodo_id"] = s["nodo_id"].to_numpy()
    out["horizonte"] = s["horizonte"].astype(int).to_numpy()
    out["hora_target"] = s["hora_target"].astype(int).to_numpy()
    out["mes_target"] = s["mes_target"].astype(int).to_numpy()
    return out
