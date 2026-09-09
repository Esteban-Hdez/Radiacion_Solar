# Análisis urbano — manchas urbanas INEGI ↔ nodos NSRDB

Identifica **qué nodos de la malla NSRDB representan a cada ciudad / cabecera
municipal de Tamaulipas**, y con cuánta confianza, para poder reportar después
métricas de pronóstico por ciudad.

Es un análisis **independiente**: no importa nada de `forecasting/` ni toca sus
datos. Su producto son tres CSV ligeros en `Data/Tamaulipas/urbano/`.

```bash
conda run -n rs python -m urbano.construir        # pipeline completo
conda run -n rs python -m urbano.construir --sin-mapas
conda run -n rs pytest urbano/tests -q
```

---

## El problema que resuelve

La malla NSRDB es de **0.04°** → celdas de ~4.4 × 4.1 km ≈ **18 km²**.
De las **63 localidades urbanas** de Tamaulipas, **51 miden menos que una celda**:

| | área urbana |
|---|---|
| Reynosa | 169.9 km² |
| Nuevo Laredo | 126.7 km² |
| Heroica Matamoros | 118.0 km² |
| Ciudad Victoria | 70.6 km² |
| Tampico | 55.0 km² |
| … | |
| San Nicolás | **0.10 km²** |

Un `punto dentro del polígono` puro dejaría sin ningún nodo a la mayoría de las
43 cabeceras. Por eso la asignación es una **cascada de tres métodos**, y cada
ciudad lleva una **bandera de calidad** que dice qué tan bien la representan sus
nodos.

## Fuente de datos

> Ficha completa de todas las fuentes del proyecto —ediciones, URLs, fechas
> de descarga y CRS— en [`docs/fuentes_geograficas.md`](../docs/fuentes_geograficas.md).


**Marco Geoestadístico del INEGI, edición 2025** (paquete estatal `28_tamaulipas.zip`,
74 MB, id de producto `794551163061`). Capas usadas:

| capa | contenido | uso |
|---|---|---|
| `28l` | localidades **amanzanadas** (polígono), campo `AMBITO` | la mancha urbana |
| `28mun` | 43 municipios | nombre y clave del municipio |
| AGEEML (municipios) | catálogo único de claves, `CVE_CAB`/`NOM_CAB` | **qué localidad es la cabecera** |
| `28lpr` | localidades rurales puntuales | detectar cabeceras sin polígono urbano |
| `28a` | AGEB urbanas | desagregación futura dentro de ciudades grandes |

La mancha urbana es el polígono de **manzanas reales**, no el municipio ni un
buffer alrededor de un punto.

Para cambiar de edición basta editar `EDICION_MG` e `ID_PRODUCTO_MG` en
`urbano/config.py`. Si el INEGI retira ese id, la descarga falla con un mensaje
que dice exactamente qué actualizar.

## Método de asignación

Todo el cálculo geométrico ocurre en **EPSG:6372** (Cónica Conforme de Lambert de
México, metros), así que áreas y distancias son reales.

| método | condición | calidad típica |
|---|---|---|
| `dentro` | el centro del nodo cae dentro de la mancha | alta / media |
| `celda` | la celda de 0.04° del nodo intersecta la mancha | baja |
| `cercano` | la mancha no toca ninguna celda → nodo más cercano al centroide | baja |

A cada par nodo↔ciudad se le asigna un **peso** = fracción del área urbana de esa
ciudad que cae dentro de la celda del nodo. **Los pesos de cada ciudad suman 1**,
así que una métrica por ciudad es directamente `Σ pesoᵢ · métricaᵢ`.

La bandera `calidad` cuenta cuántos nodos tienen su **centro** dentro de la mancha:
`alta` ≥ 3, `media` 1–2, `baja` 0.

### Qué localidad es la cabecera

**No se usa la convención "la localidad 0001 es la cabecera".** Es falsa en
Tamaulipas para **Gómez Farías** (011): su `0001` es *Loma Alta (Loma Alta de
Gómez Farías)* —la localidad más poblada— pero la cabecera es *Gómez Farías*, la
`0036`. Es el único caso de los 43, y basta uno para que el catálogo de
cabeceras muestre el pueblo equivocado.

