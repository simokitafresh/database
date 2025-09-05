# 未登録銘柄自動登録機能 - 詳細実装タスクリスト

## 📋 プロジェクト概要
yfinance APIを使用して、未登録銘柄を自動的に検証・登録する機能を実装する。

## 背景と目的
**WHY**: 現在、symbolsテーブルに事前登録されていない銘柄は取得できない。ユーザーが任意の銘柄を取得したい場合、管理者による手動登録が必要で利便性が低い。

**WHAT**: yfinance APIで銘柄の存在を確認し、存在する場合は自動的にsymbolsテーブルに登録する機能を追加する。

## 前提条件
- Python 3.12環境 ✓
- 既存のStock OHLCV APIプロジェクト ✓
- yfinanceライブラリインストール済み（Yahoo Finance APIラッパー）✓
- PostgreSQL（Supabase）接続設定済み ✓
- FastAPI フレームワーク ✓
- SQLAlchemy 2.0 (async) ✓
- Pydantic v2 ✓
- 既存のテストフレームワーク（pytest + pytest-asyncio）✓

## 現在のフォルダー構造
```
app/
├── api/
│   ├── deps.py           # 依存性注入 ✓
│   ├── errors.py         # エラー定義 ✓
│   └── v1/
│       ├── prices.py     # 価格API ✓
│       ├── symbols.py    # シンボルAPI ✓
│       ├── coverage.py   # カバレッジAPI ✓
│       ├── fetch.py      # フェッチジョブAPI ✓
│       └── health.py     # ヘルスチェック ✓
├── core/
│   ├── config.py         # アプリケーション設定 ✓
│   ├── cors.py           # CORS設定 ✓
│   ├── logging.py        # ログ設定 ✓
│   └── middleware.py     # ミドルウェア ✓
├── db/
│   ├── engine.py         # データベースエンジン ✓
│   ├── models.py         # SQLAlchemyモデル ✓
│   ├── queries.py        # データベースクエリ ✓
│   └── utils.py          # DB ユーティリティ ✓
├── schemas/
│   ├── common.py         # 共通スキーマ ✓
│   ├── prices.py         # 価格スキーマ ✓
│   ├── symbols.py        # シンボルスキーマ ✓
│   ├── coverage.py       # カバレッジスキーマ ✓
│   └── fetch_jobs.py     # フェッチジョブスキーマ ✓
├── services/
│   ├── fetcher.py        # yfinance データフェッチ ✓
│   ├── normalize.py      # 銘柄正規化 ✓
│   ├── resolver.py       # データ解決 ✓
│   ├── upsert.py         # データアップサート ✓
│   ├── coverage.py       # カバレッジ分析 ✓
│   ├── fetch_jobs.py     # フェッチジョブ管理 ✓
│   ├── fetch_worker.py   # フェッチワーカー ✓
│   ├── query_optimizer.py # クエリ最適化 ✓
│   ├── symbol_validator.py     # 【新規作成予定】
│   └── auto_register.py        # 【新規作成予定】
└── tests/                       # 【テスト拡張予定】
    ├── unit/             # 既存ユニットテスト ✓
    ├── e2e/              # 既存E2Eテスト ✓
    ├── test_symbol_validator.py # 【新規作成予定】
    ├── test_auto_register.py    # 【新規作成予定】
    └── test_api_auto_register.py # 【新規作成予定】
```

---

## タスク一覧

### 1. 銘柄検証サービスの作成

#### タスク 1.1: yfinance銘柄検証関数の作成
- [ ] **ファイル**: `app/services/symbol_validator.py`を新規作成
- [ ] **WHY**: yfinance APIで銘柄が実在するか確認するため
- [ ] **WHAT**: 
  ```python
  def validate_symbol_exists(symbol: str) -> bool:
      """
      yfinance.Ticker(symbol).infoを呼び出し、
      'symbol'キーが存在するかで判定。
      HTTPError 404 = 銘柄なし
      データ取得成功 = 銘柄あり
      """
  ```
- [ ] **例外処理**: HTTPError(404), KeyError, TimeoutError, ConnectionErrorをキャッチ
- [ ] **タイムアウト**: 10秒設定

#### タスク 1.2: 銘柄情報取得関数の作成
- [ ] **ファイル**: `app/services/symbol_validator.py`に追加
- [ ] **WHY**: エラー詳細をユーザーに返すため
- [ ] **WHAT**:
  ```python
  def get_symbol_info(symbol: str) -> Dict[str, Any]:
      """
      戻り値例:
      {"symbol": "AAPL", "exists": True, "error": None}
      {"symbol": "XXXYYY", "exists": False, "error": "Symbol not found in Yahoo Finance"}
      """
  ```
