"""
Mapas estáticos (PNG) del análisis urbano.

Cuatro figuras, cada una responde una pregunta distinta:

  1. `mapa_estatal.png`      ¿dónde están las 63 manchas urbanas dentro de la
                             malla de 4384 nodos, y cuáles quedan bien cubiertas?
  2. `panel_ciudades.png`    ¿cómo se ve el traslape celda↔mancha en las 12
                             ciudades más grandes? (una lámina por ciudad, con
                             barra de escala para que el tamaño sea comparable)
  3. `panel_ciudades_chicas.png`  lo mismo para las 12 más chicas: es la figura
                             que hace visible el problema de resolución —la
                             mancha es un punto dentro de una celda de 18 km².
  4. `mapa_conglomerados.png`  detalle de las conurbaciones (Tampico–Madero–
                             Miramar–Altamira y las demás de varias localidades).

De cada una se generan DOS versiones:

- **Esquemática** (`*.png`): fondo liso. Es la que aísla lo que importa —la
  geometría relativa mancha/celda— sin ruido, y se rinde sin red.
- **Sobre mapa base** (`*_base.png`): la misma capa naranja encima de un mosaico
  de referencia de OpenStreetMap, con carreteras, calles y nombres. Sirve para
  *ubicarse*: reconocer la ciudad, ver por dónde entra la carretera federal, o
  verificar que la mancha del INEGI coincide con la traza real.

La segunda necesita red la primera vez (después usa `cache/tiles/`) y va en
EPSG:3857, que es el CRS de los mosaicos. Si la red falla, la figura se genera
igual sin fondo en vez de tumbar la corrida.
"""
from __future__ import annotations
import os
import textwrap

import geopandas as gpd
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.lines import Line2D
from matplotlib.patches import Patch

from urbano import config as C
from urbano.data import manchas as M
from urbano.mapas import estilo as E
from urbano.nodos import asignacion as A


def _proy(gdf: gpd.GeoDataFrame, base: bool) -> gpd.GeoDataFrame:
    """Al CRS del mosaico (3857) si hay mapa base; si no, se queda en 6372."""
    return gdf.to_crs(C.CRS_MAPA) if base else gdf


def _alfa_mancha(base: bool) -> float:
    """Sobre el mosaico la mancha va traslúcida: si no, tapa justo las calles."""
    return 0.42 if base else 0.95


def meta_estandar(info, ciudad) -> str:
    """
    Renglón bajo el título: área, nodos, calidad y —si toca— el municipio.

    El municipio se rotula solo cuando la localidad NO es la cabecera. Es el
    caso de Miramar: es una localidad urbana del municipio de Altamira, distinta
    de la cabecera (que también se llama Altamira y sale en su propia lámina).
    Sin el rótulo el panel parece decir que son dos municipios. En las cabeceras
    se omite, porque "Ciudad Victoria · mun. Victoria" no informa de nada.
    """
    n = int(info["n_nodos_ciudad"])
    sufijo = "" if info["es_cabecera"] else f" · loc. del mun. {info['municipio']}"
    return (f"{ciudad['area_km2']:.1f} km² · {n} nodo{'s' if n > 1 else ''} · "
            f"{info['calidad']}{sufijo}")


def meta_cabecera(info, ciudad) -> str:
    """Para el catálogo de cabeceras: antepone la clave INEGI del municipio."""
    n = int(info["n_nodos_ciudad"])
    return (f"mun. {info['cve_mun']} · {ciudad['area_km2']:.1f} km² · "
            f"{n} nodo{'s' if n > 1 else ''} · {info['calidad']}")


def meta_otra_localidad(info, ciudad) -> str:
    """Para el catálogo de localidades no cabecera: el municipio va primero."""
    n = int(info["n_nodos_ciudad"])
    return (f"mun. {info['municipio']} ({info['cve_mun']}) · "
            f"{ciudad['area_km2']:.1f} km² · {n} nodo{'s' if n > 1 else ''} · "
            f"{info['calidad']}")


def _celdas_de(pares: pd.DataFrame, celdas: gpd.GeoDataFrame,
               cvegeo: str) -> gpd.GeoDataFrame:
    sub = pares[pares["cvegeo"] == cvegeo]
    g = celdas[celdas["nodo_id"].isin(sub["nodo_id"])].copy()
    return g.merge(sub[["nodo_id", "peso"]], on="nodo_id", how="left")


