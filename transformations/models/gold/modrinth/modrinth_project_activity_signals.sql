{{
    config(
        materialized='table',
        alias='modrinth_project_activity_signals',
        tags=['gold', 'modrinth', 'activity_signals']
    )
}}


{% set activity_window_days = var(
    'activity_signal_window_days',
    35
) %}

{% set min_downloads_gained = var(
    'activity_signal_min_downloads_gained',
    1000
) %}


WITH project_signals AS (
    SELECT
        project_id,
        project_type,
        title,

        current_observed_at,

        current_downloads,
        current_downloads_gained,

        current_velocity,
        baseline_velocity,
        velocity_lift,
        velocity_ratio,

        trend_score,
        trend_rank

    FROM {{ ref('modrinth_project_signals') }}

    WHERE current_velocity IS NOT NULL
),


latest_versions AS (
    SELECT
        project_id,
        project_type,

        version_id AS latest_version_id,
        version_number AS latest_version_number,
        version_type AS latest_version_type,
        date_published AS latest_release_at

    FROM (
        SELECT
            v.project_id,
            v.project_type,

            v.version_id,
            v.version_number,
            v.version_type,
            v.date_published,

            ROW_NUMBER() OVER (
                PARTITION BY
                    v.project_id,
                    v.project_type

                ORDER BY
                    v.date_published DESC,
                    v.version_id DESC
            ) AS row_number

        FROM silver.modrinth_project_versions AS v

        INNER JOIN project_signals AS s
            ON v.project_id = s.project_id
            AND v.project_type = s.project_type

        WHERE v.date_published <=
            s.current_observed_at
    )

    WHERE row_number = 1
),


version_activity AS (
    SELECT
        v.project_id,
        v.project_type,

        COUNT(
            DISTINCT CAST(
                v.date_published AS DATE
            )
        ) FILTER (
            WHERE v.date_published >=
                s.current_observed_at
                - INTERVAL 30 DAY

            AND v.date_published <=
                s.current_observed_at
        ) AS active_release_days_last_30_days,

        COUNT(
            DISTINCT CAST(
                v.date_published AS DATE
            )
        ) FILTER (
            WHERE v.date_published >=
                s.current_observed_at
                - INTERVAL 90 DAY

            AND v.date_published <=
                s.current_observed_at
        ) AS active_release_days_last_90_days

    FROM silver.modrinth_project_versions AS v

    INNER JOIN project_signals AS s
        ON v.project_id = s.project_id
        AND v.project_type = s.project_type

    GROUP BY
        v.project_id,
        v.project_type
),


project_activity AS (
    SELECT
        s.project_id,
        s.project_type,
        s.title,

        s.current_observed_at,

        l.latest_version_id,
        l.latest_version_number,
        l.latest_version_type,
        l.latest_release_at,

        DATE_DIFF(
            'hour',
            l.latest_release_at,
            s.current_observed_at
        ) / 24.0
            AS days_since_latest_release,

        a.active_release_days_last_30_days,
        a.active_release_days_last_90_days,

        s.current_downloads,
        s.current_downloads_gained,

        s.current_velocity,
        s.baseline_velocity,
        s.velocity_lift,
        s.velocity_ratio,

        s.trend_score,
        s.trend_rank

    FROM project_signals AS s

    INNER JOIN latest_versions AS l
        ON s.project_id = l.project_id
        AND s.project_type = l.project_type

    INNER JOIN version_activity AS a
        ON s.project_id = a.project_id
        AND s.project_type = a.project_type
),


activity_candidates AS (
    SELECT
        *

    FROM project_activity

    WHERE days_since_latest_release
            BETWEEN 0 AND {{ activity_window_days }}

        AND current_downloads_gained >=
            {{ min_downloads_gained }}

        AND current_velocity > 0
),


candidate_ranks AS (
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
                current_velocity
        ) AS current_velocity_rank,

        COUNT(*) OVER (
            PARTITION BY
                current_velocity
        ) AS current_velocity_tie_count,

        COUNT(*) OVER ()
            AS candidate_count

    FROM activity_candidates
),


candidate_percentiles AS (
    SELECT
        *,

        (
            release_recency_rank
            + (
                release_recency_tie_count - 1
            ) / 2.0
        )
        / candidate_count
            AS release_recency_percentile,

        (
            current_velocity_rank
            + (
                current_velocity_tie_count - 1
            ) / 2.0
        )
        / candidate_count
            AS current_velocity_percentile

    FROM candidate_ranks
),


candidate_scores AS (
    SELECT
        *,

        100.0
        * (
            2.0
            * release_recency_percentile
            * current_velocity_percentile
        )
        / NULLIF(
            release_recency_percentile
            + current_velocity_percentile,
            0
        ) AS activity_score

    FROM candidate_percentiles
),


ranked_candidates AS (
    SELECT
        *,

        ROW_NUMBER() OVER (
            ORDER BY
                activity_score DESC,
                current_velocity DESC,
                latest_release_at DESC,
                project_id
        ) AS activity_rank

    FROM candidate_scores
)


SELECT
    p.project_id,
    p.project_type,
    p.title,

    p.current_observed_at,

    p.latest_version_id,
    p.latest_version_number,
    p.latest_version_type,
    p.latest_release_at,

    p.days_since_latest_release,

    p.active_release_days_last_30_days,
    p.active_release_days_last_90_days,

    p.current_downloads,
    p.current_downloads_gained,

    p.current_velocity,
    p.baseline_velocity,
    p.velocity_lift,
    p.velocity_ratio,

    p.trend_score,
    p.trend_rank,

    r.release_recency_percentile,
    r.current_velocity_percentile,

    r.activity_score,
    r.activity_rank,

    CASE
        WHEN r.project_id IS NOT NULL
            THEN TRUE
        ELSE FALSE
    END AS is_activity_candidate

FROM project_activity AS p

LEFT JOIN ranked_candidates AS r
    ON p.project_id = r.project_id
    AND p.project_type = r.project_type