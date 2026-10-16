{{
    config(
        materialized='table',
        alias='modrinth_project_breakout_signals',
        tags=['gold', 'modrinth', 'breakout_signals']
    )
}}


WITH project_signals AS (
    SELECT
        project_id,
        project_type,
        title,

        current_observed_at,

        current_downloads,
        comparison_downloads,
        current_downloads_gained,

        current_velocity,
        baseline_velocity,
        velocity_lift,
        velocity_ratio,

        trend_score,
        trend_rank,
        is_trending_candidate,

        (
            current_downloads_gained::DOUBLE
            / NULLIF(
                comparison_downloads,
                0
            )
        ) AS recent_growth_share

    FROM {{ ref('modrinth_project_signals') }}

    WHERE current_downloads IS NOT NULL
        AND current_downloads > 0
),


breakout_candidates AS (
    SELECT
        *

    FROM project_signals

    WHERE is_trending_candidate = TRUE
        AND trend_score IS NOT NULL
        AND current_downloads_gained > 0
),


candidate_ranks AS (
    SELECT
        *,

        RANK() OVER (
            ORDER BY
                trend_score
        ) AS trend_strength_rank,

        COUNT(*) OVER (
            PARTITION BY
                trend_score
        ) AS trend_strength_tie_count,

        RANK() OVER (
            ORDER BY
                current_downloads DESC
        ) AS underexposure_rank,

        COUNT(*) OVER (
            PARTITION BY
                current_downloads
        ) AS underexposure_tie_count,

        COUNT(*) OVER ()
            AS candidate_count

    FROM breakout_candidates
),


candidate_percentiles AS (
    SELECT
        *,

        (
            trend_strength_rank
            + (
                trend_strength_tie_count - 1
            ) / 2.0
        )
        / candidate_count
            AS trend_strength_percentile,

        (
            underexposure_rank
            + (
                underexposure_tie_count - 1
            ) / 2.0
        )
        / candidate_count
            AS underexposure_percentile

    FROM candidate_ranks
),


candidate_scores AS (
    SELECT
        *,

        100.0
        * (
            2.0
            * trend_strength_percentile
            * underexposure_percentile
        )
        / NULLIF(
            trend_strength_percentile
            + underexposure_percentile,
            0
        ) AS breakout_score

    FROM candidate_percentiles
),


ranked_candidates AS (
    SELECT
        *,

        ROW_NUMBER() OVER (
            ORDER BY
                breakout_score DESC,
                trend_score DESC,
                underexposure_percentile DESC,
                current_downloads_gained DESC,
                project_id
        ) AS breakout_rank

    FROM candidate_scores
)


SELECT
    p.project_id,
    p.project_type,
    p.title,

    p.current_observed_at,

    p.current_downloads,
    p.comparison_downloads,
    p.current_downloads_gained,
    p.recent_growth_share,

    p.current_velocity,
    p.baseline_velocity,
    p.velocity_lift,
    p.velocity_ratio,

    p.trend_score,
    p.trend_rank,

    r.trend_strength_percentile,
    r.underexposure_percentile,

    r.breakout_score,
    r.breakout_rank,

    CASE
        WHEN r.project_id IS NOT NULL
            THEN TRUE
        ELSE FALSE
    END AS is_breakout_candidate

FROM project_signals AS p

LEFT JOIN ranked_candidates AS r
    ON p.project_id = r.project_id
    AND p.project_type = r.project_type