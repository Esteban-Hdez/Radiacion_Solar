# Guía de comandos — Proyecto Radiación Solar (NSRDB v4)

Referencia práctica de **cómo usar cada script**, en orden de uso, con sus
configuraciones y para qué sirve. Todos los scripts se ejecutan **como módulo desde
la raíz del proyecto** y usan rutas relativas a ella.

Documentación relacionada:
- Tamaulipas: [`Data/Tamaulipas/README.md`](Data/Tamaulipas/README.md)
- Puerto Rico (corrección de malla): [`Data/Puerto_Rico/README.md`](Data/Puerto_Rico/README.md)
- Pipeline anual: [`Utils/descarga_regiones/README.md`](Utils/descarga_regiones/README.md)
- Campos constantes NSRDB: [`Data/Tamaulipas/REFERENCIA_NSRDB.md`](Data/Tamaulipas/REFERENCIA_NSRDB.md)

---

## 0. Preparación (una vez)

```bash
conda activate rs                      # entorno con pandas/pyarrow/geopandas/contextily
# El archivo .env (raíz) debe tener:
#   API_KEY=...            (clave de la API NSRDB v4)
#   EMAIL_USUARIO=...      (email registrado)
```

> **Día bisiesto:** desde 2026-06 toda descarga **incluye el 29-feb por defecto**
> (años bisiestos = 8784 h; normales = 8760 h). Añadir `--excluir-bisiesto` para
> forzar años homogéneos de 8760 h. Debe usarse el **mismo** criterio en
> descarga, parche, recuperación y consolidación de un año.

---

## 1. `Utils/descarga_regiones/descargar_regiones.py` — ORQUESTADOR (engloba a varios)

Punto de entrada recomendado. Por cada **(región, año)** corre en orden:
**descarga → parche (×2) → consolidación**. Reanudable; si la API agota la cuota
diaria (429) se detiene de forma segura y se reanuda con el mismo comando.
Internamente usa `descargar_anio`, `parche_anio` y `consolidar_anio`.

```bash
# Caso típico: 2024 para ambas regiones, guardando toda la metadata, con 29-feb.
python -m Utils.descarga_regiones --regiones tamaulipas puerto_rico --anios 2024 --metadatos todos

# Solo una región, varios años:
python -m Utils.descarga_regiones --regiones puerto_rico --anios 2024 2025

# Años homogéneos de 8760 h (sin 29-feb):
python -m Utils.descarga_regiones --regiones tamaulipas --anios 2024 --excluir-bisiesto
```

### Ejecución desatendida por SSH (Ubuntu — máquina principal)

La descarga dura horas, así que en el servidor **siempre** hay que lanzarla de forma
que **sobreviva al cierre de la sesión SSH**. Hay dos formas; **`tmux` es la
recomendada** porque además permite volver a ver la consola en vivo.

**Opción A — `tmux` (recomendada).** El proceso vive en una sesión que sigue
corriendo aunque se caiga el SSH:

```bash
conda activate rs
tmux new -s descarga                       # abre la sesión "descarga"
# (ya dentro de tmux):
PYTHONUNBUFFERED=1 python -m Utils.descarga_regiones \
  --regiones tamaulipas puerto_rico --anios 2024 --metadatos todos \
  | tee Data/registro_descarga.log
# Desconectar dejándolo corriendo:  Ctrl-b  luego  d
```
```bash
# En cualquier momento (incluso tras reconectar el SSH) volver a la consola:
tmux attach -t descarga
tmux ls                                     # listar sesiones activas
```

**Opción B — `nohup` (sin tmux).** Queda en segundo plano y se sigue por el log:

```bash
conda activate rs
PYTHONUNBUFFERED=1 nohup python -m Utils.descarga_regiones \
  --regiones tamaulipas puerto_rico --anios 2024 --metadatos todos \
  > Data/registro_descarga.log 2>&1 &
disown                                       # lo desliga de la terminal/SSH
tail -f Data/registro_descarga.log           # seguir el progreso (Ctrl-C solo corta el tail)
```
```bash
# Verificar que sigue vivo / detenerlo:
pgrep -af "descarga_regiones"
kill <PID>                                   # parada segura: es reanudable con el mismo comando
```

> Reanudable: si la conexión a la API se corta o se agota la cuota diaria (429), se
> relanza el **mismo** comando y continúa desde donde quedó.

### Windows (ocasional)

Gracias a la corrección de codificación en `__main__.py`, ya **no** hace falta forzar
UTF-8; basta redirigir a un log. En Windows no hay SSH, así que solo se busca dejarlo
en segundo plano.

