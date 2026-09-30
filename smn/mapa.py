"""
Mapa de las estaciones del SMN sobre la división política de Tamaulipas.

    conda run -n rs python -m smn.mapa
    conda run -n rs python -m smn.mapa --cobertura-min 90 --base

Misma estructura que los mapas de `urbano/`: municipios del Marco Geoestadístico
del INEGI como fondo, la capa de datos encima, ejes limpios, barra de escala y
—opcionalmente— mosaico de referencia. Reutiliza `urbano.mapas.estilo` en vez de
copiar la paleta, para que las dos familias de figuras se lean como una sola.

## La cobertura es ORDINAL, así que va en una rampa de un tono

Más oscuro = más completo, en los mismos tres pasos de azul que `urbano` usa
para la calidad. Un esquema categórico (rojo/amarillo/verde) obligaría a
consultar la leyenda para saber cuál es "mejor", y además tropieza con el
daltonismo justo en el par rojo-verde.

## Lo que el mapa NO puede mostrar

Las 82 estaciones del catálogo sin datos descargados **no tienen coordenadas**
—el catálogo del SMN no las trae y las series son de donde salen—, así que no
existe forma de dibujarlas. El subtítulo dice cuántas quedaron fuera para que su
ausencia no se lea como que no existen.
"""
from __future__ import annotations
import argparse
import os
import textwrap

import matplotlib.pyplot as plt
from matplotlib.lines import Line2D

from smn import config as C
from smn import cobertura as K


def _gdf(sel):
    """Las estaciones seleccionadas como GeoDataFrame en el CRS métrico."""
    import geopandas as gpd
    from urbano import config as UC
    return gpd.GeoDataFrame(
        sel, geometry=gpd.points_from_xy(sel["longitud"], sel["latitud"]),
        crs=UC.CRS_GEO).to_crs(UC.CRS_METRICO)


def _leyenda(ax, sel, E, base: bool = False) -> None:
    """Leyenda de bandas, con el conteo de cada una."""
    marcas = []
    for _, banda in C.BANDAS:
        n = int((sel["banda"] == banda).sum())
        if not n:
            continue
        etiqueta = {"alta": "≥ 95 %", "media": "85 – 95 %",
                    "baja": "< 85 %"}[banda]
        marcas.append(Line2D([], [], marker="o", ls="", markersize=7,
                             markerfacecolor=E.CALIDAD[banda],
                             markeredgecolor="white", markeredgewidth=0.6,
                             label=f"{etiqueta}  ({n})"))
    if marcas:
        # Sobre el mosaico hace falta un fondo: el rótulo de una carretera o el
        # azul del golfo por debajo dejan el texto ilegible. Sobre fondo liso el
        # recuadro sería ruido.
        leg = ax.legend(handles=marcas, loc="upper right", frameon=base,
                        fontsize=8, title="Cobertura del periodo",
                        title_fontsize=8.5, labelspacing=0.6)
        if base:
            marco = leg.get_frame()
            marco.set_facecolor(E.SUPERFICIE)
            marco.set_edgecolor(E.BORDE)
            marco.set_alpha(0.88)
            marco.set_linewidth(0.6)


