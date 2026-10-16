import duckdb
import pandas as pd

modrinth_bronze_db_path = "/Users/admin/AroTekCodingSpace/Python-Workspace/Minecraft-Data-Platform/data/bronze/dev/api_modrinth_com.duckdb"
modrinth_silver_db_path = "/Users/admin/AroTekCodingSpace/Python-Workspace/Minecraft-Data-Platform/data/silver/dev/api_modrinth_com.duckdb"
modrinth_gold_db_path = "/Users/admin/AroTekCodingSpace/Python-Workspace/Minecraft-Data-Platform/data/gold/dev/api_modrinth_com.duckdb"
mojang_version_manifest_silver_db_path = "/Users/admin/AroTekCodingSpace/Python-Workspace/Minecraft-Data-Platform/data/silver/dev/piston_meta_mojang_com.duckdb"


#Utility methods
def run_query(query: str, modrinth_db_path: str) -> pd.DataFrame:
    with duckdb.connect(modrinth_db_path, read_only=True) as conn:
        df = conn.execute(query).df()
    #handle UUID as pyarrow struggles with that data type   
    for column_name in df.columns:
        if not df.empty and df[column_name].apply(lambda x: hasattr(x, "hex") and type(x).__name__ == "UUID").any():
            df[column_name] = df[column_name].astype(str)

    return df

def _escape_sql_literal(
    value: str,
) -> str:
    return value.replace(
        "'",
        "''",
    )


def _clean_selected_values(
    selected_values: list[str] | None,
) -> list[str]:
    if not selected_values:
        return []

    return [
        value
        for value in selected_values
        if value.strip().lower() != "all"
    ]


def _build_or_conditions(
    conditions: list[str],
) -> str:
    return (
        "("
        + " OR ".join(conditions)
        + ")"
    )


def contains_all_option(selected_values: list[str] | None) -> bool:
    if not selected_values:
        return False

    return any(
        value.strip().lower() == "all"
        for value in selected_values
    )

#Cross functional Modrinth Methods
def get_distinct_gameplay_categories(project_type: str):
    query = f"""
        SELECT
            *
        FROM modrinth_categories
        WHERE project_type = '{project_type}'
        AND header = 'categories'
        ORDER BY name
    """
    return run_query(query, modrinth_silver_db_path)
 
def get_project_listings(
    project_type: str,
    selected_gameplay_categories: list[str] | None = None,
    selected_platform_loaders: list[str] | None = None,
    selected_versions: list[str] | None = None,
    selected_project_id: str | None = None,
    selected_author_id: str | None = None,
    selected_search: bool = False,
):
    filter_conditions = []

    if (
        selected_gameplay_categories
        and not contains_all_option(
            selected_gameplay_categories
        )
    ):
        gameplay_conditions = [
            f"list_contains(categories, '{category}')"
            for category in selected_gameplay_categories
        ]

        filter_conditions.append(
            f"({' OR '.join(gameplay_conditions)})"
        )

    if (
        selected_platform_loaders
        and not contains_all_option(
            selected_platform_loaders
        )
    ):
        loader_conditions = [
            f"list_contains(categories, '{loader}')"
            for loader in selected_platform_loaders
        ]

        filter_conditions.append(
            f"({' OR '.join(loader_conditions)})"
        )

    if (
        selected_versions
        and not contains_all_option(
            selected_versions
        )
    ):
        version_conditions = [
            f"list_contains(game_versions, '{version}')"
            for version in selected_versions
        ]

        filter_conditions.append(
            f"({' OR '.join(version_conditions)})"
        )

    if selected_project_id:
        filter_conditions.append(
            f"project_id = '{selected_project_id}'"
        )

    if selected_author_id:
        filter_conditions.append(
            f"author_id = '{selected_author_id}'"
        )

    search_operator = (
        "AND"
        if selected_search
        else "OR"
    )

    where_clause = (
        f"project_type = '{project_type}'"
    )

    if filter_conditions:
        where_clause += (
            f"""
            AND (
                {' {} '.format(search_operator).join(filter_conditions)}
            )
            """
        )

    query = f"""
        SELECT
            *

        FROM modrinth_project_listings

        WHERE {where_clause}
    """

    return run_query(
        query,
        modrinth_silver_db_path,
    )

def get_project_versions(
    project_type: str,
    selected_gameplay_categories: list[str] | None = None,
    selected_platform_loaders: list[str] | None = None,
    selected_versions: list[str] | None = None,
    selected_project_id: str | None = None,
    selected_author_id: str | None = None,
    selected_search: bool = False,
):
    filter_groups = []

    if (
        selected_gameplay_categories
        and not contains_all_option(
            selected_gameplay_categories
        )
    ):
        gameplay_category_conditions = [
            f"list_contains(p.categories, '{category}')"
            for category in selected_gameplay_categories
        ]

        filter_groups.append(
            f"({' OR '.join(gameplay_category_conditions)})"
        )

    if (
        selected_platform_loaders
        and not contains_all_option(
            selected_platform_loaders
        )
    ):
        platform_loader_conditions = [
            f"list_contains(v.loaders, '{loader}')"
            for loader in selected_platform_loaders
        ]

        filter_groups.append(
            f"({' OR '.join(platform_loader_conditions)})"
        )

    if (
        selected_versions
        and not contains_all_option(
            selected_versions
        )
    ):
        version_conditions = [
            f"list_contains(v.game_versions, '{version}')"
            for version in selected_versions
        ]

        filter_groups.append(
            f"({' OR '.join(version_conditions)})"
        )

    if selected_project_id:
        filter_groups.append(
            f"v.project_id = '{selected_project_id}'"
        )

    if selected_author_id:
        filter_groups.append(
            f"v.author_id = '{selected_author_id}'"
        )

    search_operator = (
        "AND"
        if selected_search
        else "OR"
    )

    optional_filters = ""

    if filter_groups:
        optional_filters = (
            f"""
            AND (
                {' {} '.format(search_operator).join(filter_groups)}
            )
            """
        )

    query = f"""
        SELECT
            v.*,
            p.title AS project_title,
            p.author AS project_author,
            p.categories AS project_categories

        FROM modrinth_project_versions AS v

        LEFT JOIN modrinth_project_listings AS p
            ON v.project_id = p.project_id
            AND v.project_type = p.project_type

        WHERE v.project_type = '{project_type}'

        {optional_filters}
    """

    return run_query(
        query,
        modrinth_silver_db_path,
    )

