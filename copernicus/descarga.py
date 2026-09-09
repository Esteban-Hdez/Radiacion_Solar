"""
Descarga de ERA5 desde el CDS, mes a mes y reanudable.

    conda run -n rs python -m copernicus.descarga --prueba
    conda run -n rs python -m copernicus.descarga --producto land --anios 2024
    conda run -n rs python -m copernicus.descarga --disponibilidad 2025

Por qué mes a mes: el CDS encola las peticiones y las grandes tardan o se
rechazan. Un mes por petición es un tamaño que pasa siempre, y hace la descarga
retomable —cada mes ya bajado se salta— que es lo que hace falta cuando el
proceso dura horas.

Detalle que sorprende la primera vez: aunque se pida `netcdf`, el CDS devuelve
un **ZIP** cuando el pedido mezcla variables instantáneas (temperatura, viento)
con acumuladas (radiación). Dentro vienen dos NetCDF, uno por tipo de paso. El
archivo se guarda tal cual llega y `normalizar()` lo deja como uno o dos `.nc`
con sufijo `_instant` / `_accum`.
"""
from __future__ import annotations
import argparse
import os
import sys
import zipfile

from copernicus import config as C


def cliente(quiet: bool = False):
    import cdsapi
    url, key = C.credenciales()
    return cdsapi.Client(url=url, key=key, quiet=quiet, wait_until_complete=True)


def _peticion(producto: str, anio: int, mes: int, dias=None, horas=None) -> dict:
    p = C.PRODUCTOS[producto]
    dias = dias or [f"{d:02d}" for d in range(1, 32)]
    horas = horas or [f"{h:02d}:00" for h in range(24)]
    return {
        **p["extra"],
        "variable": C.VARIABLES,
        "year": str(anio),
        "month": f"{mes:02d}",
        "day": dias,
        "time": horas,
        "area": C.AREA,
        "data_format": "netcdf",
        # Se pide sin comprimir; el CDS lo ignora y manda ZIP igualmente cuando
        # hay varios flujos, pero cuando puede evita el paso de descompresión.
        "download_format": "unarchived",
    }


def descargar_mes(producto: str, anio: int, mes: int, c=None,
                  forzar: bool = False) -> str:
    """Baja un mes. Si el archivo ya está y no se fuerza, no hace nada."""
    destino = C.archivo_crudo(producto, anio, mes)
    os.makedirs(os.path.dirname(destino), exist_ok=True)
    if os.path.exists(destino) and not forzar:
        print(f"[cds] {anio}-{mes:02d} {producto}: ya está "
              f"({os.path.getsize(destino)/1e6:.1f} MB)")
        return destino

    c = c or cliente()
    print(f"[cds] pidiendo {producto} {anio}-{mes:02d}…", flush=True)
    parcial = destino + ".parcial"
    c.retrieve(C.PRODUCTOS[producto]["dataset"],
               _peticion(producto, anio, mes), parcial)
    os.replace(parcial, destino)
    print(f"[cds] {anio}-{mes:02d} {producto}: "
          f"{os.path.getsize(destino)/1e6:.1f} MB")
    return destino


def normalizar(ruta: str, producto: str) -> list[str]:
    """
    Deja el archivo bajado como uno o más `.nc` en `dir_nc(producto)`.

    Devuelve las rutas resultantes. Si el archivo ya es NetCDF se copia el
    nombre; si es ZIP se extrae cada miembro con el sufijo de su tipo de paso.
    """
    salida = C.dir_nc(producto)
    os.makedirs(salida, exist_ok=True)
    base = os.path.splitext(os.path.basename(ruta))[0]

    if not zipfile.is_zipfile(ruta):
        destino = os.path.join(salida, base + ".nc")
        if not os.path.exists(destino):
            with open(ruta, "rb") as f, open(destino, "wb") as g:
                g.write(f.read())
        return [destino]

    rutas = []
    with zipfile.ZipFile(ruta) as z:
        for miembro in z.namelist():
            # El CDS nombra los miembros como ..._stepType-instant.nc /
            # ..._stepType-accum.nc; se conserva esa distinción porque decide
            # cómo se trata la radiación al extraer.
            tipo = "accum" if "accum" in miembro else "instant"
            destino = os.path.join(salida, f"{base}_{tipo}.nc")
            with open(destino, "wb") as g:
                g.write(z.read(miembro))
            rutas.append(destino)
    return sorted(rutas)


