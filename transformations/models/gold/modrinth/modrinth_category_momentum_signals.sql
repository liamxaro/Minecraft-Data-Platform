{{
    config(
        materialized='table',
        alias='modrinth_category_momentum_signals',
        tags=['gold', 'modrinth', 'category_momentum']
    )
}}


{% set strong_signal_threshold = var(
    'category_momentum_strong_signal_threshold',
    80
) %}

{% set min_category_projects = var(
    'category_momentum_min_projects',
    10
) %}

{% set min_momentum_projects = var(
    'category_momentum_min_signal_projects',
    3
) %}


WITH platform_loaders AS (
    SELECT DISTINCT
        loader_value AS platform_loader

    FROM silver.modrinth_project_versions AS v

    CROSS JOIN UNNEST(
        v.loaders
    ) AS loader_table(loader_value)

    WHERE loader_value IS NOT NULL
),


unnested_categories AS (
    SELECT DISTINCT
        p.project_id,
        p.project_type,
        category_value AS category

    FROM silver.modrinth_project_listings AS p

    CROSS JOIN UNNEST(
        p.categories
    ) AS category_table(category_value)

    WHERE category_value IS NOT NULL
        AND TRIM(category_value) <> ''
),


gameplay_categories AS (
    SELECT
        c.project_id,
        c.project_type,
        c.category AS gameplay_category

    FROM unnested_categories AS c

    LEFT JOIN platform_loaders AS l
        ON LOWER(c.category)
            = LOWER(l.platform_loader)

    WHERE l.platform_loader IS NULL
),


project_signals AS (
    SELECT
        c.project_id,
        c.project_type,
        c.gameplay_category,

        s.current_observed_at,

        s.current_downloads,
        s.current_downloads_gained,

        s.current_velocity,
        s.baseline_velocity,
        s.velocity_ratio,

        s.trend_score,
        s.trend_rank,

        b.breakout_score,
        b.breakout_rank,
        b.recent_growth_share,

        f.fan_affinity_score,
        f.fan_affinity_rank,

        a.activity_score,
        a.activity_rank,

        CASE
            WHEN s.trend_score IS NOT NULL
                OR b.breakout_score IS NOT NULL
            THEN GREATEST(
                COALESCE(
                    s.trend_score,
                    0
                ),
                COALESCE(
                    b.breakout_score,
                    0
                )
            )

            ELSE NULL
        END AS discovery_score

    FROM gameplay_categories AS c

    LEFT JOIN {{ ref('modrinth_project_signals') }} AS s
        ON c.project_id = s.project_id
        AND c.project_type = s.project_type

    LEFT JOIN {{ ref('modrinth_project_breakout_signals') }} AS b
        ON c.project_id = b.project_id
        AND c.project_type = b.project_type

    LEFT JOIN {{ ref('modrinth_project_fan_signals') }} AS f
        ON c.project_id = f.project_id
        AND c.project_type = f.project_type

    LEFT JOIN {{ ref('modrinth_project_activity_signals') }} AS a
        ON c.project_id = a.project_id
        AND c.project_type = a.project_type
),


project_flags AS (
    SELECT
        *,

        CASE
            WHEN discovery_score IS NOT NULL
            THEN TRUE
            ELSE FALSE
        END AS has_discovery_signal,

        CASE
            WHEN discovery_score
                >= {{ strong_signal_threshold }}
            THEN TRUE
            ELSE FALSE
        END AS has_strong_discovery_signal,

        CASE
            WHEN breakout_score IS NOT NULL
            THEN TRUE
            ELSE FALSE
        END AS has_breakout_signal,

        CASE
            WHEN fan_affinity_score IS NOT NULL
            THEN TRUE
            ELSE FALSE
        END AS has_audience_signal,

        CASE
            WHEN fan_affinity_score
                >= {{ strong_signal_threshold }}
            THEN TRUE
            ELSE FALSE
        END AS has_strong_audience_signal,

        CASE
            WHEN activity_score IS NOT NULL
            THEN TRUE
            ELSE FALSE
        END AS has_activity_signal,

        CASE
            WHEN activity_score
                >= {{ strong_signal_threshold }}
            THEN TRUE
            ELSE FALSE
        END AS has_strong_activity_signal,

        CASE
            WHEN discovery_score IS NOT NULL
                OR activity_score IS NOT NULL
            THEN TRUE
            ELSE FALSE
        END AS has_content_opportunity,

        CASE
            WHEN discovery_score
                    >= {{ strong_signal_threshold }}
                OR activity_score
                    >= {{ strong_signal_threshold }}
            THEN TRUE
            ELSE FALSE
        END AS is_momentum_project

    FROM project_signals
),


