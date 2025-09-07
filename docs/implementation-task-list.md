# Stock API 修正実装タスクリスト

## 📋 実装概要
**目的**: Stock APIの4つの重大な問題を修正  
**総タスク数**: 32タスク  
**推定時間**: 4時間  
**実装者**: エンジニアリングLLM（コーディング専門）

---

## 🔧 Phase 1: P1修正 - トランザクション管理（25分）

### Task 1.1: fetch_worker.pyのトランザクション削除
- [x] **開始条件**: `app/services/fetch_worker.py`を開く
- [x] **作業内容**: L43-44の`async with session.begin():`行を削除
- [x] **終了条件**: 該当行が削除され、インデントエラーがない
- [x] **検証方法**: `python -m py_compile app/services/fetch_worker.py`でエラーなし

### Task 1.2: fetch_worker.pyのインデント修正
- [x] **開始条件**: Task 1.1完了
- [x] **作業内容**: L45以降のインデントを1レベル左にシフト（try:ブロック全体）
- [x] **終了条件**: tryブロックが正しいインデントレベルになっている
- [x] **検証方法**: エディタのインデント表示で確認

### Task 1.3: トランザクションテストコード作成
- [x] **開始条件**: `tests/unit/`ディレクトリにアクセス
- [x] **作業内容**: `test_fetch_worker_transaction.py`を新規作成
- [x] **コード内容**:
```python
import pytest
from unittest.mock import patch, AsyncMock
from datetime import date
from app.services.fetch_worker import process_fetch_job

@pytest.mark.asyncio
async def test_no_nested_transaction_error():
    """トランザクションエラーが発生しないことを確認"""
    with patch('app.services.fetch_jobs.update_job_status') as mock_update:
        mock_update.return_value = None
        with patch('app.db.engine.create_engine_and_sessionmaker') as mock_engine:
            mock_session = AsyncMock()
            mock_engine.return_value = (None, AsyncMock(return_value=mock_session))
            
            # エラーが発生しないことを確認
            await process_fetch_job(
                "test-job-001",
                ["AAPL"],
                date(2024, 1, 1),
                date(2024, 1, 31)
            )
            assert mock_update.called
```
- [x] **終了条件**: テストファイルが作成され、構文エラーなし
- [x] **検証方法**: `pytest tests/unit/test_fetch_worker_transaction.py -v`

---

## 🔧 Phase 2: P2修正 - 日付境界条件（45分）

### Task 2.1: 日付範囲検証関数の追加
- [x] **開始条件**: `app/db/queries.py`を開く
- [x] **作業内容**: L230付近、`ensure_coverage_with_auto_fetch`関数内に日付検証追加
- [x] **コード内容**:
```python
# actual_start = await find_earliest_available_date(...) の後に追加
if actual_start > date_to:
    logger.warning(
        f"Symbol {symbol}: No data available in requested range "
        f"({date_from} to {date_to}). Data starts from {actual_start}"
    )
    result_meta["adjustments"][symbol] = {
        "status": "no_data_in_range",
        "requested_start": str(date_from),
        "requested_end": str(date_to),
        "actual_start": str(actual_start),
        "message": f"Data only available from {actual_start}"
    }
    continue  # このシンボルをスキップ
```
- [x] **終了条件**: 条件分岐が正しく追加されている
- [x] **検証方法**: 構文チェック成功

### Task 2.2: 部分データ処理の追加
- [x] **開始条件**: Task 2.1完了
- [x] **作業内容**: 同じく`ensure_coverage_with_auto_fetch`内、日付調整時の処理追加
- [x] **コード内容**:
```python
# actual_start > date_from の場合の処理を追加
if actual_start > date_from:
    logger.info(
        f"Symbol {symbol}: Adjusting date range. "
        f"Requested: {date_from}, Available: {actual_start}"
    )
    result_meta["adjustments"][symbol] = {
        "status": "partial_data",
        "requested_start": str(date_from),
        "actual_start": str(actual_start),
        "message": "Data adjusted to available range"
    }
```
- [x] **終了条件**: 部分データケースが処理される
- [x] **検証方法**: ログ出力の確認