def descargar(producto: str, anios=C.ANIOS, meses=C.MESES,
              forzar: bool = False) -> list[str]:
    """Descarga y normaliza un rango completo. Es idempotente."""
    c = cliente()
    salidas = []
    for anio in anios:
        for mes in meses:
            try:
                crudo = descargar_mes(producto, anio, mes, c=c, forzar=forzar)
                salidas += normalizar(crudo, producto)
            except Exception as e:                 # un mes caído no tumba el resto
                print(f"[cds] ERROR en {producto} {anio}-{mes:02d}: "
                      f"{type(e).__name__}: {str(e)[:200]}", file=sys.stderr)
    return salidas


# --------------------------------------------------------------------------- #
# Disponibilidad
# --------------------------------------------------------------------------- #
def disponibilidad(anio: int, producto: str | None = None) -> dict[str, bool]:
    """
    ¿Hay datos para el 31 de diciembre de `anio`?

    ERA5 va con pocos días de retraso pero **ERA5-Land** puede ir con dos o tres
    MESES, así que "el año pasado" no siempre está completo. Se comprueba con
    una petición mínima —una hora, una variable, un recorte diminuto— en vez de
    fiarse de la documentación, que no siempre refleja el estado real.
    """
    c = cliente(quiet=True)
    productos = [producto] if producto else list(C.PRODUCTOS)
    out = {}
    for p in productos:
        pet = {
            **C.PRODUCTOS[p]["extra"],
            "variable": ["2m_temperature"],
            "year": str(anio), "month": "12", "day": ["31"], "time": ["12:00"],
            "area": [C.AREA[0], C.AREA[1], C.AREA[0] - 0.5, C.AREA[1] + 0.5],
            "data_format": "netcdf",
        }
        tmp = os.path.join(C.DIR_BASE, f"_sonda_{p}_{anio}.nc")
        os.makedirs(C.DIR_BASE, exist_ok=True)
        try:
            c.retrieve(C.PRODUCTOS[p]["dataset"], pet, tmp)
            out[p] = True
            print(f"[sonda] {p} {anio}-12-31: DISPONIBLE")
        except Exception as e:
            out[p] = False
            print(f"[sonda] {p} {anio}-12-31: no disponible "
                  f"({type(e).__name__}: {str(e)[:160]})")
        finally:
            if os.path.exists(tmp):
                os.remove(tmp)
    return out


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--producto", choices=list(C.PRODUCTOS), default=None,
                    help="por omisión, los dos")
    ap.add_argument("--anios", nargs="+", type=int, default=list(C.ANIOS))
    ap.add_argument("--meses", nargs="+", type=int, default=list(C.MESES))
    ap.add_argument("--forzar", action="store_true")
    ap.add_argument("--prueba", action="store_true",
                    help="un solo mes (enero 2024) de ambos productos")
    ap.add_argument("--disponibilidad", type=int, metavar="ANIO",
                    help="comprueba si ese año está completo y sale")
    a = ap.parse_args()

    if a.disponibilidad:
        disponibilidad(a.disponibilidad, a.producto)
        sys.exit(0)

    anios, meses = ([2024], [1]) if a.prueba else (a.anios, a.meses)
    for p in ([a.producto] if a.producto else list(C.PRODUCTOS)):
        for r in descargar(p, anios, meses, a.forzar):
            print("[nc]", r)
