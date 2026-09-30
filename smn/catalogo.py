"""
Catálogo visual: una lámina por municipio con sus estaciones del SMN.

    conda run -n rs python -m smn.catalogo
    conda run -n rs python -m smn.catalogo --sin-base

Cuatro páginas de 12 láminas (3 × 4) para los 43 municipios, ordenados por clave
INEGI —el orden del catálogo oficial, que permite buscar un municipio sin
conocer su tamaño—. Mismo formato que `urbano.mapas.catalogo`, del que copia la
rejilla, la barra de escala por lámina y la leyenda al pie.

## La pregunta que responde cada lámina

"¿Qué estaciones puedo usar para este municipio?" Y tiene dos respuestas
distintas según el caso:

- **Municipio con estaciones**: las de dentro, coloreadas por cobertura.
- **Municipio sin ninguna** (8 de los 43): el encuadre se amplía hasta alcanzar
  la más cercana, que se marca con un anillo y la distancia al borde. Dejar la
  lámina vacía sería correcto pero inútil: lo que hace falta saber es a qué
  distancia está el sustituto.

## La asignación es GEOMÉTRICA, no por el nombre del SMN

El archivo diario trae una columna `municipio`, pero **en tres estaciones no
coincide con el polígono donde caen sus coordenadas** (La Servilleta dice El
Mante y cae en Gómez Farías; El Barretal II dice Padilla y cae en Hidalgo; San
Francisco dice Casas y cae en Llera). Manda la geometría: es la que decide si
una estación está dentro del municipio que se está mirando. Las discrepancias se
listan en `discrepancias()`.

## Distancia al BORDE, no al centro

Para un municipio sin estaciones, lo que importa es cuánto hay que salirse de
él, no cuán lejos está de su centro geométrico. Una estación a 3 km del borde
sirve para casi cualquier propósito; una a 60 km, no. Por eso la distancia se
mide contra el polígono (y vale 0 para las de dentro).
"""
from __future__ import annotations
import argparse
import os

import numpy as np
import pandas as pd

from smn import config as C
from smn import cobertura as K

POR_PAGINA = 12          # rejilla 3 × 4
NCOLS = 4
# Cuántas estaciones de fuera se buscan como respaldo de un municipio vacío.
VECINAS = 3


# --------------------------------------------------------------------------- #
# Asignación estación -> municipio
# --------------------------------------------------------------------------- #
def _geo_estaciones(t=None):
    """Las estaciones con datos, como puntos en el CRS métrico."""
    import geopandas as gpd
    from urbano import config as UC
    t = K.tabla() if t is None else t
    con = t[t["tiene_datos"]].copy()
    return gpd.GeoDataFrame(
        con, geometry=gpd.points_from_xy(con["longitud"], con["latitud"]),
        crs=UC.CRS_GEO).to_crs(UC.CRS_METRICO)


def asignar(t=None):
    """
    Cada estación con el municipio en cuyo polígono CAE (no el que dice el SMN).

    Devuelve el GeoDataFrame de estaciones con `cve_mun_geo` y `mun_geo`.
    """
    import geopandas as gpd
    from urbano.data import manchas as M
    g = _geo_estaciones(t)
    mun = M.municipios()[["CVE_MUN", "municipio", "geometry"]].rename(
        columns={"CVE_MUN": "cve_mun_geo", "municipio": "mun_geo"})
    return gpd.sjoin(g, mun, how="left", predicate="within").drop(
        columns=["index_right"], errors="ignore")


def discrepancias(t=None) -> pd.DataFrame:
    """Estaciones cuyo municipio declarado no es donde caen sus coordenadas."""
    a = asignar(t).dropna(subset=["mun_geo"])
    d = a[a["municipio"].str.lower().str.strip()
          != a["mun_geo"].str.lower().str.strip()]
    return d[["clave", "nombre", "municipio", "mun_geo"]].reset_index(drop=True)


