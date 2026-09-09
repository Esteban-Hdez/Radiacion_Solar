"""
Mapas de un NODO concreto.

Responde la pregunta "¿de qué punto exacto salen estos datos?". Es el mismo mapa
de ciudad de `estaticos.panel_ciudades`, con el mismo encuadre —para que las dos
láminas sean comparables— pero con un nodo marcado y los demás atenuados.

    conda run -n rs python -m urbano.mapas.nodo 1737          # un nodo
    conda run -n rs python -m urbano.mapas.nodo --interes     # los 12 marcados
    conda run -n rs python -m urbano.mapas.nodo --municipios  # las 43 cabeceras
    conda run -n rs python -m urbano.mapas.nodo 1737 --base   # sobre mapa base

Los 12 nodos de `Data/Tamaulipas/urbano/nodos_interes.csv` son los que se
señalaron a mano sobre `panel_ciudades_base.png`; se identificaron detectando los
círculos por color y proyectándolos a coordenadas del mapa (el nodo elegido queda
a 0.1–1.2 km del centro del círculo y el siguiente a 3.6–4.4 km, así que no hay
ambigüedad posible).
"""
from __future__ import annotations
import os

import pandas as pd

from urbano import config as C
from urbano.data import manchas as M
from urbano.mapas import estaticos as X
from urbano.nodos import asignacion as A

CSV_INTERES = os.path.join(C.DIR_SALIDA_DATOS, "nodos_interes.csv")
CSV_INTERES_MUN = os.path.join(C.DIR_SALIDA_DATOS,
                               "nodos_interes_municipios.csv")
DIR_CATALOGO = os.path.join(C.DIR_SALIDA_MAPAS, "catalogo", "nodos_de_interes")


def nodos_interes() -> pd.DataFrame:
    """Los 12 nodos señalados a mano, uno por cada ciudad grande."""
    if not os.path.exists(CSV_INTERES):
        raise FileNotFoundError(
            f"Falta {CSV_INTERES}. Es la identificación de los nodos marcados "
            "sobre el panel; se versiona con el repo.")
    return pd.read_csv(CSV_INTERES, dtype={"cvegeo": str, "cve_mun": str})


def nodos_interes_municipios() -> pd.DataFrame:
    """
    Un nodo señalado por cada una de las 43 CABECERAS municipales.

    Se identificaron igual que los 12 del panel de ciudades: detectando los
    círculos por color sobre las páginas del catálogo y proyectándolos a
    coordenadas del mapa. El nodo elegido quedó a 0.35 km o menos del centro de
    cada círculo, con el siguiente a 4.2 km o más.

    Gómez Farías va aparte: sus páginas se marcaron ANTES de corregir la
    cabecera (ver `urbano/data/cabeceras.py`), así que el círculo rojo caía
    sobre Loma Alta. El nodo bueno —el 784, en la cabecera de verdad— se tomó
    del recorte que se marcó en verde.
    """
    if not os.path.exists(CSV_INTERES_MUN):
        raise FileNotFoundError(f"Falta {CSV_INTERES_MUN}.")
    return pd.read_csv(CSV_INTERES_MUN, dtype={"cve_mun": str, "cvegeo": str})


def _meta_mun(info, ciudad) -> str:
    """Renglón del catálogo por municipio: clave, área y nodo marcado."""
    return (f"mun. {info['cve_mun']} · {ciudad['area_km2']:.1f} km² · "
            f"nodo {int(info['nodo_id'])} · peso {info['peso']:.3f} · "
            f"{info['calidad']}")


def catalogo_municipios(seleccion: pd.DataFrame | None = None,
                        dir_salida: str | None = None, con_base: bool = True,
                        urb=None, nodos=None, pares=None) -> list[str]:
    """
    Catálogo de las 43 cabeceras con su nodo marcado, paginado 3 × 4.

    Cuatro páginas (12 + 12 + 12 + 7) en las dos modalidades: esquemática y
    sobre mapa base. Mismo orden y encuadre que el catálogo de cabeceras, para
    poder ponerlos lado a lado.
    """
    from urbano.mapas import catalogo as CAT

    urb = M.manchas_urbanas() if urb is None else urb
    nodos = A.cargar_nodos() if nodos is None else nodos
    pares = A.asignar(urb, nodos) if pares is None else pares
    seleccion = nodos_interes_municipios() if seleccion is None else seleccion

    resaltar = dict(zip(seleccion["cvegeo"].astype(str),
                        seleccion["nodo_id"].astype(int)))
    orden = [c for c in CAT.orden_cabeceras(urb) if c in resaltar]
    faltan = set(CAT.orden_cabeceras(urb)) - set(orden)
    if faltan:
        raise ValueError(f"Sin nodo marcado: {sorted(faltan)}")

    d = dir_salida or DIR_CATALOGO
    os.makedirs(d, exist_ok=True)
    paginas = CAT._paginar(orden)
    rutas = []
    for base in ([False, True] if con_base else [False]):
        sfx = "_base" if base else ""
        for i, pagina in enumerate(paginas, start=1):
            ruta = os.path.join(
                d, f"nodos_municipios_{i}de{len(paginas)}{sfx}.png")
            rutas.append(X.panel_ciudades(
                urb, nodos, pares, ruta, pagina,
                f"Nodo seleccionado en las {len(orden)} cabeceras municipales "
                f"· página {i} de {len(paginas)}"
                + (" (sobre mapa base)" if base else ""),
                ncols=CAT.NCOLS, base=base, meta=_meta_mun, resaltar=resaltar))
    return rutas


