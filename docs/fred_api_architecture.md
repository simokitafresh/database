# Fred API統合アーキテクチャ設計書

## 1. システム概要

### 1.1 目的
Federal Reserve Economic Data (Fred) APIからDTB3（3ヶ月米国財務省証券金利）データを取得し、既存の株価データシステムに統合する。

### 1.2 主要コンポーネント
```
┌─────────────────────────────────────────────────────┐
│                   Client/Browser                     │
└──────────────────────┬──────────────────────────────┘
                       │ HTTPS
┌──────────────────────▼──────────────────────────────┐
│                  FastAPI Application                │
├─────────────────────────────────────────────────────┤
│  ┌─────────────┐  ┌─────────────┐  ┌────────────┐ │
│  │ Stock API   │  │  Fred API   │  │  Cron Job  │ │
│  │  Router     │  │   Router    │  │   Router   │ │
│  └──────┬──────┘  └──────┬──────┘  └──────┬──────┘ │
│         │                │                 │        │
│  ┌──────▼────────────────▼─────────────────▼──────┐ │
│  │           Service Layer                        │ │
│  ├─────────────────┬───────────────┬──────────────┤ │
│  │ Stock Service   │ Fred Service  │ Cron Service │ │
│  └─────────────────┴───────────────┴──────────────┘ │
│                          │                          │
│  ┌───────────────────────▼─────────────────────────┐ │
│  │            Database Layer (AsyncPG)             │ │
│  └──────────────────────────────────────────────────┘ │
└──────────────────────┬──────────────────────────────┘
                       │
        ┌──────────────▼──────────────┐
        │    PostgreSQL Database      │
        │  ┌────────────────────────┐ │
        │  │ prices  │ fred_series  │ │
        │  │ symbols │ fred_obs...  │ │
        │  └────────────────────────┘ │
        └──────────────────────────────┘
```

## 2. ファイル・フォルダ構成

```
app/
├── api/
│   └── v1/
│       ├── fred.py              # 新規: Fred APIエンドポイント
│       ├── router.py             # 更新: Fredルーター追加
│       └── cron.py               # 更新: Fred更新タスク追加
│
├── services/
│   ├── fred/                    # 新規: Fredサービスパッケージ
│   │   ├── __init__.py
│   │   ├── client.py            # Fred APIクライアント
│   │   ├── fetcher.py           # データ取得ロジック
│   │   ├── processor.py         # データ処理・正規化
│   │   └── updater.py           # 更新ロジック
│   └── cron_tasks.py            # 更新: Fred更新タスク追加
│
├── schemas/
│   └── fred.py                  # 新規: Fredデータスキーマ
│
├── db/
│   └── models.py                # 更新: Fredモデル追加
│
├── migrations/
│   └── versions/
│       └── 009_create_fred_tables.py  # 新規: Fredテーブル作成
│
├── core/
│   └── config.py                # 更新: Fred設定追加
│
└── tests/
    └── fred/                    # 新規: Fredテスト
        ├── test_client.py
        ├── test_endpoints.py
        └── test_service.py
```

## 3. データモデル詳細

### 3.1 fred_series テーブル
```python
class FredSeries(Base):
    """Fred系列マスタテーブル"""
    __tablename__ = "fred_series"
    
    series_id = Column(String(20), primary_key=True)  # 'DTB3'
    title = Column(String(255), nullable=False)
    units = Column(String(50))                        # 'percent'
    units_short = Column(String(10))                  # '%'
    frequency = Column(String(20))                    # 'daily'
    seasonal_adjustment = Column(String(20))          # 'not_seasonally_adjusted'
    observation_start = Column(Date)
    observation_end = Column(Date)
    last_updated = Column(DateTime(timezone=True))
    popularity = Column(Integer)
    notes = Column(Text)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    is_active = Column(Boolean, default=True)
```

### 3.2 fred_observations テーブル
```python
class FredObservation(Base):
    """Fred観測データテーブル"""
    __tablename__ = "fred_observations"
    __table_args__ = (
        PrimaryKeyConstraint('series_id', 'date'),
        Index('idx_fred_obs_date', 'date'),
        Index('idx_fred_obs_series_date', 'series_id', 'date'),
    )
    
    series_id = Column(String(20), ForeignKey('fred_series.series_id'))
    date = Column(Date, nullable=False)
    value = Column(Float)                           # NULL可能（休日など）
    realtime_start = Column(Date)
    realtime_end = Column(Date)
    last_updated = Column(DateTime(timezone=True), server_default=func.now())
```