### Task 2.3: 境界条件テストコード作成
- [x] **開始条件**: `tests/unit/`ディレクトリ
- [x] **作業内容**: `test_date_boundary.py`を新規作成
- [x] **コード内容**:
```python
import pytest
from datetime import date
from unittest.mock import patch, AsyncMock
from app.db.queries import ensure_coverage_with_auto_fetch

@pytest.mark.asyncio
async def test_date_boundary_conditions():
    """日付境界条件のテスト"""
    mock_session = AsyncMock()
    
    # GLD: 2004年以前のデータなし
    with patch('app.db.queries.find_earliest_available_date') as mock_find:
        mock_find.return_value = date(2004, 11, 18)
        
        result = await ensure_coverage_with_auto_fetch(
            mock_session,
            ["GLD"],
            date(1990, 1, 1),
            date(2001, 1, 1),
            30
        )
        
        assert "GLD" in result["adjustments"]
        assert result["adjustments"]["GLD"]["status"] == "no_data_in_range"
```
- [x] **終了条件**: テストが作成され実行可能
- [x] **検証方法**: `pytest tests/unit/test_date_boundary.py -v`

---

## 🔧 Phase 3: P3修正 - YFinance警告（15分）

### Task 3.1: fetcher.pyのauto_adjust追加（1箇所目）
- [x] **開始条件**: `app/services/fetcher.py`を開く
- [x] **作業内容**: L58付近、最初の`yf.download()`呼び出しに`auto_adjust=True`追加
- [x] **変更前**:
```python
df = yf.download(
    symbol,
    start=fetch_start,
    end=fetch_end,
    progress=False,
    timeout=settings.FETCH_TIMEOUT_SECONDS,
)
```
- [x] **変更後**:
```python
df = yf.download(
    symbol,
    start=fetch_start,
    end=fetch_end,
    auto_adjust=True,  # 明示的に追加
    progress=False,
    timeout=settings.FETCH_TIMEOUT_SECONDS,
)
```
- [x] **終了条件**: パラメータが追加されている
- [x] **検証方法**: grepで確認 `grep -n "auto_adjust" app/services/fetcher.py`

### Task 3.2: fetcher.pyのauto_adjust追加（2箇所目）
- [x] **開始条件**: Task 3.1完了
- [x] **作業内容**: L79付近、フォールバックの`tk.history()`呼び出しを確認
- [x] **確認内容**: `auto_adjust=True`が既に設定されているか確認、なければ追加
- [x] **終了条件**: 両方のYahoo Finance呼び出しでauto_adjustが明示的
- [x] **検証方法**: 該当箇所の目視確認

### Task 3.3: fetch_worker.pyのtickerも修正
- [x] **開始条件**: `app/services/fetch_worker.py`を開く
- [x] **作業内容**: L162付近、`ticker.history()`の呼び出しを確認
- [x] **変更内容**: `auto_adjust=True`が明示的に設定されているか確認、なければ追加
- [x] **終了条件**: パラメータ確認完了
- [x] **検証方法**: 該当箇所の確認

### Task 3.4: YFinance警告テスト作成
- [x] **開始条件**: `tests/unit/`ディレクトリ
- [x] **作業内容**: `test_yfinance_warnings.py`を新規作成
- [x] **コード内容**:
```python
import logging
import pytest
from unittest.mock import patch, MagicMock
from datetime import date
from app.services.fetcher import fetch_prices
from app.core.config import settings

def test_no_yfinance_warning(caplog):
    """YFinance警告が出力されないことを確認"""
    with patch('yfinance.download') as mock_download:
        mock_download.return_value = MagicMock(empty=False)
        
        with caplog.at_level(logging.WARNING):
            fetch_prices("AAPL", date(2024, 1, 1), date(2024, 1, 31), settings=settings)
        
        # auto_adjustの警告が出ていないことを確認
        assert "auto_adjust" not in caplog.text
        
        # auto_adjustが明示的に渡されていることを確認
        call_kwargs = mock_download.call_args.kwargs
        assert "auto_adjust" in call_kwargs
        assert call_kwargs["auto_adjust"] is True
```
- [x] **終了条件**: テスト作成完了
- [x] **検証方法**: `pytest tests/unit/test_yfinance_warnings.py -v`

---

## 🔧 Phase 4: P4修正 - データ可用性判定（60分）

### Task 4.1: utilsディレクトリ作成
- [ ] **開始条件**: プロジェクトルート
- [ ] **作業内容**: 
  1. `mkdir -p app/utils` を実行
  2. `touch app/utils/__init__.py` を実行（空のinitファイル作成）
- [ ] **終了条件**: `app/utils/`ディレクトリが存在し、`__init__.py`がある
- [ ] **検証方法**: `ls -la app/utils/`で確認

