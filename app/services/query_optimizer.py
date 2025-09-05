"""Query optimization utilities for performance enhancement."""

from typing import Dict, Any, List, Optional
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


async def analyze_query_performance(
    session: AsyncSession, 
    query: str, 
    params: Dict[str, Any]
) -> Dict[str, Any]:
    """
    Analyze query performance using EXPLAIN ANALYZE.
    
    Args:
        session: Database session
        query: SQL query to analyze
        params: Query parameters
        
    Returns:
        Query performance analysis results
    """
    explain_query = f"EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON) {query}"
    
    try:
        result = await session.execute(text(explain_query), params)
        explain_result = result.scalar()
        
        # Extract key performance metrics
        plan = explain_result[0]['Plan']
        
        performance_info = {
            'total_cost': plan.get('Total Cost', 0),
            'actual_total_time': plan.get('Actual Total Time', 0),
            'actual_rows': plan.get('Actual Rows', 0),
            'planning_time': explain_result[0].get('Planning Time', 0),
            'execution_time': explain_result[0].get('Execution Time', 0),
            'node_type': plan.get('Node Type', ''),
            'startup_cost': plan.get('Startup Cost', 0),
            'shared_hit_blocks': plan.get('Shared Hit Blocks', 0),
            'shared_read_blocks': plan.get('Shared Read Blocks', 0),
        }
        
        return performance_info
        
    except Exception as e:
        return {'error': str(e), 'query': query}


def get_optimized_coverage_query(use_materialized_view: bool = False) -> str:
    """
    Get optimized coverage query with performance enhancements.
    
    Args:
        use_materialized_view: Whether to use materialized view if available
        
    Returns:
        Optimized SQL query string
    """
    if use_materialized_view:
        # Use materialized view for better performance
        return """
        SELECT 
            symbol,
            name,
            exchange,
            currency,
            is_active,
            data_start,
            data_end,
            data_days,
            row_count,
            last_updated,
            has_gaps
        FROM mv_symbol_coverage
        WHERE 1=1
        """
    
    # Optimized regular query with CTEs and improved joins
    return """
    WITH price_stats AS (
        SELECT 
            symbol,
            MIN(date) AS data_start,
            MAX(date) AS data_end,
            COUNT(DISTINCT date) AS data_days,
            COUNT(*) AS row_count,
            MAX(last_updated) AS last_updated,
            -- More efficient gap detection
            COUNT(*) < (MAX(date) - MIN(date) + 1) * 0.8 AS has_gaps
        FROM prices
        WHERE date >= CURRENT_DATE - INTERVAL '5 years'  -- Limit to recent data
        GROUP BY symbol
    ),
    symbol_with_stats AS (
        SELECT 
            s.symbol,
            s.name,
            s.exchange,
            s.currency,
            s.is_active,
            ps.data_start,
            ps.data_end,
            COALESCE(ps.data_days, 0) AS data_days,
            COALESCE(ps.row_count, 0) AS row_count,
            ps.last_updated,
            COALESCE(ps.has_gaps, false) AS has_gaps
        FROM symbols s
        LEFT JOIN price_stats ps USING (symbol)
    )
    SELECT * FROM symbol_with_stats
    WHERE 1=1
    """


def get_batch_upsert_query() -> str:
    """
    Get optimized batch upsert query for price data.
    
    Returns:
        Optimized batch upsert SQL query
    """
    return """
    INSERT INTO prices (symbol, date, open, high, low, close, volume, last_updated)
    VALUES %(values)s
    ON CONFLICT (symbol, date) 
    DO UPDATE SET
        open = EXCLUDED.open,
        high = EXCLUDED.high,
        low = EXCLUDED.low,
        close = EXCLUDED.close,
        volume = EXCLUDED.volume,
        last_updated = EXCLUDED.last_updated
    WHERE prices.last_updated < EXCLUDED.last_updated OR %(force_update)s
    """