def _leyenda_calidad(ax, loc="lower right", extra=()) -> None:
    manijas = [
        Patch(facecolor=E.MANCHA, edgecolor=E.MANCHA_BORDE,
              label="Mancha urbana (INEGI)"),
        *[Line2D([], [], marker="o", ls="none", ms=6, mec="white", mew=0.6,
                 mfc=E.CALIDAD[c], label=f"Nodo · cobertura {c}")
          for c in E.ORDEN_CALIDAD],
        Line2D([], [], marker="o", ls="none", ms=3, mfc=E.NODO_FUERA,
               mec="none", label="Nodo sin ciudad"),
        *extra,
    ]
    leg = ax.legend(handles=manijas, loc=loc, frameon=True, fontsize=8,
                    facecolor=E.SUPERFICIE, edgecolor=E.RETICULA,
                    labelcolor=E.TINTA_2)
    leg.get_frame().set_linewidth(0.8)


def _etiquetar(ax, urb, n: int = 10) -> None:
    """
    Etiqueta las mayores aglomeraciones sin que los nombres se encimen.

    Dos decisiones: se etiqueta UNA vez por conglomerado (si no, Tampico, Madero,
    Miramar y Altamira apilan cuatro nombres sobre el mismo punto), y cada
    etiqueta se empuja verticalmente hasta que su caja deja de chocar con las ya
    colocadas, con una línea guía al punto real cuando se movió.
    """
    porconglo = (urb.sort_values("area_km2", ascending=False)
                 .drop_duplicates("nombre_conglomerado").head(n))
    y0, y1 = ax.get_ylim()
    alto = (y1 - y0) * 0.016          # alto aproximado de la caja de texto
    ancho_car = (y1 - y0) * 0.0085    # ancho aproximado por carácter
    colocadas: list[tuple[float, float, float, float]] = []

    for _, r in porconglo.iterrows():
        cen = r.geometry.centroid
        etiqueta = r["nombre_conglomerado"]
        w = len(etiqueta) * ancho_car
        x = cen.x + (y1 - y0) * 0.006
        y = cen.y + (y1 - y0) * 0.006
        for _ in range(40):           # empuja hacia arriba hasta liberar hueco
            caja = (x, y - alto / 2, x + w, y + alto / 2)
            if not any(caja[0] < c[2] and c[0] < caja[2] and
                       caja[1] < c[3] and c[1] < caja[3] for c in colocadas):
                break
            y += alto * 1.15
        colocadas.append((x, y - alto / 2, x + w, y + alto / 2))
        movida = abs(y - cen.y) > (y1 - y0) * 0.02
        ax.annotate(
            etiqueta, xy=(cen.x, cen.y), xytext=(x, y), fontsize=8,
            color=E.TINTA, va="center", ha="left", zorder=6,
            bbox=dict(boxstyle="round,pad=0.18", fc=E.SUPERFICIE,
                      ec=E.RETICULA, lw=0.5, alpha=0.92),
            arrowprops=dict(arrowstyle="-", lw=0.6, color=E.BORDE,
                            shrinkA=0, shrinkB=2) if movida else None)


