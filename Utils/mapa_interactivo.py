"""
mapa_interactivo.py
==================

Mapa INTERACTIVO (folium) para inspeccionar nodos con zoom dentro del notebook,
con imagen satelital de fondo (Esri) para distinguir agua de tierra.

Uso en una celda de Jupyter (se renderiza inline al devolver el mapa):

    from Utils.mapa_interactivo import mapa_nodos
    mapa_nodos([2603, 2604, 2650, 2701])      # resalta esos nodos en rojo

Los nodos resaltados salen como marcadores rojos con popup (nodo_id, coords, msnm);
los nodos cercanos salen como puntos azules pequeños para dar contexto.
"""

import pandas as pd
import folium

METADATA = 'Data/Tamaulipas/metadata_nodos_tamaulipas.csv'


def mapa_nodos(resaltar, metadata=METADATA, zoom_inicial=12, margen=0.25):
    """
    Devuelve un mapa folium con `resaltar` (lista de nodo_id) destacados.

    Parameters
    ----------
    resaltar : list[int]   nodo_id a destacar (marcadores rojos con popup).
    metadata : str         CSV con nodo_id, latitude, longitude, msnm (y opcionales).
    zoom_inicial : int     nivel de zoom inicial.
    margen : float         grados alrededor de los nodos resaltados que se muestran
                           como contexto (puntos azules).
    """
    m = pd.read_csv(metadata)
    foco = m[m['nodo_id'].isin(resaltar)]
    if foco.empty:
        raise ValueError("Ninguno de los nodo_id indicados está en la metadata.")

    centro = [foco['latitude'].mean(), foco['longitude'].mean()]
    mapa = folium.Map(location=centro, zoom_start=zoom_inicial, tiles=None)

    # Capas base: satélite (para ver agua/tierra) + callejero
    folium.TileLayer(
        tiles='https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}',
        attr='Esri World Imagery', name='Satélite (Esri)').add_to(mapa)
    folium.TileLayer('OpenStreetMap', name='Callejero').add_to(mapa)

    # Contexto: nodos cercanos (azul, pequeños)
    cerca = m[
        (m['latitude'].between(foco['latitude'].min() - margen, foco['latitude'].max() + margen)) &
        (m['longitude'].between(foco['longitude'].min() - margen, foco['longitude'].max() + margen))
    ]
    for _, r in cerca.iterrows():
        if r['nodo_id'] in set(resaltar):
            continue
        folium.CircleMarker([r['latitude'], r['longitude']], radius=3,
                            color='#1f6feb', fill=True, fill_opacity=0.7, weight=0,
                            popup=f"nodo {int(r['nodo_id'])} · msnm {r['msnm']}").add_to(mapa)

    # Nodos a revisar (rojo, grandes, con popup detallado)
    cols_extra = [c for c in ('nodo_id_4501', 'nodo_id_original') if c in foco.columns]
    for _, r in foco.iterrows():
        extra = ''.join(f"<br>{c}: {int(r[c])}" for c in cols_extra)
        popup = (f"<b>nodo_id: {int(r['nodo_id'])}</b>{extra}"
                 f"<br>lat: {r['latitude']:.3f} · lon: {r['longitude']:.3f}"
                 f"<br><b>msnm: {r['msnm']}</b>")
        folium.Marker([r['latitude'], r['longitude']],
                      popup=folium.Popup(popup, max_width=250),
                      icon=folium.Icon(color='red', icon='tint', prefix='fa')).add_to(mapa)
        folium.CircleMarker([r['latitude'], r['longitude']], radius=9,
                            color='red', fill=False, weight=2).add_to(mapa)

    folium.LayerControl().add_to(mapa)
    return mapa