def get_modrinth_kpis(project_type: str):
    query = f"""
        ATTACH '{modrinth_silver_db_path}'
        AS silver
        (READ_ONLY);

        WITH run_summary AS (
            SELECT
                run_id,
                MAX(c_pull_timestamp_utc) AS refresh_date

            FROM modrinth_project_listings

            WHERE project_type = '{project_type}'

            GROUP BY
                run_id
        ),

        ranked_runs AS (
            SELECT
                run_id,
                refresh_date,

                ROW_NUMBER() OVER (
                    ORDER BY
                        refresh_date DESC,
                        run_id DESC
                ) AS run_rank

            FROM run_summary

            QUALIFY
                run_rank <= 2
        ),

        filtered_projects AS (
            SELECT
                p.run_id,
                p.project_id,

                JSON_EXTRACT_STRING(
                    p.payload,
                    '$.author'
                ) AS author,

                TRY_CAST(
                    JSON_EXTRACT_STRING(
                        p.payload,
                        '$.downloads'
                    )
                    AS BIGINT
                ) AS downloads,

                JSON_EXTRACT_STRING(
                    p.payload,
                    '$.license'
                ) AS license,

                CAST(
                    JSON_EXTRACT(
                        p.payload,
                        '$.categories'
                    )
                    AS VARCHAR[]
                ) AS categories,

                p.project_type,
                p.c_pull_timestamp_utc

            FROM modrinth_project_listings AS p

            INNER JOIN ranked_runs AS r
                ON p.run_id = r.run_id

            WHERE p.project_type = '{project_type}'

            QUALIFY
                ROW_NUMBER() OVER (
                    PARTITION BY
                        p.run_id,
                        p.project_id

                    ORDER BY
                        p.c_pull_timestamp_utc DESC
                ) = 1
        ),

        project_kpis AS (
            SELECT
                run_id,

                COUNT(DISTINCT project_id)
                    AS total_projects,

                COUNT(DISTINCT author)
                    AS total_authors,

                CAST(
                    SUM(COALESCE(downloads, 0))
                    AS BIGINT
                ) AS total_downloads,

                MAX(c_pull_timestamp_utc)
                    AS current_refresh_date,

                COUNT(DISTINCT license)
                    AS total_distinct_licenses

            FROM filtered_projects

            GROUP BY
                run_id
        ),

        exploded_categories AS (
            SELECT
                p.run_id,
                p.project_id,
                p.project_type,
                category

            FROM filtered_projects AS p

            CROSS JOIN UNNEST(p.categories) AS u(category)
        ),

        loader_kpis AS (
            SELECT
                e.run_id,

                COUNT(DISTINCT l.name)
                    AS total_distinct_platform_loaders

            FROM exploded_categories AS e

            INNER JOIN silver.modrinth_loaders AS l
                ON e.category = l.name

            GROUP BY
                e.run_id
        ),

        category_kpis AS (
            SELECT
                e.run_id,

                COUNT(DISTINCT c.name)
                    AS total_distinct_gameplay_categories

            FROM exploded_categories AS e

            INNER JOIN silver.modrinth_categories AS c
                ON e.category = c.name
                AND e.project_type = c.project_type

            GROUP BY
                e.run_id
        )

        SELECT
            CASE
                WHEN r.run_rank = 1 THEN 'current'
                WHEN r.run_rank = 2 THEN 'previous'
            END AS snapshot,

            p.total_projects,
            p.total_authors,
            p.total_downloads,
            p.current_refresh_date,
            p.total_distinct_licenses,

            COALESCE(
                l.total_distinct_platform_loaders,
                0
            ) AS total_distinct_platform_loaders,

            COALESCE(
                c.total_distinct_gameplay_categories,
                0
            ) AS total_distinct_gameplay_categories

        FROM project_kpis AS p

        INNER JOIN ranked_runs AS r
            ON p.run_id = r.run_id

        LEFT JOIN loader_kpis AS l
            ON p.run_id = l.run_id

        LEFT JOIN category_kpis AS c
            ON p.run_id = c.run_id

        ORDER BY
            r.run_rank
    """

    return run_query(
        query,
        modrinth_bronze_db_path,
    )

def get_first_activity(project_type: str):
    
    query = f"""
    SELECT
    STRFTIME(
        MIN(TRY_CAST(date_published AS TIMESTAMPTZ)),
        '%Y-%m-%d'
    ) AS first_activity_date
    FROM modrinth_project_versions
    WHERE project_type = '{project_type}';
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
        SELECT
            version_id AS version,
            release_time
        FROM mojang_version_manifest
        WHERE type = 'release'
        ORDER BY
            release_time DESC
    """

    return run_query(
        query,
        mojang_version_manifest_silver_db_path,
    )

def get_mod_category_distribution():
    query = """
        SELECT
            c.gameplay_category,
            COUNT(*) AS project_count,
            SUM(c.downloads) AS total_downloads

        FROM (
            SELECT
                UNNEST(categories) AS gameplay_category,
                downloads

            FROM modrinth_project_listings

            WHERE project_type = 'mod'
        ) AS c

        INNER JOIN modrinth_categories AS mc
            ON c.gameplay_category = mc.name
            AND mc.project_type = 'mod'
            AND mc.header = 'categories'

        GROUP BY
            c.gameplay_category

        ORDER BY
            total_downloads DESC
    """

    return run_query(
        query,
        modrinth_silver_db_path,
    )

def get_distinct_mod_loaders():
    query = f"""
        SELECT
            name AS platform_loaders
        FROM modrinth_loaders
        WHERE len(supported_project_types) > 0
        AND list_has_all(
                ['mod', 'modpack', 'project'],
                supported_project_types
            )
        AND list_has_any(
                supported_project_types,
                ['mod', 'modpack']
            );
    """
    return run_query(query, modrinth_silver_db_path)

def get_mod_loader_distribution():
    query = """
        SELECT
            c.platform_loader,
            COUNT(*) AS project_count,
            SUM(c.downloads) AS total_downloads

        FROM (
            SELECT
                UNNEST(categories) AS platform_loader,
                downloads

            FROM modrinth_project_listings

            WHERE project_type = 'mod'
        ) AS c

        INNER JOIN modrinth_loaders AS l
            ON c.platform_loader = l.name

        GROUP BY
            c.platform_loader

        ORDER BY
            project_count DESC
    """

    return run_query(
        query,
        modrinth_silver_db_path,
    )

def get_mod_version_distribution():
    query = f"""
        ATTACH '{mojang_version_manifest_silver_db_path}' AS mojang (READ_ONLY);

        SELECT
            v.version,
            m.release_time,
            COUNT(*) AS project_count,
            SUM(v.downloads) AS total_downloads

        FROM (
            SELECT
                UNNEST(versions) AS version,
                downloads

            FROM modrinth_project_listings

            WHERE project_type = 'mod'
        ) AS v

        INNER JOIN (
            SELECT DISTINCT
                version_id,
                release_time
            FROM mojang.mojang_version_manifest
            WHERE type = 'release'
        ) AS m
            ON v.version = m.version_id

        GROUP BY
            v.version,
            m.release_time

        ORDER BY
            total_downloads DESC
    """

    return run_query(
        query,
        modrinth_silver_db_path,
    )

