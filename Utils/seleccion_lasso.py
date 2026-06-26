"""
seleccion_lasso.py
==================

Selección INTERACTIVA de nodos a eliminar (mar / laguna / isla u otros) dibujando
regiones con el mouse sobre el mapa, dentro de un notebook de Jupyter.

Requiere el backend interactivo `ipympl`:

    %matplotlib widget                       # <- en la PRIMERA celda
    from Utils.seleccion_lasso import SelectorNodos

    sel = SelectorNodos()                     # dibuja el mapa (preselecciona msnm==0)
    #  ... arrastra con el mouse sobre el mapa ...
    #    · botón IZQUIERDO  -> AGREGA los nodos encerrados a la selección
    #    · botón DERECHO    -> QUITA los nodos encerrados de la selección
    #  los seleccionados se pintan de NEGRO y el título muestra el conteo.

    sel.guardar()                             # -> Data/Tamaulipas/nodos_a_eliminar.csv
    sel.seleccionados                         # lista de nodo_id seleccionados

Métodos útiles:
    sel.reiniciar()        -> vacía la selección
    sel.preseleccionar(0)  -> selecciona todos los nodos con msnm <= umbral
    sel.guardar(ruta)      -> exporta la selección a CSV

Nota: si no usas `%matplotlib widget` el lasso no responderá (matplotlib estará en
modo estático). En ese caso usa el método por reglas (`identificar_nodos_mar_tamaulipas.py`).
"""

import os
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from matplotlib.widgets import LassoSelector
from matplotlib.path import Path

METADATA = 'Data/Tamaulipas/metadata_nodos_tamaulipas.csv'
RUTA_SALIDA = 'Data/Tamaulipas/nodos_a_eliminar.csv'


class SelectorNodos:
    """
    Selector interactivo de nodos sobre el mapa de Tamaulipas.

    Arrastrar con el botón IZQUIERDO agrega los nodos encerrados; con el botón
    DERECHO los quita. Los seleccionados se muestran en negro.

    Parameters
    ----------
    metadata : str
        CSV con `nodo_id, latitude, longitude, msnm`.
    preseleccion_msnm : float | None
        Si se da, preselecciona los nodos con `msnm <= preseleccion_msnm`
        (por defecto 0.0 -> arranca con los nodos sobre agua ya marcados).
    con_basemap : bool
        Dibuja el mapa base topográfico de fondo (contextily).

    Attributes
    ----------
    seleccionados : list[int]   nodo_id actualmente seleccionados.
    mascara : np.ndarray(bool)  máscara booleana sobre el orden de la metadata.
    """

    def __init__(self, metadata=METADATA, preseleccion_msnm=0.0, con_basemap=True):
        self.df = pd.read_csv(metadata).reset_index(drop=True)
        self.xy = self.df[['longitude', 'latitude']].to_numpy()
        self.mascara = np.zeros(len(self.df), dtype=bool)

        # Figura
        self.fig, self.ax = plt.subplots(figsize=(8, 10))
        self.col = self.ax.scatter(self.xy[:, 0], self.xy[:, 1], s=12,
                                   c='#5b8db8', edgecolors='none', zorder=3)
        pad = 0.1
        self.ax.set_xlim(self.xy[:, 0].min() - pad, self.xy[:, 0].max() + pad)
        self.ax.set_ylim(self.xy[:, 1].min() - pad, self.xy[:, 1].max() + pad)
        self.ax.set_xlabel("Longitud"); self.ax.set_ylabel("Latitud")

        if con_basemap:
            try:
                import contextily as cx
                cx.add_basemap(self.ax, crs='EPSG:4326',
                               source=cx.providers.CartoDB.Positron, alpha=0.85, zorder=1)
                self.ax.set_aspect('auto')
                self.ax.set_xlim(self.xy[:, 0].min() - pad, self.xy[:, 0].max() + pad)
                self.ax.set_ylim(self.xy[:, 1].min() - pad, self.xy[:, 1].max() + pad)
            except Exception as e:
                print(f"(sin mapa base: {e})")

        # Dos lazos: izquierdo agrega, derecho quita
        self._lazo_add = LassoSelector(self.ax, onselect=self._agregar, button=1)
        self._lazo_del = LassoSelector(self.ax, onselect=self._quitar, button=3)

        if preseleccion_msnm is not None:
            self.preseleccionar(preseleccion_msnm, _redibujar=False)
        self._actualizar()

    # ---- callbacks del lasso ----
    def _dentro(self, verts):
        return Path(verts).contains_points(self.xy)

    def _agregar(self, verts):
        self.mascara |= self._dentro(verts)
        self._actualizar()

    def _quitar(self, verts):
        self.mascara &= ~self._dentro(verts)
        self._actualizar()

    # ---- estado / dibujo ----
    def _actualizar(self):
        colores = np.where(self.mascara, 'black', '#5b8db8')
        tam = np.where(self.mascara, 26, 12)
        self.col.set_color(colores)
        self.col.set_sizes(tam)
        self.ax.set_title(f"Selecciona nodos a eliminar  ·  seleccionados: {int(self.mascara.sum())}",
                          fontsize=12, fontweight='bold')
        self.fig.canvas.draw_idle()

    # ---- API ----
    def preseleccionar(self, msnm_max=0.0, _redibujar=True):
        """Marca todos los nodos con msnm <= msnm_max (acumulativo)."""
        self.mascara |= (self.df['msnm'] <= msnm_max).to_numpy()
        if _redibujar:
            self._actualizar()

    def reiniciar(self):
        """Vacía la selección."""
        self.mascara[:] = False
        self._actualizar()

    @property
    def seleccionados(self):
        return self.df.loc[self.mascara, 'nodo_id'].tolist()

    def guardar(self, ruta=RUTA_SALIDA):
        """Exporta los nodos seleccionados a CSV y devuelve la ruta."""
        os.makedirs(os.path.dirname(ruta), exist_ok=True)
        cols = [c for c in ['nodo_id', 'nodo_id_original', 'latitude', 'longitude', 'msnm']
                if c in self.df.columns]
        sel = self.df.loc[self.mascara, cols]
        sel.to_csv(ruta, index=False)
        print(f"✅ {len(sel)} nodos guardados en {ruta}")
        return ruta
