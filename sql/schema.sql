-- DDL Schema definition for Google Analytics 4 Event Streams
DROP TABLE IF EXISTS raw_ga4_events CASCADE;

CREATE TABLE raw_ga4_events (
    event_id SERIAL PRIMARY KEY,
    user_pseudo_id VARCHAR(100) NOT NULL,
    session_id BIGINT NOT NULL,
    event_name VARCHAR(50) NOT NULL,
    event_timestamp TIMESTAMPTZ NOT NULL,
    traffic_source_medium VARCHAR(50) DEFAULT 'direct',
    device_category VARCHAR(30) DEFAULT 'desktop',
    geo_country VARCHAR(50) DEFAULT 'unknown',
    page_location TEXT
);

-- B-Tree Performance Index Strategy for Sessionization and Funnel Sorting
CREATE INDEX idx_ga4_session_events ON raw_ga4_events(session_id, event_timestamp);
CREATE INDEX idx_ga4_user_mapping ON raw_ga4_events(user_pseudo_id);
CREATE INDEX idx_ga4_event_lookup ON raw_ga4_events(event_name);
CREATE INDEX idx_ga4_traffic_medium ON raw_ga4_events(traffic_source_medium);