def resumen_municipios(t=None) -> pd.DataFrame:
    """
    Una fila por municipio: cuántas estaciones tiene y cuál es la más cercana.

    `n_estaciones` cuenta las que caen dentro; `n_utiles`, las que además pasan
    el umbral por omisión. `mas_cercana_km` es 0 cuando hay alguna dentro.
    """
    from urbano.data import manchas as M
    a = asignar(t)
    mun = M.municipios()
    filas = []
    for _, m in mun.sort_values("CVE_MUN").iterrows():
        dentro = a[a["cve_mun_geo"] == m["CVE_MUN"]]
        d_km = a.geometry.distance(m.geometry) / 1000
        cercana = a.loc[d_km.idxmin()]
        filas.append({
            "cve_mun": m["CVE_MUN"], "municipio": m["municipio"],
            "n_estaciones": len(dentro),
            "n_utiles": int((dentro["cobertura"] >= C.COBERTURA_MIN_OMISION).sum()),
            "mejor_cobertura": (round(float(dentro["cobertura"].max()), 1)
                                if len(dentro) else np.nan),
            "mas_cercana": cercana["nombre"],
            "mas_cercana_km": round(float(d_km.min()), 1),
        })
    return pd.DataFrame(filas)


# --------------------------------------------------------------------------- #
# Las láminas
# --------------------------------------------------------------------------- #
def _meta(fila, n_dentro, cercana_km) -> str:
    """
    Renglón de datos bajo el título de cada lámina.

    El NOMBRE de la estación más cercana no va aquí sino rotulado junto a su
    anillo en el mapa: en una lámina de 3.2 pulgadas este renglón no llega a 55
    caracteres, y con el nombre dentro se desbordaba sobre el título de la
    lámina vecina. Además, así el nombre queda donde está el punto.
    """
    cve = f"mun. {fila['CVE_MUN']}"
    if n_dentro == 0:
        return f"{cve} · sin estaciones · la más cercana a {cercana_km:.0f} km"
    plural = "estación" if n_dentro == 1 else "estaciones"
    return f"{cve} · {n_dentro} {plural}"


