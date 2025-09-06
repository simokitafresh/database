"""
最古日フォールバック動作のログとモニタリング強化

このファイルはフォールバック動作の可視性を向上させるための
ログ、メトリクス、アラート機能を提供します。
"""

import logging
import time
from datetime import date, datetime
from typing import Dict, List, Optional, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from enum import Enum
import json


class FallbackEventType(Enum):
    """フォールバック関連イベントタイプ"""
    DATE_ADJUSTED = "date_adjusted"          # 日付がフォールバックで調整された
    EMPTY_RESULT = "empty_result"            # 指定範囲にデータなし
    SYMBOL_NOT_FOUND = "symbol_not_found"    # シンボル未登録
    PERFORMANCE_WARNING = "perf_warning"     # 性能警告
    ERROR_OCCURRED = "error_occurred"        # エラー発生


@dataclass
class FallbackEvent:
    """フォールバック関連イベントの詳細情報"""
    event_type: FallbackEventType
    timestamp: datetime
    symbols: List[str]
    date_from: Optional[date] = None
    date_to: Optional[date] = None
    adjusted_from: Optional[date] = None
    adjustment_days: Optional[int] = None
    duration_ms: Optional[float] = None
    error_message: Optional[str] = None
    result_count: Optional[int] = None
    additional_data: Optional[dict] = None
    
    def to_dict(self) -> dict:
        """イベントを辞書形式に変換（ログ出力用）"""
        return {
            "event_type": self.event_type.value,
            "timestamp": self.timestamp.isoformat(),
            "symbols": self.symbols,
            "date_from": self.date_from.isoformat() if self.date_from else None,
            "date_to": self.date_to.isoformat() if self.date_to else None,
            "adjusted_from": self.adjusted_from.isoformat() if self.adjusted_from else None,
            "adjustment_days": self.adjustment_days,
            "duration_ms": self.duration_ms,
            "error_message": self.error_message,
            "result_count": self.result_count,
            "additional_data": self.additional_data
        }
    
    def to_json(self) -> str:
        """JSON形式でシリアライズ"""
        return json.dumps(self.to_dict(), ensure_ascii=False, separators=(',', ':'))


class FallbackLogger:
    """フォールバック専用のログ機能"""
    
    def __init__(self, logger_name: str = "fallback_monitor"):
        self.logger = logging.getLogger(logger_name)
        
        # 構造化ログ用のフォーマッター設定
        if not self.logger.handlers:
            handler = logging.StreamHandler()
            formatter = logging.Formatter(
                '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
            )
            handler.setFormatter(formatter)
            self.logger.addHandler(handler)
            self.logger.setLevel(logging.INFO)
    
    def log_event(self, event: FallbackEvent):
        """フォールバックイベントをログ出力"""
        if event.event_type == FallbackEventType.ERROR_OCCURRED:
            self.logger.error(f"Fallback Error: {event.to_json()}")
        elif event.event_type == FallbackEventType.PERFORMANCE_WARNING:
            self.logger.warning(f"Fallback Performance: {event.to_json()}")
        elif event.event_type == FallbackEventType.DATE_ADJUSTED:
            self.logger.info(f"Fallback Date Adjustment: {event.to_json()}")
        else:
            self.logger.info(f"Fallback Event: {event.to_json()}")
    
    def log_date_adjustment(
        self,
        symbols: List[str],
        original_from: date,
        adjusted_from: date,
        date_to: date,
        duration_ms: float
    ):
        """日付調整イベントをログ"""
        event = FallbackEvent(
            event_type=FallbackEventType.DATE_ADJUSTED,
            timestamp=datetime.now(),
            symbols=symbols,
            date_from=original_from,
            date_to=date_to,
            adjusted_from=adjusted_from,
            adjustment_days=(adjusted_from - original_from).days,
            duration_ms=duration_ms
        )
        self.log_event(event)
    
    def log_empty_result(
        self,
        symbols: List[str],
        date_from: date,
        date_to: date,
        duration_ms: float
    ):
        """空結果イベントをログ"""
        event = FallbackEvent(
            event_type=FallbackEventType.EMPTY_RESULT,
            timestamp=datetime.now(),
            symbols=symbols,
            date_from=date_from,
            date_to=date_to,
            duration_ms=duration_ms,
            result_count=0
        )
        self.log_event(event)
    
    def log_performance_warning(
        self,
        symbols: List[str],
        duration_ms: float,
        result_count: int,
        threshold_ms: float = 1000.0
    ):
        """性能警告をログ"""
        if duration_ms > threshold_ms:
            event = FallbackEvent(
                event_type=FallbackEventType.PERFORMANCE_WARNING,
                timestamp=datetime.now(),
                symbols=symbols,
                duration_ms=duration_ms,
                result_count=result_count,
                additional_data={"threshold_ms": threshold_ms}
            )
            self.log_event(event)
    
    def log_error(
        self,
        symbols: List[str],
        error_message: str,
        date_from: Optional[date] = None,
        date_to: Optional[date] = None
    ):
        """エラーイベントをログ"""
        event = FallbackEvent(
            event_type=FallbackEventType.ERROR_OCCURRED,
            timestamp=datetime.now(),
            symbols=symbols,
            date_from=date_from,
            date_to=date_to,
            error_message=error_message
        )
        self.log_event(event)


