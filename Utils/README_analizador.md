# `AnalizadorSolar` — análisis exploratorio y de integridad

Herramienta para explorar, validar y comparar los datasets NSRDB consolidados
(parquet de 24 h) de Tamaulipas / Puerto Rico. Es la compañera de
[`mapas_espaciales.MapaEspacial`](mapas_espaciales.py): aquella resuelve la
dimensión **espacial** (un valor por nodo sobre el mapa); `AnalizadorSolar`
cubre **estadística, integridad, series temporales, correlaciones, índice de
claridad, comparación entre años y exportación**.

- Módulo: [`Utils/analizador_datos.py`](analizador_datos.py)
- Diseñada para **notebook** (los métodos de gráfica devuelven el `Figure`, que
  el notebook muestra solo) y para **consola/scripts** (pasando
  `guardar='ruta.png'` se escribe el PNG; además hay una CLI).
- Referencia de columnas, unidades y flags:
  [`Data/Tamaulipas/REFERENCIA_NSRDB.md`](../Data/Tamaulipas/REFERENCIA_NSRDB.md).

---

## 1. Instalación / requisitos

Usa las dependencias que ya tiene el proyecto (`pandas`, `pyarrow`,
`matplotlib`, `numpy`). Para `exportar` a Excel hace falta `openpyxl`.

---

## 2. Creación del analizador

```python
from Utils.analizador_datos import AnalizadorSolar

# (a) Consolidado estándar del proyecto, por año y región:
a = AnalizadorSolar(anio=2024)                       # Tamaulipas 2024
a = AnalizadorSolar(anio=2017, region='Puerto_Rico') # otra región

# (b) Un parquet cualquiera (consolidado o un trozo individual):
a = AnalizadorSolar(parquet="ruta/al/archivo.parquet")

# (c) Parámetros opcionales: caché y tolerancia de presión
a = AnalizadorSolar(anio=2024,
                    usar_cache=True,   # caché de lectura (def. True)
                    cache_max=4,       # nº de filtros distintos a retener
                    tol_presion=60)    # ±mbar para el chequeo de presión
```

La ruta estándar que arma sola es:
`Data/<Region>/<anio>/Finales/completo/dataset_<region>_completo_24h_<anio>.parquet`.

> La carga es **perezosa** y con *predicate pushdown*: los métodos solo leen del
> disco las columnas y filas que pides.

**Caché de lectura.** Cada lectura se guarda por *firma de filtro* (nodos/mes/
día/hora/rango). Las llamadas posteriores con el **mismo filtro** reutilizan lo
ya leído —aunque pidan otras columnas, solo se lee del disco lo que falte—, lo
que acelera mucho re-ejecutar celdas y los análisis encadenados (p.ej. repetir
`integridad(mes=2)` pasa de ~11 s a ~1.5 s). Se desactiva con `usar_cache=False`
y se vacía con `a.limpiar_cache()`.

---

## 3. Filtros (comunes a casi todos los métodos)

Todos los métodos de estadística y gráfica aceptan estos parámetros de filtro
(se delegan a `filtrar`):

| Parámetro | Tipo | Ejemplo | Qué hace |
|---|---|---|---|
| `nodos` | int / lista | `nodos=[0,1,2]` | Filtra por `nodo_id`. |
| `mes` | int / lista | `mes=2` | Mes(es) 1-12. |
| `dia` | int / str / lista | `dia='2024-02-29'` | Día del mes o fecha `YYYY-MM-DD` / `MM-DD`. |
| `hora` | int / lista | `hora=[12,13]` | Hora(s) UTC 0-23. |
| `rango_fechas` | (str, str) | `('2024-06-01','2024-06-30')` | Rango por `datetime`. |
| `solo_diurno` | bool | `solo_diurno=True` | Solo horas con sol (`solar_zenith_angle < 90`). |
| `cloud_type` | int / lista | `cloud_type=[0,1]` | Filtra por código de nube. |
| `query` | str | `query="ghi>800 and relative_humidity<50"` | Filtro avanzado pandas. |
| `con_kt` | bool | `con_kt=True` | Añade la columna derivada `kt`. |

