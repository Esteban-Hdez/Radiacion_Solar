# Estaciones del SMN en Tamaulipas (`smn/`)

Qué estaciones climatológicas convencionales del Servicio Meteorológico Nacional
tienen datos utilizables de 2020 en adelante, y dónde están.

```bash
conda run -n rs python -m smn.cobertura                      # los números
conda run -n rs python -m smn.cobertura --cobertura-min 90
conda run -n rs python -m smn.mapa                           # el mapa
conda run -n rs python -m smn.mapa --cobertura-min 90 --descartadas --base
```

Cuaderno con ejemplos de todo:
[`notebooks/smn/estaciones_smn.ipynb`](../notebooks/smn/estaciones_smn.ipynb).

## Las dos fuentes no cubren lo mismo

| archivo | qué trae | coordenadas |
|---|---|---|
| `estaciones_convencionales_tamps.csv` | el **catálogo**: 199 estaciones con clave, nombre, municipio y situación | **no** |
| `temperatura_diaria_tamps_2020.csv` | las **series diarias** de 2020 en adelante: tmax, tmin, media, precipitación, evaporación | sí |

De ahí la limitación que gobierna el módulo: **solo se puede ubicar en un mapa
una estación que tenga datos**. Las coordenadas salen de la cabecera del archivo
diario de cada estación, así que las 82 que no descargaron nada no están en
ningún sitio. Se cuentan y se listan, pero no se dibujan.

> El archivo se llama `..._2020.csv` porque 2020 es el año de **inicio**, no el
> único: llega hasta 2026-09-10. El periodo se lee del propio dato, nunca
> hardcodeado, para que una re-descarga no deje la cobertura mal calculada en
> silencio.

## Los números

Periodo **2020-01-01 a 2026-09-10** (2445 días):

| | |
|---|---|
| estaciones en el catálogo | **199** |
| con datos descargados | **117** |
| **sin ningún dato** | **82** |
| arrancan en 2020 | 99 |
| siguen reportando (dato en los últimos 90 días) | 65 |
| cobertura mediana / media | 78.6 % / 62.0 % |

Por umbral de cobertura:

| umbral | con datos | y además desde 2020 |
|---|---|---|
| ≥ 50 % | 77 | 73 |
| **≥ 75 %** | 59 | **58** ← el filtro por omisión |
| ≥ 90 % | 39 | 39 |
| ≥ 95 % | 24 | 24 |

La mediana (78.6 %) está muy por encima de la media (62 %) porque la
distribución es **bimodal**: un bloque de estaciones casi completas y una cola
de estaciones que apenas reportaron. Eso es una buena noticia para elegir
umbral — mover el corte entre 70 y 85 % cambia poco.

### "Operando" no garantiza datos

| situación | sin datos | con datos |
|---|---|---|
| Operando | **4** | 109 |
| Suspendida | 78 | **8** |

Cuatro estaciones marcadas como operando no descargaron un solo día, y ocho
suspendidas sí tienen histórico. La situación del catálogo es un dato
administrativo: no sustituye a medir la cobertura real.

## Cómo se mide la cobertura

**`cobertura` = días con fila / días del periodo completo.** Las filas ausentes
*son* los huecos: si una estación no reportó el 3 de marzo, no hay fila ese día
(por eso `tmax_c` y `tmin_c` no tienen nulos en las filas presentes) y contar
filas basta.

El denominador es el **periodo completo**, no el tramo propio de cada estación.
Es deliberado: una estación que solo reportó enero de 2020 tendría 100 % de "su"
tramo, que es justo la lectura que hay que evitar.

Para el otro punto de vista está **`cobertura_activa`**, medida de su primera a
su última fecha. La diferencia entre ambas es diagnóstica:

- `cobertura` baja y `cobertura_activa` alta → no tiene huecos; empezó tarde o
  dejó de reportar.
- las dos bajas → le falta dato por dentro.

### Por variable

`tmax_c`, `tmin_c` y `temp_media_c` vienen siempre que hay fila y `precip_mm`
casi siempre, pero **`evap_mm` falta en 4 de cada 5 días**: no se puede tratar
como una serie más. La tabla trae una columna `cob_<variable>` para cada una.

## El mapa

```python
from smn.mapa import mapa_estaciones

mapa_estaciones()                                  # el de por omisión
mapa_estaciones(cobertura_min=95, etiquetar=10)
mapa_estaciones(mostrar_descartadas=True)
mapa_estaciones(desde_2020=False, cobertura_min=0.1)   # las 117 con algo de dato
```

