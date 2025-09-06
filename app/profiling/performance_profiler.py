"""
Oldest Data Fallback Performance Profiling Tool

This module provides comprehensive performance analysis and bottleneck identification
for the oldest data fallback functionality.
"""

import asyncio
import time
import statistics
from datetime import date, datetime, timedelta
from typing import Dict, List, Optional, Sequence, Tuple
from dataclasses import dataclass, field
from contextlib import asynccontextmanager
import cProfile
import pstats
from io import StringIO
from sqlalchemy.ext.asyncio import AsyncSession
from unittest.mock import AsyncMock

from app.db import queries


@dataclass
class PerformanceProfile:
    """Performance profile for a single operation"""
    operation_name: str
    duration_ms: float
    cpu_time_ms: Optional[float] = None
    memory_usage_mb: Optional[float] = None
    db_queries: int = 0
    rows_processed: int = 0
    symbols_processed: int = 0
    fallback_occurred: bool = False
    adjustment_days: int = 0
    timestamp: datetime = field(default_factory=datetime.now)
    
    @property
    def throughput_rows_per_second(self) -> float:
        """Calculate rows processed per second"""
        if self.duration_ms == 0:
            return 0
        return (self.rows_processed * 1000) / self.duration_ms
    
    @property
    def efficiency_score(self) -> float:
        """Calculate efficiency score (0-100)"""
        # Base score on throughput and query efficiency
        base_score = min(self.throughput_rows_per_second / 1000 * 100, 50)  # Up to 50 points
        
        # Query efficiency (fewer queries per symbol is better)
        if self.symbols_processed > 0:
            queries_per_symbol = self.db_queries / self.symbols_processed
            query_efficiency = max(0, 30 - queries_per_symbol * 5)  # Up to 30 points
        else:
            query_efficiency = 0
        
        # Duration penalty for slow operations
        duration_penalty = max(0, 20 - (self.duration_ms / 1000) * 5)  # Up to 20 points
        
        return min(100, base_score + query_efficiency + duration_penalty)


@dataclass 
class ProfilerResults:
    """Aggregated profiling results"""
    profiles: List[PerformanceProfile]
    total_duration_ms: float
    
    @property
    def summary_stats(self) -> Dict:
        """Calculate summary statistics"""
        if not self.profiles:
            return {}
        
        durations = [p.duration_ms for p in self.profiles]
        rows = [p.rows_processed for p in self.profiles]
        queries = [p.db_queries for p in self.profiles]
        
        return {
            "total_operations": len(self.profiles),
            "total_duration_ms": self.total_duration_ms,
            "avg_duration_ms": statistics.mean(durations),
            "median_duration_ms": statistics.median(durations),
            "p95_duration_ms": statistics.quantiles(durations, n=20)[18] if len(durations) >= 20 else max(durations),
            "total_rows_processed": sum(rows),
            "total_db_queries": sum(queries),
            "avg_efficiency_score": statistics.mean([p.efficiency_score for p in self.profiles]),
            "fallback_rate": len([p for p in self.profiles if p.fallback_occurred]) / len(self.profiles) * 100,
            "operations_per_second": len(self.profiles) / (self.total_duration_ms / 1000) if self.total_duration_ms > 0 else 0
        }
    
    def get_bottlenecks(self) -> List[str]:
        """Identify performance bottlenecks"""
        bottlenecks = []
        stats = self.summary_stats
        
        if stats.get("avg_duration_ms", 0) > 1000:
            bottlenecks.append("High average response time (>1000ms)")
        
        if stats.get("p95_duration_ms", 0) > 5000:
            bottlenecks.append("High 95th percentile response time (>5000ms)")
        
        if stats.get("avg_efficiency_score", 100) < 70:
            bottlenecks.append("Low efficiency score (<70)")
        
        if stats.get("total_db_queries", 0) / stats.get("total_operations", 1) > 10:
            bottlenecks.append("High database query count per operation")
        
        if stats.get("operations_per_second", 0) < 10:
            bottlenecks.append("Low throughput (<10 operations/second)")
        
        return bottlenecks


