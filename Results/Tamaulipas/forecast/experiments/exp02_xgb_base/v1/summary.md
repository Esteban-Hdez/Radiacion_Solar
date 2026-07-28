# exp02_xgb_base — v1

XGBoost t+1 con feature-set base (lags kt 1/2/3/24 + kt_last_op + deterministas known-future + estáticas + observadas lag1). Reproduce la Fase 3; referencia para el resto de experimentos.

- Nodo: 1736 | feature-set: `base` (35 features) | best_iteration: 189
- Bloques: ['base'] | modelo: xgboost | ponderar_ghi: False

**Test global:** RMSE 79.82 vs persistence 84.87 W/m² · skill 0.0596 · R² 0.926

## Métricas globales (val + test)

| segmento         |    n |   RMSE_persistence |   RMSE_modelo |   MAE_modelo |   MBE_modelo |   R2_persistence |   R2_modelo |   skill | split   |
|:-----------------|-----:|-------------------:|--------------:|-------------:|-------------:|-----------------:|------------:|--------:|:--------|
| global           | 4112 |             84.625 |        77.394 |       42.051 |        3.061 |            0.921 |       0.934 |   0.085 | val     |
| limpio_ff0       | 3712 |             86.679 |        79.166 |       42.725 |        2.213 |            0.912 |       0.927 |   0.087 | val     |
| rellenado_ff_pos |  400 |             62.425 |        58.44  |       35.789 |       10.932 |            0.89  |       0.904 |   0.064 | val     |
| global           | 4123 |             84.873 |        79.818 |       46.642 |        1.002 |            0.916 |       0.926 |   0.06  | test    |
| limpio_ff0       | 3734 |             86.482 |        81.507 |       47.95  |        1.094 |            0.906 |       0.917 |   0.058 | test    |
| rellenado_ff_pos |  389 |             67.497 |        61.281 |       34.086 |        0.117 |            0.887 |       0.906 |   0.092 | test    |

## Por régimen de nubosidad (test)

| regimen_nubosidad   |    n |   RMSE_modelo |   RMSE_persistence |   MAE_modelo |   R2_modelo |   skill |
|:--------------------|-----:|--------------:|-------------------:|-------------:|------------:|--------:|
| cubierto (kt<0.3)   |  286 |       144.013 |            135.642 |      104.247 |      -3.761 |  -0.062 |
| parcial (0.3-0.7)   |  708 |       115.353 |            127.541 |       79.734 |       0.528 |   0.096 |
| despejado (kt>=0.7) | 3129 |        59.061 |             64.26  |       33.889 |       0.954 |   0.081 |

## Por régimen de rampa (test)

| regimen_rampa             |    n |   RMSE_modelo |   RMSE_persistence |   MAE_modelo |   R2_modelo |   skill |
|:--------------------------|-----:|--------------:|-------------------:|-------------:|------------:|--------:|
| rampa suave (<0.1)        | 2818 |        39.311 |             23.286 |       24.84  |       0.981 |  -0.688 |
| rampa moderada (0.1-0.25) |  817 |        94.104 |             97.163 |       72.176 |       0.862 |   0.031 |
| rampa fuerte (>0.25)      |  487 |       173.599 |            204.961 |      130.002 |       0.384 |   0.153 |

## Top 15 importancias (gain)

|                         |      0 |
|:------------------------|-------:|
| kt_lag1                 | 0.4062 |
| kt_last_op              | 0.1513 |
| cloud_type_lag1         | 0.0972 |
| cos_hour                | 0.0231 |
| kt_lag2                 | 0.0157 |
| hour                    | 0.0154 |
| temperature_lag1        | 0.0153 |
| solar_zenith_angle      | 0.0137 |
| relative_humidity_lag1  | 0.0134 |
| clearsky_dni            | 0.0132 |
| wind_direction_lag1     | 0.0128 |
| sin_hour                | 0.0126 |
| precipitable_water_lag1 | 0.0126 |
| clearsky_ghi            | 0.0123 |
| ozone_lag1              | 0.0119 |