# --------------------------------------------------------------------------- #
# 1. Estatal
# --------------------------------------------------------------------------- #
def mapa_estatal(urb, nodos, pares, res, ruta: str, base: bool = False) -> str:
    E.aplicar_estilo()
    mun = _proy(M.municipios(), base)
    urb = _proy(urb, base)
    nodos = _proy(nodos, base)

    # Cada nodo hereda la MEJOR calidad entre las ciudades que toca.
    rango = {"alta": 3, "media": 2, "baja": 1}
    mejor = (pares.assign(r=pares["calidad"].map(rango))
             .sort_values("r", ascending=False)
             .drop_duplicates("nodo_id").set_index("nodo_id")["calidad"])
    n = nodos.copy()
    n["calidad"] = n["nodo_id"].map(mejor)

    fig, ax = plt.subplots(figsize=(8.5, 12))
    # Sobre el mosaico los municipios NO se rellenan: taparían el mapa entero.
    mun.plot(ax=ax, facecolor="none" if base else "white",
             edgecolor=E.RETICULA, lw=0.6, zorder=1)
    mun.dissolve().boundary.plot(ax=ax, color=E.BORDE, lw=1.2, zorder=2)

    fuera = n[n["calidad"].isna()]
    ax.scatter(fuera.geometry.x, fuera.geometry.y, s=1.6, c=E.NODO_FUERA,
               linewidths=0, zorder=3)
    for cal in E.ORDEN_CALIDAD[::-1]:
        sub = n[n["calidad"] == cal]
        ax.scatter(sub.geometry.x, sub.geometry.y, s=15, c=E.CALIDAD[cal],
                   edgecolors="white", linewidths=0.4, zorder=4)

    urb.plot(ax=ax, facecolor=E.MANCHA, edgecolor=E.MANCHA_BORDE, lw=0.4,
             alpha=_alfa_mancha(base), zorder=5)

    _etiquetar(ax, urb)

    E.limpiar_ejes(ax)
    if base:
        E.add_mapa_base(ax, mun.crs, zoom=8)
    E.barra_escala(ax, 50, web_mercator=base)
    n_asig = pares["nodo_id"].nunique()
    ax.set_title(
        "Manchas urbanas de Tamaulipas y nodos NSRDB que las cubren"
        + (" · sobre mapa base" if base else "") + "\n",
        loc="left", fontsize=13)
    ax.text(0, 1.005, f"{len(urb)} localidades urbanas (Marco Geoestadístico INEGI "
            f"{C.EDICION_MG}) · {n_asig} de {len(nodos)} nodos asignados · "
            f"malla {C.PASO_MALLA}° ≈ 4 km",
            transform=ax.transAxes, fontsize=8.5, color=E.TINTA_2, va="bottom")
    _leyenda_calidad(ax, loc="upper right")
    fig.savefig(ruta)
    plt.close(fig)
    return ruta