**Variable derivada `kt`** (índice de claridad = `ghi / clearsky_ghi`, definida
solo de día): se puede pedir como una columna más, p.ej.
`columnas=['nodo_id','kt']` o `con_kt=True`, y se usa igual que cualquier
variable en histogramas, estadísticas, correlaciones y comparaciones.

---

## 4. Métodos

### 4.1 Introspección

```python
a.info()          # tamaño, filas, nodos, días, rango temporal, columnas+unidades
a.variables       # columnas numéricas analizables (sin claves ni flags)
a.nodos()         # lista de nodo_id presentes
```

### 4.2 Filtrado y extracción

```python
# Subconjunto en memoria (DataFrame):
df = a.filtrar(nodos=[0,1,2], mes=2, solo_diurno=True,
               columnas=['nodo_id','datetime','ghi','dni','kt'])

# Añadir columnas legibles (cloud_type_desc, relleno=fill_flag!=0):
df = a.decodificar(df)
```

### 4.3 Estadísticas

```python
a.estadisticas(['ghi','temperature'], mes=2)   # describe + nulos por variable
a.resumen_nodos('ghi', mes=2)                  # media/std/min/max POR nodo (+coords)
a.flags(dia='2024-02-29')                      # distribución de las 3 banderas
```

### 4.4 Integridad

```python
rep = a.integridad()                  # informe impreso + dict con métricas
rep = a.integridad(graficar=True)     # + panel de flags y completitud
a.integridad(mes=2, graficar=True, guardar='integridad_feb.png')
```

Comprueba: completitud (filas reales vs esperadas), duplicados, nodos
incompletos, nulos por columna, valores fuera de rango físico, **% de datos
rellenados** (`fill_flag != 0`) y **anomalías físicas** (GHI > clearsky,
GHI/DNI = 0 de día, GHI negativo).

**Presión calibrada por elevación.** El chequeo de `pressure` no usa un rango
plano: si la metadata trae `msnm`, se compara cada valor contra la **presión
esperada por la altitud** del nodo (fórmula barométrica ISA, ver
`presion_barometrica`) con tolerancia `±tol_presion` mbar (def. 60). Así no se
marcan como anómalos los nodos de montaña (p.ej. un nodo a ~2900 m con ~700 mbar
es normal) y sí se detectan desviaciones reales (>~5σ). Ajusta la sensibilidad
con `tol_presion` al crear el analizador.

Mientras `integridad` da el **conteo**, `anomalias` devuelve las **filas**
concretas para inspeccionarlas (un DataFrame por tipo de anomalía):

```python
an = a.anomalias()                    # dict de DataFrames + resumen impreso
an = a.anomalias(mes=3, limite=None)  # sin tope de filas, acotado a marzo
an['rango_pressure']                  # filas con presión fuera del rango físico
an['dni_cero_de_dia']                 # DNI=0 con sol (suele ser cielo cubierto)
```

### 4.5 Índice de claridad y clasificación de días

```python
# kt como variable normal:
a.histograma('kt', solo_diurno=True, mes=2)
a.estadisticas(['kt'], mes=2, solo_diurno=True)

# Clasificar cada día en despejado / parcial / cubierto según kt medio diurno:
clas = a.clasificar_dias(mes=2, graficar=True)         # uno por día (región)
clas = a.clasificar_dias(por_nodo=True, mes=2)         # por (nodo, día)
# Umbrales ajustables: umbral_despejado=0.65, umbral_cubierto=0.35
```

### 4.6 Comparación inter-anual

```python
# GHI medio por mes, 2024 vs 2023 (línea por año):
a.comparar(2023, variable='ghi', por='mes', graficar=True)

# Delta por nodo (incluye delta y delta_%, con coordenadas):
a.comparar(2023, variable='kt', por='nodo', mes=2)

# Valor único agregado por año:
a.comparar([2023], variable='ghi', por='total')

# Varios años a la vez:
a.comparar([2022, 2023], variable='ghi', por='mes')
```

