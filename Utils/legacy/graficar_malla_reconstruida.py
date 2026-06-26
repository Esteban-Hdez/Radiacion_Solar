"""
Validación visual de la malla reconstruida (coordenadas reales NSRDB v4).

Compara la malla original solicitada (0.038°, con duplicados) contra la malla
real deduplicada (0.04°) para comprobar si la eliminación de duplicados deja
huecos o solo reduce el sobre-muestreo.
"""
import os
import pandas as pd
import matplotlib.pyplot as plt

RUTA_CSV = 'Data/Geometria/metadata_nodos_tamaulipas_reconstruido.csv'
RUTA_PNG = 'Data/Geometria/validacion_malla_reconstruida.png'


def cargar_frontera():
    """Frontera de Tamaulipas desde la caché de osmnx (sin red si ya existe)."""
    try:
        import osmnx as ox
        ox.settings.use_cache = True
        return ox.geocode_to_gdf("Tamaulipas, Mexico")
    except Exception as e:
        print(f"(sin frontera OSM: {e})")
        return None


def main():
    df = pd.read_csv(RUTA_CSV)
    unicos = df[~df['es_duplicado']]
    dups = df[df['es_duplicado']]
    frontera = cargar_frontera()

    fig, axes = plt.subplots(1, 3, figsize=(21, 9), dpi=150, sharex=True, sharey=True)
    titulos = [
        f"Original solicitada 0.038°\n({len(df)} nodos, con duplicados)",
        f"Real NSRDB 0.04° deduplicada\n({len(unicos)} celdas únicas)",
        f"Nodos duplicados eliminados\n({len(dups)} redundantes)",
    ]
    for ax, titulo in zip(axes, titulos):
        if frontera is not None:
            frontera.plot(ax=ax, facecolor='lightblue', edgecolor='blue', alpha=0.4)
        ax.set_title(titulo, fontsize=12, fontweight='bold')
        ax.set_xlabel("Longitud"); ax.grid(True, linestyle='--', alpha=0.3)
    axes[0].set_ylabel("Latitud")

    axes[0].scatter(df.lon_local, df.lat_local, s=3, c='red', alpha=0.7)
    axes[1].scatter(unicos.lon_real, unicos.lat_real, s=3, c='green', alpha=0.8)
    # Panel 3: únicos en gris + duplicados resaltados encima
    axes[2].scatter(unicos.lon_real, unicos.lat_real, s=3, c='lightgray', alpha=0.6)
    axes[2].scatter(dups.lon_local, dups.lat_local, s=10, c='orange',
                    alpha=0.9, edgecolors='darkorange', linewidths=0.3)

    plt.suptitle("Malla Tamaulipas: solicitada vs. rejilla real NSRDB v4",
                 fontsize=15, fontweight='bold')
    plt.tight_layout()
    plt.savefig(RUTA_PNG, bbox_inches='tight')
    plt.close()
    print(f"Mapa guardado en: {RUTA_PNG}")
    print(f"  Original: {len(df)}  |  Únicos: {len(unicos)}  |  Duplicados: {len(dups)}")


if __name__ == "__main__":
    main()
