"""
analizador_datos.py
===================

Herramienta de análisis exploratorio y de integridad para los datasets NSRDB
consolidados (parquet de 24 h) de Tamaulipas / Puerto Rico.

Pensada como compañera de `mapas_espaciales.MapaEspacial`: mientras aquella se
ocupa de la dimensión ESPACIAL (un valor por nodo sobre el mapa), esta clase
(`AnalizadorSolar`) cubre todo lo demás:

  - Lectura de un parquet CONSOLIDADO (año completo) o INDIVIDUAL (un trozo),
    con carga perezosa y *predicate pushdown* (solo lee del disco lo filtrado).
  - Filtros componibles: por nodo(s), mes, día, hora, rango de fechas, solo
    horas diurnas, tipo de nube, o `query` libre de pandas.
  - Estadísticas: `describe` por variable, resumen por nodo, conteos de flags.
  - Extracción de subconjuntos: nodos concretos o filas bajo condiciones.
  - INTEGRIDAD de los datos: completitud (filas esperadas vs reales),
    duplicados, timestamps faltantes, nulos, valores fuera de rango físico,
    % de datos rellenados (`fill_flag`), anomalías (GHI>clearsky, GHI/DNI=0 de
    día), y la distribución de las banderas de calidad.
  - Gráficas: histograma, serie temporal, correlaciones (heatmap),
    perfil diario medio, barras de flags y mapa de completitud por nodo.

Diseñada para usarse cómodamente en NOTEBOOK (los métodos de gráfica devuelven
el `Figure`, que el notebook renderiza solo) y también en CONSOLA / scripts
(pasando `guardar='ruta.png'` se escribe el PNG, y hay una CLI al final).

Uso rápido (Python / notebook)
------------------------------
    from Utils.analizador_datos import AnalizadorSolar
    a = AnalizadorSolar(anio=2024)            # usa el parquet consolidado del año

    a.info()                                  # qué hay dentro (columnas, nodos, fechas)
    a.integridad()                            # informe de calidad completo
    a.integridad(graficar=True)               # + gráficas de flags y completitud

    a.estadisticas(['ghi', 'temperature'])    # describe de esas variables
    a.resumen_nodos('ghi')                    # media/min/max de GHI por nodo

    df = a.filtrar(nodos=[0, 1, 2], mes=2, solo_diurno=True)   # subconjunto
    a.histograma('ghi', solo_diurno=True)
    a.serie_temporal('ghi', nodos=0, dia='2024-02-29')
    a.correlaciones(['ghi', 'dni', 'temperature', 'relative_humidity'])
    a.perfil_diario('ghi', mes=6)

Uso rápido (línea de comandos)
------------------------------
    python Utils/analizador_datos.py --anio 2024 --info
    python Utils/analizador_datos.py --anio 2024 --integridad
    python Utils/analizador_datos.py --anio 2024 --estadisticas ghi dni temperature
    python Utils/analizador_datos.py --anio 2024 --histograma ghi --solo-diurno --guardar hist_ghi.png
    python Utils/analizador_datos.py --anio 2024 --serie ghi --nodos 0 --dia 2024-02-29 --guardar serie.png
    python Utils/analizador_datos.py --anio 2024 --correlaciones ghi dni temperature --guardar corr.png
    python Utils/analizador_datos.py --parquet ruta/al/archivo.parquet --info
"""

import os
import time
import argparse
import numpy as np
import pandas as pd
import pyarrow.parquet as pq
import matplotlib.pyplot as plt

# --------------------------------------------------------------------------- #
# Diccionarios y metadatos del NSRDB (ver Data/Tamaulipas/REFERENCIA_NSRDB.md)
# --------------------------------------------------------------------------- #
MESES_ES = ['', 'Enero', 'Febrero', 'Marzo', 'Abril', 'Mayo', 'Junio', 'Julio',
            'Agosto', 'Septiembre', 'Octubre', 'Noviembre', 'Diciembre']

CLOUD_TYPE = {0: 'Clear', 1: 'Probably Clear', 2: 'Fog', 3: 'Water',
              4: 'Super-Cooled Water', 5: 'Mixed', 6: 'Opaque Ice', 7: 'Cirrus',
              8: 'Overlapping', 9: 'Overshooting', 10: 'Unknown', 11: 'Dust',
              12: 'Smoke', -15: 'Sin dato'}

# Unidades por variable (para títulos y ejes).
UNIDADES = {
    'ghi': 'W/m²', 'dni': 'W/m²', 'dhi': 'W/m²',
    'clearsky_ghi': 'W/m²', 'clearsky_dni': 'W/m²', 'clearsky_dhi': 'W/m²',
    'ghi_uv_280_400': 'W/m²', 'ghi_uv_295_385': 'W/m²',
    'temperature': '°C', 'dew_point': '°C', 'pressure': 'mbar',
    'relative_humidity': '%', 'precipitable_water': 'cm',
    'wind_speed': 'm/s', 'wind_direction': '°', 'solar_zenith_angle': '°',
    'surface_albedo': '', 'aerosol_optical_depth': '', 'alpha': '',
    'asymmetry': '', 'ssa': '', 'ozone': 'atm-cm',
    'kt': '',   # índice de claridad (derivado): ghi / clearsky_ghi
}

# Rangos físicos plausibles para detectar valores imposibles en `integridad`.
# (None = sin límite por ese lado).
RANGOS_FISICOS = {
    'ghi': (0, 1500), 'dni': (0, 1200), 'dhi': (0, 1200),
    'clearsky_ghi': (0, 1500), 'clearsky_dni': (0, 1200), 'clearsky_dhi': (0, 1200),
    'temperature': (-40, 60), 'dew_point': (-50, 45),
    'relative_humidity': (0, 100), 'pressure': (700, 1100),
    'precipitable_water': (0, 10), 'wind_speed': (0, 80),
    'wind_direction': (0, 360), 'solar_zenith_angle': (0, 180),
    'surface_albedo': (0, 1),
}

# Columnas que NO son variables analizables (claves / tiempo).
_CLAVES = ('nodo_id', 'datetime', 'year', 'month', 'day', 'hour')
_FLAGS = ('cloud_type', 'cloud_fill_flag', 'fill_flag')

# Tolerancia (mbar) alrededor de la presión esperada por altitud, para el chequeo
# de presión calibrado por elevación (ver `presion_barometrica`).
TOL_PRESION_MBAR = 60.0


def presion_barometrica(altitud_m):
    """
    Presión atmosférica de superficie esperada (mbar) según la altitud (m),
    por la fórmula barométrica de la atmósfera estándar internacional (ISA).
    Acepta escalar o array/serie. Sirve para calibrar el rango físico de
    `pressure` por nodo: a 0 m ≈ 1013 mbar, a 2000 m ≈ 795, a 3000 m ≈ 701.
    """
    h = np.asarray(altitud_m, dtype='float64')
    return 1013.25 * (1.0 - 2.25577e-5 * h) ** 5.25588


