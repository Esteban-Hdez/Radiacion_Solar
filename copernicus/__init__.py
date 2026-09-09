"""
Descarga y extracción de reanálisis de Copernicus sobre los nodos NSRDB.

Se llama `copernicus` y no `era5` a propósito: en macOS el sistema de archivos
no distingue mayúsculas, así que un paquete `era5/` se mezclaría con la carpeta
`ERA5/` del notebook de referencia —funcionaría aquí por accidente y fallaría en
Linux, que sí distingue—. El nombre además deja sitio a otros productos del
mismo proveedor (CAMS, por ejemplo) sin volver a renombrar.
"""