- [ ] **yfinance使用箇所**: `yf.Ticker(symbol).info`

---

### 2. 自動登録サービスの作成

#### タスク 2.1: 自動登録メイン関数の作成
- [ ] **ファイル**: `app/services/auto_register.py`を新規作成
- [ ] **WHY**: 銘柄検証→DB登録の一連の流れを管理
- [ ] **WHAT**:
  ```python
  async def auto_register_symbol(session: AsyncSession, symbol: str) -> bool:
      """
      1. normalize_symbol()で正規化
      2. symbol_exists_in_db()でDB確認
      3. 未登録ならvalidate_symbol_exists()でyfinance確認
      4. 存在するならinsert_symbol()でDB登録
      """
  ```
- [ ] **インポート**: 
  ```python
  from sqlalchemy.ext.asyncio import AsyncSession
  from sqlalchemy import text
  from app.services.normalize import normalize_symbol
  from app.services.symbol_validator import validate_symbol_exists
  import logging
  
  logger = logging.getLogger(__name__)
  ```

#### タスク 2.2: 銘柄存在確認クエリの作成
- [ ] **ファイル**: `app/services/auto_register.py`に追加
- [ ] **WHY**: 既に登録済みの銘柄は再登録不要
- [ ] **WHAT**:
  ```python
  async def symbol_exists_in_db(session: AsyncSession, symbol: str) -> bool:
      result = await session.execute(
          text("SELECT COUNT(*) FROM symbols WHERE symbol = :symbol"),
          {"symbol": symbol}
      )
      return result.scalar() > 0
  ```

#### タスク 2.3: 銘柄登録SQL実行関数の作成
- [ ] **ファイル**: `app/services/auto_register.py`に追加
- [ ] **WHY**: symbolsテーブルへの挿入処理
- [ ] **WHAT**:
  ```python
  async def insert_symbol(session: AsyncSession, symbol: str) -> bool:
      """
      Insert new symbol into database with minimal information.
      
      INSERT INTO symbols (symbol, is_active, name, exchange, currency, first_date, last_date)
      VALUES (:symbol, true, NULL, NULL, NULL, NULL, NULL)
      ON CONFLICT (symbol) DO NOTHING
      """
      try:
          result = await session.execute(
              text("""
                  INSERT INTO symbols (symbol, is_active, name, exchange, currency, first_date, last_date)
                  VALUES (:symbol, true, NULL, NULL, NULL, NULL, NULL)
                  ON CONFLICT (symbol) DO NOTHING
              """),
              {"symbol": symbol}
          )
          await session.commit()
          return result.rowcount > 0
      except Exception as e:
          await session.rollback()
          raise e
  ```
- [ ] **注意**: name, exchange, currency, first_date, last_dateはNULLで登録（最小限の情報）

---

### 3. エラーハンドリングの追加

#### タスク 3.1: Yahoo Finance銘柄不存在エラーの作成
- [ ] **ファイル**: `app/api/errors.py`に追加
- [ ] **WHY**: ユーザーに銘柄が存在しないことを明確に伝える
- [ ] **WHAT**:
  ```python
  # 新しいエラーコード（既存のエラーコード定義部分に追加）
  SYMBOL_NOT_EXISTS = "SYMBOL_NOT_EXISTS"
  AUTO_REGISTRATION_FAILED = "AUTO_REGISTRATION_FAILED"
  
  class SymbolNotExistsError(HTTPException):
      """Exception raised when symbol does not exist in Yahoo Finance."""
      def __init__(self, symbol: str):
          super().__init__(
              status_code=404,
              detail={
                  "code": SYMBOL_NOT_EXISTS,
                  "message": f"Symbol '{symbol}' does not exist in Yahoo Finance",
                  "symbol": symbol
              }
          )
  ```

#### タスク 3.2: 自動登録失敗エラーの作成
- [ ] **ファイル**: `app/api/errors.py`に追加
- [ ] **WHY**: DB登録失敗を通知
- [ ] **WHAT**:
  ```python
  class SymbolRegistrationError(HTTPException):
      """Exception raised when automatic symbol registration fails."""
      def __init__(self, symbol: str, reason: str):
          super().__init__(
              status_code=500,
              detail={
                  "code": AUTO_REGISTRATION_FAILED,
                  "message": f"Failed to auto-register symbol '{symbol}': {reason}",
                  "symbol": symbol,
                  "reason": reason
              }
          )
  ```

---

### 4. 設定の追加

