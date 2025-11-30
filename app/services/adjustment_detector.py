"""
Price adjustment detection service (TID-ADJ-002 - TID-ADJ-008).

This module provides functionality to detect when historical price data
needs to be refreshed due to corporate actions like stock splits,
dividends, and spinoffs.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal, ROUND_HALF_UP
from enum import Enum
from typing import Any, List, Optional, Tuple

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.queries.adjustments import get_adjustment_sample_data, get_symbols_for_scan
from app.services.adjustment_fixer import AdjustmentFixer


class AdjustmentType(Enum):
    """Type of corporate action that caused price adjustment."""
    
    STOCK_SPLIT = "stock_split"
    REVERSE_SPLIT = "reverse_split"
    DIVIDEND = "dividend"
    SPECIAL_DIVIDEND = "special_dividend"
    CAPITAL_GAIN = "capital_gain"
    SPINOFF = "spinoff"
    UNKNOWN = "unknown"


class AdjustmentSeverity(Enum):
    """Severity level of detected adjustment.
    
    Determines the urgency of refreshing the affected data.
    """
    
    CRITICAL = "critical"  # Immediate action required (splits, spinoffs)
    HIGH = "high"          # Early action recommended (special dividends)
    NORMAL = "normal"      # Regular action (dividend accumulation)
    LOW = "low"            # Low priority (minor discrepancies)


@dataclass
class DetectionThresholds:
    """Configuration thresholds for adjustment detection.
    
    Attributes:
        float_noise_pct: Percentage below which differences are considered
            floating-point noise and ignored (default: 0.0001%).
        min_detection_pct: Minimum percentage difference to trigger detection
            (default: 0.001%).
        split_threshold_pct: Percentage difference indicating a likely stock split
            (default: 10.0%).
        special_div_threshold_pct: Percentage difference indicating special dividend
            (default: 2.0%).
        spinoff_threshold_pct: Percentage difference indicating possible spinoff
            (default: 15.0%).
        sample_points: Number of historical price points to sample for comparison
            (default: 10).
        min_data_age_days: Minimum age of data in days before checking
            (default: 7 days, reduced from 60 to catch recent splits).
        check_full_history: Whether to check entire history including recent data
            (default: True for comprehensive split detection).
    """
    
    float_noise_pct: float = 0.0001
    min_detection_pct: float = 0.001
    split_threshold_pct: float = 10.0
    special_div_threshold_pct: float = 2.0
    spinoff_threshold_pct: float = 15.0
    sample_points: int = 10
    min_data_age_days: int = 7  # Reduced from 60 to catch recent splits
    check_full_history: bool = True  # Check entire history for split detection


@dataclass
class AdjustmentEvent:
    """Represents a detected adjustment event.
    
    Attributes:
        symbol: The ticker symbol.
        event_type: Type of detected adjustment.
        severity: Urgency level of the adjustment.
        pct_difference: Percentage difference between DB and yfinance prices.
        check_date: Date of the price point that was checked.
        db_price: Price stored in the database.
        yf_adjusted_price: Current adjusted price from yfinance.
        details: Additional event-specific details.
        recommendation: Suggested action to take.
    """
    
    symbol: str
    event_type: AdjustmentType
    severity: AdjustmentSeverity
    pct_difference: float
    check_date: str  # ISO format date string
    db_price: float
    yf_adjusted_price: float
    details: dict[str, Any] = field(default_factory=dict)
    recommendation: str = ""
    
    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary representation."""
        return {
            "symbol": self.symbol,
            "event_type": self.event_type.value,
            "severity": self.severity.value,
            "pct_difference": self.pct_difference,
            "check_date": self.check_date,
            "db_price": self.db_price,
            "yf_adjusted_price": self.yf_adjusted_price,
            "details": self.details,
            "recommendation": self.recommendation,
        }