# --------------------------------------------------------------------------- #
# 2 y 3. Paneles de ciudades
# --------------------------------------------------------------------------- #
def panel_ciudades(urb, nodos, pares, ruta: str, cvegeos: list[str],
                   titulo: str, subtitulo: str | None = None,
                   ncols: int = 4, base: bool = False, meta=None,
                   resaltar: dict | None = None) -> str:
    """
    Rejilla de láminas, una por ciudad, en el orden en que llegan `cvegeos`.

    `meta` permite cambiar el renglón de datos bajo cada título; recibe la fila
    de `pares` y la de `urb`, y devuelve el texto. Por omisión da
    "área · nodos · calidad".

    `resaltar` es un dict `{cvegeo: nodo_id}`. La lámina de esa ciudad marca ese
    nodo con un anillo y deja los demás atenuados, y solo dibuja con trazo firme
    la celda del nodo marcado. Sirve para responder "¿de qué punto exacto salen
    estos datos?" sin cambiar el encuadre, de modo que la lámina siga siendo
    comparable con la del panel completo.

    El alto de la figura escala con el número de renglones, así que una página
    incompleta conserva el mismo tamaño de lámina que las demás sin necesidad de
    rellenarla con ejes vacíos.
    """
    E.aplicar_estilo()
    celdas = _proy(A.celdas_nodos(nodos), base)
    urb = _proy(urb, base)
    nodos = _proy(nodos, base)
    filas = int(np.ceil(len(cvegeos) / ncols))
    # El mosaico llena la caja de lado a lado (el fondo liso deja márgenes
    # blancos que hacían de separación), así que la versión con mapa base
    # necesita más alto por fila o el título choca con la lámina de arriba.
    alto_fila = 3.9 if base else 3.5
    fig, axes = plt.subplots(filas, ncols,
                             figsize=(3.2 * ncols, alto_fila * filas))
    axes = np.atleast_1d(axes).ravel()

    for ax, cve in zip(axes, cvegeos):
        ciudad = urb[urb["cvegeo"] == cve]
        cel = _celdas_de(pares, celdas, cve)
        filas_ciudad = pares[pares["cvegeo"] == cve]
        # Cuando hay un nodo resaltado, la lámina va de ESE nodo: el renglón de
        # datos tiene que describirlo a él, no a la primera fila que aparezca de
        # la ciudad (que es otro nodo cualquiera y mostraría su id y su peso).
        marcado_info = (resaltar or {}).get(cve)
        if marcado_info is None:
            info = filas_ciudad.iloc[0]
        else:
            coincide = filas_ciudad[filas_ciudad["nodo_id"] == marcado_info]
            if coincide.empty:
                raise ValueError(
                    f"El nodo {marcado_info} no está asignado a {cve}; sus "
                    f"nodos son {sorted(filas_ciudad['nodo_id'])}.")
            info = coincide.iloc[0]

        # El encuadre lo fijan las celdas —así se ve cuánto de la celda es campo
        # y no ciudad—, unidas a la mancha para no recortarla nunca.
        b_cel, b_ciu = cel.total_bounds, ciudad.total_bounds
        minx, miny = np.minimum(b_cel[:2], b_ciu[:2])
        maxx, maxy = np.maximum(b_cel[2:], b_ciu[2:])
        # Ventana CUADRADA centrada en el contenido: con aspecto equal, un
        # encuadre apaisado y uno vertical dan cajas de distinta altura y los
        # títulos del panel dejan de alinearse entre sí.
        lado = max(maxx - minx, maxy - miny) * 1.12
        cx, cy = (minx + maxx) / 2, (miny + maxy) / 2
        minx, maxx = cx - lado / 2, cx + lado / 2
        miny, maxy = cy - lado / 2, cy + lado / 2
        margen = 0.0
        marcado_cel = (resaltar or {}).get(cve)
        if marcado_cel is None:
            cel.plot(ax=ax, facecolor="none", edgecolor=E.CELDA, lw=0.9,
                     ls="--", zorder=2)
        else:
            # En una ciudad de un solo nodo no hay "otras" celdas que atenuar.
            otras_cel = cel[cel["nodo_id"] != marcado_cel]
            if len(otras_cel):
                otras_cel.plot(ax=ax, facecolor="none", edgecolor=E.CELDA,
                               lw=0.6, ls="--", alpha=0.35, zorder=2)
            cel[cel["nodo_id"] == marcado_cel].plot(
                ax=ax, facecolor="none", edgecolor=E.RESALTE, lw=1.8,
                zorder=3.5)
        # El relleno de la celda gradúa el peso: cuánta ciudad aporta cada nodo.
        # Sobre el mosaico se omite —dos capas traslúcidas encima de las calles
        # las vuelven ilegibles—; ahí el peso lo lleva solo el borde punteado.
        if not base:
            cel.plot(ax=ax, column="peso", cmap="Blues", vmin=0, vmax=1,
                     alpha=0.35, edgecolor="none", zorder=1)
        ciudad.plot(ax=ax, facecolor=E.MANCHA, edgecolor=E.MANCHA_BORDE,
                    lw=0.7, alpha=_alfa_mancha(base), zorder=3)
        pts = nodos[nodos["nodo_id"].isin(cel["nodo_id"])]
        marcado = (resaltar or {}).get(cve)
        if marcado is None:
            ax.scatter(pts.geometry.x, pts.geometry.y, s=26,
                       c=E.CALIDAD[info["calidad"]], edgecolors="white",
                       linewidths=0.7, zorder=4)
        else:
            otros = pts[pts["nodo_id"] != marcado]
            uno = pts[pts["nodo_id"] == marcado]
            if uno.empty:
                raise ValueError(
                    f"El nodo {marcado} no está asignado a {info['ciudad']} "
                    f"({cve}); sus nodos son {sorted(cel['nodo_id'])}.")
            ax.scatter(otros.geometry.x, otros.geometry.y, s=18,
                       c=E.NODO_FUERA, edgecolors="white", linewidths=0.5,
                       zorder=4)
            # Halo blanco debajo del anillo: el resalte tiene que leerse igual
            # sobre el mosaico, sobre la mancha naranja y sobre el fondo liso.
            for radio, color, ancho in ((330, "white", 5.0),
                                        (330, E.RESALTE, 2.6)):
                ax.scatter(uno.geometry.x, uno.geometry.y, s=radio,
                           facecolors="none", edgecolors=color,
                           linewidths=ancho, zorder=5)
            ax.scatter(uno.geometry.x, uno.geometry.y, s=30, c=E.RESALTE,
                       edgecolors="white", linewidths=0.8, zorder=6)

        E.limpiar_ejes(ax)
        ax.set_xlim(minx - margen, maxx + margen)
        ax.set_ylim(miny - margen, maxy + margen)
        ancho_km = (maxx - minx) / 1000
        if base:
            E.add_mapa_base(ax, cel.crs)
        E.barra_escala(ax, 5 if ancho_km > 14 else 2, web_mercator=base)
        ax.set_title(f"{info['ciudad']}", loc="left", fontsize=10, pad=18)
        ax.text(0, 1.008, (meta or meta_estandar)(info, ciudad.iloc[0]),
                transform=ax.transAxes, fontsize=7.5, color=E.TINTA_2, va="bottom")

    for ax in axes[len(cvegeos):]:
        ax.set_visible(False)

    if resaltar:
        manijas = [
            Patch(facecolor=E.MANCHA, edgecolor=E.MANCHA_BORDE,
                  label="Mancha urbana"),
            Line2D([], [], marker="o", ls="none", ms=11, mfc="none",
                   mec=E.RESALTE, mew=2.2, label="Nodo seleccionado y su celda"),
            Line2D([], [], marker="o", ls="none", ms=6, mfc=E.NODO_FUERA,
                   mec="white", label="Otros nodos de la ciudad"),
        ]
    else:
        manijas = [
            Patch(facecolor=E.MANCHA, edgecolor=E.MANCHA_BORDE,
                  label="Mancha urbana"),
            Patch(facecolor="none" if base else "#c6dbef", edgecolor=E.CELDA,
                  ls="--",
                  label="Celda del nodo (0.04°, ~18 km²)"
                        + ("" if base else "; tono = peso")),
            Line2D([], [], marker="o", ls="none", ms=7, mfc=E.CALIDAD["alta"],
                   mec="white", label="Nodo NSRDB (color = cobertura de la ciudad)"),
        ]
    # La leyenda en una sola fila mide ~7 pulgadas; en un panel de una columna
    # (3.2") eso estiraría la figura entera, así que se apila.
    n_leyenda = min(len(manijas), max(1, ncols))
    # Anclada por su borde SUPERIOR al pie de la figura, así queda entera por
    # fuera y `bbox_inches="tight"` la recoge al guardar. Anclarla por el borde
    # inferior la metía dentro del área de los mapas cuando se apila en varias
    # filas (paneles de una sola columna).
    fig.legend(handles=manijas, loc="upper center", ncol=n_leyenda, frameon=False,
               fontsize=9, labelcolor=E.TINTA_2, bbox_to_anchor=(0.5, 0.0))

    # Título y subtítulo se colocan en PULGADAS desde el borde, no en fracción
    # de figura: una fracción fija equivale a muy pocos puntos en una figura
    # baja, y el título de 13 pt acababa encimado con el subtítulo de 9 pt.
    ancho_pulg, alto_pulg = fig.get_size_inches()
    if subtitulo:
        # ~11 caracteres por pulgada a 9 pt; se parte para no desbordar.
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


