"""
mapas_espaciales.py
===================

Generador de mapas espaciales estáticos (PNG) para CUALQUIER variable del
dataset NSRDB v4 de Tamaulipas (2017), sobre un mapa base topográfico.

Unifica en una sola clase (`MapaEspacial`) los mapas que veníamos haciendo
(GHI, radiación) y los generaliza a cualquier columna del dataset (temperatura,
viento, humedad, presión, etc.), con:

  - Filtro temporal:   anual · mensual · un día.
  - Modo de agregación por nodo:
        'media'        -> promedio de los valores horarios (temperatura, viento,
                          GHI en W/m², ...).
        'suma_diaria'  -> promedio de los TOTALES diarios (Σ de cada día y luego
                          media entre días). Con `factor` para convertir unidades.
                          Es la "radiación solar media diaria" (insolación):
                          variable='ghi', agregacion='suma_diaria', factor=1/1000
                          -> kWh/m²/día.
        'max' / 'min'  -> extremos por nodo.
  - Panel 4x3 con los 12 meses (escala de color compartida).

Uso rápido (Python)
-------------------
    from Utils.mapas_espaciales import MapaEspacial
    m = MapaEspacial()

    # Temperatura media anual
    m.mapa('temperature', titulo_var='Temperatura', unidades='°C', cmap='inferno')

    # Radiación solar media diaria (insolación) anual
    m.mapa('ghi', agregacion='suma_diaria', factor=1/1000,
           titulo_var='Radiación solar media diaria', unidades='kWh/m²/día')

    # GHI medio de junio (W/m²)
    m.mapa('ghi', filtro='mensual', mes=6, titulo_var='GHI', unidades='W/m²')

    # Velocidad del viento de un día
    m.mapa('wind_speed', filtro='diario', dia='2017-06-21',
           titulo_var='Velocidad del viento', unidades='m/s', cmap='viridis')

    # Panel de los 12 meses (temperatura)
    m.mapa_12_meses('temperature', titulo_var='Temperatura', unidades='°C', cmap='inferno')

Uso rápido (línea de comandos)
------------------------------
    python Utils/mapas_espaciales.py --variable temperature --unidades "°C" --cmap inferno
    python Utils/mapas_espaciales.py --variable ghi --agregacion suma_diaria --factor 0.001 \
           --unidades "kWh/m²/día" --titulo "Radiación solar media diaria"
    python Utils/mapas_espaciales.py --variable ghi --filtro mensual --mes 6 --unidades "W/m²"
    python Utils/mapas_espaciales.py --variable wind_speed --filtro diario --dia 2017-06-21 --unidades m/s
    python Utils/mapas_espaciales.py --variable temperature --panel12 --unidades "°C" --cmap inferno
"""

import os
import time
import argparse
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

MESES_ES = ['', 'Enero', 'Febrero', 'Marzo', 'Abril', 'Mayo', 'Junio', 'Julio',
            'Agosto', 'Septiembre', 'Octubre', 'Noviembre', 'Diciembre']

# Texto que describe cada modo de agregación (para los títulos)
_DESC_AGG = {'media': 'media', 'suma_diaria': 'media diaria',
             'max': 'máxima', 'min': 'mínima'}

# Paleta recomendada por variable (intuitiva). Si no se pasa `cmap` explícito,
# la clase elige una de aquí; si la variable no está, usa PALETA_DEFECTO.
#   - Temperatura/punto de rocío: frío = azul, calor = rojo (convención meteo).
#   - Humedad / agua precipitable: seco = claro, húmedo = azul-verde.
#   - Viento / presión: secuenciales perceptualmente uniformes.
#   - Radiación / irradiancia: se quedan con la diverging por defecto (rojo = más sol).
PALETAS = {
    'temperature': 'coolwarm',
    'dew_point': 'coolwarm',
    'relative_humidity': 'YlGnBu',
    'precipitable_water': 'YlGnBu',
    'wind_speed': 'viridis',
    'wind_direction': 'twilight',      # circular (0°=360°)
    'pressure': 'cividis',
    'solar_zenith_angle': 'cividis',
}
PALETA_DEFECTO = 'Spectral_r'          # GHI/irradiancia y cualquier otra no listada


