# Copernicus — ERA5 sobre los nodos NSRDB

Descarga reanálisis de Copernicus para **los mismos 43 puntos** que ya tenemos en
NSRDB (uno por cabecera municipal), para medir cuánta diferencia hay entre
fuentes.

```bash
conda run -n rs python -m copernicus.descarga --disponibilidad 2025
conda run -n rs python -m copernicus.descarga --prueba          # un mes, ambos
conda run -n rs python -m copernicus.descarga --producto land --anios 2020 2021 2022 2023 2024 2025
conda run -n rs python -m copernicus.extraer  --producto land --anios 2020 2021 2022 2023 2024 2025 --consolidar
conda run -n rs pytest copernicus/tests -q
```

> **Estado**: descargado y extraído **2020–2025 completo** en los dos productos
> (72 meses × 2, sin huecos). `Data/Tamaulipas/era5/<producto>/series/<producto>_completo.parquet`
> son 2 262 144 filas = 43 nodos × 52 608 horas.
>
> Para **graficar** la comparación contra el NSRDB está `copernicus.graficas`;
> los ejemplos y la documentación, en
> [`notebooks/comparacion_fuentes/`](../notebooks/comparacion_fuentes/README.md).

> Ojo con el log cuando la descarga corre en segundo plano: `conda run`
> bufferiza la salida y el archivo se queda vacío hasta que el proceso termina.
> Para vigilar un trabajo de horas hay que invocar el intérprete directo,
> `~/miniconda3/envs/rs/bin/python -u -m copernicus.descarga …`.

## Por qué se llama `copernicus` y no `era5`

macOS no distingue mayúsculas en el sistema de archivos, así que un paquete
`era5/` se mezclaría con la carpeta `ERA5/` del notebook de referencia:
funcionaría aquí por accidente y fallaría en Linux, que sí distingue. El nombre
además deja sitio a otros productos del mismo proveedor.

> Ficha completa de todas las fuentes del proyecto en
> [`docs/fuentes_geograficas.md`](../docs/fuentes_geograficas.md).

## Las tres fuentes que se comparan

| fuente | resolución | origen de la meteorología |
|---|---|---|
| NSRDB PSM v4 | 0.04° (~4 km) | satélite GOES + MERRA-2 |
| ERA5-Land | 0.1° (~9 km) | reanálisis, **solo tierra** |
| ERA5 single levels | 0.25° (~31 km) | reanálisis |

## Credenciales

De `.env` (ignorado por git), claves `URL_ERA5` y `KEY_ERA5`. Se lee con la ruta
explícita del repo y no con `load_dotenv()`, que busca desde el directorio de
trabajo: desde un notebook en otra carpeta devolvería `None` sin avisar.

Ninguna clave se escribe en el código; hay un test que lo comprueba.

## Estrategia de descarga

**Un solo bounding box** `[27.75, −100.10, 21.95, −97.20]` para los 43 nodos, no
43 peticiones: la cola del CDS es el cuello de botella, la descarga en sí son
megabytes.

**Un mes por petición.** Las peticiones grandes se rechazan o se encolan
indefinidamente, y trocear por mes hace la descarga reanudable: cada mes ya
bajado se salta, que es lo que hace falta cuando el proceso dura horas.

**El CDS devuelve ZIP aunque pidas `netcdf`** cuando el pedido mezcla variables
instantáneas (temperatura, viento) con acumuladas (radiación). Dentro vienen dos
NetCDF, uno por tipo de paso. `normalizar()` los deja como `..._instant.nc` y
`..._accum.nc`.

## La trampa: la acumulación de `ssrd`

`ssrd` viene en J/m² acumulados y **la ventana no es la misma en los dos
productos**:

| producto | ventana | conversión a W/m² |
|---|---|---|
| ERA5 `single` | la hora anterior | `ssrd / 3600` |
| ERA5-`land` | **desde las 00 UTC del día** | diferencia de pasos consecutivos, salvo a las 01 UTC |

A las 01 UTC el acumulado ya es la primera hora del día; restarle el paso de las
00 —que trae las 24 h anteriores— daría un negativo enorme. Y el paso de las
00 UTC, diferenciado contra las 23 UTC del día previo, da correctamente la
última hora de ese día.

Aplicar la regla de `single` a `land` produce una irradiancia que **crece a lo
largo del día**: absurda físicamente, pero no evidentemente rota en una tabla.
Hay un test que documenta ese modo de fallo.

Consecuencia: la primera hora de cada archivo mensual de `land` no se puede
desacumular sin el último paso del mes anterior. Por eso se guarda también
`ssrd_acum` (el crudo) y `consolidar()` recalcula la irradiancia sobre la serie
completa, dejando un único hueco al principio de todo en vez de uno por mes.

## Otras diferencias que hay que tener presentes

- **Viento**: ERA5 lo da a **10 m**; NSRDB a **2 m**. No son el mismo dato. Se
  extraen tal cual, sin extrapolar, y la comparación debe decirlo.
