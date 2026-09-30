# Comparación NSRDB vs ERA5

Series de tiempo de las tres fuentes sobre los **mismos 43 nodos** (uno por
cabecera municipal de Tamaulipas), y la función que las dibuja.

- **[`comparacion_nsrdb_era5.ipynb`](comparacion_nsrdb_era5.ipynb)** — cuaderno
  ejecutado, con un ejemplo de cada cosa que la función sabe hacer.
- **`copernicus/graficas.py`** — el código.

```bash
conda run -n rs jupyter lab notebooks/comparacion_fuentes/
```

## Qué hay comparado

| fuente | resolución | periodo | origen |
|---|---|---|---|
| **NSRDB** PSM v4 | 0.04° (~4 km) | 2020–2024 | satélite GOES + meteorología MERRA-2 |
| **ERA5-Land** | 0.1° (~9 km) | 2020–2025 | reanálisis, **solo tierra** |
| **ERA5-single** | 0.25° (~31 km) | 2020–2025 | reanálisis |

Variables con contraparte en las dos fuentes: `ghi`, `temperature`, `dew_point`,
`relative_humidity`, `pressure`, `wind_speed`, `wind_direction`.

Los datos de ERA5 salen de
`Data/Tamaulipas/era5/<producto>/series/<producto>_completo.parquet`
(2 262 144 filas = 43 nodos × 52 608 horas). Si faltan, se regeneran con:

```bash
conda run -n rs python -m copernicus.extraer --producto land \
    --anios 2020 2021 2022 2023 2024 2025 --consolidar
```

## La función

```python
from copernicus.graficas import comparar_series

comparar_series("ghi", lugares="victoria", desde="2024-06-01", hasta="2024-06-07")
```

**Solo `variable` es obligatoria.** Todo lo demás tiene valor por omisión.

| parámetro | qué hace | por omisión |
|---|---|---|
| `variable` | qué se compara | `"ghi"` |
| `lugares` | `nodo_id`, nombre de municipio, o lista de ambos | los 43 |
| `desde` / `hasta` | rango inclusivo, en hora local | sin límite |
| `horas` | `(11, 17)` rango inclusivo, o `[6, 12, 18]` horas sueltas | todas |
| `meses` | `[6, 7, 8]` | todos |
| `fuentes` | subconjunto de `NSRDB`, `ERA5-Land`, `ERA5-single` | las tres |
| `frecuencia` | `"hora"`, `"dia"`, `"mes"` | `"hora"` |
| `agregacion` | `"media"`, `"max"`, `"min"`, `"suma"` | `"media"` |
| `tz` | `"local"` o `"utc"` — cambia el eje **y los filtros de hora** | `"local"` |
| `facetas` | `"auto"` (un panel por lugar si hay varios), `True`, `False` | `"auto"` |
| `titulo`, `subtitulo`, `etiqueta_x`, `etiqueta_y`, `nota` | textos | autogenerados |
| `leyenda` | mostrarla (con una sola fuente se oculta sola) | `True` |
| `figsize`, `ax`, `guardar` | lienzo y salida | — |
| `datos` | tabla ya cargada con `cargar()`, para no releer | — |
| `mostrar_tabla` | devolver también los datos dibujados | `False` |

Devuelve la `Figure` (o `(Figure, DataFrame)` con `mostrar_tabla=True`).

### Los textos tienen tres estados

- **omitido** (`None`) → se autogenera a partir de los datos;
- **una cadena** → se usa tal cual;
- **`""`** → se quita, sin dejar hueco.

```python
comparar_series("ghi", lugares="victoria", desde="2024-06-01", hasta="2024-06-05",
                titulo="Irradiancia en Ciudad Victoria",
                subtitulo="", nota="")           # sin subtítulo ni pie
```

### Los lugares se resuelven de forma laxa

`"victoria"`, `"VICTORIA"` y `"Victoria"` son lo mismo; los acentos no importan
(`"guemez"` → Güémez) y una coincidencia parcial única vale. Un nombre que no
existe **falla ahí mismo**, con la lista de candidatos, en vez de producir una
gráfica vacía. `catalogo_lugares()` lista los 43.

### Cargar una vez, dibujar muchas

Leer el NSRDB de varios años tarda. `cargar()` devuelve la tabla larga y
`comparar_series(datos=...)` la reutiliza aplicando los filtros encima:

```python
from copernicus.graficas import cargar

d = cargar("ghi", lugares=["Victoria", "Tampico"], desde="2024-01-01", hasta="2024-12-31")
comparar_series(datos=d, lugares="Victoria", meses=[1], frecuencia="dia")
comparar_series(datos=d, horas=(12, 16), frecuencia="mes")
```

