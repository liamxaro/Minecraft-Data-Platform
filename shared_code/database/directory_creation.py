import os
import tldextract
from urllib.parse import urlparse

def _extract_tld(url: str) -> str:
        """
        description: extracts the top-level-domain of a url
        
        ex: modrinth.com -> .com
        """
        return f".{tldextract.extract(url).suffix}"
      
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

    return f"{hostname}.duckdb"

#data directories / locations
# self.root_project_directory = os.path.dirname(os.getcwd())
# self.data_directory = data_directory
# self.environment = environment
# self.bronze_env_folder_path = os.path.join(self.root_project_directory,
#                                         self.data_directory,
#                                         'bronze',
#                                         self.environment
#                                         )
# self.bronze_db_path = os.path.join(self.bronze_env_folder_path,
#                                     self.build_db_filename())
# self.silver_env_folder_path = os.path.join(self.root_project_directory,
#                                         self.data_directory,
#                                         'silver',
#                                         self.environment
#                                         )
# self.silver_db_path = os.path.join(self.silver_env_folder_path,
#                                     self.build_db_filename())
# self.gold_env_folder_path = os.path.join(self.root_project_directory,
#                                         self.data_directory,
#                                         'gold',
#                                         self.environment
#                                         )
# self.gold_db_path = os.path.join(self.gold_env_folder_path,
#                                     self.build_db_filename())
