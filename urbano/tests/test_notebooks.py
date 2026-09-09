"""
Que los notebooks arranquen desde donde los abre Jupyter.

Jupyter ejecuta cada notebook con el CWD en **su propia carpeta**, no en la raíz
del repo. Y esa carpeta se llama `notebooks/urbano`, igual que el paquete. Una
búsqueda ingenua de "un directorio llamado urbano" encuentra la del notebook,
Python la importa como paquete de espacio de nombres vacío y todo revienta con
`cannot import name 'config' from 'urbano' (unknown location)`.

Estos tests corren la celda de arranque en un subproceso con el CWD puesto donde
lo pone Jupyter, que es la única forma de reproducir el fallo: lanzados desde la
raíz del repo, los notebooks funcionan aunque la celda esté mal.

    conda run -n rs pytest urbano/tests/test_notebooks.py -q
"""
from __future__ import annotations
import json
import os
import subprocess
import sys

import pytest

from urbano import config as C

DIR_NB = os.path.join(C.RAIZ, "notebooks", "urbano")
NOTEBOOKS = ["01_manchas_y_nodos.ipynb", "02_clima_por_ciudad.ipynb",
             "03_consultas.ipynb"]

pytestmark = pytest.mark.skipif(not os.path.isdir(DIR_NB),
                                reason="no están los notebooks")


def _celda_de_arranque(nb: str, sin_magias: bool = False) -> str:
    """
    El texto de la celda de arranque.

    `sin_magias=True` quita las líneas de magia de IPython (`%load_ext`,
    `%autoreload`): estos tests ejecutan la celda como Python plano en un
    subproceso, donde `%` es un error de sintaxis. Lo que se quiere comprobar es
    la resolución de `sys.path`, no las magias.
    """
    doc = json.load(open(os.path.join(DIR_NB, nb), encoding="utf-8"))
    for c in doc["cells"]:
        src = "".join(c["source"])
        if c["cell_type"] == "code" and src.startswith("# --- arranque"):
            if sin_magias:
                src = "\n".join(l for l in src.split("\n")
                                 if not l.lstrip().startswith("%"))
            return src
    raise AssertionError(f"{nb} no tiene celda de arranque")


def _correr(guion: str, cwd: str) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, "-c", guion], cwd=cwd,
                          capture_output=True, text=True,
                          env={**os.environ, "PYTHONPATH": ""})


def test_la_carpeta_de_notebooks_no_es_un_paquete():
    """
    Si alguien le pusiera un `__init__.py` a `notebooks/urbano`, se volvería un
    paquete importable llamado igual que el de verdad y la ambigüedad dejaría de
    poder resolverse desde el path.
    """
    assert not os.path.exists(os.path.join(DIR_NB, "__init__.py"))


@pytest.mark.parametrize("nb", NOTEBOOKS)
def test_arranca_desde_su_propia_carpeta(nb):
    guion = _celda_de_arranque(nb, sin_magias=True) + (
        "\nfrom urbano import config"
        "\nfrom urbano.clima import consulta"
        "\nassert os.path.dirname(urbano.__file__) == os.path.join(RAIZ, 'urbano')"
        "\nprint('OK')\n")
    r = _correr(guion, DIR_NB)
    assert r.returncode == 0, r.stderr[-1500:]
    assert "OK" in r.stdout


@pytest.mark.parametrize("nb", NOTEBOOKS)
def test_arranca_tambien_desde_la_raiz(nb):
    guion = (_celda_de_arranque(nb, sin_magias=True)
             + "\nfrom urbano import config\nprint('OK')\n")
    r = _correr(guion, C.RAIZ)
    assert r.returncode == 0, r.stderr[-1500:]


def test_el_arranque_es_el_mismo_en_los_tres():
    """Un solo texto que mantener; si divergen, uno se quedará atrás."""
    assert len({_celda_de_arranque(nb) for nb in NOTEBOOKS}) == 1


@pytest.mark.parametrize("nb", NOTEBOOKS)
def test_el_arranque_activa_autoreload(nb):
    """
    Sin `autoreload`, un kernel abierto se queda con la versión del paquete que
    importó al principio y las celdas fallan con errores desconcertantes
    —"['cve_mun'] not in index"— cuando el código de `urbano/` cambia debajo.
    """
    src = _celda_de_arranque(nb)
    assert "%load_ext autoreload" in src
    assert "%autoreload 2" in src