#### タスク 4.1: 環境変数の追加
- [ ] **ファイル**: `app/core/config.py`を修正
- [ ] **WHY**: 機能のON/OFF切り替えとタイムアウト設定
- [ ] **WHAT**:
  ```python
  class Settings(BaseSettings):
      # ... 既存の設定 ...
      
      # 自動登録機能
      ENABLE_AUTO_REGISTRATION: bool = True
      AUTO_REGISTER_TIMEOUT: int = 15  # 全体のタイムアウト
      YF_VALIDATE_TIMEOUT: int = 10    # yfinance検証のタイムアウト
      AUTO_REGISTER_MAX_PARALLEL: int = 3  # 並行処理数
      AUTO_REGISTER_BATCH_SIZE: int = 10  # バッチ登録サイズ
  ```
- [ ] **挿入位置**: Fetch Job Settingsの後

---

### 5. API エンドポイントの修正

#### タスク 5.1: 自動登録処理の統合
- [ ] **ファイル**: `app/api/v1/prices.py`の`get_prices`関数を修正
- [ ] **WHY**: 既存のAPIに自動登録機能を組み込む
- [ ] **WHAT**: 
  ```python
  async def get_prices(...):
      # ... 既存のバリデーション（_parse_and_validate_symbols）...
      
      # 新規追加: 自動登録処理
      if settings.ENABLE_AUTO_REGISTRATION:
          await ensure_symbols_registered(session, symbols_list)
      
      # 既存のensure_coverageより前に実行
      await queries.ensure_coverage(
          session=session,
          symbols=symbols_list,
          date_from=from_date,
          date_to=to_date,
          refetch_days=settings.YF_REFETCH_DAYS
      )
  ```
- [ ] **挿入位置**: `queries.ensure_coverage`の直前

#### タスク 5.2: 自動登録ロジック関数の実装
- [ ] **ファイル**: `app/api/v1/prices.py`に追加
- [ ] **WHY**: 複数銘柄をループして処理
- [ ] **WHAT**:
  ```python
  async def ensure_symbols_registered(
      session: AsyncSession, 
      symbols: List[str]
  ) -> None:
      """
      for symbol in symbols:
          1. DB確認
          2. 未登録ならyfinance確認
          3. 存在するなら登録
          4. 存在しないならSymbolNotExistsError発生
      """
  ```
- [ ] **インポート追加**: 
  ```python
  from app.services.auto_register import auto_register_symbol, ensure_symbols_registered
  ```
- [ ] **挿入位置**: 既存のインポート文の後、`normalize_symbol`インポートの近く

---

### 6. ロギングの追加

#### タスク 6.1: 自動登録ログの追加
- [ ] **ファイル**: `app/services/auto_register.py`の各関数
- [ ] **WHY**: デバッグとモニタリング
- [ ] **WHAT**:
  ```python
  logger.info(f"Auto-registering new symbol: {symbol}")
  logger.warning(f"Symbol {symbol} not found in Yahoo Finance")
  logger.error(f"Failed to register {symbol}: {error}")
  ```

#### タスク 6.2: APIログの追加
- [ ] **ファイル**: `app/api/v1/prices.py`
- [ ] **WHY**: API呼び出しレベルでの追跡
- [ ] **WHAT**:
  ```python
  logger.info(f"Checking registration for symbols: {symbols}")
  logger.info(f"Successfully auto-registered: {symbol}")
  ```

---

### 7. ユニットテストの作成

#### タスク 7.1: yfinance銘柄検証テスト
- [ ] **ファイル**: `tests/unit/test_symbol_validator.py`を作成
- [ ] **WHY**: yfinance連携の動作確認
- [ ] **WHAT**:
  ```python
  import pytest
  from app.services.symbol_validator import validate_symbol_exists, get_symbol_info
  
  def test_valid_symbol():
      """既存の銘柄（AAPL）が正常に検証される"""
      assert validate_symbol_exists("AAPL") == True
      
  def test_invalid_symbol():
      """存在しない銘柄（XXXYYY）が正しく失敗する"""
      assert validate_symbol_exists("XXXYYY") == False
      
  def test_timeout():
      """タイムアウト処理のテスト（モック使用）"""
      # モックでタイムアウトをシミュレート
      
  def test_get_symbol_info_valid():
      """銘柄情報取得のテスト - 有効な銘柄"""
      info = get_symbol_info("AAPL")
      assert info["symbol"] == "AAPL"
      assert info["exists"] == True
      assert info["error"] is None
  ```

