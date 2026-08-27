# exp03_xgb_volatilidad — v2

base + nocturno (config retenida: volatilidad sobreajustaba; nocturno aporta skill marginal y mejora rampas fuertes).

- Alcance: nodo 1736 | feature-set: `base-nocturno` (44 features) | best_iteration: 253
- Bloques: ['base', 'nocturno'] | modelo: xgboost | cuantiles: —

**Test global (P50 si cuantílico):** RMSE 80.28 vs persistence 84.87 W/m² · skill 0.0541 · R² 0.925

## Métricas globales (val + test)

| segmento         |    n |   RMSE_persistence |   RMSE_modelo |   MAE_modelo |   MBE_modelo |   R2_persistence |   R2_modelo |   skill | split   |
|:-----------------|-----:|-------------------:|--------------:|-------------:|-------------:|-----------------:|------------:|--------:|:--------|
| global           | 4112 |             84.625 |        77.38  |       42.308 |        2.95  |            0.921 |       0.934 |   0.086 | val     |
| limpio_ff0       | 3712 |             86.679 |        79.163 |       42.991 |        2.217 |            0.912 |       0.927 |   0.087 | val     |
| rellenado_ff_pos |  400 |             62.425 |        58.288 |       35.975 |        9.751 |            0.89  |       0.904 |   0.066 | val     |
| global           | 4123 |             84.873 |        80.278 |       46.99  |        1.685 |            0.916 |       0.925 |   0.054 | test    |
| limpio_ff0       | 3734 |             86.482 |        82.037 |       48.313 |        1.724 |            0.906 |       0.915 |   0.051 | test    |
| rellenado_ff_pos |  389 |             67.497 |        60.866 |       34.284 |        1.316 |            0.887 |       0.908 |   0.098 | test    |

## Por régimen de nubosidad (test)

| regimen_nubosidad   |    n |   RMSE_modelo |   RMSE_persistence |   MAE_modelo |   R2_modelo |   skill |
|:--------------------|-----:|--------------:|-------------------:|-------------:|------------:|--------:|
| cubierto (kt<0.3)   |  286 |       145.959 |            135.642 |      106.538 |      -3.891 |  -0.076 |
| parcial (0.3-0.7)   |  708 |       117.188 |            127.541 |       80.705 |       0.513 |   0.081 |
| despejado (kt>=0.7) | 3129 |        58.628 |             64.26  |       33.918 |       0.954 |   0.088 |

## Por régimen de rampa (test)

| regimen_rampa             |    n |   RMSE_modelo |   RMSE_persistence |   MAE_modelo |   R2_modelo |   skill |
|:--------------------------|-----:|--------------:|-------------------:|-------------:|------------:|--------:|
| rampa suave (<0.1)        | 2818 |        40.795 |             23.286 |       25.56  |       0.979 |  -0.752 |
| rampa moderada (0.1-0.25) |  817 |        94.168 |             97.163 |       71.774 |       0.862 |   0.031 |
| rampa fuerte (>0.25)      |  487 |       173.358 |            204.961 |      129.452 |       0.385 |   0.154 |

## Top 15 importancias (gain)

|                        |      0 |
|:-----------------------|-------:|
| kt_lag1                | 0.3729 |
| kt_last_op             | 0.1398 |
| cloud_type_lag1        | 0.0556 |
| cos_hour               | 0.0244 |
| hour                   | 0.0164 |
| temperature_max_12h    | 0.0151 |
| wind_direction_lag1    | 0.0132 |
| temperature_tend_12h   | 0.0131 |
| relative_humidity_lag1 | 0.0129 |
| temperature_lag1       | 0.0129 |
| clearsky_dni           | 0.0127 |
| asymmetry_lag1         | 0.0126 |
| clearsky_dhi           | 0.0125 |
| pressure_tend_12h      | 0.0121 |
| ssa_lag1               | 0.0118 |
