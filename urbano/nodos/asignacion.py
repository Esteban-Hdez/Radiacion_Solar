"""
Asignación de nodos NSRDB a manchas urbanas.

El problema es de ESCALA: la celda del nodo (~18 km²) suele ser más grande que
la ciudad que quiere representar. Por eso la asignación es una cascada de tres
métodos, y cada fila declara con cuál se resolvió para que nunca se comparen
métricas de distinta confiabilidad como si fueran equivalentes:

  1. "dentro"   — el centro del nodo cae dentro de la mancha urbana. Es el caso
                  ideal y solo ocurre en las ciudades grandes.
  2. "celda"    — la celda de 0.04°×0.04° del nodo intersecta la mancha. Método
                  principal: da un `peso` = fracción del área urbana que cae en
                  esa celda, con el que se promedian métricas por ciudad.
  3. "cercano"  — la mancha no intersecta ninguna celda (borde del dominio, o
                  ciudad costera fuera de la malla): se toma el nodo más cercano
                  al centroide. `calidad = "baja"`.

Los pesos de cada ciudad suman 1, así que una métrica por ciudad es
`sum(peso_i * metrica_nodo_i)`: para Reynosa promedia ~12 nodos ponderados por
cuánta ciudad cubre cada uno; para San Nicolás es literalmente el nodo que la
contiene, y la bandera de calidad lo dice.
"""
from __future__ import annotations
import os

import geopandas as gpd
import numpy as np
import pandas as pd
from shapely.geometry import box

from urbano import config as C
from urbano.data import manchas as M


# --------------------------------------------------------------------------- #
# Malla
# --------------------------------------------------------------------------- #
def cargar_nodos() -> gpd.GeoDataFrame:
    """Nodos NSRDB como puntos, en CRS métrico, con lat/lon originales."""
    meta = pd.read_csv(C.META_NODOS)
    g = gpd.GeoDataFrame(
        meta, geometry=gpd.points_from_xy(meta["longitude"], meta["latitude"]),
        crs=C.CRS_GEO).to_crs(C.CRS_METRICO)
    if os.path.exists(C.RUTA_REGIONES):
        g = g.merge(pd.read_csv(C.RUTA_REGIONES), on="nodo_id", how="left")
    return g