- **Humedad relativa**: ninguna de las dos fuentes la mide. NSRDB la deriva de
  T2M+QV2M+PS; aquí se deriva de T2M+Td por Magnus-Tetens. Parte de la
  diferencia puede venir de la fórmula, no del dato.
- **ERA5-Land es solo tierra.** Un nodo costero puede caer en una celda de mar
  (NaN). Se busca la celda con datos más cercana y se marca `celda_fallback`.
- **Altitud**: los nodos van de 6 a 2140 m. Una celda de 31 km sobre la Sierra
  Madre promedia altitudes muy distintas; a −6.5 °C/km eso solo explica varios
  grados de sesgo. La columna `dist_celda_km` está en la salida por lo mismo.

## Disponibilidad

`--disponibilidad ANIO` hace una petición mínima al 31 de diciembre de ese año
en vez de fiarse de la documentación. **Comprobado: 2025 está completo en los
dos productos** (ERA5-Land suele ir con dos o tres meses de retraso, así que no
se puede dar por hecho).

## Resultado de la prueba de un mes (enero 2024, 43 nodos)

Descarga: `single` 2.5 MB en ~7 min de cola; `land` 13 MB. Extracción sin
incidencias, **ningún nodo necesitó celda de respaldo** (ninguno cayó en mar).

| | ERA5-Land (0.1°) | ERA5 single (0.25°) |
|---|---|---|
| distancia nodo→celda, mediana | **4.2 km** | 9.7 km |
| distancia máxima | 6.9 km | 15.8 km |

RMSE de ERA5 respecto al NSRDB, promediado sobre los 43 nodos, **con las horas
alineadas** (`--alinear`, ver más abajo):

```bash
conda run -n rs python -m copernicus.comparar --anios 2024 --meses 1 --alinear
```

| variable | land | single | mejora de land |
|---|---|---|---|
| presión (mbar) | **7.92** | 12.80 | 38.1 % |
| temperatura (°C) | **2.35** | 2.78 | 15.3 % |
| punto de rocío (°C) | **2.58** | 2.67 | 3.2 % |
| GHI (W/m²) | 78.87 | 79.03 | 0.2 % |

> **Qué cambió respecto a la versión anterior de esta tabla.** Estaba medida sin
> alinear la hora. Las dos fuentes están en UTC, pero etiquetan el intervalo en
> extremos opuestos: el NSRDB con el inicio (`12:00` = promedio de 12:00–13:00)
> y ERA5 con el final (`13:00` = acumulado de 12:00 a 13:00), así que el merge
> emparejaba cada hora de ERA5 con la siguiente del NSRDB.
>
> | variable | sin alinear | alineado |
> |---|---|---|
> | GHI (W/m²) | 111.53 | **78.87** |
> | temperatura (°C) | 2.94 | **2.35** |
> | punto de rocío (°C) | 2.67 | 2.58 |
> | presión (mbar) | 8.05 | 7.92 |
>
> El GHI baja un **29 %** y la temperatura un 20 %; la presión apenas se mueve,
> porque es una variable suave que una hora no cambia. **Las conclusiones de
> abajo se mantienen**: el orden entre productos y la ventaja de `land` en las
> variables de terreno son los mismos, solo que sin el desfase sumado encima.
>
> En el GHI la corrección es exacta (viene de la acumulación de `ssrd`); en las
> instantáneas (`t2m`, `sp`, viento) el desajuste real es de media hora y no se
> resuelve con datos horarios, así que ahí alinear mejora pero no deja exacto.
> Detalle y evidencia en
> [`notebooks/comparacion_fuentes/`](../notebooks/comparacion_fuentes/README.md),
> sección 0.

Dos lecturas que salen de aquí:

- **La resolución fina gana donde manda el terreno.** El sesgo de presión
  correlaciona con la altitud del nodo (r = −0.48): Jaumave (752 m), Ocampo
  (363 m) y Miquihuana (1946 m) son los peores, porque la orografía de la celda
  no coincide con la del punto. En temperatura la ganancia es menor (15.3 %) y
  en GHI, nula.
- **En GHI los dos productos empatan** (RMSE ~79 W/m², correlación 0.94). Tiene
  sentido: la irradiancia a esta escala la manda la nubosidad, no el relieve, y
  ahí NSRDB parte de observación satelital mientras ERA5 la modela. Es
  justamente la diferencia entre fuentes que se quería medir.

El sesgo del viento sale positivo (+0.4 m/s en land, +0.6 en single) como se
esperaba del desfase 10 m vs 2 m; no debe leerse como error del reanálisis. Es
además insensible a la alineación —desplazar una serie no cambia su media—, que
es justo lo que confirma que el desfase era de emparejamiento y no de nivel.

## Salidas

```
Data/Tamaulipas/era5/<producto>/
├── crudos/    lo que entrega el CDS (puede ser ZIP)
├── nc/        NetCDF normalizados
└── series/    parquet por mes + <producto>_completo.parquet
```

Todo ignorado por git: son gigabytes reproducibles.
