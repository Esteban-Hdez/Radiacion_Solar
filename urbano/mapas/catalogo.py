"""
Catálogo visual completo: una lámina por cada localidad urbana del estado.

Dos series, porque responden preguntas distintas:

- **Cabeceras municipales** (43): ordenadas por CLAVE INEGI del municipio
  (001 Abasolo → 043 Xicoténcatl), que es el orden del catálogo oficial y el que
  permite buscar un municipio sin conocer su tamaño. 12 por página → 4 páginas.
- **Otras localidades urbanas** (20): las que NO son cabecera, ordenadas por
  área de mayor a menor. Cada lámina rotula a qué municipio pertenece, porque el
  nombre por sí solo no lo dice (Miramar es del municipio de Altamira).
  12 por página → 2 páginas.

Cada página se genera en las dos versiones del proyecto: esquemática y sobre
mapa base. Son 12 figuras en total; `con_base=False` deja solo 6.

    conda run -n rs python -m urbano.mapas.catalogo
    conda run -n rs python -m urbano.mapas.catalogo --sin-base
"""
from __future__ import annotations
import os

from urbano import config as C
from urbano.data import manchas as M
from urbano.mapas import estaticos as X
from urbano.nodos import asignacion as A

POR_PAGINA = 12          # rejilla 3 × 4
NCOLS = 4


def _paginar(cvegeos: list[str]) -> list[list[str]]:
    return [cvegeos[i:i + POR_PAGINA]
            for i in range(0, len(cvegeos), POR_PAGINA)]


def _serie(urb, nodos, pares, cvegeos, dir_salida, prefijo, titulo_base,
           subtitulo, meta, base) -> list[str]:
    """Genera las páginas de una serie del catálogo."""
    paginas = _paginar(cvegeos)
    sfx = "_base" if base else ""
    rutas = []
    for i, pagina in enumerate(paginas, start=1):
        ruta = os.path.join(dir_salida, f"{prefijo}_{i}de{len(paginas)}{sfx}.png")
        rutas.append(X.panel_ciudades(
            urb, nodos, pares, ruta, pagina,
            f"{titulo_base} · página {i} de {len(paginas)}"
            + (" (sobre mapa base)" if base else ""),
            subtitulo if i == 1 else None,
            ncols=NCOLS, base=base, meta=meta))
    return rutas


def orden_cabeceras(urb) -> list[str]:
    """Las 43 cabeceras, por clave INEGI de municipio."""
    c = urb[urb["es_cabecera"]].sort_values("cve_mun")
    return c["cvegeo"].tolist()


def orden_otras(urb) -> list[str]:
    """Las localidades urbanas que NO son cabecera, por área descendente."""
    o = urb[~urb["es_cabecera"]].sort_values("area_km2", ascending=False)
    return o["cvegeo"].tolist()


def generar(urb=None, nodos=None, pares=None, dir_salida: str | None = None,
            con_base: bool = True) -> list[str]:
    urb = M.manchas_urbanas() if urb is None else urb
    nodos = A.cargar_nodos() if nodos is None else nodos
    pares = A.asignar(urb, nodos) if pares is None else pares
    d = dir_salida or os.path.join(C.DIR_SALIDA_MAPAS, "catalogo")
    os.makedirs(d, exist_ok=True)

    cabeceras, otras = orden_cabeceras(urb), orden_otras(urb)
    rutas = []
    for base in ([False, True] if con_base else [False]):
        rutas += _serie(
            urb, nodos, pares, cabeceras, d, "cabeceras",
            f"Las {len(cabeceras)} cabeceras municipales de Tamaulipas",
            "Ordenadas por clave INEGI de municipio. La mancha naranja es la "
            "localidad urbana completa; las celdas punteadas, los nodos NSRDB "
            "que la cubren.",
            X.meta_cabecera, base)
        rutas += _serie(
            urb, nodos, pares, otras, d, "otras_localidades",
            f"Las otras {len(otras)} localidades urbanas de Tamaulipas",
            "Localidades urbanas que NO son cabecera municipal, de mayor a "
            "menor área. Cada lámina indica el municipio al que pertenecen.",
            X.meta_otra_localidad, base)
    return rutas


if __name__ == "__main__":
    import sys
    for r in generar(con_base="--sin-base" not in sys.argv):
        print("[catalogo]", r)