def celdas_nodos(nodos: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    """
    Celda cuadrada de PASO_MALLA grados centrada en cada nodo.

    Se construye en coordenadas geográficas —que es como está definida la malla
    NSRDB— y se reproyecta a metros; construirla directamente en metros daría
    cuadrados que no coinciden con la malla real.
    """
    h = C.PASO_MALLA / 2
    geo = nodos.to_crs(C.CRS_GEO)
    cajas = [box(lon - h, lat - h, lon + h, lat + h)
             for lon, lat in zip(geo.geometry.x, geo.geometry.y)]
    celdas = gpd.GeoDataFrame(
        nodos.drop(columns="geometry"), geometry=cajas, crs=C.CRS_GEO)
    return celdas.to_crs(C.CRS_METRICO)


# --------------------------------------------------------------------------- #
# Asignación
# --------------------------------------------------------------------------- #
def asignar(urb: gpd.GeoDataFrame | None = None,
            nodos: gpd.GeoDataFrame | None = None) -> pd.DataFrame:
    """
    Tabla larga nodo↔ciudad. Un nodo puede aparecer en varias ciudades (una
    celda de 18 km² puede tocar dos manchas vecinas) y una ciudad tiene siempre
    al menos una fila.
    """
    urb = M.manchas_urbanas() if urb is None else urb
    nodos = cargar_nodos() if nodos is None else nodos
    celdas = celdas_nodos(nodos)

    # --- métodos 1 y 2: intersección celda ↔ mancha -------------------------
    pares = gpd.overlay(
        celdas[["nodo_id", "geometry"]],
        urb[["cvegeo", "ciudad", "municipio", "es_cabecera", "cve_mun",
             "conglomerado", "nombre_conglomerado", "area_km2", "geometry"]],
        how="intersection", keep_geom_type=True)
    pares["area_urbana_celda_km2"] = pares.geometry.area / 1e6
    # Los slivers de borde (< 1 m² por redondeo topológico) no son cobertura real.
    pares = pares[pares["area_urbana_celda_km2"] > 1e-6].copy()

    puntos = nodos[["nodo_id", "geometry"]]
    dentro = gpd.sjoin(puntos, urb[["cvegeo", "geometry"]],
                       how="inner", predicate="within")
    llaves_dentro = set(zip(dentro["nodo_id"], dentro["cvegeo"]))
    pares["metodo"] = np.where(
        [k in llaves_dentro for k in zip(pares["nodo_id"], pares["cvegeo"])],
        "dentro", "celda")

    # --- método 3: fallback para ciudades sin ninguna intersección ----------
    huerfanas = urb[~urb["cvegeo"].isin(pares["cvegeo"])]
    if len(huerfanas):
        cen = gpd.GeoDataFrame(
            huerfanas.drop(columns="geometry"),
            geometry=huerfanas.geometry.centroid, crs=urb.crs)
        cercano = gpd.sjoin_nearest(
            cen, puntos, how="left", distance_col="dist_m")
        cercano["metodo"] = "cercano"
        cercano["area_urbana_celda_km2"] = cercano["area_km2"]
        pares = pd.concat(
            [pares.drop(columns="geometry"),
             cercano[pares.columns.drop("geometry")].assign(
                 metodo="cercano")], ignore_index=True)
    else:
        pares = pares.drop(columns="geometry")

    # --- peso: fracción del área urbana de la ciudad que cae en esa celda ---
    total = pares.groupby("cvegeo")["area_urbana_celda_km2"].transform("sum")
    pares["peso"] = pares["area_urbana_celda_km2"] / total

    # --- distancia nodo↔centroide de la ciudad (contexto para el fallback) --
    cen_ciudad = dict(zip(urb["cvegeo"], urb.geometry.centroid))
    pt_nodo = dict(zip(nodos["nodo_id"], nodos.geometry))
    pares["dist_centro_km"] = [
        pt_nodo[n].distance(cen_ciudad[c]) / 1000
        for n, c in zip(pares["nodo_id"], pares["cvegeo"])]

    # --- calidad: cuántos nodos tienen su CENTRO dentro de la mancha --------
    n_dentro = (pares[pares["metodo"] == "dentro"].groupby("cvegeo")["nodo_id"]
                .nunique().reindex(urb["cvegeo"]).fillna(0).astype(int))
    def _calidad(cve: str) -> str:
        k = int(n_dentro.get(cve, 0))
        if k >= C.MIN_NODOS_ALTA:
            return "alta"
        if k >= C.MIN_NODOS_MEDIA:
            return "media"
        return "baja"
    pares["n_nodos_dentro"] = pares["cvegeo"].map(n_dentro).astype(int)
    pares["calidad"] = pares["cvegeo"].map(_calidad)
    pares["n_nodos_ciudad"] = pares.groupby("cvegeo")["nodo_id"].transform("nunique")

    if "region" in nodos.columns:
        pares = pares.merge(nodos[["nodo_id", "region"]], on="nodo_id", how="left")

    cols = ["nodo_id", "cvegeo", "ciudad", "municipio", "cve_mun", "es_cabecera",
            "conglomerado", "nombre_conglomerado", "metodo", "peso",
            "area_urbana_celda_km2", "dist_centro_km", "n_nodos_dentro",
            "n_nodos_ciudad", "calidad"]
    if "region" in pares.columns:
        cols.append("region")
    return (pares[cols].sort_values(["ciudad", "peso"], ascending=[True, False])
            .reset_index(drop=True))


def resumen(pares: pd.DataFrame, urb: gpd.GeoDataFrame) -> pd.DataFrame:
    """Una fila por ciudad: cuántos nodos la representan y con qué confianza."""
    g = pares.groupby("cvegeo")
    res = pd.DataFrame({
        "n_nodos": g["nodo_id"].nunique(),
        "n_nodos_dentro": g["n_nodos_dentro"].first(),
        "metodo": g["metodo"].agg(lambda s: "cercano" if (s == "cercano").all()
                                  else ("dentro" if (s == "dentro").any() else "celda")),
        "peso_max": g["peso"].max(),
        "calidad": g["calidad"].first(),
    }).reset_index()
    res = urb.drop(columns="geometry").merge(res, on="cvegeo", how="left")
    return res.sort_values("area_km2", ascending=False).reset_index(drop=True)


if __name__ == "__main__":
    urb = M.manchas_urbanas()
    pares = asignar(urb)
    res = resumen(pares, urb)
    print(f"{len(pares)} pares nodo↔ciudad · {pares['nodo_id'].nunique()} nodos "
          f"distintos · {res['cvegeo'].nunique()} ciudades")
    print("\nmétodo:", pares["metodo"].value_counts().to_dict())
    print("calidad (por ciudad):", res["calidad"].value_counts().to_dict())
    print("\nsuma de pesos por ciudad — min/max:",
          round(pares.groupby("cvegeo")["peso"].sum().min(), 6),
          round(pares.groupby("cvegeo")["peso"].sum().max(), 6))
    print("\n", res[["ciudad", "municipio", "area_km2", "n_nodos",
                     "n_nodos_dentro", "peso_max", "calidad"]].head(15).to_string(index=False))
    print("\n--- ciudades peor representadas ---")
    print(res[["ciudad", "municipio", "area_km2", "n_nodos", "peso_max", "calidad"]]
          .tail(10).to_string(index=False))
