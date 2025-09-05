# 未登録銘柄自動登録機能 - 詳細実装タスクリスト

## 📋 プロジェクト概要
yfinance APIを使用して、未登録銘柄を自動的に検証・登録する機能を実装する。

## 背景と目的
**WHY**: 現在、symbolsテーブルに事前登録されていない銘柄は取得できない。ユーザーが任意の銘柄を取得したい場合、管理者による手動登録が必要で利便性が低い。

**WHAT**: yfinance APIで銘柄の存在を確認し、存在する場合は自動的にsymbolsテーブルに登録する機能を追加する。

## 前提条件
- Python 3.11環境
- 既存のStock OHLCV APIプロジェクト  
- yfinanceライブラリインストール済み（Yahoo Finance APIラッパー）
- PostgreSQL（Supabase）接続設定済み

## 現在のフォルダー構造
```
app/
├── api/
│   ├── deps.py           # 依存性注入（実装済み）
│   ├── errors.py         # エラー定義（実装済み）
│   └── v1/
│       ├── prices.py     # 価格API（修正対象）
│       ├── symbols.py    # 銘柄API（実装済み）
│       ├── coverage.py   # カバレッジAPI（実装済み）
│       ├── fetch.py      # フェッチAPI（実装済み）
│       └── health.py     # ヘルスAPI（実装済み）
├── core/
│   └── config.py         # 設定（修正対象）
├── db/
│   ├── engine.py         # DB接続（実装済み）
│   ├── models.py         # DBモデル（実装済み）
│   ├── queries.py        # DBクエリ（実装済み）
│   └── utils.py          # DBユーティリティ（実装済み）
├── services/
│   ├── coverage.py       # カバレッジサービス（実装済み）
│   ├── fetcher.py        # yfinance利用（実装済み）
│   ├── fetch_jobs.py     # フェッチジョブ（実装済み）
│   ├── fetch_worker.py   # フェッチワーカー（実装済み）
│   ├── normalize.py      # 銘柄正規化（実装済み）
│   ├── resolver.py       # 解決サービス（実装済み）
│   ├── upsert.py         # アップサート（実装済み）
│   ├── query_optimizer.py # クエリ最適化（実装済み）
│   ├── symbol_validator.py     # 【新規作成予定】
│   └── auto_register.py        # 【新規作成予定】
├── schemas/
│   ├── common.py         # 共通スキーマ（実装済み）
│   ├── coverage.py       # カバレッジスキーマ（実装済み）
│   ├── fetch_jobs.py     # フェッチジョブスキーマ（実装済み）
│   ├── prices.py         # 価格スキーマ（実装済み）
│   └── symbols.py        # 銘柄スキーマ（実装済み）
└── tests/                       # 【新規作成予定】
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
- [ ] **インポート**: `from app.services.symbol_validator import validate_symbol_exists`

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
      INSERT INTO symbols (symbol, is_active, first_date, last_date)
      VALUES (:symbol, true, NULL, NULL)
      ON CONFLICT (symbol) DO NOTHING
      """
  ```
- [ ] **注意**: name, exchange, currencyはNULLで登録（最小限の情報）

---

### 3. エラーハンドリングの追加

#### タスク 3.1: Yahoo Finance銘柄不存在エラーの確認・拡張
- [ ] **ファイル**: `app/api/errors.py`を確認・修正
- [ ] **WHY**: ユーザーに銘柄が存在しないことを明確に伝える
- [ ] **現在の実装**: `SymbolNotFoundError`クラスが既に存在（65行目）
- [ ] **WHAT**:
  ```python
  # 既存のSymbolNotFoundErrorを確認し、必要に応じて拡張
  class SymbolNotFoundError(HTTPException):
      """Exception raised when a symbol is not found."""
      def __init__(self, symbol: str, source: str = "database"):
          message = f"Symbol '{symbol}' not found"
          if source == "yfinance":
              message = f"Symbol '{symbol}' does not exist in Yahoo Finance"
          elif source == "database":
              message = f"Symbol '{symbol}' not found in database"
          
          super().__init__(
              status_code=404,
              detail={"code": SYMBOL_NOT_FOUND, "message": message, "symbol": symbol}
          )
  ```
