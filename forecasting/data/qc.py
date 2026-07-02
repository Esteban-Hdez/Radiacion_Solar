"""
Control de calidad (Fase 1) del pipeline de pronóstico.

Dos responsabilidades:
1. `seleccionar_nodo_arranque`: elige AUTOMÁTICAMENTE el nodo single-node de
   arranque por calidad (tierra firme, completitud total, menor relleno satelital,
   cercano a Cd. Victoria para interpretar resultados).
2. `reporte_qc`: para un nodo, produce un reporte de calidad reproducible
   (estructura temporal, rangos físicos, relleno satelital, horas operativas,
   distribución del target kt, estadísticas por variable).

Uso:
    conda run -n rs python -m forecasting.data.qc
"""
from __future__ import annotations
import os
import numpy as np
import pandas as pd

from forecasting import config as C
from forecasting.data import loaders as L

# Cd. Victoria (referencia para elegir un nodo interpretable).
CD_VICTORIA = (23.74, -99.14)


# --------------------------------------------------------------------------- #
# Selección del nodo de arranque
# --------------------------------------------------------------------------- #
def seleccionar_nodo_arranque(anios: list[int] | None = None,
                              verbose: bool = True) -> dict:
    """Elige el nodo de arranque por calidad y devuelve un dict con el detalle.

    Criterio: (1) filas completas en TODOS los años; (2) fracción de relleno
    satelital por debajo de la mediana; (3) de esos, el más cercano a Cd. Victoria.
    """
    anios = anios or C.ANIOS_TODOS
    meta = L.cargar_metadata()

    # Métricas de calidad agregadas entre años.
    resumenes = []
    for anio in anios:
        r = L.resumen_calidad_nodos(anio).assign(anio=anio)
        resumenes.append(r)
        if verbose:
            print(f"  [{anio}] nodos={r['nodo_id'].nunique()} "
                  f"frac_fill medio={r['frac_fill'].mean():.3f}")
    todos = pd.concat(resumenes, ignore_index=True)

    horas_esperadas = {a: pd.date_range(f"{a}-01-01", f"{a}-12-31 23:00", freq="h").size
                       for a in anios}
    todos["completo"] = todos.apply(
        lambda x: x["n_filas"] >= horas_esperadas[x["anio"]], axis=1)

    agg = todos.groupby("nodo_id").agg(
        anios_presente=("anio", "nunique"),
        anios_completos=("completo", "sum"),
        frac_fill=("frac_fill", "mean"),
        frac_operativa=("frac_operativa", "mean")).reset_index()
    agg = agg.merge(meta[["nodo_id", "latitude", "longitude", "msnm"]], on="nodo_id")

    # (1) presente y completo en todos los años.
    cand = agg[(agg["anios_presente"] == len(anios)) &
               (agg["anios_completos"] == len(anios))].copy()
    # (2) relleno por debajo de la mediana (mejor calidad satelital).
    umbral = cand["frac_fill"].median()
    cand = cand[cand["frac_fill"] <= umbral].copy()
    # (3) cercanía a Cd. Victoria.
    cand["dist_victoria"] = np.hypot(cand["latitude"] - CD_VICTORIA[0],
                                     cand["longitude"] - CD_VICTORIA[1])
    elegido = cand.sort_values("dist_victoria").iloc[0]

    info = {
        "nodo_id": int(elegido["nodo_id"]),
        "latitude": float(elegido["latitude"]),
        "longitude": float(elegido["longitude"]),
        "msnm": float(elegido["msnm"]),
        "frac_fill": float(elegido["frac_fill"]),
        "frac_operativa": float(elegido["frac_operativa"]),
        "candidatos": int(len(cand)),
    }
    if verbose:
        print(f"\n>> Nodo de arranque: {info['nodo_id']} "
              f"(lat {info['latitude']:.2f}, lon {info['longitude']:.2f}, "
              f"{info['msnm']:.0f} msnm) | fill={info['frac_fill']:.3f} | "
              f"{info['candidatos']} candidatos de calidad")
    return info


