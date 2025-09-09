-- Database verification queries for cron job system
-- Run these queries to verify database structure and cron job history

-- 1. Check database tables
SELECT table_name, table_type
FROM information_schema.tables 
WHERE table_schema = 'public'
ORDER BY table_name;

-- 2. Check symbols table structure
SELECT column_name, data_type, is_nullable
FROM information_schema.columns 
WHERE table_name = 'symbols'
ORDER BY ordinal_position;

-- 3. Count active symbols (what cron will process)
SELECT 
    COUNT(*) as total_symbols,
    COUNT(*) FILTER (WHERE is_active = true) as active_symbols,
    COUNT(*) FILTER (WHERE is_active = false) as inactive_symbols
FROM symbols;

-- 4. Check for any existing cron-related data
-- (This will fail if fetch_jobs table doesn't exist - that's expected)
-- SELECT COUNT(*) as cron_job_count
-- FROM fetch_jobs
-- WHERE created_by = 'cron_daily_update';

-- 5. Sample of active symbols
SELECT symbol, name, exchange, is_active, first_date, last_date
FROM symbols 
WHERE is_active = true
ORDER BY symbol
LIMIT 10;

-- 6. Check price data coverage
SELECT 
    COUNT(*) as total_price_records,
    COUNT(DISTINCT symbol) as symbols_with_data,
    MIN(date) as earliest_date,
    MAX(date) as latest_date
FROM prices;

-- 7. Recent price data activity
SELECT 
    symbol,
    COUNT(*) as record_count,
    MIN(date) as first_date,
    MAX(date) as last_date
FROM prices
WHERE date >= CURRENT_DATE - INTERVAL '30 days'
GROUP BY symbol
ORDER BY record_count DESC
LIMIT 10;