- [ ] **新しいエラーコード追加**: `SYMBOL_NOT_EXISTS = "SYMBOL_NOT_EXISTS"`

#### タスク 3.2: 自動登録失敗エラーの作成
- [ ] **ファイル**: `app/api/errors.py`に追加
- [ ] **WHY**: DB登録失敗を通知
- [ ] **WHAT**:
  ```python
  # 新しいエラーコード
  SYMBOL_REGISTRATION_FAILED = "SYMBOL_REGISTRATION_FAILED"
  
  class SymbolRegistrationError(HTTPException):
      """Exception raised when automatic symbol registration fails."""
      def __init__(self, symbol: str, reason: str):
          super().__init__(
              status_code=500,
              detail={
                  "code": SYMBOL_REGISTRATION_FAILED,
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
      
      # 自動登録機能 (既存のAPI設定セクションに追加)
      ENABLE_AUTO_REGISTRATION: bool = True
      AUTO_REGISTER_TIMEOUT: int = 15  # 全体のタイムアウト
      YF_VALIDATE_TIMEOUT: int = 10    # yfinance検証のタイムアウト（既存のFETCH_TIMEOUT_SECONDSと同様）
      
      # 既存: FETCH_TIMEOUT_SECONDS: int = 8
      # 既存: FETCH_MAX_RETRIES: int = 3
      # 既存: FETCH_BACKOFF_MAX_SECONDS: float = 8.0
  ```

---

### 5. API エンドポイントの修正

#### タスク 5.1: 自動登録処理の統合
- [ ] **ファイル**: `app/api/v1/prices.py`の`get_prices`関数を修正
- [ ] **WHY**: 既存のAPIに自動登録機能を組み込む
- [ ] **現在の実装**: 65行目付近でensure_coverageを呼び出し中
- [ ] **WHAT**: 
  ```python
  async def get_prices(...):
      # --- validation --- (既存)
      if date_to < date_from:
          raise HTTPException(status_code=422, detail="invalid date range")
      symbols_list = _parse_and_validate_symbols(symbols)
      if not symbols_list:
          return []

      # --- 新規追加: 自動登録処理 ---
      if settings.ENABLE_AUTO_REGISTRATION:
          await ensure_symbols_registered(session, symbols_list)

      # --- orchestration --- (既存のensure_coverage処理)
      t0 = time.perf_counter()
      await queries.ensure_coverage(...)
  ```