def panel_municipios(cves: list[str], ruta: str, titulo: str,
                     subtitulo: str | None = None, base: bool = False,
                     cobertura_min: float = C.COBERTURA_MIN_OMISION,
                     asignadas=None) -> str:
    """Una página de la rejilla: 12 municipios con sus estaciones."""
    import matplotlib.pyplot as plt
    import textwrap
    from matplotlib.lines import Line2D
    from matplotlib.patches import Patch
    from urbano import config as UC
    from urbano.data import manchas as M
    from urbano.mapas import estilo as E

    E.aplicar_estilo()
    a = asignar() if asignadas is None else asignadas
    mun = M.municipios()
    if base:
        mun, a = mun.to_crs(UC.CRS_MAPA), a.to_crs(UC.CRS_MAPA)
    # Las distancias se miden SIEMPRE en el CRS métrico: en Web Mercator un
    # "metro" a 25 °N es un 10 % más corto de lo que dice.
    a_m = asignar() if asignadas is None else asignadas.to_crs(UC.CRS_METRICO)
    mun_m = M.municipios()

    filas = int(np.ceil(len(cves) / NCOLS))
    alto_fila = 3.9 if base else 3.5
    fig, axes = plt.subplots(filas, NCOLS,
                             figsize=(3.2 * NCOLS, alto_fila * filas))
    axes = np.atleast_1d(axes).ravel()

    for ax, cve in zip(axes, cves):
        m = mun[mun["CVE_MUN"] == cve].iloc[0]
        m_m = mun_m[mun_m["CVE_MUN"] == cve].iloc[0]
        dentro = a[a["cve_mun_geo"] == cve]
        d_km = a_m.geometry.distance(m_m.geometry) / 1000
        orden = d_km.sort_values()
        cercana = a.loc[orden.index[0]]
        cercana_km = float(orden.iloc[0])

        # Encuadre: el municipio más un margen. Si no tiene estaciones dentro,
        # se abre hasta alcanzar las más próximas — el dato que hace falta ahí
        # es a qué distancia está el sustituto, no un polígono vacío.
        b = list(m.geometry.bounds)
        if dentro.empty:
            vecinas = a.loc[orden.index[:VECINAS]]
            b[0] = min(b[0], vecinas.geometry.x.min())
            b[1] = min(b[1], vecinas.geometry.y.min())
            b[2] = max(b[2], vecinas.geometry.x.max())
            b[3] = max(b[3], vecinas.geometry.y.max())
        lado = max(b[2] - b[0], b[3] - b[1]) * 1.14
        cx, cy = (b[0] + b[2]) / 2, (b[1] + b[3]) / 2
        minx, maxx = cx - lado / 2, cx + lado / 2
        miny, maxy = cy - lado / 2, cy + lado / 2

        vecinos = mun[mun["CVE_MUN"] != cve]
        vecinos.plot(ax=ax, facecolor="none" if base else "white",
                     edgecolor=E.RETICULA, lw=0.5, zorder=1)
        # El municipio de la lámina va relleno sobre fondo liso y solo
        # contorneado sobre el mosaico, donde un relleno taparía las calles.
        mun[mun["CVE_MUN"] == cve].plot(
            ax=ax, facecolor="none" if base else "#eef3fa",
            edgecolor=E.TINTA_2, lw=1.4, zorder=2)

        # Las de otros municipios que entran en el encuadre: contexto, en gris.
        fuera = a[(a["cve_mun_geo"] != cve)
                  & a.geometry.x.between(minx, maxx)
                  & a.geometry.y.between(miny, maxy)]
        if len(fuera):
            ax.scatter(fuera.geometry.x, fuera.geometry.y, s=14,
                       c=E.NODO_FUERA, edgecolors="white", linewidths=0.4,
                       zorder=3)

        # Dentro: color por banda de cobertura; gris las que no llegan al umbral.
        for _, banda in C.BANDAS[::-1]:
            sub = dentro[(dentro["banda"] == banda)
                         & (dentro["cobertura"] >= cobertura_min)]
            if len(sub):
                ax.scatter(sub.geometry.x, sub.geometry.y, s=52,
                           c=E.CALIDAD[banda], edgecolors="white",
                           linewidths=0.8, zorder=5)
        flojas = dentro[dentro["cobertura"] < cobertura_min]
        if len(flojas):
            ax.scatter(flojas.geometry.x, flojas.geometry.y, s=32,
                       c=E.NODO_FUERA, edgecolors=E.TINTA_MUTED,
                       linewidths=0.7, zorder=4)

        if dentro.empty:
            # Anillo con halo blanco: tiene que leerse igual sobre el mosaico,
            # sobre el relleno del municipio y sobre el fondo liso.
            for radio, color, ancho in ((300, "white", 4.2), (300, E.RESALTE, 2.2)):
                ax.scatter([cercana.geometry.x], [cercana.geometry.y], s=radio,
                           facecolors="none", edgecolors=color, linewidths=ancho,
                           zorder=6)
            ax.scatter([cercana.geometry.x], [cercana.geometry.y], s=34,
                       c=E.RESALTE, edgecolors="white", linewidths=0.8, zorder=7)
            ax.annotate(cercana["nombre"],
                        (cercana.geometry.x, cercana.geometry.y),
                        xytext=(0, -16), textcoords="offset points",
                        ha="center", va="top", fontsize=7, color=E.TINTA,
                        zorder=8,
                        bbox=dict(boxstyle="round,pad=0.22", fc=E.SUPERFICIE,
                                  ec="none", alpha=0.85))

        E.limpiar_ejes(ax)
        ax.set_xlim(minx, maxx)
        ax.set_ylim(miny, maxy)
        ancho_km = (maxx - minx) / 1000
        if base:
            E.add_mapa_base(ax, mun.crs)
        E.barra_escala(ax, 50 if ancho_km > 140 else (20 if ancho_km > 55 else 10),
                       web_mercator=base)
        ax.set_title(m["municipio"], loc="left", fontsize=10, pad=18)
        ax.text(0, 1.008,
                _meta(m, len(dentro), cercana_km),
                transform=ax.transAxes, fontsize=7.5, color=E.TINTA_2,
                va="bottom")

    for ax in axes[len(cves):]:
        ax.set_visible(False)

    manijas = [
        Patch(facecolor="none" if base else "#eef3fa", edgecolor=E.TINTA_2,
              label="Municipio de la lámina"),
        Line2D([], [], marker="o", ls="none", ms=8, mfc=E.CALIDAD["alta"],
               mec="white", label="Estación dentro (tono = cobertura)"),
        Line2D([], [], marker="o", ls="none", ms=6, mfc=E.NODO_FUERA,
               mec=E.TINTA_MUTED, label=f"Cobertura < {cobertura_min:g} %, o de otro municipio"),
        Line2D([], [], marker="o", ls="none", ms=11, mfc="none", mec=E.RESALTE,
               mew=2.0, label="Estación más cercana (municipio sin ninguna)"),
    ]
    fig.legend(handles=manijas, loc="upper center", ncol=min(len(manijas), NCOLS),
               frameon=False, fontsize=9, labelcolor=E.TINTA_2,
               bbox_to_anchor=(0.5, 0.0))

    ancho_pulg, alto_pulg = fig.get_size_inches()
    if subtitulo:
        subtitulo = textwrap.fill(subtitulo, max(30, int(ancho_pulg * 11)))
    n_lineas = subtitulo.count("\n") + 1 if subtitulo else 0
    alto_cabecera = 0.30 + (0.16 + 0.15 * n_lineas if subtitulo else 0.0)

    fig.tight_layout(rect=[0, 0.010, 1, 1 - alto_cabecera / alto_pulg],
                     h_pad=3.5 if base else 1.08)
    fig.suptitle(titulo, x=0.02, ha="left", fontsize=13, fontweight="bold",
                 y=1 - 0.075 / alto_pulg, va="top")
    if subtitulo:
        fig.text(0.02, 1 - 0.34 / alto_pulg, subtitulo, ha="left", va="top",
                 fontsize=9, color=E.TINTA_2)
    fig.savefig(ruta)
    plt.close(fig)
    return ruta