category_aggregates AS (
    SELECT
        project_type,
        gameplay_category,

        MAX(
            current_observed_at
        ) AS current_observed_at,

        COUNT(
            DISTINCT project_id
        ) AS total_projects,

        COUNT(
            DISTINCT project_id
        ) FILTER (
            WHERE has_discovery_signal = TRUE
        ) AS projects_with_discovery_signal,

        COUNT(
            DISTINCT project_id
        ) FILTER (
            WHERE has_strong_discovery_signal = TRUE
        ) AS projects_with_strong_discovery,

        COUNT(
            DISTINCT project_id
        ) FILTER (
            WHERE has_breakout_signal = TRUE
        ) AS projects_with_breakout_signal,

        COUNT(
            DISTINCT project_id
        ) FILTER (
            WHERE has_audience_signal = TRUE
        ) AS projects_with_audience_signal,

        COUNT(
            DISTINCT project_id
        ) FILTER (
            WHERE has_strong_audience_signal = TRUE
        ) AS projects_with_strong_audience,

        COUNT(
            DISTINCT project_id
        ) FILTER (
            WHERE has_activity_signal = TRUE
        ) AS projects_with_activity_signal,

        COUNT(
            DISTINCT project_id
        ) FILTER (
            WHERE has_strong_activity_signal = TRUE
        ) AS projects_with_strong_activity,

        COUNT(
            DISTINCT project_id
        ) FILTER (
            WHERE has_content_opportunity = TRUE
        ) AS projects_with_content_opportunity,

        COUNT(
            DISTINCT project_id
        ) FILTER (
            WHERE is_momentum_project = TRUE
        ) AS momentum_project_count,

        SUM(
            COALESCE(
                current_downloads_gained,
                0
            )
        ) AS total_downloads_gained,

        SUM(
            CASE
                WHEN is_momentum_project = TRUE
                THEN COALESCE(
                    current_downloads_gained,
                    0
                )

                ELSE 0
            END
        ) AS momentum_downloads_gained,

        AVG(
            COALESCE(
                current_downloads_gained,
                0
            )
        ) AS average_downloads_gained,

        AVG(
            current_downloads_gained
        ) FILTER (
            WHERE is_momentum_project = TRUE
        ) AS average_momentum_downloads_gained,

        MEDIAN(
            velocity_ratio
        ) FILTER (
            WHERE velocity_ratio IS NOT NULL
        ) AS median_velocity_ratio

    FROM project_flags

    GROUP BY
        project_type,
        gameplay_category
),


eligible_categories AS (
    SELECT
        *,

        CAST(
            momentum_project_count
            AS DOUBLE
        )
        /
        NULLIF(
            total_projects,
            0
        ) AS momentum_project_share,

        CAST(
            momentum_downloads_gained
            AS DOUBLE
        )
        /
        NULLIF(
            total_downloads_gained,
            0
        ) AS momentum_download_gain_share,

        CASE
            WHEN momentum_project_count
                >= {{ min_momentum_projects }}
            THEN TRUE
            ELSE FALSE
        END AS is_category_momentum_candidate

    FROM category_aggregates

    WHERE total_projects
        >= {{ min_category_projects }}
),


