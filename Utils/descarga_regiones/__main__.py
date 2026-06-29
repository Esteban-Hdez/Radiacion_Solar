"""Permite ejecutar el orquestador con `python -m Utils.descarga_regiones`."""
import sys

# Fuerza UTF-8 en la salida para que los emojis (⏱️, 🛑, 📄) no rompan la
# corrida al redirigir a un archivo en Windows (la consola redirigida usa cp1252).
for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8", errors="replace")

from Utils.descarga_regiones.descargar_regiones import _cli

if __name__ == "__main__":
    _cli()
