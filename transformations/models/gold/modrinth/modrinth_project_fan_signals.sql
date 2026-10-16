{{
    config(
        materialized='table',
        alias='modrinth_project_fan_signals',
        tags=['gold', 'modrinth', 'fan_signals']
    )
}}

{% set min_downloads = var(
    'fan_signal_min_downloads',
    10000
) %}

{% set min_follows = var(
    'fan_signal_min_follows',
    25
) %}


WITH project_metrics AS (
    SELECT
        project_id,
        project_type,
        title,

        run_id AS source_run_id,
        c_pull_timestamp_utc AS source_observed_at,

        downloads AS current_downloads,
        follows,

        (
            follows::DOUBLE
            / NULLIF(downloads, 0)
            * 1000.0
        ) AS follows_per_1000_downloads

    FROM silver.modrinth_project_listings

    WHERE project_type = 'mod'
        AND downloads IS NOT NULL
        AND downloads > 0
        AND follows IS NOT NULL
        AND follows >= 0
),

fan_candidates AS (
    SELECT
        *

    FROM project_metrics

    WHERE current_downloads >= {{ min_downloads }}
        AND follows >= {{ min_follows }}
),

candidate_ranks AS (
    SELECT
        *,

        RANK() OVER (
            ORDER BY follows_per_1000_downloads
        ) AS follow_rate_rank,

        COUNT(*) OVER (
            PARTITION BY follows_per_1000_downloads
        ) AS follow_rate_tie_count,

        RANK() OVER (
            ORDER BY follows
        ) AS follower_count_rank,

        COUNT(*) OVER (
            PARTITION BY follows
        ) AS follower_count_tie_count,

        COUNT(*) OVER () AS candidate_count

    FROM fan_candidates
),

candidate_percentiles AS (
    SELECT
        *,

        (
            follow_rate_rank
            + ((follow_rate_tie_count - 1) / 2.0)
        )
        / candidate_count
            AS follow_rate_percentile,

        (
            follower_count_rank
            + ((follower_count_tie_count - 1) / 2.0)
        )
        / candidate_count
            AS follower_count_percentile

    FROM candidate_ranks
),

candidate_scores AS (
    SELECT
        *,

        100.0
        * (
            2.0
            * follow_rate_percentile
            * follower_count_percentile
        )
        / NULLIF(
            follow_rate_percentile
            + follower_count_percentile,
            0
        ) AS fan_affinity_score

    FROM candidate_percentiles
),

ranked_candidates AS (
    SELECT
        *,

        ROW_NUMBER() OVER (
            ORDER BY
                fan_affinity_score DESC,
                follows_per_1000_downloads DESC,
                follows DESC,
                project_id
        ) AS fan_affinity_rank

    FROM candidate_scores
)

SELECT
    p.project_id,
    p.project_type,
    p.title,

    p.source_run_id,
    p.source_observed_at,

    p.current_downloads,
    p.follows,
    p.follows_per_1000_downloads,

    r.follow_rate_percentile,
    r.follower_count_percentile,

    r.fan_affinity_score,
    r.fan_affinity_rank,

    CASE
        WHEN r.project_id IS NOT NULL
            THEN TRUE
        ELSE FALSE
    END AS is_fan_signal_candidate

FROM project_metrics AS p

LEFT JOIN ranked_candidates AS r
    ON p.project_id = r.project_id