def get_modrinth_trending_signals(
    project_type: str,
    selected_gameplay_categories: list[str] | None = None,
    selected_platform_loaders: list[str] | None = None,
    selected_versions: list[str] | None = None,
    selected_search: bool = False,
):
    filter_groups = []

    if (
        selected_gameplay_categories
        and not contains_all_option(
            selected_gameplay_categories
        )
    ):
        gameplay_category_conditions = [
            f"list_contains(p.categories, '{category}')"
            for category in selected_gameplay_categories
        ]

        filter_groups.append(
            f"({' OR '.join(gameplay_category_conditions)})"
        )

    if (
        selected_platform_loaders
        and not contains_all_option(
            selected_platform_loaders
        )
    ):
        platform_loader_conditions = [
            f"""
            EXISTS (
                SELECT 1

                FROM silver.modrinth_project_versions AS v

                WHERE v.project_id = s.project_id
                    AND v.project_type = s.project_type
                    AND list_contains(
                        v.loaders,
                        '{loader}'
                    )
            )
            """
            for loader in selected_platform_loaders
        ]

        filter_groups.append(
            f"({' OR '.join(platform_loader_conditions)})"
        )

    if (
        selected_versions
        and not contains_all_option(
            selected_versions
        )
    ):
        version_conditions = [
            f"""
            EXISTS (
                SELECT 1

                FROM silver.modrinth_project_versions AS v

                WHERE v.project_id = s.project_id
                    AND v.project_type = s.project_type
                    AND list_contains(
                        v.game_versions,
                        '{version}'
                    )
            )
            """
            for version in selected_versions
        ]

        filter_groups.append(
            f"({' OR '.join(version_conditions)})"
        )

    search_operator = (
        "AND"
        if selected_search
        else "OR"
    )

    optional_filters = ""

    if filter_groups:
        optional_filters = (
            f"""
            AND (
                {' {} '.format(search_operator).join(filter_groups)}
            )
            """
        )

    query = f"""
        ATTACH '{modrinth_silver_db_path}'
            AS silver
            (READ_ONLY);

        SELECT
            s.trend_rank,
            s.project_id,
            s.project_type,
            s.title,
            s.current_downloads,
            s.current_downloads_gained,
            s.current_velocity,
            s.baseline_velocity,
            s.velocity_lift,
            s.velocity_ratio,
            s.trend_score

        FROM modrinth_project_signals AS s

        LEFT JOIN silver.modrinth_project_listings AS p
            ON s.project_id = p.project_id
            AND s.project_type = p.project_type

        WHERE s.project_type = '{project_type}'
            AND s.is_trending_candidate = TRUE

            {optional_filters}

        ORDER BY
            s.trend_rank
    """

    return run_query(
        query,
        modrinth_gold_db_path,
    )

def get_modrinth_hottest_signals(
    project_type: str,
    selected_gameplay_categories: list[str] | None = None,
    selected_platform_loaders: list[str] | None = None,
    selected_versions: list[str] | None = None,
    selected_search: bool = False,
    limit: int = 20,
):
    filter_groups = []

    if (
        selected_gameplay_categories
        and not contains_all_option(
            selected_gameplay_categories
        )
    ):
        gameplay_category_conditions = [
            f"list_contains(p.categories, '{category}')"
            for category in selected_gameplay_categories
        ]

        filter_groups.append(
            f"({' OR '.join(gameplay_category_conditions)})"
        )

    if (
        selected_platform_loaders
        and not contains_all_option(
            selected_platform_loaders
        )
    ):
        platform_loader_conditions = [
            f"""
            EXISTS (
                SELECT 1

                FROM silver.modrinth_project_versions AS v

                WHERE v.project_id = s.project_id
                    AND v.project_type = s.project_type
                    AND list_contains(
                        v.loaders,
                        '{loader}'
                    )
            )
            """
            for loader in selected_platform_loaders
        ]

        filter_groups.append(
            f"({' OR '.join(platform_loader_conditions)})"
        )

    if (
        selected_versions
        and not contains_all_option(
            selected_versions
        )
    ):
        version_conditions = [
            f"""
            EXISTS (
                SELECT 1

                FROM silver.modrinth_project_versions AS v

                WHERE v.project_id = s.project_id
                    AND v.project_type = s.project_type
                    AND list_contains(
                        v.game_versions,
                        '{version}'
                    )
            )
            """
            for version in selected_versions
        ]

        filter_groups.append(
            f"({' OR '.join(version_conditions)})"
        )

    search_operator = (
        "AND"
        if selected_search
        else "OR"
    )

    optional_filters = ""

    if filter_groups:
        optional_filters = (
            f"""
            AND (
                {' {} '.format(search_operator).join(filter_groups)}
            )
            """
        )

    query = f"""
        ATTACH '{modrinth_silver_db_path}'
            AS silver
            (READ_ONLY);

        SELECT
            s.project_id,
            s.project_type,
            s.title,
            s.current_downloads,
            s.current_downloads_gained,
            s.current_velocity,
            s.baseline_velocity,
            s.velocity_lift,
            s.velocity_ratio,
            s.trend_score,
            s.trend_rank

        FROM modrinth_project_signals AS s

        LEFT JOIN silver.modrinth_project_listings AS p
            ON s.project_id = p.project_id
            AND s.project_type = p.project_type

        WHERE s.project_type = '{project_type}'
            AND s.current_velocity IS NOT NULL
            AND s.current_velocity > 0

            {optional_filters}

        ORDER BY
            s.current_velocity DESC

        LIMIT {limit}
    """

    return run_query(
        query,
        modrinth_gold_db_path,
    )

