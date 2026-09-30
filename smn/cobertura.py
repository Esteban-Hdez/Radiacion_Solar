"""
Cuánto dato tiene de verdad cada estación del SMN.

    conda run -n rs python -m smn.cobertura
    conda run -n rs python -m smn.cobertura --cobertura-min 90

La pregunta que responde: de las 199 estaciones del catálogo, ¿cuáles sirven
para algo? Una estación "Operando" puede no haber descargado un solo día, y una
que descargó seis años puede tener la mitad de los días vacíos.

## Cobertura = días con fila / días del periodo

Las filas ausentes son los huecos: si una estación no reportó el 3 de marzo, no
hay fila ese día. Por eso `tmax_c` y `tmin_c` no tienen nulos en las filas
presentes, y contar filas basta.

El **denominador es el periodo completo** (2020-01-01 a la última fecha del
archivo), no el tramo propio de cada estación. Es deliberado: una estación que
solo reportó enero de 2020 tendría 100 % de "su" tramo, que es exactamente la
lectura que hay que evitar. Para el otro punto de vista está `cobertura_activa`,
que sí mide de su primera a su última fecha, y la diferencia entre ambas dice si
el problema es que empezó tarde/paró pronto o que falta dato por dentro.

## Las que no tienen datos no tienen coordenadas

El catálogo del SMN no trae lat/lon; las coordenadas salen de la cabecera de
cada archivo diario. Una estación sin descarga no está en ningún sitio, así que
aparece en la tabla y en los conteos con `tiene_datos=False` y geometría nula.
"""
from __future__ import annotations
import argparse

import numpy as np
import pandas as pd

from smn import config as C


# --------------------------------------------------------------------------- #
# Carga
# --------------------------------------------------------------------------- #
def cargar_diario() -> pd.DataFrame:
    """Las series diarias, con `clave` como texto y `fecha` como fecha."""
    d = pd.read_csv(C.CSV_DIARIO, dtype={"clave": str}, parse_dates=["fecha"])
    return d


def cargar_catalogo() -> pd.DataFrame:
    """Las 199 estaciones convencionales del catálogo. Sin coordenadas."""
    return pd.read_csv(C.CSV_CATALOGO, dtype={"clave": str})


def periodo(d: pd.DataFrame | None = None) -> tuple[pd.Timestamp, pd.Timestamp, int]:
    """
    `(primera, última, n_días)` del archivo.

    Se lee del dato y no se escribe a mano: el archivo se llama `_2020` pero
    crece con cada re-descarga, y un periodo hardcodeado convertiría una
    actualización en una cobertura mal calculada sin avisar.
    """
    d = cargar_diario() if d is None else d
    lo, hi = d["fecha"].min(), d["fecha"].max()
    return lo, hi, (hi - lo).days + 1


# --------------------------------------------------------------------------- #
# Tabla por estación
# --------------------------------------------------------------------------- #
def _banda(pct: float) -> str:
    for corte, nombre in C.BANDAS:
        if pct >= corte:
            return nombre
    return C.BANDAS[-1][1]


def tabla(d: pd.DataFrame | None = None,
          cat: pd.DataFrame | None = None) -> pd.DataFrame:
    """
    Una fila por estación del CATÁLOGO (199), tenga datos o no.

    El catálogo manda sobre las series a propósito: si se partiera de los datos,
    las 82 estaciones vacías desaparecerían del análisis y la pregunta "¿cuántas
    no tienen datos?" no se podría contestar.

    Columnas: identificación, `situacion` del catálogo, primera/última fecha,
    `n_dias`, `cobertura` (sobre el periodo completo), `cobertura_activa` (sobre
    su propio tramo), `desde_2020`, `banda`, y la cobertura de cada variable.
    """
    d = cargar_diario() if d is None else d
    cat = cargar_catalogo() if cat is None else cat
    lo, hi, dias = periodo(d)

    g = d.groupby("clave").agg(
        primera=("fecha", "min"), ultima=("fecha", "max"),
        n_dias=("fecha", "nunique"),
        latitud=("latitud", "first"), longitud=("longitud", "first"),
        altitud_msnm=("altitud_msnm", "first"))

    # Cobertura por variable: aquí sí hay nulos dentro de las filas presentes
    # (`evap_mm` falta en 4 de cada 5 días), y el denominador sigue siendo el
    # periodo completo para que se compare con la cobertura general.
    for v in C.VARIABLES:
        if v in d.columns:
            g[f"cob_{v}"] = d.groupby("clave")[v].count() / dias * 100

    t = cat.merge(g, left_on="clave", right_index=True, how="left")
    t["tiene_datos"] = t["n_dias"].notna()
    t["n_dias"] = t["n_dias"].fillna(0).astype(int)
    t["cobertura"] = t["n_dias"] / dias * 100
    activos = (t["ultima"] - t["primera"]).dt.days + 1
    t["cobertura_activa"] = np.where(t["tiene_datos"],
                                     t["n_dias"] / activos * 100, np.nan)
    # "Desde 2020" es que su PRIMERA fecha caiga dentro de 2020, no que tenga
    # alguna fila de 2020: lo segundo lo cumple cualquiera que empiece después.
    t["desde_2020"] = t["primera"].notna() & (t["primera"] <= pd.Timestamp(
        C.DESDE_OMISION))
    t["banda"] = t["cobertura"].map(_banda).where(t["tiene_datos"])
    t["sigue_activa"] = t["ultima"] >= (hi - pd.Timedelta(days=90))

    orden = ["clave", "nombre", "municipio", "situacion", "red", "tiene_datos",
             "primera", "ultima", "n_dias", "cobertura", "cobertura_activa",
             "desde_2020", "sigue_activa", "banda", "latitud", "longitud",
             "altitud_msnm"] + [f"cob_{v}" for v in C.VARIABLES if f"cob_{v}" in t]
    return (t[[c for c in orden if c in t.columns]]
            .sort_values(["cobertura", "clave"], ascending=[False, True])
            .reset_index(drop=True))


