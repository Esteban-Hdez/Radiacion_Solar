import os
import time
import pandas as pd
import numpy as np

def fusionar_datasets_estructurales():
    ruta_hdf5_filtrado = 'Data/Datasets_Diurnos/nsrdb_pr_preprocesado_2017.parquet'
    ruta_api_consolidada = 'Data/API_Historico/api_consolidada_2017.parquet'
    ruta_final = 'Data/Datasets_Finales/dataset_solar_completo_2017.parquet'
    
    print("=== PASO 2: FUSIÓN DE MATRICES ESPACIOTEMPORALES ===")
    inicio = time.time()
    
    # 1. Cargar el dataset que ya tiene el filtro diurno activo
    print("Cargando dataset físico filtrado (HDF5)...")
    df_fisico = pd.read_parquet(ruta_hdf5_filtrado)
    
    # Extraer variables clave de tiempo del timestamp para la llave de cruce
    print("Extrayendo llaves temporales del dataset físico...")
    df_fisico['year'] = df_fisico['timestamp'].dt.year.astype(np.int16)
    df_fisico['day'] = df_fisico['timestamp'].dt.day.astype(np.int8)
    # Renombrar las columnas existentes para que coincidan con la API
    df_fisico.rename(columns={'hora': 'hour', 'mes': 'month'}, inplace=True)
    
    # 2. Cargar el dataset consolidado de la API (Paso 1)
    print("Cargando dataset meteorológico complementario (API)...")
    df_api = pd.read_parquet(ruta_api_consolidada)
    
    # Asegurar tipos de datos correctos para optimizar el merge
    columnas_llave = ['nodo_id', 'year', 'month', 'day', 'hour']
    for col in columnas_llave:
        df_fisico[col] = df_fisico[col].astype(np.int32)
        df_api[col] = df_api[col].astype(np.int32)
        
    # Omitimos la temperatura de la API para mantener consistencia con MERRA-2 (Opción A)
    if 'temperature' in df_api.columns:
        df_api.drop(columns=['temperature'], inplace=True)

    # 3. Operación de Fusión (Inner Merge)
    print("Ejecutando Inner Merge de alta velocidad...")
    # Al usar 'inner', la tabla de la API se recortará automáticamente 
    # dejando solo las horas diurnas que sobrevivieron al filtro astronómico del HDF5
    df_completo = pd.merge(df_fisico, df_api, on=columnas_llave, how='inner')
    
    # Ordenar el dataset para mantener la estructura secuencial idónea para GNN/LSTM
    print("Ordenando índice espaciotemporal (nodo_id -> timestamp)...")
    df_completo.sort_values(by=['nodo_id', 'timestamp'], inplace=True, ignore_index=True)

    print("\nVista previa del Dataset Maestro Final (Primeras filas):")
    print(df_completo.head())
    
    # Guardar resultado final
    print("Escribiendo Dataset Maestro Final...")
    os.makedirs(os.path.dirname(ruta_final), exist_ok=True)
    df_completo.to_parquet(ruta_final, engine='pyarrow', index=False)
    
    tiempo_total = time.time() - inicio
    
    # ==========================================
    # Bloque de Validación de Consistencia
    # ==========================================
    print("\n" + "="*40)
    print("✅ VALIDACIÓN DEL PASO 2 COMPLETA")
    print("="*40)
    print(f"Tiempo de ejecución: {tiempo_total:.2f} segundos")
    print(f"Filas originales (Filtro Diurno HDF5): {df_fisico.shape[0]:,}")
    print(f"Filas finales unificadas:              {df_completo.shape[0]:,}")
    
    if df_fisico.shape[0] == df_completo.shape[0]:
        print("-> Integridad de filas: PERFECTA (No se perdió ningún registro diurno)")
    else:
        print("-> ⚠️ ADVERTENCIA: Hubo una discrepancia en la alineación de filas.")
        
    print(f"\nLista de características listas para el modelo:\n{list(df_completo.columns)}")
    print("="*40 + "\n")

if __name__ == "__main__":
    fusionar_datasets_estructurales()