percentile_rank_inputs AS (
    SELECT
        *,

        RANK() OVER (
            PARTITION BY project_type

            ORDER BY
                momentum_project_count ASC
        ) AS momentum_count_rank,

        COUNT(*) OVER (
            PARTITION BY
                project_type,
                momentum_project_count
        ) AS momentum_count_tie_count,


        RANK() OVER (
            PARTITION BY project_type

            ORDER BY
                momentum_project_share ASC
        ) AS momentum_share_rank,

        COUNT(*) OVER (
            PARTITION BY
                project_type,
                momentum_project_share
        ) AS momentum_share_tie_count,


        RANK() OVER (
            PARTITION BY project_type

            ORDER BY
                momentum_download_gain_share ASC
        ) AS momentum_download_gain_share_rank,

        COUNT(*) OVER (
            PARTITION BY
                project_type,
                momentum_download_gain_share
        ) AS momentum_download_gain_share_tie_count,


        COUNT(*) OVER (
            PARTITION BY project_type
        ) AS category_count

    FROM eligible_categories
),


percentiles AS (
    SELECT
        *,

        (
            momentum_count_rank
            +
            (
                momentum_count_tie_count
                - 1
            )
            / 2.0
        )
        /
        category_count
        AS momentum_count_percentile,


        (
            momentum_share_rank
            +
            (
                momentum_share_tie_count
                - 1
            )
            / 2.0
        )
        /
        category_count
        AS momentum_share_percentile,


        (
            momentum_download_gain_share_rank
            +
            (
                momentum_download_gain_share_tie_count
                - 1
            )
            / 2.0
        )
        /
        category_count
        AS momentum_download_gain_share_percentile

    FROM percentile_rank_inputs
),


scored_categories AS (
    SELECT
        *,

        CASE
            WHEN is_category_momentum_candidate = TRUE
            THEN
                100.0
                *
                (
                    3.0
                    * momentum_count_percentile
                    * momentum_share_percentile
                    * momentum_download_gain_share_percentile
                )
                /
                NULLIF(
                    (
                        momentum_count_percentile
                        * momentum_share_percentile
                    )
                    +
                    (
                        momentum_count_percentile
                        * momentum_download_gain_share_percentile
                    )
                    +
                    (
                        momentum_share_percentile
                        * momentum_download_gain_share_percentile
                    ),
                    0
                )

            ELSE NULL
        END AS category_momentum_score

    FROM percentiles
),


ranked_candidates AS (
    SELECT
        project_type,
        gameplay_category,

        ROW_NUMBER() OVER (
            PARTITION BY project_type

            ORDER BY
                category_momentum_score DESC,
                momentum_project_count DESC,
                momentum_project_share DESC,
                momentum_download_gain_share DESC,
                gameplay_category
        ) AS category_momentum_rank

    FROM scored_categories

    WHERE is_category_momentum_candidate = TRUE
)


SELECT
    s.project_type,
    s.gameplay_category,

    s.current_observed_at,

    s.total_projects,

    s.projects_with_discovery_signal,
    s.projects_with_strong_discovery,

    s.projects_with_breakout_signal,

    s.projects_with_audience_signal,
    s.projects_with_strong_audience,

    s.projects_with_activity_signal,
    s.projects_with_strong_activity,

    s.projects_with_content_opportunity,

    s.momentum_project_count,
    s.momentum_project_share,

    s.total_downloads_gained,
    s.momentum_downloads_gained,
    s.momentum_download_gain_share,

    s.average_downloads_gained,
    s.average_momentum_downloads_gained,

    s.median_velocity_ratio,

    s.momentum_count_percentile,
    s.momentum_share_percentile,
    s.momentum_download_gain_share_percentile,

    s.category_momentum_score,
    r.category_momentum_rank,

    s.is_category_momentum_candidate

FROM scored_categories AS s

LEFT JOIN ranked_candidates AS r
    ON s.project_type = r.project_type
    AND s.gameplay_category = r.gameplay_category