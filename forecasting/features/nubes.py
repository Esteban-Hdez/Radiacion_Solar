"""
Bloque de NUBES con codificación correcta de `cloud_type` (categórica nominal).

`cloud_type` NO debe promediarse como código crudo (sus enteros no ordenan por
opacidad: p.ej. cirros=7 es fino y agua=3 es opaco). Dos tratamientos válidos:

- Target/opacity encoding: cada categoría → kt medio de ese tipo, calculado SOLO en
  train (anti-fuga) y aplicado igual a val/test (categoría no vista → media global).
  Da un score ordenado por opacidad. `cloud_op_lag1` (instantáneo) y
  `cloud_op_media_12h` (media trailing 12 h).
- Fracción de horas nubladas `frac_nublado_12h`: proporción de horas con nube en las
  últimas 12 h. Mide FRECUENCIA (complementa a la opacidad).

El encoding es ESTADO ajustado en train (no una función pura); se ajusta una vez
(global entre nodos en multi-nodo) y se pasa al construir features. Se guarda como
artefacto del experimento para reproducibilidad.
"""
from __future__ import annotations
import pandas as pd

from forecasting import config as C
from forecasting import target as T

_GLOBAL = "_global_"


def ajustar_opacidad(df: pd.DataFrame) -> dict:
    """Encoding {cloud_type: kt medio en train operativas} (+ media global) para una
    serie single-node (índice datetime con columna cloud_type)."""
    kt = T.calcular_kt(df)
    op = T.mascara_operativa(df)
    m = df.index.year.isin(C.ANIOS_TRAIN) & op & kt.notna()
    tab = kt[m].groupby(df["cloud_type"][m]).mean()
    d = {int(k): float(v) for k, v in tab.items()}
    d[_GLOBAL] = float(kt[m].mean())
    return d


def ajustar_opacidad_largo(df_bloque: pd.DataFrame) -> dict:
    """Igual pero GLOBAL sobre el bloque multi-nodo (formato largo de cargar_bloque:
    columnas datetime, cloud_type, ghi, clearsky_ghi, solar_zenith_angle)."""
    cs = df_bloque["clearsky_ghi"]
    kt = (df_bloque["ghi"] / cs.where(cs > 0)).clip(0, C.KT_MAX)
    op = (cs > C.CLEARSKY_MIN) & (df_bloque["solar_zenith_angle"] < C.ZENITH_MAX)
    anio = pd.to_datetime(df_bloque["datetime"]).dt.year
    m = anio.isin(C.ANIOS_TRAIN) & op & kt.notna()
    tab = kt[m].groupby(df_bloque["cloud_type"][m]).mean()
    d = {int(k): float(v) for k, v in tab.items()}
    d[_GLOBAL] = float(kt[m].mean())
    return d


def bloque_nubes(df: pd.DataFrame, opacidad: dict) -> pd.DataFrame:
    """Features de nubes con el encoding `opacidad` ya ajustado (en train)."""
    g = opacidad[_GLOBAL]
    mapa = {int(k): v for k, v in opacidad.items() if k != _GLOBAL}
    ct = df["cloud_type"]

    # Opacidad instantánea: código -> kt medio del tipo (no visto -> global).
    score = ct.map(mapa)
    score = score.mask(ct.notna() & score.isna(), g)

    # Fracción nublada (código > 0 = con nube); NaN donde no hay dato.
    nublado = (ct > 0).astype("float").where(ct.notna())

    out = pd.DataFrame(index=df.index)
    out["cloud_op_lag1"] = score.shift(1)
    out["cloud_op_media_12h"] = score.shift(1).rolling(12, min_periods=6).mean()
    out["frac_nublado_12h"] = nublado.shift(1).rolling(12, min_periods=6).mean()
    return out
