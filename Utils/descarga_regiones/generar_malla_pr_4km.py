"""
Genera la malla CORRECTA de Puerto Rico a resolución 4 km (0.04°) a partir de las
coordenadas REALES devueltas por NSRDB en la descarga 2024.

La malla de referencia anterior (`metadata_nodos_pr.csv`) se generó a 0.02°, el
doble de fino que la rejilla real de NSRDB v4. Por eso los 2480 nodos colapsan en
solo 754 celdas físicas (location_id) únicas: 1726 son duplicados.

Este script NO toca los datos descargados. Solo deduplica por `location_id`,
reindexa 0..N-1 y deja en staging:
  Data/Puerto_Rico/malla_4km_propuesta/
    - metadata_nodos_pr_4km.csv   (malla nueva: nodo_id, latitude, longitude, msnm, location_id)
    - mapeo_pr_4km.csv            (nodo_id_viejo -> nodo_id_nuevo, location_id)  [para el filtro]

Y dibuja el mapa de verificación con fondo satelital:
  Results/Puerto_Rico/malla_4km_propuesta.png

    python -m Utils.descarga_regiones.generar_malla_pr_4km
"""

import os
import numpy as np
import pandas as pd

META_2024 = 'Data/Puerto_Rico/2024/metadata_nodos_2024.csv'
OUT_DIR = 'Data/Puerto_Rico/malla_4km_propuesta'
OUT_META = f'{OUT_DIR}/metadata_nodos_pr_4km.csv'
OUT_MAPEO = f'{OUT_DIR}/mapeo_pr_4km.csv'
OUT_MAPA = 'Results/Puerto_Rico/malla_4km_propuesta.png'


def construir_malla(meta_2024=META_2024):
    """Devuelve (malla, mapeo) deduplicando por location_id."""
    m = pd.read_csv(meta_2024, usecols=['nodo_id', 'location_id', 'latitude',
                                        'longitude', 'elevation'])
    # Representante por celda: el nodo_id viejo más pequeño de cada location_id.
    m = m.sort_values('nodo_id')
    rep = m.drop_duplicates('location_id', keep='first').reset_index(drop=True)
    rep = rep.sort_values(['latitude', 'longitude']).reset_index(drop=True)
    rep['nodo_id_nuevo'] = range(len(rep))

    malla = rep.rename(columns={'elevation': 'msnm'})[
        ['nodo_id_nuevo', 'latitude', 'longitude', 'msnm', 'location_id']
    ].rename(columns={'nodo_id_nuevo': 'nodo_id'})

    # Mapeo viejo->nuevo por location_id (todos los nodos viejos de la celda).
    loc2new = rep.set_index('location_id')['nodo_id_nuevo']
    mapeo = m[['nodo_id', 'location_id']].copy()
    mapeo['nodo_id_nuevo'] = mapeo['location_id'].map(loc2new)
    mapeo = mapeo.rename(columns={'nodo_id': 'nodo_id_viejo'}).sort_values('nodo_id_viejo')
    return malla, mapeo


def _paso_rejilla(vals):
    d = np.diff(np.sort(np.unique(np.round(vals, 4))))
    return np.round(np.unique(d), 4)


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    os.makedirs(os.path.dirname(OUT_MAPA), exist_ok=True)

    malla, mapeo = construir_malla()
    malla.to_csv(OUT_META, index=False)
    mapeo.to_csv(OUT_MAPEO, index=False)

    print("=== MALLA PR 4 km (propuesta) ===")
    print(f"Celdas únicas (location_id) : {len(malla)}")
    print(f"Nodos viejos mapeados       : {len(mapeo)}")
    print(f"Paso lat (°)                : {_paso_rejilla(malla.latitude)[:6]}")
    print(f"Paso lon (°)                : {_paso_rejilla(malla.longitude)[:6]}")
    print(f"BBox lat                    : {malla.latitude.min():.3f} .. {malla.latitude.max():.3f}")
    print(f"BBox lon                    : {malla.longitude.min():.3f} .. {malla.longitude.max():.3f}")
    print(f"msnm  min/median/max        : {malla.msnm.min():.0f} / {malla.msnm.median():.0f} / {malla.msnm.max():.0f}")
    print(f"  · celdas con msnm==0      : {(malla.msnm == 0).sum()}")
    print(f"📄 {OUT_META}")
    print(f"📄 {OUT_MAPEO}")

    _mapa(malla)
    print(f"🗺️  {OUT_MAPA}")
    return malla, mapeo


def _mapa(malla):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    try:
        import contextily as cx
        tiene_cx = True
    except Exception:
        tiene_cx = False

    # Web Mercator para casar con los teselados de fondo.
    import numpy as np
    R = 6378137.0
    x = np.radians(malla.longitude) * R
    y = np.log(np.tan(np.pi / 4 + np.radians(malla.latitude) / 2)) * R

    fig, ax = plt.subplots(figsize=(13, 7))
    sobre_mar = malla.msnm == 0
    ax.scatter(x[~sobre_mar], y[~sobre_mar], s=14, c='#00e5ff', edgecolors='k',
               linewidths=0.2, label=f'tierra (msnm>0): {(~sobre_mar).sum()}', zorder=3)
    if sobre_mar.any():
        ax.scatter(x[sobre_mar], y[sobre_mar], s=26, c='red', edgecolors='k',
                   linewidths=0.3, label=f'msnm==0 (revisar): {sobre_mar.sum()}', zorder=4)

    dx = (x.max() - x.min()) * 0.05 + 2000
    dy = (y.max() - y.min()) * 0.05 + 2000
    ax.set_xlim(x.min() - dx, x.max() + dx)
    ax.set_ylim(y.min() - dy, y.max() + dy)
    ax.set_aspect('equal')
    if tiene_cx:
        try:
            cx.add_basemap(ax, source=cx.providers.Esri.WorldImagery, attribution_size=6)
        except Exception as e:
            print(f"  (sin fondo satelital: {e})")
    ax.set_xticks([]); ax.set_yticks([])
    ax.set_title(f'Malla Puerto Rico 4 km (0.04°) — {len(malla)} celdas NSRDB v4 reales')
    ax.legend(loc='lower left', framealpha=0.9)
    fig.tight_layout()
    fig.savefig(OUT_MAPA, dpi=150)
    plt.close(fig)


if __name__ == "__main__":
    main()