def ciudad_del_nodo(nodo_id: int, pares: pd.DataFrame) -> str:
    """
    Ciudad a la que pertenece un nodo.

    Un nodo puede tocar dos manchas vecinas; se devuelve aquella de la que cubre
    más superficie urbana, que es la que mejor lo describe.
    """
    sub = pares[pares["nodo_id"] == int(nodo_id)]
    if sub.empty:
        raise ValueError(
            f"El nodo {nodo_id} no toca ninguna mancha urbana. Los nodos con "
            "ciudad son los 225 de `nodos_ciudades.csv`.")
    return sub.sort_values("peso", ascending=False)["cvegeo"].iloc[0]


def _meta(info, ciudad) -> str:
    return (f"{ciudad['area_km2']:.1f} km² · nodo {int(info['nodo_id'])} · "
            f"peso {info['peso']:.3f} · método {info['metodo']}")


def mapa_nodo(nodo_id: int, ruta: str | None = None, base: bool = False,
              urb=None, nodos=None, pares=None) -> str:
    """Lámina única con un nodo marcado dentro de su ciudad."""
    urb = M.manchas_urbanas() if urb is None else urb
    nodos = A.cargar_nodos() if nodos is None else nodos
    pares = A.asignar(urb, nodos) if pares is None else pares

    cve = ciudad_del_nodo(nodo_id, pares)
    nombre = urb.loc[urb["cvegeo"] == cve, "ciudad"].iloc[0]
    sfx = "_base" if base else ""
    ruta = ruta or os.path.join(C.DIR_SALIDA_MAPAS, "nodos",
                                f"nodo_{int(nodo_id)}{sfx}.png")
    os.makedirs(os.path.dirname(ruta), exist_ok=True)

    fila = pares[(pares["nodo_id"] == int(nodo_id)) & (pares["cvegeo"] == cve)]
    return X.panel_ciudades(
        urb, nodos, pares, ruta, [cve],
        f"Nodo {int(nodo_id)} · {nombre}" + (" (sobre mapa base)" if base else ""),
        f"El nodo aporta el {fila['peso'].iloc[0]:.1%} del área urbana de "
        f"{nombre}; los demás nodos de la ciudad quedan atenuados.",
        ncols=1, base=base, meta=_meta,
        resaltar={cve: int(nodo_id)})


def panel_nodos(seleccion: pd.DataFrame | dict | None = None,
                ruta: str | None = None, base: bool = False, ncols: int = 4,
                urb=None, nodos=None, pares=None) -> str:
    """
    Rejilla con un nodo marcado por ciudad.

    `seleccion` puede ser un dict `{cvegeo: nodo_id}`, un DataFrame con esas dos
    columnas, o `None` para usar `nodos_interes.csv`.
    """
    urb = M.manchas_urbanas() if urb is None else urb
    nodos = A.cargar_nodos() if nodos is None else nodos
    pares = A.asignar(urb, nodos) if pares is None else pares

    if seleccion is None:
        seleccion = nodos_interes()
    if isinstance(seleccion, pd.DataFrame):
        seleccion = dict(zip(seleccion["cvegeo"].astype(str),
                             seleccion["nodo_id"].astype(int)))
    # El orden de las láminas es el del panel de ciudades, para poder compararlas
    # una contra otra sin buscar.
    res = A.resumen(pares, urb)
    orden = [c for c in res["cvegeo"] if c in seleccion]

    sfx = "_base" if base else ""
    ruta = ruta or os.path.join(C.DIR_SALIDA_MAPAS,
                                f"panel_nodos_seleccionados{sfx}.png")
    os.makedirs(os.path.dirname(ruta), exist_ok=True)
    return X.panel_ciudades(
        urb, nodos, pares, ruta, orden,
        "Nodo seleccionado en cada ciudad"
        + (" (sobre mapa base)" if base else ""),
        ncols=ncols, base=base, meta=_meta, resaltar=seleccion)


if __name__ == "__main__":
    import sys
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    base = "--base" in sys.argv
    urb = M.manchas_urbanas()
    nodos = A.cargar_nodos()
    pares = A.asignar(urb, nodos)
    if "--municipios" in sys.argv:
        for r in catalogo_municipios(con_base="--sin-base" not in sys.argv,
                                     urb=urb, nodos=nodos, pares=pares):
            print("[catalogo]", r)
    elif "--interes" in sys.argv or not args:
        for b in ([False, True] if "--base" not in sys.argv else [True]):
            print("[mapa]", panel_nodos(base=b, urb=urb, nodos=nodos, pares=pares))
    for a in args:
        print("[mapa]", mapa_nodo(int(a), base=base, urb=urb, nodos=nodos,
                                  pares=pares))