`por='mes'` → fila por mes, columna por año · `por='nodo'` → fila por nodo con
`delta`/`delta_%` · `por='total'` → un valor por año.

### 4.7 Gráficas

```python
a.histograma('ghi', solo_diurno=True, mes=2)
a.serie_temporal('ghi', nodos=0, dia='2024-02-29')   # un nodo o promedio de varios
a.perfil_diario('ghi', mes=6)                        # perfil horario medio 0-23h ±σ
a.correlaciones(['ghi','dni','temperature','relative_humidity'], mes=2)
```

Todas devuelven el `Figure` (visible en notebook). En consola/script añade
`guardar='salida.png'`.

### 4.8 Agregados temporales, recurso y estacionalidad

```python
# Insolación: total diario en kWh/m²/día (suma horaria × 1/1000), promedio región:
a.resamplear('ghi', frecuencia='D', agregacion='sum', factor=1/1000, graficar=True)
# GHI medio mensual; por_nodo=True devuelve una serie por nodo:
a.resamplear('ghi', frecuencia='M', agregacion='mean')
a.resamplear('temperature', frecuencia='D', por_nodo=True, mes=6)

# Curva de duración: qué valor se supera en qué % del tiempo (recurso):
a.curva_duracion('ghi', solo_diurno=True)

# Nodos atípicos según el GHI medio (z-score o IQR), con mapa de ubicación:
a.outliers_nodos('ghi', metodo='zscore', umbral=3.0, graficar=True)
a.outliers_nodos('temperature', metodo='iqr')

# Rosa de los vientos (wind_speed + wind_direction):
a.rosa_viento(mes=2)
a.rosa_viento_12meses()                    # panel 4x3, una rosa por mes

# Estacionalidad / ciclo diario:
a.boxplot('temperature', por='mes')        # boxplots por mes
a.boxplot('ghi', por='hora', solo_diurno=True)  # por hora del día
a.heatmap_mes_hora('ghi')                  # mapa de calor mes × hora
```

| Método | Para qué |
|---|---|
| `resamplear(var, frecuencia, agregacion, factor, por_nodo)` | Series horarias/diarias/mensuales; insolación en kWh/m²/día. |
| `curva_duracion(var, solo_diurno)` | Curva de excedencia (dimensionamiento de plantas). |
| `outliers_nodos(var, metodo, umbral, agg)` | Nodos atípicos (z-score / IQR) + mapa. |
| `rosa_viento(sectores, bins_velocidad)` | Rosa de los vientos (anual). |
| `rosa_viento_12meses(...)` | Panel 4x3: una rosa por mes (ciclo estacional del viento). |
| `boxplot(var, por='mes'|'hora')` | Dispersión por mes o por hora. |
| `heatmap_mes_hora(var, agregacion)` | Estacionalidad y ciclo diario en una imagen. |

### 4.9 Mapas por nodo — recurso e inter-anual (puente con `MapaEspacial`)

Pintan un valor por nodo sobre el mapa (con mapa base topográfico si está instalado
`contextily`; si no, dibujan los puntos igualmente). Requieren la metadata con coordenadas.

```python
# Atlas del recurso solar: insolación media diaria por nodo (kWh/m²/día):
a.mapa_recurso('ghi')                       # factor=1/1000, unidades='kWh/m²/día' por defecto

# Diferencia por nodo entre dos años (escala divergente centrada en 0):
a.mapa_delta(2023, variable='ghi')          # delta absoluto (W/m²)
a.mapa_delta(2023, variable='kt', relativo=True)   # delta relativo (%)
```

| Método | Para qué |
|---|---|
| `mapa_recurso(var, factor, unidades, cmap)` | Atlas de insolación media diaria por nodo. |
| `mapa_delta(otro, var, agregacion, relativo)` | Mapa de la diferencia por nodo entre años. |