# --------------------------------------------------------------------------- #
# 4. Conglomerados
# --------------------------------------------------------------------------- #
def mapa_conglomerados(urb, nodos, pares, ruta: str, base: bool = False) -> str:
    E.aplicar_estilo()
    celdas = _proy(A.celdas_nodos(nodos), base)
    urb = _proy(urb, base)
    nodos = _proy(nodos, base)
    multi = (urb.groupby("nombre_conglomerado")["cvegeo"].count()
             .sort_values(ascending=False))
    grupos = [g for g, k in multi.items() if k > 1]

    ncols = 3
    filas = int(np.ceil(len(grupos) / ncols))
    fig, axes = plt.subplots(filas, ncols,
                             figsize=(4.2 * ncols, (4.7 if base else 4.3) * filas))
    axes = np.atleast_1d(axes).ravel()
    cmap = plt.get_cmap("Oranges")

    for ax, nombre in zip(axes, grupos):
        g = urb[urb["nombre_conglomerado"] == nombre].sort_values(
            "area_km2", ascending=False)
        cel = celdas[celdas["nodo_id"].isin(
            pares.loc[pares["cvegeo"].isin(g["cvegeo"]), "nodo_id"])]
        cel.plot(ax=ax, facecolor="none", edgecolor=E.CELDA, lw=0.7,
                 ls="--", zorder=2)
        for i, (_, r) in enumerate(g.iterrows()):
            # Rampa de un solo tono, ordenada por tamaño: la localidad mayor
            # es la más oscura, para que el peso visual siga al peso real.
            col = cmap(0.92 - 0.45 * i / max(len(g) - 1, 1))
            gpd.GeoSeries([r.geometry], crs=urb.crs).plot(
                ax=ax, facecolor=col, edgecolor=E.MANCHA_BORDE, lw=0.6,
                alpha=_alfa_mancha(base), zorder=3)
            cen = r.geometry.centroid
            ax.annotate(r["ciudad"], (cen.x, cen.y), fontsize=7.5,
                        ha="center", color=E.TINTA, zorder=5,
                        bbox=dict(boxstyle="round,pad=0.16", fc=E.SUPERFICIE,
                                  ec=E.RETICULA, lw=0.5, alpha=0.9))
        pts = nodos[nodos["nodo_id"].isin(cel["nodo_id"])]
        ax.scatter(pts.geometry.x, pts.geometry.y, s=22, c=E.CALIDAD["media"],
                   edgecolors="white", linewidths=0.6, zorder=4)
        E.limpiar_ejes(ax)
        minx, miny, maxx, maxy = cel.total_bounds
        lado = max(maxx - minx, maxy - miny) * 1.10
        cx, cy = (minx + maxx) / 2, (miny + maxy) / 2
        ax.set_xlim(cx - lado / 2, cx + lado / 2)
        ax.set_ylim(cy - lado / 2, cy + lado / 2)
        if base:
            E.add_mapa_base(ax, cel.crs)
        E.barra_escala(ax, 5, web_mercator=base)
        ax.set_title(f"Conglomerado {nombre}", loc="left", fontsize=10, pad=18)
        ax.text(0, 1.008, f"{len(g)} localidades · {g['area_km2'].sum():.1f} km² · "
                f"{cel['nodo_id'].nunique()} nodos",
                transform=ax.transAxes, fontsize=7.5, color=E.TINTA_2, va="bottom")

    for ax in axes[len(grupos):]:
        ax.set_visible(False)
    fig.tight_layout(rect=[0, 0, 1, 0.930], h_pad=3.5 if base else 1.08)
    fig.suptitle("Conglomerados urbanos: manchas a menos de 2 km entre sí",
                 x=0.02, ha="left", fontsize=13, fontweight="bold", y=0.992)
    fig.text(0.02, 0.955,
             "Alternativa data-driven a la lista oficial de zonas metropolitanas. "
             "Permite reportar métricas por localidad o por conurbación.",
             ha="left", fontsize=9, color=E.TINTA_2)
    fig.savefig(ruta)
    plt.close(fig)
    return ruta


