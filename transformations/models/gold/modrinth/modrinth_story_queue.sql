{{
    config(
        materialized='table',
        alias='modrinth_story_queue',
        tags=['gold', 'modrinth', 'story_queue']
    )
}}


{% set strong_signal_threshold = var(
    'story_queue_strong_signal_threshold',
    80
) %}

{% set breakout_story_threshold = var(
    'story_queue_breakout_threshold',
    90
) %}

{% set established_trend_threshold = var(
    'story_queue_established_trend_threshold',
    90
) %}

{% set established_download_threshold = var(
    'story_queue_established_download_threshold',
    1000000
) %}

{% set cult_favorite_threshold = var(
    'story_queue_cult_favorite_threshold',
    90
) %}

{% set strong_category_threshold = var(
    'story_queue_strong_category_threshold',
    60
) %}


WITH content_signals AS (
    SELECT
        c.*

    FROM {{ ref('modrinth_project_content_signals') }} AS c
),


category_matches AS (
    SELECT
        c.project_id,
        c.project_type,

        m.gameplay_category,

        m.category_momentum_score,
        m.category_momentum_rank,

        m.total_projects
            AS category_total_projects,

        m.momentum_project_count
            AS category_momentum_project_count,

        m.momentum_project_share
            AS category_momentum_project_share,

        m.momentum_downloads_gained
            AS category_momentum_downloads_gained,

        m.momentum_download_gain_share
            AS category_momentum_download_gain_share,

        ROW_NUMBER() OVER (
            PARTITION BY
                c.project_id,
                c.project_type

            ORDER BY
                m.category_momentum_score DESC NULLS LAST,
                m.category_momentum_rank ASC NULLS LAST,
                m.gameplay_category
        ) AS category_row_num

    FROM content_signals AS c

    INNER JOIN silver.modrinth_project_listings AS p
        ON c.project_id = p.project_id
        AND c.project_type = p.project_type

    INNER JOIN {{ ref('modrinth_category_momentum_signals') }} AS m
        ON c.project_type = m.project_type

        AND list_contains(
            p.categories,
            m.gameplay_category
        )

    WHERE m.is_category_momentum_candidate = TRUE
),


category_context AS (
    SELECT
        project_id,
        project_type,

        MAX(
            CASE
                WHEN category_row_num = 1
                THEN gameplay_category
            END
        ) AS strongest_momentum_category,

        MAX(
            CASE
                WHEN category_row_num = 1
                THEN category_momentum_score
            END
        ) AS strongest_category_momentum_score,

        MAX(
            CASE
                WHEN category_row_num = 1
                THEN category_momentum_rank
            END
        ) AS strongest_category_momentum_rank,

        MAX(
            CASE
                WHEN category_row_num = 1
                THEN category_total_projects
            END
        ) AS strongest_category_total_projects,

        MAX(
            CASE
                WHEN category_row_num = 1
                THEN category_momentum_project_count
            END
        ) AS strongest_category_momentum_project_count,

        MAX(
            CASE
                WHEN category_row_num = 1
                THEN category_momentum_project_share
            END
        ) AS strongest_category_momentum_project_share,

        MAX(
            CASE
                WHEN category_row_num = 1
                THEN category_momentum_downloads_gained
            END
        ) AS strongest_category_momentum_downloads_gained,

        MAX(
            CASE
                WHEN category_row_num = 1
                THEN category_momentum_download_gain_share
            END
        ) AS strongest_category_momentum_download_gain_share,

        COUNT(
            DISTINCT gameplay_category
        ) FILTER (
            WHERE category_momentum_score
                >= {{ strong_category_threshold }}
        ) AS high_momentum_category_count

    FROM category_matches

    GROUP BY
        project_id,
        project_type
),


story_inputs AS (
    SELECT
        c.*,

        ctx.strongest_momentum_category,
        ctx.strongest_category_momentum_score,
        ctx.strongest_category_momentum_rank,

        ctx.strongest_category_total_projects,
        ctx.strongest_category_momentum_project_count,
        ctx.strongest_category_momentum_project_share,

        ctx.strongest_category_momentum_downloads_gained,
        ctx.strongest_category_momentum_download_gain_share,

        COALESCE(
            ctx.high_momentum_category_count,
            0
        ) AS high_momentum_category_count

    FROM content_signals AS c

    LEFT JOIN category_context AS ctx
        ON c.project_id = ctx.project_id
        AND c.project_type = ctx.project_type
),


