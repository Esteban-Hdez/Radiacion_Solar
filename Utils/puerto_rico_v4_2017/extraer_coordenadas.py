import os
import h5py
import pandas as pd

def extraer_metadata_nodos():
    ruta_h5 = 'Data/datos_nsrdb/nsrdb_puerto_rico_2017.h5'
    ruta_salida = 'Data/Puerto_Rico_v4_2017/metadata_nodos_pr.csv'
    
    print("=== EXTRACCIÓN DE TOPOLOGÍA Y METADATA ESPACIAL ===")
    print(f"Leyendo archivo origen: {ruta_h5}")
    
    try:
        with h5py.File(ruta_h5, 'r') as f:
            # Extraer el tensor de metadatos directamente a Pandas
            df_meta = pd.DataFrame(f['meta'][:])
            
            # Los archivos HDF5 suelen guardar el texto como cadenas de bytes.
            # Este bucle decodifica todas las columnas de bytes a texto o números normales.
            for col in df_meta.columns:
                if isinstance(df_meta[col].iloc[0], bytes):
                    df_meta[col] = df_meta[col].apply(lambda x: x.decode('utf-8'))
                    # Intentar convertir a numérico (útil para lat/lon que a veces vienen como texto)
                    try:
                        df_meta[col] = pd.to_numeric(df_meta[col])
                    except ValueError:
                        pass
                        
        # La posición de la fila en el archivo HDF5 corresponde a nuestro 'nodo_id'
        df_meta.insert(0, 'nodo_id', df_meta.index)
        
        # Renombramos 'elevation' a 'msnm' para que sea más intuitivo
        if 'elevation' in df_meta.columns:
            df_meta.rename(columns={'elevation': 'msnm'}, inplace=True)
            
        print("\nVista previa de la matriz topológica:")
        pd.set_option('display.max_columns', None)
        pd.set_option('display.width', 1000)
        print(df_meta.head())
        
        # Guardar en formato CSV para fácil lectura y uso futuro
        os.makedirs(os.path.dirname(ruta_salida), exist_ok=True)
        df_meta.to_csv(ruta_salida, index=False)
        
        print(f"\n✅ Extracción exitosa.")
        print(f"💾 Archivo guardado en: {ruta_salida}")
        print(f"📊 Dimensiones: {len(df_meta)} nodos x {len(df_meta.columns)} atributos.")

    except FileNotFoundError:
        print(f"❌ Error: No se encontró el archivo {ruta_h5}")
    except Exception as e:
        print(f"❌ Ocurrió un error inesperado: {e}")

if __name__ == "__main__":
    extraer_metadata_nodos()