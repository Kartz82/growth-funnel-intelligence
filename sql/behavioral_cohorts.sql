-- User Behavioral Engagement Duration & Device Matrix Cohort Analysis
CREATE OR REPLACE VIEW v_behavioral_cohort_velocity AS
WITH session_durations AS (
    SELECT 
        session_id,
        user_pseudo_id,
        traffic_source_medium,
        device_category,
        MIN(event_timestamp) as session_start_time,
        MAX(event_timestamp) as session_end_time,
        EXTRACT(EPOCH FROM (MAX(event_timestamp) - MIN(event_timestamp))) as duration_seconds,
        MAX(CASE WHEN event_name = 'add_to_cart' THEN 1 ELSE 0 END) as added_to_cart,
        MAX(CASE WHEN event_name = 'purchase' THEN 1 ELSE 0 END) as completed_purchase
    FROM raw_ga4_events
    GROUP BY session_id, user_pseudo_id, traffic_source_medium, device_category
),
session_engagement_cohorts AS (
    SELECT 
        *,
        CASE 
            WHEN duration_seconds < 60 THEN '1. Bounce / Under 1 Min'
            WHEN duration_seconds >= 60 AND duration_seconds < 300 THEN '2. Casual / 1-5 Mins'
            WHEN duration_seconds >= 300 AND duration_seconds < 1200 THEN '3. Core Explorer / 5-20 Mins'
            ELSE '4. High Intent / 20+ Mins'
        END as engagement_tier
    FROM session_durations
)
SELECT 
    engagement_tier,
    device_category,
    COUNT(session_id) as absolute_session_volume,
    SUM(added_to_cart) as cart_additions,
    SUM(completed_purchase) as total_purchases,
    ROUND((SUM(added_to_cart)::NUMERIC / NULLIF(COUNT(session_id), 0)) * 100, 2) as cart_add_rate_pct,
    ROUND((SUM(completed_purchase)::NUMERIC / NULLIF(COUNT(session_id), 0)) * 100, 2) as absolute_conversion_rate_pct
FROM session_engagement_cohorts
GROUP BY engagement_tier, device_category
ORDER BY engagement_tier ASC, absolute_session_volume DESC;