story_flags AS (
    SELECT
        *,

        CASE
            WHEN cross_signal_count >= 2
            THEN TRUE
            ELSE FALSE
        END AS is_multi_signal_story,


        CASE
            WHEN breakout_score
                >= {{ breakout_story_threshold }}
            THEN TRUE
            ELSE FALSE
        END AS is_breakout_story,


        CASE
            WHEN discovery_score
                    >= {{ strong_signal_threshold }}

                AND development_activity_score
                    >= {{ strong_signal_threshold }}

            THEN TRUE
            ELSE FALSE
        END AS is_fresh_update_momentum_story,


        CASE
            WHEN trend_score
                    >= {{ established_trend_threshold }}

                AND current_downloads
                    >= {{ established_download_threshold }}

            THEN TRUE
            ELSE FALSE
        END AS is_established_heating_up_story,


        CASE
            WHEN audience_score
                    >= {{ cult_favorite_threshold }}

                AND (
                    discovery_score
                        >= {{ strong_signal_threshold }}

                    OR development_activity_score
                        >= {{ strong_signal_threshold }}
                )

            THEN TRUE
            ELSE FALSE
        END AS is_cult_favorite_story,


        CASE
            WHEN development_activity_score >= 90
            THEN TRUE
            ELSE FALSE
        END AS is_fresh_release_attention_story,


        CASE
            WHEN discovery_score >= 90
            THEN TRUE
            ELSE FALSE
        END AS is_discovery_spike_story,


        CASE
            WHEN strongest_category_momentum_score
                >= {{ strong_category_threshold }}

            THEN TRUE
            ELSE FALSE
        END AS has_strong_ecosystem_context

    FROM story_inputs
),


story_classification AS (
    SELECT
        *,

        CASE
            WHEN is_breakout_story = TRUE
            THEN 'Breakout Gem'

            WHEN is_fresh_update_momentum_story = TRUE
            THEN 'Fresh Update + Momentum'

            WHEN is_established_heating_up_story = TRUE
            THEN 'Established Mod Heating Up'

            WHEN is_cult_favorite_story = TRUE
            THEN 'Cult Favorite in Motion'

            WHEN is_fresh_release_attention_story = TRUE
            THEN 'Fresh Release Getting Attention'

            WHEN is_discovery_spike_story = TRUE
            THEN 'Discovery Spike'

            ELSE 'General Opportunity'
        END AS primary_story_type,


        CASE
            WHEN is_breakout_story = TRUE
            THEN
                'Underexposed project showing unusually strong current discovery momentum.'

            WHEN is_fresh_update_momentum_story = TRUE
            THEN
                'Project has both strong discovery momentum and strong recent release activity.'

            WHEN is_established_heating_up_story = TRUE
            THEN
                'Established project is showing unusually strong current trend momentum.'

            WHEN is_cult_favorite_story = TRUE
            THEN
                'Project has unusually strong fan affinity alongside a strong current discovery or activity signal.'

            WHEN is_fresh_release_attention_story = TRUE
            THEN
                'Project has a recent release receiving unusually strong current attention.'

            WHEN is_discovery_spike_story = TRUE
            THEN
                'Project is showing unusually strong current discovery momentum.'

            ELSE
                'Project qualifies as a current content opportunity based on discovery or activity signals.'
        END AS story_reason

    FROM story_flags
)


SELECT
    content_opportunity_rank
        AS story_priority_rank,

    content_opportunity_score
        AS story_priority_score,

    project_id,
    project_type,
    title,

    primary_story_type,
    story_reason,

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

    cross_signal_count,

    primary_signal_score,
    support_strength,

    is_multi_signal_story,
    is_breakout_story,
    is_fresh_update_momentum_story,
    is_established_heating_up_story,
    is_cult_favorite_story,
    is_fresh_release_attention_story,
    is_discovery_spike_story,

    strongest_momentum_category,
    strongest_category_momentum_score,
    strongest_category_momentum_rank,

    strongest_category_total_projects,
    strongest_category_momentum_project_count,
    strongest_category_momentum_project_share,

    strongest_category_momentum_downloads_gained,
    strongest_category_momentum_download_gain_share,

    high_momentum_category_count,
    has_strong_ecosystem_context

FROM story_classification