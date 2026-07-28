"""
Carga de datos para el pronóstico. Dos rutas:

- `cargar_nodo(nodo_id, anios, columnas)`: serie horaria de UN nodo a lo largo de
  varios años, con índice temporal contiguo (reindexado a horas UTC), listo para
  construir features/lags sin saltos.
- `resumen_calidad_nodos(anio, ...)`: agrega por nodo métricas baratas (completitud
  y fracción de relleno satelital) para poder ELEGIR el nodo de arranque por calidad
  sin cargar el año entero en memoria de golpe.

Todo respeta lo definido en `forecasting.config`.
"""
from __future__ import annotations
import os
import numpy as np
import pandas as pd
import pyarrow.parquet as pq

from forecasting import config as C


def cargar_serie_nodo(nodo_id: int = 1736, ruta: str | None = None) -> pd.DataFrame:
    """Serie horaria contigua de un nodo desde el parquet YA generado y committeado.

    A diferencia de `cargar_nodo` (que lee los grandes `Data/*.parquet`, no presentes
    en la laptop), esto lee `Results/<REGION>/forecast/nodo_<id>_serie.parquet`, con
    índice `datetime` y malla horaria completa (huecos expuestos como NaN). Es la
    entrada de la Fase 2 en adelante para el trabajo single-node.
    """
    ruta = ruta or os.path.join(C.DIR_RESULTADOS, f"nodo_{nodo_id}_serie.parquet")
    df = pd.read_parquet(ruta)
    df["datetime"] = pd.to_datetime(df["datetime"])
    df = df.drop_duplicates("datetime").sort_values("datetime").set_index("datetime")

    # Índice horario contiguo: expone timestamps faltantes como NaN (no los oculta).
    idx = pd.date_range(df.index.min(), df.index.max(), freq="h")
    df = df.reindex(idx)
    df.index.name = "datetime"
    df["nodo_id"] = nodo_id
    return df


def cargar_bloque(nodos: list[int], anios: list[int] | None = None) -> pd.DataFrame:
    """Carga un BLOQUE de nodos (multi-nodo) desde los grandes `Data/*.parquet`.

    Lee cada año una sola vez con filtro `nodo_id in nodos` (empuje a nivel de
    row-group, eficiente). Devuelve un DataFrame largo con columna `datetime` y
    `nodo_id`; las estáticas (lat/lon/msnm) se aseguran desde la metadata. NO
    reindexa aquí: la malla horaria contigua por nodo se arma al construir features.
    """
    anios = anios or C.ANIOS_TODOS
    partes = []
    for anio in anios:
        df = pd.read_parquet(C.ruta_parquet(anio),
                             filters=[("nodo_id", "in", list(nodos))])
        partes.append(df)
    df = pd.concat(partes, ignore_index=True)
    df["datetime"] = pd.to_datetime(df["datetime"])
    df = df.drop_duplicates(["nodo_id", "datetime"])

    faltan = [c for c in C.ESTATICAS if c not in df.columns]
    if faltan:
        meta = cargar_metadata(list(nodos))[["nodo_id", *C.ESTATICAS]]
        df = df.merge(meta, on="nodo_id", how="left")
    return df


def serie_contigua_nodo(df_nodo: pd.DataFrame) -> pd.DataFrame:
    """Reindexa las filas de UN nodo a una malla horaria contigua (índice datetime),
    exponiendo huecos como NaN. Usado por el ensamblado multi-nodo de features."""
    d = df_nodo.drop_duplicates("datetime").sort_values("datetime").set_index("datetime")
    idx = pd.date_range(d.index.min(), d.index.max(), freq="h")
    d = d.reindex(idx)
    d.index.name = "datetime"
    d["nodo_id"] = df_nodo["nodo_id"].iloc[0]
    return d