def generar(dir_salida: str | None = None, con_base: bool = True,
            cobertura_min: float = C.COBERTURA_MIN_OMISION) -> list[str]:
    """Las 4 páginas del catálogo, en sus dos versiones."""
    from urbano.data import manchas as M
    d = dir_salida or os.path.join(C.DIR_SALIDA, "catalogo")
    os.makedirs(d, exist_ok=True)

    cves = M.municipios().sort_values("CVE_MUN")["CVE_MUN"].tolist()
    paginas = [cves[i:i + POR_PAGINA] for i in range(0, len(cves), POR_PAGINA)]
    a = asignar()
    r = resumen_municipios()
    sin = int((r["n_estaciones"] == 0).sum())

    rutas = []
    for base in ([False, True] if con_base else [False]):
        sfx = "_base" if base else ""
        for i, pagina in enumerate(paginas, start=1):
            ruta = os.path.join(d, f"municipios_{i}de{len(paginas)}{sfx}.png")
            rutas.append(panel_municipios(
                pagina, ruta,
                f"Estaciones del SMN por municipio · página {i} de {len(paginas)}"
                + (" (sobre mapa base)" if base else ""),
                (f"Ordenados por clave INEGI. La estación se asigna al municipio "
                 f"donde CAEN sus coordenadas, no al que declara el SMN. "
                 f"{sin} municipios no tienen ninguna: en su lámina se marca la "
                 f"más cercana y la distancia a su borde.") if i == 1 else None,
                base=base, cobertura_min=cobertura_min, asignadas=a))
            print(f"[catalogo] {rutas[-1]}")
    return rutas


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--sin-base", action="store_true")
    ap.add_argument("--cobertura-min", type=float,
                    default=C.COBERTURA_MIN_OMISION)
    ap.add_argument("--dir")
    a = ap.parse_args()

    import matplotlib
    matplotlib.use("Agg")
    pd.set_option("display.width", 200)

    r = resumen_municipios()
    print(f"\n{int((r.n_estaciones > 0).sum())} de {len(r)} municipios tienen "
          f"al menos una estación\n")
    vacios = r[r.n_estaciones == 0]
    if len(vacios):
        print("Municipios SIN estaciones y su más cercana:")
        print(vacios[["cve_mun", "municipio", "mas_cercana",
                      "mas_cercana_km"]].to_string(index=False))
    d = discrepancias()
    if len(d):
        print(f"\n{len(d)} estaciones cuyo municipio declarado no es donde caen:")
        print(d.to_string(index=False))
    print()
    generar(dir_salida=a.dir, con_base=not a.sin_base,
            cobertura_min=a.cobertura_min)