## 4. API仕様詳細

### 4.1 GET /v1/fred/series
```python
@router.get("/fred/series", response_model=FredSeriesListResponse)
async def list_fred_series(
    active_only: bool = Query(True),
    session: AsyncSession = Depends(get_session)
):
    """利用可能なFred系列一覧を取得"""
    # レスポンス例:
    {
        "series": [
            {
                "series_id": "DTB3",
                "title": "3-Month Treasury Bill Secondary Market Rate",
                "units": "percent",
                "frequency": "daily",
                "observation_start": "1954-01-04",
                "observation_end": "2024-12-20",
                "last_updated": "2024-12-21T10:00:00Z",
                "is_active": true
            }
        ],
        "total": 1
    }
```

### 4.2 GET /v1/fred/series/{series_id}
```python
@router.get("/fred/series/{series_id}", response_model=FredDataResponse)
async def get_fred_series_data(
    series_id: str,
    date_from: Optional[date] = Query(None, alias="from"),
    date_to: Optional[date] = Query(None, alias="to"),
    format: str = Query("json", regex="^(json|csv)$"),
    include_nulls: bool = Query(False),
    session: AsyncSession = Depends(get_session)
):
    """特定Fred系列のデータを取得"""
    # レスポンス例:
    {
        "series": {
            "series_id": "DTB3",
            "title": "3-Month Treasury Bill Secondary Market Rate",
            "units": "percent"
        },
        "observations": [
            {
                "date": "2024-01-02",
                "value": 5.24
            },
            {
                "date": "2024-01-03",
                "value": 5.25
            }
        ],
        "metadata": {
            "count": 250,
            "start_date": "2024-01-02",
            "end_date": "2024-12-20",
            "missing_dates": 0
        }
    }
```

### 4.3 POST /v1/fred/fetch
```python
@router.post("/fred/fetch", response_model=FredFetchJobResponse)
async def create_fred_fetch_job(
    request: FredFetchRequest,
    background_tasks: BackgroundTasks,
    session: AsyncSession = Depends(get_session)
):
    """Fredデータ取得ジョブを作成"""
    # リクエスト:
    {
        "series_ids": ["DTB3"],
        "date_from": "2024-01-01",
        "date_to": "2024-12-31",
        "force_refresh": false
    }
    # レスポンス:
    {
        "job_id": "fred_20241221_120000_abc123",
        "status": "pending",
        "series_count": 1,
        "date_range": {
            "from": "2024-01-01",
            "to": "2024-12-31"
        }
    }
```

### 4.4 GET /v1/fred/coverage
```python
@router.get("/fred/coverage", response_model=FredCoverageResponse)
async def get_fred_coverage(
    session: AsyncSession = Depends(get_session)
):
    """Fredデータのカバレッジ情報を取得"""
    # レスポンス例:
    {
        "coverage": [
            {
                "series_id": "DTB3",
                "total_observations": 18250,
                "date_start": "1954-01-04",
                "date_end": "2024-12-20",
                "missing_count": 0,
                "last_updated": "2024-12-21T10:00:00Z",
                "update_frequency": "daily",
                "next_update": "2024-12-23T10:00:00Z"
            }
        ]
    }
```

## 5. サービス層実装詳細

### 5.1 Fred APIクライアント (fred/client.py)
```python
class FredApiClient:
    """Fred API通信クライアント"""
    
    def __init__(self, api_key: str, base_url: str):
        self.api_key = api_key
        self.base_url = base_url
        self.session = httpx.AsyncClient(
            timeout=30.0,
            limits=httpx.Limits(max_keepalive_connections=5)
        )
    
    async def get_series_info(self, series_id: str) -> dict:
        """系列メタデータ取得"""
        endpoint = f"{self.base_url}/series"
        params = {
            "series_id": series_id,
            "api_key": self.api_key,
            "file_type": "json"
        }
        response = await self.session.get(endpoint, params=params)
        return response.json()
    
    async def get_observations(
        self,
        series_id: str,
        observation_start: Optional[date] = None,
        observation_end: Optional[date] = None,
        limit: int = 100000
    ) -> List[dict]:
        """観測データ取得"""
        endpoint = f"{self.base_url}/series/observations"
        params = {
            "series_id": series_id,
            "api_key": self.api_key,
            "file_type": "json",
            "limit": limit,
            "sort_order": "asc"
        }
        if observation_start:
            params["observation_start"] = observation_start.isoformat()
        if observation_end:
            params["observation_end"] = observation_end.isoformat()
        
        response = await self.session.get(endpoint, params=params)
        data = response.json()
        return data.get("observations", [])
```

