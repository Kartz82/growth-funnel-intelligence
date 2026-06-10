-- First-Touch vs Last-Touch Marketing Channel Attribution Comparison
CREATE OR REPLACE VIEW v_marketing_channel_attribution AS
WITH user_purchase_sessions AS (
    SELECT 
        user_pseudo_id,
        session_id AS purchase_session_id,
        traffic_source_medium AS purchase_session_medium,
        event_timestamp AS purchase_timestamp
    FROM raw_ga4_events
    WHERE event_name = 'purchase'
),
user_touchpoints AS (
    SELECT 
        r.user_pseudo_id,
        r.traffic_source_medium AS touchpoint_medium,
        r.event_timestamp,
        -- First touchpoint across the entire user lifetime history
        FIRST_VALUE(r.traffic_source_medium) OVER (
            PARTITION BY r.user_pseudo_id 
            ORDER BY r.event_timestamp ASC
            ROWS BETWEEN UNBOUNDED PRECEDING AND UNBOUNDED FOLLOWING
        ) as first_touch_medium,
        -- Last touchpoint immediately leading up to or equal to the purchase timestamp
        FIRST_VALUE(r.traffic_source_medium) OVER (
            PARTITION BY r.user_pseudo_id, p.purchase_session_id
            ORDER BY r.event_timestamp DESC
            ROWS BETWEEN UNBOUNDED PRECEDING AND UNBOUNDED FOLLOWING
        ) as last_touch_medium
    FROM raw_ga4_events r
    JOIN user_purchase_sessions p ON r.user_pseudo_id = p.user_pseudo_id 
        AND r.event_timestamp <= p.purchase_timestamp
),
first_touch_aggregates AS (
    SELECT 
        first_touch_medium AS channel,
        COUNT(DISTINCT user_pseudo_id) as first_touch_conversions
    FROM user_touchpoints
    GROUP BY first_touch_medium
),
last_touch_aggregates AS (
    SELECT 
        last_touch_medium AS channel,
        COUNT(DISTINCT user_pseudo_id) as last_touch_conversions
    FROM user_touchpoints
    GROUP BY last_touch_medium
)
SELECT 
    COALESCE(f.channel, l.channel) as marketing_channel,
    COALESCE(f.first_touch_conversions, 0) as first_touch_conversions,
    COALESCE(l.last_touch_conversions, 0) as last_touch_conversions,
    -- Variance measurement highlights top-of-funnel versus bottom-of-funnel channels
    (COALESCE(l.last_touch_conversions, 0) - COALESCE(f.first_touch_conversions, 0)) as attribution_delta
FROM first_touch_aggregates f
FULL OUTER JOIN last_touch_aggregates l ON f.channel = l.channel
ORDER BY last_touch_conversions DESC;