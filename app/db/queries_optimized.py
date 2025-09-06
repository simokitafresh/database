"""
フォールバックロジック最適化の提案と実装

このファイルは、最古日フォールバック機能の性能向上と効率化を目的とした
最適化案を含んでいます。

最適化項目:
1. 事前フィルタリング - 最古日チェックによる無駄なクエリの削減
2. バッチ処理 - 複数シンボルの効率的な処理
3. キャッシング - 最古日情報のキャッシュ
4. 並列処理 - I/O処理の並列化
"""

from datetime import date
from typing import Dict, List, Optional, Sequence
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
import asyncio
import logging
from collections import defaultdict

logger = logging.getLogger(__name__)


async def get_symbols_oldest_dates(
    session: AsyncSession, 
    symbols: Sequence[str]
) -> Dict[str, Optional[date]]:
    """
    複数シンボルの最古日を効率的にバッチ取得する最適化関数。
    
    単一クエリで複数シンボルの first_date を取得し、
    個別クエリの回数を削減する。
    
    Args:
        session: データベースセッション
        symbols: シンボルリスト
        
    Returns:
        シンボル名 -> 最古日のマッピング辞書（データなしの場合はNone）
    """
    if not symbols:
        return {}
    
    # 複数シンボルを一括で取得するクエリ
    sql = text("""
        SELECT symbol, first_date 
        FROM symbols 
        WHERE symbol = ANY(:symbols) AND is_active = true
    """)
    
    result = await session.execute(sql, {"symbols": list(symbols)})
    
    oldest_dates = {}
    for row in result:
        oldest_dates[row.symbol] = row.first_date
    
    # リクエストされたシンボルで未登録のものはNoneとして追加
    for symbol in symbols:
        if symbol not in oldest_dates:
            oldest_dates[symbol] = None
            
    return oldest_dates


def filter_symbols_by_date_range(
    symbols_oldest_dates: Dict[str, Optional[date]],
    date_from: date,
    date_to: date
) -> Dict[str, List[str]]:
    """
    シンボルを日付範囲に基づいて分類する最適化関数。
    
    最古日情報を使って、シンボルを以下に分類:
    - needs_data: データ取得が必要なシンボル
    - no_data: 指定範囲にデータがないシンボル  
    - unknown: 最古日が不明なシンボル（新規登録候補）
    
    Args:
        symbols_oldest_dates: シンボル -> 最古日のマッピング
        date_from: 要求開始日
        date_to: 要求終了日
        
    Returns:
        カテゴリ -> シンボルリストのマッピング
    """
    categorized = {
        "needs_data": [],      # データ取得必要
        "no_data": [],         # 指定範囲にデータなし
        "unknown": []          # 最古日不明（新規登録候補）
    }
    
    for symbol, oldest_date in symbols_oldest_dates.items():
        if oldest_date is None:
            # 最古日不明 = シンボル未登録または未取得
            categorized["unknown"].append(symbol)
        elif date_to < oldest_date:
            # 要求終了日が最古日より前 = データなし
            categorized["no_data"].append(symbol)
        else:
            # データ取得必要（部分的でも）
            categorized["needs_data"].append(symbol)
    
    return categorized


