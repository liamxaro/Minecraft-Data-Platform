import os
import duckdb
import tldextract

class Bundle():
    def __init__(self, modrinth_base_url = 'https://api.modrinth.com/v2',
                 minecraft_java_version_url = 'https://piston-meta.mojang.com/mc/game/version_manifest_v2.json',
                 headers = {
                   'User-Agent' : 'liamxaro/Minecraft-data-platform/(contact: stormcraftmods@gmail.com)'  
                 }, search_limit = 100, concurrency = 25,
                 data_directory = 'data', environment = 'dev',
                api_project_listings_table_name = 'api_project_listings',
                api_file_tables_table_name = 'api_file_tables',
                minecraft_java_versions_table_name = 'minecraft_java_versions',
                project_distribution_over_time_table_name = 'project_distribution_over_time'):
        
        
        #url and api information
        self.modrinth_base_url = modrinth_base_url
          #tehnically a different data soucre, but so small and tidy it's baked into Modrinth pipline
        self.minecraft_java_version_url = minecraft_java_version_url
        self.headers = headers
        self.search_limit = min(search_limit, 100)  # 100 is max. Modrinth supports pagination with limit/offset :contentReference[oaicite:1]{index=1}
        self.concurrency = concurrency
        
        #data directories / locations
        self.root_project_directory = os.path.dirname(os.getcwd())
        self.data_directory = data_directory
        self.environment = environment
        self.bronze_env_folder_path = os.path.join(self.root_project_directory,
                                                self.data_directory,
                                                'bronze',
                                                self.environment
                                                )
        self.bronze_db_path = os.path.join(self.bronze_env_folder_path,
                                           self.build_db_filename())
        self.silver_env_folder_path = os.path.join(self.root_project_directory,
                                                self.data_directory,
                                                'silver',
                                                self.environment
                                                )
        self.silver_db_path = os.path.join(self.silver_env_folder_path,
                                           self.build_db_filename())
        self.gold_env_folder_path = os.path.join(self.root_project_directory,
                                                self.data_directory,
                                                'gold',
                                                self.environment
                                                )
        self.gold_db_path = os.path.join(self.gold_env_folder_path,
                                         self.build_db_filename())
        
        
        #table names
          #utility layer
        self.ingestion_log_table_name = "ingestion_log"
        self.data_rule_table_name = 'data_rule'
        
          #bronze layer
        self.raw_api_project_listings_table_name = f"raw_{api_project_listings_table_name}"
        self.raw_api_file_tables_table_name = f"raw_{api_file_tables_table_name}"
        
        
          #silver layer (base)
        self.base_api_project_listings_table_name = f"base_{api_project_listings_table_name}"
        self.base_api_file_tables_table_name = f"base_{api_file_tables_table_name}"
        self.base_project_distribution_over_time_table_name = f"base_{project_distribution_over_time_table_name}"
        
          #silver layer (enriched)
        self.enriched_api_project_listings_table_name = f"enriched_{api_project_listings_table_name}"
        self.enriched_api_file_tables_table_name = f"enriched_{api_file_tables_table_name}"
        
          #gold layer
        self.snapshot_api_project_listings_table_name = f"snapshot_{api_project_listings_table_name}"
        
        self.snapshot_minecraft_java_versions_table_name = f"snapshot_{minecraft_java_versions_table_name}"
        
        
        #Schemas
        #---utility schemas
        self.ingestion_log_schema = f"""
                CREATE TABLE IF NOT EXISTS {self.ingestion_log_table_name} (
                    run_id                  VARCHAR NOT NULL,
                    ingestion_type          VARCHAR NOT NULL,
                    api_url                 VARCHAR NOT NULL,
                    project_type            VARCHAR NOT NULL,
                    status                  VARCHAR NOT NULL,

                    records_processed       BIGINT,
                    records_written         BIGINT,
                    records_failed          BIGINT,
                    records_skipped         BIGINT,
                    nested_records_fetched  BIGINT,

                    failed_record_ids       VARCHAR[],
                    skipped_record_ids      VARCHAR[],

                    error_message           VARCHAR,
                    start_time              TIMESTAMPTZ,
                    end_time                TIMESTAMPTZ,
                    duration_seconds        DOUBLE,

                    PRIMARY KEY (
                        run_id,
                        ingestion_type,
                        project_type
                    )
                );
            """
        
        
        self.data_rule_schema = f"""
        """

        #---bronze schemas
        self.raw_api_project_listings_schema = f"""
          CREATE TABLE IF NOT EXISTS {self.raw_api_project_listings_table_name} (
              run_id VARCHAR NOT NULL,
              project_type VARCHAR NOT NULL,
              project_id VARCHAR NOT NULL,
              payload JSON NOT NULL,
              c_pull_timestamp_utc TIMESTAMPTZ NOT NULL,
              PRIMARY KEY (run_id, project_type, project_id)
          );
          """
        
        self.raw_api_file_tables_schema = f"""
              CREATE TABLE IF NOT EXISTS {self.raw_api_file_tables_table_name} (
                  run_id             VARCHAR NOT NULL,
                  project_type       VARCHAR NOT NULL,
                  project_id         VARCHAR NOT NULL,
                  payload            JSON NOT NULL,
                  c_pull_timestamp_utc TIMESTAMPTZ NOT NULL,
                  PRIMARY KEY (run_id, project_type, project_id)
              );
        """
        
        
        #---silver base schemas
        self.base_api_project_listings_schema = f"""
                    CREATE TABLE IF NOT EXISTS {self.base_api_project_listings_table_name} (
                        run_id             UUID NOT NULL,
                        project_type       VARCHAR NOT NULL,
                        project_id         VARCHAR NOT NULL,
                        slug               VARCHAR,
                        display_title      VARCHAR NOT NULL,
                        author             VARCHAR,
                        description        VARCHAR,
                        categories         VARCHAR[] NOT NULL,
                        versions           VARCHAR[] NOT NULL,
                        latest_version     VARCHAR,
                        download_count     BIGINT NOT NULL,
                        follows            BIGINT NOT NULL,
                        client_side        VARCHAR,
                        server_side        VARCHAR,
                        license            VARCHAR,
                        date_created       TIMESTAMP NOT NULL,
                        date_modified      TIMESTAMP NOT NULL,
                        date_retrieved_at  TIMESTAMP NOT NULL,
                        PRIMARY KEY (project_id)
                                            
                                        )
        """
        
        
        #---gold schemas
        self.snapshot_minecraft_java_versions_schema = f"""
                      CREATE TABLE IF NOT EXISTS {self.snapshot_minecraft_java_versions_table_name} (
                        version_id           VARCHAR NOT NULL,
                        release_type         VARCHAR,
                        version_url          VARCHAR,
                        release_time         TIMESTAMP,
                        manifest_time        TIMESTAMP,
                        sha1                 VARCHAR,
                        compliance_level     BIGINT,
                        manifest_order       BIGINT NOT NULL,
                        is_latest_release    BOOLEAN NOT NULL,
                        is_latest_snapshot   BOOLEAN NOT NULL,
                        PRIMARY KEY (version_id)
                    )
                        """
        
        self.platform_loader_map = {
            "mod": {
                "fabric",
                "forge",
                "neoforge",
                "quilt",
                "rift",
                "liteloader",
                "legacy-fabric",
                "ornithe",
                "nilloader",
                "modloader",
                "babric",
                "bta-babric",
            },
            "modpack": {
                "fabric",
                "forge",
                "neoforge",
                "quilt",
                "rift",
                "liteloader",
                "legacy-fabric",
                "ornithe",
                "nilloader",
                "modloader",
                "babric",
                "bta-babric",
            },
            "plugin": {
                "paper",
                "spigot",
                "bukkit",
                "folia",
                "velocity",
                "bungeecord",
                "waterfall",
                "purpur",
                "sponge",
            },
            "shader": {
                "iris",
                "optifine",
                "canvas",
            },
            "datapack": {
                "datapack",
                "vanilla",
            },
            "minecraft_java_server": {
                "paper",
                "spigot",
                "bukkit",
                "folia",
                "velocity",
                "bungeecord",
                "waterfall",
                "purpur",
                "sponge",
                "vanilla",
                "minecraft",
                "geyser",
            },
        }
        
        # self.base_project_distribution_over_time_schema = f"""
        #           CREATE TABLE IF NOT EXISTS {self.base_project_distribution_over_time_table_name} (
        #             run_id                  UUID NOT NULL,
        #             project_type            VARCHAR NOT NULL,
        #             project_type_count      BIGINT NOT NULL,
        #             date_retrieved_at       TIMESTAMP NOT NULL
                    
        #           )
        # """
          
    def get_layer_map(self) -> dict:
      return {
          "bronze": {
              "db_path": self.bronze_db_path,
              "schemas": [
                  self.raw_api_project_listings_schema,
                  self.raw_api_file_tables_schema,
                  self.ingestion_log_schema,
                  
                  
              ]
          },
          "silver": {
              "db_path": self.silver_db_path,
              "schemas": [
                  self.base_api_project_listings_schema
              ]
          },
          "gold": {
              "db_path": self.gold_db_path,
              "schemas": [
                
                #separate data source of minecraft java versions
                  self.snapshot_minecraft_java_versions_schema]
          }
      }
        
    def extract_tld(self, url: str) -> str:
        """
        description: extracts the top-level-domain of a url
        
        ex: modrinth.com -> .com
        """
        return f".{tldextract.extract(url).suffix}"
      
    def build_layer_directory(self, layer_env_path: str) -> None:
      """
      description: is responsible for building data paths
      
      ex: data/bronze/dev/file.duckdb
          data/gold/prod/file.duckdb
      """
      os.makedirs(layer_env_path, exist_ok=True)
      
    def build_db_filename(self) -> str:
      """
      description: function that builds the database filename
      
      example: https:||api.modrinth.com.duckdb
      
      note: potentially come back and see if you can givev it a new name based on param url passed in
      """
      tld = self.extract_tld(self.modrinth_base_url)
      base = self.modrinth_base_url.replace('/', '|')
      base = base[0:(self.modrinth_base_url.index(tld) + len(tld))]
      return f"{base}.duckdb"
        
    def init_db(self, layer: str) -> None:
      """
      description: the goal of this function is to initialize all tables per layer
      
      param(s):
        layer (string): must be [bronze, silver, gold]
        
        db_path (str): absolute file path to the duckdb. should be included in self.bronze_db_path
        
      """
      layer_map = self.get_layer_map()
      
      if layer not in layer_map:
          raise ValueError(f"Unsupported layer: {layer}")
        
      db_path = layer_map[layer]["db_path"]
      schemas = layer_map[layer]["schemas"]

      with duckdb.connect(db_path) as db_con:
          for schema in schemas:
              db_con.execute(schema)