| parámetro | qué hace | por omisión |
|---|---|---|
| `desde_2020` | exigir que la estación arranque en 2020 | `True` |
| `cobertura_min` | mínimo de cobertura del periodo (%) | `75` |
| `mostrar_descartadas` | pinta en gris las que tienen datos y no pasan el filtro | `False` |
| `base` | mosaico de OpenStreetMap de fondo | `False` |
| `etiquetar` | rotula las N de mayor cobertura | `0` |
| `titulo`, `subtitulo` | `None` los autogenera, `""` los quita | `None` |
| `ruta` | dónde guardar el PNG | `Results/smn/` |
| `tabla` | tabla ya calculada, para no releer | `None` |

Devuelve `(Figure, DataFrame)` con las estaciones dibujadas.

### Decisiones de diseño

Misma estructura que los mapas de `urbano/`: municipios del Marco Geoestadístico
del INEGI como fondo, ejes limpios, barra de escala y mosaico opcional. Reutiliza
`urbano.mapas.estilo` en vez de copiar la paleta, para que las dos familias de
figuras se lean como una sola.

**La cobertura es una variable ordinal, así que va en una rampa de un solo
tono** (los tres pasos de azul que `urbano` usa para la calidad): más oscuro es
más completo, y eso se entiende sin consultar la leyenda. Un esquema
rojo/amarillo/verde obligaría a mirarla para saber cuál es "mejor", y además
tropieza con el daltonismo justo en ese par.

Las estaciones se dibujan **de clara a oscura**, para que las de mayor cobertura
queden encima cuando dos caen casi en el mismo punto.

## Lo que se ve en el mapa

**El norte está vacío.** Entre Nuevo Laredo, Reynosa y Matamoros —donde vive la
mayor parte de la población del estado— apenas hay estaciones que pasen el
filtro, mientras el centro-sur está densamente cubierto.

Y no es culpa del umbral: con `mostrar_descartadas=True` se ve que las
descartadas se reparten por todo el estado. **El hueco es de la red, no del
filtro.** Para validar datos satelitales contra estaciones, eso condiciona qué
zonas se pueden contrastar y cuáles no.

## Catálogo por municipio

```bash
conda run -n rs python -m smn.catalogo            # 4 páginas × 2 versiones
conda run -n rs python -m smn.catalogo --sin-base # solo las esquemáticas
```

Cuatro páginas de 12 láminas (3 × 4) para los 43 municipios, ordenados por clave
INEGI. Mismo formato que
[`urbano.mapas.catalogo`](../urbano/mapas/catalogo.py), del que copia la rejilla,
la barra de escala por lámina y la leyenda al pie. Salida en
`Results/smn/catalogo/municipios_<n>de4[_base].png`.

Cada lámina responde "¿qué estaciones puedo usar para este municipio?", y tiene
dos formas según el caso:

- **Con estaciones**: las de dentro, coloreadas por cobertura; en gris las que no
  llegan al umbral y las de municipios vecinos que caen en el encuadre.
- **Sin ninguna** (8 de los 43): el encuadre se abre hasta alcanzar la más
  cercana, que se marca con un anillo, su nombre y la distancia al borde. Dejar
  la lámina vacía sería correcto pero inútil — lo que hace falta saber es a qué
  distancia queda el sustituto.

### La asignación es geométrica, no por el nombre del SMN

El archivo diario trae una columna `municipio`, pero **en tres estaciones no
coincide con el polígono donde caen sus coordenadas**:

| clave | estación | dice el SMN | cae en |
|---|---|---|---|
| 28049 | La Servilleta | El Mante | **Gómez Farías** |
| 28148 | El Barretal II | Padilla | **Hidalgo** |
| 28222 | San Francisco | Casas | **Llera** |

Manda la geometría. `discrepancias()` las lista.

### Los ocho municipios sin estación

| municipio | más cercana | distancia al borde |
|---|---|---|
| Tampico | Tampico (Obs) | 5.7 km |
| Ciudad Madero | Tampico (Obs) | 8.5 km |
| Miguel Alemán | S.J. 2-09 Camargo | 14.3 km |
| Mier | S.J. 2-09 Camargo | 29.5 km |
| Valle Hermoso | Matamoros | 30.3 km |
| Río Bravo | Palo Solo | 32.6 km |
| Guerrero | S.J. 2-09 Camargo | 49.1 km |
| **Nuevo Laredo** | S.J. 2-09 Camargo | **131.3 km** |

Los ocho son del norte o de la conurbación de Tampico, y es la misma historia
que cuenta el mapa estatal. Tampico y Ciudad Madero están cubiertos de hecho
—Tampico (Obs) queda a menos de 10 km, en Altamira—, pero **Nuevo Laredo no
tiene nada a menos de 131 km**: para ese municipio no hay estación de referencia
en todo el estado.

La distancia se mide al **borde** del municipio, no a su centro: lo que importa
es cuánto hay que salirse de él.

## API