### 5.2 データ取得サービス (fred/fetcher.py)
```python
class FredDataFetcher:
    """Fredデータ取得・処理サービス"""
    
    def __init__(self, client: FredApiClient):
        self.client = client
        self.logger = logging.getLogger(__name__)
    
    async def fetch_series_data(
        self,
        series_id: str,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
        batch_size: int = 10000
    ) -> pd.DataFrame:
        """系列データ取得とDataFrame変換"""
        
        # メタデータ取得
        series_info = await self.client.get_series_info(series_id)
        
        # 観測データ取得
        observations = await self.client.get_observations(
            series_id=series_id,
            observation_start=start_date,
            observation_end=end_date
        )
        
        # DataFrame変換
        df = pd.DataFrame(observations)
        df['date'] = pd.to_datetime(df['date'])
        df['value'] = pd.to_numeric(df['value'], errors='coerce')
        
        # 欠損値処理
        df = df.dropna(subset=['value'])
        
        return df, series_info
    
    async def validate_data(self, df: pd.DataFrame, series_id: str) -> bool:
        """データ検証"""
        if df.empty:
            self.logger.warning(f"No data for {series_id}")
            return False
        
        # 重複チェック
        if df.duplicated(subset=['date']).any():
            self.logger.error(f"Duplicate dates found for {series_id}")
            return False
        
        # 異常値チェック（DTB3は0-30%の範囲）
        if series_id == 'DTB3':
            invalid = df[(df['value'] < 0) | (df['value'] > 30)]
            if not invalid.empty:
                self.logger.warning(f"Invalid values found: {invalid}")
        
        return True
```

### 5.3 データベース更新サービス (fred/updater.py)
```python
class FredDataUpdater:
    """Fredデータベース更新サービス"""
    
    async def upsert_series_metadata(
        self,
        session: AsyncSession,
        series_info: dict
    ) -> None:
        """系列メタデータ更新"""
        stmt = insert(FredSeries).values(
            series_id=series_info['id'],
            title=series_info['title'],
            units=series_info['units'],
            frequency=series_info['frequency'],
            observation_start=series_info['observation_start'],
            observation_end=series_info['observation_end'],
            last_updated=datetime.utcnow()
        ).on_conflict_do_update(
            index_elements=['series_id'],
            set_=dict(
                observation_end=series_info['observation_end'],
                last_updated=datetime.utcnow()
            )
        )
        await session.execute(stmt)
    
    async def upsert_observations(
        self,
        session: AsyncSession,
        series_id: str,
        observations: List[dict],
        batch_size: int = 1000
    ) -> tuple[int, int]:
        """観測データバッチ更新"""
        total_inserted = 0
        total_updated = 0
        
        for i in range(0, len(observations), batch_size):
            batch = observations[i:i + batch_size]
            
            stmt = insert(FredObservation).values([
                {
                    'series_id': series_id,
                    'date': obs['date'],
                    'value': obs['value'],
                    'last_updated': datetime.utcnow()
                }
                for obs in batch
            ]).on_conflict_do_update(
                index_elements=['series_id', 'date'],
                set_=dict(
                    value=insert(FredObservation).excluded.value,
                    last_updated=datetime.utcnow()
                )
            )
            
            result = await session.execute(stmt)
            # PostgreSQLではON CONFLICTの詳細カウント取得が難しいため推定
            affected = result.rowcount or len(batch)
            total_inserted += int(affected * 0.3)  # 推定
            total_updated += int(affected * 0.7)   # 推定
        
        return total_inserted, total_updated
```

## 6. Cron統合

### 6.1 日次更新タスク追加
```python
# app/api/v1/cron.py に追加
async def update_fred_data(
    session: AsyncSession,
    symbols: List[str] = ["DTB3"],
    days_back: int = 30
) -> dict:
    """Fred データの日次更新"""
    fred_service = FredService(settings.FRED_API_KEY)
    results = {}
    
    for symbol in symbols:
        try:
            # 直近N日分のデータ取得
            end_date = date.today()
            start_date = end_date - timedelta(days=days_back)
            
            df, series_info = await fred_service.fetch_series_data(
                series_id=symbol,
                start_date=start_date,
                end_date=end_date
            )
            
            # データベース更新
            inserted, updated = await fred_service.upsert_observations(
                session=session,
                series_id=symbol,
                observations=df.to_dict('records')
            )
            
            results[symbol] = {
                'status': 'success',
                'inserted': inserted,
                'updated': updated
            }
            
        except Exception as e:
            logger.error(f"Failed to update {symbol}: {e}")
            results[symbol] = {
                'status': 'failed',
                'error': str(e)
            }
    
    return results

# daily_updateエンドポイント内で呼び出し
@router.post("/daily-update")
async def daily_update(request: CronDailyUpdateRequest, ...):
    # 既存の株価更新処理
    ...
    
    # Fred データ更新を追加
    if not request.dry_run:
        fred_results = await update_fred_data(
            session=session,
            symbols=["DTB3"],
            days_back=settings.FRED_UPDATE_DAYS
        )
        logger.info(f"Fred update results: {fred_results}")
```

