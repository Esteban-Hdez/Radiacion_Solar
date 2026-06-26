"""
Mapa estático (PNG) de RADIACIÓN SOLAR MEDIA DIARIA — Tamaulipas (NSRDB v4, 2017).

Igual que `mapa_ghi_tamaulipas.py`, pero cada nodo se colorea por su insolación
media diaria (kWh/m²/día) en lugar del GHI medio (W/m²):

    insolación_diaria[nodo] = mean_días( Σ_24h GHI[W/m²] · 1 h / 1000 )

Filtros:
  - Anual (por defecto)   ->  python Utils/mapa_radiacion_tamaulipas.py
  - Mensual               ->  python Utils/mapa_radiacion_tamaulipas.py --mes 6
  - Un día                ->  python Utils/mapa_radiacion_tamaulipas.py --dia 2017-06-21

Salida: Results/Tamaulipas/mapa_radiacion_tamaulipas_2017<sufijo>.png
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
    if dia:
        m, d, fecha = parsear_dia(dia)
        sufijo, etiqueta = f'_{fecha}', f'Día: {fecha}'
    elif mes:
        sufijo, etiqueta = f'_mes{int(mes):02d}', f'Mes: {int(mes)}'
    else:
        sufijo, etiqueta = '_anual', 'Anual'

    os.makedirs(DIR_RESULTADOS, exist_ok=True)
    ruta_png = os.path.join(DIR_RESULTADOS, f'mapa_radiacion_tamaulipas_{ANIO}{sufijo}.png')

    print(f"=== MAPA RADIACIÓN SOLAR MEDIA — TAMAULIPAS {ANIO} | {etiqueta} ===")
    inicio = time.time()

    # --- Cargar y filtrar ---
    print("Cargando GHI horario y metadata...")
    df = pd.read_parquet(DATASET, columns=['nodo_id', 'ghi', 'month', 'day'])
    if dia:
        df = df[(df['month'] == m) & (df['day'] == d)]
    elif mes:
        df = df[df['month'] == int(mes)]
    if df.empty:
        print("⚠️  El filtro no devolvió filas. Revisa el mes/día.")
        return

    # --- Insolación diaria por nodo -> media sobre los días del filtro ---
    print("Calculando radiación media diaria por nodo (kWh/m²/día)...")
    diaria = df.groupby(['nodo_id', 'month', 'day'])['ghi'].sum() / 1000.0
    por_nodo = diaria.groupby('nodo_id').mean().reset_index(name='insol')

    meta = pd.read_csv(METADATA, usecols=['nodo_id', 'latitude', 'longitude'])
    mapa = por_nodo.merge(meta, on='nodo_id', how='inner')
    print(f"Nodos: {len(mapa)} | media {mapa.insol.mean():.2f} | "
          f"rango [{mapa.insol.min():.2f}, {mapa.insol.max():.2f}] kWh/m²/día")

    # --- Mapa estático ---
    print("Renderizando PNG...")
    fig, ax = plt.subplots(figsize=(9, 12), dpi=250)
    sc = ax.scatter(mapa['longitude'], mapa['latitude'], c=mapa['insol'],
                    cmap='Spectral_r', s=14, alpha=0.85, edgecolors='none', zorder=2)

    try:
        import contextily as cx
        cx.add_basemap(ax, crs='EPSG:4326',
                       source=cx.providers.CartoDB.Positron, alpha=0.85, zorder=1)
    except Exception as e:
        print(f"(sin mapa base: {e})")

    plt.colorbar(sc, ax=ax, label='Radiación solar media diaria (kWh/m²/día)',
                 fraction=0.046, pad=0.04)
    ax.set_title(f"Radiación solar media diaria — Tamaulipas ({ANIO}) | {etiqueta}",
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
    ap = argparse.ArgumentParser(description="Mapa PNG de radiación solar media diaria (Tamaulipas 2017).")
    ap.add_argument('--mes', type=int, choices=range(1, 13), metavar='1-12',
                    help='Filtra por mes (promedio mensual).')
    ap.add_argument('--dia', type=str, metavar='YYYY-MM-DD',
                    help='Filtra por un día. Tiene prioridad sobre --mes.')
    args = ap.parse_args()
    if args.dia and args.mes:
        print("ℹ️  Se especificaron --dia y --mes; se usa --dia.")
    generar_mapa(mes=args.mes, dia=args.dia)