@dataclass
class ScanResult:
    """Result of scanning a symbol for adjustments.
    
    Attributes:
        symbol: The ticker symbol that was scanned.
        needs_refresh: Whether the symbol's data needs to be refreshed.
        events: List of detected adjustment events.
        max_pct_diff: Maximum percentage difference found.
        error: Error message if scan failed, None otherwise.
    """
    
    symbol: str
    needs_refresh: bool = False
    events: list[AdjustmentEvent] = field(default_factory=list)
    max_pct_diff: float = 0.0
    error: str | None = None
    
    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary representation."""
        return {
            "symbol": self.symbol,
            "needs_refresh": self.needs_refresh,
            "events": [e.to_dict() for e in self.events],
            "max_pct_diff": self.max_pct_diff,
            "error": self.error,
        }


class PrecisionAdjustmentDetector:
    """High-precision price adjustment detector service.
    
    Compares database prices with current yfinance adjusted prices
    to detect corporate actions that require data refresh.
    """
    
    def __init__(self, thresholds: Optional[DetectionThresholds] = None):
        """Initialize the detector with optional custom thresholds.
        
        Args:
            thresholds: Custom detection thresholds. If None, defaults are used.
        """
        self.thresholds = thresholds or DetectionThresholds()
    
    def _compare_with_precision(
        self,
        db_price: float,
        yf_price: float,
    ) -> Tuple[float, bool]:
        """Compare two prices with high precision using Decimal arithmetic.
        
        Calculates the percentage difference between database price and
        yfinance adjusted price, accounting for floating-point noise.
        
        Args:
            db_price: Price stored in the database.
            yf_price: Current adjusted price from yfinance.
            
        Returns:
            Tuple of (percentage_difference, is_significant).
            - percentage_difference: Absolute percentage difference.
            - is_significant: True if difference exceeds detection threshold.
        """
        # Handle zero prices - no meaningful comparison possible
        if db_price == 0 or yf_price == 0:
            return 0.0, False
        
        # Use Decimal for high precision calculation
        db_dec = Decimal(str(db_price))
        yf_dec = Decimal(str(yf_price))
        
        # Calculate absolute difference
        diff = abs(db_dec - yf_dec)
        
        # Calculate percentage difference relative to db_price
        pct_diff = (diff / db_dec) * Decimal("100")
        pct_diff_float = float(pct_diff.quantize(Decimal("0.000001"), rounding=ROUND_HALF_UP))
        
        # Check if difference is significant (above noise and above minimum threshold)
        is_significant = (
            pct_diff_float >= self.thresholds.float_noise_pct and
            pct_diff_float >= self.thresholds.min_detection_pct
        )
        
        return pct_diff_float, is_significant

    def _classify_event(
        self,
        pct_diff: float,
        ticker_data: dict[str, Any],
        check_date: str,
    ) -> Tuple[AdjustmentType, AdjustmentSeverity, dict[str, Any]]:
        """Classify the type of corporate action based on price difference and history.
        
        Uses yfinance ticker data (splits, dividends, capital_gains) to determine
        the most likely cause of the price discrepancy.
        
        Args:
            pct_diff: Percentage difference between DB and yfinance prices.
            ticker_data: Dictionary containing 'splits', 'dividends', and optionally
                        'capital_gains' pandas Series from yfinance ticker.
            check_date: ISO format date string of the price point being checked.
            
        Returns:
            Tuple of (AdjustmentType, AdjustmentSeverity, details_dict).
        """
        details: dict[str, Any] = {}
        
        splits = ticker_data.get("splits")
        dividends = ticker_data.get("dividends")
        capital_gains = ticker_data.get("capital_gains")
        
        # Check for stock split (large difference + splits history)
        if pct_diff >= self.thresholds.split_threshold_pct:
            if splits is not None and len(splits) > 0:
                # Filter splits after check_date
                recent_splits = splits[splits.index > check_date]
                if not recent_splits.empty:
                    factor = float(recent_splits.prod())
                    details["splits"] = [
                        {"date": str(idx.date()), "ratio": float(val)}
                        for idx, val in recent_splits.items()
                    ]
                    details["cumulative_factor"] = factor
                    
                    # Reverse split if factor < 1
                    if factor < 1:
                        return AdjustmentType.REVERSE_SPLIT, AdjustmentSeverity.HIGH, details
                    return AdjustmentType.STOCK_SPLIT, AdjustmentSeverity.CRITICAL, details
            
            # Large difference but no splits - possible spinoff
            if pct_diff >= self.thresholds.spinoff_threshold_pct:
                details["note"] = "Possible spinoff or data quality issue"
                return AdjustmentType.SPINOFF, AdjustmentSeverity.CRITICAL, details
        
        # Check for dividends
        if dividends is not None and len(dividends) > 0:
            recent_divs = dividends[dividends.index > check_date]
            if not recent_divs.empty:
                details["dividend_count"] = len(recent_divs)
                details["total_dividends"] = float(recent_divs.sum())
                
                # Check for special dividend (large single dividend)
                if pct_diff >= self.thresholds.special_div_threshold_pct:
                    max_div = float(recent_divs.max())
                    mean_div = float(recent_divs.mean())
                    if max_div > mean_div * 2:
                        details["special_dividend"] = max_div
                        return AdjustmentType.SPECIAL_DIVIDEND, AdjustmentSeverity.HIGH, details
                
                return AdjustmentType.DIVIDEND, AdjustmentSeverity.NORMAL, details
        
        # Check for capital gains (ETFs)
        if capital_gains is not None and len(capital_gains) > 0:
            recent_gains = capital_gains[capital_gains.index > check_date]
            if not recent_gains.empty:
                details["capital_gains"] = float(recent_gains.sum())
                return AdjustmentType.CAPITAL_GAIN, AdjustmentSeverity.NORMAL, details
        
        # Unknown cause
        details["note"] = "Could not determine cause"
        return AdjustmentType.UNKNOWN, AdjustmentSeverity.LOW, details

    async def get_sample_prices(
        self,
        session: AsyncSession,
        symbol: str,
    ) -> List[Tuple[date, float]]:
        """Get sample price points from DB for comparison.
        
        Retrieves evenly-spaced price points from the database for a symbol.
        When check_full_history is True, samples from entire history to catch
        recent splits. Otherwise, excludes recent data within min_data_age_days.
        
        Args:
            session: Async database session.
            symbol: Ticker symbol to get prices for.
            
        Returns:
            List of (date, close_price) tuples. Returns empty list if
            insufficient data is available.
        """
        # Determine date range based on check_full_history setting
        if self.thresholds.check_full_history:
            # Check entire history - only exclude very recent data (7 days)
            # to avoid in-flight data issues
            min_age = date.today() - timedelta(days=self.thresholds.min_data_age_days)
        else:
            # Legacy behavior - exclude recent refetch period
            min_age = date.today() - timedelta(days=self.thresholds.min_data_age_days)
        
        # Use query helper
        all_rows = await get_adjustment_sample_data(session, symbol, min_age)
        
        # Need at least 2 data points for meaningful comparison
        if len(all_rows) < 2:
            return []
        
        # Enhanced sampling: ensure we cover different time periods
        # to catch splits that happened at any point
        total_points = len(all_rows)
        sample_count = min(self.thresholds.sample_points, total_points)
        
        # Sample evenly spaced points across entire history
        step = max(1, total_points // sample_count)
        
        # Get indices at regular intervals
        indices = list(range(0, total_points, step))[:sample_count]
        
        # Always include the last point (most recent before cutoff)
        if (total_points - 1) not in indices:
            indices.append(total_points - 1)
        
        # Always include the first point (oldest)
        if 0 not in indices:
            indices.insert(0, 0)
        
        # Also include some points from the middle-recent period
        # to catch splits in the gap zone
        if total_points > 20:
            # Add samples from last 90 days of available data
            recent_start = max(0, total_points - 90)
            if recent_start not in indices:
                indices.append(recent_start)
            mid_recent = (recent_start + total_points) // 2
            if mid_recent not in indices:
                indices.append(mid_recent)
        
        # Sort indices and remove duplicates
        indices = sorted(set(indices))
        
        return [(all_rows[i][0], float(all_rows[i][1])) for i in indices]

    async def detect_adjustments(
        self,
        session: AsyncSession,
        symbol: str,
    ) -> ScanResult:
        """Detect price adjustments needed for a single symbol.
        
        Compares database prices with current yfinance adjusted prices
        at multiple sample points to detect corporate actions.
        
        Args:
            session: Async database session.
            symbol: Ticker symbol to check.
            
        Returns:
            ScanResult containing detected events and recommendations.
        """
        import yfinance as yf
        
        result = ScanResult(symbol=symbol)
        
        try:
            # Get sample prices from database
            samples = await self.get_sample_prices(session, symbol)
            
            if len(samples) < 2:
                result.error = "Insufficient historical data (need at least 2 points older than {} days)".format(
                    self.thresholds.min_data_age_days
                )
                return result
            
            # Fetch current adjusted prices from yfinance
            ticker = yf.Ticker(symbol)
            
            # Get history covering all sample dates
            start_date = samples[0][0].strftime('%Y-%m-%d')
            end_date = (samples[-1][0] + timedelta(days=1)).strftime('%Y-%m-%d')
            
            try:
                yf_hist = ticker.history(
                    start=start_date,
                    end=end_date,
                    auto_adjust=True,
                )
            except Exception as e:
                result.error = f"Failed to fetch yfinance data: {str(e)}"
                return result
            
            if yf_hist.empty:
                result.error = "No yfinance data available for the sample period"
                return result
            
            # Get ticker corporate action data for classification
            try:
                ticker_data = {
                    "splits": ticker.splits,
                    "dividends": ticker.dividends,
                    "capital_gains": getattr(ticker, 'capital_gains', None),
                }
            except Exception:
                ticker_data = {
                    "splits": None,
                    "dividends": None,
                    "capital_gains": None,
                }
            
            # Compare each sample point
            for check_date, db_close in samples:
                date_str = check_date.strftime('%Y-%m-%d')
                
                # Find matching date in yfinance data
                yf_row = yf_hist[yf_hist.index.strftime('%Y-%m-%d') == date_str]
                
                if yf_row.empty:
                    continue
                
                yf_close = float(yf_row['Close'].iloc[0])
                pct_diff, is_significant = self._compare_with_precision(db_close, yf_close)
                
                if is_significant:
                    event_type, severity, details = self._classify_event(
                        pct_diff, ticker_data, date_str
                    )
                    
                    # Determine recommendation based on severity
                    if severity == AdjustmentSeverity.CRITICAL:
                        recommendation = "Immediate data refresh required"
                    elif severity == AdjustmentSeverity.HIGH:
                        recommendation = "Refresh data at earliest convenience"
                    elif severity == AdjustmentSeverity.NORMAL:
                        recommendation = "Schedule data refresh"
                    else:
                        recommendation = "Monitor for changes"
                    
                    event = AdjustmentEvent(
                        symbol=symbol,
                        event_type=event_type,
                        severity=severity,
                        pct_difference=round(pct_diff, 6),
                        check_date=date_str,
                        db_price=db_close,
                        yf_adjusted_price=yf_close,
                        details=details,
                        recommendation=recommendation,
                    )
                    result.events.append(event)
                    result.max_pct_diff = max(result.max_pct_diff, pct_diff)
            
            result.needs_refresh = len(result.events) > 0
            
        except Exception as e:
            result.error = f"Detection failed: {str(e)}"
        
        return result

    async def scan_all_symbols(
        self,
        session: AsyncSession,
        symbols: Optional[List[str]] = None,
        auto_fix: bool = False,
    ) -> dict[str, Any]:
        """Scan multiple symbols for price adjustments.
        
        Iterates through provided symbols (or all active symbols) and
        detects any needed price adjustments.
        
        Args:
            session: Async database session.
            symbols: List of symbols to check. If None, fetches all active symbols.
            auto_fix: Whether to automatically fix detected issues.
            
        Returns:
            Dictionary containing scan results, statistics, and any errors.
        """
        import logging
        from datetime import datetime
        
        logger = logging.getLogger(__name__)
        
        # Get symbols to scan if not provided
        if symbols is None:
            symbols = await get_symbols_for_scan(session)
        
        scan_result = {
            "scan_timestamp": datetime.utcnow().isoformat(),
            "total_symbols": len(symbols),
            "scanned": 0,
            "needs_refresh": [],
            "no_change": [],
            "errors": [],
            "fixed": [],
            "summary": {
                "by_type": {},
                "by_severity": {},
            },
        }
        
        fixer = AdjustmentFixer(session) if auto_fix else None
        
        for i, symbol in enumerate(symbols):
            logger.info(f"Scanning symbol {i+1}/{len(symbols)}: {symbol}")
            
            try:
                detection_result = await self.detect_adjustments(session, symbol)
                scan_result["scanned"] += 1
                
                if detection_result.error:
                    scan_result["errors"].append({
                        "symbol": symbol,
                        "error": detection_result.error,
                    })
                elif detection_result.needs_refresh:
                    scan_result["needs_refresh"].append(detection_result.to_dict())
                    
                    # Update summary statistics
                    for event in detection_result.events:
                        event_type = event.event_type.value
                        severity = event.severity.value
                        
                        scan_result["summary"]["by_type"][event_type] = (
                            scan_result["summary"]["by_type"].get(event_type, 0) + 1
                        )
                        scan_result["summary"]["by_severity"][severity] = (
                            scan_result["summary"]["by_severity"].get(severity, 0) + 1
                        )
                    
                    # Auto-fix if enabled
                    if fixer:
                        fix_result = await fixer.auto_fix_symbol(symbol)
                        scan_result["fixed"].append({
                            "symbol": symbol,
                            **fix_result,
                        })
                else:
                    scan_result["no_change"].append(symbol)
                    
            except Exception as e:
                logger.error(f"Error scanning {symbol}: {str(e)}")
                scan_result["errors"].append({
                    "symbol": symbol,
                    "error": str(e),
                })
        
        logger.info(
            f"Scan complete: {scan_result['scanned']} symbols, "
            f"{len(scan_result['needs_refresh'])} need refresh, "
            f"{len(scan_result['errors'])} errors"
        )
        
        return scan_result
