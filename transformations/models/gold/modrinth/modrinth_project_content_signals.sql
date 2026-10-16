{{
    config(
        materialized='table',
        alias='modrinth_project_content_signals',
        tags=['gold', 'modrinth', 'content_signals']
    )
}}


{% set strong_signal_threshold = var(
    'content_signal_strong_threshold',
    80
) %}

{% set support_signal_floor = var(
    'content_signal_support_floor',
    50
) %}

{% set corroboration_weight = var(
    'content_signal_corroboration_weight',
    0.50
) %}


WITH combined_signals AS (
    SELECT
        s.project_id,
        s.project_type,
        s.title,

        s.current_observed_at,

        s.current_downloads,
        s.current_downloads_gained,

        s.current_velocity,
        s.baseline_velocity,
        s.velocity_ratio,

        s.trend_score,
        s.trend_rank,
        s.is_trending_candidate,

        b.breakout_score,
        b.breakout_rank,
        b.recent_growth_share,
        b.is_breakout_candidate,

        f.fan_affinity_score,
        f.fan_affinity_rank,
        f.follows,
        f.follows_per_1000_downloads,
        f.is_fan_signal_candidate,

        a.activity_score,
        a.activity_rank,

        a.latest_version_number,
        a.latest_version_type,
        a.latest_release_at,
        a.days_since_latest_release,

        a.active_release_days_last_30_days,
        a.active_release_days_last_90_days,

        a.is_activity_candidate

    FROM {{ ref('modrinth_project_signals') }} AS s

    LEFT JOIN {{ ref('modrinth_project_breakout_signals') }} AS b
        ON s.project_id = b.project_id
        AND s.project_type = b.project_type

    LEFT JOIN {{ ref('modrinth_project_fan_signals') }} AS f
        ON s.project_id = f.project_id
        AND s.project_type = f.project_type

    LEFT JOIN {{ ref('modrinth_project_activity_signals') }} AS a
        ON s.project_id = a.project_id
        AND s.project_type = a.project_type
),


signal_families AS (
    SELECT
        *,

        CASE
            WHEN trend_score IS NOT NULL
                OR breakout_score IS NOT NULL
            THEN GREATEST(
                COALESCE(
                    trend_score,
                    0
                ),
                COALESCE(
                    breakout_score,
                    0
                )
            )

            ELSE NULL
        END AS discovery_score,

        fan_affinity_score
            AS audience_score,

        activity_score
            AS development_activity_score

    FROM combined_signals
),


signal_flags AS (
    SELECT
        *,

        CASE
            WHEN discovery_score IS NOT NULL
                THEN TRUE
            ELSE FALSE
        END AS has_discovery_signal,

        CASE
            WHEN audience_score IS NOT NULL
                THEN TRUE
            ELSE FALSE
        END AS has_audience_signal,

        CASE
            WHEN development_activity_score IS NOT NULL
                THEN TRUE
            ELSE FALSE
        END AS has_activity_signal,

        CASE
            WHEN discovery_score >=
                {{ strong_signal_threshold }}
                THEN TRUE
            ELSE FALSE
        END AS has_strong_discovery_signal,

        CASE
            WHEN audience_score >=
                {{ strong_signal_threshold }}
                THEN TRUE
            ELSE FALSE
        END AS has_strong_audience_signal,

        CASE
            WHEN development_activity_score >=
                {{ strong_signal_threshold }}
                THEN TRUE
            ELSE FALSE
        END AS has_strong_activity_signal

    FROM signal_families
),


signal_counts AS (
    SELECT
        *,

        CAST(
            has_strong_discovery_signal
            AS INTEGER
        )
        +
        CAST(
            has_strong_audience_signal
            AS INTEGER
        )
        +
        CAST(
            has_strong_activity_signal
            AS INTEGER
        ) AS cross_signal_count

    FROM signal_flags
),


content_candidates AS (
    SELECT
        *,

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

    FROM signal_counts

    WHERE has_discovery_signal = TRUE
        OR has_activity_signal = TRUE
),


support_units AS (
    SELECT
        *,

        LEAST(
            1.0,
            GREATEST(
                COALESCE(
                    discovery_score,
                    0
                )
                - {{ support_signal_floor }},
                0
            )
            / NULLIF(
                100.0
                - {{ support_signal_floor }},
                0
            )
        ) AS discovery_support_unit,

        LEAST(
            1.0,
            GREATEST(
                COALESCE(
                    audience_score,
                    0
                )
                - {{ support_signal_floor }},
                0
            )
            / NULLIF(
                100.0
                - {{ support_signal_floor }},
                0
            )
        ) AS audience_support_unit,

        LEAST(
            1.0,
            GREATEST(
                COALESCE(
                    development_activity_score,
                    0
                )
                - {{ support_signal_floor }},
                0
            )
            / NULLIF(
                100.0
                - {{ support_signal_floor }},
                0
            )
        ) AS activity_support_unit,

        LEAST(
            1.0,
            GREATEST(
                primary_signal_score
                - {{ support_signal_floor }},
                0
            )
            / NULLIF(
                100.0
                - {{ support_signal_floor }},
                0
            )
        ) AS primary_support_unit

    FROM content_candidates
),


support_scores AS (
    SELECT
        *,

        (
            discovery_support_unit
            + audience_support_unit
            + activity_support_unit
            - primary_support_unit
        )
        / 2.0 AS support_strength

    FROM support_units
),


content_scores AS (
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
            * {{ corroboration_weight }}
            * support_strength
        ) AS content_opportunity_score

    FROM support_scores
),


ranked_content AS (
    SELECT
        *,

        ROW_NUMBER() OVER (
            ORDER BY
                content_opportunity_score DESC,
                cross_signal_count DESC,
                primary_signal_score DESC,
                current_downloads_gained DESC,
                project_id
        ) AS content_opportunity_rank

    FROM content_scores
)


SELECT
    project_id,
    project_type,
    title,

    current_observed_at,

    current_downloads,
    current_downloads_gained,

    current_velocity,
    baseline_velocity,
    velocity_ratio,

    trend_score,
    trend_rank,

    breakout_score,
    breakout_rank,
    recent_growth_share,

    fan_affinity_score,
    fan_affinity_rank,
    follows,
    follows_per_1000_downloads,

    activity_score,
    activity_rank,

    latest_version_number,
    latest_version_type,
    latest_release_at,
    days_since_latest_release,

    active_release_days_last_30_days,
    active_release_days_last_90_days,

    discovery_score,
    audience_score,
    development_activity_score,

    has_discovery_signal,
    has_audience_signal,
    has_activity_signal,

    has_strong_discovery_signal,
    has_strong_audience_signal,
    has_strong_activity_signal,

    cross_signal_count,

    primary_signal_score,
    support_strength,

    content_opportunity_score,
    content_opportunity_rank,

    is_breakout_candidate

FROM ranked_content