- [ ] **挿入位置**: `await queries.ensure_coverage`の直前（65行目付近）

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
      自動登録処理：複数銘柄の登録確認と自動登録
      """
      for symbol in symbols:
          try:
              # 1. DB確認（既存チェック）
              # 2. 未登録ならyfinance確認
              # 3. 存在するなら登録、存在しないならSymbolNotExistsError発生
              success = await auto_register_symbol(session, symbol)
              if success:
                  logger.info(f"Successfully auto-registered symbol: {symbol}")
          except Exception as e:
              logger.error(f"Auto-registration failed for {symbol}: {e}")
              # 銘柄不存在の場合は明確なエラーを発生
              if "not found" in str(e).lower():
                  from app.api.errors import SymbolNotFoundError
                  raise SymbolNotFoundError(symbol)
              raise
  ```
- [ ] **インポート追加**: `from app.services.auto_register import auto_register_symbol`
- [ ] **配置**: ファイル上部の関数定義エリア（`_parse_and_validate_symbols`の下）

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
- [ ] **現在のテスト環境**: 既存の`tests/unit/`ディレクトリに多数のテストファイルが存在
- [ ] **WHAT**:
  ```python
  import pytest
  from unittest.mock import patch, MagicMock
  from app.services.symbol_validator import validate_symbol_exists, get_symbol_info
  
  def test_valid_symbol():
      """実在銘柄のテスト"""
      assert validate_symbol_exists("AAPL") == True
      
  def test_invalid_symbol():
      """存在しない銘柄のテスト"""  
      assert validate_symbol_exists("XXXYYY") == False
      
  @patch('app.services.symbol_validator.yf.Ticker')
  def test_timeout_handling(mock_ticker):
      """タイムアウトの処理テスト"""
      # モックでタイムアウトをシミュレート
      pass
  ```
- [ ] **参考**: `tests/unit/test_fetcher.py`（既存のyfinance関連テスト）

#### タスク 7.2: 自動登録テスト  
- [ ] **ファイル**: `tests/unit/test_auto_register.py`を作成
- [ ] **WHY**: DB操作の正確性確認
- [ ] **WHAT**:
  ```python
  import pytest
  from sqlalchemy.ext.asyncio import AsyncSession
  from app.services.auto_register import auto_register_symbol, symbol_exists_in_db
  
  @pytest.mark.asyncio
  async def test_register_new_symbol(async_session: AsyncSession):
      """新規銘柄の登録テスト"""
      # MSFT未登録→登録成功のシナリオ
      pass
      
  @pytest.mark.asyncio  
  async def test_skip_existing_symbol(async_session: AsyncSession):
      """既存銘柄のスキップテスト"""
      # AAPL登録済み→スキップのシナリオ
      pass
      
  @pytest.mark.asyncio
  async def test_invalid_symbol_error(async_session: AsyncSession):
      """無効銘柄のエラーテスト"""
      # XXXYYY→エラーのシナリオ
      pass
  ```
- [ ] **参考**: `tests/unit/test_db_coverage.py`（既存のDB関連テスト）

#### タスク 7.3: API統合テスト
- [ ] **ファイル**: `tests/integration/test_auto_register_api.py`を作成
- [ ] **WHY**: エンドツーエンドの動作確認
- [ ] **現在のintegrationテスト**: `tests/integration/`ディレクトリに複数のAPIテストが存在
- [ ] **WHAT**:
  ```python
  import pytest
  from fastapi.testclient import TestClient
  from app.main import app
  
  client = TestClient(app)
  
  @pytest.mark.asyncio
  async def test_api_with_unregistered_symbol():
      """未登録銘柄での自動登録テスト"""
      response = client.get("/v1/prices?symbols=TSLA&from=2024-01-01&to=2024-01-31")
      assert response.status_code == 200
      
  @pytest.mark.asyncio  
  async def test_api_with_invalid_symbol():
      """無効銘柄でのエラーレスポンステスト"""
      response = client.get("/v1/prices?symbols=XXXYYY&from=2024-01-01&to=2024-01-31")
      assert response.status_code == 404
      assert "SYMBOL_NOT_FOUND" in response.json()["detail"]["code"]
  ```
- [ ] **参考**: `tests/integration/test_fetch_api.py`（既存のAPI統合テスト）

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
- [ ] **ファイル**: `app/db/queries.py`の`ensure_coverage`関数を修正
- [ ] **WHY**: 銘柄が未登録の場合のエラーメッセージ改善
- [ ] **現在の実装**: `ensure_coverage`関数（102行目）が存在し、アドバイザリロック機能を持つ
- [ ] **WHAT**: 
  ```python
  # with_symbol_lockまたは_get_coverage内で外部キー違反をキャッチ
  except IntegrityError as e:
      if "foreign key violation" in str(e).lower():
          raise ValueError(f"Symbol '{symbol}' not registered in symbols table. Enable auto-registration or register manually.")
      raise
  ```
- [ ] **対象関数**: `_get_coverage`または`with_symbol_lock`内の例外処理

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
- [ ] **ファイル**: `.env.example`を作成（または更新）
- [ ] **WHY**: デプロイ時の設定ガイド
- [ ] **現在の環境**: Renderクラウドデプロイメント対応
- [ ] **WHAT**:
  ```bash
  # Auto-registration settings (新規追加)
  ENABLE_AUTO_REGISTRATION=true     # Enable automatic symbol registration
  AUTO_REGISTER_TIMEOUT=15          # Total timeout for registration process (seconds)
  YF_VALIDATE_TIMEOUT=10            # Timeout for Yahoo Finance validation (seconds)
  
  # Existing API settings (参考)
  API_MAX_SYMBOLS=5                 # Maximum symbols per request
  FETCH_TIMEOUT_SECONDS=8           # yfinance fetch timeout
  FETCH_MAX_RETRIES=3               # Retry attempts for failed fetches
  YF_REFETCH_DAYS=30               # Days to refetch recent data
  ```

---

## 実装順序（推奨）

### フェーズ1: 基盤作成 (1-2日)
1. **タスク1**: `symbol_validator.py`作成（yfinance連携）
2. **タスク2**: `auto_register.py`作成（DB操作）
3. **タスク4.1**: 設定追加（config.py修正）

### フェーズ2: エラー処理 (0.5日)
4. **タスク3**: エラーハンドリング（errors.py修正）

### フェーズ3: API統合 (1日)  
5. **タスク5**: API統合（prices.py修正）
6. **タスク6**: ロギング追加

### フェーズ4: テスト (1-2日)
7. **タスク7**: ユニットテスト作成と実行

### フェーズ5: 最適化（オプション、1-2日）
8. **タスク8**: 並行処理最適化
9. **タスク9**: 既存コード調整
10. **タスク10**: ドキュメント更新

## MVP（最小実行可能製品）スコープ

**必須機能（フェーズ1-3）**:
- yfinance銘柄検証
- 基本的な自動登録  
- API統合とエラーハンドリング
- 設定による機能ON/OFF

**後追加可能（フェーズ4-5）**:
- 包括的テストスイート
- 並行処理最適化
- 詳細ロギングと監視
- ドキュメント整備

## 完了基準

### 基本機能確認
- [ ] 未登録銘柄（例: 新しいIPO銘柄）のAPI呼び出しが自動登録後に成功する
- [ ] 無効銘柄（例: XXXYYY）は明確な404エラーを返す  
- [ ] 2回目以降の同一銘柄呼び出しは高速（DBから直接取得）
- [ ] `ENABLE_AUTO_REGISTRATION=false`で機能を無効化できる

### 運用面確認
- [ ] ログで自動登録プロセスを追跡できる
- [ ] yfinance APIエラー時の適切な例外処理
- [ ] 既存機能に影響を与えない（既存のテストがパス）

### パフォーマンス確認
- [ ] 単一銘柄の初回登録: 10秒以内
- [ ] 5銘柄の並行登録: 15秒以内  
- [ ] 既存銘柄のレスポンス時間: 影響なし

## yfinance API仕様メモ

```python
import yfinance as yf

# 銘柄オブジェクト作成
ticker = yf.Ticker("AAPL")

# 銘柄情報取得（存在確認に使用）
info = ticker.info  # 辞書型、存在しない場合はHTTPError 404

# よく使うinfoのキー
info['symbol']       # "AAPL"
info['shortName']    # "Apple Inc."
info['exchange']     # "NMS"
info['currency']     # "USD"

# 価格データ取得（既存のfetcher.pyで実装済み）
df = yf.download("AAPL", start="2024-01-01", end="2024-12-31")
```

## 注意事項

- yfinance.Ticker().infoは初回呼び出しが遅い（2-5秒）
- Yahoo Financeのレート制限あり（秒間2リクエスト推奨）
- yfinanceは同期APIなのでasyncioではrun_in_threadpool使用
- トランザクション管理を適切に（外部キー制約エラー対策）
- 必ずnormalize_symbol()で正規化してから処理