### Task 4.2: 日付ユーティリティ作成
- [ ] **開始条件**: Task 4.1完了
- [ ] **作業内容**: `app/utils/date_utils.py`を新規作成
- [ ] **コード内容**（全文をコピー）:
```python
"""日付範囲処理ユーティリティ"""
from datetime import date, timedelta
from typing import List, Tuple

def merge_date_ranges(ranges: List[Tuple[date, date]]) -> List[Tuple[date, date]]:
    """
    重複する日付範囲をマージする
    
    Args:
        ranges: (開始日, 終了日)のタプルのリスト
        
    Returns:
        マージされた日付範囲のリスト
    """
    if not ranges:
        return []
    
    # 開始日でソート
    sorted_ranges = sorted(ranges, key=lambda x: x[0])
    merged = [sorted_ranges[0]]
    
    for current_start, current_end in sorted_ranges[1:]:
        last_start, last_end = merged[-1]
        
        # 重複または隣接する範囲をマージ
        if current_start <= last_end + timedelta(days=1):
            merged[-1] = (last_start, max(last_end, current_end))
        else:
            merged.append((current_start, current_end))
    
    return merged

def validate_date_range(start: date, end: date) -> dict:
    """
    日付範囲の妥当性を検証
    
    Args:
        start: 開始日
        end: 終了日
        
    Returns:
        検証結果の辞書
    """
    if start > end:
        return {
            "valid": False,
            "reason": "start_after_end",
            "message": f"Start date {start} is after end date {end}"
        }
    
    if end > date.today():
        return {
            "valid": False,
            "reason": "future_date",
            "message": f"End date {end} is in the future"
        }
    
    # 20年以上前のデータは通常取得できない
    min_date = date.today() - timedelta(days=365 * 20)
    if start < min_date:
        return {
            "valid": True,
            "warning": "very_old_date",
            "message": f"Start date {start} is very old, data may not be available"
        }
    
    return {
        "valid": True,
        "message": "Date range is valid"
    }
```
- [ ] **終了条件**: ファイル作成完了
- [ ] **検証方法**: `python -c "from app.utils.date_utils import merge_date_ranges"`でエラーなし

### Task 4.2: find_earliest_available_date改善
- [ ] **開始条件**: Task 4.1完了
- [ ] **作業内容**: `find_earliest_available_date`関数を完全に書き換え
- [ ] **コード内容**:
```python
async def find_earliest_available_date(
    symbol: str, 
    target_date: date,
    session: AsyncSession = None  # オプショナルに
) -> tuple[date, bool]:
    """実際の最古利用可能日を効率的に特定"""
    logger = logging.getLogger(__name__)
    
    # DBチェック（sessionがある場合のみ）
    db_min_date = None
    if session:
        db_result = await session.execute(
            text("SELECT MIN(date) FROM prices WHERE symbol = :symbol"),
            {"symbol": symbol}
        )
        db_min_date = db_result.scalar()
    
    # DBにデータがある場合、その前を探索
    if db_min_date and target_date < db_min_date:
        logger.debug(f"Searching YF data for {symbol} before {db_min_date}")
        actual_start = await binary_search_yf_start_date(
            symbol, 
            date(1970, 1, 1),
            db_min_date,
            target_date
        )
        return actual_start, True
    
    # DBが空またはターゲットがDB範囲内
    if not db_min_date:
        # 簡易探索
        actual_start = await binary_search_yf_start_date(
            symbol,
            date(1970, 1, 1),
            date.today(),
            target_date
        )
        return actual_start, actual_start == target_date
    
    return target_date, True
```
- [ ] **終了条件**: 関数が改善され、戻り値がtuple
- [ ] **検証方法**: 戻り値の型確認

### Task 4.3: 日付範囲マージユーティリティ作成
- [ ] **開始条件**: `app/utils/`ディレクトリ確認（なければ作成）
- [ ] **作業内容**: `app/utils/date_utils.py`を新規作成
- [ ] **コード内容**:
```python
from datetime import date, timedelta
from typing import List, Tuple

def merge_date_ranges(ranges: List[Tuple[date, date]]) -> List[Tuple[date, date]]:
    """重複する日付範囲をマージ"""
    if not ranges:
        return []
    
    sorted_ranges = sorted(ranges, key=lambda x: x[0])
    merged = [sorted_ranges[0]]
    
    for current_start, current_end in sorted_ranges[1:]:
        last_start, last_end = merged[-1]
        
        if current_start <= last_end + timedelta(days=1):
            merged[-1] = (last_start, max(last_end, current_end))
        else:
            merged.append((current_start, current_end))
    
    return merged
```
- [ ] **終了条件**: ユーティリティ関数作成完了
- [ ] **検証方法**: `python -c "from app.utils.date_utils import merge_date_ranges"`