# --------------------------------------------------------------------------- #
# Reporte de calidad de un nodo
# --------------------------------------------------------------------------- #
def reporte_qc(nodo_id: int, anios: list[int] | None = None) -> dict:
    """Reporte de calidad de la serie de un nodo. Devuelve un dict de métricas
    y lo imprime de forma legible."""
    anios = anios or C.ANIOS_TODOS
    df = L.cargar_nodo(nodo_id, anios)
    n = len(df)
    rep: dict = {"nodo_id": nodo_id, "anios": anios, "n_filas": n}

    print(f"\n{'='*66}\nQC nodo {nodo_id} | años {anios}\n{'='*66}")

    # 1. Estructura temporal.
    faltantes = int(df[C.COL_GHI].isna().sum())
    dt = df["datetime"]
    print(f"[1] Estructura: {n} horas ({dt.min()} -> {dt.max()}), UTC")
    print(f"    Timestamps faltantes (reindex): {faltantes} "
          f"({100*faltantes/n:.3f}%)  | duplicados: 0 (drop previo)")
    rep["faltantes"] = faltantes

    # 2. Rangos físicos.
    print("[2] Rangos físicos (valores fuera de rango plausible):")
    fuera = {}
    for col, (lo, hi) in C.RANGOS_FISICOS.items():
        if col not in df:
            continue
        m = pd.Series(False, index=df.index)
        if lo is not None:
            m |= df[col] < lo
        if hi is not None:
            m |= df[col] > hi
        c = int(m.sum())
        if c:
            fuera[col] = c
    print(f"    {fuera if fuera else 'sin valores imposibles'}")
    rep["fuera_rango"] = fuera

    # 3. Calidad satelital (fill_flag / cloud_fill_flag).
    if "fill_flag" in df:
        ff = df["fill_flag"].value_counts(dropna=True).sort_index()
        print("[3] fill_flag (relleno):",
              {int(k): int(v) for k, v in ff.items()})
        rep["fill_flag"] = {int(k): int(v) for k, v in ff.items()}

    # 4. Horas operativas.
    op = (df[C.COL_CLEARSKY] > C.CLEARSKY_MIN) & (df[C.COL_ZENITH] < C.ZENITH_MAX)
    n_op = int(op.sum())
    print(f"[4] Horas operativas (csghi>0 & zen<{C.ZENITH_MAX:.0f}): "
          f"{n_op} ({100*n_op/n:.1f}%)")
    rep["n_operativas"] = n_op

    # 5. Target kt (solo operativas).
    dop = df[op]
    kt = (dop[C.COL_GHI] / dop[C.COL_CLEARSKY]).clip(upper=C.KT_MAX)
    print(f"[5] kt operativas: n={len(kt)} nan={int(kt.isna().sum())} "
          f"| min={kt.min():.3f} p50={kt.median():.3f} max={kt.max():.3f}")
    kt_bruto = dop[C.COL_GHI] / dop[C.COL_CLEARSKY]
    print(f"    kt>1 antes de recorte: {int((kt_bruto > C.KT_MAX).sum())}")
    rep["kt"] = {"n": int(len(kt)), "p50": float(kt.median()),
                 "kt_mayor_1": int((kt_bruto > C.KT_MAX).sum())}

    # 6. Estadísticas y correlación con kt (informa selección de features).
    dop = dop.assign(kt=kt)
    numericas = [c for c in C.OBSERVADAS + C.DETERMINISTAS
                 if c in dop and dop[c].dtype.kind in "fiu"]
    corr = dop[numericas + ["kt"]].corr()["kt"].drop("kt").sort_values()
    print("[6] Correlación (operativas) de cada variable con kt "
          "[top +/- 5]:")
    print("    positivas:", {k: round(v, 2) for k, v in corr.tail(5).items()})
    print("    negativas:", {k: round(v, 2) for k, v in corr.head(5).items()})
    rep["corr_kt"] = {k: round(float(v), 3) for k, v in corr.items()}

    return rep