async def get_prices_resolved_optimized(
    session: AsyncSession,
    symbols: Sequence[str],
    date_from: date,
    date_to: date,
) -> List[dict]:
    """
    最適化された価格データ取得関数。
    
    従来の get_prices_resolved に対する最適化:
    1. 事前に最古日を一括取得して無駄なクエリを削減
    2. データが存在しないシンボルは早期スキップ  
    3. 並列処理による I/O 待機時間の短縮
    
    Args:
        session: データベースセッション
        symbols: 取得対象シンボルリスト
        date_from: 取得開始日
        date_to: 取得終了日
        
    Returns:
        価格データのリスト（日付・シンボル順でソート済み）
    """
    if not symbols:
        return []
    
    logger.info(f"Optimized price fetch for {len(symbols)} symbols: {date_from} to {date_to}")
    
    # Phase 1: 最古日一括取得による事前フィルタリング
    oldest_dates = await get_symbols_oldest_dates(session, symbols)
    categorized = filter_symbols_by_date_range(oldest_dates, date_from, date_to)
    
    logger.debug(f"Symbol categorization: needs_data={len(categorized['needs_data'])}, "
                f"no_data={len(categorized['no_data'])}, unknown={len(categorized['unknown'])}")
    
    # Phase 2: データ取得が必要なシンボルのみを並列処理
    results = []
    
    if categorized["needs_data"]:
        # 並列でデータベースクエリを実行
        sql = text("SELECT * FROM get_prices_resolved(:symbol, :date_from, :date_to)")
        
        async def fetch_symbol_data(symbol: str) -> List[dict]:
            """単一シンボルのデータを取得"""
            try:
                result = await session.execute(
                    sql, {"symbol": symbol, "date_from": date_from, "date_to": date_to}
                )
                return [dict(row) for row in result.mappings().all()]
            except Exception as e:
                logger.error(f"Failed to fetch data for symbol {symbol}: {e}")
                return []
        
        # 並列実行（ただしデータベースセッション制限に注意）
        symbol_tasks = [
            fetch_symbol_data(symbol) 
            for symbol in categorized["needs_data"]
        ]
        
        # セマフォで同時実行数を制限（PostgreSQL接続数制限対策）
        semaphore = asyncio.Semaphore(5)  # 最大5同時実行
        
        async def fetch_with_semaphore(task):
            async with semaphore:
                return await task
        
        limited_tasks = [fetch_with_semaphore(task) for task in symbol_tasks]
        symbol_results = await asyncio.gather(*limited_tasks, return_exceptions=True)
        
        # 正常結果のみを結合
        for symbol_data in symbol_results:
            if isinstance(symbol_data, list):
                results.extend(symbol_data)
    
    # Phase 3: unknown シンボルの処理（自動登録が有効な場合）
    # 注: 実際の自動登録ロジックは既存のコードに委ね、ここでは警告ログのみ
    if categorized["unknown"]:
        logger.warning(f"Unknown symbols detected (may need registration): {categorized['unknown']}")
    
    # Phase 4: 結果をソート
    results.sort(key=lambda row: (row.get("date", date.min), row.get("symbol", "")))
    
    logger.info(f"Optimized fetch completed: {len(results)} rows returned")
    return results


class FallbackMetrics:
    """フォールバック動作の統計情報を収集するクラス"""
    
    def __init__(self):
        self.reset()
    
    def reset(self):
        """統計情報をリセット"""
        self.total_requests = 0
        self.fallback_requests = 0
        self.empty_results = 0
        self.symbols_with_fallback = set()
        self.date_adjustments = []
    
    def record_request(self, symbols: Sequence[str], date_from: date, date_to: date, oldest_dates: Dict[str, Optional[date]]):
        """リクエストの統計情報を記録"""
        self.total_requests += 1
        
        has_fallback = False
        for symbol in symbols:
            oldest_date = oldest_dates.get(symbol)
            if oldest_date and date_from < oldest_date:
                has_fallback = True
                self.symbols_with_fallback.add(symbol)
                self.date_adjustments.append({
                    "symbol": symbol,
                    "requested_from": date_from,
                    "actual_from": oldest_date,
                    "adjustment_days": (oldest_date - date_from).days
                })
        
        if has_fallback:
            self.fallback_requests += 1
    
    def record_empty_result(self):
        """空の結果を記録"""
        self.empty_results += 1
    
    def get_summary(self) -> dict:
        """統計情報の要約を取得"""
        fallback_rate = (self.fallback_requests / self.total_requests * 100) if self.total_requests > 0 else 0
        empty_rate = (self.empty_results / self.total_requests * 100) if self.total_requests > 0 else 0
        
        return {
            "total_requests": self.total_requests,
            "fallback_requests": self.fallback_requests,
            "fallback_rate_percent": round(fallback_rate, 2),
            "empty_results": self.empty_results,
            "empty_rate_percent": round(empty_rate, 2),
            "unique_symbols_with_fallback": len(self.symbols_with_fallback),
            "total_date_adjustments": len(self.date_adjustments),
            "avg_adjustment_days": (
                sum(adj["adjustment_days"] for adj in self.date_adjustments) / 
                len(self.date_adjustments)
            ) if self.date_adjustments else 0
        }


# グローバル統計インスタンス（本番環境では Redis 等に移行検討）
_fallback_metrics = FallbackMetrics()


def get_fallback_metrics() -> FallbackMetrics:
    """フォールバック統計インスタンスを取得"""
    return _fallback_metrics


async def get_prices_resolved_with_metrics(
    session: AsyncSession,
    symbols: Sequence[str], 
    date_from: date,
    date_to: date,
) -> List[dict]:
    """
    統計情報付きの最適化価格取得関数。
    
    get_prices_resolved_optimized にメトリクス収集機能を追加。
    """
    # 最古日情報取得
    oldest_dates = await get_symbols_oldest_dates(session, symbols)
    
    # 統計情報記録
    _fallback_metrics.record_request(symbols, date_from, date_to, oldest_dates)
    
    # 最適化された取得処理を実行
    results = await get_prices_resolved_optimized(session, symbols, date_from, date_to)
    
    # 空の結果の場合も記録
    if not results:
        _fallback_metrics.record_empty_result()
    
    return results
