# Referencia NSRDB PSM v4 — metadatos constantes y diccionarios

Campos de la cabecera del CSV de NSRDB (GOES aggregated v4) que son **constantes
entre nodos y entre años**. Aplican a los datasets de Tamaulipas y Puerto Rico.
Los únicos campos que **varían por nodo** son `location_id`, `latitude`,
`longitude` y `elevation` (por eso `descargar_anio --metadatos cambian` guarda solo
esos; `--metadatos todos` guarda los 47 campos completos).

Versión del dataset: **`version = 4.0.1`** · Fuente: **`source = NSRDB`**.

---

## Unidades por variable

| Columna del dataset | Unidad | Descripción |
|---|---|---|
| `ghi`, `dni`, `dhi` | W/m² | irradiancia global / directa / difusa horizontal |
| `clearsky_ghi`, `clearsky_dni`, `clearsky_dhi` | W/m² | irradiancia de cielo despejado |
| `ghi_uv_280_400`, `ghi_uv_295_385` | W/m² | irradiancia UV horizontal (bandas en nm) |
| `temperature`, `dew_point` | °C | temperatura del aire / punto de rocío |
| `pressure` | mbar | presión en superficie |
| `relative_humidity` | % | humedad relativa |
| `precipitable_water` | cm | agua precipitable |
| `wind_speed` | m/s | velocidad del viento |
| `wind_direction` | grados | dirección del viento (0–360) |
| `solar_zenith_angle` | grados | ángulo cenital solar |
| `surface_albedo` | — | albedo de superficie (adimensional, 0–1) |
| `aerosol_optical_depth`, `alpha`, `asymmetry`, `ssa` | — | propiedades ópticas de aerosol (adimensionales)* |
| `ozone` | atm-cm | columna de ozono* |

\* La cabecera de NSRDB no trae campo de unidad para estas; se documenta según la
convención de NSRDB.

---

## Diccionario `cloud_type`

| Código | Significado |
|---|---|
| 0 | Clear (despejado) |
| 1 | Probably Clear |
| 2 | Fog (niebla) |
| 3 | Water (nube de agua) |
| 4 | Super-Cooled Water |
| 5 | Mixed (mixta) |
| 6 | Opaque Ice (hielo opaco) |
| 7 | Cirrus |
| 8 | Overlapping (superpuestas) |
| 9 | Overshooting |
| 10 | Unknown (desconocido) |
| 11 | Dust (polvo) |
| 12 | Smoke (humo) |
| −15 | (sin dato / relleno) |

## Diccionario `fill_flag`

| Código | Significado |
|---|---|
| 0 | (sin relleno) |
| 1 | Missing Image |
| 2 | Low Irradiance |
| 3 | Exceeds Clearsky |
| 4 | Missing Cloud Properties |
| 5 | Rayleigh Violation |

> `cloud_fill_flag` es otra columna del dataset (bandera de relleno de nubosidad);
> la cabecera no incluye su diccionario.

---

## Husos horarios

| Campo | Valor | Nota |
|---|---|---|
| `time_zone` | 0 | los datos se descargan en **UTC** (`utc=true`) |
| `local_time_zone` | −6 | hora central de México (para convertir a local) |

`city`, `state`, `country` vienen vacíos (`-`) en esta región.

---

## Uso: decodificar las categóricas en pandas

```python
CLOUD_TYPE = {0:'Clear',1:'Probably Clear',2:'Fog',3:'Water',4:'Super-Cooled Water',
              5:'Mixed',6:'Opaque Ice',7:'Cirrus',8:'Overlapping',9:'Overshooting',
              10:'Unknown',11:'Dust',12:'Smoke'}
FILL_FLAG  = {0:'',1:'Missing Image',2:'Low Irradiance',3:'Exceeds Clearsky',
              4:'Missing Cloud Properties',5:'Rayleigh Violation'}

df['cloud_type_desc'] = df['cloud_type'].map(CLOUD_TYPE)
df['fill_flag_desc']  = df['fill_flag'].map(FILL_FLAG)
```

> Para regenerar/verificar estos diccionarios desde la API:
> `python -m Utils.tamaulipas_anual.descargar_anio --anio <AÑO> --metadatos todos --limite 1`
> y revisar `Data/Tamaulipas/<AÑO>/metadata_nodos_<AÑO>.csv`.
