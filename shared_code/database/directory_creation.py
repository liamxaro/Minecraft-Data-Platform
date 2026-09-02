import os
from urllib.parse import urlparse


      
def build_layer_directory(layer_env_path: str) -> None:
    """
    description: is responsible for building data paths
    
    ex: data/bronze/dev/file.duckdb
        data/gold/prod/file.duckdb
    """
    os.makedirs(layer_env_path, exist_ok=True)
    
def build_db_filename(url: str) -> str:
    """
    description: function that builds the database filename
    
    example: api.modrinth.com.duckdb
    
    note: potentially come back and see if you can givev it a new name based on param url passed in
    """
    hostname = urlparse(url).netloc
    hostname = hostname.replace('.', '_')
    hostname = hostname.replace('-', '_')

    return f"{hostname}.duckdb"