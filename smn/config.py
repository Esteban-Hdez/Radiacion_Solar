"""
Rutas y umbrales de la red convencional del SMN en Tamaulipas.

## Las dos tablas, y por qué no cubren lo mismo

- `estaciones_convencionales_tamps.csv` — el **catálogo** scrapeado del SMN: 199
  estaciones con su clave, nombre, municipio y situación (Operando/Suspendida).
  **No trae coordenadas.**
- `temperatura_diaria_tamps_2020.csv` — las **series diarias** descargadas, de
  2020 en adelante. Aquí sí vienen `latitud`, `longitud` y `altitud_msnm`,
  porque salen de la cabecera del archivo de cada estación.

Consecuencia que manda en todo el módulo: **solo se puede ubicar en un mapa una
estación que tenga datos**. Las 82 del catálogo que no descargaron nada no
tienen coordenadas en ninguna de las dos tablas, así que se cuentan y se listan,
pero no se dibujan. No es una decisión de diseño, es lo que hay.

## El nombre del archivo miente (un poco)

Se llama `..._2020.csv` porque 2020 es el año de INICIO, no el único: el archivo
llega hasta 2026-09-10. El periodo real se lee del propio archivo y nunca se
escribe a mano, para que al re-descargar no haya que tocar código.

## Qué cuenta como "tener dato"

Las filas ausentes SON los huecos: una estación que no reportó el 3 de marzo no
tiene fila ese día (`tmax_c` y `tmin_c` no tienen nulos en las filas presentes).
Así que la cobertura es `días con fila / días del periodo`, y no hace falta
reindexar contra un calendario para contarla.
"""
from __future__ import annotations
import os

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REGION = "Tamaulipas"

DIR_SMN = os.path.join(RAIZ, "Data", REGION, "smn")
CSV_DIARIO = os.path.join(DIR_SMN, "temperatura_diaria_tamps_2020.csv")
CSV_CATALOGO = os.path.join(DIR_SMN, "estaciones_convencionales_tamps.csv")
DIR_EMAS = os.path.join(DIR_SMN, "crudos_emas")

DIR_SALIDA = os.path.join(RAIZ, "Results", "smn")

# --------------------------------------------------------------------------- #
# Umbrales
# --------------------------------------------------------------------------- #
# Los de fábrica del mapa: estaciones que arrancan en 2020 y cubren al menos
# tres cuartas partes del periodo. Con estos, de las 199 del catálogo quedan 58.
DESDE_OMISION = "2020-12-31"     # la PRIMERA fecha de la estación debe ser <= esta
COBERTURA_MIN_OMISION = 75.0

# Bandas para colorear la cobertura. Es una variable ORDINAL, así que va con una
# rampa de un solo tono (la misma de `urbano.mapas.estilo`), no con colores
# categóricos: "más oscuro = más completo" se lee sin consultar la leyenda.
BANDAS = ((95.0, "alta"), (85.0, "media"), (0.0, "baja"))

# Columnas de medición del archivo diario, en el orden en que se reportan.
VARIABLES = ("tmax_c", "tmin_c", "temp_media_c", "precip_mm", "evap_mm")