class MapaEspacial:
    """
    Mapas espaciales (PNG) de una variable del dataset NSRDB de Tamaulipas.

    Cada nodo (4501 celdas reales) se colorea con el valor agregado de la
    variable sobre el periodo elegido, dibujado sobre un mapa base topográfico
    (contextily; si no está disponible se omite el fondo y se dibujan los puntos).

    Parameters
    ----------
    dataset : str
        Ruta al parquet COMPLETO unificado (24 h, todas las variables).
    metadata : str
        CSV con `nodo_id, latitude, longitude` (clave de unión `nodo_id`).
    dir_salida : str
        Carpeta donde se guardan los PNG.
    anio : int
        Año (solo para títulos y nombres de archivo).

    Métodos públicos
    ----------------
    mapa(variable, filtro='anual', mes=None, dia=None, agregacion='media',
         factor=1.0, titulo_var=None, unidades='', cmap='Spectral_r')
        Un mapa con filtro anual / mensual / diario.
    mapa_12_meses(variable, agregacion='media', factor=1.0, titulo_var=None,
                  unidades='', cmap='Spectral_r')
        Panel 4x3 con los 12 meses (escala de color compartida).

    Notas
    -----
    - 'media' agrega promediando los valores horarios (apto para temperatura,
      viento, humedad, GHI en W/m², etc.).
    - 'suma_diaria' suma cada día y promedia entre días -> "promedio diario".
      Para radiación: factor=1/1000 convierte W·h/m² a kWh/m²/día.
    - El filtro 'diario' acepta 'YYYY-MM-DD' o 'MM-DD'.
    - Paleta: si no se pasa `cmap`, se elige una intuitiva por variable
      (ver `PALETAS`): temperatura -> 'coolwarm' (frío azul, calor rojo),
      humedad -> 'YlGnBu', viento -> 'viridis', presión -> 'cividis', etc.
      Un `cmap` explícito siempre tiene prioridad.

    Examples
    --------
    >>> m = MapaEspacial()
    >>> m.mapa('temperature', titulo_var='Temperatura', unidades='°C', cmap='inferno')
    >>> m.mapa('ghi', agregacion='suma_diaria', factor=1/1000,
    ...        titulo_var='Radiación solar media diaria', unidades='kWh/m²/día')
    >>> m.mapa_12_meses('relative_humidity', titulo_var='Humedad relativa',
    ...                 unidades='%', cmap='YlGnBu')
    """

    DATASET = 'Data/Tamaulipas/2017/Finales/completo/dataset_tamaulipas_completo_24h_2017.parquet'
    METADATA = 'Data/Tamaulipas/metadata_nodos_tamaulipas.csv'
    DIR_SALIDA = 'Results/Tamaulipas'

    def __init__(self, dataset=None, metadata=None, dir_salida=None, anio=2017,
                 region='Tamaulipas'):
        self.dataset = dataset or self.DATASET
        self.metadata = metadata or self.METADATA
        self.dir_salida = dir_salida or self.DIR_SALIDA
        self.anio = anio
        self.region = region          # solo para los títulos
        os.makedirs(self.dir_salida, exist_ok=True)

        # Coordenadas y extensión del mapa (se reutilizan en todos los gráficos)
        self.meta = pd.read_csv(self.metadata, usecols=['nodo_id', 'latitude', 'longitude'])
        pad = 0.1
        self.xlim = (self.meta['longitude'].min() - pad, self.meta['longitude'].max() + pad)
        self.ylim = (self.meta['latitude'].min() - pad, self.meta['latitude'].max() + pad)

        # Columnas disponibles (para validar la variable pedida)
        import pyarrow.parquet as pq
        self.columnas = [c.name for c in pq.ParquetFile(self.dataset).schema_arrow]

    # ------------------------------------------------------------------ #
    # Internos
    # ------------------------------------------------------------------ #
    def _validar(self, variable, agregacion):
        if variable not in self.columnas:
            raise ValueError(
                f"Variable '{variable}' no existe. Disponibles:\n  "
                + ', '.join(c for c in self.columnas if c not in
                            ('nodo_id', 'datetime', 'year', 'month', 'day', 'hour')))
        if agregacion not in _DESC_AGG:
            raise ValueError(f"agregacion debe ser uno de {list(_DESC_AGG)}")

    @staticmethod
    def _resolver_cmap(variable, cmap):
        """Paleta explícita si se pasa; si no, la recomendada por variable."""
        return cmap or PALETAS.get(variable, PALETA_DEFECTO)

    @staticmethod
    def _parsear_dia(valor, anio):
        ts = pd.to_datetime(valor if len(str(valor).split('-')) == 3 else f'{anio}-{valor}')
        return int(ts.month), int(ts.day), ts.strftime('%Y-%m-%d')

    def _cargar(self, variable):
        """Carga solo lo necesario: nodo_id, la variable y las llaves de tiempo."""
        return pd.read_parquet(self.dataset, columns=['nodo_id', 'month', 'day', variable])

    @staticmethod
    def _agregar(df, variable, agregacion, factor, por=('nodo_id',)):
        """Valor agregado de `variable` por `por` (p.ej. nodo, o nodo+mes)."""
        por = list(por)
        if agregacion == 'media':
            s = df.groupby(por)[variable].mean()
        elif agregacion == 'max':
            s = df.groupby(por)[variable].max()
        elif agregacion == 'min':
            s = df.groupby(por)[variable].min()
        elif agregacion == 'suma_diaria':
            llaves = por + [k for k in ('month', 'day') if k not in por]
            diaria = df.groupby(llaves)[variable].sum()
            s = diaria.groupby(por).mean()
        return (s * factor).rename('valor')

    def _con_coords(self, serie):
        return serie.reset_index().merge(self.meta, on='nodo_id', how='inner')

    def _dibujar(self, ax, mapa, cmap, vmin, vmax, basemap=True, s=14):
        """Pinta el scatter + mapa base en un eje y devuelve el mappable."""
        sc = ax.scatter(mapa['longitude'], mapa['latitude'], c=mapa['valor'],
                        cmap=cmap, s=s, alpha=0.88, edgecolors='none',
                        vmin=vmin, vmax=vmax, zorder=2)
        ax.set_xlim(*self.xlim)
        ax.set_ylim(*self.ylim)
        if basemap:
            try:
                import contextily as cx
                cx.add_basemap(ax, crs='EPSG:4326',
                               source=cx.providers.CartoDB.Positron, alpha=0.85, zorder=1)
                ax.set_aspect('auto')              # llenar la celda
                ax.set_xlim(*self.xlim)
                ax.set_ylim(*self.ylim)
            except Exception as e:
                print(f"(sin mapa base: {e})")
        return sc

    # ------------------------------------------------------------------ #
    # API pública
    # ------------------------------------------------------------------ #
    def mapa(self, variable, filtro='anual', mes=None, dia=None, agregacion='media',
             factor=1.0, titulo_var=None, unidades='', cmap=None, guardar=True):
        """
        Genera un mapa de `variable` para un periodo (anual / mensual / diario).

        Parameters
        ----------
        variable : str           Columna del dataset (p.ej. 'ghi', 'temperature').
        filtro : {'anual','mensual','diario'}
        mes : int                Mes 1-12 (si filtro='mensual').
        dia : str                'YYYY-MM-DD' o 'MM-DD' (si filtro='diario').
        agregacion : {'media','suma_diaria','max','min'}
        factor : float           Multiplica el valor final (conversión de unidades).
        titulo_var : str         Nombre legible de la variable (por defecto, la columna).
        unidades : str           Texto de unidades para la colorbar.
        cmap : str               Mapa de color de matplotlib.
        guardar : bool           Si False, no escribe el PNG (solo lo calcula).

        Returns
        -------
        str : ruta del PNG generado.
        """
        self._validar(variable, agregacion)
        titulo_var = titulo_var or variable
        cmap = self._resolver_cmap(variable, cmap)

        # Resolver filtro temporal
        df = self._cargar(variable)
        if filtro == 'mensual':
            if not mes:
                raise ValueError("filtro='mensual' requiere mes=1..12")
            df = df[df['month'] == int(mes)]
            etiqueta, sufijo = f'Mes: {int(mes)}', f'_mes{int(mes):02d}'
        elif filtro == 'diario':
            if not dia:
                raise ValueError("filtro='diario' requiere dia='YYYY-MM-DD'")
            mm, dd, fecha = self._parsear_dia(dia, self.anio)
            df = df[(df['month'] == mm) & (df['day'] == dd)]
            etiqueta, sufijo = f'Día: {fecha}', f'_{fecha}'
        elif filtro == 'anual':
            etiqueta, sufijo = 'Anual', '_anual'
        else:
            raise ValueError("filtro debe ser 'anual', 'mensual' o 'diario'")

        if df.empty:
            raise ValueError("El filtro no devolvió filas (revisa mes/día).")

        print(f"=== MAPA {titulo_var} ({_DESC_AGG[agregacion]}) | {etiqueta} ===")
        inicio = time.time()
        mapa = self._con_coords(self._agregar(df, variable, agregacion, factor))
        print(f"Nodos: {len(mapa)} | valor medio {mapa.valor.mean():.2f} "
              f"| rango [{mapa.valor.min():.2f}, {mapa.valor.max():.2f}] {unidades}")

        _fig, ax = plt.subplots(figsize=(9, 12), dpi=250)
        sc = self._dibujar(ax, mapa, cmap, mapa.valor.min(), mapa.valor.max())
        etiqueta_cb = f"{titulo_var} {_DESC_AGG[agregacion]}" + (f" ({unidades})" if unidades else "")
        plt.colorbar(sc, ax=ax, label=etiqueta_cb, fraction=0.046, pad=0.04)
        ax.set_title(f"{titulo_var} {_DESC_AGG[agregacion]} - {self.region} ({self.anio}) | {etiqueta}",
                     fontsize=13, fontweight='bold')
        ax.set_xlabel("Longitud")
        ax.set_ylabel("Latitud")
        ax.grid(True, linestyle='--', alpha=0.3, zorder=3)
        plt.tight_layout()

        ruta = os.path.join(self.dir_salida, f'mapa_{variable}_{self.anio}{sufijo}.png')
        if guardar:
            plt.savefig(ruta, bbox_inches='tight', facecolor='white')
        plt.close()
        print(f"✅ {time.time() - inicio:.1f} s -> {ruta}\n")
        return ruta

    def mapa_12_meses(self, variable, agregacion='media', factor=1.0,
                      titulo_var=None, unidades='', cmap=None):
        """
        Panel 4x3 con un mapa por mes (escala de color compartida y comparable).

        Mismos parámetros de agregación que `mapa`. Devuelve la ruta del PNG.
        """
        self._validar(variable, agregacion)
        titulo_var = titulo_var or variable
        cmap = self._resolver_cmap(variable, cmap)

        print(f"=== PANEL 12 MESES {titulo_var} ({_DESC_AGG[agregacion]}) ===")
        inicio = time.time()
        df = self._cargar(variable)
        serie = self._agregar(df, variable, agregacion, factor, por=('nodo_id', 'month'))
        mensual = self._con_coords(serie)
        vmin, vmax = mensual['valor'].min(), mensual['valor'].max()
        print(f"Escala compartida: [{vmin:.2f}, {vmax:.2f}] {unidades}")

        fig, axes = plt.subplots(4, 3, figsize=(10, 19), dpi=170, layout='constrained')
        fig.set_constrained_layout_pads(w_pad=0.01, h_pad=0.01, wspace=0.008, hspace=0.015)
        sc = None
        for mes in range(1, 13):
            ax = axes[(mes - 1) // 3, (mes - 1) % 3]
            sub = mensual[mensual['month'] == mes]
            sc = self._dibujar(ax, sub, cmap, vmin, vmax, s=6)
            ax.set_title(f"{MESES_ES[mes]} - μ={sub['valor'].mean():.2f}",
                         fontsize=11, fontweight='bold', pad=2)
            ax.set_xticks([]); ax.set_yticks([])

        etiqueta_cb = f"{titulo_var} {_DESC_AGG[agregacion]}" + (f" ({unidades})" if unidades else "")
        fig.suptitle(f"{titulo_var} {_DESC_AGG[agregacion]} por mes - {self.region} ({self.anio})",
                     fontsize=15, fontweight='bold')
        cbar = fig.colorbar(sc, ax=axes, fraction=0.02, pad=0.01)
        cbar.set_label(etiqueta_cb)

        ruta = os.path.join(self.dir_salida, f'mapa_{variable}_{self.anio}_12meses.png')
        plt.savefig(ruta, facecolor='white')
        plt.close()
        print(f"✅ {time.time() - inicio:.1f} s -> {ruta}\n")
        return ruta


# ---------------------------------------------------------------------- #
# CLI
# ---------------------------------------------------------------------- #
def _cli():
    ap = argparse.ArgumentParser(
        description="Mapas espaciales de variables NSRDB (Tamaulipas).",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="Ejemplos:\n"
               "  python Utils/mapas_espaciales.py --variable temperature --unidades '°C' --cmap inferno\n"
               "  python Utils/mapas_espaciales.py --variable ghi --agregacion suma_diaria --factor 0.001 --unidades 'kWh/m²/día'\n"
               "  python Utils/mapas_espaciales.py --variable ghi --filtro mensual --mes 6 --unidades 'W/m²'\n"
               "  python Utils/mapas_espaciales.py --variable wind_speed --filtro diario --dia 2017-06-21 --unidades m/s\n"
               "  python Utils/mapas_espaciales.py --variable temperature --panel12 --unidades '°C' --cmap inferno")
    ap.add_argument('--variable', default='ghi', help="Columna del dataset (def: ghi).")
    ap.add_argument('--filtro', default='anual', choices=['anual', 'mensual', 'diario'])
    ap.add_argument('--mes', type=int, choices=range(1, 13), metavar='1-12')
    ap.add_argument('--dia', type=str, metavar='YYYY-MM-DD')
    ap.add_argument('--agregacion', default='media', choices=['media', 'suma_diaria', 'max', 'min'])
    ap.add_argument('--factor', type=float, default=1.0)
    ap.add_argument('--titulo', type=str, default=None, help="Nombre legible de la variable.")
    ap.add_argument('--unidades', type=str, default='')
    ap.add_argument('--cmap', type=str, default=None,
                    help="Paleta matplotlib. Si se omite, se elige una intuitiva por variable.")
    ap.add_argument('--panel12', action='store_true', help="Genera el panel 4x3 de los 12 meses.")
    args = ap.parse_args()

    m = MapaEspacial()
    if args.panel12:
        m.mapa_12_meses(args.variable, agregacion=args.agregacion, factor=args.factor,
                        titulo_var=args.titulo, unidades=args.unidades, cmap=args.cmap)
    else:
        m.mapa(args.variable, filtro=args.filtro, mes=args.mes, dia=args.dia,
               agregacion=args.agregacion, factor=args.factor, titulo_var=args.titulo,
               unidades=args.unidades, cmap=args.cmap)


if __name__ == "__main__":
    _cli()