```bat
:: cmd.exe — en primer plano con log
set PYTHONUNBUFFERED=1 && python -m Utils.descarga_regiones --regiones tamaulipas puerto_rico --anios 2023 --metadatos todos > Data\registro_descarga.log 2>&1
```
```powershell
# PowerShell — en segundo plano (sobrevive a cerrar esta consola, no al cierre de sesión de Windows)
$env:PYTHONUNBUFFERED = "1"
Start-Process -NoNewWindow python `
  -ArgumentList "-m","Utils.descarga_regiones","--regiones","tamaulipas","puerto_rico","--anios","2024","--metadatos","todos" `
  -RedirectStandardOutput "Data\registro_descarga.log" `
  -RedirectStandardError  "Data\registro_descarga.err"
Get-Content Data\registro_descarga.log -Wait      # equivalente a tail -f
```

| Opción | Valores | Para qué |
|---|---|---|
| `--regiones` | `tamaulipas` `puerto_rico` (1+) | regiones a procesar |
| `--anios` | enteros (1+) **obligatorio** | años a descargar |
| `--metadatos` | `todos` \| `cambian` | guarda metadata por año (ver §4). Sin la opción no guarda |
| `--pausa` | float (def. 1.0) | segundos entre peticiones |
| `--excluir-bisiesto` | flag | excluye el 29-feb (8760 h) |

Nodos por región: **Tamaulipas 4384**, **Puerto Rico 754**.

---

## 2. Scripts por año (componentes del orquestador)

Útiles para ejecutar una etapa suelta o depurar. Por defecto operan sobre
Tamaulipas; con `--metadata`/`--raiz` sirven para otras regiones (lo hace el
orquestador automáticamente).

### 2.1 `descargar_anio.py` — descarga del año

```bash
python -m Utils.descarga_regiones.descargar_anio --anio 2024
python -m Utils.descarga_regiones.descargar_anio --anio 2024 --metadatos todos
python -m Utils.descarga_regiones.descargar_anio --anio 2024 --limite 50   # prueba: primeros 50
```
| Opción | Para qué |
|---|---|
| `--anio` (obligatorio) | año a descargar |
| `--metadatos {todos,cambian}` | guarda `metadata_nodos_<anio>.csv` |
| `--limite N` | solo los primeros N nodos pendientes (pruebas) |
| `--pausa`, `--excluir-bisiesto` | igual que el orquestador |

### 2.2 `parche_anio.py` — recupera nodos faltantes (fallas de red)

Re-descarga los nodos que faltan en disco. Correr **después** de `descargar_anio` y
**antes** de `consolidar_anio`. Ahora **también guarda metadata** si se le pasa
`--metadatos` (antes no, lo que dejaba nodos sin metadata).

```bash
python -m Utils.descarga_regiones.parche_anio --anio 2024 --metadatos todos
```

### 2.3 `consolidar_anio.py` — dataset COMPLETO unificado

Une los crudos del año en un único parquet con la ingeniería del proyecto
(datetime, dtypes compactos, columnas UV renombradas, orden, zstd).

```bash
python -m Utils.descarga_regiones.consolidar_anio --anio 2024
python -m Utils.descarga_regiones.consolidar_anio --anio 2024 --excluir-bisiesto
```
Salida: `Data/<Region>/<anio>/Finales/completo/dataset_<tag>_completo_24h_<anio>.parquet`.

---

## 3. `recuperar_metadata.py` — recupera metadata faltante

Para nodos que **ya tienen parquet** pero **no quedaron en** `metadata_nodos_<anio>.csv`
(caso típico: parches antiguos que no guardaban metadata). Re-consulta la API solo
para esos nodos, fusiona con el CSV existente y lo reordena por `nodo_id`.

```bash
# Tamaulipas: recupera los que falten en el CSV
python -m Utils.descarga_regiones.recuperar_metadata --anio 2024

# Otra región / ids concretos
python -m Utils.descarga_regiones.recuperar_metadata --anio 2024 \
    --metadata Data/Puerto_Rico/metadata_nodos_pr.csv --raiz Data/Puerto_Rico