class FallbackMetricsCollector:
    """フォールバックメトリクス収集器"""
    
    def __init__(self):
        self.reset_metrics()
    
    def reset_metrics(self):
        """メトリクスをリセット"""
        self.total_requests = 0
        self.fallback_requests = 0
        self.empty_results = 0
        self.error_count = 0
        self.total_duration_ms = 0.0
        self.max_duration_ms = 0.0
        self.adjustment_days_histogram = {}  # 調整日数の分布
        self.symbol_frequency = {}  # シンボル別リクエスト頻度
        self.hourly_stats = {}  # 時間別統計
    
    def record_request(
        self,
        symbols: List[str],
        date_from: date,
        date_to: date,
        adjusted_from: Optional[date],
        duration_ms: float,
        result_count: int,
        had_error: bool = False
    ):
        """リクエストメトリクスを記録"""
        self.total_requests += 1
        self.total_duration_ms += duration_ms
        self.max_duration_ms = max(self.max_duration_ms, duration_ms)
        
        if had_error:
            self.error_count += 1
        
        if result_count == 0:
            self.empty_results += 1
        
        if adjusted_from and adjusted_from != date_from:
            self.fallback_requests += 1
            adjustment_days = (adjusted_from - date_from).days
            self.adjustment_days_histogram[adjustment_days] = (
                self.adjustment_days_histogram.get(adjustment_days, 0) + 1
            )
        
        # シンボル頻度記録
        for symbol in symbols:
            self.symbol_frequency[symbol] = self.symbol_frequency.get(symbol, 0) + 1
        
        # 時間別統計
        hour = datetime.now().hour
        if hour not in self.hourly_stats:
            self.hourly_stats[hour] = {"requests": 0, "total_duration": 0.0}
        self.hourly_stats[hour]["requests"] += 1
        self.hourly_stats[hour]["total_duration"] += duration_ms
    
    def get_summary(self) -> dict:
        """メトリクス要約を取得"""
        avg_duration = (
            self.total_duration_ms / self.total_requests 
            if self.total_requests > 0 else 0
        )
        
        fallback_rate = (
            self.fallback_requests / self.total_requests * 100
            if self.total_requests > 0 else 0
        )
        
        error_rate = (
            self.error_count / self.total_requests * 100
            if self.total_requests > 0 else 0
        )
        
        return {
            "total_requests": self.total_requests,
            "fallback_requests": self.fallback_requests,
            "fallback_rate_percent": round(fallback_rate, 2),
            "empty_results": self.empty_results,
            "error_count": self.error_count,
            "error_rate_percent": round(error_rate, 2),
            "avg_duration_ms": round(avg_duration, 2),
            "max_duration_ms": round(self.max_duration_ms, 2),
            "adjustment_days_distribution": self.adjustment_days_histogram,
            "top_symbols": sorted(
                self.symbol_frequency.items(), 
                key=lambda x: x[1], 
                reverse=True
            )[:10],
            "hourly_avg_duration": {
                str(hour): round(stats["total_duration"] / stats["requests"], 2)
                for hour, stats in self.hourly_stats.items()
                if stats["requests"] > 0
            }
        }


# グローバルインスタンス
_fallback_logger = FallbackLogger()
_metrics_collector = FallbackMetricsCollector()


@contextmanager
def fallback_monitoring(
    symbols: Sequence[str],
    date_from: date,
    date_to: date,
    performance_threshold_ms: float = 1000.0
):
    """
    フォールバック処理のモニタリングコンテキストマネージャー
    
    使用例:
    ```python
    with fallback_monitoring(symbols, date_from, date_to) as monitor:
        # フォールバック処理実行
        result = await get_prices_resolved(session, symbols, date_from, date_to)
        
        # 結果情報を設定
        monitor.set_result(result, adjusted_from=actual_from)
    ```
    """
    class Monitor:
        def __init__(self):
            self.start_time = time.time()
            self.result_count = 0
            self.adjusted_from = None
            self.had_error = False
            self.error_message = None
        
        def set_result(self, result: List, adjusted_from: Optional[date] = None):
            """結果情報を設定"""
            self.result_count = len(result) if result else 0
            self.adjusted_from = adjusted_from
        
        def set_error(self, error_message: str):
            """エラー情報を設定"""
            self.had_error = True
            self.error_message = error_message
    
    monitor = Monitor()
    
    try:
        yield monitor
    except Exception as e:
        monitor.set_error(str(e))
        _fallback_logger.log_error(list(symbols), str(e), date_from, date_to)
        raise
    finally:
        # 処理完了時の記録
        duration_ms = (time.time() - monitor.start_time) * 1000
        
        # メトリクス記録
        _metrics_collector.record_request(
            symbols=list(symbols),
            date_from=date_from,
            date_to=date_to,
            adjusted_from=monitor.adjusted_from,
            duration_ms=duration_ms,
            result_count=monitor.result_count,
            had_error=monitor.had_error
        )
        
        # ログ出力
        if monitor.had_error:
            # エラーは既にログ済み
            pass
        elif monitor.result_count == 0:
            _fallback_logger.log_empty_result(
                list(symbols), date_from, date_to, duration_ms
            )
        elif monitor.adjusted_from and monitor.adjusted_from != date_from:
            _fallback_logger.log_date_adjustment(
                list(symbols), date_from, monitor.adjusted_from, date_to, duration_ms
            )
        
        # 性能警告チェック
        _fallback_logger.log_performance_warning(
            list(symbols), duration_ms, monitor.result_count, performance_threshold_ms
        )


def get_fallback_logger() -> FallbackLogger:
    """フォールバックログインスタンスを取得"""
    return _fallback_logger


def get_metrics_collector() -> FallbackMetricsCollector:
    """メトリクス収集器インスタンスを取得"""
    return _metrics_collector


def get_monitoring_dashboard_data() -> dict:
    """モニタリングダッシュボード用のデータを取得"""
    return {
        "metrics_summary": _metrics_collector.get_summary(),
        "last_updated": datetime.now().isoformat(),
        "status": "healthy" if _metrics_collector.error_count == 0 else "degraded"
    }
