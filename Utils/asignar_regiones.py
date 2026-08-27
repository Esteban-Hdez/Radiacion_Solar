"""
Asigna cada nodo NSRDB de Tamaulipas a una de las 6 REGIONES oficiales del estado.

Genera `Data/Tamaulipas/regiones_tamaulipas.csv` (nodo_id, region), que es la
entrada de `forecasting.data.regiones`. Solo hay que volver a correrlo si cambia
la malla de nodos; el CSV resultante SÍ se versiona.

Fuente de la regionalización: Gobierno del Estado de Tamaulipas (Secretaría de
Recursos Hidráulicos / CEAT) — 43 municipios en 6 regiones.
Fuente de los polígonos: OpenStreetMap, relaciones `admin_level=6` con la etiqueta
`INEGI:MUNID` (origen declarado: INEGI, Marco Geoestadístico Nacional 2014 v6.2).
Se filtra por el prefijo `28` del MUNID —el código INEGI de Tamaulipas— porque
varios nombres (Victoria, Bustamante, Aldama, Camargo, Jiménez…) se repiten en
estados vecinos y filtrar por nombre daría falsos positivos.

Uso:
    conda run -n rs python Utils/asignar_regiones.py
"""
from __future__ import annotations
import json
import os
import subprocess
import warnings

import geopandas as gpd
import pandas as pd
from shapely.geometry import LineString, Point
from shapely.ops import linemerge, polygonize, unary_union

warnings.filterwarnings("ignore")

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
META = os.path.join(RAIZ, "Data", "Tamaulipas", "metadata_nodos_tamaulipas.csv")
SALIDA = os.path.join(RAIZ, "Data", "Tamaulipas", "regiones_tamaulipas.csv")
CACHE_OSM = os.path.join(RAIZ, "cache", "municipios_tamaulipas.json")

# Los 43 municipios por región. Los nombres son los de OSM (que sigue a INEGI):
# "El Mante" por Mante, "Casas" por Villa de Casas, "Ciudad Madero" por Madero.
REGIONES: dict[str, list[str]] = {
    "Fronteriza": ["Nuevo Laredo", "Guerrero", "Mier", "Miguel Alemán", "Camargo",
                   "Gustavo Díaz Ordaz", "Reynosa", "Río Bravo", "Valle Hermoso",
                   "Matamoros"],
    "Valle de San Fernando": ["Méndez", "Burgos", "Cruillas", "San Fernando"],
    "Centro": ["Abasolo", "Güémez", "Hidalgo", "Jiménez", "Llera", "Mainero",
               "Padilla", "San Carlos", "San Nicolás", "Soto la Marina", "Victoria",
               "Casas", "Villagrán"],
    "Altiplano": ["Jaumave", "Miquihuana", "Palmillas", "Bustamante", "Tula"],
    "Mante": ["Nuevo Morelos", "Antiguo Morelos", "El Mante", "Xicoténcatl",
              "Ocampo", "Gómez Farías"],
    "Sur": ["González", "Aldama", "Altamira", "Tampico", "Ciudad Madero"],
}

CONSULTA_OSM = """
[out:json][timeout:600];
rel["boundary"="administrative"]["admin_level"="6"](22.0,-100.3,27.8,-97.0);
out geom;
"""


def descargar_municipios(ruta_cache: str = CACHE_OSM) -> dict:
    """Relaciones admin_level=6 del bbox de Tamaulipas (cacheadas en disco)."""
    if os.path.exists(ruta_cache):
        with open(ruta_cache) as f:
            return json.load(f)
    os.makedirs(os.path.dirname(ruta_cache), exist_ok=True)
    subprocess.run(["curl", "-sS", "--max-time", "900", "-X", "POST",
                    "-d", CONSULTA_OSM, "https://overpass-api.de/api/interpreter",
                    "-o", ruta_cache], check=True)
    with open(ruta_cache) as f:
        return json.load(f)


def poligonos_municipios(datos: dict) -> gpd.GeoDataFrame:
    """Ensambla los polígonos de los 43 municipios de Tamaulipas (MUNID 28xxx)."""
    a_region = {m: r for r, ms in REGIONES.items() for m in ms}
    filas = []
    for e in datos["elements"]:
        if not str(e.get("tags", {}).get("INEGI:MUNID", "")).startswith("28"):
            continue
        anillos = [LineString([(p["lon"], p["lat"]) for p in mb["geometry"]])
                   for mb in e.get("members", [])
                   if mb.get("role") in ("outer", "") and len(mb.get("geometry") or []) > 1]
        polis = list(polygonize(linemerge(anillos))) if anillos else []
        if polis:
            filas.append({"name": e["tags"]["name"], "geometry": unary_union(polis)})
    g = gpd.GeoDataFrame(filas, crs="EPSG:4326")
    g["region"] = g["name"].map(a_region)
    faltan = sorted(set(a_region) - set(g["name"]))
    if faltan:
        raise RuntimeError(f"Municipios no encontrados en OSM: {faltan}")
    sin = sorted(g.loc[g.region.isna(), "name"])
    if sin:
        raise RuntimeError(f"Municipios sin región asignada: {sin}")
    return g


def asignar(meta: pd.DataFrame, municipios: gpd.GeoDataFrame) -> pd.DataFrame:
    """Cada nodo -> su región. Los nodos que caen fuera de los polígonos (costa,
    imprecisión del borde) van a la región más cercana, no se descartan."""
    puntos = gpd.GeoDataFrame(
        meta, geometry=[Point(xy) for xy in zip(meta.longitude, meta.latitude)],
        crs="EPSG:4326")
    regiones = municipios.dissolve("region").reset_index()[["region", "geometry"]]
    j = gpd.sjoin(puntos, regiones, how="left", predicate="within")
    fuera = j.region.isna()
    if fuera.any():
        j.loc[fuera, "region"] = gpd.sjoin_nearest(
            puntos[fuera.values], regiones, how="left").region.values
    return (j.drop_duplicates("nodo_id")[["nodo_id", "region"]]
             .sort_values("nodo_id").reset_index(drop=True))


def main() -> None:
    meta = pd.read_csv(META)
    tabla = asignar(meta, poligonos_municipios(descargar_municipios()))
    assert len(tabla) == len(meta), f"{len(tabla)} filas para {len(meta)} nodos"
    tabla.to_csv(SALIDA, index=False)
    print(f"{len(tabla)} nodos asignados -> {SALIDA}")
    print(tabla.region.value_counts().to_string())


if __name__ == "__main__":
    main()
