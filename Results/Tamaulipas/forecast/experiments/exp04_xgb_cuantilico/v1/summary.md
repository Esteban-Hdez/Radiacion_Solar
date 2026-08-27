# exp04_xgb_cuantilico — v1

XGBoost cuantílico P10/P50/P90 sobre kt, feature-set base+nocturno. P50 puntual + banda de incertidumbre; métricas de intervalo.

- Alcance: nodo 1736 | feature-set: `base-nocturno` (44 features) | best_iteration: 306
- Bloques: ['base', 'nocturno'] | modelo: xgboost_cuantilico | cuantiles: [0.1, 0.5, 0.9]

**Test global (P50 si cuantílico):** RMSE 80.11 vs persistence 84.87 W/m² · skill 0.0561 · R² 0.925

## Métricas globales (val + test)

| segmento         |    n |   RMSE_persistence |   RMSE_modelo |   MAE_modelo |   MBE_modelo |   R2_persistence |   R2_modelo |   skill | split   |
|:-----------------|-----:|-------------------:|--------------:|-------------:|-------------:|-----------------:|------------:|--------:|:--------|
| global           | 4112 |             84.625 |        79.368 |       39.908 |        8.248 |            0.921 |       0.931 |   0.062 | val     |
| limpio_ff0       | 3712 |             86.679 |        81.313 |       40.36  |        7.896 |            0.912 |       0.923 |   0.062 | val     |
| rellenado_ff_pos |  400 |             62.425 |        58.306 |       35.711 |       11.507 |            0.89  |       0.904 |   0.066 | val     |
| global           | 4123 |             84.873 |        80.11  |       43.14  |        8.193 |            0.916 |       0.925 |   0.056 | test    |
| limpio_ff0       | 3734 |             86.482 |        81.87  |       44.233 |        8.617 |            0.906 |       0.916 |   0.053 | test    |
| rellenado_ff_pos |  389 |             67.497 |        60.671 |       32.647 |        4.126 |            0.887 |       0.908 |   0.101 | test    |

## Por régimen de nubosidad (test)

| regimen_nubosidad   |    n |   RMSE_modelo |   RMSE_persistence |   MAE_modelo |   R2_modelo |   skill |
|:--------------------|-----:|--------------:|-------------------:|-------------:|------------:|--------:|
| cubierto (kt<0.3)   |  286 |       141.994 |            135.642 |       98.416 |      -3.629 |  -0.047 |
| parcial (0.3-0.7)   |  708 |       121.095 |            127.541 |       82.806 |       0.48  |   0.051 |
| despejado (kt>=0.7) | 3129 |        57.405 |             64.26  |       29.113 |       0.956 |   0.107 |

## Por régimen de rampa (test)

| regimen_rampa             |    n |   RMSE_modelo |   RMSE_persistence |   MAE_modelo |   R2_modelo |   skill |
|:--------------------------|-----:|--------------:|-------------------:|-------------:|------------:|--------:|
| rampa suave (<0.1)        | 2818 |        32.396 |             23.286 |       18     |       0.987 |  -0.391 |
| rampa moderada (0.1-0.25) |  817 |        93.265 |             97.163 |       73.078 |       0.864 |   0.04  |
| rampa fuerte (>0.25)      |  487 |       183.48  |            204.961 |      138.421 |       0.312 |   0.105 |

## Intervalo de predicción (test)

|    n |   pinball_medio |   cobertura_80 |   cobertura_nominal |   anchura_media |
|-----:|----------------:|---------------:|--------------------:|----------------:|
| 4123 |          14.387 |          0.525 |                 0.8 |         133.096 |

### Cobertura y anchura por régimen de nubosidad

| regimen_nubosidad   |    n |   cobertura |   anchura_media |
|:--------------------|-----:|------------:|----------------:|
| cubierto (kt<0.3)   |  286 |       0.423 |         201.368 |
| parcial (0.3-0.7)   |  708 |       0.737 |         203.151 |
| despejado (kt>=0.7) | 3129 |       0.486 |         111.005 |

## Top 15 importancias (gain)

|                              |      0 |
|:-----------------------------|-------:|
| kt_lag1                      | 0.3096 |
| kt_last_op                   | 0.2792 |
| cloud_type_lag1              | 0.1019 |
| kt_lag2                      | 0.0613 |
| fill_flag_lag1               | 0.0284 |
| precipitable_water_lag1      | 0.0201 |
| kt_lag3                      | 0.0153 |
| cos_hour                     | 0.0134 |
| cloud_fill_flag_lag1         | 0.0112 |
| ssa_lag1                     | 0.0106 |
| temperature_lag1             | 0.0089 |
| clearsky_dni                 | 0.0079 |
| precipitable_water_media_12h | 0.0075 |
| kt_lag24                     | 0.0071 |
| wind_direction_lag1          | 0.0066 |