def tabla_fill_flag(anios: list[int] | None = None, nodo_id: int | None = None,
                    guardar: str | None = None) -> pd.DataFrame:
    """Frecuencia de cada valor de `fill_flag` + estadísticas de apoyo para
    investigar su significado.

    Por cada valor de fill_flag agrega, sobre todo el periodo (todos los nodos,
    o un `nodo_id` concreto): nº de observaciones, %, y medias de ghi, clearsky,
    kt, cloud_type, cloud_fill_flag y zenith. Si fill_flag es un % de relleno,
    debería verse una degradación monótona de kt/ghi al subir el valor.
    """
    anios = anios or C.ANIOS_TODOS
    cols = ["fill_flag", "ghi", "clearsky_ghi", "cloud_type",
            "cloud_fill_flag", "solar_zenith_angle"]
    if nodo_id is not None:
        cols = ["nodo_id"] + cols

    piezas = []
    for anio in anios:
        filtros = [("nodo_id", "==", nodo_id)] if nodo_id is not None else None
        d = pd.read_parquet(C.ruta_parquet(anio), columns=cols, filters=filtros)
        op = (d["clearsky_ghi"] > C.CLEARSKY_MIN) & (d["solar_zenith_angle"] < C.ZENITH_MAX)
        d["_kt_op"] = (d["ghi"] / d["clearsky_ghi"]).where(op).clip(upper=C.KT_MAX)
        d["_op"] = op.astype("int64")
        g = d.groupby("fill_flag").agg(
            n_obs=("ghi", "size"),
            n_operativas=("_op", "sum"),
            ghi_medio=("ghi", "mean"),
            clearsky_ghi_medio=("clearsky_ghi", "mean"),
            kt_medio_op=("_kt_op", "mean"),
            cloud_type_medio=("cloud_type", "mean"),
            cloud_fill_flag_medio=("cloud_fill_flag", "mean"),
            zenith_medio=("solar_zenith_angle", "mean"))
        # Reponderar medias por n_obs para poder acumular entre años.
        for c in ["ghi_medio", "clearsky_ghi_medio", "cloud_type_medio",
                  "cloud_fill_flag_medio", "zenith_medio"]:
            g[c] = g[c] * g["n_obs"]
        g["kt_medio_op"] = g["kt_medio_op"] * g["n_operativas"]
        piezas.append(g)

    t = pd.concat(piezas).groupby("fill_flag").sum()
    for c in ["ghi_medio", "clearsky_ghi_medio", "cloud_type_medio",
              "cloud_fill_flag_medio", "zenith_medio"]:
        t[c] = (t[c] / t["n_obs"]).round(2)
    t["kt_medio_op"] = (t["kt_medio_op"] / t["n_operativas"]).round(4)
    t["pct"] = (100 * t["n_obs"] / t["n_obs"].sum()).round(3)
    t = t.reset_index()
    t = t[["fill_flag", "n_obs", "pct", "n_operativas", "ghi_medio",
           "clearsky_ghi_medio", "kt_medio_op", "cloud_type_medio",
           "cloud_fill_flag_medio", "zenith_medio"]].sort_values("fill_flag")

    if guardar:
        t.to_csv(guardar, index=False)
        print(f"Tabla fill_flag guardada en: {guardar}  ({len(t)} valores)")
    return t


def main():
    print("Seleccionando nodo de arranque por calidad...")
    info = seleccionar_nodo_arranque()
    rep = reporte_qc(info["nodo_id"])
    # Persistir un CSV con la serie limpia del nodo para las siguientes fases.
    df = L.cargar_nodo(info["nodo_id"])
    salida = os.path.join(C.DIR_RESULTADOS, f"nodo_{info['nodo_id']}_serie.parquet")
    df.to_parquet(salida, index=False)
    print(f"\nSerie del nodo guardada en: {salida}")
    return info, rep


if __name__ == "__main__":
    main()