```python
from smn import cobertura as K

K.periodo()                      # (primera, última, n_días), leído del archivo
K.tabla()                        # una fila por estación del catálogo (199)
K.resumen()                      # los conteos de un vistazo
K.seleccionar(cobertura_min=75)  # las que pasan el filtro
K.por_situacion()                # situación del catálogo × tiene datos
K.sin_datos()                    # las 82 que no descargaron nada

from smn import catalogo as CAT

CAT.asignar()              # estaciones con el municipio donde CAEN
CAT.resumen_municipios()   # una fila por municipio: cuántas tiene y la más cercana
CAT.discrepancias()        # municipio declarado ≠ municipio geométrico
CAT.generar()              # las 4 páginas, en sus dos versiones
```

`tabla()` parte del **catálogo**, no de las series: si partiera de los datos, las
82 estaciones vacías desaparecerían del análisis y la pregunta "¿cuántas no
tienen datos?" no se podría contestar.

## La otra red: las EMAS

```bash
conda run -n rs python -m smn.emas                 # la información
conda run -n rs python -m smn.emas --mapa --base   # además, el mapa
```

Cinco estaciones **automáticas**, cada **10 minutos**, y solo los **últimos 90
días**: el SMN no publica histórico por este canal. Frente a las 117
convencionales con seis años de dato diario es una ventana estrecha, pero traen
algo que ninguna otra fuente del proyecto tiene:

> **Son la única medición de radiación solar de superficie.** El NSRDB la estima
> desde satélite y ERA5 la modela; estas cinco la miden. Es el único contraste
> in situ disponible para el GHI.

Periodo 2026-06-17 → 2026-09-15, 54 078 registros:

| EMA | municipio | msnm | cobertura | sin reportar | offset nocturno |
|---|---|---|---|---|---|
| Tampico | Aldama* | 9 | 97.5 % | — | 0 |
| Villagrán | Villagrán | 393 | 97.4 % | — | 0 |
| Ciudad Mante | El Mante | 80 | 96.5 % | — | 0 |
| Ciudad Victoria | Victoria | 336 | 90.3 % | 2 d | **+52 W/m²** |
| Barra del Tordo | Aldama | 9 | **47.3 %** | **18 d** | 0 |

### Cuatro trampas, todas comprobadas

1. **El orden de las columnas cambia entre archivos.** Barra del Tordo, Ciudad
   Mante y Villagrán abren por viento; Ciudad Victoria y Tampico, por
   temperatura. Leer por posición mezclaría humedad con presión sin que nada
   fallara, así que `cargar()` resuelve siempre por nombre.
2. **La noche se codifica de dos maneras.** Mante y Tampico dejan la radiación
   nocturna vacía; Victoria y Villagrán escriben 0. Un `dropna()` borraría media
   serie en dos estaciones y ninguna en las otras dos. Se normaliza a 0.
3. **La presión de Ciudad Victoria es 0 en los 11 437 registros**: el barómetro
   no mide. Se pasa a NaN, porque promediar ceros da 0 sin avisar.
4. **Ciudad Victoria marca ~52 W/m² de radiación de noche**, cuando el valor real
   es 0 y las otras cuatro dan 0. Es el desplazamiento de cero de su
   piranómetro, y se suma también a sus lecturas diurnas — de ahí que tenga el
   máximo más alto de las cinco (1311 W/m²; 1259 restando el offset). **Su
   radiación no es comparable sin corregirla**, y es justo la estación de la
   capital. `resumen()` lo mide en `rad_offset_noche`.

### El nombre del archivo engaña

\* La EMA llamada **TAMPICO** no está en Tampico —queda unos 50 km al norte—, el
SMN la declara en **Altamira**, y sus coordenadas caen dentro del polígono de
**Aldama**, a 5.3 km del límite con Altamira. Por eso el municipio se resuelve
por geometría en `ubicar()` y la discrepancia se reporta en vez de elegirse en
silencio.

### El mapa

`Results/smn/emas_tamaulipas[_base].png`. Cada EMA lleva su punto, el municipio
donde cae pintado y la mancha urbana de la cabecera correspondiente. A escala
estatal una cabecera chica (Villagrán son 1.3 km²) mide menos que un píxel, así
que se le añade un marcador cuadrado en su centroide — un símbolo no exagera el
área como haría engordar el polígono. Una línea punteada une la EMA con su
cabecera cuando no coinciden: **Barra del Tordo está a 32 km de Aldama y la EMA
"Tampico" a 26 km**, así que en ese municipio ninguna de las dos mide la ciudad.

```python
from smn import emas as EM

EM.metadatos()      # las 5 con coordenadas y municipio declarado
EM.cargar_todas()   # las series de 10 min, columnas normalizadas
EM.resumen()        # cobertura, sensores muertos, offset nocturno
EM.ubicar()         # municipio geométrico y cabecera correspondiente
EM.ciclo_diario()   # radiación media por hora local — el control de cordura
EM.mapa_emas()
```
