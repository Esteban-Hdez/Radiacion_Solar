"""
Estaciones Meteorológicas Automáticas (EMAS) del SMN en Tamaulipas.

    conda run -n rs python -m smn.emas          # la información
    conda run -n rs python -m smn.emas --mapa   # además, el mapa

Otra red distinta de la convencional: **cinco** estaciones, cada **10 minutos**,
y solo los **últimos 90 días** —el SMN no publica histórico por este canal—.
Frente a las 117 convencionales con seis años de dato diario, esto es una
ventana estrecha; lo que la hace valiosa es otra cosa:

## Son la única medición de radiación solar del proyecto

Las EMAS traen **`Radiación Solar (W/m²)`** medida in situ. El NSRDB la estima
desde satélite y ERA5 la modela: estas cinco son el único dato de superficie
contra el que contrastar ambas. Esa es su razón de estar aquí, no la
meteorología general.

## Tres trampas del formato, todas comprobadas

1. **El orden de las columnas NO es el mismo en los cinco archivos.** Barra del
   Tordo, Ciudad Mante y Villagrán abren por viento; Ciudad Victoria y Tampico,
   por temperatura. Leer por posición mezclaría humedad con presión sin que nada
   fallara, así que aquí se lee SIEMPRE por nombre.
2. **La noche se codifica de dos maneras.** Ciudad Mante y Tampico dejan la
   radiación nocturna vacía; Ciudad Victoria y Villagrán escriben 0. Un
   `dropna()` ingenuo borraría media serie en dos estaciones y ninguna en las
   otras dos. `cargar()` normaliza la noche a 0 y deja constancia en
   `rad_nocturna_nula`.
3. **La presión de Ciudad Victoria es 0 en los 11 437 registros.** El barómetro
   no reporta; el cero no es una lectura. Se convierte a NaN al cargar, porque
   promediarlo da 0 sin avisar.

4. **Ciudad Victoria marca ~52 W/m² de radiación DE NOCHE**, cuando el valor
   real es 0 en cualquier estación del año; las otras cuatro dan 0. Es el
   desplazamiento de cero de su piranómetro, y se está sumando también a sus
   lecturas diurnas —lo que explica que tenga el máximo más alto de las cinco
   (1311 W/m²)—. `resumen()` lo mide en `rad_offset_noche` y el CLI avisa.

## Los metadatos van en la cabecera, no en el nombre del archivo

Las primeras nueve líneas traen estación, municipio, latitud, longitud y
altitud. El nombre del archivo es una pista, no el dato — y aquí engaña por
partida doble: la EMA llamada **TAMPICO** no está en Tampico (queda unos 50 km
al norte), el SMN la declara en **Altamira**, y sus coordenadas caen dentro del
polígono de **Aldama**, a 5.3 km del límite con Altamira. Por eso el municipio
se resuelve por geometría en `ubicar()`, y la discrepancia se reporta en vez de
elegir en silencio.
"""
from __future__ import annotations
import argparse
import csv
import glob
import os

import numpy as np
import pandas as pd

from smn import config as C

# Nombre corto de cada variable -> fragmento que la identifica en la cabecera.
# Se busca por subcadena porque los encabezados varían entre archivos (uno trae
# "Dirección del Viento" sin "(grados)").
COLUMNAS = {
    "temperatura_c": "Temperatura",
    "precipitacion_mm": "Precipitación",
    "humedad_rel": "Humedad",
    "presion_hpa": "Presión",
    "radiacion_wm2": "Radiación",
    "dir_viento": "Dirección del Viento",
    "vel_viento_kmh": "Rapidez de viento",
    "dir_rafaga": "Dirección de ráfaga",
    "vel_rafaga_kmh": "Rapidez de ráfaga",
}

# Filas de la cabecera antes de los encabezados de columna.
FILAS_CABECERA = 9

# Horas locales que se consideran "de día" para separar los huecos nocturnos
# —que son convención— de los diurnos, que sí son pérdida de dato.
HORAS_DIA = (9, 16)
# Horas centradas en la madrugada: ahí el GHI real es 0 en cualquier estación
# del año, así que lo que marque el sensor es su offset.
HORAS_NOCHE = (22, 23, 0, 1, 2, 3)