python -m Utils.descarga_regiones.recuperar_metadata --anio 2024 --ids 308 309 312
```
| Opción | Para qué |
|---|---|
| `--ids N...` | nodos concretos (def.: los que falten en el CSV) |
| `--meta-modo {todos,cambian}` | campos a capturar (def. `todos`) |
| `--metadata`, `--raiz` | apuntar a otra región |
| `--excluir-bisiesto` | debe coincidir con cómo se bajó el año |

---

## 4. `consultar_cupo.py` — cupo diario de la API

Muestra cuántas peticiones quedan hoy (límite diario 10 000). **Cuesta 1 petición.**

```bash
python -m Utils.descarga_regiones.consultar_cupo
# -> Cupo NSRDB (hoy): 3,088 / 10,000 restantes  ·  usadas: 6,912
```

Modos de metadata (`--metadatos` / `--meta-modo`):
- **`todos`** — toda la cabecera NSRDB (47 campos): localización, unidades,
  diccionarios de `cloud_type`/`fill_flag`, husos, versión.
- **`cambian`** — solo lo que varía por nodo: `location_id, latitude, longitude, elevation`.

---

## 5. Malla / corrección de Puerto Rico

Herramientas usadas para corregir la malla de PR (0.02° → 0.04°). Ver el porqué y el
resultado en [`Data/Puerto_Rico/README.md`](Data/Puerto_Rico/README.md).

### 5.1 `generar_malla_pr_4km.py` — construye la malla correcta (no destructivo)

Deduplica por `location_id` las coordenadas reales de la descarga, reindexa `0…753`
y deja en staging la metadata + el mapeo viejo→nuevo, más un mapa de verificación.

```bash
python -m Utils.descarga_regiones.generar_malla_pr_4km
# -> Data/Puerto_Rico/malla_4km_propuesta/{metadata_nodos_pr_4km.csv, mapeo_pr_4km.csv}
# -> Results/Puerto_Rico/malla_4km_propuesta.png
```

### 5.2 `filtrar_pr_4km.py` — aplica la malla sobre datos ya descargados

Verifica que los duplicados sean idénticos, mueve la metadata original al histórico,
la reemplaza por la de 754, filtra/reindexa los crudos (eliminando duplicados) y
regenera el consolidado. **No re-descarga** (los duplicados son copias exactas).

```bash
python -m Utils.descarga_regiones.filtrar_pr_4km --anio 2024
```

> Para re-descargar PR con el 29-feb (ya solo 754 consultas):
> `rm -rf Data/Puerto_Rico/2024 && python -m Utils.descarga_regiones --regiones puerto_rico --anios 2024 --metadatos todos`

---

## 6. Visualización e inspección de nodos

### 6.1 `mapa_interactivo.py` — mapa interactivo (folium, satélite) — en notebook

Para revisar si los nodos caen sobre agua (fondo satelital Esri, con zoom).

```python
from Utils.mapa_interactivo import mapa_nodos
mapa_nodos([2603, 2604, 2650, 2701])               # Tamaulipas (metadata por defecto)
mapa_nodos([0, 1, 2], metadata='Data/Puerto_Rico/metadata_nodos_pr.csv')
```

### 6.2 `mapas_espaciales.py` — mapas estáticos (PNG) de cualquier variable

```bash
# Temperatura media anual
python Utils/mapas_espaciales.py --variable temperature --unidades "°C" --cmap inferno
# Radiación solar media diaria (insolación), kWh/m²/día
python Utils/mapas_espaciales.py --variable ghi --agregacion suma_diaria --factor 0.001 \
    --unidades "kWh/m²/día" --titulo "Radiación solar media diaria"
# GHI de junio / de un día concreto
python Utils/mapas_espaciales.py --variable ghi --filtro mensual --mes 6 --unidades "W/m²"
python Utils/mapas_espaciales.py --variable wind_speed --filtro diario --dia 2017-06-21 --unidades m/s
# Panel 4x3 de los 12 meses
python Utils/mapas_espaciales.py --variable temperature --panel12 --unidades "°C" --cmap inferno
```
| Opción | Valores |
|---|---|
| `--variable` | columna del dataset (def. `ghi`) |
| `--filtro` | `anual` \| `mensual` \| `diario` |
| `--mes` `1-12` / `--dia` `YYYY-MM-DD` | según el filtro |
| `--agregacion` | `media` \| `suma_diaria` \| `max` \| `min` |
| `--factor`, `--titulo`, `--unidades`, `--cmap`, `--panel12` | formato/escala |

### 6.3 `seleccion_lasso.py` — selección interactiva de nodos (notebook)

Selecciona nodos a eliminar (mar/laguna/isla) dibujando con el mouse. Requiere
`%matplotlib widget` en la primera celda.

```python
%matplotlib widget
from Utils.seleccion_lasso import SelectorNodos
sel = SelectorNodos()        # preselecciona msnm==0; arrastra para añadir/quitar
sel.guardar()                # -> Data/Tamaulipas/nodos_a_eliminar.csv
```

---

## 7. Scripts históricos (armado inicial — referencia)

Quedaron como histórico del armado y **no** son el flujo activo:

- **`Utils/legacy/`** — scripts de un solo uso / tareas específicas del armado de
  Tamaulipas 2017 (mallas, descargas masivas, deduplicación, mapas puntuales
  superados por `mapas_espaciales.py`). Detalle en
  [`Utils/legacy/README.md`](Utils/legacy/README.md).
- **`Utils/puerto_rico_v3_2017/`**, **`Utils/puerto_rico_v4_2017/`** — armado
  histórico de Puerto Rico (un notebook aún importa de ellas).
- Orquestador solo-Tamaulipas (legacy): `Utils.descarga_regiones.descargar_varios_anios`.

Para años/regiones nuevas usar siempre **`Utils/descarga_regiones/descargar_regiones.py`** (§1).