## 7. エラーハンドリング

### 7.1 Fred固有のエラークラス
```python
# app/api/errors.py に追加
class FredApiError(HTTPException):
    """Fred API関連エラー"""
    def __init__(self, message: str, status_code: int = 500):
        super().__init__(
            status_code=status_code,
            detail={
                "code": "FRED_API_ERROR",
                "message": message
            }
        )

class FredSeriesNotFoundError(HTTPException):
    """Fred系列が見つからない"""
    def __init__(self, series_id: str):
        super().__init__(
            status_code=404,
            detail={
                "code": "FRED_SERIES_NOT_FOUND",
                "message": f"Series '{series_id}' not found",
                "series_id": series_id
            }
        )

class FredDataValidationError(HTTPException):
    """Fredデータ検証エラー"""
    def __init__(self, series_id: str, reason: str):
        super().__init__(
            status_code=422,
            detail={
                "code": "FRED_DATA_VALIDATION_ERROR",
                "message": f"Invalid data for series '{series_id}': {reason}",
                "series_id": series_id,
                "reason": reason
            }
        )
```

### 7.2 リトライ戦略
```python
class FredApiRetryStrategy:
    """Fred APIリトライ戦略"""
    
    def __init__(
        self,
        max_retries: int = 3,
        base_delay: float = 1.0,
        max_delay: float = 60.0
    ):
        self.max_retries = max_retries
        self.base_delay = base_delay
        self.max_delay = max_delay
    
    async def execute_with_retry(self, func, *args, **kwargs):
        """指数バックオフでリトライ"""
        last_exception = None
        
        for attempt in range(self.max_retries):
            try:
                return await func(*args, **kwargs)
            except (httpx.HTTPStatusError, httpx.TimeoutException) as e:
                last_exception = e
                
                if hasattr(e, 'response') and e.response.status_code == 429:
                    # Rate limit対応
                    retry_after = e.response.headers.get('Retry-After', 60)
                    delay = min(float(retry_after), self.max_delay)
                else:
                    # 指数バックオフ
                    delay = min(
                        self.base_delay * (2 ** attempt),
                        self.max_delay
                    )
                
                logger.warning(
                    f"Retry {attempt + 1}/{self.max_retries} after {delay}s"
                )
                await asyncio.sleep(delay)
        
        raise last_exception
```

## 8. パフォーマンス最適化

### 8.1 キャッシュ戦略
```python
from functools import lru_cache
from datetime import datetime, timedelta

class FredDataCache:
    """Fredデータキャッシュ"""
    
    def __init__(self, ttl_seconds: int = 3600):
        self.cache = {}
        self.ttl = ttl_seconds
    
    def get_cache_key(self, series_id: str, start: date, end: date) -> str:
        """キャッシュキー生成"""
        return f"{series_id}:{start}:{end}"
    
    def get(self, key: str) -> Optional[pd.DataFrame]:
        """キャッシュ取得"""
        if key in self.cache:
            data, timestamp = self.cache[key]
            if datetime.utcnow() - timestamp < timedelta(seconds=self.ttl):
                return data
            else:
                del self.cache[key]
        return None
    
    def set(self, key: str, data: pd.DataFrame) -> None:
        """キャッシュ設定"""
        self.cache[key] = (data, datetime.utcnow())
    
    def invalidate(self, series_id: Optional[str] = None) -> None:
        """キャッシュ無効化"""
        if series_id:
            keys_to_delete = [
                k for k in self.cache.keys()
                if k.startswith(f"{series_id}:")
            ]
            for key in keys_to_delete:
                del self.cache[key]
        else:
            self.cache.clear()
```