def archivos() -> list[str]:
    return sorted(glob.glob(os.path.join(C.DIR_EMAS, "*.csv")))


# --------------------------------------------------------------------------- #
# Cabecera
# --------------------------------------------------------------------------- #
def _cabecera(ruta: str) -> dict:
    """Los metadatos de las primeras líneas: estación, municipio, coordenadas."""
    campos = {}
    with open(ruta, encoding="utf-8-sig", newline="") as f:
        for fila in csv.reader(f):
            if not fila or len(fila) < 2:
                continue
            clave = fila[0].strip().lower()
            if clave.startswith("estaci"):
                campos["estacion"] = fila[1].strip()
            elif clave == "municipio":
                campos["municipio"] = fila[1].strip()
            elif clave == "latitud":
                campos["latitud"] = float(fila[1])
            elif clave == "longitud":
                campos["longitud"] = float(fila[1])
            elif clave == "altitud":
                campos["altitud_msnm"] = float(fila[1])
            if len(campos) == 5:
                break
    campos["archivo"] = os.path.basename(ruta)
    return campos


def metadatos() -> pd.DataFrame:
    """Las cinco EMAS con su municipio declarado y sus coordenadas."""
    return pd.DataFrame([_cabecera(r) for r in archivos()]).sort_values(
        "estacion").reset_index(drop=True)


# --------------------------------------------------------------------------- #
# Datos
# --------------------------------------------------------------------------- #
def cargar(ruta: str) -> pd.DataFrame:
    """
    La serie de 10 minutos de una EMA, con columnas normalizadas.

    Se resuelve cada columna POR NOMBRE (ver el docstring del módulo: el orden
    cambia entre archivos). Además:

    - la radiación nocturna vacía se pone a 0, para que las cinco estaciones
      signifiquen lo mismo;
    - la presión idénticamente 0 de una estación se pasa a NaN, porque es un
      sensor apagado y no una lectura.
    """
    meta = _cabecera(ruta)
    d = pd.read_csv(ruta, skiprows=FILAS_CABECERA, encoding="utf-8-sig")
    d.columns = [c.strip() for c in d.columns]

    fuera = {}
    for corto, trozo in COLUMNAS.items():
        halladas = [c for c in d.columns if trozo.lower() in c.lower()]
        if halladas:
            fuera[corto] = pd.to_numeric(d[halladas[0]], errors="coerce")
    out = pd.DataFrame(fuera)
    out.insert(0, "fecha_local", pd.to_datetime(d["Fecha Local"]))
    out.insert(1, "fecha_utc", pd.to_datetime(d["Fecha UTC"], utc=True))
    out.insert(0, "estacion", meta["estacion"])

    if "radiacion_wm2" in out:
        noche = ~out["fecha_local"].dt.hour.between(*HORAS_DIA)
        out["radiacion_wm2"] = out["radiacion_wm2"].mask(
            noche & out["radiacion_wm2"].isna(), 0.0)
    # Un sensor que devuelve 0 en el 100 % de los registros no está midiendo.
    for v in ("presion_hpa",):
        if v in out and (out[v] == 0).all():
            out[v] = np.nan
    return out.sort_values("fecha_local").reset_index(drop=True)


def cargar_todas() -> pd.DataFrame:
    """Las cinco series apiladas, con `estacion` como identificador."""
    return pd.concat([cargar(r) for r in archivos()], ignore_index=True)