# --------------------------------------------------------------------------- #
def generar_todos(urb, nodos, pares, res, dir_salida: str | None = None,
                  con_base: bool = True) -> list[str]:
    """
    Las cuatro figuras, en sus dos versiones.

    `con_base=False` salta las de mosaico: útil sin red, o cuando solo se quiere
    regenerar rápido la parte esquemática (el mosaico es lo que tarda).
    """
    d = dir_salida or C.DIR_SALIDA_MAPAS
    os.makedirs(d, exist_ok=True)
    grandes = res.head(12)["cvegeo"].tolist()
    chicas = res.tail(12)["cvegeo"].tolist()[::-1]

    T_GRANDES = "Las 12 ciudades más grandes frente a la malla NSRDB"
    T_CHICAS = "Las 12 localidades urbanas más chicas frente a la malla NSRDB"
    S_CHICAS = ("Aquí la mancha cabe entera dentro de una celda: la métrica "
                "\"de la ciudad\" es en realidad la del nodo que la contiene, "
                "sin detalle interno.")

    rutas = []
    for base in ([False, True] if con_base else [False]):
        sfx = "_base" if base else ""
        etq = " (sobre mapa base)" if base else ""
        rutas += [
            mapa_estatal(urb, nodos, pares, res,
                         os.path.join(d, f"mapa_estatal{sfx}.png"), base=base),
            panel_ciudades(urb, nodos, pares,
                           os.path.join(d, f"panel_ciudades{sfx}.png"), grandes,
                           T_GRANDES + etq, base=base),
            panel_ciudades(urb, nodos, pares,
                           os.path.join(d, f"panel_ciudades_chicas{sfx}.png"),
                           chicas, T_CHICAS + etq, S_CHICAS, base=base),
            mapa_conglomerados(urb, nodos, pares,
                               os.path.join(d, f"mapa_conglomerados{sfx}.png"),
                               base=base),
        ]
    return rutas


if __name__ == "__main__":
    urb = M.manchas_urbanas()
    nodos = A.cargar_nodos()
    pares = A.asignar(urb, nodos)
    res = A.resumen(pares, urb)
    import sys
    for r in generar_todos(urb, nodos, pares, res,
                           con_base="--sin-base" not in sys.argv):
        print("[mapa]", r)