def get_modrinth_fan_signals(
    project_type: str,
    selected_gameplay_categories: list[str] | None = None,
    selected_platform_loaders: list[str] | None = None,
    selected_versions: list[str] | None = None,
    selected_search: bool = False,
):
    filter_groups = []

    if (
        selected_gameplay_categories
        and not contains_all_option(
            selected_gameplay_categories
        )
    ):
        gameplay_category_conditions = [
            f"list_contains(p.categories, '{category}')"
            for category in selected_gameplay_categories
        ]

        filter_groups.append(
            f"({' OR '.join(gameplay_category_conditions)})"
        )

    if (
        selected_platform_loaders
        and not contains_all_option(
            selected_platform_loaders
        )
    ):
        platform_loader_conditions = [
            f"""
            EXISTS (
                SELECT 1

                FROM silver.modrinth_project_versions AS v

                WHERE v.project_id = f.project_id
                    AND v.project_type = f.project_type
                    AND list_contains(
                        v.loaders,
                        '{loader}'
                    )
            )
            """
            for loader in selected_platform_loaders
        ]

        filter_groups.append(
            f"({' OR '.join(platform_loader_conditions)})"
        )

    if (
        selected_versions
        and not contains_all_option(
            selected_versions
        )
    ):
        version_conditions = [
            f"""
            EXISTS (
                SELECT 1

                FROM silver.modrinth_project_versions AS v

                WHERE v.project_id = f.project_id
                    AND v.project_type = f.project_type
                    AND list_contains(
                        v.game_versions,
                        '{version}'
                    )
            )
            """
            for version in selected_versions
        ]

        filter_groups.append(
            f"({' OR '.join(version_conditions)})"
        )

    search_operator = (
        "AND"
        if selected_search
        else "OR"
    )

    optional_filters = ""

    if filter_groups:
        optional_filters = (
            f"""
            AND (
                {' {} '.format(search_operator).join(filter_groups)}
            )
            """
        )

    query = f"""
        ATTACH '{modrinth_silver_db_path}'
            AS silver
            (READ_ONLY);

        SELECT
            f.fan_affinity_rank,
            f.project_id,
            f.project_type,
            f.title,
            f.current_downloads,
            f.follows,
            f.follows_per_1000_downloads,
            f.follow_rate_percentile,
            f.follower_count_percentile,
            f.fan_affinity_score

        FROM modrinth_project_fan_signals AS f

        LEFT JOIN silver.modrinth_project_listings AS p
            ON f.project_id = p.project_id
            AND f.project_type = p.project_type

        WHERE f.project_type = '{project_type}'
            AND f.is_fan_signal_candidate = TRUE

            {optional_filters}

        ORDER BY
            f.fan_affinity_rank
    """

    return run_query(
        query,
        modrinth_gold_db_path,
    )

def get_modrinth_activity_signals(
    project_type: str,
    selected_gameplay_categories: list[str] | None = None,
    selected_platform_loaders: list[str] | None = None,
    selected_versions: list[str] | None = None,
    selected_search: bool = False,
):
    filter_groups = []

    if (
        selected_gameplay_categories
        and not contains_all_option(
            selected_gameplay_categories
        )
    ):
        gameplay_category_conditions = [
            f"list_contains(p.categories, '{category}')"
            for category in selected_gameplay_categories
        ]

        filter_groups.append(
            f"({' OR '.join(gameplay_category_conditions)})"
        )

    if (
        selected_platform_loaders
        and not contains_all_option(
            selected_platform_loaders
        )
    ):
        platform_loader_conditions = [
            f"""
            EXISTS (
                SELECT 1

                FROM silver.modrinth_project_versions AS v

                WHERE v.project_id = a.project_id
                    AND v.project_type = a.project_type
                    AND list_contains(
                        v.loaders,
                        '{loader}'
                    )
            )
            """
            for loader in selected_platform_loaders
        ]

        filter_groups.append(
            f"({' OR '.join(platform_loader_conditions)})"
        )

    if (
        selected_versions
        and not contains_all_option(
            selected_versions
        )
    ):
        version_conditions = [
            f"""
            EXISTS (
                SELECT 1

                FROM silver.modrinth_project_versions AS v

                WHERE v.project_id = a.project_id
                    AND v.project_type = a.project_type
                    AND list_contains(
                        v.game_versions,
                        '{version}'
                    )
            )
            """
            for version in selected_versions
        ]

        filter_groups.append(
            f"({' OR '.join(version_conditions)})"
        )

    search_operator = (
        "AND"
        if selected_search
        else "OR"
    )

    optional_filters = ""

    if filter_groups:
        optional_filters = (
            f"""
            AND (
                {' {} '.format(search_operator).join(filter_groups)}
            )
            """
        )

    query = f"""
        ATTACH '{modrinth_silver_db_path}'
            AS silver
            (READ_ONLY);

        SELECT
            a.activity_rank,
            a.project_id,
            a.project_type,
            a.title,

            a.current_observed_at,

            a.latest_version_id,
            a.latest_version_number,
            a.latest_version_type,
            a.latest_release_at,

            a.days_since_latest_release,

            a.active_release_days_last_30_days,
            a.active_release_days_last_90_days,

            a.current_downloads,
            a.current_downloads_gained,

            a.current_velocity,
            a.baseline_velocity,
            a.velocity_lift,
            a.velocity_ratio,

            a.trend_score,
            a.trend_rank,

            a.release_recency_percentile,
            a.current_velocity_percentile,

            a.activity_score

        FROM modrinth_project_activity_signals AS a

        LEFT JOIN silver.modrinth_project_listings AS p
            ON a.project_id = p.project_id
            AND a.project_type = p.project_type

        WHERE a.project_type = '{project_type}'
            AND a.is_activity_candidate = TRUE

            {optional_filters}

        ORDER BY
            a.activity_rank
    """

    return run_query(
        query,
        modrinth_gold_db_path,
    )