# --------------------------------------------------------------------------- #
# Información
# --------------------------------------------------------------------------- #
def resumen(d: pd.DataFrame | None = None) -> pd.DataFrame:
    """
    Una fila por EMA: periodo, pasos, cobertura y estado de sus sensores.

    `cobertura` son los pasos de 10 minutos presentes sobre los esperados entre
    su primera y su última lectura; `dias_sin_reportar` mide contra la lectura
    más reciente de TODA la red, que es lo que delata a una estación caída.
    """
    d = cargar_todas() if d is None else d
    meta = metadatos().set_index("estacion")
    fin_red = d["fecha_local"].max()
    filas = []
    for est, g in d.groupby("estacion"):
        lo, hi = g["fecha_local"].min(), g["fecha_local"].max()
        esperados = int((hi - lo).total_seconds() // 600) + 1
        dia = g["fecha_local"].dt.hour.between(*HORAS_DIA)
        fila = {
            "estacion": est,
            "municipio": meta.loc[est, "municipio"],
            "altitud_msnm": meta.loc[est, "altitud_msnm"],
            "primera": lo, "ultima": hi,
            "pasos": len(g), "esperados": esperados,
            "cobertura": round(len(g) / esperados * 100, 1),
            "dias_sin_reportar": int((fin_red - hi).days),
            "rad_max": (round(float(g["radiacion_wm2"].max()), 0)
                        if "radiacion_wm2" in g else np.nan),
            # De noche el GHI es 0 por definición. Lo que mida el piranómetro a
            # las 2 de la mañana es su desplazamiento de cero, y se le está
            # sumando a TODAS las lecturas del día.
            "rad_offset_noche": (
                round(float(g.loc[g["fecha_local"].dt.hour.isin(HORAS_NOCHE),
                                  "radiacion_wm2"].median()), 1)
                if "radiacion_wm2" in g else np.nan),
            "rad_nula_dia": int(g.loc[dia, "radiacion_wm2"].isna().sum())
                            if "radiacion_wm2" in g else 0,
            "sensores_muertos": ", ".join(
                v for v in ("presion_hpa", "radiacion_wm2", "temperatura_c")
                if v in g and g[v].isna().all()) or "—",
        }
        filas.append(fila)
    return pd.DataFrame(filas).sort_values("cobertura",
                                           ascending=False).reset_index(drop=True)


def ciclo_diario(d: pd.DataFrame | None = None) -> pd.DataFrame:
    """Radiación media por hora local y estación. El control de cordura."""
    d = cargar_todas() if d is None else d
    return (d.groupby(["estacion", d["fecha_local"].dt.hour])["radiacion_wm2"]
            .mean().unstack(0).round(0).rename_axis("hora local"))


# --------------------------------------------------------------------------- #
# Ubicación: a qué municipio y a qué cabecera corresponde cada EMA
# --------------------------------------------------------------------------- #
def ubicar() -> "pd.DataFrame":
    """
    Cada EMA con el municipio donde CAE y la cabecera de ese municipio.

    El municipio se resuelve por geometría, no por el nombre del archivo ni por
    el campo del SMN: la EMA llamada TAMPICO está en el municipio de Altamira, y
    su cabecera es la ciudad de Altamira.
    """
    import geopandas as gpd
    from urbano import config as UC
    from urbano.data import manchas as M

    m = metadatos()
    g = gpd.GeoDataFrame(
        m, geometry=gpd.points_from_xy(m["longitud"], m["latitud"]),
        crs=UC.CRS_GEO).to_crs(UC.CRS_METRICO)
    mun = M.municipios()[["CVE_MUN", "municipio", "geometry"]].rename(
        columns={"municipio": "mun_geo"})
    g = gpd.sjoin(g, mun, how="left", predicate="within").drop(
        columns=["index_right"], errors="ignore")

    urb = M.manchas_urbanas()
    cab = urb[urb["es_cabecera"]].set_index("cve_mun")
    g["cabecera"] = g["CVE_MUN"].map(cab["ciudad"])
    g["cabecera_cvegeo"] = g["CVE_MUN"].map(cab["cvegeo"])
    # Distancia de la EMA a la mancha urbana de su propia cabecera: dice si la
    # estación está EN la ciudad o en otro punto del municipio.
    cab_m = urb[urb["es_cabecera"]].set_index("cve_mun").to_crs(UC.CRS_METRICO)
    g["km_a_cabecera"] = [
        round(float(cab_m.loc[cve].geometry.distance(pt) / 1000), 1)
        if cve in cab_m.index else np.nan
        for cve, pt in zip(g["CVE_MUN"], g.geometry)]
    return g


# --------------------------------------------------------------------------- #
# Mapa
# --------------------------------------------------------------------------- #
def mapa_emas(ruta: str | None = None, base: bool = False,
              titulo: str | None = None, subtitulo: str | None = None,
              figsize=(8.5, 12)):
    """
    Las cinco EMAS sobre Tamaulipas, con su cabecera municipal resaltada.

    Cada EMA lleva dos marcas: el punto de la estación y, pintados, el municipio
    al que pertenece y la mancha urbana de su cabecera. A escala estatal una
    mancha urbana mide poco más que el propio punto, así que el municipio
    coloreado es lo que hace visible la correspondencia.
    """
    import matplotlib.pyplot as plt
    from matplotlib.lines import Line2D
    from matplotlib.patches import Patch
    from urbano import config as UC
    from urbano.data import manchas as M
    from urbano.mapas import estilo as E

    E.aplicar_estilo()
    g = ubicar()
    r = resumen().set_index("estacion")
    mun = M.municipios()
    urb = M.manchas_urbanas()
    cab = urb[urb["es_cabecera"] & urb["cve_mun"].isin(g["CVE_MUN"])]
    mun_ema = mun[mun["CVE_MUN"].isin(g["CVE_MUN"])]
    if base:
        mun, cab, mun_ema = (x.to_crs(UC.CRS_MAPA) for x in (mun, cab, mun_ema))
        g = g.to_crs(UC.CRS_MAPA)

    fig, ax = plt.subplots(figsize=figsize)
    mun.plot(ax=ax, facecolor="none" if base else "white",
             edgecolor=E.RETICULA, lw=0.6, zorder=1)
    # El municipio de cada EMA, en el azul claro de la rampa: es el "contenedor"
    # que hace visible a qué cabecera corresponde la estación.
    mun_ema.plot(ax=ax, facecolor="none" if base else "#dbe7f7",
                 edgecolor=E.CALIDAD["media"], lw=1.1, zorder=2,
                 alpha=0.9 if not base else 1.0)
    mun.dissolve().boundary.plot(ax=ax, color=E.BORDE, lw=1.2, zorder=3)
    # La cabecera municipal, en el naranja que el proyecto usa para mancha urbana.
    cab.plot(ax=ax, facecolor=E.MANCHA, edgecolor=E.MANCHA_BORDE, lw=0.8,
             alpha=0.42 if base else 0.95, zorder=4)
    # A escala estatal la mancha de una cabecera chica (Villagrán son 1.3 km²)
    # mide menos que un píxel. Se le añade un marcador en su centroide: un
    # símbolo no exagera el área como haría engordar el polígono.
    cen = cab.geometry.representative_point()
    ax.scatter(cen.x, cen.y, s=30, marker="s", c=E.MANCHA,
               edgecolors=E.MANCHA_BORDE, linewidths=0.7, zorder=5)

    # Línea EMA -> su cabecera cuando no coinciden: dos de las cinco están a más
    # de 25 km de la ciudad que les toca, y sin el trazo no se ve cuál es cuál.
    cab_cen = cab.set_index("cve_mun").geometry.representative_point()
    for _, e in g.iterrows():
        destino = cab_cen.get(e["CVE_MUN"])
        if destino is not None and e["km_a_cabecera"] and e["km_a_cabecera"] > 1:
            ax.plot([e.geometry.x, destino.x], [e.geometry.y, destino.y],
                    color=E.MANCHA_BORDE, lw=0.9, ls=(0, (3, 2)), alpha=0.75,
                    zorder=5.5)

    for _, e in g.iterrows():
        for radio, color, ancho in ((320, "white", 4.4), (320, E.RESALTE, 2.4)):
            ax.scatter([e.geometry.x], [e.geometry.y], s=radio,
                       facecolors="none", edgecolors=color, linewidths=ancho,
                       zorder=6)
        ax.scatter([e.geometry.x], [e.geometry.y], s=40, c=E.RESALTE,
                   edgecolors="white", linewidths=0.9, zorder=7)
        cob = r.loc[e["estacion"], "cobertura"]
        ax.annotate(f"{e['estacion'].title()}\n{e['cabecera']} · {cob:.0f} %",
                    (e.geometry.x, e.geometry.y), xytext=(13, -4),
                    textcoords="offset points", fontsize=8, color=E.TINTA,
                    va="top", zorder=8, linespacing=1.4,
                    bbox=dict(boxstyle="round,pad=0.3", fc=E.SUPERFICIE,
                              ec=E.BORDE, lw=0.5, alpha=0.9))

    E.limpiar_ejes(ax)
    if base:
        E.add_mapa_base(ax, mun.crs, zoom=8)
    E.barra_escala(ax, 50, web_mercator=base)

    if titulo is None:
        titulo = ("Estaciones automáticas (EMAS) del SMN en Tamaulipas"
                  + (" · sobre mapa base" if base else ""))
    if subtitulo is None:
        lo = r["primera"].min()
        hi = r["ultima"].max()
        subtitulo = (
            f"Las {len(g)} EMAS del estado, con su municipio y la mancha urbana "
            f"de la cabecera correspondiente.\nDatos cada 10 minutos, "
            f"{lo:%Y-%m-%d} a {hi:%Y-%m-%d} (solo los últimos 90 días: el SMN no "
            f"publica histórico por este canal).")

    y = 0.985
    if titulo:
        fig.text(0.012, y, titulo, fontsize=13, weight="bold", color=E.TINTA,
                 ha="left", va="top")
        y -= 0.016
    if subtitulo:
        import textwrap
        ancho = int(fig.get_size_inches()[0] * 16)
        subtitulo = "\n".join(
            linea for parrafo in subtitulo.split("\n")
            for linea in textwrap.wrap(parrafo, ancho) or [""])
        fig.text(0.012, y, subtitulo, fontsize=8.5, color=E.TINTA_2,
                 ha="left", va="top", linespacing=1.5)
        y -= 0.014 * (subtitulo.count("\n") + 1)

    manijas = [
        Line2D([], [], marker="o", ls="none", ms=10, mfc=E.RESALTE, mec="white",
               label="EMA (nombre · cabecera · cobertura)"),
        Patch(facecolor="none" if base else "#dbe7f7",
              edgecolor=E.CALIDAD["media"], label="Municipio de la EMA"),
        Patch(facecolor=E.MANCHA, edgecolor=E.MANCHA_BORDE,
              label="Cabecera municipal (■ si es muy pequeña)"),
        Line2D([], [], color=E.MANCHA_BORDE, lw=1.0, ls=(0, (3, 2)),
               label="EMA → su cabecera, si no coinciden"),
    ]
    ax.legend(handles=manijas, loc="upper right", frameon=base, fontsize=8.5,
              labelspacing=0.6)
    fig.subplots_adjust(top=y - 0.005, bottom=0.02, left=0.01, right=0.99)

    ruta = ruta or os.path.join(C.DIR_SALIDA,
                                f"emas_tamaulipas{'_base' if base else ''}.png")
    os.makedirs(os.path.dirname(os.path.abspath(ruta)), exist_ok=True)
    fig.savefig(ruta)
    print(f"[mapa] {ruta}")
    return fig, g


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--mapa", action="store_true")
    ap.add_argument("--base", action="store_true", help="con mosaico de fondo")
    ap.add_argument("--ruta")
    a = ap.parse_args()

    pd.set_option("display.width", 220)
    d = cargar_todas()
    r = resumen(d)
    print(f"\n{len(r)} EMAS · {len(d):,} registros de 10 minutos\n")
    print(r[["estacion", "municipio", "altitud_msnm", "primera", "ultima",
             "pasos", "cobertura", "dias_sin_reportar", "rad_max",
             "rad_offset_noche", "sensores_muertos"]].to_string(index=False))

    sesgadas = r[r["rad_offset_noche"] > 5]
    for _, e in sesgadas.iterrows():
        print(f"\n⚠ {e['estacion']}: el piranómetro marca "
              f"{e['rad_offset_noche']:.0f} W/m² DE NOCHE, cuando el valor real "
              f"es 0. Ese desplazamiento de cero se suma a todas sus lecturas "
              f"diurnas: su radiación no es comparable sin corregirlo.")

    u = ubicar()
    print("\nMunicipio real y cabecera correspondiente:")
    print(u[["estacion", "municipio", "mun_geo", "cabecera",
             "km_a_cabecera"]].to_string(index=False))
    desajuste = u[u["municipio"].str.lower() != u["mun_geo"].str.lower()]
    if len(desajuste):
        print(f"\n⚠ {len(desajuste)} EMA(s) cuyo nombre o municipio declarado no "
              "coincide con donde caen sus coordenadas.")

    print("\nRadiación solar media por hora local (W/m²):")
    print(ciclo_diario(d).to_string())

    if a.mapa:
        import matplotlib
        matplotlib.use("Agg")
        mapa_emas(ruta=a.ruta, base=a.base)