## Decisiones de diseño

### Color = fuente, faceta = lugar

El color identifica **siempre** la misma fuente —NSRDB azul, ERA5-Land naranja,
ERA5-single verde-agua— y nunca el lugar. Si el color se repartiera entre
municipios, añadir uno repintaría los demás y dos figuras del mismo cuaderno
dejarían de poderse leer juntas.

Por eso varios lugares van a **paneles separados** en vez de a más colores sobre
los mismos ejes: tres fuentes × cinco municipios son quince líneas superpuestas.
Con `facetas=False` se fuerza el eje único y los lugares se distinguen por el
estilo de línea; es legible con dos, no con cinco.

Los tres colores son los slots 1–3 de la paleta categórica de referencia, que
son los que validan **todos** los pares entre sí para daltonismo (CVD ΔE 9.2 en
claro). Importa porque las tres líneas se cruzan constantemente y cualquier par
puede quedar adyacente.

### El NSRDB es la referencia

Va con línea más gruesa y por encima de las otras dos: es contra lo que se mide.

## Cuatro cosas que hay que saber leer

### 0. Cada fuente etiqueta la hora en un extremo distinto del intervalo

**Lo más importante de esta página.** Las dos series están en **UTC** —ni el CDS
ni el parquet del NSRDB traen hora local— así que el desfase no tiene nada que
ver con husos ni con el horario de verano. Es dónde pone cada una la etiqueta:

- **NSRDB** etiqueta con el **inicio** del intervalo: el valor `12:00` es el
  promedio de 12:00–13:00.
- **ERA5** acumula `ssrd` sobre la **hora anterior** y etiqueta con el **final**:
  el valor `13:00` es lo acumulado entre 12:00 y 13:00.

El mismo intervalo físico 12:00–13:00 el NSRDB lo llama *12* y ERA5 lo llama
*13*. Se ve directamente en el perfil diurno medio de junio 2024 en Victoria
(W/m², UTC) — **ERA5 en `t` es el NSRDB en `t−1`**:

| hora UTC | NSRDB | ERA5-Land |
|---|---|---|
| 12 | 66.4 | 0.4 |
| 13 | 227.6 | **65.2** |
| 14 | 395.1 | **225.5** |
| 15 | 540.9 | **403.2** |
| 16 | 681.0 | **562.4** |

Que el NSRDB etiqueta el inicio se confirma con un reloj independiente: en
Victoria (lon −99.14°) el mediodía solar cae a las **18.6 UTC**, y el mínimo de
`solar_zenith_angle` está etiquetado a las **18 UTC** — el centro real de ese
intervalo, 18:30. (De paso: eso prueba que el parquet está en UTC y no en hora
local estándar, donde el mínimo caería cerca de las 12.)

Lo que cuesta no alinearlo:

| variable | RMSE sin alinear | RMSE con −1 h | corr sin alinear | corr con −1 h |
|---|---|---|---|---|
| `ghi` (W/m²) | 121.11 | **75.71** | 0.925 | 0.971 |
| `temperature` (°C) | 3.93 | 3.37 | 0.907 | 0.956 |
| `pressure` (mbar) | 25.62 | 25.61 | 0.977 | 0.987 |

**El RMSE del GHI baja un 37 % solo por reetiquetar la hora.**

#### Las variables instantáneas son otro caso

El desfase de una hora **exacto** es el del GHI, y viene de la acumulación. Para
`t2m`, `sp`, `u10` y `v10` ERA5 da valores **instantáneos en `t`**, no
acumulados: frente al NSRDB —media de `[t, t+1)`, centrada en `t+30min`— el
desajuste real es de **media hora**, y con datos horarios no se puede resolver
medio paso. Empíricamente `−1` sale mejor que `0` (3.93 → 3.37 °C en
temperatura), pero **ninguno de los dos es exacto**. En presión casi da igual,
porque es una variable suave que media hora apenas mueve.

Así que: para GHI, reetiquetar es una corrección; para las instantáneas es una
aproximación que hay que elegir y documentar, no mezclar entre análisis.

#### Consecuencias

**Toda métrica calculada sin alinear sobrestima la discrepancia entre fuentes.**
Las cifras de [`copernicus/README.md`](../../copernicus/README.md) ya están
re-medidas con `--alinear`, y esa página conserva la tabla anterior al lado para
que se vea qué cambió.

Los datos se dejan tal como los entrega cada fuente —corregirlos por dentro
escondería el problema—, así que el desplazamiento se aplica explícitamente al
comparar. La sección 12 del cuaderno trae el código; conviene pensarlo como
"restar una hora a la marca de tiempo de ERA5" y no como un `shift` con signo,
que es donde uno se equivoca.

