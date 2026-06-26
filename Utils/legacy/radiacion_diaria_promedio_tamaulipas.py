"""
Radiación solar diaria promedio — Tamaulipas (NSRDB v4, 2017).

Calcula la insolación diaria (kWh/m²/día) = suma del GHI horario de cada día,
para cada nodo, y grafica el promedio espacial a lo largo del año con su banda
de variabilidad (±1 desviación estándar entre nodos).

  insolación_diaria [kWh/m²/día] = Σ_24h GHI[W/m²] · 1 h / 1000

Salida: Results/Tamaulipas/radiacion_diaria_promedio_tamaulipas_2017.png
"""

import os
import time
import pandas as pd
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.dates as mdates

DATASET = 'Data/Tamaulipas/2017/Finales/completo/dataset_tamaulipas_completo_24h_2017.parquet'
DIR_RESULTADOS = 'Results/Tamaulipas'
ANIO = 2017
RUTA_PNG = os.path.join(DIR_RESULTADOS, f'radiacion_diaria_promedio_tamaulipas_{ANIO}.png')


def main():
    os.makedirs(DIR_RESULTADOS, exist_ok=True)
    print(f"=== RADIACIÓN SOLAR DIARIA PROMEDIO — TAMAULIPAS {ANIO} ===")
    inicio = time.time()

    print("Cargando GHI horario...")
    df = pd.read_parquet(DATASET, columns=['nodo_id', 'datetime', 'ghi'])
    df['fecha'] = df['datetime'].dt.normalize()

    # 1) Insolación diaria por nodo (kWh/m²/día) = suma horaria / 1000
    print("Calculando insolación diaria por nodo...")
    insol_nodo = (df.groupby(['fecha', 'nodo_id'])['ghi'].sum() / 1000.0).rename('insol')

    # 2) Estadísticos espaciales por día (entre nodos)
    diario = insol_nodo.groupby('fecha').agg(['mean', 'std', 'min', 'max'])
    media_anual = diario['mean'].mean()
    print(f"Días: {len(diario)} | Insolación media anual: {media_anual:.2f} kWh/m²/día | "
          f"rango diario [{diario['mean'].min():.2f}, {diario['mean'].max():.2f}]")

    # 3) Gráfico
    print("Renderizando...")
    fig, ax = plt.subplots(figsize=(14, 6), dpi=200)
    x = diario.index

    ax.fill_between(x, diario['mean'] - diario['std'], diario['mean'] + diario['std'],
                    color='orange', alpha=0.25, label='±1 σ entre nodos')
    ax.plot(x, diario['mean'], color='#d1410c', lw=1.4, label='Promedio espacial diario')
    ax.axhline(media_anual, color='gray', ls='--', lw=1.2,
               label=f'Media anual = {media_anual:.2f} kWh/m²/día')

    # Promedio mensual como referencia (escalón)
    mensual = diario['mean'].groupby(diario.index.to_period('M')).mean()
    ax.step([p.to_timestamp(how='start') for p in mensual.index] + [pd.Timestamp(f'{ANIO+1}-01-01')],
            list(mensual.values) + [mensual.values[-1]],
            where='post', color='#1f4e79', lw=1.6, alpha=0.8, label='Promedio mensual')

    ax.set_title(f"Radiación solar diaria promedio — Tamaulipas ({ANIO})",
                 fontsize=14, fontweight='bold')
    ax.set_xlabel("Mes")
    ax.set_ylabel("Insolación diaria  (kWh/m²/día)")
    ax.xaxis.set_major_locator(mdates.MonthLocator())
    ax.xaxis.set_major_formatter(mdates.DateFormatter('%b'))
    ax.set_xlim(x.min(), pd.Timestamp(f'{ANIO}-12-31'))
    ax.grid(True, ls='--', alpha=0.3)
    ax.legend(loc='lower center', ncol=4, fontsize=9, framealpha=0.9)
    plt.tight_layout()
    plt.savefig(RUTA_PNG, bbox_inches='tight', facecolor='white')
    plt.close()

    print(f"\n✅ Listo en {time.time() - inicio:.1f} s")
    print(f"🖼️  {RUTA_PNG}")


if __name__ == "__main__":
    main()