#### タスク 7.2: 自動登録テスト  
- [ ] **ファイル**: `tests/unit/test_auto_register.py`を作成
- [ ] **WHY**: DB操作の正確性確認
- [ ] **WHAT**:
  ```python
  import pytest
  from sqlalchemy.ext.asyncio import AsyncSession
  from app.services.auto_register import (
      auto_register_symbol, 
      symbol_exists_in_db, 
      insert_symbol,
      ensure_symbols_registered
  )
  from app.db.engine import create_engine_and_sessionmaker
  
  @pytest.mark.asyncio
  async def test_register_new_symbol(async_session: AsyncSession):
      """新しい銘柄の登録テスト"""
      # テスト用の未登録銘柄でテスト
      result = await auto_register_symbol(async_session, "MSFT")
      assert result == True
      
  @pytest.mark.asyncio  
  async def test_skip_existing_symbol(async_session: AsyncSession):
      """既存銘柄のスキップテスト"""
      # 既に登録済みの銘柄でテスト
      result = await auto_register_symbol(async_session, "AAPL")
      assert result == False  # 既存なのでスキップ
      
  @pytest.mark.asyncio
  async def test_invalid_symbol_error(async_session: AsyncSession):
      """無効な銘柄でのエラーテスト"""
      with pytest.raises(Exception):  # SymbolNotExistsError
          await auto_register_symbol(async_session, "XXXYYY")
  ```

#### タスク 7.3: API統合テスト
- [ ] **ファイル**: `tests/e2e/test_api_auto_register.py`を作成
- [ ] **WHY**: エンドツーエンドの動作確認
- [ ] **WHAT**:
  ```python
  import pytest
  from fastapi.testclient import TestClient
  from app.main import app
  from app.core.config import settings
  
  client = TestClient(app)
  
  @pytest.mark.asyncio
  async def test_api_with_unregistered_symbol():
      """未登録銘柄での API テスト"""
      # 事前に銘柄が未登録であることを確認
      response = client.get("/v1/prices?symbols=TSLA&from=2024-01-01&to=2024-01-31")
      assert response.status_code == 200
      data = response.json()
      assert "prices" in data
      
  @pytest.mark.asyncio
  async def test_api_with_invalid_symbol():
      """無効な銘柄での API テスト"""
      response = client.get("/v1/prices?symbols=XXXYYY&from=2024-01-01&to=2024-01-31")
      assert response.status_code == 404
      data = response.json()
      assert data["error"]["code"] == "SYMBOL_NOT_EXISTS"
      
  @pytest.mark.asyncio 
  async def test_auto_registration_disabled():
      """自動登録無効時のテスト"""
      # 設定で自動登録を無効にしてテスト
      # （モックまたは一時的な設定変更）
      pass
  ```

---

### 8. 並行処理の最適化

#### タスク 8.1: 並行バリデーションの実装
- [ ] **ファイル**: `app/services/auto_register.py`を修正
- [ ] **WHY**: 複数銘柄の検証を高速化（5銘柄×3秒→3秒）
- [ ] **WHAT**:
  ```python
  async def validate_symbols_parallel(symbols: List[str]) -> Dict[str, bool]:
      """
      asyncio.gather()とrun_in_threadpoolで
      yfinance呼び出しを並行実行
      最大5並行（セマフォで制御）
      """
  ```
- [ ] **注意**: yfinanceは同期APIなのでrun_in_threadpool必要

#### タスク 8.2: バッチ登録の実装
- [ ] **ファイル**: `app/services/auto_register.py`を修正
- [ ] **WHY**: DB操作を1トランザクションにまとめて高速化
- [ ] **WHAT**:
  ```python
  async def batch_register_symbols(
      session: AsyncSession, 
      symbols: List[str]
  ) -> Dict[str, bool]:
      """
      INSERT INTO symbols (symbol, is_active)
      VALUES 
        ('TSLA', true),
        ('RIVN', true)
      ON CONFLICT DO NOTHING
      """
  ```

---

### 9. 既存コードの調整

#### タスク 9.1: ensure_coverage関数のエラー改善
- [ ] **ファイル**: `app/db/queries.py`の`ensure_coverage`関数
- [ ] **WHY**: 銘柄不在時のエラーメッセージ改善
- [ ] **WHAT**:
  ```python
  # 外部キー違反をキャッチして詳細メッセージ
  except IntegrityError as e:
      if "foreign key violation" in str(e):
          raise ValueError(f"Symbol {symbol} not registered in database")
  ```

