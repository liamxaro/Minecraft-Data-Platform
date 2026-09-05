import duckdb
import pandas as pd

modrinth_bronze_db_path = "/Users/admin/AroTekCodingSpace/Python-Workspace/Minecraft-Data-Platform/data/bronze/dev/api_modrinth_com.duckdb"
modrinth_silver_db_path = "/Users/admin/AroTekCodingSpace/Python-Workspace/Minecraft-Data-Platform/data/silver/dev/api_modrinth_com.duckdb"
mojang_version_manifest_db_path = "/Users/admin/AroTekCodingSpace/Python-Workspace/Minecraft-Data-Platform/data/silver/dev/mojang_version_manifest.duckdb"


#Utility methods
def run_query(query: str, modrinth_db_path: str) -> pd.DataFrame:
    with duckdb.connect(modrinth_db_path, read_only=True) as conn:
        df = conn.execute(query).df()
    #handle UUID as pyarrow struggles with that data type   
    for column_name in df.columns:
        if not df.empty and df[column_name].apply(lambda x: hasattr(x, "hex") and type(x).__name__ == "UUID").any():
            df[column_name] = df[column_name].astype(str)

    return df

#Cross functional Modrinth Methods
def get_distinct_gameplay_categories(project_type: str):
    query = f"""
        SELECT DISTINCT gameplay_category
        FROM (
            SELECT UNNEST(gameplay_categories) AS gameplay_category
            FROM modrinth_project_listings
            WHERE project_type = '{project_type}'
        ) t
        WHERE gameplay_category IS NOT NULL
          AND TRIM(gameplay_category) <> ''
        ORDER BY gameplay_category
    """
    return run_query(query, modrinth_silver_db_path)

def get_distinct_modrinth_versions(project_type: str):
    query = f"""
        SELECT DISTINCT version_value
        FROM (
            SELECT UNNEST(versions) AS version_value
            FROM modrinth_project_listings
            WHERE project_type = '{project_type}'
        ) t
        WHERE version_value IS NOT NULL
          AND TRIM(version_value) <> ''
          AND regexp_matches(version_value, '^[0-9]+(\\.[0-9]+)*$')
    """
    return run_query(query, modrinth_silver_db_path)    

def get_modrinth_kpis(project_type: str):
    query = f"""
    SELECT
        COUNT(DISTINCT project_id) AS total_projects,

        COUNT(DISTINCT author) AS total_authors,

        CAST(
            SUM(COALESCE(downloads, 0))
            AS BIGINT
        ) AS total_downloads,

        MAX(c_pull_timestamp_utc) AS current_refresh_date,

        COUNT(DISTINCT license) AS total_distinct_licenses,

        COALESCE(
            list_count(
                list_distinct(
                    flatten(
                        list(platform_loaders)
                        FILTER (
                            WHERE platform_loaders IS NOT NULL
                        )
                    )
                )
            ),
            0
        ) AS total_distinct_platform_loaders,

        COALESCE(
            list_count(
                list_distinct(
                    flatten(
                        list(gameplay_categories)
                        FILTER (
                            WHERE gameplay_categories IS NOT NULL
                        )
                    )
                )
            ),
            0
        ) AS total_distinct_gameplay_categories

    FROM modrinth_project_listings

    WHERE project_type = '{project_type}'
    """

    return run_query(
        query,
        modrinth_silver_db_path,
    )

def get_most_popular_modrinth_projects(
    project_type: str,
    limit: int = 10,
    gameplay_categories: list[str] | None = None,
    platform_loaders: list[str] | None = None,
    versions: list[str] | None = None,
):
    filters = [f"project_type = '{project_type}'"]

    if gameplay_categories:
        safe_gameplay_categories = [
            category.strip().lower().replace("'", "''")
            for category in gameplay_categories
        ]

        gameplay_conditions = [
            f"list_contains(gameplay_categories, '{category}')"
            for category in safe_gameplay_categories
        ]

        filters.append(f"({' OR '.join(gameplay_conditions)})")

    if platform_loaders:
        safe_platform_loaders = [
            loader.strip().lower().replace("'", "''")
            for loader in platform_loaders
        ]

        platform_conditions = [
            f"list_contains(platform_loaders, '{loader}')"
            for loader in safe_platform_loaders
        ]

        filters.append(f"({' OR '.join(platform_conditions)})")

    if versions:
        safe_versions = [
            version.strip().replace("'", "''")
            for version in versions
        ]

        version_conditions = [
            f"list_contains(versions, '{version}')"
            for version in safe_versions
        ]

        filters.append(f"({' OR '.join(version_conditions)})")

    where_clause = " AND ".join(filters)

    query = f"""
        SELECT
            display_title,
            author,
            description,
            platform_loaders,
            gameplay_categories,
            versions,
            latest_version,
            downloads,
            follows,
            date_modified,
            date_created
        FROM modrinth_project_listings
        WHERE {where_clause}
        ORDER BY downloads DESC, follows DESC, display_title ASC
        LIMIT {limit}
    """

    return run_query(query, modrinth_silver_db_path)

