"""
Mapa interactivo (HTML, folium) de manchas urbanas y nodos.

Complementa a los PNG: aquí sí se puede hacer zoom hasta la manzana y consultar
nodo por nodo. Tres capas conmutables —manchas, nodos asignados, nodos sin
ciudad— porque dibujar los 4384 nodos siempre encima haría el mapa inservible.

Se abre solo (archivo local, sin servidor). El fondo es OpenStreetMap, así que
necesita red para verse; los PNG de `estaticos.py` no.
"""
from __future__ import annotations
import os

import folium
import pandas as pd
from folium.plugins import MarkerCluster

from urbano import config as C
from urbano.data import manchas as M
from urbano.mapas import estilo as E
from urbano.nodos import asignacion as A


def construir(urb, nodos, pares, res, ruta: str) -> str:
    urb_geo = urb.to_crs(C.CRS_GEO)
    nodos_geo = nodos.to_crs(C.CRS_GEO)

    m = folium.Map(location=[24.3, -98.6], zoom_start=7, tiles="OpenStreetMap",
                   control_scale=True)

    # --- manchas urbanas -----------------------------------------------------
    capa_u = folium.FeatureGroup(name=f"Manchas urbanas ({len(urb_geo)})", show=True)
    info = res.set_index("cvegeo")
    for _, r in urb_geo.iterrows():
        d = info.loc[r["cvegeo"]]
        folium.GeoJson(
            r.geometry,
            style_function=lambda _f: {"fillColor": E.MANCHA, "color": E.MANCHA_BORDE,
                                       "weight": 1, "fillOpacity": 0.55},
            tooltip=folium.Tooltip(
                f"<b>{r['ciudad']}</b><br>{r['municipio']}<br>"
                f"{r['area_km2']:.2f} km²<br>"
                f"{'cabecera municipal' if r['es_cabecera'] else 'localidad urbana'}<br>"
                f"nodos: {int(d['n_nodos'])} (dentro: {int(d['n_nodos_dentro'])})<br>"
                f"cobertura: <b>{d['calidad']}</b><br>"
                f"conglomerado: {r['nombre_conglomerado']}"),
        ).add_to(capa_u)
    capa_u.add_to(m)

    # --- nodos asignados -----------------------------------------------------
    por_nodo = (pares.sort_values("peso", ascending=False)
                .groupby("nodo_id")
                .agg(ciudades=("ciudad", lambda s: ", ".join(s)),
                     peso_max=("peso", "max"),
                     calidad=("calidad", "first")))
    capa_n = folium.FeatureGroup(
        name=f"Nodos asignados ({len(por_nodo)})", show=True)
    for _, r in nodos_geo[nodos_geo["nodo_id"].isin(por_nodo.index)].iterrows():
        d = por_nodo.loc[r["nodo_id"]]
        folium.CircleMarker(
            [r["latitude"], r["longitude"]], radius=4,
            color="white", weight=1, fill=True,
            fill_color=E.CALIDAD[d["calidad"]], fill_opacity=1.0,
            tooltip=(f"<b>nodo {r['nodo_id']}</b><br>"
                     f"{r['latitude']:.2f}, {r['longitude']:.2f} · "
                     f"{r['msnm']:.0f} msnm<br>"
                     f"ciudad(es): {d['ciudades']}<br>"
                     f"peso máx: {d['peso_max']:.3f}"),
        ).add_to(capa_n)
    capa_n.add_to(m)

    # --- resto de la malla (agrupada; 4159 marcadores sueltos matan al navegador)
    capa_r = folium.FeatureGroup(name="Resto de la malla", show=False)
    cluster = MarkerCluster().add_to(capa_r)
    for _, r in nodos_geo[~nodos_geo["nodo_id"].isin(por_nodo.index)].iterrows():
        folium.CircleMarker(
            [r["latitude"], r["longitude"]], radius=2, color=E.NODO_FUERA,
            weight=0, fill=True, fill_color=E.NODO_FUERA, fill_opacity=0.8,
            tooltip=f"nodo {r['nodo_id']} (sin ciudad)").add_to(cluster)
    capa_r.add_to(m)

    folium.LayerControl(collapsed=False).add_to(m)

    leyenda = f"""
    <div style="position:fixed; bottom:24px; left:24px; z-index:9999;
                background:{E.SUPERFICIE}; border:1px solid {E.RETICULA};
                border-radius:6px; padding:10px 12px; font:12px system-ui,sans-serif;
                color:{E.TINTA_2}; box-shadow:0 1px 4px rgba(0,0,0,.12)">
      <div style="font-weight:600;color:{E.TINTA};margin-bottom:6px">
        Cobertura de la ciudad por la malla</div>
      <div><span style="display:inline-block;width:10px;height:10px;border-radius:50%;
        background:{E.CALIDAD['alta']};margin-right:6px"></span>alta &mdash; 3+ nodos dentro</div>
      <div><span style="display:inline-block;width:10px;height:10px;border-radius:50%;
        background:{E.CALIDAD['media']};margin-right:6px"></span>media &mdash; 1&ndash;2 nodos dentro</div>
      <div><span style="display:inline-block;width:10px;height:10px;border-radius:50%;
        background:{E.CALIDAD['baja']};margin-right:6px"></span>baja &mdash; solo intersección de celda</div>
      <div style="margin-top:6px">
        <span style="display:inline-block;width:10px;height:10px;
        background:{E.MANCHA};margin-right:6px"></span>mancha urbana INEGI {C.EDICION_MG}</div>
    </div>"""
    m.get_root().html.add_child(folium.Element(leyenda))

    os.makedirs(os.path.dirname(ruta), exist_ok=True)
    m.save(ruta)
    return ruta


if __name__ == "__main__":
    urb = M.manchas_urbanas()
    nodos = A.cargar_nodos()
    pares = A.asignar(urb, nodos)
    res = A.resumen(pares, urb)
    print("[mapa]", construir(urb, nodos, pares, res,
                              os.path.join(C.DIR_SALIDA_MAPAS, "mapa_urbano.html")))