def mapa_estaciones(desde_2020: bool = True,
                    cobertura_min: float = C.COBERTURA_MIN_OMISION,
                    mostrar_descartadas: bool = False, base: bool = False,
                    etiquetar: int = 0, ruta: str | None = None,
                    titulo: str | None = None, subtitulo: str | None = None,
                    figsize=(8.5, 12), tabla=None):
    """
    Dibuja las estaciones sobre los 43 municipios.

    Parameters
    ----------
    desde_2020 : exigir que la estación arranque en 2020. Por omisión sí.
    cobertura_min : mínimo de cobertura del periodo, en %. Por omisión 75.
    mostrar_descartadas : pinta en gris las que tienen datos pero no pasan el
        filtro, para ver qué se está dejando fuera. Las que no tienen datos no
        se pueden dibujar nunca (no hay coordenadas).
    base : mosaico de OpenStreetMap de fondo (necesita red la primera vez).
    etiquetar : rotula las N estaciones de mayor cobertura. 0 = ninguna.
    ruta : dónde guardar el PNG. Por omisión, dentro de `Results/smn/`.
    titulo, subtitulo : `None` los autogenera, `""` los quita.
    tabla : tabla ya calculada con `cobertura.tabla()`, para no releer.

    Returns
    -------
    `(Figure, DataFrame)` — la figura y las estaciones dibujadas.
    """
    from urbano import config as UC
    from urbano.data import manchas as M
    from urbano.mapas import estilo as E

    E.aplicar_estilo()
    t = K.tabla() if tabla is None else tabla
    sel = K.seleccionar(t, desde_2020=desde_2020, cobertura_min=cobertura_min)
    if sel.empty:
        raise ValueError(
            f"Ningún registro con cobertura ≥ {cobertura_min} %"
            + (" arrancando en 2020" if desde_2020 else "")
            + f". El máximo disponible es {t['cobertura'].max():.1f} %.")

    mun = M.municipios()
    if base:
        mun = mun.to_crs(UC.CRS_MAPA)
    g = _gdf(sel)
    if base:
        g = g.to_crs(UC.CRS_MAPA)

    fig, ax = plt.subplots(figsize=figsize)
    # Sobre el mosaico los municipios no se rellenan: taparían el mapa entero.
    mun.plot(ax=ax, facecolor="none" if base else "white",
             edgecolor=E.RETICULA, lw=0.6, zorder=1)
    mun.dissolve().boundary.plot(ax=ax, color=E.BORDE, lw=1.2, zorder=2)

    n_desc = 0
    if mostrar_descartadas:
        desc = t[t["tiene_datos"] & ~t["clave"].isin(sel["clave"])]
        if not desc.empty:
            gd = _gdf(desc)
            if base:
                gd = gd.to_crs(UC.CRS_MAPA)
            ax.scatter(gd.geometry.x, gd.geometry.y, s=18, c=E.NODO_FUERA,
                       edgecolors="white", linewidths=0.4, zorder=3)
            n_desc = len(desc)

    # De clara a oscura, para que las de mayor cobertura queden ARRIBA cuando
    # dos estaciones caen casi en el mismo punto.
    for _, banda in C.BANDAS[::-1]:
        sub = g[g["banda"] == banda]
        if sub.empty:
            continue
        ax.scatter(sub.geometry.x, sub.geometry.y, s=46, c=E.CALIDAD[banda],
                   edgecolors="white", linewidths=0.7, zorder=4)

    if etiquetar:
        for _, e in g.nlargest(etiquetar, "cobertura").iterrows():
            ax.annotate(e["nombre"], (e.geometry.x, e.geometry.y),
                        xytext=(5, 4), textcoords="offset points",
                        fontsize=6.5, color=E.TINTA_2, zorder=6)

    E.limpiar_ejes(ax)
    if base:
        E.add_mapa_base(ax, mun.crs, zoom=8)
    E.barra_escala(ax, 50, web_mercator=base)

    if titulo is None:
        titulo = ("Estaciones climatológicas del SMN en Tamaulipas"
                  + (" · sobre mapa base" if base else ""))
    if subtitulo is None:
        lo, hi, dias = K.periodo()
        r = K.resumen(t)
        filtro = (f"cobertura ≥ {cobertura_min:g} %"
                  + (" y con dato desde 2020" if desde_2020 else ""))
        subtitulo = (
            f"{len(sel)} de {r['catalogo']} estaciones del catálogo cumplen "
            f"{filtro}\nperiodo {lo:%Y-%m-%d} a {hi:%Y-%m-%d} ({dias} días) · "
            f"{r['sin_datos']} sin ningún dato descargado (el catálogo del SMN "
            f"no trae coordenadas: no se pueden ubicar)"
            + (f" · {n_desc} descartadas en gris" if n_desc else ""))

    # Los textos van en coordenadas de FIGURA, no del eje. Tamaulipas es alto y
    # estrecho, así que con `aspect="equal"` el eje se encoge a la mitad del
    # ancho del lienzo: anclado a él, el encabezado se salía por la derecha y se
    # montaba sobre el título.
    y = 0.985
    if titulo:
        fig.text(0.012, y, titulo, fontsize=13, weight="bold", color=E.TINTA,
                 ha="left", va="top")
        y -= 0.016 + 0.012 * titulo.count("\n")
    if subtitulo:
        # Se envuelve por ancho: el subtítulo crece con las opciones activas
        # (el conteo de descartadas, el filtro) y sin esto se sale del lienzo
        # por la derecha justo cuando lleva más información.
        ancho = int(fig.get_size_inches()[0] * 16)
        subtitulo = "\n".join(
            linea for parrafo in subtitulo.split("\n")
            for linea in textwrap.wrap(parrafo, ancho) or [""])
        fig.text(0.012, y, subtitulo, fontsize=8.5, color=E.TINTA_2,
                 ha="left", va="top", linespacing=1.5)
        y -= 0.014 * (subtitulo.count("\n") + 1)
    fig.subplots_adjust(top=y - 0.005, bottom=0.02, left=0.01, right=0.99)
    _leyenda(ax, sel, E, base=base)

    ruta = ruta or os.path.join(
        C.DIR_SALIDA,
        f"estaciones_smn_cob{cobertura_min:g}{'_base' if base else ''}.png")
    os.makedirs(os.path.dirname(os.path.abspath(ruta)), exist_ok=True)
    fig.savefig(ruta)
    print(f"[mapa] {ruta}")
    return fig, sel


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--cobertura-min", type=float,
                    default=C.COBERTURA_MIN_OMISION)
    ap.add_argument("--todas", action="store_true",
                    help="no exigir que la estación arranque en 2020")
    ap.add_argument("--descartadas", action="store_true",
                    help="pinta en gris las que no pasan el filtro")
    ap.add_argument("--base", action="store_true", help="mosaico de fondo")
    ap.add_argument("--etiquetar", type=int, default=0)
    ap.add_argument("--ruta")
    a = ap.parse_args()

    import matplotlib
    matplotlib.use("Agg")
    mapa_estaciones(desde_2020=not a.todas, cobertura_min=a.cobertura_min,
                    mostrar_descartadas=a.descartadas, base=a.base,
                    etiquetar=a.etiquetar, ruta=a.ruta)
