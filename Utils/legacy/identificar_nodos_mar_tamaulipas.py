"""
Identifica los nodos sobre AGUA (Golfo de México / Laguna Madre / isla de barrera)
en la malla de Tamaulipas y los marca como candidatos a eliminar.

Señal usada: elevación `msnm == 0`. NSRDB asigna elevación 0 a las celdas sobre
agua, así que `msnm == 0` captura limpiamente los nodos costeros sobre mar/laguna
(en Tamaulipas: 58 nodos, todos en la franja este; sin falsos positivos tierra
adentro). El umbral es ajustable (`--umbral`) por si se quiere incluir la isla de
barrera con elevación ligeramente > 0.

Por ahora NO filtra nada: solo genera una imagen de diagnóstico pintando de NEGRO
los nodos candidatos sobre el mapa, y guarda su lista en CSV para el filtro futuro.

Salidas:
  - Results/Tamaulipas/nodos_mar_candidatos.png   (imagen de diagnóstico)
  - Data/Tamaulipas/nodos_mar_candidatos.csv      (lista de nodos candidatos)
"""

import os
import argparse
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

METADATA = 'Data/Tamaulipas/metadata_nodos_tamaulipas.csv'
DIR_RESULTADOS = 'Results/Tamaulipas'
RUTA_PNG = os.path.join(DIR_RESULTADOS, 'nodos_mar_candidatos.png')
RUTA_CSV = 'Data/Tamaulipas/nodos_mar_candidatos.csv'


SELECCION_DEFECTO = 'Data/Tamaulipas/nodos_a_eliminar.csv'


def main(umbral=0.0, seleccion=None):
    os.makedirs(DIR_RESULTADOS, exist_ok=True)
    m = pd.read_csv(METADATA)

    if seleccion and os.path.exists(seleccion):
        ids = set(pd.read_csv(seleccion)['nodo_id'])
        es_mar = m['nodo_id'].isin(ids)
        criterio = f"selección manual ({seleccion}): {len(ids)} nodos"
    else:
        es_mar = m['msnm'] <= umbral
        criterio = f"msnm <= {umbral}"

    cand = m[es_mar].copy()
    tierra = m[~es_mar]

    print(f"=== NODOS CANDIDATOS A ELIMINAR (mar / laguna / isla) ===")
    print(f"Criterio: {criterio}")
    print(f"Candidatos: {len(cand)} de {len(m)}  ({100*len(cand)/len(m):.1f}%)")
    print(f"Quedarían en tierra: {len(tierra)}")
    print(f"Rango lon candidatos: [{cand.longitude.min():.2f}, {cand.longitude.max():.2f}]")

    # Guardar la lista para el filtro futuro
    cand[['nodo_id', 'nodo_id_original', 'latitude', 'longitude', 'msnm']].to_csv(RUTA_CSV, index=False)

    # --- Imagen de diagnóstico ---
    fig, ax = plt.subplots(figsize=(9, 12), dpi=250)
    pad = 0.1
    ax.set_xlim(m.longitude.min() - pad, m.longitude.max() + pad)
    ax.set_ylim(m.latitude.min() - pad, m.latitude.max() + pad)

    ax.scatter(tierra.longitude, tierra.latitude, s=10, c='#5b8db8',
               alpha=0.7, edgecolors='none', zorder=2, label=f'Tierra ({len(tierra)})')
    ax.scatter(cand.longitude, cand.latitude, s=22, c='black',
               alpha=0.95, edgecolors='none', zorder=3,
               label=f'Candidatos a eliminar ({len(cand)})')

    try:
        import contextily as cx
        cx.add_basemap(ax, crs='EPSG:4326',
                       source=cx.providers.CartoDB.Positron, alpha=0.9, zorder=1)
        ax.set_aspect('auto')
        ax.set_xlim(m.longitude.min() - pad, m.longitude.max() + pad)
        ax.set_ylim(m.latitude.min() - pad, m.latitude.max() + pad)
    except Exception as e:
        print(f"(sin mapa base: {e})")

    ax.set_title("Nodos candidatos a eliminar (mar / laguna / isla) - Tamaulipas",
                 fontsize=13, fontweight='bold')
    ax.set_xlabel("Longitud")
    ax.set_ylabel("Latitud")
    ax.legend(loc='lower left', framealpha=0.9)
    ax.grid(True, linestyle='--', alpha=0.3, zorder=4)
    plt.tight_layout()
    plt.savefig(RUTA_PNG, bbox_inches='tight', facecolor='white')
    plt.close()

    print(f"\n🖼️  {RUTA_PNG}")
    print(f"📄 {RUTA_CSV}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Identifica y pinta los nodos sobre agua (Tamaulipas).")
    ap.add_argument('--umbral', type=float, default=0.0,
                    help="Elevación máxima (msnm) para considerar un nodo como agua. Def: 0.")
    ap.add_argument('--seleccion', type=str, default=None,
                    help="CSV con la selección manual (col 'nodo_id'). Si se pasa, se usa "
                         f"en vez del umbral. Ej: {SELECCION_DEFECTO}")
    args = ap.parse_args()
    main(umbral=args.umbral, seleccion=args.seleccion)
