-- Run this against your ClickHouse Cloud service before running fetch_data.py.
-- Easiest path: paste into the ClickHouse Cloud SQL console in your browser.
-- (fetch_data.py only INSERTs — it assumes these tables already exist.)
--
-- If you already created `films` with release_date Date, migrate first:
--   ALTER TABLE films MODIFY COLUMN release_date Date32;

CREATE TABLE IF NOT EXISTS films
(
    film_id            UInt32,
    title              String,
    primary_genre      String,
    budget_usd         Float64,
    worldwide_revenue_usd Float64,
    release_date       Date32,   -- Date only supports 1970+; TMDb has pre-1970 hits
    release_quarter    String,      -- 'Q1'..'Q4', derived at load time
    runtime_minutes    UInt16,
    vote_average       Float32,
    popularity         Float32,
    overview           String
)
ENGINE = MergeTree
ORDER BY (primary_genre, film_id);

CREATE TABLE IF NOT EXISTS regional_performance
(
    film_id                    UInt32,
    region                     String,   -- 'North America','EMEA','APAC','LATAM'
    opening_weekend_revenue_usd Float64,
    total_regional_revenue_usd Float64,
    marketing_spend_usd        Float64,
    social_engagement_score    Float32,  -- synthetic, 0-100
    release_window             String    -- 'Q1'..'Q4'
)
ENGINE = MergeTree
ORDER BY (region, film_id);

-- Sanity checks to run after fetch_data.py:
-- SELECT count() FROM films;
-- SELECT count() FROM regional_performance;
-- SELECT primary_genre, count(), avg(worldwide_revenue_usd) FROM films GROUP BY primary_genre ORDER BY 2 DESC;
