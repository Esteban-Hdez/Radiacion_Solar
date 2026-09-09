"""
Paleta y utilidades compartidas por los mapas.

Los colores NO se eligieron a ojo: son valores ya validados de la paleta de
referencia del proyecto de visualización.

- `calidad` es una variable ORDINAL (baja < media < alta), así que se codifica
  con una rampa de UN solo tono (azul) de claro a oscuro, en los pasos 250/400/600.
  El 250 es el paso más claro que todavía separa 2:1 de la superficie clara.
- La mancha urbana es otra variable, no otro nivel de la misma: lleva el naranja
  de la ranura categórica 2, que es el par validado contra el azul de la 1.
- El resto (retícula, bordes, tinta) son los grises de chrome de la paleta, para
  que nada del fondo compita con los datos.

Los mapas se rinden en superficie clara a propósito (van a PDF/informe).
"""
from __future__ import annotations

import os as _os

from urbano import config as _C

# Los mosaicos descargados se cachean para no volver a pedirlos en cada corrida
# (y para que el pipeline funcione sin red una vez calentado el caché).
DIR_CACHE_TILES = _os.path.join(_C.RAIZ, "cache", "tiles")

SUPERFICIE = "#fcfcfb"
TINTA = "#0b0b0b"
TINTA_2 = "#52514e"
TINTA_MUTED = "#898781"
RETICULA = "#e1e0d9"
BORDE = "#c3c2b7"

# Rampa ordinal de confianza (un tono, claro -> oscuro).
CALIDAD = {"baja": "#86b6ef", "media": "#3987e5", "alta": "#184f95"}
ORDEN_CALIDAD = ["alta", "media", "baja"]

MANCHA = "#eb6834"          # área urbana INEGI
MANCHA_BORDE = "#b8420f"
NODO_FUERA = "#d8d7d0"      # nodos no asignados a ninguna ciudad
CELDA = "#2a78d6"

# Resalte de un nodo concreto. No es una serie de datos sino un indicador de
# SELECCIÓN, así que va en la ranura categórica 3 (aqua) —validada contra el azul
# de los nodos y el naranja de la mancha— y siempre con un halo blanco debajo,
# para que se lea igual sobre el mosaico, sobre la mancha o sobre el fondo liso.
RESALTE = "#1baf7a"

FUENTE = ["system-ui", "Helvetica Neue", "Arial", "DejaVu Sans"]


# --------------------------------------------------------------------------- #
# Mapas base (mosaicos de referencia: carreteras, calles, nombres)
# --------------------------------------------------------------------------- #
# El mosaico de OpenStreetMap es el que mejor rotula México (nombres de calles,
# colonias y número de carretera federal/estatal). Su servidor rechaza el
# user-agent por omisión de contextily con un 403, así que hay que declarar uno
# propio, como pide su política de uso.
USER_AGENT = "radiacion-solar-tamaulipas/1.0 (analisis academico)"

PROVEEDORES = {
    "osm": ("OpenStreetMap", "Mapnik"),     # calles + nombres + carreteras
    "esri": ("Esri", "WorldStreetMap"),     # alternativa; relieve suave de fondo
    "claro": ("CartoDB", "Positron"),       # minimalista, casi sin rótulos
}
PROVEEDOR_OMISION = "osm"


def add_mapa_base(ax, crs, proveedor: str = PROVEEDOR_OMISION,
                  zoom="auto") -> bool:
    """
    Pega el mosaico de referencia bajo lo ya dibujado. Devuelve si lo consiguió.

    Nunca lanza: si no hay red o el servidor falla, el mapa se rinde igual sin
    fondo y se avisa por consola. Un mapa sin mosaico sigue siendo correcto; una
    excepción a media generación tira las ocho figuras.
    """
    try:
        import contextily as cx
        import contextily.tile as ctile
    except ImportError:
        print("[base] contextily no está instalado; se omite el mosaico")
        return False

    ctile.USER_AGENT = USER_AGENT
    try:
        cx.set_cache_dir(DIR_CACHE_TILES)
    except Exception:
        pass

    grupo, variante = PROVEEDORES[proveedor]
    fuente = getattr(getattr(cx.providers, grupo), variante)
    try:
        cx.add_basemap(ax, source=fuente, crs=crs, zoom=zoom,
                       attribution_size=5)
        return True
    except Exception as e:                     # red caída, 403, tile corrupto…
        print(f"[base] no se pudo traer el mosaico ({type(e).__name__}: "
              f"{str(e)[:80]}); el mapa se genera sin fondo")
        return False


def aplicar_estilo() -> None:
    """Ajustes globales de matplotlib comunes a todas las figuras."""
    import matplotlib as mpl
    mpl.rcParams.update({
        "figure.facecolor": SUPERFICIE,
        "axes.facecolor": SUPERFICIE,
        "savefig.facecolor": SUPERFICIE,
        "font.family": "sans-serif",
        "font.sans-serif": FUENTE,
        "text.color": TINTA,
        "axes.edgecolor": BORDE,
        "axes.labelcolor": TINTA_2,
        "xtick.color": TINTA_MUTED,
        "ytick.color": TINTA_MUTED,
        "axes.titlesize": 11,
        "axes.titleweight": "bold",
        "figure.dpi": 110,
        "savefig.dpi": 200,
        "savefig.bbox": "tight",
    })


def barra_escala(ax, largo_km: float, etiqueta: str | None = None,
                 web_mercator: bool = False) -> None:
    """
    Barra de escala en un eje proyectado en metros.

    Un mapa de una ciudad de 1 km² y uno de 170 km² se ven idénticos sin ella,
    y en este análisis el tamaño relativo mancha↔celda ES el hallazgo.

    `web_mercator=True` para los mapas con mosaico de fondo, que van en EPSG:3857.
    Ahí el "metro" del eje NO es un metro en el suelo: Mercator infla las
    distancias por `1/cos(latitud)`, que a 25 °N es un 10 % —suficiente para que
    una barra dibujada como si fuera 6372 mintiera de forma visible—. Así que la
    longitud en unidades de mapa se corrige con la latitud del centro del eje.
    """
    x0, x1 = ax.get_xlim()
    y0, y1 = ax.get_ylim()
    largo_m = largo_km * 1000
    if web_mercator:  # noqa: E701
        import math
        R = 6378137.0
        lat = math.degrees(2 * math.atan(math.exp((y0 + y1) / 2 / R)) - math.pi / 2)
        largo_m /= math.cos(math.radians(lat))
    # Con mosaico, contextily estampa su atribución abajo a la IZQUIERDA; la
    # barra se va a la derecha para no encimarse con ella.
    py = y0 + (y1 - y0) * (0.085 if web_mercator else 0.06)
    if web_mercator:
        px = x1 - (x1 - x0) * 0.06 - largo_m
    else:
        px = x0 + (x1 - x0) * 0.06
    ax.plot([px, px + largo_m], [py, py], color=TINTA_2, lw=2,
            solid_capstyle="butt", zorder=10)
    ax.text(px + largo_m / 2, py + (y1 - y0) * 0.018,
            etiqueta or f"{largo_km:g} km", ha="center", va="bottom",
            fontsize=7, color=TINTA_2, zorder=10)


def limpiar_ejes(ax) -> None:
    """Un mapa no lleva ejes de coordenadas: son ruido, no información."""
    ax.set_xticks([])
    ax.set_yticks([])
    for lado in ax.spines.values():
        lado.set_visible(False)
    ax.set_aspect("equal")
