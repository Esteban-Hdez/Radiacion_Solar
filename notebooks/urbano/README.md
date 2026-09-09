# Notebooks del análisis urbano

Tres notebooks, **cada uno autocontenido**: corren de arriba a abajo sin
necesitar a los otros. La primera celda de cada uno es el único requisito (ajusta
`sys.path` sola, así que da igual desde dónde lances Jupyter).

| # | notebook | qué responde |
|---|---|---|
| **01** | `01_manchas_y_nodos.ipynb` | la **geometría**: qué es una mancha urbana, qué nodos NSRDB la cubren y con qué confianza. Genera todos los mapas. |
| **02** | `02_clima_por_ciudad.ipynb` | el **método**: cómo se pasa de series de nodo a series de ciudad, y qué decisiones cambian los números. |
| **03** | `03_consultas.ipynb` | el **manual de uso**: cómo pedir cualquier serie de cualquier zona urbana. |

## Por dónde empezar

- **"Quiero la temperatura de Victoria en junio"** → directo al **03**.
- **"¿Por qué esta ciudad tiene un solo nodo?"** → **01**.
- **"¿Este promedio de qué es exactamente?"** → **02**.

## Requisitos

```bash
# 1. Los CSV de pesos nodo↔ciudad (lo necesitan los tres)
conda run -n rs python -m urbano.construir

# 2. Los parquet anuales, para 02 y 03
#    Data/Tamaulipas/<año>/Finales/completo/dataset_tamaulipas_completo_24h_<año>.parquet
```

El notebook 01 puede correrse sin los parquet; solo usa geometría.

## El orden de trabajo del 03

```
1. Mirar el catálogo        Q.catalogo()            ¿qué existe y cómo se llama?
2. Elegir la unidad         Q.resolver("victoria")  o  ambito="cabeceras"
3. Elegir las variables     V.CATALOGO              ¿temperatura? ¿GHI? ¿viento?
4. Acotar el periodo        desde= / hasta=         en hora LOCAL, inclusivos
5. Elegir la frecuencia     "hora" o "dia"
6. Pedir                    Q.serie(...)
```

## Nota sobre el arranque

Esta carpeta se llama `urbano`, **igual que el paquete de código** (`/urbano`).
Jupyter ejecuta cada notebook con el directorio de trabajo aquí, así que una
búsqueda ingenua de "un directorio llamado urbano" encuentra **esta** y Python la
importa como paquete de espacio de nombres vacío:

```
ImportError: cannot import name 'config' from 'urbano' (unknown location)
```

La celda de arranque de los tres notebooks lo evita exigiendo el
`urbano/__init__.py` (solo el paquete real lo tiene), y además descarta de
`sys.modules` cualquier `urbano` que se hubiera importado mal antes, para que no
haga falta reiniciar el kernel. Imprime de dónde salió el paquete, así que si
algo va mal se ve en la primera línea de salida.

Cubierto por `urbano/tests/test_notebooks.py`, que corre la celda de arranque con
el CWD puesto donde lo pone Jupyter — lanzada desde la raíz del repo, la versión
rota también funcionaba, y por eso el fallo se coló.

## Si una celda falla con un `KeyError` de una columna que sí debería estar

Es casi siempre el **kernel con el código viejo**: `urbano/` se edita mientras el
notebook está abierto y Python no recarga un módulo ya importado. La celda de
arranque activa `%autoreload 2`, que vuelve a leer el código en cada ejecución,
así que basta con volver a correr la celda. Si aun así algo se comporta raro,
reinicia el kernel: `autoreload` no rehace objetos ya creados en memoria.