def get_distinct_platform_loaders(project_type: str):
    query = f"""
        SELECT DISTINCT platform_loader
        FROM (
            SELECT UNNEST(platform_loaders) AS platform_loader
            FROM modrinth_project_listings
            WHERE project_type = '{project_type}'
        ) t
        WHERE platform_loader IS NOT NULL
          AND TRIM(platform_loader) <> ''
        ORDER BY platform_loader
    """
    return run_query(query, modrinth_silver_db_path)


#Modrinth Overview Data Pulls
def get_modrinth_overview_kpis():
    query = f"""
        ATTACH '{modrinth_bronze_db_path}'
        AS bronze
        (READ_ONLY);

        WITH successful_runs AS (
            SELECT DISTINCT
                run_id,
                project_type
            FROM bronze.main.ingestion_log
            WHERE status = 'success'
        )

        SELECT
            COUNT(
                DISTINCT p.project_id
            ) AS total_projects,

            COUNT(
                DISTINCT p.author
            ) AS total_authors,

            CAST(
                SUM(
                    COALESCE(
                        p.downloads,
                        0
                    )
                )
                AS BIGINT
            ) AS total_downloads,

            strftime(
                MAX(
                    p.c_pull_timestamp_utc
                ),
                '%Y-%m-%d %H:%M:%S'
            ) AS last_refresh_date

        FROM modrinth_project_listings AS p

        INNER JOIN successful_runs AS s
            ON p.run_id = s.run_id
            AND p.project_type = s.project_type
    """

    return run_query(
        query,
        modrinth_silver_db_path,
    )

def get_project_type_distribution():
    query = f"""
        ATTACH '{modrinth_bronze_db_path}'
        AS bronze
        (READ_ONLY);

        WITH successful_runs AS (
            SELECT DISTINCT
                run_id,
                project_type
            FROM bronze.main.ingestion_log
            WHERE status = 'success'
        )

        SELECT
            p.project_type,
            COUNT(*) AS project_type_count

        FROM modrinth_project_listings AS p

        INNER JOIN successful_runs AS s
            ON p.run_id = s.run_id
            AND p.project_type = s.project_type

        GROUP BY
            p.project_type

        ORDER BY
            project_type_count DESC
    """

    return run_query(
        query,
        modrinth_silver_db_path,
    )

def get_modrinth_project_listings_time_series():
    query = """
        WITH successful_runs AS (
            SELECT DISTINCT
                run_id,
                project_type

            FROM ingestion_log

            WHERE status = 'success'
        ),

        successful_rows AS (
            SELECT
                r.run_id,
                r.project_type,
                r.c_pull_timestamp_utc,

                json_extract_string(
                    r.payload,
                    '$.author'
                ) AS author,

                TRY_CAST(
                    json_extract_string(
                        r.payload,
                        '$.downloads'
                    )
                    AS BIGINT
                ) AS downloads

            FROM modrinth_project_listings AS r

            INNER JOIN successful_runs AS s
                ON r.run_id = s.run_id
                AND r.project_type = s.project_type
        ),

        run_metrics AS (
            SELECT
                run_id,
                project_type,

                COUNT(*) AS project_count,

                CAST(
                    SUM(
                        COALESCE(
                            downloads,
                            0
                        )
                    )
                    AS BIGINT
                ) AS total_downloads

            FROM successful_rows

            GROUP BY
                run_id,
                project_type
        ),

        run_authors AS (
            SELECT
                run_id,
                COUNT(
                    DISTINCT author
                ) AS total_authors

            FROM successful_rows

            WHERE author IS NOT NULL

            GROUP BY
                run_id
        ),

        run_dates AS (
            SELECT
                run_id,

                MAX(
                    c_pull_timestamp_utc
                ) AS pull_timestamp

            FROM successful_rows

            GROUP BY
                run_id
        )

        SELECT
            rm.run_id,
            rm.project_type,

            strftime(
                rd.pull_timestamp,
                '%Y-%m-%d %H:%M:%S'
            ) AS pull_date,

            rm.project_count,
            rm.total_downloads,
            ra.total_authors

        FROM run_metrics AS rm

        INNER JOIN run_dates AS rd
            ON rm.run_id = rd.run_id

        INNER JOIN run_authors AS ra
            ON rm.run_id = ra.run_id

        ORDER BY
            rd.pull_timestamp,
            rm.project_type
    """

    return run_query(
        query,
        modrinth_bronze_db_path,
    )