### Task 4.4: ensure_coverage_unified関数作成
- [ ] **開始条件**: Task 4.1-4.3完了
- [ ] **作業内容**: `app/db/queries.py`に統一関数を追加
- [ ] **コード位置**: `ensure_coverage_with_auto_fetch`の下に新規追加
- [ ] **コード内容**: （長いので要約）
  - DBカバレッジ確認
  - 不足範囲の特定
  - Yahoo Finance探索
  - 統合フェッチ処理
- [ ] **終了条件**: 関数追加完了、500行程度
- [ ] **検証方法**: 関数定義の確認

### Task 4.5: 既存関数の統合
- [ ] **開始条件**: Task 4.4完了
- [ ] **作業内容**: `ensure_coverage_with_auto_fetch`を`ensure_coverage_unified`を呼び出すように変更
- [ ] **コード内容**:
```python
async def ensure_coverage_with_auto_fetch(
    session: AsyncSession,
    symbols: Sequence[str],
    date_from: date,
    date_to: date,
    refetch_days: int,
) -> Dict[str, Any]:
    """既存関数を新しい統一実装にリダイレクト"""
    logger.info("Redirecting to unified coverage implementation")
    return await ensure_coverage_unified(
        session=session,
        symbols=symbols,
        date_from=date_from,
        date_to=date_to,
        refetch_days=refetch_days
    )
```
- [ ] **終了条件**: リダイレクト実装完了
- [ ] **検証方法**: 関数呼び出しの確認

### Task 4.6: データ可用性テスト作成
- [ ] **開始条件**: `tests/unit/`ディレクトリ
- [ ] **作業内容**: `test_data_availability.py`を新規作成
- [ ] **コード内容**:
```python
import pytest
from datetime import date
from unittest.mock import patch, AsyncMock, MagicMock
from app.db.queries import ensure_coverage_unified

@pytest.mark.asyncio
async def test_db_unregistered_historical_data():
    """DB未登録の過去データ取得テスト"""
    mock_session = AsyncMock()
    
    # DBには2020年以降のデータのみ
    mock_session.execute.return_value.fetchone.return_value = MagicMock(
        min_date=date(2020, 1, 1),
        max_date=date(2024, 12, 31)
    )
    
    with patch('app.db.queries.fetch_prices_df') as mock_fetch:
        # 2010-2019のデータ取得をシミュレート
        mock_fetch.return_value = MagicMock(empty=False)
        
        result = await ensure_coverage_unified(
            mock_session,
            ["AAPL"],
            date(2010, 1, 1),
            date(2024, 12, 31),
            30
        )
        
        # 過去データの取得が試行されたことを確認
        assert mock_fetch.called
        call_args = mock_fetch.call_args_list
        
        # 2010年付近のデータ取得を確認
        fetched_ranges = [
            (args[1]['start'], args[1]['end']) 
            for args in call_args
        ]
        assert any(
            start.year <= 2010 
            for start, _ in fetched_ranges
        )
```
- [ ] **終了条件**: テスト作成完了
- [ ] **検証方法**: `pytest tests/unit/test_data_availability.py -v`

---

## 🔧 Phase 5: 統合テスト（30分）

### Task 5.1: 統合テストスクリプト作成
- [ ] **開始条件**: `tests/integration/`ディレクトリ確認
- [ ] **作業内容**: `test_all_fixes.py`を新規作成
- [ ] **コード内容**:
```python
import pytest
from datetime import date
from unittest.mock import patch, AsyncMock
import logging

@pytest.mark.asyncio
async def test_all_problems_fixed():
    """P1-P4の全問題が修正されていることを確認"""
    
    # P1: トランザクションエラーなし
    from app.services.fetch_worker import process_fetch_job
    # モック設定...
    
    # P2: 境界条件処理
    from app.db.queries import ensure_coverage_unified
    # テスト実装...
    
    # P3: YFinance警告なし
    # ログチェック...
    
    # P4: DB未登録データ取得
    # 統合動作確認...
    
    assert True  # 全テストパス
```
- [ ] **終了条件**: 統合テスト作成
- [ ] **検証方法**: `pytest tests/integration/test_all_fixes.py -v`

