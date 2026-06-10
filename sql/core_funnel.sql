-- Multi-Stage Linear Checkout Funnel Leakage & Conversion Efficiency View
CREATE OR REPLACE VIEW v_growth_funnel_leakage AS
WITH flattened_events AS (
    SELECT
        user_pseudo_id,
        session_id,
        traffic_source_medium AS acquisition_channel,
        device_category,
        event_name,
        event_timestamp,
        ROW_NUMBER() OVER(PARTITION BY session_id ORDER BY event_timestamp) as event_seq
    FROM raw_ga4_events
),
session_milestones AS (
    SELECT
        session_id,
        acquisition_channel,
        device_category,
        MAX(CASE WHEN event_name = 'session_start' THEN 1 ELSE 0 END) as stage_1_start,
        MAX(CASE WHEN event_name = 'view_item' THEN 1 ELSE 0 END) as stage_2_view,
        MAX(CASE WHEN event_name = 'add_to_cart' THEN 1 ELSE 0 END) as stage_3_cart,
        MAX(CASE WHEN event_name = 'begin_checkout' THEN 1 ELSE 0 END) as stage_4_checkout,
        MAX(CASE WHEN event_name = 'purchase' THEN 1 ELSE 0 END) as stage_5_purchase
    FROM flattened_events
    GROUP BY session_id, acquisition_channel, device_category
)
SELECT
    acquisition_channel,
    device_category,
    COUNT(DISTINCT session_id) as total_sessions,
    SUM(stage_1_start) as base_traffic,
    SUM(stage_2_view) as product_views,
    SUM(stage_3_cart) as cart_additions,
    SUM(stage_4_checkout) as checkout_initiations,
    SUM(stage_5_purchase) as realized_purchases,
    
    -- Inter-stage micro-conversion drop-off calculations 
    ROUND((1 - (SUM(stage_2_view)::NUMERIC / NULLIF(SUM(stage_1_start), 0))) * 100, 2) as landing_to_view_drop_pct,
    ROUND((1 - (SUM(stage_3_cart)::NUMERIC / NULLIF(SUM(stage_2_view), 0))) * 100, 2) as product_to_cart_drop_pct,
    ROUND((1 - (SUM(stage_4_checkout)::NUMERIC / NULLIF(SUM(stage_3_cart), 0))) * 100, 2) as cart_to_checkout_drop_pct,
    ROUND((1 - (SUM(stage_5_purchase)::NUMERIC / NULLIF(SUM(stage_4_checkout), 0))) * 100, 2) as checkout_to_purchase_drop_pct,
    
    -- Macro Conversion Efficiency
    ROUND((SUM(stage_5_purchase)::NUMERIC / NULLIF(SUM(stage_1_start), 0)) * 100, 3) as macro_conversion_rate_pct
FROM session_milestones
GROUP BY acquisition_channel, device_category;