### 8.2 バッチ処理最適化
```python
class OptimizedFredUpdater:
    """最適化されたFred更新処理"""
    
    async def bulk_update_with_copy(
        self,
        session: AsyncSession,
        series_id: str,
        df: pd.DataFrame
    ) -> int:
        """PostgreSQL COPYを使用した高速一括更新"""
        
        # 一時テーブル作成
        temp_table = f"temp_fred_{series_id}_{int(time.time())}"
        await session.execute(text(f"""
            CREATE TEMP TABLE {temp_table} (
                series_id VARCHAR,
                date DATE,
                value FLOAT,
                last_updated TIMESTAMPTZ
            )
        """))
        
        # COPYでデータ投入
        conn = await session.connection()
        raw_conn = await conn.get_raw_connection()
        
        copy_sql = f"""
            COPY {temp_table} (series_id, date, value, last_updated)
            FROM STDIN WITH CSV
        """
        
        # データをCSV形式で準備
        buffer = io.StringIO()
        df['series_id'] = series_id
        df['last_updated'] = datetime.utcnow()
        df.to_csv(buffer, index=False, header=False)
        buffer.seek(0)
        
        # COPY実行
        await raw_conn.driver_connection.copy_expert(copy_sql, buffer)
        
        # UPSERT実行
        await session.execute(text(f"""
            INSERT INTO fred_observations (series_id, date, value, last_updated)
            SELECT series_id, date, value, last_updated
            FROM {temp_table}
            ON CONFLICT (series_id, date)
            DO UPDATE SET
                value = EXCLUDED.value,
                last_updated = EXCLUDED.last_updated
        """))
        
        # 一時テーブル削除
        await session.execute(text(f"DROP TABLE {temp_table}"))
        
        return len(df)
```

## 9. 設定ファイル更新

### 9.1 環境変数 (.env)
```env
# Fred API設定
FRED_API_KEY=your-fred-api-key-here
FRED_BASE_URL=https://api.stlouisfed.org/fred
FRED_UPDATE_DAYS=30
FRED_BATCH_SIZE=1000
FRED_CACHE_TTL=3600
FRED_RATE_LIMIT=120  # requests per minute
FRED_TIMEOUT=30
```

### 9.2 設定クラス (core/config.py)
```python
class Settings(BaseSettings):
    # 既存の設定...
    
    # Fred API設定
    FRED_API_KEY: str = ""
    FRED_BASE_URL: str = "https://api.stlouisfed.org/fred"
    FRED_UPDATE_DAYS: int = 30
    FRED_BATCH_SIZE: int = 1000
    FRED_CACHE_TTL: int = 3600
    FRED_RATE_LIMIT: int = 120
    FRED_TIMEOUT: int = 30
    FRED_SERIES_WHITELIST: List[str] = ["DTB3"]  # 許可する系列ID
    
    @validator("FRED_API_KEY")
    def validate_fred_api_key(cls, v):
        if not v:
            logger.warning("FRED_API_KEY not set, Fred features will be disabled")
        return v
```

## 10. テスト戦略

### 10.1 単体テスト
```python
# tests/fred/test_client.py
import pytest
from unittest.mock import AsyncMock, patch

class TestFredApiClient:
    @pytest.fixture
    def client(self):
        return FredApiClient(api_key="test_key", base_url="http://test")
    
    @pytest.mark.asyncio
    async def test_get_series_info(self, client):
        with patch.object(client.session, 'get') as mock_get:
            mock_get.return_value = AsyncMock(
                json=AsyncMock(return_value={
                    "seriess": [{
                        "id": "DTB3",
                        "title": "3-Month Treasury Bill"
                    }]
                })
            )
            
            result = await client.get_series_info("DTB3")
            assert result["seriess"][0]["id"] == "DTB3"
```

### 10.2 統合テスト
```python
# tests/fred/test_integration.py
@pytest.mark.integration
class TestFredIntegration:
    @pytest.mark.asyncio
    async def test_end_to_end_flow(self, test_db):
        """エンドツーエンドのデータ取得・保存フロー"""
        # 1. Fred APIからデータ取得
        client = FredApiClient(settings.FRED_API_KEY)
        data = await client.get_observations("DTB3", limit=10)
        
        # 2. データベースに保存
        updater = FredDataUpdater()
        await updater.upsert_observations(
            session=test_db,
            series_id="DTB3",
            observations=data
        )
        
        # 3. 検証
        result = await test_db.execute(
            select(FredObservation).where(
                FredObservation.series_id == "DTB3"
            )
        )
        assert len(result.all()) == 10
```

## 11. モニタリング・ログ