### Task 5.2: 検証スクリプト作成
- [ ] **開始条件**: プロジェクトルート
- [ ] **作業内容**: `scripts/verify_fixes.py`を新規作成
- [ ] **コード内容**:
```python
#!/usr/bin/env python
"""修正検証スクリプト"""
import sys
import subprocess

def verify_fix(name, command):
    """個別修正の検証"""
    print(f"Verifying {name}...")
    result = subprocess.run(command, shell=True, capture_output=True)
    if result.returncode == 0:
        print(f"✅ {name} passed")
        return True
    else:
        print(f"❌ {name} failed")
        print(result.stderr.decode())
        return False

def main():
    checks = [
        ("P1: Transaction", "pytest tests/unit/test_fetch_worker_transaction.py"),
        ("P2: Date Boundary", "pytest tests/unit/test_date_boundary.py"),
        ("P3: YFinance Warning", "pytest tests/unit/test_yfinance_warnings.py"),
        ("P4: Data Availability", "pytest tests/unit/test_data_availability.py"),
    ]
    
    all_passed = all(verify_fix(name, cmd) for name, cmd in checks)
    
    if all_passed:
        print("\n✅ All fixes verified successfully!")
        sys.exit(0)
    else:
        print("\n❌ Some fixes failed verification")
        sys.exit(1)

if __name__ == "__main__":
    main()
```
- [ ] **終了条件**: 検証スクリプト作成完了
- [ ] **検証方法**: `python scripts/verify_fixes.py`

---

## 🔧 Phase 6: クリーンアップ（15分）

### Task 6.1: 不要なインポート削除
- [x] **開始条件**: 修正したファイルすべて
- [x] **作業内容**: 未使用インポートの削除
- [x] **ツール**: `ruff check --fix app/`
- [ ] **終了条件**: Lintエラーなし
- [x] **検証方法**: `ruff check app/`

### Task 6.2: コードフォーマット
- [x] **開始条件**: Task 6.1完了
- [x] **作業内容**: 全修正ファイルのフォーマット
- [x] **コマンド**: `black app/services/fetch_worker.py app/db/queries.py app/services/fetcher.py`
- [ ] **終了条件**: フォーマット完了
- [x] **検証方法**: `black --check app/`

### Task 6.3: 型チェック（オプション）
- [ ] **開始条件**: Task 6.2完了
- [ ] **作業内容**: 型アノテーションの確認
- [ ] **コマンド**: `mypy app/services/fetch_worker.py app/db/queries.py`
- [ ] **終了条件**: 重大な型エラーなし
- [ ] **検証方法**: mypyの出力確認

---

## ✅ 最終確認チェックリスト

### コード変更の確認
- [ ] `app/services/fetch_worker.py`: session.begin()削除
- [ ] `app/db/queries.py`: 日付検証追加
- [ ] `app/db/queries.py`: 二分探索実装
- [ ] `app/services/fetcher.py`: auto_adjust追加
- [ ] `app/utils/date_utils.py`: 新規作成

### テストファイルの確認
- [ ] `tests/unit/test_fetch_worker_transaction.py`: 作成
- [ ] `tests/unit/test_date_boundary.py`: 作成
- [ ] `tests/unit/test_yfinance_warnings.py`: 作成
- [ ] `tests/unit/test_data_availability.py`: 作成
- [ ] `tests/integration/test_all_fixes.py`: 作成

### 動作確認
- [ ] 全単体テストパス: `pytest tests/unit/ -v`
- [ ] 統合テストパス: `pytest tests/integration/ -v`
- [ ] 検証スクリプト成功: `python scripts/verify_fixes.py`
- [ ] Lintチェック通過: `ruff check app/`

---

## 📝 実装者への注意事項

1. **トランザクション管理（P1）**: `session.begin()`を削除する際、インデントに注意
2. **日付処理（P2, P4）**: dateオブジェクトの比較は`>`や`<`を使用
3. **YFinance（P3）**: `auto_adjust=True`を全箇所に明示的に追加
4. **テスト**: モックを使用して外部依存を排除
5. **エラーハンドリング**: try-exceptは最小限に、ログは適切に

## 🚀 実装開始

このタスクリストに従って、上から順番に実装を進めてください。
各タスクは独立しており、完了したらチェックボックスにチェックを入れてください。

**推定完了時間**: 4時間（休憩含む）