def get_optimized_price_query() -> str:
    """
    Get optimized price data query with efficient filtering.
    
    Returns:
        Optimized price query with proper indexing hints
    """
    return """
    SELECT /*+ INDEX(prices, idx_prices_symbol_date) */
        symbol,
        date,
        open,
        high,
        low,
        close,
        volume,
        last_updated
    FROM prices
    WHERE 1=1
    ORDER BY symbol, date
    """


async def create_query_performance_log(
    session: AsyncSession,
    query_name: str,
    execution_time_ms: int,
    row_count: int,
    params: Optional[Dict[str, Any]] = None
) -> None:
    """
    Log query performance for monitoring and optimization.
    
    Args:
        session: Database session
        query_name: Name/identifier of the query
        execution_time_ms: Execution time in milliseconds
        row_count: Number of rows returned/affected
        params: Query parameters (optional)
    """
    try:
        log_query = """
        INSERT INTO query_performance_log 
        (query_name, execution_time_ms, row_count, params, executed_at)
        VALUES (:query_name, :execution_time_ms, :row_count, :params, NOW())
        """
        
        await session.execute(text(log_query), {
            'query_name': query_name,
            'execution_time_ms': execution_time_ms,
            'row_count': row_count,
            'params': str(params) if params else None
        })
        
    except Exception:
        # Silently fail if performance log table doesn't exist
        pass


class QueryOptimizer:
    """Query optimization helper class."""
    
    def __init__(self, session: AsyncSession):
        self.session = session
        self._query_cache = {}
    
    async def get_table_stats(self, table_name: str) -> Dict[str, Any]:
        """Get table statistics for optimization decisions."""
        stats_query = """
        SELECT 
            schemaname,
            tablename,
            n_tup_ins,
            n_tup_upd,
            n_tup_del,
            n_live_tup,
            n_dead_tup,
            last_vacuum,
            last_autovacuum,
            last_analyze,
            last_autoanalyze
        FROM pg_stat_user_tables 
        WHERE tablename = :table_name
        """
        
        result = await self.session.execute(text(stats_query), {'table_name': table_name})
        row = result.first()
        
        if row:
            return {
                'live_tuples': row.n_live_tup,
                'dead_tuples': row.n_dead_tup,
                'last_vacuum': row.last_vacuum,
                'last_analyze': row.last_analyze,
                'needs_vacuum': row.n_dead_tup > row.n_live_tup * 0.1 if row.n_live_tup else False
            }
        return {}
    
    async def suggest_indexes(self, table_name: str) -> List[str]:
        """Suggest missing indexes based on query patterns."""
        # This would analyze query logs and suggest indexes
        # For now, return common index suggestions
        suggestions = []
        
        if table_name == 'prices':
            stats = await self.get_table_stats('prices')
            if stats.get('live_tuples', 0) > 100000:
                suggestions.extend([
                    "CREATE INDEX CONCURRENTLY idx_prices_date_symbol ON prices (date, symbol);",
                    "CREATE INDEX CONCURRENTLY idx_prices_last_updated ON prices (last_updated);",
                    "CREATE INDEX CONCURRENTLY idx_prices_symbol_date_desc ON prices (symbol, date DESC);"
                ])
        
        elif table_name == 'symbols':
            suggestions.append(
                "CREATE INDEX CONCURRENTLY idx_symbols_active ON symbols (is_active) WHERE is_active = true;"
            )
        
        return suggestions
    
    def cache_query_plan(self, query_hash: str, plan: Dict[str, Any]) -> None:
        """Cache query execution plan for reuse."""
        self._query_cache[query_hash] = plan
    
    def get_cached_plan(self, query_hash: str) -> Optional[Dict[str, Any]]:
        """Get cached query execution plan."""
        return self._query_cache.get(query_hash)


__all__ = [
    "analyze_query_performance",
    "get_optimized_coverage_query", 
    "get_batch_upsert_query",
    "get_optimized_price_query",
    "create_query_performance_log",
    "QueryOptimizer"
]