class AnalizadorSolar:
    """
    Análisis exploratorio y de integridad de un parquet NSRDB consolidado.

    Parameters
    ----------
    parquet : str, opcional
        Ruta a un parquet (consolidado del año o individual). Si se omite, se
        arma con `region`/`anio` apuntando al consolidado estándar del proyecto.
    metadata : str, opcional
        CSV con `nodo_id, latitude, longitude, ...`. Si se omite, el estándar de
        la región. Se usa para los mapas de completitud (opcional).
    anio : int
        Año del consolidado estándar (default 2024).
    region : str
        Región del consolidado estándar (default 'Tamaulipas').

    Notas
    -----
    - La carga es perezosa: nada se lee hasta el primer método que lo necesita.
    - Los filtros baratos (nodo, año, mes, día, hora) se empujan a pyarrow para
      leer del disco SOLO lo necesario; el resto se aplica en memoria.
    - Los métodos de gráfica devuelven el `matplotlib.figure.Figure` (el
      notebook lo muestra solo). Pasa `guardar='ruta.png'` para escribirlo.
    """

    PLANTILLA = ('Data/{region}/{anio}/Finales/completo/'
                 'dataset_{region_low}_completo_24h_{anio}.parquet')
    META_PLANTILLA = 'Data/{region}/metadata_nodos_{region_low}.csv'

    def __init__(self, parquet=None, metadata=None, anio=2024, region='Tamaulipas',
                 usar_cache=True, cache_max=4, tol_presion=TOL_PRESION_MBAR):
        self.anio = anio
        self.region = region
        rl = region.lower()
        self.parquet = parquet or self.PLANTILLA.format(
            region=region, region_low=rl, anio=anio)
        self.metadata = metadata or self.META_PLANTILLA.format(
            region=region, region_low=rl)
        if not os.path.exists(self.parquet):
            raise FileNotFoundError(f"No existe el parquet: {self.parquet}")

        # Esquema (columnas y tipos) sin leer los datos.
        self._pf = pq.ParquetFile(self.parquet)
        self.columnas = [c.name for c in self._pf.schema_arrow]
        self._meta = None          # cache perezosa de coordenadas
        self._elev = None          # cache perezosa de elevación por nodo
        self.tol_presion = tol_presion

        # Caché de lectura: una entrada por firma de filtro pyarrow, con las
        # columnas crudas leídas hasta el momento (las llamadas posteriores con
        # el mismo filtro reutilizan la lectura aunque pidan otras columnas).
        self.usar_cache = usar_cache
        self.cache_max = cache_max
        self._cache = {}

    # ===================================================================== #
    # Introspección
    # ===================================================================== #
    @property
    def variables(self):
        """Columnas numéricas analizables (sin claves ni flags)."""
        return [c for c in self.columnas if c not in _CLAVES + _FLAGS]

    @property
    def meta(self):
        """Coordenadas de los nodos (perezoso). None si no hay CSV."""
        if self._meta is None and os.path.exists(self.metadata):
            self._meta = pd.read_csv(
                self.metadata, usecols=lambda c: c in
                ('nodo_id', 'latitude', 'longitude'))
        return self._meta

    @property
    def elev(self):
        """Mapa {nodo_id: msnm} (perezoso). None si la metadata no trae `msnm`."""
        if self._elev is None and os.path.exists(self.metadata):
            cols = pd.read_csv(self.metadata, nrows=0).columns
            if 'msnm' in cols and 'nodo_id' in cols:
                e = pd.read_csv(self.metadata, usecols=['nodo_id', 'msnm'])
                self._elev = e.set_index('nodo_id')['msnm']
        return self._elev

    def limpiar_cache(self):
        """Vacía la caché de lectura (libera memoria)."""
        self._cache.clear()

    def info(self):
        """Imprime un resumen del contenido del parquet y lo devuelve como dict."""
        md = self._pf.metadata
        n_filas = md.num_rows
        tam_mb = os.path.getsize(self.parquet) / 1e6
        # Lee solo claves para conocer nodos y rango temporal (barato).
        claves = pd.read_parquet(self.parquet,
                                 columns=['nodo_id', 'datetime', 'month', 'day'])
        n_nodos = claves['nodo_id'].nunique()
        dias = claves[['month', 'day']].drop_duplicates()
        fmin, fmax = claves['datetime'].min(), claves['datetime'].max()

        print(f"=== {os.path.basename(self.parquet)} ===")
        print(f"  Tamaño en disco : {tam_mb:,.1f} MB")
        print(f"  Filas           : {n_filas:,}")
        print(f"  Nodos           : {n_nodos:,}")
        print(f"  Días distintos  : {len(dias)}")
        print(f"  Rango temporal  : {fmin}  ->  {fmax}")
        print(f"  Columnas ({len(self.columnas)}):")
        for c in self.columnas:
            u = UNIDADES.get(c, '')
            etq = 'FLAG' if c in _FLAGS else ('clave' if c in _CLAVES else u or '—')
            print(f"      {c:24s} {etq}")
        return {'archivo': self.parquet, 'tam_mb': tam_mb, 'filas': n_filas,
                'nodos': n_nodos, 'dias': len(dias),
                'fecha_min': fmin, 'fecha_max': fmax}

    # ===================================================================== #
    # Filtrado / extracción
    # ===================================================================== #
    def filtrar(self, columnas=None, nodos=None, mes=None, dia=None, hora=None,
                rango_fechas=None, solo_diurno=False, cloud_type=None,
                query=None, con_kt=False, zenith_max=90.0):
        """
        Devuelve un DataFrame filtrado leyendo del disco solo lo necesario.

        Parameters
        ----------
        columnas : list[str], opcional
            Columnas a traer (además siempre se incluyen las claves usadas por
            los filtros). Acepta la variable DERIVADA ``'kt'`` (índice de
            claridad = ghi/clearsky_ghi). None = todas.
        con_kt : bool
            Añade la columna ``kt`` aunque no esté en `columnas`.
        nodos : int | list[int], opcional
            Nodo o lista de nodos (`nodo_id`).
        mes : int | list[int], opcional         Mes(es) 1-12.
        dia : int | str | list, opcional
            Día del mes (int) o fecha 'YYYY-MM-DD' / 'MM-DD'. Si es fecha, fija
            también el mes.
        hora : int | list[int], opcional        Hora(s) UTC 0-23.
        rango_fechas : (str, str), opcional      ('YYYY-MM-DD', 'YYYY-MM-DD').
        solo_diurno : bool
            Conserva solo horas con sol sobre el horizonte
            (`solar_zenith_angle < zenith_max`).
        cloud_type : int | list[int], opcional   Filtra por código de nube.
        query : str, opcional
            Expresión `DataFrame.query` aplicada al final (filtros avanzados,
            p.ej. "ghi > 800 and relative_humidity < 50").
        zenith_max : float
            Umbral de día/noche (default 90°).

        Returns
        -------
        pandas.DataFrame
        """
        filtros = []          # predicados pyarrow (pushdown)
        if nodos is not None:
            filtros.append(('nodo_id', 'in', self._aslist(nodos)))
        if mes is not None and dia is None:
            filtros.append(('month', 'in', self._aslist(mes)))
        if hora is not None:
            filtros.append(('hour', 'in', self._aslist(hora)))
        if dia is not None:
            mm, dd = self._parsear_dia(dia)
            if mm is not None:
                filtros.append(('month', '==', mm))
            filtros.append(('day', 'in', self._aslist(dd)))
        if rango_fechas is not None:
            ini, fin = pd.to_datetime(rango_fechas[0]), pd.to_datetime(rango_fechas[1])
            filtros += [('datetime', '>=', ini), ('datetime', '<=', fin)]

        # `kt` es derivada: requiere ghi y clearsky_ghi del disco.
        pedir_kt = con_kt or (columnas is not None and 'kt' in columnas)

        # Columnas crudas que hay que leer del disco (las pedidas, menos `kt`,
        # más las que necesitan los filtros posteriores y el cálculo de kt).
        cols = None
        if columnas is not None:
            cols = list(dict.fromkeys(
                [c for c in columnas if c != 'kt']
                + (['ghi', 'clearsky_ghi'] if pedir_kt else [])
                + (['solar_zenith_angle'] if solo_diurno else [])
                + (['cloud_type'] if cloud_type is not None else [])))

        raw = self._leer_crudo(filtros, cols)

        # Trabaja sobre copias para no mutar la entrada cacheada.
        df = raw
        if solo_diurno and 'solar_zenith_angle' in df.columns:
            df = df[df['solar_zenith_angle'] < zenith_max]
        if cloud_type is not None and 'cloud_type' in df.columns:
            df = df[df['cloud_type'].isin(self._aslist(cloud_type))]
        if pedir_kt:
            df = df.copy()           # evita SettingWithCopy y mutar la caché
            # Índice de claridad: definido solo de día (clearsky_ghi > 0).
            df['kt'] = np.where(df['clearsky_ghi'] > 0,
                                df['ghi'] / df['clearsky_ghi'], np.nan)
        if query:
            df = df.query(query)
        if columnas is not None:
            keep = list(columnas)
            if pedir_kt and 'kt' not in keep:   # con_kt añade kt aunque no se liste
                keep.append('kt')
            df = df[keep]                        # devuelve solo lo pedido (+ kt)
        return df.reset_index(drop=True)

    def _leer_crudo(self, filtros, cols):
        """
        Lee del parquet aplicando los predicados pyarrow `filtros`, con caché.
        Devuelve el DataFrame crudo (sin filtros pandas posteriores). Si la caché
        está activa, reutiliza la lectura previa de la misma firma de filtro y
        solo lee del disco las columnas que falten.
        """
        if not self.usar_cache:
            return pd.read_parquet(self.parquet, columns=cols, filters=filtros or None)

        clave = self._firma_filtros(filtros)
        quiere = None if cols is None else list(dict.fromkeys(cols))
        cacheado = self._cache.pop(clave, None)   # pop+reinsert = LRU

        if cacheado is not None:
            tiene_todo = (quiere is None and
                          set(self.columnas) <= set(cacheado.columns)) or \
                         (quiere is not None and set(quiere) <= set(cacheado.columns))
            if tiene_todo:
                self._cache[clave] = cacheado
                return cacheado
            # Faltan columnas: lee solo las que faltan y las concatena (las
            # lecturas con el mismo filtro conservan el orden de filas).
            faltan = (None if quiere is None
                      else [c for c in quiere if c not in cacheado.columns])
            extra = pd.read_parquet(self.parquet, columns=faltan,
                                    filters=filtros or None)
            nuevo = pd.concat([cacheado.reset_index(drop=True),
                               extra.reset_index(drop=True)], axis=1)
            nuevo = nuevo.loc[:, ~nuevo.columns.duplicated()]
        else:
            nuevo = pd.read_parquet(self.parquet, columns=quiere,
                                    filters=filtros or None)

        self._cache[clave] = nuevo
        while len(self._cache) > self.cache_max:           # evict más antiguo
            self._cache.pop(next(iter(self._cache)))
        return nuevo

    @staticmethod
    def _firma_filtros(filtros):
        """Firma hashable y canónica de la lista de predicados pyarrow."""
        norm = [(c, op, tuple(v) if isinstance(v, list) else v)
                for c, op, v in filtros]
        return tuple(sorted(norm, key=lambda x: (x[0], x[1], repr(x[2]))))

    def nodos(self):
        """Lista ordenada de `nodo_id` presentes en el dataset."""
        return sorted(pd.read_parquet(self.parquet, columns=['nodo_id'])
                      ['nodo_id'].unique().tolist())

    def decodificar(self, df):
        """Agrega columnas legibles `cloud_type_desc` y `relleno` (fill_flag!=0)."""
        out = df.copy()
        if 'cloud_type' in out:
            out['cloud_type_desc'] = out['cloud_type'].map(CLOUD_TYPE)
        if 'fill_flag' in out:
            out['relleno'] = out['fill_flag'] != 0
        return out

    # ===================================================================== #
    # Estadísticas
    # ===================================================================== #
    def estadisticas(self, variables=None, percentiles=(.05, .25, .5, .75, .95),
                     **filtros):
        """
        `describe` (con percentiles) de las variables indicadas tras aplicar
        filtros. `variables=None` usa todas las numéricas.

        Acepta los mismos parámetros de filtro que `filtrar`.
        """
        variables = self._aslist(variables) if variables else self.variables
        df = self.filtrar(columnas=variables, **filtros)
        desc = df[variables].describe(percentiles=list(percentiles)).T
        desc['nulos'] = df[variables].isna().sum()
        desc['%nulos'] = (desc['nulos'] / len(df) * 100).round(2)
        return desc

    def resumen_nodos(self, variable, agg=('mean', 'std', 'min', 'max'),
                      con_coords=True, **filtros):
        """
        Estadísticos de `variable` agregados POR nodo (un renglón por `nodo_id`).
        Útil para detectar nodos atípicos. Une coordenadas si hay metadata.
        """
        df = self.filtrar(columnas=['nodo_id', variable], **filtros)
        res = df.groupby('nodo_id')[variable].agg(list(agg)).reset_index()
        if con_coords and self.meta is not None:
            res = res.merge(self.meta, on='nodo_id', how='left')
        return res

    def flags(self, **filtros):
        """
        Distribución (conteo y %) de las tres banderas de calidad:
        `cloud_type`, `cloud_fill_flag`, `fill_flag`. Devuelve un dict de
        DataFrames. `cloud_type` viene con su descripción legible.
        """
        df = self.filtrar(columnas=list(_FLAGS), **filtros)
        out = {}
        for c in _FLAGS:
            vc = df[c].value_counts().sort_index()
            tab = pd.DataFrame({'codigo': vc.index, 'conteo': vc.values})
            tab['%'] = (tab['conteo'] / len(df) * 100).round(3)
            if c == 'cloud_type':
                tab['desc'] = tab['codigo'].map(CLOUD_TYPE)
            out[c] = tab
        return out

    # ===================================================================== #
    # Índice de claridad (kt) · comparación inter-anual · exportación
    # ===================================================================== #
    def clasificar_dias(self, por_nodo=False, umbral_despejado=0.65,
                        umbral_cubierto=0.35, graficar=False, guardar=None,
                        **filtros):
        """
        Clasifica cada día según el índice de claridad medio diurno
        ``kt = ghi / clearsky_ghi`` (promediado sobre las horas con sol).

        Categorías (sobre el kt medio del día):
          - 'despejado' : kt >= `umbral_despejado`
          - 'cubierto'  : kt <  `umbral_cubierto`
          - 'parcial'   : entre ambos

        Parameters
        ----------
        por_nodo : bool
            Si True, clasifica por (nodo_id, día); si False, promedia todos los
            nodos y clasifica un valor por día (recurso medio de la región).
        graficar : bool
            Dibuja la serie diaria de kt coloreada por categoría.

        Returns
        -------
        pandas.DataFrame con kt_medio y categoria.
        """
        cols = ['nodo_id', 'datetime', 'month', 'day']
        df = self.filtrar(columnas=cols, con_kt=True, solo_diurno=True, **filtros)
        claves = (['nodo_id', 'month', 'day'] if por_nodo else ['month', 'day'])
        res = (df.groupby(claves)['kt'].mean().reset_index()
               .rename(columns={'kt': 'kt_medio'}))
        res['categoria'] = np.select(
            [res['kt_medio'] >= umbral_despejado,
             res['kt_medio'] < umbral_cubierto],
            ['despejado', 'cubierto'], default='parcial')

        if not por_nodo:
            res['fecha'] = pd.to_datetime(dict(year=self.anio, month=res['month'],
                                               day=res['day']))
            res = res.sort_values('fecha').reset_index(drop=True)
            print("Días por categoría:",
                  res['categoria'].value_counts().to_dict())
            if graficar:
                colores = {'despejado': '#d95f02', 'parcial': '#7570b3',
                           'cubierto': '#1b9e77'}
                fig, ax = plt.subplots(figsize=(13, 4.5))
                ax.scatter(res['fecha'], res['kt_medio'], s=18,
                           c=res['categoria'].map(colores))
                ax.axhline(umbral_despejado, ls='--', color='#d95f02', lw=1)
                ax.axhline(umbral_cubierto, ls='--', color='#1b9e77', lw=1)
                ax.set_ylabel("kt medio diario")
                ax.set_xlabel("Fecha")
                ax.set_title(f"Índice de claridad diario — {self.region} {self.anio}")
                ax.grid(alpha=.3)
                from matplotlib.patches import Patch
                ax.legend(handles=[Patch(color=v, label=k)
                                   for k, v in colores.items()], loc='lower left')
                self._finalizar(fig, guardar)
        return res

    def comparar(self, otros, variable='ghi', por='mes', agregacion='mean',
                 graficar=False, guardar=None, **filtros):
        """
        Compara `variable` entre este año y otro(s) año(s).

        Parameters
        ----------
        otros : int | list[int] | AnalizadorSolar | list[AnalizadorSolar]
            Año(s) a comparar contra `self` (se construye el analizador del año
            con la misma región/rutas) o instancias ya creadas.
        variable : str
            Columna a comparar (acepta 'kt').
        por : {'mes', 'nodo', 'total'}
            'mes'   -> una fila por mes, una columna por año (+ comparable).
            'nodo'  -> una fila por nodo con el valor de cada año y su delta.
            'total' -> un único valor agregado por año.
        agregacion : {'mean','sum','max','min'}
        graficar : bool
            'mes' -> líneas por año; 'nodo' -> histograma de deltas.

        Returns
        -------
        pandas.DataFrame
        """
        analizadores = {self.anio: self}
        for o in self._aslist(otros):
            if isinstance(o, AnalizadorSolar):
                analizadores[o.anio] = o
            else:
                analizadores[int(o)] = AnalizadorSolar(
                    anio=int(o), region=self.region)
        anios = sorted(analizadores)
        usa_kt = (variable == 'kt')

        # Agrupación por año.
        partes = {}
        for an, az in analizadores.items():
            grp = ['month'] if por == 'mes' else (['nodo_id'] if por == 'nodo' else [])
            df = az.filtrar(columnas=([variable] if not usa_kt else [])
                            + (['month'] if por == 'mes' else [])
                            + (['nodo_id'] if por == 'nodo' else []),
                            con_kt=usa_kt,
                            solo_diurno=usa_kt, **filtros)
            partes[an] = (df[variable].agg(agregacion) if not grp
                          else df.groupby(grp)[variable].agg(agregacion))

        if por == 'total':
            tabla = pd.DataFrame({'anio': anios,
                                  variable: [partes[a] for a in anios]})
            print(tabla.to_string(index=False))
            return tabla

        tabla = pd.concat([partes[a].rename(a) for a in anios], axis=1)
        if por == 'nodo':
            tabla = tabla.reset_index()
            if len(anios) == 2:
                tabla['delta'] = tabla[anios[1]] - tabla[anios[0]]
                tabla['delta_%'] = (tabla['delta'] / tabla[anios[0]] * 100).round(2)
            if self.meta is not None:
                tabla = tabla.merge(self.meta, on='nodo_id', how='left')
        else:  # 'mes'
            tabla.index = [MESES_ES[m] for m in tabla.index]

        if graficar:
            fig, ax = plt.subplots(figsize=(11, 5))
            u = UNIDADES.get(variable, '')
            if por == 'mes':
                for a in anios:
                    ax.plot(range(1, len(tabla) + 1), tabla[a], '-o', label=str(a))
                ax.set_xticks(range(1, len(tabla) + 1))
                ax.set_xticklabels(tabla.index, rotation=45)
                ax.set_ylabel(f"{variable} ({agregacion})" + (f" [{u}]" if u else ""))
                ax.legend(title="Año")
            else:  # nodo: histograma de deltas
                ax.hist(tabla['delta'].dropna(), bins=50, color='#7570b3',
                        edgecolor='white')
                ax.axvline(0, color='k', lw=1)
                ax.set_xlabel(f"Δ {variable} ({anios[1]} − {anios[0]})"
                              + (f" [{u}]" if u else ""))
                ax.set_ylabel("nº de nodos")
            ax.set_title(f"Comparación de {variable} ({agregacion}) por {por} — "
                         f"{self.region} {anios}")
            ax.grid(alpha=.3)
            self._finalizar(fig, guardar)
        return tabla

    def exportar(self, ruta, formato=None, decodificar=False, **filtros):
        """
        Exporta el subconjunto filtrado a CSV / Parquet / Excel / Feather.

        Parameters
        ----------
        ruta : str
            Destino. Si `formato` es None, se infiere por la extensión
            (.csv, .parquet, .xlsx, .feather).
        formato : str, opcional
            Fuerza el formato ('csv', 'parquet', 'excel', 'feather').
        decodificar : bool
            Añade columnas legibles (`cloud_type_desc`, `relleno`).
        **filtros : se pasan a `filtrar` (incluye `columnas`, `con_kt`, etc.).

        Returns
        -------
        str : la ruta escrita.
        """
        df = self.filtrar(**filtros)
        if decodificar:
            df = self.decodificar(df)
        fmt = (formato or os.path.splitext(ruta)[1].lstrip('.')).lower()
        os.makedirs(os.path.dirname(os.path.abspath(ruta)) or '.', exist_ok=True)
        if fmt in ('csv', 'txt'):
            df.to_csv(ruta, index=False)
        elif fmt in ('parquet', 'pq'):
            df.to_parquet(ruta, index=False)
        elif fmt in ('xlsx', 'excel', 'xls'):
            df.to_excel(ruta, index=False)
        elif fmt in ('feather', 'ft'):
            df.to_feather(ruta)
        else:
            raise ValueError(f"Formato no soportado: '{fmt}'")
        print(f"✅ exportado {len(df):,} filas × {df.shape[1]} cols -> {ruta}")
        return ruta

    # ===================================================================== #
    # Integridad
    # ===================================================================== #
    def integridad(self, graficar=False, guardar=None, **filtros):
        """
        Informe de integridad/calidad. Imprime un resumen y devuelve un dict
        con todas las métricas. Con `graficar=True` añade gráficas (barras de
        flags + completitud por nodo).

        Comprueba:
          - completitud  : filas reales vs esperadas (nodos × horas × días)
          - duplicados   : pares (nodo_id, datetime) repetidos
          - faltantes    : nodos con menos horas de las esperadas
          - nulos        : NaN por columna
          - rango físico : valores fuera de `RANGOS_FISICOS`
          - relleno      : % de filas con `fill_flag != 0` (dato interpolado)
          - anomalías    : GHI>clearsky_ghi, y GHI/DNI=0 en horas diurnas
        """
        t0 = time.time()
        cols = ['nodo_id', 'datetime', 'month', 'day', 'hour',
                'ghi', 'dni', 'clearsky_ghi', 'solar_zenith_angle'] + list(_FLAGS)
        cols += [c for c in RANGOS_FISICOS if c in self.columnas and c not in cols]
        cols = [c for c in dict.fromkeys(cols) if c in self.columnas]
        df = self.filtrar(columnas=cols, **filtros)
        n = len(df)
        rep = {}

        # -- completitud -------------------------------------------------- #
        n_nodos = df['nodo_id'].nunique()
        n_dias = df[['month', 'day']].drop_duplicates().shape[0]
        n_horas = df['hour'].nunique()
        esperadas = n_nodos * n_dias * n_horas
        rep['completitud'] = {
            'filas': n, 'esperadas': esperadas,
            'faltan': esperadas - n,
            'pct': round(n / esperadas * 100, 4) if esperadas else float('nan'),
            'nodos': n_nodos, 'dias': n_dias, 'horas_dia': n_horas}

        # -- duplicados --------------------------------------------------- #
        dup = int(df.duplicated(['nodo_id', 'datetime']).sum())
        rep['duplicados'] = dup

        # -- nodos incompletos ------------------------------------------- #
        por_nodo = df.groupby('nodo_id').size()
        esp_nodo = n_dias * n_horas
        incompletos = por_nodo[por_nodo != esp_nodo]
        rep['nodos_incompletos'] = incompletos.to_dict()

        # -- nulos -------------------------------------------------------- #
        nulos = df.isna().sum()
        rep['nulos'] = nulos[nulos > 0].to_dict()

        # -- fuera de rango físico --------------------------------------- #
        fuera = {}
        for c in RANGOS_FISICOS:
            if c not in df.columns:
                continue
            n_mal = int(self._mascara_fuera_rango(df, c).sum())
            if n_mal:
                fuera[c] = n_mal
        rep['fuera_de_rango'] = fuera

        # -- relleno (fill_flag) ----------------------------------------- #
        rel = int((df['fill_flag'] != 0).sum())
        rep['relleno'] = {'filas': rel, 'pct': round(rel / n * 100, 3) if n else 0}

        # -- anomalías físicas ------------------------------------------- #
        diurno = df['solar_zenith_angle'] < 90
        rep['anomalias'] = {
            'ghi_mayor_clearsky': int((df['ghi'] > df['clearsky_ghi']).sum()),
            'ghi_cero_de_dia': int(((df['ghi'] == 0) & diurno).sum()),
            'dni_cero_de_dia': int(((df['dni'] == 0) & diurno).sum()),
            'ghi_negativo': int((df['ghi'] < 0).sum()),
        }

        self._imprimir_integridad(rep, time.time() - t0)

        fig = None
        if graficar:
            fig = self._grafico_integridad(df, guardar)
        rep['_figura'] = fig
        return rep

    def _imprimir_integridad(self, r, segs):
        c = r['completitud']
        print(f"========== INTEGRIDAD — {os.path.basename(self.parquet)} ==========")
        print(f"Completitud : {c['filas']:,} / {c['esperadas']:,} filas "
              f"({c['pct']}%)  | nodos={c['nodos']} días={c['dias']} "
              f"horas/día={c['horas_dia']}")
        if c['faltan']:
            print(f"   ⚠ faltan {c['faltan']:,} filas")
        print(f"Duplicados  : {r['duplicados']:,}")
        print(f"Nodos incompletos: {len(r['nodos_incompletos'])}")
        print(f"Relleno (fill_flag!=0): {r['relleno']['filas']:,} "
              f"({r['relleno']['pct']}%)")
        print("Nulos       : " + ("ninguno" if not r['nulos']
                                   else str(r['nulos'])))
        print("Fuera de rango físico: " + ("ninguno" if not r['fuera_de_rango']
                                            else str(r['fuera_de_rango'])))
        a = r['anomalias']
        print("Anomalías físicas:")
        print(f"   GHI > clearsky_ghi : {a['ghi_mayor_clearsky']:,}")
        print(f"   GHI = 0 de día     : {a['ghi_cero_de_dia']:,}")
        print(f"   DNI = 0 de día     : {a['dni_cero_de_dia']:,} "
              f"(normal con cielo cubierto)")
        print(f"   GHI negativo       : {a['ghi_negativo']:,}")
        print(f"⏱ {segs:.1f} s")

    def anomalias(self, limite=1000, **filtros):
        """
        Devuelve las **filas** con anomalías (no solo el conteo, como
        `integridad`), para poder inspeccionarlas. Complementa a `integridad`.

        Parameters
        ----------
        limite : int | None
            Máximo de filas por tipo de anomalía (None = sin tope).
        **filtros : se pasan a `filtrar`.

        Returns
        -------
        dict[str, pandas.DataFrame]
            Una tabla por tipo de anomalía encontrada:
              - 'rango_<col>'        : valores fuera del rango físico de esa columna.
              - 'ghi_mayor_clearsky' : GHI por encima del de cielo despejado.
              - 'ghi_cero_de_dia'    : GHI=0 con el sol sobre el horizonte.
              - 'dni_cero_de_dia'    : DNI=0 de día (suele ser cielo cubierto).
              - 'ghi_negativo'       : GHI < 0.
              - 'duplicados'         : pares (nodo_id, datetime) repetidos.
        """
        base = ['nodo_id', 'datetime', 'ghi', 'dni', 'clearsky_ghi',
                'solar_zenith_angle']
        cols = base + [c for c in RANGOS_FISICOS if c in self.columnas and c not in base]
        cols = [c for c in dict.fromkeys(cols) if c in self.columnas]
        df = self.filtrar(columnas=cols, **filtros)
        diurno = df['solar_zenith_angle'] < 90

        def _cap(d):
            return d if limite is None else d.head(limite)

        out = {}
        for c in RANGOS_FISICOS:
            if c not in df.columns:
                continue
            mal = self._mascara_fuera_rango(df, c)
            if mal.any():
                cc = ['nodo_id', 'datetime', c] + (['solar_zenith_angle']
                                                   if c in ('ghi', 'dni', 'dhi') else [])
                out[f'rango_{c}'] = _cap(df.loc[mal, list(dict.fromkeys(cc))])

        chequeos = {
            'ghi_mayor_clearsky': df['ghi'] > df['clearsky_ghi'],
            'ghi_cero_de_dia': (df['ghi'] == 0) & diurno,
            'dni_cero_de_dia': (df['dni'] == 0) & diurno,
            'ghi_negativo': df['ghi'] < 0,
        }
        for nombre, mask in chequeos.items():
            if mask.any():
                out[nombre] = _cap(df.loc[mask, ['nodo_id', 'datetime', 'ghi', 'dni',
                                                 'clearsky_ghi', 'solar_zenith_angle']])
        dup = df[df.duplicated(['nodo_id', 'datetime'], keep=False)]
        if len(dup):
            out['duplicados'] = _cap(dup.sort_values(['nodo_id', 'datetime']))

        print(f"===== ANOMALÍAS — {os.path.basename(self.parquet)} =====")
        if not out:
            print("  Ninguna anomalía detectada.")
        for nombre, tab in out.items():
            tope = '' if limite is None or len(tab) < limite else f" (primeras {limite})"
            print(f"  {nombre:22s}: {len(tab):>8,} filas{tope}")
        return out

    # ===================================================================== #
    # Gráficas
    # ===================================================================== #
    def histograma(self, variable, bins=60, solo_diurno=False, guardar=None,
                   **filtros):
        """Histograma de `variable` (con filtros). Devuelve el Figure."""
        df = self.filtrar(columnas=[variable], solo_diurno=solo_diurno, **filtros)
        serie = df[variable].dropna()
        fig, ax = plt.subplots(figsize=(9, 5))
        ax.hist(serie, bins=bins, color='#2c7fb8', edgecolor='white', alpha=.85)
        u = UNIDADES.get(variable, '')
        ax.set_xlabel(f"{variable}" + (f" ({u})" if u else ""))
        ax.set_ylabel("Frecuencia")
        ax.set_title(f"Histograma de {variable} — {self.region} {self.anio}"
                     + ("  (solo diurno)" if solo_diurno else ""))
        ax.axvline(serie.mean(), color='crimson', ls='--', lw=1.5,
                   label=f"media={serie.mean():.1f}")
        ax.axvline(serie.median(), color='orange', ls=':', lw=1.5,
                   label=f"mediana={serie.median():.1f}")
        ax.legend()
        ax.grid(alpha=.3)
        return self._finalizar(fig, guardar)

    def serie_temporal(self, variable, nodos=None, agregacion='mean',
                       guardar=None, **filtros):
        """
        Serie temporal de `variable`. Si se pasan varios `nodos` se promedian
        (o según `agregacion`: 'mean'/'min'/'max'); si se pasa uno, es ese nodo.
        Devuelve el Figure.
        """
        df = self.filtrar(columnas=['datetime', 'nodo_id', variable],
                          nodos=nodos, **filtros)
        serie = df.groupby('datetime')[variable].agg(agregacion)
        fig, ax = plt.subplots(figsize=(13, 4.5))
        ax.plot(serie.index, serie.values, lw=.8, color='#1b9e77')
        u = UNIDADES.get(variable, '')
        ax.set_ylabel(f"{variable}" + (f" ({u})" if u else ""))
        ax.set_xlabel("Fecha (UTC)")
        etq_nodo = ('todos los nodos' if nodos is None
                    else f"nodo(s) {nodos}")
        ax.set_title(f"Serie temporal de {variable} ({agregacion}) — {etq_nodo}")
        ax.grid(alpha=.3)
        fig.autofmt_xdate()
        return self._finalizar(fig, guardar)

    def perfil_diario(self, variable, agregacion='mean', guardar=None, **filtros):
        """Perfil horario medio (0-23 h): `variable` promediada por hora del día."""
        df = self.filtrar(columnas=['hour', variable], **filtros)
        perfil = df.groupby('hour')[variable].agg(['mean', 'std'])
        fig, ax = plt.subplots(figsize=(9, 5))
        ax.plot(perfil.index, perfil['mean'], '-o', color='#d95f02', lw=2)
        ax.fill_between(perfil.index, perfil['mean'] - perfil['std'],
                        perfil['mean'] + perfil['std'], alpha=.2, color='#d95f02')
        u = UNIDADES.get(variable, '')
        ax.set_xlabel("Hora del día (UTC)")
        ax.set_ylabel(f"{variable}" + (f" ({u})" if u else ""))
        ax.set_title(f"Perfil diario medio de {variable} — {self.region} {self.anio}")
        ax.set_xticks(range(0, 24, 2))
        ax.grid(alpha=.3)
        return self._finalizar(fig, guardar)

    def correlaciones(self, variables=None, metodo='pearson', guardar=None,
                      **filtros):
        """Heatmap de correlaciones entre `variables` (default: todas)."""
        variables = self._aslist(variables) if variables else self.variables
        df = self.filtrar(columnas=variables, **filtros)
        corr = df[variables].corr(method=metodo)
        fig, ax = plt.subplots(figsize=(1 + .7 * len(variables),
                                        1 + .6 * len(variables)))
        im = ax.imshow(corr, cmap='RdBu_r', vmin=-1, vmax=1)
        ax.set_xticks(range(len(variables)))
        ax.set_yticks(range(len(variables)))
        ax.set_xticklabels(variables, rotation=90, fontsize=8)
        ax.set_yticklabels(variables, fontsize=8)
        for i in range(len(variables)):
            for j in range(len(variables)):
                ax.text(j, i, f"{corr.iloc[i, j]:.2f}", ha='center', va='center',
                        fontsize=7, color='black')
        fig.colorbar(im, ax=ax, fraction=0.046, pad=0.04, label=f"corr ({metodo})")
        ax.set_title(f"Correlaciones — {self.region} {self.anio}")
        return self._finalizar(fig, guardar)

    def _grafico_integridad(self, df, guardar):
        """Panel: distribución de las 3 flags + completitud por nodo."""
        fig, axes = plt.subplots(2, 2, figsize=(14, 9))
        for ax, c in zip(axes.flat[:3], _FLAGS):
            vc = df[c].value_counts().sort_index()
            ax.bar([str(i) for i in vc.index], vc.values, color='#7570b3')
            ax.set_title(f"Distribución de {c}")
            ax.set_ylabel("filas")
            ax.tick_params(axis='x', rotation=45, labelsize=8)
        # Completitud por nodo (filas por nodo).
        ax = axes.flat[3]
        por_nodo = df.groupby('nodo_id').size()
        ax.hist(por_nodo.values, bins=40, color='#1b9e77', edgecolor='white')
        ax.set_title("Filas por nodo (completitud)")
        ax.set_xlabel("nº de filas en el nodo")
        ax.set_ylabel("nº de nodos")
        fig.suptitle(f"Integridad — {os.path.basename(self.parquet)}",
                     fontsize=14, fontweight='bold')
        fig.tight_layout()
        return self._finalizar(fig, guardar)

    # ===================================================================== #
    # Agregados temporales · curva de duración · outliers · viento · estacionalidad
    # ===================================================================== #
    def resamplear(self, variable, frecuencia='D', agregacion='mean', factor=1.0,
                   por_nodo=False, graficar=False, guardar=None, **filtros):
        """
        Agrega `variable` a una frecuencia temporal (horaria/diaria/mensual).

        Parameters
        ----------
        frecuencia : {'H','D','M'}   Hora, día o mes.
        agregacion : {'mean','sum','max','min'}
            Para INSOLACIÓN (kWh/m²/día): variable='ghi', frecuencia='D',
            agregacion='sum', factor=1/1000.
        factor : float              Multiplica el resultado (conversión de unidades).
        por_nodo : bool
            Si True devuelve una serie por nodo; si False promedia entre nodos.
        graficar : bool             Dibuja la serie resultante (si no es por_nodo).

        Returns
        -------
        pandas.DataFrame con columnas [periodo, (nodo_id), variable].
        """
        usa_kt = (variable == 'kt')
        df = self.filtrar(columnas=['nodo_id', 'datetime'] + ([variable] if not usa_kt else []),
                          con_kt=usa_kt, **filtros)
        freq = {'H': 'h', 'D': 'D', 'M': 'MS'}.get(frecuencia, frecuencia)
        df['periodo'] = df['datetime'].dt.floor('h').dt.to_period(
            {'h': 'h', 'D': 'D', 'MS': 'M'}[freq]).dt.to_timestamp()
        serie = (df.groupby(['nodo_id', 'periodo'])[variable].agg(agregacion) * factor)
        if por_nodo:
            res = serie.reset_index()
        else:
            res = serie.groupby('periodo').mean().reset_index()
            if graficar:
                u = UNIDADES.get(variable, '')
                fig, ax = plt.subplots(figsize=(13, 4.5))
                ax.plot(res['periodo'], res[variable], '-o', ms=3, lw=1,
                        color='#d95f02')
                ax.set_ylabel(f"{variable} ({agregacion})" + (f" [{u}]" if u else ""))
                ax.set_xlabel("Periodo")
                ax.set_title(f"{variable} {agregacion} ({frecuencia}) — "
                             f"{self.region} {self.anio}")
                ax.grid(alpha=.3)
                fig.autofmt_xdate()
                self._finalizar(fig, guardar)
        return res

    def curva_duracion(self, variable='ghi', solo_diurno=True, graficar=True,
                       guardar=None, **filtros):
        """
        Curva de duración: valores ordenados de mayor a menor frente al % de
        tiempo en que se superan. Estándar para caracterizar el recurso (cuántas
        horas al año se supera cierta irradiancia). Devuelve un DataFrame con
        `valor` y `excedencia_%`.
        """
        df = self.filtrar(columnas=[variable], solo_diurno=solo_diurno, **filtros)
        vals = np.sort(df[variable].dropna().values)[::-1]
        exced = np.arange(1, len(vals) + 1) / len(vals) * 100
        tabla = pd.DataFrame({'valor': vals, 'excedencia_%': exced})
        if graficar:
            u = UNIDADES.get(variable, '')
            fig, ax = plt.subplots(figsize=(9, 5))
            ax.plot(exced, vals, color='#2c7fb8', lw=1.8)
            ax.set_xlabel("% del tiempo en que se supera")
            ax.set_ylabel(f"{variable}" + (f" ({u})" if u else ""))
            ax.set_title(f"Curva de duración de {variable} — {self.region} {self.anio}"
                         + ("  (solo diurno)" if solo_diurno else ""))
            ax.grid(alpha=.3)
            self._finalizar(fig, guardar)
        return tabla

    def outliers_nodos(self, variable, metodo='zscore', umbral=3.0, agg='mean',
                       graficar=False, guardar=None, **filtros):
        """
        Detecta nodos atípicos según el estadístico `agg` de `variable` por nodo.

        Parameters
        ----------
        metodo : {'zscore','iqr'}
            'zscore' -> |valor - media| / desv > `umbral` (def 3).
            'iqr'    -> fuera de [Q1 - k·IQR, Q3 + k·IQR] con k=`umbral` (usa 1.5).
        agg : estadístico por nodo a evaluar ('mean','max','min','std').

        Returns
        -------
        pandas.DataFrame con los nodos marcados como outliers (valor, z/limites,
        coordenadas si hay metadata).
        """
        base = self.resumen_nodos(variable, agg=(agg,), con_coords=True, **filtros)
        v = base[agg]
        if metodo == 'zscore':
            z = (v - v.mean()) / v.std(ddof=0)
            base['zscore'] = z.round(3)
            mask = z.abs() > umbral
            ref = f"|z| > {umbral}"
        elif metodo == 'iqr':
            q1, q3 = v.quantile(.25), v.quantile(.75)
            k = 1.5 if umbral == 3.0 else umbral
            lo, hi = q1 - k * (q3 - q1), q3 + k * (q3 - q1)
            mask = (v < lo) | (v > hi)
            ref = f"fuera de [{lo:.2f}, {hi:.2f}]"
        else:
            raise ValueError("metodo debe ser 'zscore' o 'iqr'")
        out = base[mask].copy()
        print(f"Outliers de {variable} ({agg}) por nodo [{metodo}: {ref}]: "
              f"{len(out)} de {len(base)} nodos")
        if graficar and self.meta is not None:
            fig, ax = plt.subplots(figsize=(9, 11))
            ax.scatter(base['longitude'], base['latitude'], c=base[agg],
                       cmap='Spectral_r', s=12)
            ax.scatter(out['longitude'], out['latitude'], facecolors='none',
                       edgecolors='red', s=60, lw=1.5, label='outlier')
            ax.set_title(f"Nodos atípicos de {variable} ({agg}) — {self.region} {self.anio}")
            ax.set_xlabel("Longitud"); ax.set_ylabel("Latitud")
            ax.legend(); ax.grid(alpha=.3)
            self._finalizar(fig, guardar)
        return out

    def rosa_viento(self, sectores=16, bins_velocidad=(0, 2, 4, 6, 8, 10),
                    guardar=None, **filtros):
        """
        Rosa de los vientos: frecuencia por dirección (`wind_direction`) y rango
        de velocidad (`wind_speed`). Devuelve el Figure (eje polar).
        """
        df = self.filtrar(columnas=['wind_speed', 'wind_direction'], **filtros)
        fig = plt.figure(figsize=(8, 8))
        ax = fig.add_subplot(111, projection='polar')
        self._rosa_en_eje(ax, df, sectores, bins_velocidad, leyenda=True)
        ax.set_title(f"Rosa de los vientos — {self.region} {self.anio}", pad=20)
        return self._finalizar(fig, guardar)

    def rosa_viento_12meses(self, sectores=16, bins_velocidad=(0, 2, 4, 6, 8, 10),
                            guardar=None, **filtros):
        """
        Panel 4x3 con una rosa de los vientos por mes (al estilo de
        `MapaEspacial.mapa_12_meses`). Devuelve el Figure.
        """
        df = self.filtrar(columnas=['month', 'wind_speed', 'wind_direction'],
                          **filtros)
        fig, axes = plt.subplots(4, 3, figsize=(12, 16),
                                 subplot_kw={'projection': 'polar'})
        for mes in range(1, 13):
            ax = axes[(mes - 1) // 3, (mes - 1) % 3]
            sub = df[df['month'] == mes]
            self._rosa_en_eje(ax, sub, sectores, bins_velocidad,
                              leyenda=(mes == 3))
            ax.set_title(MESES_ES[mes], fontsize=11, fontweight='bold', pad=12)
            ax.set_xticklabels([]); ax.set_yticklabels([])
        fig.suptitle(f"Rosa de los vientos por mes — {self.region} {self.anio}",
                     fontsize=15, fontweight='bold')
        fig.tight_layout(rect=(0, 0, 1, 0.98))
        return self._finalizar(fig, guardar)

    def _rosa_en_eje(self, ax, df, sectores, bins_velocidad, leyenda=False):
        """Dibuja una rosa de los vientos sobre un eje polar ya creado."""
        ancho = 360 / sectores
        # Sector centrado en 0 = Norte; asigna cada dirección a su sector.
        sec = (((df['wind_direction'] % 360) + ancho / 2) // ancho % sectores).astype(int)
        cats = pd.cut(df['wind_speed'], bins=list(bins_velocidad) + [np.inf])
        tabla = pd.crosstab(sec, cats) / max(len(df), 1) * 100   # % del tiempo
        tabla = tabla.reindex(range(sectores), fill_value=0)
        theta = np.deg2rad(tabla.index.values * ancho)
        ax.set_theta_zero_location('N')
        ax.set_theta_direction(-1)
        base = np.zeros(sectores)
        colores = plt.cm.viridis(np.linspace(0, 1, tabla.shape[1]))
        for col, color in zip(tabla.columns, colores):
            ax.bar(theta, tabla[col].values, width=np.deg2rad(ancho), bottom=base,
                   color=color, edgecolor='white', lw=.3, label=str(col))
            base += tabla[col].values
        if leyenda:
            ax.legend(title="m/s", bbox_to_anchor=(1.12, 1.05), fontsize=8)

    def boxplot(self, variable, por='mes', solo_diurno=False, guardar=None,
                **filtros):
        """
        Boxplots de `variable` agrupados por mes (`por='mes'`) o por hora del día
        (`por='hora'`). Muestra mediana, cuartiles y dispersión por grupo.
        """
        clave = 'month' if por == 'mes' else 'hour'
        df = self.filtrar(columnas=[clave, variable], solo_diurno=solo_diurno,
                          **filtros)
        claves = sorted(df[clave].unique())
        grupos = [df.loc[df[clave] == k, variable].dropna().values for k in claves]
        etiquetas = [MESES_ES[k][:3] if por == 'mes' else str(k) for k in claves]
        fig, ax = plt.subplots(figsize=(12, 5))
        # Las etiquetas se ponen con set_xticklabels (no con el kwarg `labels`,
        # deprecado en matplotlib >= 3.9) para ser compatible entre versiones.
        ax.boxplot(grupos, showfliers=False)
        ax.set_xticks(range(1, len(claves) + 1))
        ax.set_xticklabels(etiquetas)
        u = UNIDADES.get(variable, '')
        ax.set_ylabel(f"{variable}" + (f" ({u})" if u else ""))
        ax.set_xlabel("Mes" if por == 'mes' else "Hora del día (UTC)")
        ax.set_title(f"Distribución de {variable} por {por} — {self.region} {self.anio}")
        ax.grid(alpha=.3, axis='y')
        return self._finalizar(fig, guardar)

    def heatmap_mes_hora(self, variable, agregacion='mean', guardar=None,
                         **filtros):
        """
        Mapa de calor mes × hora: estacionalidad y ciclo diario de `variable` en
        una sola imagen (filas=mes, columnas=hora). Devuelve el Figure.
        """
        usa_kt = (variable == 'kt')
        df = self.filtrar(columnas=['month', 'hour'] + ([variable] if not usa_kt else []),
                          con_kt=usa_kt, **filtros)
        tabla = df.pivot_table(index='month', columns='hour', values=variable,
                               aggfunc=agregacion)
        fig, ax = plt.subplots(figsize=(12, 6))
        im = ax.imshow(tabla.values, aspect='auto', cmap='Spectral_r',
                       origin='upper')
        ax.set_xticks(range(len(tabla.columns)))
        ax.set_xticklabels(tabla.columns)
        ax.set_yticks(range(len(tabla.index)))
        ax.set_yticklabels([MESES_ES[m] for m in tabla.index])
        ax.set_xlabel("Hora del día (UTC)")
        ax.set_ylabel("Mes")
        u = UNIDADES.get(variable, '')
        fig.colorbar(im, ax=ax, fraction=0.025, pad=0.02,
                     label=f"{variable} ({agregacion})" + (f" [{u}]" if u else ""))
        ax.set_title(f"{variable} {agregacion} por mes y hora — {self.region} {self.anio}")
        return self._finalizar(fig, guardar)

    # ===================================================================== #
    # Mapas por nodo (recurso e inter-anual) — puente con MapaEspacial
    # ===================================================================== #
    def mapa_recurso(self, variable='ghi', factor=1/1000, unidades='kWh/m²/día',
                     cmap='Spectral_r', guardar=None, **filtros):
        """
        Mapa del recurso solar por nodo: **insolación media diaria** (suma diaria
        de `variable` × `factor`, promediada entre días). Con los valores por
        defecto produce el atlas en kWh/m²/día (variable='ghi', factor=1/1000).

        Necesita metadata con coordenadas. Devuelve el Figure.
        """
        diaria = self.resamplear(variable, frecuencia='D', agregacion='sum',
                                 factor=factor, por_nodo=True, **filtros)
        serie = (diaria.groupby('nodo_id')[variable].mean()
                 .rename('valor').reset_index())
        return self._mapa_nodos(
            serie, cmap=cmap,
            titulo=f"Recurso solar ({variable}) — {self.region} {self.anio}",
            etiqueta_cb=f"{variable} media diaria ({unidades})", guardar=guardar)

    def mapa_delta(self, otro, variable='ghi', agregacion='mean', relativo=False,
                   cmap='RdBu_r', guardar=None, **filtros):
        """
        Mapa de la **diferencia por nodo** de `variable` entre este año y `otro`
        (delta = otro_año_mayor − menor, según `comparar(por='nodo')`).

        Parameters
        ----------
        otro : int | AnalizadorSolar     Año (o instancia) a comparar.
        relativo : bool                  Si True usa `delta_%` en vez del absoluto.
        cmap : str                       Diverging (centrado en 0).

        Devuelve el Figure.
        """
        comp = self.comparar(otro, variable=variable, por='nodo',
                             agregacion=agregacion, **filtros)
        anios = [c for c in comp.columns if isinstance(c, (int, np.integer))]
        col = 'delta_%' if relativo else 'delta'
        serie = comp.rename(columns={col: 'valor'})
        u = '%' if relativo else (UNIDADES.get(variable, '') or '')
        rango = f"{min(anios)}→{max(anios)}"
        return self._mapa_nodos(
            serie, cmap=cmap, centrado_cero=True,
            titulo=f"Δ {variable} ({agregacion}, {rango}) — {self.region}",
            etiqueta_cb=f"Δ {variable}" + (f" ({u})" if u else ""), guardar=guardar)

    def _mapa_nodos(self, serie_nodo, titulo, etiqueta_cb, cmap='Spectral_r',
                    centrado_cero=False, guardar=None, s=14):
        """
        Dibuja un valor por nodo sobre el mapa (scatter geográfico + mapa base
        si hay contextily). `serie_nodo` debe tener columnas `nodo_id` y `valor`
        (y opcionalmente `latitude`/`longitude`; si faltan, se unen de la metadata).
        """
        if self.meta is None:
            raise RuntimeError(
                "No hay metadata con coordenadas; no se puede dibujar el mapa.")
        mapa = serie_nodo.copy()
        if 'longitude' not in mapa.columns or 'latitude' not in mapa.columns:
            mapa = mapa.merge(self.meta, on='nodo_id', how='inner')
        mapa = mapa.dropna(subset=['valor', 'longitude', 'latitude'])

        norm = None
        vmin, vmax = mapa['valor'].min(), mapa['valor'].max()
        if centrado_cero:
            import matplotlib.colors as mcolors
            m = max(abs(vmin), abs(vmax)) or 1.0
            norm = mcolors.TwoSlopeNorm(vmin=-m, vcenter=0, vmax=m)
            vmin = vmax = None

        fig, ax = plt.subplots(figsize=(9, 12))
        sc = ax.scatter(mapa['longitude'], mapa['latitude'], c=mapa['valor'],
                        cmap=cmap, s=s, alpha=.9, edgecolors='none',
                        norm=norm, vmin=vmin, vmax=vmax, zorder=2)
        pad = 0.1
        xlim = (self.meta['longitude'].min() - pad, self.meta['longitude'].max() + pad)
        ylim = (self.meta['latitude'].min() - pad, self.meta['latitude'].max() + pad)
        ax.set_xlim(*xlim); ax.set_ylim(*ylim)
        try:
            import contextily as cx
            cx.add_basemap(ax, crs='EPSG:4326',
                           source=cx.providers.CartoDB.Positron, alpha=.85, zorder=1)
            ax.set_aspect('auto'); ax.set_xlim(*xlim); ax.set_ylim(*ylim)
        except Exception as e:
            print(f"(sin mapa base: {e})")
        plt.colorbar(sc, ax=ax, label=etiqueta_cb, fraction=0.046, pad=0.04)
        ax.set_title(titulo, fontsize=13, fontweight='bold')
        ax.set_xlabel("Longitud"); ax.set_ylabel("Latitud")
        ax.grid(True, linestyle='--', alpha=.3, zorder=3)
        fig.tight_layout()
        return self._finalizar(fig, guardar)

    # ===================================================================== #
    # Informe consolidado
    # ===================================================================== #
    def reporte(self, ruta='informe_analisis.html', variables=None,
                incluir_mapas=True, **filtros):
        """
        Genera un **informe consolidado** (HTML o PDF) con `info` + `integridad`
        + las gráficas clave, en un solo documento reproducible. El formato se
        infiere de la extensión de `ruta` ('.html' o '.pdf').

        Parameters
        ----------
        ruta : str                 Destino ('.html' autocontenido o '.pdf').
        variables : list[str]      Variables para el heatmap de correlaciones.
        incluir_mapas : bool       Añade el mapa del recurso (si hay metadata).
        **filtros : se pasan a todos los cálculos (p.ej. `mes=2` para acotar).

        Notas
        -----
        Es una operación pesada (recorre el dataset varias veces). Para el año
        completo puede tardar minutos; acota con filtros (p.ej. `mes=`) si solo
        quieres una vista rápida.

        Returns
        -------
        str : la ruta del informe escrito.
        """
        import io
        import base64
        import datetime as _dt

        fmt = os.path.splitext(ruta)[1].lower().lstrip('.') or 'html'
        variables = [v for v in (variables or
                     ['ghi', 'dni', 'dhi', 'temperature', 'relative_humidity',
                      'wind_speed']) if v in self.columnas]

        print("Generando informe… (1/3) métricas")
        info = self.info()
        rep = self.integridad(graficar=True, **filtros)
        fig_integ = rep.pop('_figura', None)

        print("Generando informe… (2/3) gráficas")
        figs = [('Integridad: banderas y completitud', fig_integ),
                ('Histograma de GHI (diurno)',
                 self.histograma('ghi', solo_diurno=True, **filtros)),
                ('Perfil diario medio de GHI', self.perfil_diario('ghi', **filtros)),
                ('GHI medio por mes y hora', self.heatmap_mes_hora('ghi', **filtros)),
                ('Correlaciones', self.correlaciones(variables, **filtros))]
        if {'wind_speed', 'wind_direction'} <= set(self.columnas):
            figs.append(('Rosa de los vientos', self.rosa_viento(**filtros)))
        if incluir_mapas and self.meta is not None:
            figs.append(('Recurso solar (insolación media diaria)',
                         self.mapa_recurso(**filtros)))

        print("Generando informe… (3/3) documento")
        titulo = f"Informe de análisis — {self.region} {self.anio}"
        sub = (f"{os.path.basename(self.parquet)} · generado "
               f"{_dt.datetime.now():%Y-%m-%d %H:%M}"
               + (f" · filtros: {filtros}" if filtros else ""))

        if fmt == 'pdf':
            from matplotlib.backends.backend_pdf import PdfPages
            os.makedirs(os.path.dirname(os.path.abspath(ruta)) or '.', exist_ok=True)
            with PdfPages(ruta) as pdf:
                portada = plt.figure(figsize=(8.5, 11))
                portada.text(0.5, 0.93, titulo, ha='center', fontsize=16,
                             fontweight='bold')
                portada.text(0.5, 0.90, sub, ha='center', fontsize=8, color='gray')
                portada.text(0.06, 0.85, self._texto_resumen(info, rep),
                             va='top', family='monospace', fontsize=9)
                pdf.savefig(portada); plt.close(portada)
                for _t, f in figs:
                    if f is not None:
                        pdf.savefig(f); plt.close(f)
            print(f"✅ informe -> {ruta}")
            return ruta

        # HTML autocontenido (figuras embebidas en base64).
        def _b64(fig):
            buf = io.BytesIO()
            fig.savefig(buf, format='png', bbox_inches='tight', dpi=110,
                        facecolor='white')
            plt.close(fig)
            return base64.b64encode(buf.getvalue()).decode()

        bloques = [f"<h2>{t}</h2><img src='data:image/png;base64,{_b64(f)}'>"
                   for t, f in figs if f is not None]
        html = f"""<!doctype html><html lang='es'><head><meta charset='utf-8'>
<title>{titulo}</title><style>
body{{font-family:system-ui,Arial,sans-serif;max-width:1000px;margin:24px auto;
padding:0 16px;color:#222}} h1{{margin-bottom:0}} .sub{{color:#888;font-size:13px}}
img{{max-width:100%;border:1px solid #eee;border-radius:6px;margin:6px 0 22px}}
pre{{background:#f6f8fa;padding:14px;border-radius:6px;overflow:auto;font-size:13px}}
h2{{border-bottom:2px solid #eee;padding-bottom:4px;margin-top:28px}}
</style></head><body>
<h1>{titulo}</h1><div class='sub'>{sub}</div>
<h2>Resumen</h2><pre>{self._texto_resumen(info, rep)}</pre>
{''.join(bloques)}
</body></html>"""
        os.makedirs(os.path.dirname(os.path.abspath(ruta)) or '.', exist_ok=True)
        with open(ruta, 'w', encoding='utf-8') as fh:
            fh.write(html)
        print(f"✅ informe -> {ruta}")
        return ruta

    @staticmethod
    def _texto_resumen(info, rep):
        """Texto monoespaciado con info + métricas de integridad (para el informe)."""
        c = rep['completitud']
        a = rep['anomalias']
        L = [
            f"Archivo        : {info['archivo']}",
            f"Tamaño en disco: {info['tam_mb']:,.1f} MB",
            f"Filas / nodos  : {info['filas']:,} / {info['nodos']:,}",
            f"Rango temporal : {info['fecha_min']}  ->  {info['fecha_max']}",
            "",
            f"Completitud    : {c['filas']:,} / {c['esperadas']:,} ({c['pct']}%)",
            f"Duplicados     : {rep['duplicados']:,}",
            f"Nodos incompletos: {len(rep['nodos_incompletos'])}",
            f"Relleno (fill_flag!=0): {rep['relleno']['filas']:,} "
            f"({rep['relleno']['pct']}%)",
            f"Nulos          : {rep['nulos'] or 'ninguno'}",
            f"Fuera de rango físico: {rep['fuera_de_rango'] or 'ninguno'}",
            "Anomalías físicas:",
            f"   GHI > clearsky_ghi : {a['ghi_mayor_clearsky']:,}",
            f"   GHI = 0 de día     : {a['ghi_cero_de_dia']:,}",
            f"   DNI = 0 de día     : {a['dni_cero_de_dia']:,}",
            f"   GHI negativo       : {a['ghi_negativo']:,}",
        ]
        return "\n".join(L)

    # ===================================================================== #
    # Utilidades internas
    # ===================================================================== #
    def _mascara_fuera_rango(self, df, col):
        """
        Máscara booleana de valores fuera de rango físico de `col`. Para
        `pressure`, si la metadata trae `msnm`, usa la **presión esperada por
        elevación** del nodo ±`tol_presion` (calibración barométrica); los nodos
        sin elevación caen al rango plano de `RANGOS_FISICOS`.
        """
        if (col == 'pressure' and self.elev is not None
                and 'nodo_id' in df.columns):
            p = df['pressure'].to_numpy(dtype='float64')
            esp = presion_barometrica(self.elev.reindex(df['nodo_id'].values)
                                      .to_numpy(dtype='float64'))
            mal = np.abs(p - esp) > self.tol_presion
            sin = np.isnan(esp)                # nodos sin elevación -> rango plano
            if sin.any():
                lo, hi = RANGOS_FISICOS['pressure']
                mal = np.where(sin, (p < lo) | (p > hi), mal)
            return pd.Series(mal, index=df.index)

        lo, hi = RANGOS_FISICOS.get(col, (None, None))
        mal = pd.Series(False, index=df.index)
        if lo is not None:
            mal |= df[col] < lo
        if hi is not None:
            mal |= df[col] > hi
        return mal

    @staticmethod
    def _aslist(x):
        if x is None:
            return None
        return list(x) if isinstance(x, (list, tuple, set, np.ndarray)) else [x]

    @staticmethod
    def _parsear_dia(dia):
        """Devuelve (mes|None, [dias]). Acepta int, 'YYYY-MM-DD', 'MM-DD' o lista."""
        if isinstance(dia, (list, tuple)):
            return None, list(dia)
        if isinstance(dia, str):
            ts = pd.to_datetime(dia if dia.count('-') == 2 else f'2000-{dia}')
            return int(ts.month), [int(ts.day)]
        return None, [int(dia)]

    @staticmethod
    def _finalizar(fig, guardar):
        """Guarda el PNG si se pidió y devuelve el Figure (para notebook)."""
        if guardar:
            os.makedirs(os.path.dirname(os.path.abspath(guardar)), exist_ok=True)
            fig.savefig(guardar, bbox_inches='tight', facecolor='white', dpi=150)
            print(f"✅ guardado -> {guardar}")
        return fig


# ------------------------------------------------------------------------- #
# CLI
# ------------------------------------------------------------------------- #
def _cli():
    ap = argparse.ArgumentParser(
        description="Análisis exploratorio y de integridad de parquets NSRDB.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="Ejemplos:\n"
               "  python Utils/analizador_datos.py --anio 2024 --info\n"
               "  python Utils/analizador_datos.py --anio 2024 --integridad\n"
               "  python Utils/analizador_datos.py --anio 2024 --estadisticas ghi dni temperature\n"
               "  python Utils/analizador_datos.py --anio 2024 --histograma ghi --solo-diurno --guardar h.png\n"
               "  python Utils/analizador_datos.py --anio 2024 --serie ghi --nodos 0 --dia 2024-02-29 --guardar s.png\n"
               "  python Utils/analizador_datos.py --anio 2024 --correlaciones ghi dni temperature --guardar c.png\n"
               "  python Utils/analizador_datos.py --parquet ruta.parquet --info")
    ap.add_argument('--parquet', default=None, help="Ruta a un parquet concreto.")
    ap.add_argument('--anio', type=int, default=2024)
    ap.add_argument('--region', default='Tamaulipas')
    ap.add_argument('--info', action='store_true')
    ap.add_argument('--integridad', action='store_true')
    ap.add_argument('--estadisticas', nargs='*', metavar='VAR')
    ap.add_argument('--histograma', metavar='VAR')
    ap.add_argument('--serie', metavar='VAR')
    ap.add_argument('--perfil', metavar='VAR')
    ap.add_argument('--correlaciones', nargs='*', metavar='VAR')
    ap.add_argument('--clasificar-dias', action='store_true', dest='clasificar')
    ap.add_argument('--comparar', nargs='+', type=int, metavar='ANIO',
                    help="Año(s) a comparar contra --anio.")
    ap.add_argument('--por', default='mes', choices=['mes', 'nodo', 'total'])
    ap.add_argument('--variable', default='ghi', help="Variable para --comparar.")
    ap.add_argument('--exportar', metavar='RUTA',
                    help="Exporta el subconjunto filtrado (csv/parquet/xlsx/feather).")
    ap.add_argument('--resamplear', metavar='VAR',
                    help="Agrega VAR a la frecuencia --frecuencia.")
    ap.add_argument('--frecuencia', default='D', choices=['H', 'D', 'M'])
    ap.add_argument('--agregacion', default='mean',
                    choices=['mean', 'sum', 'max', 'min'])
    ap.add_argument('--factor', type=float, default=1.0)
    ap.add_argument('--curva-duracion', metavar='VAR', dest='curva')
    ap.add_argument('--outliers', metavar='VAR',
                    help="Detecta nodos atípicos según VAR.")
    ap.add_argument('--metodo', default='zscore', choices=['zscore', 'iqr'])
    ap.add_argument('--rosa-viento', action='store_true', dest='rosa')
    ap.add_argument('--rosa-viento-12', action='store_true', dest='rosa12',
                    help="Panel 4x3 de rosas de viento por mes.")
    ap.add_argument('--boxplot', metavar='VAR')
    ap.add_argument('--heatmap', metavar='VAR',
                    help="Mapa de calor mes×hora de VAR.")
    ap.add_argument('--mapa-recurso', metavar='VAR', dest='mapa_recurso',
                    nargs='?', const='ghi',
                    help="Mapa de insolación media diaria (def VAR=ghi).")
    ap.add_argument('--mapa-delta', type=int, metavar='ANIO', dest='mapa_delta',
                    help="Mapa de la diferencia por nodo de --variable vs ANIO.")
    ap.add_argument('--anomalias', action='store_true',
                    help="Lista las filas con anomalías (conteo por tipo).")
    ap.add_argument('--reporte', metavar='RUTA',
                    help="Genera un informe consolidado (.html o .pdf).")
    # filtros comunes
    ap.add_argument('--nodos', nargs='*', type=int)
    ap.add_argument('--mes', type=int)
    ap.add_argument('--dia', type=str)
    ap.add_argument('--solo-diurno', action='store_true', dest='solo_diurno')
    ap.add_argument('--guardar', default=None, help="PNG de salida (gráficas).")
    args = ap.parse_args()

    a = AnalizadorSolar(parquet=args.parquet, anio=args.anio, region=args.region)
    filtros = {k: v for k, v in
               dict(nodos=args.nodos, mes=args.mes, dia=args.dia).items()
               if v is not None}

    if args.info:
        a.info()
    if args.integridad:
        a.integridad(graficar=bool(args.guardar), guardar=args.guardar, **filtros)
    if args.estadisticas is not None:
        with pd.option_context('display.max_columns', None, 'display.width', 200):
            print(a.estadisticas(args.estadisticas or None, **filtros))
    if args.histograma:
        a.histograma(args.histograma, solo_diurno=args.solo_diurno,
                     guardar=args.guardar, **filtros)
    if args.serie:
        a.serie_temporal(args.serie, guardar=args.guardar, **filtros)
    if args.perfil:
        a.perfil_diario(args.perfil, guardar=args.guardar, **filtros)
    if args.correlaciones is not None:
        a.correlaciones(args.correlaciones or None, guardar=args.guardar, **filtros)
    if args.clasificar:
        a.clasificar_dias(graficar=bool(args.guardar), guardar=args.guardar, **filtros)
    if args.comparar:
        with pd.option_context('display.max_columns', None, 'display.width', 200):
            print(a.comparar(args.comparar, variable=args.variable, por=args.por,
                             graficar=bool(args.guardar), guardar=args.guardar,
                             **filtros))
    if args.exportar:
        a.exportar(args.exportar, **filtros)
    if args.resamplear:
        with pd.option_context('display.max_rows', 40):
            print(a.resamplear(args.resamplear, frecuencia=args.frecuencia,
                               agregacion=args.agregacion, factor=args.factor,
                               graficar=bool(args.guardar), guardar=args.guardar,
                               **filtros))
    if args.curva:
        a.curva_duracion(args.curva, solo_diurno=args.solo_diurno,
                         guardar=args.guardar, **filtros)
    if args.outliers:
        with pd.option_context('display.max_columns', None, 'display.width', 200):
            print(a.outliers_nodos(args.outliers, metodo=args.metodo,
                                   graficar=bool(args.guardar), guardar=args.guardar,
                                   **filtros))
    if args.rosa:
        a.rosa_viento(guardar=args.guardar, **filtros)
    if args.rosa12:
        a.rosa_viento_12meses(guardar=args.guardar, **filtros)
    if args.boxplot:
        a.boxplot(args.boxplot, solo_diurno=args.solo_diurno,
                  guardar=args.guardar, **filtros)
    if args.heatmap:
        a.heatmap_mes_hora(args.heatmap, agregacion=args.agregacion,
                           guardar=args.guardar, **filtros)
    if args.mapa_recurso:
        a.mapa_recurso(args.mapa_recurso, guardar=args.guardar, **filtros)
    if args.mapa_delta:
        a.mapa_delta(args.mapa_delta, variable=args.variable,
                     guardar=args.guardar, **filtros)
    if args.anomalias:
        a.anomalias(**filtros)
    if args.reporte:
        a.reporte(args.reporte, **filtros)


if __name__ == "__main__":
    _cli()