#### タスク 9.2: 正規化の適用
- [ ] **ファイル**: `app/services/auto_register.py`
- [ ] **WHY**: BRK.B → BRK-B のような変換統一
- [ ] **WHAT**:
  ```python
  from app.services.normalize import normalize_symbol
  
  async def auto_register_symbol(session, symbol):
      symbol = normalize_symbol(symbol)  # 必ず最初に実行
  ```

---

### 10. ドキュメント更新

#### タスク 10.1: APIドキュメントの更新
- [ ] **ファイル**: `app/api/v1/prices.py`のdocstring
- [ ] **WHY**: API利用者への情報提供
- [ ] **WHAT**:
  ```python
  """
  Get prices endpoint.
  
  Note: If ENABLE_AUTO_REGISTRATION is True, unregistered symbols
  will be automatically validated against Yahoo Finance and registered.
  First-time fetch may take 5-10 seconds per new symbol.
  """
  ```

#### タスク 10.2: 環境変数ドキュメントの追加
- [ ] **ファイル**: `.env.example`を更新
- [ ] **WHY**: デプロイ時の設定ガイド
- [ ] **WHAT**:
  ```bash
  # Auto-registration settings
  ENABLE_AUTO_REGISTRATION=true      # Enable automatic symbol registration
  AUTO_REGISTER_TIMEOUT=15           # Total timeout for registration process (seconds)
  YF_VALIDATE_TIMEOUT=10             # Timeout for Yahoo Finance validation (seconds)
  AUTO_REGISTER_MAX_PARALLEL=3       # Maximum parallel validation processes
  AUTO_REGISTER_BATCH_SIZE=10        # Batch size for symbol registration
  ```
- [ ] **挿入位置**: Fetch Job Settingsセクションの後

---

## 実装順序（推奨）

1. **基盤作成**: タスク1, 2（yfinance連携とDB操作）
2. **エラー処理**: タスク3, 4（例外とと設定）
3. **統合**: タスク5, 6（API組み込み）
4. **テスト**: タスク7（動作確認）
5. **最適化**: タスク8, 9（性能改善）
6. **文書化**: タスク10（ドキュメント）

## 完了基準

- [ ] 未登録銘柄（例: NVDA、TSLA）のAPI呼び出しが成功する
- [ ] 無効銘柄（例: XXXYYY）は404エラー（SYMBOL_NOT_EXISTS）を返す
- [ ] 2回目以降のアクセスは高速（DBキャッシュ利用、自動登録スキップ）
- [ ] ログで自動登録処理を確認できる
- [ ] 全ユニットテストがパスする
- [ ] E2Eテストで実際のAPI経由での動作確認ができる
- [ ] 本番環境（Render）での動作確認が完了する
- [ ] `ENABLE_AUTO_REGISTRATION=false`でも既存機能が正常動作する

## yfinance API仕様メモ（現在の実装ベース）

```python
import yfinance as yf
from datetime import datetime, timedelta

# 銘柄オブジェクト作成
ticker = yf.Ticker("AAPL")

# 銘柄情報取得（存在確認に使用）
try:
    info = ticker.info  # 辞書型、存在しない場合は空のdictまたはHTTPError
    # 存在確認: info.get('symbol') や info.get('regularMarketPrice') の有無で判定
except Exception as e:
    # HTTPError 404またはその他のエラー = 銘柄なし
    print(f"Symbol validation error: {e}")

# よく使うinfoのキー（存在する場合）
symbol = info.get('symbol', 'N/A')           # "AAPL"
short_name = info.get('shortName', 'N/A')    # "Apple Inc."  
exchange = info.get('exchange', 'N/A')       # "NMS"
currency = info.get('currency', 'N/A')      # "USD"
regular_market_price = info.get('regularMarketPrice')  # 現在価格（存在確認に有用）

# 価格データ取得（既存のfetcher.pyで実装済み）
# app/services/fetcher.py の fetch_prices() 関数を参照
start_date = datetime.now() - timedelta(days=365)
end_date = datetime.now()
df = yf.download("AAPL", start=start_date, end=end_date, progress=False)
```

## 注意事項

- yfinance.Ticker().infoは初回呼び出しが遅い（2-5秒）
- Yahoo Financeのレート制限あり（秒間2-5リクエスト推奨）
- yfinanceは同期APIなのでFastAPIでは`run_in_threadpool`使用が必要
- トランザクション管理を適切に（外部キー制約エラー対策）
- 必ずnormalize_symbol()で正規化してから処理
- 既存のfetcher.pyサービスとの整合性を保つ
- 現在のデータベースプールサイズ（5）とmax_overflow（5）を考慮した並行処理設計
- Supabaseクラウドデータベースとの接続安定性を確保