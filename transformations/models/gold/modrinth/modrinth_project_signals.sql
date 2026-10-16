{{
    config(
        materialized='table',
        alias='modrinth_project_signals',
        tags=['gold', 'modrinth', 'project_signals']
    )
}}

WITH run_summary AS (
    SELECT
        run_id,
        MAX(c_pull_timestamp_utc) AS observed_at

    FROM bronze.main.modrinth_project_listings

    WHERE project_type = 'mod'

    GROUP BY
        run_id
),

current_run AS (
    SELECT
        run_id,
        observed_at

    FROM run_summary

    ORDER BY
        observed_at DESC,
        run_id DESC

    LIMIT 1
),

comparison_run AS (
    SELECT
        r.run_id,
        r.observed_at

    FROM run_summary AS r

    CROSS JOIN current_run AS c

    WHERE r.observed_at <= (
        c.observed_at - INTERVAL '24 hours'
    )

    ORDER BY
        r.observed_at DESC,
        r.run_id DESC

    LIMIT 1
),

baseline_run AS (
    SELECT
        r.run_id,
        r.observed_at

    FROM run_summary AS r

    CROSS JOIN comparison_run AS c

    WHERE r.observed_at <= (
        c.observed_at - INTERVAL '7 days'
    )

    ORDER BY
        r.observed_at DESC,
        r.run_id DESC

    LIMIT 1
),

selected_runs AS (
    SELECT
        run_id,
        observed_at,
        'current' AS snapshot

    FROM current_run

    UNION ALL

    SELECT
        run_id,
        observed_at,
        'comparison' AS snapshot

    FROM comparison_run

    UNION ALL

    SELECT
        run_id,
        observed_at,
        'baseline' AS snapshot

    FROM baseline_run
),

project_snapshots AS (
    SELECT
        s.snapshot,
        s.observed_at,
        p.run_id,
        p.project_id,

        JSON_EXTRACT_STRING(
            p.payload,
            '$.title'
        ) AS title,

        TRY_CAST(
            JSON_EXTRACT_STRING(
                p.payload,
                '$.downloads'
            )
            AS BIGINT
        ) AS total_downloads,

        p.c_pull_timestamp_utc,

        ROW_NUMBER() OVER (
            PARTITION BY
                s.snapshot,
                p.project_id

            ORDER BY
                p.c_pull_timestamp_utc DESC
        ) AS row_num

    FROM bronze.main.modrinth_project_listings AS p

    INNER JOIN selected_runs AS s
        ON p.run_id = s.run_id

    WHERE p.project_type = 'mod'
),

deduped_snapshots AS (
    SELECT
        snapshot,
        observed_at,
        run_id,
        project_id,
        title,
        total_downloads

    FROM project_snapshots

    WHERE row_num = 1
),

pivoted_snapshots AS (
    SELECT
        project_id,

        MAX(title) FILTER (
            WHERE snapshot = 'current'
        ) AS title,

        MAX(total_downloads) FILTER (
            WHERE snapshot = 'current'
        ) AS current_downloads,

        MAX(total_downloads) FILTER (
            WHERE snapshot = 'comparison'
        ) AS comparison_downloads,

        MAX(total_downloads) FILTER (
            WHERE snapshot = 'baseline'
        ) AS baseline_downloads,

        MAX(observed_at) FILTER (
            WHERE snapshot = 'current'
        ) AS current_observed_at,

        MAX(observed_at) FILTER (
            WHERE snapshot = 'comparison'
        ) AS comparison_observed_at,

        MAX(observed_at) FILTER (
            WHERE snapshot = 'baseline'
        ) AS baseline_observed_at,

        MAX(run_id) FILTER (
            WHERE snapshot = 'current'
        ) AS current_run_id,

        MAX(run_id) FILTER (
            WHERE snapshot = 'comparison'
        ) AS comparison_run_id,

        MAX(run_id) FILTER (
            WHERE snapshot = 'baseline'
        ) AS baseline_run_id

    FROM deduped_snapshots

    GROUP BY
        project_id
),

