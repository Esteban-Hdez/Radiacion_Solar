# exp04_xgb_cuantilico — v1

XGBoost cuantílico P10/P50/P90 sobre kt, feature-set base+nocturno. P50 puntual + banda de incertidumbre; métricas de intervalo.

- Nodo: 1736 | feature-set: `base-nocturno` (45 features) | best_iteration: 286
- Bloques: ['base', 'nocturno'] | modelo: xgboost_cuantilico | cuantiles: [0.1, 0.5, 0.9]

**Test global (P50 si cuantílico):** RMSE 80.28 vs persistence 84.87 W/m² · skill 0.0541 · R² 0.925

## Métricas globales (val + test)

| segmento         |    n |   RMSE_persistence |   RMSE_modelo |   MAE_modelo |   MBE_modelo |   R2_persistence |   R2_modelo |   skill | split   |
|:-----------------|-----:|-------------------:|--------------:|-------------:|-------------:|-----------------:|------------:|--------:|:--------|
| global           | 4112 |             84.625 |        79.062 |       39.728 |        8.191 |            0.921 |       0.931 |   0.066 | val     |
| limpio_ff0       | 3712 |             86.679 |        80.965 |       40.189 |        7.86  |            0.912 |       0.923 |   0.066 | val     |
| rellenado_ff_pos |  400 |             62.425 |        58.519 |       35.444 |       11.26  |            0.89  |       0.903 |   0.063 | val     |
| global           | 4123 |             84.873 |        80.281 |       43.383 |        7.976 |            0.916 |       0.925 |   0.054 | test    |
| limpio_ff0       | 3734 |             86.482 |        82.046 |       44.477 |        8.409 |            0.906 |       0.915 |   0.051 | test    |
| rellenado_ff_pos |  389 |             67.497 |        60.789 |       32.88  |        3.824 |            0.887 |       0.908 |   0.099 | test    |

## Por régimen de nubosidad (test)

| regimen_nubosidad   |    n |   RMSE_modelo |   RMSE_persistence |   MAE_modelo |   R2_modelo |   skill |
|:--------------------|-----:|--------------:|-------------------:|-------------:|------------:|--------:|
| cubierto (kt<0.3)   |  286 |       142.679 |            135.642 |       98.99  |      -3.673 |  -0.052 |
| parcial (0.3-0.7)   |  708 |       120.925 |            127.541 |       82.8   |       0.481 |   0.052 |
| despejado (kt>=0.7) | 3129 |        57.646 |             64.26  |       29.381 |       0.956 |   0.103 |

## Por régimen de rampa (test)

| regimen_rampa             |    n |   RMSE_modelo |   RMSE_persistence |   MAE_modelo |   R2_modelo |   skill |
|:--------------------------|-----:|--------------:|-------------------:|-------------:|------------:|--------:|
| rampa suave (<0.1)        | 2818 |        32.333 |             23.286 |       18.16  |       0.987 |  -0.389 |
| rampa moderada (0.1-0.25) |  817 |        93.304 |             97.163 |       73.479 |       0.864 |   0.04  |
| rampa fuerte (>0.25)      |  487 |       184.144 |            204.961 |      138.869 |       0.307 |   0.102 |

## Intervalo de predicción (test)

|    n |   pinball_medio |   cobertura_80 |   cobertura_nominal |   anchura_media |
|-----:|----------------:|---------------:|--------------------:|----------------:|
| 4123 |          14.361 |          0.504 |                 0.8 |         131.522 |

### Cobertura y anchura por régimen de nubosidad

| regimen_nubosidad   |    n |   cobertura |   anchura_media |
|:--------------------|-----:|------------:|----------------:|
| cubierto (kt<0.3)   |  286 |       0.43  |         199.441 |
| parcial (0.3-0.7)   |  708 |       0.716 |         202.464 |
| despejado (kt>=0.7) | 3129 |       0.463 |         109.262 |

## Top 15 importancias (gain)

|                            |      0 |
|:---------------------------|-------:|
| kt_last_op                 | 0.3017 |
| kt_lag1                    | 0.2984 |
| cloud_type_lag1            | 0.1173 |
| kt_lag2                    | 0.0536 |
| fill_flag_lag1             | 0.0207 |
| precipitable_water_lag1    | 0.0154 |
| cos_hour                   | 0.0129 |
| cloud_type_media_12h       | 0.0112 |
| kt_lag3                    | 0.0097 |
| temperature_lag1           | 0.0089 |
| ssa_lag1                   | 0.0085 |
| cloud_fill_flag_lag1       | 0.0083 |
| aerosol_optical_depth_lag1 | 0.0063 |
| wind_direction_lag1        | 0.006  |
| sin_hour                   | 0.006  |
