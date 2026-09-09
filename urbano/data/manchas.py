"""
Manchas urbanas de Tamaulipas a partir del Marco Geoestadístico del INEGI.

Qué es exactamente "la mancha urbana" aquí: la capa `28l` del MG son las
LOCALIDADES AMANZANADAS (polígonos trazados sobre manzanas reales, no buffers ni
círculos). Nos quedamos con las de `AMBITO == "Urbana"` —63 en Tamaulipas, entre
ellas las 43 cabeceras municipales—, que es justo el área construida y no el
municipio entero.

Además de cada localidad por separado se calcula su CONGLOMERADO: manchas cuyos
bordes distan menos de `GAP_CONGLOMERADO_M` se agrupan (Tampico + Cd. Madero +
Altamira + Miramar son una sola mancha continua). Así las métricas pueden
reportarse por localidad o por conglomerado sin rehacer nada.
"""
from __future__ import annotations
import os

import geopandas as gpd
import numpy as np
import pandas as pd

from urbano import config as C
from urbano.data import cabeceras as CAB
from urbano.data.descarga_mgn import asegurar


def _leer(sufijo: str) -> gpd.GeoDataFrame:
    """Lee una capa del MG y la deja en el CRS métrico del proyecto."""
    ruta = C.capa(sufijo)
    if not os.path.exists(ruta):
        asegurar()
    return gpd.read_file(ruta).to_crs(C.CRS_METRICO)


def municipios() -> gpd.GeoDataFrame:
    """Los 43 municipios de Tamaulipas (`28mun`)."""
    m = _leer(C.CAPA_MUNICIPIOS)
    return m.rename(columns={"NOMGEO": "municipio"})[
        ["CVE_MUN", "municipio", "geometry"]]


def _conglomerados(g: gpd.GeoDataFrame) -> pd.Series:
    """
    Agrupa manchas separadas por < GAP_CONGLOMERADO_M.

    Se infla cada polígono la mitad del hueco tolerado, se unen los que se tocan
    y se etiqueta cada mancha con el grupo resultante. Es la misma idea de un
    clustering de enlace simple, pero hecho con geometría (sin dependencias extra).
    """
    inflados = g.geometry.buffer(C.GAP_CONGLOMERADO_M / 2)
    grupos = gpd.GeoDataFrame(geometry=[inflados.union_all()], crs=g.crs).explode(
        index_parts=False).reset_index(drop=True)
    grupos["grupo"] = grupos.index
    unido = gpd.sjoin(
        gpd.GeoDataFrame(geometry=inflados, crs=g.crs),
        grupos[["grupo", "geometry"]], how="left", predicate="within")
    # `within` puede fallar por redondeo en un borde compartido; el respaldo es
    # quedarse con el grupo que más intersecta.
    if unido["grupo"].isna().any():
        faltan = unido["grupo"].isna()
        aux = gpd.sjoin(gpd.GeoDataFrame(geometry=inflados[faltan], crs=g.crs),
                        grupos[["grupo", "geometry"]], how="left",
                        predicate="intersects").groupby(level=0)["grupo"].first()
        unido.loc[faltan, "grupo"] = aux
    return unido["grupo"].astype(int).to_numpy()


def manchas_urbanas() -> gpd.GeoDataFrame:
    """
    Las 63 localidades urbanas del estado, enriquecidas.

    Columnas: cvegeo, ciudad, cve_mun, cve_loc, municipio, es_cabecera,
    area_km2, lat/lon del centroide, conglomerado (id) y nombre_conglomerado
    (el de la localidad más grande del grupo).
    """
    loc = _leer(C.CAPA_LOCALIDADES)
    urb = loc[loc["AMBITO"] == "Urbana"].copy().reset_index(drop=True)
    urb = urb.rename(columns={"CVEGEO": "cvegeo", "NOMGEO": "ciudad",
                              "CVE_MUN": "cve_mun", "CVE_LOC": "cve_loc"})
    urb = urb.merge(municipios().drop(columns="geometry"),
                    left_on="cve_mun", right_on="CVE_MUN", how="left")

    # La cabecera se toma del catálogo oficial del INEGI, NO de la convención
    # "la localidad 0001 es la cabecera": en Tamaulipas esa convención falla en
    # Gómez Farías (011), cuya 0001 es Loma Alta y cuya cabecera es la 0036.
    # Ver `urbano/data/cabeceras.py`.
    cab = CAB.mapa_cabeceras()
    urb["es_cabecera"] = urb["cve_loc"] == urb["cve_mun"].map(cab)
    urb["area_km2"] = urb.geometry.area / 1e6

    cen = urb.geometry.centroid.to_crs(C.CRS_GEO)
    urb["lon_centro"] = cen.x.to_numpy()
    urb["lat_centro"] = cen.y.to_numpy()

    urb["conglomerado"] = _conglomerados(urb)
    mayor = urb.loc[urb.groupby("conglomerado")["area_km2"].idxmax()]
    urb["nombre_conglomerado"] = urb["conglomerado"].map(
        dict(zip(mayor["conglomerado"], mayor["ciudad"])))

    cols = ["cvegeo", "ciudad", "municipio", "cve_mun", "cve_loc", "es_cabecera",
            "area_km2", "lat_centro", "lon_centro",
            "conglomerado", "nombre_conglomerado", "geometry"]
    return urb[cols].sort_values("area_km2", ascending=False).reset_index(drop=True)


def cabeceras_sin_mancha(urb: gpd.GeoDataFrame) -> pd.DataFrame:
    """
    Cabeceras municipales que NO aparecen como localidad urbana amanzanada.

    En el MG 2025 de Tamaulipas la lista sale vacía (las 43 cabeceras son
    urbanas), pero se calcula igual para que el pipeline avise si una edición
    futura reclasifica alguna a rural, o si el catálogo de cabeceras cambia.
    """
    todos = set(municipios()["CVE_MUN"])
    con_cabecera = set(urb.loc[urb["es_cabecera"], "cve_mun"])
    faltantes = sorted(todos - con_cabecera)
    if not faltantes:
        return pd.DataFrame(columns=["cve_mun", "municipio"])
    mun = municipios().drop(columns="geometry")
    return mun[mun["CVE_MUN"].isin(faltantes)].rename(columns={"CVE_MUN": "cve_mun"})


if __name__ == "__main__":
    u = manchas_urbanas()
    print(f"{len(u)} localidades urbanas · {u['es_cabecera'].sum()} cabeceras · "
          f"{u['area_km2'].sum():.1f} km² totales")
    print(u.drop(columns="geometry").head(12).to_string(index=False))
    print("\nConglomerados con más de una localidad:")
    multi = u.groupby("nombre_conglomerado")["ciudad"].agg(list)
    for nombre, miembros in multi.items():
        if len(miembros) > 1:
            print(f"  {nombre}: {', '.join(miembros)}")
    print("\nCabeceras sin mancha urbana:", len(cabeceras_sin_mancha(u)))