calculated_metrics AS (
    SELECT
        *,

        current_downloads
            - comparison_downloads
            AS current_downloads_gained,

        comparison_downloads
            - baseline_downloads
            AS baseline_downloads_gained,

        DATE_DIFF(
            'second',
            comparison_observed_at,
            current_observed_at
        ) / 3600.0 AS current_hours,

        DATE_DIFF(
            'second',
            baseline_observed_at,
            comparison_observed_at
        ) / 3600.0 AS baseline_hours

    FROM pivoted_snapshots

    WHERE current_downloads IS NOT NULL
        AND comparison_downloads IS NOT NULL
        AND baseline_downloads IS NOT NULL
),

project_signals AS (
    SELECT
        project_id,
        title,

        current_run_id,
        comparison_run_id,
        baseline_run_id,

        current_observed_at,
        comparison_observed_at,
        baseline_observed_at,

        current_downloads,
        comparison_downloads,
        baseline_downloads,

        current_downloads_gained,
        baseline_downloads_gained,

        current_hours,
        baseline_hours,

        current_downloads_gained
            / NULLIF(
                current_hours,
                0
            ) AS current_velocity,

        baseline_downloads_gained
            / NULLIF(
                baseline_hours,
                0
            ) AS baseline_velocity

    FROM calculated_metrics

    WHERE current_downloads_gained >= 0
        AND baseline_downloads_gained >= 0
),

project_signals_with_ratios AS (
    SELECT
        *,

        current_velocity
            - baseline_velocity
            AS velocity_lift,

        current_velocity
            / NULLIF(
                baseline_velocity,
                0
            ) AS velocity_ratio

    FROM project_signals
),

trend_candidates AS (
    SELECT
        *

    FROM project_signals_with_ratios

    WHERE baseline_velocity > 0
        AND current_downloads_gained >= 1000
        AND velocity_ratio > 1
),

candidate_ranks AS (
    SELECT
        *,

        RANK() OVER (
            ORDER BY velocity_ratio
        ) AS velocity_ratio_rank,

        COUNT(*) OVER (
            PARTITION BY velocity_ratio
        ) AS velocity_ratio_tie_count,

        RANK() OVER (
            ORDER BY current_downloads_gained
        ) AS download_gain_rank,

        COUNT(*) OVER (
            PARTITION BY current_downloads_gained
        ) AS download_gain_tie_count,

        COUNT(*) OVER () AS candidate_count

    FROM trend_candidates
),

candidate_percentiles AS (
    SELECT
        *,

        (
            velocity_ratio_rank
            + ((velocity_ratio_tie_count - 1) / 2.0)
        )
        / candidate_count
            AS velocity_ratio_percentile,

        (
            download_gain_rank
            + ((download_gain_tie_count - 1) / 2.0)
        )
        / candidate_count
            AS download_gain_percentile

    FROM candidate_ranks
),

candidate_scores AS (
    SELECT
        *,

        100.0
        * (
            2.0
            * velocity_ratio_percentile
            * download_gain_percentile
        )
        / NULLIF(
            velocity_ratio_percentile
            + download_gain_percentile,
            0
        ) AS trend_score

    FROM candidate_percentiles
),

ranked_candidates AS (
    SELECT
        *,

        ROW_NUMBER() OVER (
            ORDER BY
                trend_score DESC,
                velocity_ratio DESC,
                current_downloads_gained DESC,
                project_id
        ) AS trend_rank

    FROM candidate_scores
)

SELECT
    s.project_id,
    'mod' AS project_type,
    s.title,

    s.current_run_id,
    s.comparison_run_id,
    s.baseline_run_id,

    s.current_observed_at,
    s.comparison_observed_at,
    s.baseline_observed_at,

    s.current_downloads,
    s.comparison_downloads,
    s.baseline_downloads,

    s.current_downloads_gained,
    s.baseline_downloads_gained,

    s.current_hours,
    s.baseline_hours,

    s.current_velocity,
    s.baseline_velocity,
    s.velocity_lift,
    s.velocity_ratio,

    r.velocity_ratio_percentile,
    r.download_gain_percentile,
    r.trend_score,
    r.trend_rank,

    CASE
        WHEN r.project_id IS NOT NULL
            THEN TRUE
        ELSE FALSE
    END AS is_trending_candidate

FROM project_signals_with_ratios AS s

LEFT JOIN ranked_candidates AS r
    ON s.project_id = r.project_id