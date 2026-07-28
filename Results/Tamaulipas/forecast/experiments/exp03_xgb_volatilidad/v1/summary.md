# exp03_xgb_volatilidad — v1

XGBoost t+1 = base + volatilidad (lags largos, rampas, std/rango de kt) + nocturno (agregados y tendencias de meteo 12 h). Objetivo: mejorar los episodios nublados/variables.

- Nodo: 1736 | feature-set: `base-volatilidad-nocturno` (58 features) | best_iteration: 342
- Bloques: ['base', 'volatilidad', 'nocturno'] | modelo: xgboost | ponderar_ghi: False

**Test global:** RMSE 80.24 vs persistence 84.87 W/m² · skill 0.0545 · R² 0.925

## Métricas globales (val + test)

| segmento         |    n |   RMSE_persistence |   RMSE_modelo |   MAE_modelo |   MBE_modelo |   R2_persistence |   R2_modelo |   skill | split   |
|:-----------------|-----:|-------------------:|--------------:|-------------:|-------------:|-----------------:|------------:|--------:|:--------|
| global           | 4112 |             84.625 |        77.358 |       41.989 |        2.615 |            0.921 |       0.934 |   0.086 | val     |
| limpio_ff0       | 3712 |             86.679 |        79.093 |       42.684 |        1.731 |            0.912 |       0.927 |   0.088 | val     |
| rellenado_ff_pos |  400 |             62.425 |        58.866 |       35.536 |       10.819 |            0.89  |       0.902 |   0.057 | val     |
| global           | 4123 |             84.873 |        80.244 |       46.456 |        1.757 |            0.916 |       0.925 |   0.055 | test    |
| limpio_ff0       | 3734 |             86.482 |        81.999 |       47.745 |        1.799 |            0.906 |       0.916 |   0.052 | test    |
| rellenado_ff_pos |  389 |             67.497 |        60.882 |       34.083 |        1.354 |            0.887 |       0.908 |   0.098 | test    |

## Por régimen de nubosidad (test)

| regimen_nubosidad   |    n |   RMSE_modelo |   RMSE_persistence |   MAE_modelo |   R2_modelo |   skill |
|:--------------------|-----:|--------------:|-------------------:|-------------:|------------:|--------:|
| cubierto (kt<0.3)   |  286 |       146.602 |            135.642 |      104.898 |      -3.934 |  -0.081 |
| parcial (0.3-0.7)   |  708 |       116.372 |            127.541 |       80.272 |       0.52  |   0.088 |
| despejado (kt>=0.7) | 3129 |        58.788 |             64.26  |       33.463 |       0.954 |   0.085 |

## Por régimen de rampa (test)

| regimen_rampa             |    n |   RMSE_modelo |   RMSE_persistence |   MAE_modelo |   R2_modelo |   skill |
|:--------------------------|-----:|--------------:|-------------------:|-------------:|------------:|--------:|
| rampa suave (<0.1)        | 2818 |        40.959 |             23.286 |       25.072 |       0.979 |  -0.759 |
| rampa moderada (0.1-0.25) |  817 |        93.387 |             97.163 |       71.131 |       0.864 |   0.039 |
| rampa fuerte (>0.25)      |  487 |       173.71  |            204.961 |      128.853 |       0.383 |   0.152 |

## Top 15 importancias (gain)

|                         |      0 |
|:------------------------|-------:|
| kt_lag1                 | 0.3963 |
| kt_last_op              | 0.1031 |
| cloud_type_lag1         | 0.0484 |
| cos_hour                | 0.0322 |
| pressure_tend_12h       | 0.0114 |
| temperature_lag1        | 0.0107 |
| hour                    | 0.0106 |
| wind_direction_lag1     | 0.0106 |
| temperature_max_12h     | 0.0106 |
| clearsky_dni            | 0.0104 |
| clearsky_dhi            | 0.0103 |
| sin_hour                | 0.01   |
| kt_mean_3               | 0.0095 |
| relative_humidity_lag1  | 0.0094 |
| precipitable_water_lag1 | 0.0093 |