def seleccionar(t: pd.DataFrame | None = None, desde_2020: bool = True,
                cobertura_min: float = C.COBERTURA_MIN_OMISION) -> pd.DataFrame:
    """
    Las estaciones que pasan el filtro, ya listas para mapear o analizar.

    `desde_2020=True` exige que la estación arranque en 2020 (no que tenga algún
    día suelto de ese año). `cobertura_min` se mide sobre el periodo completo.
    """
    t = tabla() if t is None else t
    sel = t[t["tiene_datos"] & (t["cobertura"] >= cobertura_min)]
    if desde_2020:
        sel = sel[sel["desde_2020"]]
    return sel.reset_index(drop=True)


# --------------------------------------------------------------------------- #
# Resumen
# --------------------------------------------------------------------------- #
def resumen(t: pd.DataFrame | None = None,
            umbrales=(50, 75, 90, 95)) -> dict:
    """Los números que contestan la pregunta de un vistazo."""
    t = tabla() if t is None else t
    lo, hi, dias = periodo()
    con = t[t["tiene_datos"]]
    r = {
        "periodo": f"{lo:%Y-%m-%d} .. {hi:%Y-%m-%d}",
        "dias_periodo": dias,
        "catalogo": len(t),
        "con_datos": int(t["tiene_datos"].sum()),
        "sin_datos": int((~t["tiene_datos"]).sum()),
        "desde_2020": int(t["desde_2020"].sum()),
        "siguen_activas": int(t["sigue_activa"].fillna(False).sum()),
        "cobertura_mediana": round(float(con["cobertura"].median()), 1),
        "cobertura_media": round(float(con["cobertura"].mean()), 1),
    }
    for u in umbrales:
        r[f"cob>={u}%"] = int((con["cobertura"] >= u).sum())
        r[f"cob>={u}%_y_desde_2020"] = int(
            ((con["cobertura"] >= u) & con["desde_2020"]).sum())
    return r


def por_situacion(t: pd.DataFrame | None = None) -> pd.DataFrame:
    """
    Cruce situación del catálogo × tiene datos.

    Es donde se ve que "Operando" no garantiza dato y "Suspendida" no lo
    excluye: hay estaciones suspendidas con años de histórico descargado.
    """
    t = tabla() if t is None else t
    return pd.crosstab(t["situacion"], t["tiene_datos"],
                       rownames=["situación"], colnames=["tiene datos"])


def sin_datos(t: pd.DataFrame | None = None) -> pd.DataFrame:
    """Las estaciones del catálogo que no descargaron un solo día."""
    t = tabla() if t is None else t
    return (t[~t["tiene_datos"]][["clave", "nombre", "municipio", "situacion"]]
            .reset_index(drop=True))


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--cobertura-min", type=float,
                    default=C.COBERTURA_MIN_OMISION)
    ap.add_argument("--todas", action="store_true",
                    help="no exigir que la estación arranque en 2020")
    ap.add_argument("--guardar", metavar="CSV",
                    help="escribe la tabla completa por estación")
    a = ap.parse_args()

    pd.set_option("display.width", 200)
    t = tabla()
    r = resumen(t)

    print(f"\nPeriodo {r['periodo']} ({r['dias_periodo']} días)\n")
    print(f"  catálogo .............. {r['catalogo']:3d} estaciones")
    print(f"  con datos ............. {r['con_datos']:3d}")
    print(f"  SIN datos ............. {r['sin_datos']:3d}  (no tienen coordenadas: "
          "no se pueden mapear)")
    print(f"  arrancan en 2020 ...... {r['desde_2020']:3d}")
    print(f"  siguen reportando ..... {r['siguen_activas']:3d}  (dato en los "
          "últimos 90 días)")
    print(f"\n  cobertura mediana ..... {r['cobertura_mediana']:.1f} %"
          f"   media {r['cobertura_media']:.1f} %")
    print("\n  por umbral de cobertura (sobre el periodo completo):")
    for u in (50, 75, 90, 95):
        print(f"    >= {u:2d} % ... {r[f'cob>={u}%']:3d}   "
              f"y además desde 2020: {r[f'cob>={u}%_y_desde_2020']:3d}")

    print("\nSituación del catálogo × tiene datos:")
    print(por_situacion(t).to_string())

    sel = seleccionar(t, desde_2020=not a.todas, cobertura_min=a.cobertura_min)
    print(f"\nSelección ({'cualquier inicio' if a.todas else 'desde 2020'}, "
          f"cobertura ≥ {a.cobertura_min:g} %): {len(sel)} estaciones\n")
    print(sel[["clave", "nombre", "municipio", "primera", "ultima", "n_dias",
               "cobertura", "banda"]].head(20).to_string(index=False))
    if len(sel) > 20:
        print(f"  … y {len(sel) - 20} más")

    if a.guardar:
        t.to_csv(a.guardar, index=False)
        print(f"\n[csv] {a.guardar}")