Y si ERA5 va a entrar como **feature del forecast**, el reetiquetado es
obligatorio antes de construir los lags: sin él se mete información del propio
intervalo que se quiere predecir.

### 1. Los periodos no coinciden

ERA5 llega a **2025**, el NSRDB a **2024**. Pedir 2025 no es un error: se dibuja
ERA5 y el pie dice hasta dónde llega el NSRDB. Sin ese aviso, la línea azul
cortándose se leería como "el NSRDB cayó a cero".

### 2. El viento no es comparable, y la humedad tampoco

`wind_speed` y `wind_direction` están a **10 m en ERA5 y a 2 m en el NSRDB**. El
viento crece con la altura, así que ERA5 sale sistemáticamente más alto: eso no
es error del reanálisis, es que no son la misma medida.

`relative_humidity` no la mide ninguna de las dos: el NSRDB la deriva de
T2M+QV2M+PS y ERA5 de T2M+Td por Magnus-Tetens. Parte de la diferencia viene de
la fórmula.

La figura marca ambos casos en el pie automáticamente.

### 3. La franja fronteriza va una hora aparte, pero solo en verano

Los 10 municipios fronterizos (Reynosa, Matamoros, Nuevo Laredo, Río Bravo…)
**mantuvieron el horario estacional** cuando el resto de Tamaulipas lo dejó en
2022. No es que estén en otro huso todo el año:

| fecha (18:00 UTC) | Victoria (interior) | Reynosa (frontera) |
|---|---|---|
| 2024-01-15 | 12:00 (UTC−6) | 12:00 (UTC−6) |
| 2024-07-15 | 12:00 (UTC−6) | **13:00 (UTC−5)** |
| 2021-07-15 | 13:00 (UTC−5) | 13:00 (UTC−5) |

En invierno coinciden; en verano difieren una hora. Y **antes de 2022 todo el
estado aplicaba el horario de verano**, así que en 2020 y 2021 el interior
también se mueve.

Esto afecta **solo a la presentación**, nunca al cruce de series: las dos fuentes
están en UTC y ahí es donde se unen. La conversión a local se hace por municipio
y el pie de la figura nombra las zonas en juego.

La trampa práctica: al mezclar un fronterizo con uno del interior en verano, un
filtro `horas=(11, 17)` **no está comparando el mismo instante** en los dos —
"las 13:00 local" son momentos distintos. Si eso estorba para un análisis
concreto, `tz="utc"` pone ambos en el mismo reloj.

## Qué se ve en los datos

Del cuaderno, con 2024 completo:

- **En GHI las dos versiones de ERA5 empatan** (RMSE ~121 W/m² sin alinear, ~76
  alineando la hora; ver el punto 0). Coinciden casi exactamente en días
  despejados y se separan con nubes: a esta escala la irradiancia la manda la
  nubosidad, y ahí el NSRDB parte de observación satelital mientras ERA5 la
  modela. La resolución no decide.
- **En temperatura sí decide, pero por la altitud, no por la malla.** En
  Miquihuana (1946 m) ERA5-Land se queda 3–4 °C por debajo todo el año mientras
  ERA5-single acierta: la celda que le toca promedia una altitud distinta a la
  del nodo, y a −6.5 °C/km eso solo explica el sesgo. En Tampico, a nivel del
  mar, las tres se pegan.
- **Las mínimas diarias se separan más que las máximas**, porque el enfriamiento
  nocturno depende del terreno local que una celda de 9 o 31 km promedia.

## Métricas

La gráfica muestra la forma; el número está en `copernicus.comparar`:

```bash
# --alinear reetiqueta ERA5 una hora atrás (ver el punto 0). Sin él, la tabla
# sale con el desfase dentro y el propio comando lo avisa al final.
conda run -n rs python -m copernicus.comparar --anios 2024 --meses 6 --alinear
```

Junio 2024 sobre los 43 nodos, lo que cambia el flag:

| variable (ERA5-Land) | RMSE sin alinear | RMSE con `--alinear` |
|---|---|---|
| `ghi` | 130.55 W/m² | **82.50 W/m²** |
| `temperature` | 2.91 °C | 2.51 °C |
| `pressure` | 12.31 mbar | 12.30 mbar |

El **sesgo apenas se mueve** (−9.99 → −9.75 W/m² en GHI), que es justo lo que se
espera: un desplazamiento temporal no cambia la media, solo el emparejamiento
punto a punto. Si al alinear cambiara también el sesgo, sería señal de que el
problema es otro.

La sección 11 del cuaderno calcula sesgo, MAE, RMSE y correlación sobre la misma
tabla que ya se cargó, global y por municipio.