def get_modrinth_overview_preview():
    query = """
        SELECT *
        FROM (
            SELECT
                *,
                ROW_NUMBER() OVER (
                    PARTITION BY project_type
                    ORDER BY RANDOM()
                ) AS random_number_threshold
            FROM modrinth_project_listings
        ) t
        WHERE random_number_threshold <= 50
    """
    return run_query(query, modrinth_silver_db_path)

#Modrinth Mod Data Pulls

def get_distinct_mod_release_versions():
    query = """
        SELECT DISTINCT
            r.version_id
        FROM mojang_version_manifest r
        INNER JOIN (
            SELECT UNNEST(versions) AS version_id
            FROM modrinth_project_listings
            WHERE project_type = 'mod'
        ) m
            ON r.version_id = m.version_id
        WHERE r.release_type = 'release'
        ORDER BY r.manifest_order ASC
    """
    return run_query(query, modrinth_silver_db_path)

def get_mod_category_distribution():
    query = """
    SELECT
        gameplay_category,
        COUNT(*) AS project_count,
        SUM(downloads) AS total_downloads
    FROM (
        SELECT
            UNNEST(gameplay_categories) AS gameplay_category,
            downloads
        FROM modrinth_project_listings
        WHERE project_type = 'mod'
    ) t
    GROUP BY gameplay_category
    ORDER BY total_downloads DESC"""
    return run_query(query, modrinth_silver_db_path)


#Modrinth Author Data Pulls
def get_modrinth_author_relevance() -> pd.DataFrame:
    query = """
    WITH latest_snapshot AS (
        SELECT *
        FROM modrinth_project_listings
        WHERE project_type = 'mod'
          AND author IS NOT NULL
          AND TRIM(author) <> ''
    ),
    author_metrics AS (
        SELECT
            author,
            COUNT(DISTINCT project_id) AS mod_count,
            SUM(COALESCE(downloads, 0)) AS total_downloads,
            AVG(COALESCE(downloads, 0)) AS avg_downloads_per_mod,
            SUM(COALESCE(follows, 0)) AS total_follows
        FROM latest_snapshot
        GROUP BY author
    ),
    normalized AS (
        SELECT
            author,
            mod_count,
            total_downloads,
            avg_downloads_per_mod,
            total_follows,
            LN(1 + mod_count) AS log_mod_count,
            LN(1 + total_downloads) AS log_total_downloads,
            LN(1 + avg_downloads_per_mod) AS log_avg_downloads_per_mod,
            LN(1 + total_follows) AS log_total_follows
        FROM author_metrics
    ),
    scored AS (
        SELECT
            author,
            mod_count,
            total_downloads,
            avg_downloads_per_mod,
            total_follows,

            COALESCE(
                (log_total_downloads - MIN(log_total_downloads) OVER ()) /
                NULLIF(MAX(log_total_downloads) OVER () - MIN(log_total_downloads) OVER (), 0),
                0
            ) AS total_downloads_score,

            COALESCE(
                (log_avg_downloads_per_mod - MIN(log_avg_downloads_per_mod) OVER ()) /
                NULLIF(MAX(log_avg_downloads_per_mod) OVER () - MIN(log_avg_downloads_per_mod) OVER (), 0),
                0
            ) AS avg_downloads_score,

            COALESCE(
                (log_total_follows - MIN(log_total_follows) OVER ()) /
                NULLIF(MAX(log_total_follows) OVER () - MIN(log_total_follows) OVER (), 0),
                0
            ) AS follows_score,

            COALESCE(
                (log_mod_count - MIN(log_mod_count) OVER ()) /
                NULLIF(MAX(log_mod_count) OVER () - MIN(log_mod_count) OVER (), 0),
                0
            ) AS mod_count_score
        FROM normalized
    )
    SELECT
        author,
        mod_count,
        total_downloads,
        avg_downloads_per_mod,
        total_follows,
        ROUND(
              total_downloads_score * 0.45
            + avg_downloads_score   * 0.30
            + follows_score         * 0.15
            + mod_count_score       * 0.10
        , 4) AS relevance_score
    FROM scored
    ORDER BY relevance_score DESC, total_downloads DESC
    """
    return run_query(query, modrinth_silver_db_path)

def get_top_authors_by_downloads():
    query = """
    SELECT
        author,
        SUM(downloads) AS total_downloads
    FROM modrinth_project_listings
    WHERE project_type = 'mod'
    GROUP BY author
    ORDER BY total_downloads DESC
    LIMIT 10
    """
    return run_query(query, modrinth_silver_db_path)