def nodos_cercanos(pivote: int, n: int) -> tuple[int, ...]:
    """Los `n` nodos más cercanos al `pivote` (distancia euclídea en lat/lon), como
    tupla ordenada de ids. Determinista dada la metadata; define bloques compactos
    (p.ej. n=144 ≈ malla 12×12 alrededor del nodo pivote)."""
    meta = cargar_metadata()
    c = meta.loc[meta["nodo_id"] == pivote].iloc[0]
    d = np.hypot(meta["latitude"] - c["latitude"], meta["longitude"] - c["longitude"])
    ids = meta.loc[d.nsmallest(n).index, "nodo_id"].astype(int)
    return tuple(sorted(ids))


def cargar_metadata(nodos: list[int] | None = None) -> pd.DataFrame:
    meta = pd.read_csv(C.META_NODOS)
    if nodos is not None:
        meta = meta[meta["nodo_id"].isin(nodos)].copy()
    return meta.reset_index(drop=True)


def cargar_nodo(nodo_id: int, anios: list[int] | None = None,
                columnas: list[str] | None = None) -> pd.DataFrame:
    """Serie horaria contigua de un nodo a lo largo de `anios`.

    Reindexa a un rango horario completo por año para exponer huecos (filas NaN)
    en vez de ocultarlos. Añade las estáticas del nodo (lat/lon/msnm).
    """
    anios = anios or C.ANIOS_TODOS
    if columnas is not None:
        columnas = list(dict.fromkeys(["nodo_id", "datetime", *columnas]))

    partes = []
    for anio in anios:
        df = pd.read_parquet(C.ruta_parquet(anio), columns=columnas,
                             filters=[("nodo_id", "==", nodo_id)])
        partes.append(df)
    df = pd.concat(partes, ignore_index=True)
    df["datetime"] = pd.to_datetime(df["datetime"])
    df = df.drop_duplicates("datetime").sort_values("datetime")

    # Índice horario contiguo (expone timestamps faltantes como NaN).
    idx = pd.date_range(df["datetime"].min(), df["datetime"].max(), freq="h")
    df = df.set_index("datetime").reindex(idx)
    df.index.name = "datetime"
    df["nodo_id"] = nodo_id

    # Estáticas del nodo.
    meta = cargar_metadata([nodo_id])
    if not meta.empty:
        for col in C.ESTATICAS:
            if col in meta.columns:
                df[col] = meta.iloc[0][col]
    return df.reset_index()


def resumen_calidad_nodos(anio: int, chunk_rows: int = 4_000_000) -> pd.DataFrame:
    """Métricas de calidad por nodo para un año, leyendo por lotes (bajo consumo).

    Devuelve por nodo: n_filas, n_horas_operativas, frac_fill (fracción de horas
    con fill_flag>0) y frac_op (proporción operativa). Sirve para rankear nodos.
    """
    cols = ["nodo_id", C.COL_CLEARSKY, C.COL_ZENITH, "fill_flag"]
    pf = pq.ParquetFile(C.ruta_parquet(anio))
    acum: dict[int, list[int]] = {}   # nodo -> [n, n_op, n_fill]
    for batch in pf.iter_batches(batch_size=chunk_rows, columns=cols):
        d = batch.to_pandas()
        op = (d[C.COL_CLEARSKY] > C.CLEARSKY_MIN) & (d[C.COL_ZENITH] < C.ZENITH_MAX)
        d = d.assign(_op=op.astype("int32"),
                     _fill=(d["fill_flag"] > 0).astype("int32"),
                     _n=1)
        g = d.groupby("nodo_id")[["_n", "_op", "_fill"]].sum()
        for nodo, row in g.iterrows():
            a = acum.setdefault(int(nodo), [0, 0, 0])
            a[0] += int(row["_n"]); a[1] += int(row["_op"]); a[2] += int(row["_fill"])

    res = pd.DataFrame(
        [(k, v[0], v[1], v[2]) for k, v in acum.items()],
        columns=["nodo_id", "n_filas", "n_operativas", "n_fill"])
    res["frac_fill"] = res["n_fill"] / res["n_filas"]
    res["frac_operativa"] = res["n_operativas"] / res["n_filas"]
    return res.sort_values("nodo_id").reset_index(drop=True)
