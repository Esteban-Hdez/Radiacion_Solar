# exp03_xgb_volatilidad — v2

base + nocturno (config retenida: volatilidad sobreajustaba; nocturno aporta skill marginal y mejora rampas fuertes).

- Nodo: 1736 | feature-set: `base-nocturno` (45 features) | best_iteration: 232
- Bloques: ['base', 'nocturno'] | modelo: xgboost | ponderar_ghi: False

**Test global:** RMSE 79.70 vs persistence 84.87 W/m² · skill 0.0610 · R² 0.926

## Métricas globales (val + test)

| segmento         |    n |   RMSE_persistence |   RMSE_modelo |   MAE_modelo |   MBE_modelo |   R2_persistence |   R2_modelo |   skill | split   |
|:-----------------|-----:|-------------------:|--------------:|-------------:|-------------:|-----------------:|------------:|--------:|:--------|
| global           | 4112 |             84.625 |        77.533 |       42.362 |        2.693 |            0.921 |       0.934 |   0.084 | val     |
| limpio_ff0       | 3712 |             86.679 |        79.334 |       43.038 |        1.862 |            0.912 |       0.926 |   0.085 | val     |
| rellenado_ff_pos |  400 |             62.425 |        58.213 |       36.085 |       10.4   |            0.89  |       0.904 |   0.067 | val     |
| global           | 4123 |             84.873 |        79.698 |       46.485 |        1.933 |            0.916 |       0.926 |   0.061 | test    |
| limpio_ff0       | 3734 |             86.482 |        81.399 |       47.777 |        2.055 |            0.906 |       0.917 |   0.059 | test    |
| rellenado_ff_pos |  389 |             67.497 |        61.001 |       34.081 |        0.765 |            0.887 |       0.907 |   0.096 | test    |

## Por régimen de nubosidad (test)

| regimen_nubosidad   |    n |   RMSE_modelo |   RMSE_persistence |   MAE_modelo |   R2_modelo |   skill |
|:--------------------|-----:|--------------:|-------------------:|-------------:|------------:|--------:|
| cubierto (kt<0.3)   |  286 |       144.497 |            135.642 |      104.995 |      -3.793 |  -0.065 |
| parcial (0.3-0.7)   |  708 |       115.912 |            127.541 |       80.39  |       0.524 |   0.091 |
| despejado (kt>=0.7) | 3129 |        58.489 |             64.26  |       33.465 |       0.954 |   0.09  |

## Por régimen de rampa (test)

| regimen_rampa             |    n |   RMSE_modelo |   RMSE_persistence |   MAE_modelo |   R2_modelo |   skill |
|:--------------------------|-----:|--------------:|-------------------:|-------------:|------------:|--------:|
| rampa suave (<0.1)        | 2818 |        40.524 |             23.286 |       25.118 |       0.98  |  -0.74  |
| rampa moderada (0.1-0.25) |  817 |        92.521 |             97.163 |       70.877 |       0.867 |   0.048 |
| rampa fuerte (>0.25)      |  487 |       172.946 |            204.961 |      129.246 |       0.388 |   0.156 |

## Top 15 importancias (gain)

|                           |      0 |
|:--------------------------|-------:|
| kt_lag1                   | 0.4611 |
| kt_last_op                | 0.0662 |
| cloud_type_lag1           | 0.0381 |
| cos_hour                  | 0.0242 |
| hour                      | 0.0145 |
| temperature_max_12h       | 0.0143 |
| temperature_lag1          | 0.0143 |
| clearsky_dni              | 0.0134 |
| relative_humidity_min_12h | 0.0132 |
| asymmetry_lag1            | 0.0129 |
| wind_direction_lag1       | 0.0127 |
| pressure_tend_12h         | 0.0123 |
| relative_humidity_lag1    | 0.0119 |
| sin_hour                  | 0.0119 |
| precipitable_water_lag1   | 0.0118 |