def get_modrinth_content_signals(
    project_type: str,
    selected_gameplay_categories: list[str] | None = None,
    selected_platform_loaders: list[str] | None = None,
    selected_versions: list[str] | None = None,
    selected_search: bool = False,
):
    filter_groups = []

    if (
        selected_gameplay_categories
        and not contains_all_option(
            selected_gameplay_categories
        )
    ):
        gameplay_category_conditions = [
            f"""
            list_contains(
                p.categories,
                '{category}'
            )
            """
            for category in selected_gameplay_categories
        ]

        filter_groups.append(
            f"({' OR '.join(gameplay_category_conditions)})"
        )

    if (
        selected_platform_loaders
        and not contains_all_option(
            selected_platform_loaders
        )
    ):
        platform_loader_conditions = [
            f"""
            EXISTS (
                SELECT 1

                FROM silver.modrinth_project_versions AS v

                WHERE v.project_id = c.project_id
                    AND v.project_type = c.project_type
                    AND list_contains(
                        v.loaders,
                        '{loader}'
                    )
            )
            """
            for loader in selected_platform_loaders
        ]

        filter_groups.append(
            f"({' OR '.join(platform_loader_conditions)})"
        )

    if (
        selected_versions
        and not contains_all_option(
            selected_versions
        )
    ):
        version_conditions = [
            f"""
            EXISTS (
                SELECT 1

                FROM silver.modrinth_project_versions AS v

                WHERE v.project_id = c.project_id
                    AND v.project_type = c.project_type
                    AND list_contains(
                        v.game_versions,
                        '{version}'
                    )
            )
            """
            for version in selected_versions
        ]

        filter_groups.append(
            f"({' OR '.join(version_conditions)})"
        )

    search_operator = (
        "AND"
        if selected_search
        else "OR"
    )

    optional_filters = ""

    if filter_groups:
        optional_filters = f"""
            AND (
                {' {} '.format(search_operator).join(filter_groups)}
            )
        """

    query = f"""
        ATTACH '{modrinth_silver_db_path}'
            AS silver
            (READ_ONLY);

        SELECT
            c.content_opportunity_rank,

            c.project_id,
            c.project_type,
            c.title,

            c.current_observed_at,

            c.current_downloads,
            c.current_downloads_gained,

            c.current_velocity,
            c.baseline_velocity,
            c.velocity_ratio,

            c.trend_score,
            c.trend_rank,

            c.breakout_score,
            c.breakout_rank,
            c.recent_growth_share,
            c.is_breakout_candidate,

            c.fan_affinity_score,
            c.fan_affinity_rank,
            c.follows,
            c.follows_per_1000_downloads,

            c.activity_score,
            c.activity_rank,

            c.latest_version_number,
            c.latest_version_type,
            c.latest_release_at,
            c.days_since_latest_release,

            c.active_release_days_last_30_days,
            c.active_release_days_last_90_days,

            c.discovery_score,
            c.audience_score,
            c.development_activity_score,

            c.has_discovery_signal,
            c.has_audience_signal,
            c.has_activity_signal,

            c.has_strong_discovery_signal,
            c.has_strong_audience_signal,
            c.has_strong_activity_signal,

            c.cross_signal_count,

            c.primary_signal_score,
            c.support_strength,

            c.content_opportunity_score

        FROM modrinth_project_content_signals AS c

        LEFT JOIN silver.modrinth_project_listings AS p
            ON c.project_id = p.project_id
            AND c.project_type = p.project_type

        WHERE c.project_type = '{project_type}'

            {optional_filters}

        ORDER BY
            c.content_opportunity_rank
    """

    return run_query(
        query,
        modrinth_gold_db_path,
    )