class FallbackProfiler:
    """Performance profiler for fallback operations"""
    
    def __init__(self):
        self.profiles: List[PerformanceProfile] = []
        self.session_start = datetime.now()
    
    @asynccontextmanager
    async def profile_operation(
        self,
        operation_name: str,
        symbols: Sequence[str],
        enable_cpu_profiling: bool = False
    ):
        """Context manager for profiling a single operation"""
        start_time = time.time()
        cpu_profiler = None
        
        if enable_cpu_profiling:
            cpu_profiler = cProfile.Profile()
            cpu_profiler.enable()
        
        class OperationContext:
            def __init__(self):
                self.db_queries = 0
                self.rows_processed = 0
                self.fallback_occurred = False
                self.adjustment_days = 0
            
            def record_db_query(self):
                self.db_queries += 1
            
            def record_rows(self, count: int):
                self.rows_processed += count
            
            def record_fallback(self, adjustment_days: int):
                self.fallback_occurred = True
                self.adjustment_days = adjustment_days
        
        context = OperationContext()
        
        try:
            yield context
        finally:
            end_time = time.time()
            duration_ms = (end_time - start_time) * 1000
            
            cpu_time_ms = None
            if cpu_profiler:
                cpu_profiler.disable()
                # Calculate CPU time from profile stats
                s = StringIO()
                ps = pstats.Stats(cpu_profiler, stream=s)
                ps.sort_stats('cumulative')
                cpu_time_ms = ps.total_tt * 1000  # Convert to milliseconds
            
            profile = PerformanceProfile(
                operation_name=operation_name,
                duration_ms=duration_ms,
                cpu_time_ms=cpu_time_ms,
                db_queries=context.db_queries,
                rows_processed=context.rows_processed,
                symbols_processed=len(symbols),
                fallback_occurred=context.fallback_occurred,
                adjustment_days=context.adjustment_days
            )
            
            self.profiles.append(profile)
    
    async def benchmark_fallback_scenarios(
        self,
        session: AsyncSession,
        test_scenarios: List[Dict]
    ) -> ProfilerResults:
        """
        Benchmark multiple fallback scenarios
        
        Args:
            session: Database session
            test_scenarios: List of test cases with 'symbols', 'date_from', 'date_to', 'name'
        """
        benchmark_start = time.time()
        
        for scenario in test_scenarios:
            async with self.profile_operation(
                operation_name=scenario["name"],
                symbols=scenario["symbols"],
                enable_cpu_profiling=True
            ) as context:
                
                # Execute the price query
                try:
                    result = await queries.get_prices_resolved(
                        session=session,
                        symbols=scenario["symbols"],
                        date_from=scenario["date_from"],
                        date_to=scenario["date_to"]
                    )
                    
                    context.record_rows(len(result))
                    # Assume one query per symbol for get_prices_resolved
                    context.record_db_query()  # For each symbol
                    
                    # Check if fallback occurred (simplified heuristic)
                    if result and result[0]["date"] > scenario["date_from"]:
                        adjustment_days = (result[0]["date"] - scenario["date_from"]).days
                        context.record_fallback(adjustment_days)
                    
                except Exception as e:
                    # Record the error but continue benchmarking
                    context.record_rows(0)
                    print(f"Error in scenario {scenario['name']}: {e}")
        
        total_duration = (time.time() - benchmark_start) * 1000
        return ProfilerResults(self.profiles.copy(), total_duration)
    
    async def stress_test_fallback(
        self,
        session: AsyncSession,
        symbols: List[str],
        concurrent_requests: int = 10,
        iterations: int = 100
    ) -> ProfilerResults:
        """
        Stress test the fallback functionality
        
        Args:
            session: Database session
            symbols: Symbols to test
            concurrent_requests: Number of concurrent requests
            iterations: Number of iterations per concurrent request
        """
        stress_start = time.time()
        
        async def single_stress_iteration(iteration_id: int):
            """Single stress test iteration"""
            # Vary date ranges to trigger different fallback scenarios
            base_date = date(2019, 1, 1)
            date_from = base_date + timedelta(days=(iteration_id % 365))
            date_to = date_from + timedelta(days=365)
            
            async with self.profile_operation(
                operation_name=f"stress_test_iteration_{iteration_id}",
                symbols=symbols[:3],  # Limit symbols for stress test
                enable_cpu_profiling=False  # Disable for performance
            ) as context:
                try:
                    result = await queries.get_prices_resolved(
                        session=session,
                        symbols=symbols[:3],
                        date_from=date_from,
                        date_to=date_to
                    )
                    
                    context.record_rows(len(result))
                    context.record_db_query()
                    
                    # Simple fallback detection
                    if result and result[0]["date"] > date_from:
                        context.record_fallback((result[0]["date"] - date_from).days)
                        
                except Exception:
                    context.record_rows(0)
        
        # Create concurrent tasks
        tasks = []
        for batch in range(concurrent_requests):
            batch_tasks = [
                single_stress_iteration(batch * iterations + i)
                for i in range(iterations)
            ]
            tasks.extend(batch_tasks)
        
        # Execute all tasks concurrently
        await asyncio.gather(*tasks, return_exceptions=True)
        
        total_duration = (time.time() - stress_start) * 1000
        return ProfilerResults(self.profiles.copy(), total_duration)
    
    def generate_performance_report(self, results: ProfilerResults) -> str:
        """Generate a comprehensive performance report"""
        stats = results.summary_stats
        bottlenecks = results.get_bottlenecks()
        
        report_lines = [
            "=== Oldest Data Fallback Performance Report ===",
            "",
            f"Report generated: {datetime.now().isoformat()}",
            f"Total operations analyzed: {stats.get('total_operations', 0)}",
            f"Total duration: {stats.get('total_duration_ms', 0):.2f}ms",
            "",
            "=== Performance Metrics ===",
            f"Average response time: {stats.get('avg_duration_ms', 0):.2f}ms",
            f"Median response time: {stats.get('median_duration_ms', 0):.2f}ms", 
            f"95th percentile response time: {stats.get('p95_duration_ms', 0):.2f}ms",
            f"Operations per second: {stats.get('operations_per_second', 0):.2f}",
            f"Total rows processed: {stats.get('total_rows_processed', 0)}",
            f"Total database queries: {stats.get('total_db_queries', 0)}",
            f"Average efficiency score: {stats.get('avg_efficiency_score', 0):.2f}/100",
            "",
            f"=== Fallback Analysis ===",
            f"Fallback occurrence rate: {stats.get('fallback_rate', 0):.2f}%",
            f"Operations with fallback: {len([p for p in results.profiles if p.fallback_occurred])}",
            ""
        ]
        
        if bottlenecks:
            report_lines.extend([
                "=== Performance Bottlenecks Identified ===",
                *[f"⚠️  {bottleneck}" for bottleneck in bottlenecks],
                ""
            ])
        else:
            report_lines.append("✅ No significant performance bottlenecks identified")
            report_lines.append("")
        
        # Top 5 slowest operations
        slowest_ops = sorted(results.profiles, key=lambda p: p.duration_ms, reverse=True)[:5]
        if slowest_ops:
            report_lines.extend([
                "=== Slowest Operations ===",
                *[f"{op.operation_name}: {op.duration_ms:.2f}ms ({op.rows_processed} rows)" 
                  for op in slowest_ops],
                ""
            ])
        
        # Top 5 most efficient operations
        efficient_ops = sorted(results.profiles, key=lambda p: p.efficiency_score, reverse=True)[:5]
        if efficient_ops:
            report_lines.extend([
                "=== Most Efficient Operations ===",
                *[f"{op.operation_name}: {op.efficiency_score:.1f}/100 score ({op.throughput_rows_per_second:.1f} rows/sec)" 
                  for op in efficient_ops],
                ""
            ])
        
        report_lines.extend([
            "=== Recommendations ===",
            "Based on the performance analysis:",
            ""
        ])
        
        # Generate recommendations based on bottlenecks
        recommendations = self._generate_recommendations(bottlenecks, stats)
        report_lines.extend(recommendations)
        
        return "\n".join(report_lines)
    
    def _generate_recommendations(self, bottlenecks: List[str], stats: Dict) -> List[str]:
        """Generate performance improvement recommendations"""
        recommendations = []
        
        if "High average response time" in str(bottlenecks):
            recommendations.extend([
                "🔧 Consider implementing response caching for frequently requested symbols",
                "🔧 Optimize database queries by adding appropriate indexes",
                "🔧 Consider connection pooling optimization"
            ])
        
        if "High database query count" in str(bottlenecks):
            recommendations.extend([
                "🔧 Implement batch query optimization for multiple symbols",
                "🔧 Consider using prepared statements for repeated queries",
                "🔧 Review query patterns for potential consolidation"
            ])
        
        if "Low throughput" in str(bottlenecks):
            recommendations.extend([
                "🔧 Consider parallel processing for multiple symbol requests",
                "🔧 Implement async request batching",
                "🔧 Review application server resource allocation"
            ])
        
        if stats.get("fallback_rate", 0) > 50:
            recommendations.extend([
                "🔧 High fallback rate detected - consider client education about date ranges",
                "🔧 Consider implementing oldest date caching to reduce lookup overhead"
            ])
        
        if not recommendations:
            recommendations.append("✅ Performance appears optimal based on current metrics")
        
        return recommendations


