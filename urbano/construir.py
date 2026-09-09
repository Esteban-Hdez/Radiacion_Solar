"""
Pipeline completo del análisis urbano, de punta a punta.

    conda run -n rs python -m urbano.construir            # todo
    conda run -n rs python -m urbano.construir --sin-mapas
    conda run -n rs python -m urbano.construir --forzar-descarga

Pasos: (1) asegurar el Marco Geoestadístico en caché, (2) extraer las manchas
urbanas, (3) asignar nodos, (4) escribir los tres CSV versionados, (5) rendir
los ocho PNG (cuatro figuras × dos versiones: esquemática y sobre mapa base) y
el HTML. `--sin-base` salta las de mosaico, que son las únicas que piden red.

Reproducible e idempotente: correrlo dos veces da exactamente lo mismo, y no
vuelve a bajar los 74 MB del INEGI si ya están.
"""
from __future__ import annotations
import argparse
import os

from urbano import config as C
from urbano.data import manchas as M
from urbano.data.descarga_mgn import asegurar
from urbano.nodos import asignacion as A


def main(sin_mapas: bool = False, forzar_descarga: bool = False,
         con_base: bool = True) -> None:
    asegurar(forzar_descarga)

    urb = M.manchas_urbanas()
    nodos = A.cargar_nodos()
    pares = A.asignar(urb, nodos)
    res = A.resumen(pares, urb)

    faltan = M.cabeceras_sin_mancha(urb)
    if len(faltan):
        print(f"[aviso] {len(faltan)} cabeceras sin mancha urbana en el MG "
              f"{C.EDICION_MG}: {', '.join(faltan['municipio'])}")

    os.makedirs(C.DIR_SALIDA_DATOS, exist_ok=True)
    # Se redondea antes de escribir: son CSV versionados, y el ruido del float64
    # en el dígito 15 haría que cada corrida ensuciara el diff de git sin que
    # nada haya cambiado en realidad.
    DEC = {"area_km2": 4, "lat_centro": 6, "lon_centro": 6, "peso": 6,
           "area_urbana_celda_km2": 4, "dist_centro_km": 3, "peso_max": 6}
    def _red(df):
        return df.round({k: v for k, v in DEC.items() if k in df.columns})

    _red(urb.drop(columns="geometry")).to_csv(C.CSV_CIUDADES, index=False)
    _red(pares).to_csv(C.CSV_NODOS_CIUDADES, index=False)
    _red(res).to_csv(C.CSV_RESUMEN, index=False)
    # Las geometrías van a caché: son pesadas y se regeneran del MG en segundos.
    urb.to_file(C.GPKG_MANCHAS, layer="manchas_urbanas", driver="GPKG")

    print(f"[csv] {C.CSV_CIUDADES}  ({len(urb)} localidades urbanas)")
    print(f"[csv] {C.CSV_NODOS_CIUDADES}  ({len(pares)} pares nodo↔ciudad)")
    print(f"[csv] {C.CSV_RESUMEN}  ({len(res)} filas)")
    print(f"[gpkg] {C.GPKG_MANCHAS}")

    if not sin_mapas:
        from urbano.mapas import estaticos, interactivo
        for r in estaticos.generar_todos(urb, nodos, pares, res,
                                         con_base=con_base):
            print("[mapa]", r)
        print("[mapa]", interactivo.construir(
            urb, nodos, pares, res,
            os.path.join(C.DIR_SALIDA_MAPAS, "mapa_urbano.html")))

    n_asig = pares["nodo_id"].nunique()
    print(f"\nResumen: {n_asig} de {len(nodos)} nodos ({n_asig/len(nodos):.1%}) "
          f"caen sobre alguna de las {len(urb)} manchas urbanas "
          f"({urb['area_km2'].sum():.0f} km², {urb['area_km2'].sum()/80175:.1%} "
          f"del estado).")
    print("Cobertura por ciudad:",
          ", ".join(f"{k} {v}" for k, v in res["calidad"].value_counts().items()))


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--sin-mapas", action="store_true",
                    help="solo genera los CSV")
    ap.add_argument("--forzar-descarga", action="store_true",
                    help="vuelve a bajar el paquete del INEGI")
    ap.add_argument("--sin-base", action="store_true",
                    help="omite las versiones sobre mapa base (no requiere red)")
    a = ap.parse_args()
    main(a.sin_mapas, a.forzar_descarga, con_base=not a.sin_base)