def get_modrinth_story_queue(
    project_type: str,
    selected_gameplay_categories: list[str] | None = None,
    selected_platform_loaders: list[str] | None = None,
    selected_versions: list[str] | None = None,
    selected_search: bool = False
):
    filter_groups = []

    project_type_value = _escape_sql_literal(
        project_type
    )

    if (
        selected_gameplay_categories
        and not contains_all_option(
            selected_gameplay_categories
        )
    ):
        gameplay_category_conditions = [
            f"""
            list_contains(
                p.categories,
                '{_escape_sql_literal(category)}'
            )
            """
            for category in selected_gameplay_categories
        ]

        filter_groups.append(
            f"({' OR '.join(gameplay_category_conditions)})"
        )

    if (
        selected_platform_loaders
        and not contains_all_option(
            selected_platform_loaders
        )
    ):
        platform_loader_conditions = [
            f"""
            EXISTS (
                SELECT
                    1

                FROM silver.modrinth_project_versions AS v

                WHERE v.project_id = s.project_id
                    AND v.project_type = s.project_type
                    AND list_contains(
                        v.loaders,
                        '{_escape_sql_literal(loader)}'
                    )
            )
            """
            for loader in selected_platform_loaders
        ]

        filter_groups.append(
            f"({' OR '.join(platform_loader_conditions)})"
        )

    if (
        selected_versions
        and not contains_all_option(
            selected_versions
        )
    ):
        version_conditions = [
            f"""
            EXISTS (
                SELECT
                    1

                FROM silver.modrinth_project_versions AS v

                WHERE v.project_id = s.project_id
                    AND v.project_type = s.project_type
                    AND list_contains(
                        v.game_versions,
                        '{_escape_sql_literal(version)}'
                    )
            )
            """
            for version in selected_versions
        ]

        filter_groups.append(
            f"({' OR '.join(version_conditions)})"
        )

    search_operator = (
        "AND"
        if selected_search
        else "OR"
    )

    optional_filters = ""

    if filter_groups:
        optional_filters = (
            f"""
            AND (
                {' {} '.format(search_operator).join(filter_groups)}
            )
            """
        )

    query = f"""
        ATTACH '{modrinth_silver_db_path}'
            AS silver
            (READ_ONLY);


        WITH filtered_universe AS (
            SELECT
                s.project_id,
                s.project_type,
                s.title,

                s.current_observed_at,

                s.current_downloads,

                (
                    s.current_downloads
                    - s.current_downloads_gained
                ) AS comparison_downloads,

                s.current_downloads_gained,

                s.current_velocity,
                s.baseline_velocity,
                s.velocity_lift,
                s.velocity_ratio,

                p.categories,
                p.follows,

                CASE
                    WHEN s.current_downloads > 0
                    THEN
                        CAST(
                            p.follows
                            AS DOUBLE
                        )
                        /
                        CAST(
                            s.current_downloads
                            AS DOUBLE
                        )
                        * 1000.0
                END AS follows_per_1000_downloads,

                a.latest_version_number,
                a.latest_version_type,
                a.latest_release_at,

                a.days_since_latest_release,

                a.active_release_days_last_30_days,
                a.active_release_days_last_90_days

            FROM modrinth_project_signals AS s

            LEFT JOIN silver.modrinth_project_listings AS p
                ON s.project_id = p.project_id
                AND s.project_type = p.project_type

            LEFT JOIN modrinth_project_activity_signals AS a
                ON s.project_id = a.project_id
                AND s.project_type = a.project_type

            WHERE s.project_type = '{project_type_value}'

                {optional_filters}
        ),


        trend_percentile_inputs AS (
            SELECT
                *,

                RANK() OVER (
                    ORDER BY
                        velocity_ratio ASC
                ) AS velocity_ratio_rank,

                COUNT(*) OVER (
                    PARTITION BY
                        velocity_ratio
                ) AS velocity_ratio_tie_count,

                RANK() OVER (
                    ORDER BY
                        current_downloads_gained ASC
                ) AS download_gain_rank,

                COUNT(*) OVER (
                    PARTITION BY
                        current_downloads_gained
                ) AS download_gain_tie_count,

                COUNT(*) OVER ()
                    AS trend_candidate_count

            FROM filtered_universe

            WHERE velocity_ratio IS NOT NULL
                AND current_downloads_gained IS NOT NULL
        ),


        trend_percentiles AS (
            SELECT
                *,

                (
                    CAST(
                        velocity_ratio_rank
                        AS DOUBLE
                    )
                    +
                    (
                        CAST(
                            velocity_ratio_tie_count
                            AS DOUBLE
                        )
                        - 1.0
                    )
                    / 2.0
                )
                /
                NULLIF(
                    CAST(
                        trend_candidate_count
                        AS DOUBLE
                    ),
                    0
                ) AS velocity_ratio_percentile,

                (
                    CAST(
                        download_gain_rank
                        AS DOUBLE
                    )
                    +
                    (
                        CAST(
                            download_gain_tie_count
                            AS DOUBLE
                        )
                        - 1.0
                    )
                    / 2.0
                )
                /
                NULLIF(
                    CAST(
                        trend_candidate_count
                        AS DOUBLE
                    ),
                    0
                ) AS download_gain_percentile

            FROM trend_percentile_inputs
        ),


        trend_scored AS (
            SELECT
                *,

                100.0
                *
                (
                    2.0
                    * velocity_ratio_percentile
                    * download_gain_percentile
                )
                /
                NULLIF(
                    velocity_ratio_percentile
                    + download_gain_percentile,
                    0
                ) AS trend_score

            FROM trend_percentiles
        ),


        trend_ranked AS (
            SELECT
                *,

                ROW_NUMBER() OVER (
                    ORDER BY
                        trend_score DESC,
                        current_downloads_gained DESC,
                        velocity_ratio DESC,
                        project_id
                ) AS trend_rank

            FROM trend_scored
        ),


        fan_percentile_inputs AS (
            SELECT
                *,

                RANK() OVER (
                    ORDER BY
                        follows_per_1000_downloads ASC
                ) AS follow_rate_rank,

                COUNT(*) OVER (
                    PARTITION BY
                        follows_per_1000_downloads
                ) AS follow_rate_tie_count,

                RANK() OVER (
                    ORDER BY
                        follows ASC
                ) AS follower_count_rank,

                COUNT(*) OVER (
                    PARTITION BY
                        follows
                ) AS follower_count_tie_count,

                COUNT(*) OVER ()
                    AS fan_candidate_count

            FROM filtered_universe

            WHERE current_downloads > 0
                AND follows IS NOT NULL
                AND follows_per_1000_downloads IS NOT NULL
        ),


        fan_percentiles AS (
            SELECT
                *,

                (
                    CAST(
                        follow_rate_rank
                        AS DOUBLE
                    )
                    +
                    (
                        CAST(
                            follow_rate_tie_count
                            AS DOUBLE
                        )
                        - 1.0
                    )
                    / 2.0
                )
                /
                NULLIF(
                    CAST(
                        fan_candidate_count
                        AS DOUBLE
                    ),
                    0
                ) AS follow_rate_percentile,

                (
                    CAST(
                        follower_count_rank
                        AS DOUBLE
                    )
                    +
                    (
                        CAST(
                            follower_count_tie_count
                            AS DOUBLE
                        )
                        - 1.0
                    )
                    / 2.0
                )
                /
                NULLIF(
                    CAST(
                        fan_candidate_count
                        AS DOUBLE
                    ),
                    0
                ) AS follower_count_percentile

            FROM fan_percentile_inputs
        ),


        fan_scored AS (
            SELECT
                *,

                100.0
                *
                (
                    2.0
                    * follow_rate_percentile
                    * follower_count_percentile
                )
                /
                NULLIF(
                    follow_rate_percentile
                    + follower_count_percentile,
                    0
                ) AS fan_affinity_score

            FROM fan_percentiles
        ),


        fan_ranked AS (
            SELECT
                *,

                ROW_NUMBER() OVER (
                    ORDER BY
                        fan_affinity_score DESC,
                        follows_per_1000_downloads DESC,
                        follows DESC,
                        project_id
                ) AS fan_affinity_rank

            FROM fan_scored
        ),


        activity_percentile_inputs AS (
            SELECT
                *,

                RANK() OVER (
                    ORDER BY
                        days_since_latest_release DESC
                ) AS release_recency_rank,

                COUNT(*) OVER (
                    PARTITION BY
                        days_since_latest_release
                ) AS release_recency_tie_count,

                RANK() OVER (
                    ORDER BY
                        current_velocity ASC
                ) AS activity_velocity_rank,

                COUNT(*) OVER (
                    PARTITION BY
                        current_velocity
                ) AS activity_velocity_tie_count,

                COUNT(*) OVER ()
                    AS activity_candidate_count

            FROM filtered_universe

            WHERE days_since_latest_release IS NOT NULL
                AND current_velocity IS NOT NULL
        ),


        activity_percentiles AS (
            SELECT
                *,

                (
                    CAST(
                        release_recency_rank
                        AS DOUBLE
                    )
                    +
                    (
                        CAST(
                            release_recency_tie_count
                            AS DOUBLE
                        )
                        - 1.0
                    )
                    / 2.0
                )
                /
                NULLIF(
                    CAST(
                        activity_candidate_count
                        AS DOUBLE
                    ),
                    0
                ) AS release_recency_percentile,

                (
                    CAST(
                        activity_velocity_rank
                        AS DOUBLE
                    )
                    +
                    (
                        CAST(
                            activity_velocity_tie_count
                            AS DOUBLE
                        )
                        - 1.0
                    )
                    / 2.0
                )
                /
                NULLIF(
                    CAST(
                        activity_candidate_count
                        AS DOUBLE
                    ),
                    0
                ) AS current_velocity_percentile

            FROM activity_percentile_inputs
        ),


        activity_scored AS (
            SELECT
                *,

                100.0
                *
                (
                    2.0
                    * release_recency_percentile
                    * current_velocity_percentile
                )
                /
                NULLIF(
                    release_recency_percentile
                    + current_velocity_percentile,
                    0
                ) AS activity_score

            FROM activity_percentiles
        ),


        activity_ranked AS (
            SELECT
                *,

                ROW_NUMBER() OVER (
                    ORDER BY
                        activity_score DESC,
                        current_velocity DESC,
                        days_since_latest_release ASC,
                        project_id
                ) AS activity_rank

            FROM activity_scored
        ),


        breakout_percentile_inputs AS (
            SELECT
                t.*,

                CASE
                    WHEN t.comparison_downloads > 0
                    THEN
                        CAST(
                            t.current_downloads_gained
                            AS DOUBLE
                        )
                        /
                        CAST(
                            t.comparison_downloads
                            AS DOUBLE
                        )
                END AS recent_growth_share,

                RANK() OVER (
                    ORDER BY
                        t.trend_score ASC
                ) AS trend_strength_rank,

                COUNT(*) OVER (
                    PARTITION BY
                        t.trend_score
                ) AS trend_strength_tie_count,

                RANK() OVER (
                    ORDER BY
                        t.current_downloads DESC
                ) AS underexposure_rank,

                COUNT(*) OVER (
                    PARTITION BY
                        t.current_downloads
                ) AS underexposure_tie_count,

                COUNT(*) OVER ()
                    AS breakout_candidate_count

            FROM trend_ranked AS t
        ),


        breakout_percentiles AS (
            SELECT
                *,

                (
                    CAST(
                        trend_strength_rank
                        AS DOUBLE
                    )
                    +
                    (
                        CAST(
                            trend_strength_tie_count
                            AS DOUBLE
                        )
                        - 1.0
                    )
                    / 2.0
                )
                /
                NULLIF(
                    CAST(
                        breakout_candidate_count
                        AS DOUBLE
                    ),
                    0
                ) AS trend_strength_percentile,

                (
                    CAST(
                        underexposure_rank
                        AS DOUBLE
                    )
                    +
                    (
                        CAST(
                            underexposure_tie_count
                            AS DOUBLE
                        )
                        - 1.0
                    )
                    / 2.0
                )
                /
                NULLIF(
                    CAST(
                        breakout_candidate_count
                        AS DOUBLE
                    ),
                    0
                ) AS underexposure_percentile

            FROM breakout_percentile_inputs
        ),


        breakout_scored AS (
            SELECT
                *,

                100.0
                *
                (
                    2.0
                    * trend_strength_percentile
                    * underexposure_percentile
                )
                /
                NULLIF(
                    trend_strength_percentile
                    + underexposure_percentile,
                    0
                ) AS breakout_score

            FROM breakout_percentiles
        ),


        breakout_ranked AS (
            SELECT
                *,

                ROW_NUMBER() OVER (
                    ORDER BY
                        breakout_score DESC,
                        trend_score DESC,
                        current_downloads ASC,
                        project_id
                ) AS breakout_rank

            FROM breakout_scored
        ),


        signal_families AS (
            SELECT
                u.project_id,
                u.project_type,
                u.title,

                u.current_observed_at,

                u.current_downloads,
                u.comparison_downloads,
                u.current_downloads_gained,

                u.current_velocity,
                u.baseline_velocity,
                u.velocity_lift,
                u.velocity_ratio,

                u.follows,
                u.follows_per_1000_downloads,

                u.latest_version_number,
                u.latest_version_type,
                u.latest_release_at,
                u.days_since_latest_release,

                u.active_release_days_last_30_days,
                u.active_release_days_last_90_days,

                t.velocity_ratio_percentile,
                t.download_gain_percentile,

                t.trend_score,
                t.trend_rank,

                b.recent_growth_share,
                b.trend_strength_percentile,
                b.underexposure_percentile,

                b.breakout_score,
                b.breakout_rank,

                f.follow_rate_percentile,
                f.follower_count_percentile,

                f.fan_affinity_score,
                f.fan_affinity_rank,

                a.release_recency_percentile,
                a.current_velocity_percentile,

                a.activity_score,
                a.activity_rank,

                CASE
                    WHEN t.trend_score IS NULL
                        AND b.breakout_score IS NULL
                    THEN NULL

                    WHEN t.trend_score IS NULL
                    THEN b.breakout_score

                    WHEN b.breakout_score IS NULL
                    THEN t.trend_score

                    ELSE GREATEST(
                        t.trend_score,
                        b.breakout_score
                    )
                END AS discovery_score,

                f.fan_affinity_score
                    AS audience_score,

                a.activity_score
                    AS development_activity_score

            FROM filtered_universe AS u

            LEFT JOIN trend_ranked AS t
                ON u.project_id = t.project_id
                AND u.project_type = t.project_type

            LEFT JOIN breakout_ranked AS b
                ON u.project_id = b.project_id
                AND u.project_type = b.project_type

            LEFT JOIN fan_ranked AS f
                ON u.project_id = f.project_id
                AND u.project_type = f.project_type

            LEFT JOIN activity_ranked AS a
                ON u.project_id = a.project_id
                AND u.project_type = a.project_type
        ),


        content_inputs AS (
            SELECT
                *,

                discovery_score IS NOT NULL
                    AS has_discovery_signal,

                audience_score IS NOT NULL
                    AS has_audience_signal,

                development_activity_score IS NOT NULL
                    AS has_activity_signal,

                COALESCE(
                    discovery_score >= 80,
                    FALSE
                ) AS has_strong_discovery_signal,

                COALESCE(
                    audience_score >= 80,
                    FALSE
                ) AS has_strong_audience_signal,

                COALESCE(
                    development_activity_score >= 80,
                    FALSE
                ) AS has_strong_activity_signal,

                (
                    CASE
                        WHEN discovery_score >= 80
                        THEN 1
                        ELSE 0
                    END

                    +

                    CASE
                        WHEN audience_score >= 80
                        THEN 1
                        ELSE 0
                    END

                    +

                    CASE
                        WHEN development_activity_score >= 80
                        THEN 1
                        ELSE 0
                    END
                ) AS cross_signal_count,

                GREATEST(
                    COALESCE(
                        discovery_score,
                        0
                    ),
                    COALESCE(
                        development_activity_score,
                        0
                    )
                ) AS primary_signal_score

            FROM signal_families
        ),


        content_units AS (
            SELECT
                *,

                LEAST(
                    1.0,
                    GREATEST(
                        COALESCE(
                            discovery_score,
                            0
                        )
                        - 50.0,
                        0
                    )
                    / 50.0
                ) AS discovery_unit,

                LEAST(
                    1.0,
                    GREATEST(
                        COALESCE(
                            audience_score,
                            0
                        )
                        - 50.0,
                        0
                    )
                    / 50.0
                ) AS audience_unit,

                LEAST(
                    1.0,
                    GREATEST(
                        COALESCE(
                            development_activity_score,
                            0
                        )
                        - 50.0,
                        0
                    )
                    / 50.0
                ) AS activity_unit,

                LEAST(
                    1.0,
                    GREATEST(
                        COALESCE(
                            primary_signal_score,
                            0
                        )
                        - 50.0,
                        0
                    )
                    / 50.0
                ) AS primary_unit

            FROM content_inputs
        ),


        content_support AS (
            SELECT
                *,

                (
                    discovery_unit
                    + audience_unit
                    + activity_unit
                    - primary_unit
                )
                / 2.0 AS support_strength

            FROM content_units
        ),


        content_scored AS (
            SELECT
                *,

                LEAST(
                    100.0,

                    primary_signal_score

                    +

                    (
                        100.0
                        - primary_signal_score
                    )
                    * 0.50
                    * support_strength
                ) AS content_opportunity_score

            FROM content_support
        ),


        story_flags AS (
            SELECT
                *,

                cross_signal_count >= 2
                    AS is_multi_signal_story,

                COALESCE(
                    breakout_score >= 90,
                    FALSE
                ) AS is_breakout_story,

                COALESCE(
                    discovery_score >= 80
                    AND development_activity_score >= 80,
                    FALSE
                ) AS is_fresh_update_momentum_story,

                COALESCE(
                    trend_score >= 90
                    AND current_downloads >= 1000000,
                    FALSE
                ) AS is_established_heating_up_story,

                COALESCE(
                    audience_score >= 90
                    AND (
                        discovery_score >= 80
                        OR development_activity_score >= 80
                    ),
                    FALSE
                ) AS is_cult_favorite_story,

                COALESCE(
                    development_activity_score >= 90,
                    FALSE
                ) AS is_fresh_release_attention_story,

                COALESCE(
                    discovery_score >= 90,
                    FALSE
                ) AS is_discovery_spike_story

            FROM content_scored
        ),


        story_classification AS (
            SELECT
                *,

                CASE
                    WHEN is_breakout_story
                    THEN 'Breakout Gem'

                    WHEN is_fresh_update_momentum_story
                    THEN 'Fresh Update + Momentum'

                    WHEN is_established_heating_up_story
                    THEN 'Established Mod Heating Up'

                    WHEN is_cult_favorite_story
                    THEN 'Cult Favorite in Motion'

                    WHEN is_fresh_release_attention_story
                    THEN 'Fresh Release Getting Attention'

                    WHEN is_discovery_spike_story
                    THEN 'Discovery Spike'

                    WHEN discovery_score IS NOT NULL
                        OR development_activity_score IS NOT NULL
                    THEN 'General Opportunity'

                    ELSE 'No Strong Current Signal'
                END AS primary_story_type,

                CASE
                        WHEN is_breakout_story
                        THEN
                            'Underexposed project showing unusually strong current discovery momentum.'

                        WHEN is_fresh_update_momentum_story
                        THEN
                            'Project has both strong discovery momentum and strong recent release activity.'

                        WHEN is_established_heating_up_story
                        THEN
                            'Established project is showing unusually strong current trend momentum.'

                        WHEN is_cult_favorite_story
                        THEN
                            'Project has unusually strong fan affinity alongside a strong current discovery or activity signal.'

                        WHEN is_fresh_release_attention_story
                        THEN
                            'Project has a recent release receiving unusually strong current attention.'

                        WHEN is_discovery_spike_story
                        THEN
                            'Project is showing unusually strong current discovery momentum.'

                        WHEN discovery_score IS NOT NULL
                            OR development_activity_score IS NOT NULL
                        THEN
                            'Project has a current discovery or activity signal but does not meet a stronger story archetype.'

                        ELSE
                            'Project matches the selected filters but does not currently qualify for a strong discovery or activity signal.'
                    END AS story_reason

            FROM story_flags
        ),



        filtered_story_ranked AS (
                SELECT
                    *,

                    ROW_NUMBER() OVER (
                        ORDER BY
                            content_opportunity_score DESC,
                            cross_signal_count DESC,
                            primary_signal_score DESC,
                            current_downloads_gained DESC,
                            project_id
                    ) AS filtered_story_priority_rank

                FROM story_classification
            )


        SELECT
            f.filtered_story_priority_rank
                AS story_priority_rank,

            f.content_opportunity_score
                AS story_priority_score,

            g.story_priority_rank
                AS global_story_priority_rank,

            g.story_priority_score
                AS global_story_priority_score,

            g.primary_story_type
                AS global_primary_story_type,

            f.project_id,
            f.project_type,
            f.title,

            f.primary_story_type,
            f.story_reason,

            f.current_observed_at,

            f.current_downloads,
            f.comparison_downloads,
            f.current_downloads_gained,

            f.current_velocity,
            f.baseline_velocity,
            f.velocity_lift,
            f.velocity_ratio,

            f.velocity_ratio_percentile,
            f.download_gain_percentile,

            f.trend_score,
            f.trend_rank,

            f.recent_growth_share,
            f.trend_strength_percentile,
            f.underexposure_percentile,

            f.breakout_score,
            f.breakout_rank,

            f.follows,
            f.follows_per_1000_downloads,

            f.follow_rate_percentile,
            f.follower_count_percentile,

            f.fan_affinity_score,
            f.fan_affinity_rank,

            f.latest_version_number,
            f.latest_version_type,
            f.latest_release_at,
            f.days_since_latest_release,

            f.active_release_days_last_30_days,
            f.active_release_days_last_90_days,

            f.release_recency_percentile,
            f.current_velocity_percentile,

            f.activity_score,
            f.activity_rank,

            f.discovery_score,
            f.audience_score,
            f.development_activity_score,

            f.has_discovery_signal,
            f.has_audience_signal,
            f.has_activity_signal,

            f.has_strong_discovery_signal,
            f.has_strong_audience_signal,
            f.has_strong_activity_signal,

            f.cross_signal_count,

            f.primary_signal_score,
            f.support_strength,

            f.is_multi_signal_story,
            f.is_breakout_story,
            f.is_fresh_update_momentum_story,
            f.is_established_heating_up_story,
            f.is_cult_favorite_story,
            f.is_fresh_release_attention_story,
            f.is_discovery_spike_story,

            g.strongest_momentum_category,
            g.strongest_category_momentum_score,
            g.strongest_category_momentum_rank,

            g.high_momentum_category_count,
            g.has_strong_ecosystem_context

        FROM filtered_story_ranked AS f

        LEFT JOIN modrinth_story_queue AS g
            ON f.project_id = g.project_id
            AND f.project_type = g.project_type

        ORDER BY
            f.filtered_story_priority_rank ASC
    """

    return run_query(
        query,
        modrinth_gold_db_path,
    )

def get_modrinth_category_momentum_signals(
    project_type: str,
    selected_gameplay_categories: list[str] | None = None,
):
    filter_groups = []

    if (
        selected_gameplay_categories
        and not contains_all_option(
            selected_gameplay_categories
        )
    ):
        gameplay_category_conditions = [
            f"c.gameplay_category = '{category}'"
            for category in selected_gameplay_categories
        ]

        filter_groups.append(
            f"({' OR '.join(gameplay_category_conditions)})"
        )

    optional_filters = ""

    if filter_groups:
        optional_filters = (
            f"""
            AND (
                {' AND '.join(filter_groups)}
            )
            """
        )

    query = f"""
        SELECT
            c.*

        FROM modrinth_category_momentum_signals AS c

        WHERE c.project_type = '{project_type}'
            AND c.is_category_momentum_candidate = TRUE

        {optional_filters}

        ORDER BY
            c.category_momentum_rank ASC
    """

    return run_query(
        query,
        modrinth_gold_db_path,
    )


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