# Convenience function for quick profiling
async def quick_profile_fallback(
    session: AsyncSession,
    symbols: List[str] = ["AAPL", "MSFT", "GOOGL"],
    include_stress_test: bool = False
) -> str:
    """
    Quick profiling function for development and testing
    
    Returns a formatted performance report
    """
    profiler = FallbackProfiler()
    
    # Define test scenarios
    test_scenarios = [
        {
            "name": "normal_range",
            "symbols": symbols[:1],
            "date_from": date(2021, 1, 1),
            "date_to": date(2021, 12, 31)
        },
        {
            "name": "fallback_partial",
            "symbols": symbols[:1], 
            "date_from": date(2019, 1, 1),  # Before oldest
            "date_to": date(2021, 12, 31)
        },
        {
            "name": "fallback_empty",
            "symbols": symbols[:1],
            "date_from": date(2018, 1, 1),  # Way before oldest
            "date_to": date(2018, 12, 31)
        },
        {
            "name": "multi_symbol_mixed",
            "symbols": symbols,
            "date_from": date(2019, 1, 1),
            "date_to": date(2021, 12, 31)
        }
    ]
    
    # Run benchmark
    results = await profiler.benchmark_fallback_scenarios(session, test_scenarios)
    
    # Optional stress test
    if include_stress_test:
        stress_results = await profiler.stress_test_fallback(
            session, symbols, concurrent_requests=5, iterations=20
        )
        # Combine results
        results.profiles.extend(stress_results.profiles)
        results.total_duration_ms += stress_results.total_duration_ms
    
    return profiler.generate_performance_report(results)
