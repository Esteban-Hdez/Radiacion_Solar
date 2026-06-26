"""
Radiación solar media diaria por MES — Tamaulipas 2017 — en una rejilla 4x3.

Genera un único PNG con 12 mapas (uno por mes) de la insolación media diaria
(kWh/m²/día) por nodo, con escala de color COMPARTIDA y colorbar común para que
los meses sean comparables entre sí.

Salida: Results/Tamaulipas/mapa_radiacion_tamaulipas_2017_12meses.png
"""

import os
import time
import calendar
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

DATASET = 'Data/Tamaulipas/2017/Finales/completo/dataset_tamaulipas_completo_24h_2017.parquet'
METADATA = 'Data/Tamaulipas/metadata_nodos_tamaulipas.csv'
DIR_RESULTADOS = 'Results/Tamaulipas'
ANIO = 2017
RUTA_PNG = os.path.join(DIR_RESULTADOS, f'mapa_radiacion_tamaulipas_{ANIO}_12meses.png')
MESES_ES = ['', 'Enero', 'Febrero', 'Marzo', 'Abril', 'Mayo', 'Junio',
            'Julio', 'Agosto', 'Septiembre', 'Octubre', 'Noviembre', 'Diciembre']


def main():
    os.makedirs(DIR_RESULTADOS, exist_ok=True)
    print(f"=== MAPAS RADIACIÓN SOLAR MEDIA POR MES — TAMAULIPAS {ANIO} (4x3) ===")
    inicio = time.time()

    print("Cargando GHI horario y calculando insolación media diaria por nodo y mes...")
    df = pd.read_parquet(DATASET, columns=['nodo_id', 'ghi', 'month', 'day'])
    # Insolación diaria (kWh/m²/día) -> promedio por nodo y mes
    diaria = df.groupby(['nodo_id', 'month', 'day'])['ghi'].sum() / 1000.0
    mensual = diaria.groupby(['nodo_id', 'month']).mean().reset_index(name='insol')

    meta = pd.read_csv(METADATA, usecols=['nodo_id', 'latitude', 'longitude'])
    mensual = mensual.merge(meta, on='nodo_id', how='inner')

    # Escala de color y extensión COMPARTIDAS
    vmin, vmax = mensual['insol'].min(), mensual['insol'].max()
    pad = 0.1
    xlim = (meta['longitude'].min() - pad, meta['longitude'].max() + pad)
    ylim = (meta['latitude'].min() - pad, meta['latitude'].max() + pad)
    print(f"Escala compartida: [{vmin:.2f}, {vmax:.2f}] kWh/m²/día")

    try:
        import contextily as cx
        proveedor = cx.providers.CartoDB.Positron
    except Exception as e:
        cx, proveedor = None, None
        print(f"(sin mapa base: {e})")

    print("Renderizando 12 subplots...")
    fig, axes = plt.subplots(4, 3, figsize=(10, 19), dpi=170, layout='constrained')
    fig.set_constrained_layout_pads(w_pad=0.01, h_pad=0.01, wspace=0.008, hspace=0.015)
    sc = None
    for mes in range(1, 13):
        ax = axes[(mes - 1) // 3, (mes - 1) % 3]
        sub = mensual[mensual['month'] == mes]
        sc = ax.scatter(sub['longitude'], sub['latitude'], c=sub['insol'],
                        cmap='Spectral_r', s=6, alpha=0.9, edgecolors='none',
                        vmin=vmin, vmax=vmax, zorder=2)
        ax.set_xlim(*xlim)
        ax.set_ylim(*ylim)
        if cx is not None:
            try:
                cx.add_basemap(ax, crs='EPSG:4326', source=proveedor, alpha=0.85, zorder=1)
            except Exception as e:
                print(f"(mes {mes} sin basemap: {e})")
        ax.set_aspect('auto')          # llenar la celda -> mínimo espacio entre mapas
        ax.set_xlim(*xlim)
        ax.set_ylim(*ylim)
        media = sub['insol'].mean()
        ax.set_title(f"{MESES_ES[mes]} - μ={media:.2f}", fontsize=11, fontweight='bold', pad=2)
        ax.set_xticks([]); ax.set_yticks([])

    fig.suptitle(f"Radiación solar media diaria por mes - Tamaulipas ({ANIO})  [kWh/m²/día]",
                 fontsize=15, fontweight='bold')
    # Colorbar común
    cbar = fig.colorbar(sc, ax=axes, fraction=0.02, pad=0.01)
    cbar.set_label('Radiación solar media diaria (kWh/m²/día)')
    plt.savefig(RUTA_PNG, facecolor='white')
    plt.close()

    print(f"\n✅ Listo en {time.time() - inicio:.1f} s")
    print(f"🖼️  {RUTA_PNG}")


if __name__ == "__main__":
    main()
