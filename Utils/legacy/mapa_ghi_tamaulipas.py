"""
Mapa estático (PNG) de GHI promedio para Tamaulipas (NSRDB v4, 2017).

Versión solo-PNG (sin el mapa interactivo HTML). Permite filtrar:
  - Anual (por defecto)        ->  python Utils/mapa_ghi_tamaulipas.py
  - Mensual                    ->  python Utils/mapa_ghi_tamaulipas.py --mes 6
  - Un día                     ->  python Utils/mapa_ghi_tamaulipas.py --dia 2017-06-21

El GHI se promedia por nodo sobre las filas del filtro y se pinta sobre un mapa
base topográfico (contextily, si está disponible; si no, se omite el fondo).

Salida: Results/Tamaulipas/mapa_ghi_tamaulipas_2017<sufijo>.png
"""

import os
import time
import argparse
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

DATASET = 'Data/Tamaulipas/2017/Finales/completo/dataset_tamaulipas_completo_24h_2017.parquet'
METADATA = 'Data/Tamaulipas/metadata_nodos_tamaulipas.csv'
DIR_RESULTADOS = 'Results/Tamaulipas'
ANIO = 2017


def parsear_dia(valor):
    """Acepta 'YYYY-MM-DD' o 'MM-DD' (asume el año del dataset)."""
    ts = pd.to_datetime(valor if len(valor.split('-')) == 3 else f'{ANIO}-{valor}')
    return int(ts.month), int(ts.day), ts.strftime('%Y-%m-%d')


def generar_mapa(mes=None, dia=None):
    # --- Resolver filtro, sufijo y título ---
    cols = ['nodo_id', 'ghi']
    if dia:
        m, d, fecha = parsear_dia(dia)
        cols += ['month', 'day']
        sufijo, etiqueta = f'_{fecha}', f'Día: {fecha}'
    elif mes:
        cols += ['month']
        sufijo, etiqueta = f'_mes{int(mes):02d}', f'Mes: {int(mes)}'
    else:
        sufijo, etiqueta = '_anual', 'Anual'

    os.makedirs(DIR_RESULTADOS, exist_ok=True)
    ruta_png = os.path.join(DIR_RESULTADOS, f'mapa_ghi_tamaulipas_{ANIO}{sufijo}.png')

    print(f"=== MAPA GHI TAMAULIPAS {ANIO} | {etiqueta} ===")
    inicio = time.time()

    # --- Cargar (solo las columnas necesarias) y filtrar ---
    print("Cargando dataset y metadata...")
    df = pd.read_parquet(DATASET, columns=list(dict.fromkeys(cols)))
    if dia:
        df = df[(df['month'] == m) & (df['day'] == d)]
    elif mes:
        df = df[df['month'] == int(mes)]
    if df.empty:
        print("⚠️  El filtro no devolvió filas. Revisa el mes/día.")
        return

    # --- Agregación por nodo + coordenadas ---
    print("Promediando GHI por nodo...")
    agg = df.groupby('nodo_id', as_index=False)['ghi'].mean()
    meta = pd.read_csv(METADATA, usecols=['nodo_id', 'latitude', 'longitude'])
    mapa = agg.merge(meta, on='nodo_id', how='inner')
    print(f"Nodos: {len(mapa)} | GHI medio {mapa.ghi.mean():.1f} | "
          f"rango [{mapa.ghi.min():.1f}, {mapa.ghi.max():.1f}] W/m²")

    # --- Mapa estático ---
    print("Renderizando PNG...")
    fig, ax = plt.subplots(figsize=(9, 12), dpi=250)
    sc = ax.scatter(mapa['longitude'], mapa['latitude'], c=mapa['ghi'],
                    cmap='Spectral_r', s=14, alpha=0.85, edgecolors='none', zorder=2)

    # Mapa base topográfico (opcional)
    try:
        import contextily as cx
        cx.add_basemap(ax, crs='EPSG:4326',
                       source=cx.providers.CartoDB.Positron, alpha=0.85, zorder=1)
    except Exception as e:
        print(f"(sin mapa base: {e})")

    plt.colorbar(sc, ax=ax, label='Irradiancia Global Horizontal promedio (W/m²)',
                 fraction=0.046, pad=0.04)
    ax.set_title(f"GHI promedio — Tamaulipas ({ANIO}) | {etiqueta}",
                 fontsize=13, fontweight='bold')
    ax.set_xlabel("Longitud")
    ax.set_ylabel("Latitud")
    ax.grid(True, linestyle='--', alpha=0.3, zorder=3)
    plt.tight_layout()
    plt.savefig(ruta_png, bbox_inches='tight', facecolor='white')
    plt.close()

    print(f"\n✅ Listo en {time.time() - inicio:.1f} s")
    print(f"🖼️  {ruta_png}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Mapa PNG de GHI promedio (Tamaulipas 2017).")
    ap.add_argument('--mes', type=int, choices=range(1, 13), metavar='1-12',
                    help='Filtra por mes (promedio mensual).')
    ap.add_argument('--dia', type=str, metavar='YYYY-MM-DD',
                    help='Filtra por un día (promedio de ese día). Tiene prioridad sobre --mes.')
    args = ap.parse_args()
    if args.dia and args.mes:
        print("ℹ️  Se especificaron --dia y --mes; se usa --dia.")
    generar_mapa(mes=args.mes, dia=args.dia)
