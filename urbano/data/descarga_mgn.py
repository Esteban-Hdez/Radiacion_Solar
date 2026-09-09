"""
Descarga y descompresión del paquete estatal del Marco Geoestadístico (INEGI).

Es idempotente: si el ZIP y los shapefiles ya están en `cache/`, no vuelve a
bajar nada. El ZIP pesa ~74 MB y NO se versiona.

Detalle no obvio: el ZIP del INEGI trae los nombres de archivo en codificación
de 8 bits sin la marca UTF-8 (bit 0x800), así que `unzip` de macOS revienta al
llegar a `catalogos/léeme.pdf`. Por eso descomprimimos con `zipfile`
reinterpretando los nombres cp437 -> latin-1 en vez de con la herramienta del
sistema.

Uso:
    conda run -n rs python -m urbano.data.descarga_mgn
"""
from __future__ import annotations
import os
import sys
import zipfile

import requests

from urbano import config as C


def _nombre_real(info: zipfile.ZipInfo) -> str:
    """Nombre del miembro con los acentos correctos (ver docstring del módulo)."""
    if info.flag_bits & 0x800:          # ya venía marcado como UTF-8
        return info.filename
    return info.filename.encode("cp437").decode("latin-1", "replace")


def descargar(forzar: bool = False) -> str:
    """Baja el ZIP estatal del MG a `cache/`. Devuelve su ruta."""
    os.makedirs(C.DIR_CACHE, exist_ok=True)
    if os.path.exists(C.ZIP_MG) and not forzar:
        mb = os.path.getsize(C.ZIP_MG) / 1e6
        print(f"[mg] ZIP ya en caché ({mb:.1f} MB): {C.ZIP_MG}")
        return C.ZIP_MG

    print(f"[mg] descargando MG {C.EDICION_MG} de {C.URL_MG}")
    r = requests.get(C.URL_MG, stream=True, timeout=180,
                     headers={"User-Agent": "Mozilla/5.0"})
    r.raise_for_status()
    tmp = C.ZIP_MG + ".parcial"
    n = 0
    with open(tmp, "wb") as f:
        for chunk in r.iter_content(1 << 20):
            f.write(chunk)
            n += len(chunk)
            print(f"\r[mg] {n/1e6:7.1f} MB", end="", file=sys.stderr)
    print(file=sys.stderr)
    # El INEGI responde 200 con una página de error si el id de producto no existe;
    # un ZIP legítimo pesa decenas de MB.
    if n < 1_000_000:
        os.remove(tmp)
        raise RuntimeError(
            f"La descarga trajo solo {n} bytes: el id de producto "
            f"{C.ID_PRODUCTO_MG} probablemente ya no está publicado. "
            "Revisa la edición vigente en https://www.inegi.org.mx/programas/mg/ "
            "y actualiza ID_PRODUCTO_MG en urbano/config.py, o baja el ZIP a mano "
            f"y déjalo en {C.ZIP_MG}.")
    os.replace(tmp, C.ZIP_MG)
    print(f"[mg] guardado {n/1e6:.1f} MB en {C.ZIP_MG}")
    return C.ZIP_MG


def descomprimir(forzar: bool = False) -> str:
    """Extrae el paquete a `cache/`. Devuelve el directorio de shapefiles."""
    if os.path.exists(C.capa(C.CAPA_LOCALIDADES)) and not forzar:
        print(f"[mg] shapefiles ya extraídos en {C.DIR_SHP}")
        return C.DIR_SHP

    with zipfile.ZipFile(C.ZIP_MG) as z:
        for info in z.infolist():
            if info.is_dir():
                continue
            destino = os.path.join(C.DIR_MG, *_nombre_real(info).split("/"))
            os.makedirs(os.path.dirname(destino), exist_ok=True)
            with z.open(info) as origen, open(destino, "wb") as salida:
                salida.write(origen.read())
    capas = sorted(f for f in os.listdir(C.DIR_SHP) if f.endswith(".shp"))
    print(f"[mg] extraídas {len(capas)} capas en {C.DIR_SHP}: {', '.join(capas)}")
    return C.DIR_SHP


def asegurar(forzar: bool = False) -> str:
    """Garantiza que los shapefiles del MG estén disponibles localmente."""
    descargar(forzar)
    return descomprimir(forzar)


if __name__ == "__main__":
    asegurar(forzar="--forzar" in sys.argv)