El dato bueno sale del **Catálogo Único de Claves de Áreas Geoestadísticas**
(AGEEML) del INEGI, tabla de municipios, columnas `CVE_CAB` / `NOM_CAB`.
`urbano/data/cabeceras.py` lo baja una vez y deja las 43 filas en
`Data/Tamaulipas/cabeceras_inegi.csv`, que **sí se versiona**: así el pipeline no
depende de la red ni de que el INEGI conserve la URL.

```bash
conda run -n rs python -m urbano.data.cabeceras          # usa lo versionado
conda run -n rs python -m urbano.data.cabeceras --bajar  # re-descarga
```

Confirmado también con el [Gobierno de Tamaulipas](https://www.tamaulipas.gob.mx/estado/municipios/gomez-farias/):
*"Gómez Farías (cabecera municipal), poblado Loma Alta, …"*.

**Conglomerados:** manchas separadas por menos de 2 km se agrupan (Tampico +
Cd. Madero + Miramar + Altamira). Es una alternativa data-driven a la lista
oficial de zonas metropolitanas: se recalcula sola con cada edición del MG. Cada
ciudad conserva su identidad, así que las métricas se pueden reportar por
localidad **o** por conurbación sin rehacer nada.

## Resultados (MG 2025)

- **225 de 4384 nodos** (5.1 %) tocan alguna mancha urbana.
- 911 km² urbanos = **1.1 % de la superficie del estado**.
- Cobertura por ciudad: **alta 4** · media 13 · **baja 46**.
- Las 4 de cobertura alta: Reynosa (25 nodos), Nuevo Laredo (17), Matamoros (17),
  Cd. Victoria (12).
- Ninguna cabecera quedó sin mancha urbana ni sin nodo.

## Salidas

`Data/Tamaulipas/urbano/` — versionado:

| archivo | contenido |
|---|---|
| `ciudades_tamaulipas.csv` | una fila por localidad urbana: clave, nombre, municipio, cabecera sí/no, área, centroide, conglomerado |
| `nodos_ciudades.csv` | tabla larga nodo↔ciudad: `nodo_id`, `cvegeo`, `metodo`, `peso`, `calidad`, región |
| `resumen_cobertura.csv` | una fila por ciudad: nodos, nodos dentro, peso máximo, calidad |
| `nodos_interes.csv` | los 12 nodos señalados a mano, uno por ciudad grande |

`Results/Tamaulipas/urbano/`:

| archivo | qué muestra |
|---|---|
| `mapa_estatal.png` | las 63 manchas dentro de la malla completa, nodos por calidad |
| `panel_ciudades.png` | las 12 mayores: traslape celda↔mancha, con barra de escala |
| `panel_ciudades_chicas.png` | las 12 menores — la figura que hace visible el límite de resolución |
| `mapa_conglomerados.png` | detalle de las 6 conurbaciones |
| `*_base.png` | las mismas cuatro, sobre **mapa base** (ver abajo) |
| `mapa_urbano.html` | mapa interactivo (no versionado; se regenera) |

### Las dos versiones de cada mapa

Cada figura se genera dos veces:

- **Esquemática** (`mapa_estatal.png`): fondo liso. Aísla lo que importa —la
  geometría relativa mancha/celda— sin ruido, y no necesita red.
- **Sobre mapa base** (`mapa_estatal_base.png`): la misma capa naranja encima de
  un mosaico de referencia de **OpenStreetMap**, con carreteras (federales y
  estatales rotuladas: MEX 101, TAM 9…), calles, colonias y nombres de
  localidad. Sirve para *ubicarse*: reconocer la ciudad, ver por dónde entra la
  carretera, o comprobar que la mancha del INEGI coincide con la traza real.

Detalles del modo con mosaico:

- Va en **EPSG:3857** (el CRS de los mosaicos). La barra de escala se corrige por
  `1/cos(latitud)`: en Web Mercator el "metro" del eje no es un metro en el
  suelo, y a 25 °N el error sería del 10 %.
- La mancha se dibuja **traslúcida** (α = 0.42) y se omite el sombreado de peso
  de las celdas; si no, tapan justo las calles que se quería ver.
- Los mosaicos se cachean en `cache/tiles/`, así que solo la primera corrida pide
  red. Si la red falla, la figura se genera **sin fondo** en vez de tumbar la
  corrida.
- El servidor de OSM rechaza el user-agent por omisión de contextily con un 403;
  `urbano/mapas/estilo.py` declara uno propio, como pide su política de uso.
  Alternativas configurables en `E.PROVEEDORES`: `esri` (Esri WorldStreetMap) y
  `claro` (CartoDB Positron). *CartoDB Voyager quedó descartado: estampa una
  marca de agua "API KEY REQUIRED".*

Para saltarlas: `--sin-base` en `urbano.construir` o en `urbano.mapas.estaticos`.

### Catálogo completo (`Results/Tamaulipas/urbano/catalogo/`)

Una lámina por **cada** localidad urbana del estado, en rejilla 3 × 4:

| serie | qué | orden | páginas |
|---|---|---|---|
| `cabeceras_NdeM.png` | las 43 cabeceras municipales | clave INEGI (001 Abasolo → 043 Xicoténcatl) | 4 |
| `otras_localidades_NdeM.png` | las 20 localidades urbanas que no son cabecera | área descendente | 2 |

Las cabeceras van por clave —no por tamaño— porque es el orden del catálogo
oficial y permite buscar un municipio sin saber cuál es su tamaño; cada lámina
antepone la clave (`mun. 003`). Las otras localidades van por área y rotulan su
municipio (`mun. Altamira (003)`), que es lo que el nombre no dice.

Cada serie existe también en `_base`, así que son 12 figuras:

```bash
conda run -n rs python -m urbano.mapas.catalogo
conda run -n rs python -m urbano.mapas.catalogo --sin-base
```

### Localidad ≠ municipio

En el panel de las 12 ciudades aparecen **Miramar** y **Altamira** como láminas
separadas. No son dos municipios: son **dos localidades urbanas del municipio de
Altamira** (clave INEGI 003). Altamira (`cve_loc 0001`) es la cabecera; Miramar
(`0122`) no lo es, y de hecho es la más grande de las dos (32.6 km² contra 25.0).
El municipio tiene además una tercera localidad urbana, Cuauhtémoc (2.9 km²).

Las láminas de las localidades que **no** son cabecera lo rotulan explícitamente
(`loc. del mun. Altamira`). Verificado en los tests: las 63 localidades caen
100 % dentro de su municipio declarado y ninguna pareja de manchas se solapa
—Miramar y Altamira comparten frontera, que es distinto—, así que el área urbana
total no cuenta nada dos veces.

`notebooks/urbano/01_manchas_y_nodos.ipynb` recorre la geometría y genera todos los mapas. Ver `notebooks/urbano/README.md` para los tres notebooks y el orden en que conviene leerlos.

## Cómo usarlo para métricas por ciudad

```python
import pandas as pd
from urbano import config as C

nc = pd.read_csv(C.CSV_NODOS_CIUDADES)
por_ciudad = (nc.merge(metricas_por_nodo, on="nodo_id")
                .assign(w=lambda d: d["peso"] * d["rmse"])
                .groupby("ciudad")["w"].sum())
```

**Filtra por `calidad` antes de comparar ciudades entre sí.** Comparar Reynosa
(25 nodos, 170 km²) contra San Nicolás (1 nodo que es 99 % campo) no es comparar
dos ciudades: es comparar una ciudad contra un pedazo de campo con un pueblo
dentro.

## Limitación conocida

Con 4 km de resolución no hay variabilidad *intra*urbana para las ciudades
chicas: su métrica es la del nodo que las contiene. Si eso llegara a importar,
la vía es re-descargar NSRDB a 2 km sobre bounding boxes urbanos — otra fase,
fuera del alcance de este módulo.

---

# Parte II — Series climáticas por ciudad (`urbano/clima/`)

Usa los pesos nodo↔ciudad para convertir series de nodo en series de ciudad:

```
nodo-hora  --(media ponderada por `peso`)-->  ciudad-hora
ciudad-hora --(media / mínimo / máximo)-->    ciudad-día
```

```bash
conda run -n rs python -m urbano.clima.construir_clima
conda run -n rs python -m urbano.clima.construir_clima --top 5
conda run -n rs python -m urbano.clima.construir_clima \
    --variables temperature relative_humidity --anios 2023 2024
conda run -n rs python -m urbano.clima.construir_clima --simple
conda run -n rs python -m urbano.clima.variables      # el catálogo
```

## ¿A qué altura está la temperatura?

**A 2 m.** Las variables meteorológicas del NSRDB no las mide el satélite: vienen
de la reanálisis **MERRA-2**. En el catálogo oficial de NREL
(`nsrdb/config/nsrdb_vars.csv`) cada una declara su dataset de origen:

| columna | dataset MERRA-2 | altura |
|---|---|---|
| `temperature` | `T2M` | **2 m**, corregida por elevación |
| `wind_speed`, `wind_direction` | `U2M` / `V2M` | **2 m** — *no* 10 m |
| `relative_humidity`, `dew_point` | derivadas de `T2M` + `QV2M` + `PS` | **2 m** |
| `pressure` | `PS` | superficie |
| `precipitable_water`, `ozone`, aerosoles | — | columna atmosférica |
| `ghi`, `dni`, `dhi` | GOES + PSM v4 | plano horizontal en superficie |

(El viento se arma en `nsrdb/data_model/merra.py` con
`height = '10M' if '_10m' in name else '2M'`; nuestra columna no lleva sufijo.)

Dos consecuencias: `temperature` **sí** es comparable con la temperatura de
abrigo de una estación (~2 m); `wind_speed` **no** lo es con un anemómetro
estándar, que la OMM define a 10 m.

El catálogo completo —unidad, altura, tipo de agregación— está en
`urbano/clima/variables.py` y se imprime con `V.tabla()`.

## Tres decisiones del método

1. **Ponderación por `peso`** por omisión: el nodo que cubre el centro de una
   ciudad pesa más que el que apenas roza un borde. Ante NaN los pesos se
   **renormalizan** sobre los nodos presentes, en vez de sesgar la media.
2. **El día es local, no UTC.** Cortar el día en UTC lo partiría a las 18:00
   hora local, mezclando el máximo de un día con el del siguiente. Se usa
   `America/Monterrey`, y `America/Matamoros` para los **10 municipios de la
   franja fronteriza** que conservaron el horario de verano (Ley de los Husos
   Horarios, DOF 2022-10-28): Camargo, Guerrero, Gustavo Díaz Ordaz, Matamoros,
   Mier, Miguel Alemán, Nuevo Laredo, Reynosa, Río Bravo y Valle Hermoso.
3. **`wind_direction` se promedia en círculo.** Promediar 350° y 10°
   aritméticamente da 180°, el rumbo contrario. Por lo mismo su mín/máx diarios
   no se reportan: en una variable circular no significan nada.

`cloud_type` y `cloud_fill_flag` son códigos, no cantidades: las agregaciones
las **rechazan** con un error explícito en vez de promediarlas en silencio.

## Promedio ponderado vs. promedio simple

`serie_horaria(..., ponderar=False)` —o `--simple` en la CLI— calcula el
**promedio simple**: todos los nodos de la ciudad cuentan igual.

Está implementado como un caso particular del ponderado (pesos uniformes `1/n`,
vía `pesos_uniformes()`), no como una rama aparte, así que hereda exactamente el
mismo trato de los NaN y la misma media circular del viento. Lo único que cambia
es el vector de pesos.

| | ponderado (por omisión) | simple (`--simple`) |
|---|---|---|
| peso de cada nodo | fracción del área urbana que cubre | `1/n` |
| representa | mejor a la ciudad | peor: el borde pesa igual que el centro |
| explicar en un informe | requiere describir la ponderación | "el promedio de los N nodos" |

**Cuánto cambian los números.** La brecha *no* crece con el número de nodos sino
con lo **desigual** que sea el reparto de pesos (temperatura, 2024):

| ciudad | nodos | peso máx. | dif. máx. |
|---|---|---|---|
| San Fernando | 5 | 0.642 | **0.61 °C** |
| Ciudad Madero | 5 | 0.478 | 0.31 °C |
| Altamira | 8 | 0.574 | 0.25 °C |
| … | | | |
| Reynosa | **25** | 0.103 | **0.09 °C** |
| Ciudad Río Bravo | 6 | 0.242 | 0.02 °C |

Reynosa, con 25 nodos, es de las que **menos** se mueven: sus pesos ya son casi
uniformes. En ciudades de un solo nodo los dos modos son idénticos.

Los dos modos escriben a **archivos distintos** (sufijo `_simple`), para que
correr uno no sobrescriba el otro en silencio.

## Salidas

| archivo | filas | versionado |
|---|---|---|
| `Data/Tamaulipas/urbano/clima/diario_ciudades.csv` | 21 936 (12 ciudades × 1 828 días) | sí (5 MB) |
| `Data/Tamaulipas/urbano/clima/horario_ciudades.parquet` | 526 176 | no (26 MB, se regenera) |
| `…_simple.csv` / `…_simple.parquet` | igual | ídem (solo si corres `--simple`) |

Todas las series —horarias y diarias, de cualquier ámbito— llevan **`cve_mun`**,
la clave INEGI del municipio. Es la llave con la que se cruzan con cualquier otra
fuente municipal; el nombre no sirve para eso, porque se escribe de varias formas
y se repite entre estados. Se guarda como cadena de 3 dígitos: leerla como
número la convierte en `3` y rompe el cruce.

El diario trae `<variable>_media`, `<variable>_min`, `<variable>_max` por
ciudad-día, más **`n_horas`**: los días de cambio de horario traen 23 o 25 h, y
el primero y el último del periodo vienen truncados. Filtra `n_horas == 24`
antes de comparar días entre sí (116 de 21 936 no lo cumplen).

## Uso

```python
from urbano.clima import agregacion as G
from urbano.clima import variables as V

# Cualquier subconjunto de variables, ciudades y años:
h = G.serie_horaria(["temperature", "relative_humidity"], top=3, anios=[2024])
d = G.resumen_diario(h)

# Una ciudad por su clave INEGI:
vic = G.serie_horaria(["temperature"], cvegeos=["280410001"], anios=[2024])

# Promedio simple en vez de ponderado:
h_simple = G.serie_horaria(["temperature"], top=3, anios=[2024], ponderar=False)
```

`notebooks/urbano/02_clima_por_ciudad.ipynb` documenta el método: catálogo de
variables y alturas, la media ponderada, el huso horario, el resumen diario y la
comparación ponderado vs. simple.

## Consultar: `urbano.clima.consulta`

Es la capa que hace usable todo lo anterior.

```python
from urbano.clima import consulta as Q

Q.catalogo()                      # las 63 unidades: clave, nombre, municipio, cobertura
Q.resolver("victoria")            # -> "280410001"

Q.serie(["temperature"], ciudad="victoria",
        desde="2024-06-01", hasta="2024-06-30", frecuencia="dia")
```

### Identificar por nombre o clave

`resolver()` prueba, del más específico al más laxo:

1. clave `cvegeo` exacta → `"280410001"`
2. nombre exacto de la localidad → `"Ciudad Victoria"`
3. nombre exacto del **municipio** → `"Victoria"` (devuelve su cabecera)
4. coincidencia parcial única → `"matamoros"`

El paso 3 existe porque uno piensa en el municipio: `"victoria"` es ambiguo como
texto —hay también *Guadalupe Victoria*, en Abasolo— pero único como municipio.
Si queda ambigüedad real, el error **lista los candidatos** en vez de adivinar.

### Rango de fechas

`desde` y `hasta` son **inclusivos y en hora local**. Solo se abren los años
necesarios, más el siguiente al del final: las últimas horas del 31 de diciembre
local viven en el archivo del año siguiente (local = UTC−6), y sin él ese día
saldría con 18 h. Un rango fuera de los datos o invertido falla con un mensaje
que lo dice, antes de tocar disco.

### Los cinco ámbitos

| ámbito | unidades | qué es |
|---|---|---|
| `cabeceras` | 43 | las cabeceras municipales |
| `otras` | 20 | localidades urbanas que no son cabecera |
| `localidades` | 63 | todas |
| `conglomerados` | 55 | manchas conurbadas agrupadas (Tampico+Madero+Miramar+Altamira = 1) |
| `global` | 1 | todo lo urbano del estado como una sola serie |

**Agrupar no es promediar los promedios.** El `peso` de `nodos_ciudades.csv` está
normalizado *dentro de cada localidad*, así que sumarlo entre localidades le daría
la misma importancia a un pueblo de 1 km² que a Reynosa. Para agrupar se vuelve al
peso **absoluto** (`peso × área` = km² de ciudad que el nodo cubre), se suma por
nodo y se renormaliza sobre el grupo. El conglomerado de Tampico queda así:

| localidad | km² | % del conglomerado |
|---|---|---|
| Tampico | 55.0 | 34.2 |
| Ciudad Madero | 48.0 | 29.9 |
| Miramar | 32.6 | 20.3 |
| Altamira | 25.0 | 15.6 |

— exactamente su proporción de área urbana.

`notebooks/urbano/03_consultas.ipynb` es el **manual de uso** completo: los
nueve pasos, cada variante con su ejemplo (una ciudad, varias, por clave, por
municipio, por ámbito, promedio simple), un recetario (agregación mensual, solo
horas de sol, comparar ciudades, días completos) y la tabla de errores frecuentes
con lo que significa cada uno.

### Bajar al nodo

Todos los ámbitos promedian varios nodos. `nodo=` hace lo contrario: devuelve el
dato **crudo** de un punto de la malla, sin promediar nada.

```python
Q.serie(["temperature"], nodo=1737, desde="2024-06-01", hasta="2024-06-30",
        frecuencia="dia")

Q.nodos_interes()            # los 12 nodos señalados a mano, uno por ciudad
Q.catalogo_nodos("victoria") # los 12 nodos de Victoria, por peso descendente
Q.pesos_nodo([1737, 3978])   # funciona con cualquiera de los 4384 nodos
```

`nodo=` manda sobre `ciudad=` y `ambito=`, y rechaza `ponderar=False` (un solo
nodo no se promedia con ninguno). El municipio —y con él el huso horario— se
resuelve por geometría, así que sirve también para nodos que no tocan ninguna
mancha urbana.

Hay **dos** juegos de nodos señalados a mano:

| archivo | qué | mapas |
|---|---|---|
| `nodos_interes.csv` | 12 nodos, uno por cada ciudad grande | `panel_nodos_seleccionados[_base].png` |
| `nodos_interes_municipios.csv` | **43 nodos, uno por cabecera municipal** | `catalogo/nodos_de_interes/nodos_municipios_NdeM[_base].png` |

```bash
conda run -n rs python -m urbano.mapas.nodo --interes     # los 12, en rejilla
conda run -n rs python -m urbano.mapas.nodo --municipios  # las 43, 4 páginas × 2
```

Los 11 nodos en que ambos juegos se solapan (Miramar no es cabecera) **coinciden
exactamente**: son dos detecciones independientes sobre imágenes distintas, y
sirven de comprobación mutua. Hay un test que lo verifica.

**Gómez Farías es un caso aparte.** Sus páginas se marcaron antes de corregir la
cabecera, así que el círculo caía sobre *Loma Alta*; el nodo bueno —el **784**,
en la cabecera de verdad— se tomó de un recorte marcado aparte, verificado
comprobando que la razón de separaciones entre nodos en el recorte (1.0854)
coincide con la esperada a 23.03 °N (1.0866).

**Los 12 nodos señalados** viven en `Data/Tamaulipas/urbano/nodos_interes.csv`.
Se marcaron a mano sobre `panel_ciudades_base.png` y se identificaron detectando
los círculos por color y proyectándolos a coordenadas del mapa: el nodo elegido
quedó a 0.1–1.2 km del centro de cada círculo y el siguiente a 3.6–4.4 km (la
malla es de ~4 km), así que no hay ambigüedad. Nueve de los doce son el nodo
dominante de su ciudad; Tampico, Río Bravo y Valle Hermoso no.

| ciudad | nodo | ciudad | nodo | ciudad | nodo |
|---|---|---|---|---|---|
| Reynosa | 3978 | Tampico | 1 | Altamira | 25 |
| Nuevo Laredo | 4342 | Ciudad Madero | 5 | Ciudad Mante | 331 |
| Heroica Matamoros | 3841 | Miramar | 13 | Valle Hermoso | 3659 |
| Ciudad Victoria | 1737 | Ciudad Río Bravo | 3925 | San Fernando | 3037 |

### Mapas de nodo (`urbano/mapas/nodo.py`)

Mismo encuadre que la lámina de ciudad —para poder compararlas— con un nodo
marcado y los demás atenuados:

```bash
conda run -n rs python -m urbano.mapas.nodo 1737          # una lámina
conda run -n rs python -m urbano.mapas.nodo 1737 --base   # sobre mapa base
conda run -n rs python -m urbano.mapas.nodo --interes     # los 12, en rejilla
```

Salidas: `Results/Tamaulipas/urbano/nodos/nodo_<id>[_base].png` y
`panel_nodos_seleccionados[_base].png`.

### Generar los archivos de cada ámbito

```bash
python -m urbano.clima.construir_clima --ambito cabeceras
python -m urbano.clima.construir_clima --ambito conglomerados
python -m urbano.clima.construir_clima --ambito global
python -m urbano.clima.construir_clima --todos-los-ambitos
```

Cada ámbito escribe `diario_<ambito>.csv` y `horario_<ambito>.parquet`, así que
no se pisan (y `--simple` añade su sufijo).

**Tamaño:** un juego completo son **~395 MB** (86 MB solo en CSV). `.gitignore`
versiona únicamente `diario_ciudades.csv` y `diario_global.csv`; lo demás se
regenera con el comando de arriba. Si quieres versionar algún ámbito más, quita
su línea del `.gitignore`.

## Advertencia

Ninguna de estas series capta la **isla de calor urbana**: MERRA-2 tiene ~50 km
de resolución nativa y no modela el efecto urbano. `temperature` es la
temperatura regional a 2 m interpolada a la celda de 4 km, no la de la calle.
Súmalo a la advertencia de `calidad`: de las 12 ciudades, solo 4 tienen
cobertura alta.

## Estructura

```
urbano/
├── config.py              fuente, CRS, umbrales, rutas
├── construir.py           pipeline completo (CLI)
├── data/
│   ├── descarga_mgn.py    baja y descomprime el MG del INEGI
│   ├── cabeceras.py       qué localidad es la cabecera (catálogo AGEEML)
│   └── manchas.py         localidades urbanas + conglomerados
├── nodos/asignacion.py    cascada de asignación, pesos y calidad
├── clima/
│   ├── variables.py       catálogo NSRDB: unidad, altura, tipo de agregación
│   ├── agregacion.py      nodo-hora -> ciudad-hora -> ciudad-día
│   ├── consulta.py        buscar por nombre/clave, rango de fechas, ámbitos
│   └── construir_clima.py CLI de las series climáticas
├── mapas/
│   ├── estilo.py          paleta y utilidades (barra de escala, ejes)
│   ├── estaticos.py       los cuatro PNG (× 2 versiones)
│   ├── catalogo.py        las 63 localidades paginadas 3 × 4
│   ├── nodo.py            lámina de un nodo concreto dentro de su ciudad
│   └── interactivo.py     el HTML de folium
└── tests/                 invariantes del análisis
```