### 11.1 メトリクス収集
```python
class FredMetrics:
    """Fred APIメトリクス収集"""
    
    def __init__(self):
        self.api_calls = 0
        self.api_errors = 0
        self.data_points_fetched = 0
        self.cache_hits = 0
        self.cache_misses = 0
        self.last_update = None
    
    async def log_api_call(self, series_id: str, success: bool, records: int = 0):
        """API呼び出しログ"""
        self.api_calls += 1
        if not success:
            self.api_errors += 1
        else:
            self.data_points_fetched += records
        
        logger.info(
            "Fred API call",
            extra={
                "series_id": series_id,
                "success": success,
                "records": records,
                "total_calls": self.api_calls,
                "error_rate": self.api_errors / max(self.api_calls, 1)
            }
        )
```

### 11.2 ヘルスチェック追加
```python
# app/api/v1/health.py に追加
@router.get("/health/fred")
async def fred_health(session: AsyncSession = Depends(get_session)):
    """Fred統合のヘルスチェック"""
    try:
        # データベース接続確認
        result = await session.execute(text("SELECT COUNT(*) FROM fred_series"))
        series_count = result.scalar()
        
        # 最新データ確認
        latest = await session.execute(text("""
            SELECT MAX(date) as latest_date
            FROM fred_observations
            WHERE series_id = 'DTB3'
        """))
        latest_date = latest.scalar()
        
        # Fred API疎通確認（軽量エンドポイント）
        client = FredApiClient(settings.FRED_API_KEY)
        api_status = "unknown"
        try:
            await client.get_series_info("DTB3")
            api_status = "healthy"
        except Exception:
            api_status = "unhealthy"
        
        return {
            "status": "healthy" if api_status == "healthy" else "degraded",
            "fred_api": api_status,
            "series_count": series_count,
            "latest_dtb3_date": latest_date.isoformat() if latest_date else None,
            "timestamp": datetime.utcnow().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Fred health check failed: {e}")
        return {
            "status": "unhealthy",
            "error": str(e),
            "timestamp": datetime.utcnow().isoformat()
        }
```

## 12. デプロイメント更新

### 12.1 render.yaml更新
```yaml
services:
  - type: web
    name: stockdata-api
    # 既存の設定...
    envVars:
      # 既存の環境変数...
      - key: FRED_API_KEY
        sync: false  # シークレット
      - key: FRED_BASE_URL
        value: "https://api.stlouisfed.org/fred"
      - key: FRED_UPDATE_DAYS
        value: "30"
      - key: FRED_BATCH_SIZE
        value: "1000"
      - key: FRED_CACHE_TTL
        value: "3600"
```

### 12.2 Docker対応
```dockerfile
# docker/Dockerfile に追加
# Fred API用の追加パッケージ
RUN pip install httpx pandas numpy
```

## 13. 実装順序

1. **Phase 1: 基盤構築**（1-2日）
   - データベーステーブル作成（マイグレーション）
   - Pydanticスキーマ定義
   - 基本的なFred APIクライアント

2. **Phase 2: コア機能**（2-3日）
   - データ取得サービス実装
   - データベース更新ロジック
   - 基本的なAPIエンドポイント

3. **Phase 3: 統合**（1-2日）
   - Cron統合
   - エラーハンドリング強化
   - キャッシュ実装

4. **Phase 4: 最適化**（1日）
   - バッチ処理最適化
   - パフォーマンスチューニング
   - モニタリング追加

5. **Phase 5: テスト・デプロイ**（1日）
   - 統合テスト
   - ドキュメント整備
   - 本番デプロイ

## 14. セキュリティ考慮事項

1. **APIキー管理**
   - 環境変数で管理
   - Renderではシークレット設定
   - ログには出力しない

2. **レート制限**
   - Fred API: 120 req/min制限遵守
   - 内部キューイング実装

3. **入力検証**
   - 系列IDホワイトリスト
   - 日付範囲制限（最大10年など）

4. **データ検証**
   - 異常値チェック
   - NULL値処理
   - 重複データ防止

## 15. 運用・保守

### 15.1 定期メンテナンス
- 週次: データ整合性チェック
- 月次: 古いキャッシュクリア
- 四半期: パフォーマンス分析

### 15.2 トラブルシューティング
- Fred API障害時: キャッシュからサービス継続
- データ欠損: 自動補完または警告
- Rate limit超過: 自動バックオフ

### 15.3 将来の拡張性
- 複数系列対応（DGS10、DEXUSEU等）
- リアルタイム更新（WebSocket）
- データ分析機能（移動平均、相関等）
