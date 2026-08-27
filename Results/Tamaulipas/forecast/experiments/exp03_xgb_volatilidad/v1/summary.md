# exp03_xgb_volatilidad — v1

base + volatilidad + nocturno (intento completo del experimento 1).

- Alcance: nodo 1736 | feature-set: `base-volatilidad-nocturno` (57 features) | best_iteration: 283
- Bloques: ['base', 'volatilidad', 'nocturno'] | modelo: xgboost | cuantiles: —

**Test global (P50 si cuantílico):** RMSE 80.24 vs persistence 84.87 W/m² · skill 0.0546 · R² 0.925

## Métricas globales (val + test)

| segmento         |    n |   RMSE_persistence |   RMSE_modelo |   MAE_modelo |   MBE_modelo |   R2_persistence |   R2_modelo |   skill | split   |
|:-----------------|-----:|-------------------:|--------------:|-------------:|-------------:|-----------------:|------------:|--------:|:--------|
| global           | 4112 |             84.625 |        77.722 |       42.385 |        3.042 |            0.921 |       0.934 |   0.082 | val     |
| limpio_ff0       | 3712 |             86.679 |        79.411 |       43.074 |        2.206 |            0.912 |       0.926 |   0.084 | val     |
| rellenado_ff_pos |  400 |             62.425 |        59.819 |       36     |       10.804 |            0.89  |       0.899 |   0.042 | val     |
| global           | 4123 |             84.873 |        80.235 |       46.62  |        1.127 |            0.916 |       0.925 |   0.055 | test    |
| limpio_ff0       | 3734 |             86.482 |        82.004 |       47.907 |        1.127 |            0.906 |       0.916 |   0.052 | test    |
| rellenado_ff_pos |  389 |             67.497 |        60.69  |       34.268 |        1.122 |            0.887 |       0.908 |   0.101 | test    |

## Por régimen de nubosidad (test)

| regimen_nubosidad   |    n |   RMSE_modelo |   RMSE_persistence |   MAE_modelo |   R2_modelo |   skill |
|:--------------------|-----:|--------------:|-------------------:|-------------:|------------:|--------:|
| cubierto (kt<0.3)   |  286 |       144.159 |            135.642 |      104.013 |      -3.771 |  -0.063 |
| parcial (0.3-0.7)   |  708 |       116.08  |            127.541 |       80.417 |       0.522 |   0.09  |
| despejado (kt>=0.7) | 3129 |        59.451 |             64.26  |       33.727 |       0.953 |   0.075 |

## Por régimen de rampa (test)

| regimen_rampa             |    n |   RMSE_modelo |   RMSE_persistence |   MAE_modelo |   R2_modelo |   skill |
|:--------------------------|-----:|--------------:|-------------------:|-------------:|------------:|--------:|
| rampa suave (<0.1)        | 2818 |        40.563 |             23.286 |       25.004 |       0.98  |  -0.742 |
| rampa moderada (0.1-0.25) |  817 |        93.997 |             97.163 |       71.693 |       0.862 |   0.033 |
| rampa fuerte (>0.25)      |  487 |       173.659 |            204.961 |      129.676 |       0.383 |   0.153 |

## Top 15 importancias (gain)

|                        |      0 |
|:-----------------------|-------:|
| kt_lag1                | 0.3735 |
| kt_last_op             | 0.1376 |
| cloud_type_lag1        | 0.0464 |
| cos_hour               | 0.0253 |
| hour                   | 0.0151 |
| temperature_max_12h    | 0.0107 |
| kt_mean_3              | 0.0104 |
| wind_direction_lag1    | 0.01   |
| cloud_fill_flag_lag1   | 0.01   |
| temperature_lag1       | 0.0098 |
| clearsky_dni           | 0.0097 |
| relative_humidity_lag1 | 0.0097 |
| clearsky_dhi           | 0.0097 |
| pressure_tend_12h      | 0.0096 |
| ssa_lag1               | 0.0096 |