### 4.10 Informe consolidado — `reporte()`

Empaqueta `info` + `integridad` + las gráficas clave en un solo documento
**HTML** (autocontenido, figuras embebidas) o **PDF** (una figura por página).
El formato se infiere de la extensión.

```python
a.reporte('informe_2024.html')          # informe del año completo
a.reporte('informe_feb.pdf', mes=2)     # acotado a febrero (mucho más rápido)
```

> Es una operación pesada (recorre el dataset varias veces): para el año completo
> puede tardar minutos. Acota con filtros (`mes=`, `nodos=`, …) para vistas rápidas.

### 4.11 Exportación

```python
a.exportar('sub.csv',     nodos=[0,1,2], dia='2024-02-29',
           columnas=['nodo_id','datetime','ghi','dni','kt'])
a.exportar('feb.parquet', mes=2, solo_diurno=True)
a.exportar('feb.xlsx',    mes=2, decodificar=True)   # con cloud_type_desc, relleno
```

Formato inferido por la extensión (`.csv`, `.parquet`, `.xlsx`, `.feather`) o
forzado con `formato=`.

---

## 5. Uso desde línea de comandos

```bash
python Utils/analizador_datos.py --anio 2024 --info
python Utils/analizador_datos.py --anio 2024 --integridad
python Utils/analizador_datos.py --anio 2024 --integridad --mes 2 --guardar integ.png
python Utils/analizador_datos.py --anio 2024 --estadisticas ghi dni temperature --mes 2
python Utils/analizador_datos.py --anio 2024 --histograma ghi --solo-diurno --guardar h.png
python Utils/analizador_datos.py --anio 2024 --serie ghi --nodos 0 --dia 2024-02-29 --guardar s.png
python Utils/analizador_datos.py --anio 2024 --perfil ghi --mes 6 --guardar p.png
python Utils/analizador_datos.py --anio 2024 --correlaciones ghi dni temperature --guardar c.png
python Utils/analizador_datos.py --anio 2024 --clasificar-dias --mes 2 --guardar kt.png
python Utils/analizador_datos.py --anio 2024 --comparar 2023 --variable ghi --por mes --guardar cmp.png
python Utils/analizador_datos.py --anio 2024 --exportar sub.parquet --mes 2 --solo-diurno
python Utils/analizador_datos.py --anio 2024 --resamplear ghi --frecuencia D --agregacion sum --factor 0.001 --guardar insol.png
python Utils/analizador_datos.py --anio 2024 --curva-duracion ghi --solo-diurno --guardar dur.png
python Utils/analizador_datos.py --anio 2024 --outliers ghi --metodo zscore --guardar out.png
python Utils/analizador_datos.py --anio 2024 --rosa-viento --mes 2 --guardar rosa.png
python Utils/analizador_datos.py --anio 2024 --rosa-viento-12 --guardar rosa12.png
python Utils/analizador_datos.py --anio 2024 --boxplot temperature --guardar box.png
python Utils/analizador_datos.py --anio 2024 --heatmap ghi --guardar heat.png
python Utils/analizador_datos.py --anio 2024 --mapa-recurso ghi --guardar recurso.png
python Utils/analizador_datos.py --anio 2024 --mapa-delta 2023 --variable ghi --guardar delta.png
python Utils/analizador_datos.py --anio 2024 --anomalias
python Utils/analizador_datos.py --anio 2024 --reporte informe_2024.html
python Utils/analizador_datos.py --anio 2024 --reporte informe_feb.pdf --mes 2
python Utils/analizador_datos.py --parquet ruta/al/archivo.parquet --info
```

> En Windows, si la consola corta caracteres como `²`/`≠`, ejecuta con
> `PYTHONIOENCODING=utf-8`. Las gráficas se guardan igual.

---

## 6. Notebook de ejemplo

[`analizador_demo.ipynb`](../analizador_demo.ipynb) recorre, con Tamaulipas 2024,
todo lo anterior con comentarios paso a paso.
