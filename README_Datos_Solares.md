# Documentación del Dataset: Red de Radiación Solar y Meteorología (Puerto Rico, 2017)

> **⚠️ Actualización (2026-06): corrección de la malla de Puerto Rico.**
> La malla de **2,480 nodos** descrita en este documento se generó con paso **0.02°**,
> el doble de fino que la rejilla real de NSRDB v4 (**0.04°**). Al deduplicar por
> `location_id` (celda real del satélite), los 2,480 nodos colapsan en **754 celdas
> físicas únicas** (1,726 eran copias). La malla corregida a 754 nodos es ahora la
> oficial (`Data/Puerto_Rico/metadata_nodos_pr.csv`); la original quedó en
> `Data/Puerto_Rico/historico_2480_0.02/`. Detalle completo en
> **[`Data/Puerto_Rico/README.md`](Data/Puerto_Rico/README.md)**. Lo descrito abajo
> corresponde al armado histórico 2017 (antes de la corrección).

## 1. Origen de los Datos
Este conjunto de datos fue extraído a través de la API oficial para desarrolladores del **Laboratorio Nacional de las Montañas Rocosas (NLR)**, anteriormente conocido como NREL. Pertenece a la Base de Datos Nacional de Radiación Solar (NSRDB).

* **Fuente Oficial:** NSRDB (National Solar Radiation Database)
* **Modelo de Extracción:** PSM v4.0.0 (Physical Solar Model - GOES Aggregated)
* **Motor Meteorológico Asimilado:** ERA5 (ECMWF) para variables termodinámicas de alta resolución.
* **Documentación Oficial de la API:** [NLR Developer Network - PSM v4](https://developer.nlr.gov/)

## 2. Cobertura Espaciotemporal
* **Región:** Puerto Rico (Malla satelital de 2,480 nodos distribuidos geográficamente).
* **Rango Temporal Histórico:** 1 de Enero de 2017 al 31 de Diciembre de 2017.
* **Resolución Temporal Original:** Horaria (Agregación matemática procesada por los servidores del laboratorio a partir de observaciones de 5 minutos).

---

## 3. Diccionario de Datos (Características Físicas y Meteorológicas)

A continuación, se describen las variables originales descargadas en bruto desde el modelo PSM v4 antes del proceso de curación.

| Atributo (Columna) | Nombre Técnico | Descripción Física | Unidad |
| :--- | :--- | :--- | :--- |
| **nodo_id** | Identificador de Nodo | Llave primaria espacial. Asignación numérica del 0 al 2479 para cada punto geográfico (cuadrícula de 4x4 km). | Adimensional |
| **year** | Año | Año de la observación. | AAAA |
| **month** | Mes | Mes de la observación (1 - 12). | Entero |
| **day** | Día | Día de la observación (1 - 31). | Entero |
| **hour** | Hora | Hora de la observación en la zona horaria local/UTC configurada (0 - 23). | Entero |
| **ghi** | Global Horizontal Irradiance | Radiación solar total recibida en una superficie horizontal. Es la suma de la radiación directa y difusa. | W/m² |
| **dni** | Direct Normal Irradiance | Radiación solar recibida directamente del disco solar en una superficie perpendicular a los rayos. | W/m² |
| **dhi** | Diffuse Horizontal Irradiance | Radiación solar recibida en una superficie horizontal dispersada por la atmósfera (nubes, partículas). | W/m² |
| **clearsky_ghi** | Clearsky GHI | Estimación teórica de la irradiancia global horizontal si no existieran nubes (cielo azul). | W/m² |
| **temperature** | Temperatura del Aire | Temperatura ambiente extraída del modelo ERA5, medida a 2 metros sobre la superficie. | °C |
| **pressure** | Presión Superficial | Presión atmosférica al nivel de la superficie del nodo. | hPa / mbar |
| **wind_speed** | Velocidad del Viento | Velocidad del viento calculada a 2 metros de altura. | m/s |
| **precipitable_water**| Agua Precipitable Total | Cantidad total de vapor de agua contenida en la columna atmosférica. | cm |
| **cloud_type** | Tipo de Nube | Clasificación categórica de la cobertura nubosa predominante (ej. 0=Despejado, 1=Probablemente Despejado, 3=Nube de Agua, etc.). | Adimensional |
| **solar_zenith_angle**| Ángulo Cenital Solar | Ángulo entre el sol y la vertical local en el punto medio de la hora (minuto 30). 0° = Sol en el cenit. | Grados (°) |
| **relative_humidity** | Humedad Relativa | Porcentaje de saturación de vapor de agua en el aire a la temperatura actual. | % |

---

## 4. Curación del Dataset Final (Dataset Maestro Diurno)

El archivo consolidado en bruto (aprox. 21.7 millones de registros) fue sometido a un pipeline de curación física e ingeniería de características para generar la matriz de entrada final para los modelos de Machine Learning (GNN / LSTM).

### Transformaciones Aplicadas:
1. **Generación de Índice Temporal Unificado:** Se combinaron las columnas `year`, `month`, `day`, `hour` para crear una nueva columna `datetime` (tipo `datetime64[ns]`), estandarizando el formato para modelos de series temporales.
2. **Renombrado de Variables:** La columna original `relative_humidity` fue renombrada a `RH_Promedio_Horario` para clarificar la naturaleza de su agregación estadística (promedio matemático de la ventana de 60 minutos).
3. **Selección Estricta:** Se eliminaron las variables secundarias (albedo superficial, asimetría de aerosoles, profundidad óptica, etc.) conservando exclusivamente las listadas en el diccionario superior.

### Filtros Físicos (Máscara Diurna):
Para evitar introducir ruido matemático en las redes neuronales por lecturas nocturnas sin aporte energético, se aplicó un filtro bidimensional. Un registro fue retenido en el dataset final únicamente si cumplió **ambas** condiciones:
* `clearsky_ghi > 0`: Indica que el motor físico espera radiación en el sitio geográfico.
* `solar_zenith_angle < 85`: Se eliminan las horas de amanecer y atardecer extremo donde los cálculos de refracción atmosférica pierden fiabilidad lineal.

### Dimensiones Finales:
* **Estructura:** Matriz espaciotemporal indexada por `nodo_id` y `datetime`.
* **Retención de Datos:** El proceso de filtrado diurno redujo el conjunto de datos descartando las horas nocturnas, dejando un tamaño final curado de aproximadamente el 50% de los registros originales, listos para modelado predictivo.

---

## 5. Ejemplo de Carga e Inspección de Datos

Script en Python utilizado para validar la estructura del dataset final, extrayendo las primeras 24 horas diurnas del Nodo 0:

```python
import pandas as pd

# Ruta al dataset definitivo con filtros astronómicos aplicados
ruta_dataset = 'dataset_v4_filtrado_diurno_2017.parquet'

# Cargar el dataframe optimizado en formato Parquet
df = pd.read_parquet(ruta_dataset, engine='pyarrow')

# Filtrar las primeras 24 filas diurnas correspondientes al Nodo 0
df_ejemplo = df[df['nodo_id'] == 0].head(24)

print("=" * 100)
print("MUESTRA DE DATOS CURADOS: PRIMERAS FILAS DIURNAS (NODO 0)")
print("=" * 100)

# Configurar Pandas para mostrar el espectro completo de variables
pd.set_option('display.max_columns', None)
pd.set_option('display.width', 1000)

# Imprimir la matriz omitiendo el índice secuencial
print(df_ejemplo.to_string(index=False))
print("=" * 100)