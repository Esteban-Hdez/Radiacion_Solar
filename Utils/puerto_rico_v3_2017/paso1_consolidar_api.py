import os
import time
import pandas as pd
import pyarrow.dataset as ds

def consolidar_archivos_api():
    dir_entrada = 'Data/Puerto_Rico_v3_2017/crudos_api/2017'
    archivo_salida = 'Data/Puerto_Rico_v3_2017/intermedios/api_consolidada_2017.parquet'
    
    print("=== PASO 1: CONSOLIDACIÓN DE CARPETA API PARQUET ===")
    print(f"Escaneando archivos en: {dir_entrada}...")
    
    inicio = time.time()
    
    # OPTIMIZACIÓN CRÍTICA: pyarrow.dataset mapea la carpeta completa en milisegundos
    # sin necesidad de hacer un bucle 'for' o 'glob' en Python.
    dataset = ds.dataset(dir_entrada, format="parquet")
    
    # Cargar el dataset completo directamente a un DataFrame de Pandas
    print("Cargando tensores a memoria RAM...")
    df_api = dataset.to_table().to_pandas()
    
    print("Normalizando nombres de columnas...")
    # Homogeneizar nombres (quitar espacios y pasar a minúsculas)
    df_api.columns = df_api.columns.str.strip().str.lower().str.replace(' ', '_')
    
    # Eliminar la columna 'minute' ya que sabemos que es el punto medio (minuto 30)
    if 'minute' in df_api.columns:
        df_api.drop(columns=['minute'], inplace=True)
        
    print("Escribiendo archivo consolidado de la API...")
    os.makedirs(os.path.dirname(archivo_salida), exist_ok=True)
    df_api.to_parquet(archivo_salida, engine='pyarrow', index=False)
    
    tiempo_total = time.time() - inicio
    
    # ==========================================
    # Bloque de Validación de Consistencia
    # ==========================================
    print("\n" + "="*40)
    print("✅ VALIDACIÓN DEL PASO 1 COMPLETA")
    print("="*40)
    print(f"Tiempo de ejecución: {tiempo_total:.2f} segundos")
    print(f"Dimensiones del dataset: {df_api.shape[0]:,} filas x {df_api.shape[1]} columnas")
    
    # Control de filas: 2480 nodos * 8760 horas = 21,724,800 filas exactas
    filas_esperadas = 2480 * 8760
    if df_api.shape[0] == filas_esperadas:
        print("-> Magnitud temporal: PERFECTA (21,724,800 registros)")
    else:
        print(f"-> ⚠️ ADVERTENCIA: Se esperaban {filas_esperadas:,} filas, pero se obtuvieron {df_api.shape[0]:,}")
        
    print(f"Columnas finales: {list(df_api.columns)}")
    print(f"Valores nulos detectados:\n{df_api.isnull().sum()}")
    print("="*40 + "\n")

if __name__ == "__main__":
    consolidar_archivos_api()