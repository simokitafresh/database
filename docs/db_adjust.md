# 価格調整検出・自動修正機能

## As-Is（現状）

### 現在の仕組み

```
┌─────────────────────────────────────────────────────────────┐
│  データ取得フロー                                            │
├─────────────────────────────────────────────────────────────┤
│  1. yfinance API (auto_adjust=True がデフォルト)            │
│     → 取得時点での調整済み価格を取得                         │
│                                                             │
│  2. DBにUPSERT                                              │
│     → 取得時点の調整済み価格として保存                       │
│                                                             │
│  3. 直近30日リフレッチ (YF_REFETCH_DAYS=30)                 │
│     → 直近30日分のみ再取得して上書き                        │
└─────────────────────────────────────────────────────────────┘
```

### 問題点

| 問題 | 影響 | 具体例 |
|------|------|--------|
| **30日超の古いデータが更新されない** | 配当・分割の調整係数が古いまま | 2024年1月取得のAAPL → その後の配当で0.94%乖離 |
| **累積誤差** | 長期になるほど差が拡大 | 1990年データ → 現在27.45%乖離（AAPL） |
| **分割の未反映** | 10倍程度の価格差 | NVDA 10:1分割 → 旧価格1200、新価格120 |
| **検出手段なし** | 問題に気づけない | 管理者が手動確認するしかない |

### 実データによる検証

```
AAPL 終値の乖離（DBの古い値 vs yfinance最新調整済み）:

日付         DB値      YF調整済    乖離率     原因
─────────────────────────────────────────────────
2025-11-20   266.25    266.25     0.00%     最新（まだ配当落ち前）
2024-11-07   227.48    226.21     0.56%     配当1回分 ($0.25)
2024-01-02   185.64    183.90     0.94%     配当数回分
2023-01-03   125.07    123.21     1.51%     約1年分の配当
1990-01-02   0.33      0.26       27.45%    35年分の累積
```

---

## To-Be（目標状態）

### 新しい仕組み

```
┌─────────────────────────────────────────────────────────────┐
│  調整検出・自動修正フロー                                    │
├─────────────────────────────────────────────────────────────┤
│  1. 定期スキャン（週次 or 日次）                            │
│     → DBの古いデータとyfinance最新値を比較                  │
│                                                             │
│  2. 乖離検出（閾値: 0.001%以上）                            │
│     → 分割/配当/スピンオフ等を自動分類                      │
│                                                             │
│  3. 自動修正（全履歴再取得）                                │
│     → 検出されたシンボルの価格データを削除→再取得           │
│                                                             │
│  4. レポート・通知                                          │
│     → 修正結果をログ/APIで確認可能                          │
└─────────────────────────────────────────────────────────────┘
```

### 期待される効果

| 項目 | 現状 | 目標 |
|------|------|------|
| **データ精度** | 古いデータは取得時の調整値のまま | 常に最新の調整済み価格 |
| **検出閾値** | なし | 0.001%（浮動小数点ノイズ除外） |
| **対応イベント** | なし | 分割/配当/特別配当/スピンオフ等 |
| **運用負荷** | 手動確認が必要 | 自動検出・修正 |
| **長期投資精度** | 年1-2%の累積誤差 | 誤差なし |

---

## Why（なぜ必要か）

### 1. 長期投資における複利効果

```python
# 例: $10,000投資、20年間、年1%の誤差がある場合

正確なリターン計算:
  実際のリターン: 7% → $38,697

1%の累積誤差がある場合:
  計算上のリターン: 6% → $32,071
  誤差: $6,626 (17%の過小評価)
```

### 2. バックテスト・分析の信頼性

- **トレーディング戦略のバックテスト**: 誤った価格で検証すると誤った結論に
- **リスク指標計算**: ボラティリティ、シャープレシオ等が不正確に
- **パフォーマンス比較**: ベンチマーク比較が意味をなさない

### 3. コーポレートアクションの頻度

| イベント | 頻度 | 価格影響 |
|----------|------|----------|
| 配当 | 四半期ごと（多くの銘柄） | 0.1-0.5%/回 |
| 株式分割 | 数年に1回 | 50-90% |
| 特別配当 | 不定期 | 1-5% |
| スピンオフ | 稀 | 10-30% |

### 4. yfinanceの調整方式

```
yfinance auto_adjust=True の動作:

取得日: 2024-01-15
  → 2024-01-15時点の調整係数で全履歴を調整

取得日: 2025-11-30
  → 2025-11-30時点の調整係数で全履歴を調整
  → 2024-01-15に取得した値とは異なる！

結論: 過去に取得したデータは「取得時点の調整済み価格」であり、
      現在の調整済み価格とは一致しない
```

---

## What（何を作るか）

### 1. 調整検出サービス

```python
# app/services/adjustment_detector.py

class PrecisionAdjustmentDetector:
    """高精度価格調整検出サービス"""
    
    # 検出対象イベント
    SUPPORTED_EVENTS = [
        "stock_split",       # 株式分割
        "reverse_split",     # 逆分割
        "dividend",          # 通常配当
        "special_dividend",  # 特別配当
        "capital_gain",      # キャピタルゲイン分配（ETF）
        "spinoff",           # スピンオフ
    ]
    
    # 閾値設定
    THRESHOLDS = {
        "float_noise_pct": 0.0001,     # 浮動小数点ノイズ（無視）
        "min_detection_pct": 0.001,    # 最小検出閾値
        "split_threshold_pct": 10.0,   # 分割判定閾値
        "spinoff_threshold_pct": 15.0, # スピンオフ判定閾値
    }
```

### 2. 新規APIエンドポイント

| メソッド | パス | 説明 |
|----------|------|------|
| `POST` | `/v1/maintenance/check-adjustments` | 調整チェック実行 |
| `GET` | `/v1/maintenance/adjustment-report` | 最新レポート取得 |
| `POST` | `/v1/maintenance/fix-adjustments` | 検出シンボルを修正 |

### 3. スキーマ定義

```python
# app/schemas/maintenance.py

class AdjustmentCheckRequest(BaseModel):
    symbols: Optional[List[str]] = None  # 省略時は全アクティブ
    auto_fix: bool = False               # 自動修正の有無
    threshold_pct: float = 0.001         # 検出閾値

class AdjustmentEvent(BaseModel):
    symbol: str
    event_type: str      # stock_split, dividend, etc.
    severity: str        # critical, high, normal, low
    pct_difference: float
    check_date: date
    db_price: float
    yf_adjusted_price: float
    details: Dict[str, Any]
    recommendation: str

class AdjustmentCheckResponse(BaseModel):
    scan_timestamp: datetime
    total_symbols: int
    scanned: int
    needs_refresh: List[AdjustmentEvent]
    no_change: List[str]
    errors: List[Dict[str, str]]
    summary: Dict[str, Any]
```

### 4. 設定項目

```python
# app/core/config.py への追加

class Settings(BaseSettings):
    # 調整検出設定
    ADJUSTMENT_CHECK_ENABLED: bool = True
    ADJUSTMENT_MIN_THRESHOLD_PCT: float = 0.001
    ADJUSTMENT_SAMPLE_POINTS: int = 10
    ADJUSTMENT_MIN_DATA_AGE_DAYS: int = 60
    ADJUSTMENT_AUTO_FIX: bool = False  # 本番は手動確認推奨
```

---

## How（どう実装するか）

### Phase 1: 検出サービス（2-3日）

#### 1.1 サービス実装

```python
# app/services/adjustment_detector.py

from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal
from enum import Enum
from typing import List, Dict, Any, Optional, Tuple

import yfinance as yf
from sqlalchemy import select, func, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Price, Symbol


class AdjustmentType(Enum):
    STOCK_SPLIT = "stock_split"
    REVERSE_SPLIT = "reverse_split"
    DIVIDEND = "dividend"
    SPECIAL_DIVIDEND = "special_dividend"
    CAPITAL_GAIN = "capital_gain"
    SPINOFF = "spinoff"
    UNKNOWN = "unknown"


class AdjustmentSeverity(Enum):
    CRITICAL = "critical"  # 即時対応（分割、スピンオフ）
    HIGH = "high"          # 早期対応（特別配当）
    NORMAL = "normal"      # 通常対応（配当累積）
    LOW = "low"            # 低優先度


@dataclass
class DetectionThresholds:
    float_noise_pct: float = 0.0001
    min_detection_pct: float = 0.001
    split_threshold_pct: float = 10.0
    special_div_threshold_pct: float = 2.0
    spinoff_threshold_pct: float = 15.0
    sample_points: int = 10
    min_data_age_days: int = 60


class PrecisionAdjustmentDetector:
    """高精度価格調整検出サービス"""
    
    def __init__(self, thresholds: Optional[DetectionThresholds] = None):
        self.thresholds = thresholds or DetectionThresholds()
    
    async def get_sample_prices(
        self,
        session: AsyncSession,
        symbol: str
    ) -> List[Tuple[date, float]]:
        """DBから分散サンプルを取得（最古〜閾値日まで）"""
        min_age = date.today() - timedelta(days=self.thresholds.min_data_age_days)
        
        result = await session.execute(
            select(Price.date, Price.close)
            .where(and_(Price.symbol == symbol, Price.date < min_age))
            .order_by(Price.date.asc())
        )
        all_rows = result.fetchall()
        
        if len(all_rows) < 2:
            return []
        
        # 等間隔でサンプリング
        step = max(1, len(all_rows) // self.thresholds.sample_points)
        indices = list(range(0, len(all_rows), step))[:self.thresholds.sample_points]
        if len(all_rows) - 1 not in indices:
            indices.append(len(all_rows) - 1)
        
        return [(all_rows[i][0], float(all_rows[i][1])) for i in indices]
    
    def _compare_with_precision(
        self,
        db_price: float,
        yf_price: float
    ) -> Tuple[float, bool]:
        """高精度価格比較"""
        if db_price == 0 or yf_price == 0:
            return 0.0, False
        
        db_dec = Decimal(str(db_price))
        yf_dec = Decimal(str(yf_price))
        diff = abs(db_dec - yf_dec)
        pct_diff = float((diff / db_dec) * 100)
        
        is_significant = (
            pct_diff >= self.thresholds.float_noise_pct and
            pct_diff >= self.thresholds.min_detection_pct
        )
        return pct_diff, is_significant
    
    def _classify_event(
        self,
        pct_diff: float,
        ticker: yf.Ticker,
        check_date: date
    ) -> Tuple[AdjustmentType, AdjustmentSeverity, Dict[str, Any]]:
        """イベント分類"""
        details: Dict[str, Any] = {}
        
        # 分割チェック
        if pct_diff >= self.thresholds.split_threshold_pct:
            splits = ticker.splits
            recent = splits[splits.index > str(check_date)]
            if not recent.empty:
                factor = recent.prod()
                details["splits"] = [
                    {"date": str(idx.date()), "ratio": val}
                    for idx, val in recent.items()
                ]
                details["cumulative_factor"] = float(factor)
                if factor < 1:
                    return AdjustmentType.REVERSE_SPLIT, AdjustmentSeverity.HIGH, details
                return AdjustmentType.STOCK_SPLIT, AdjustmentSeverity.CRITICAL, details
            
            if pct_diff >= self.thresholds.spinoff_threshold_pct:
                details["note"] = "Possible spinoff"
                return AdjustmentType.SPINOFF, AdjustmentSeverity.CRITICAL, details
        
        # 配当チェック
        dividends = ticker.dividends
        recent_divs = dividends[dividends.index > str(check_date)]
        if not recent_divs.empty:
            details["dividend_count"] = len(recent_divs)
            details["total_dividends"] = float(recent_divs.sum())
            
            if pct_diff >= self.thresholds.special_div_threshold_pct:
                max_div = recent_divs.max()
                if max_div > recent_divs.mean() * 2:
                    details["special_dividend"] = float(max_div)
                    return AdjustmentType.SPECIAL_DIVIDEND, AdjustmentSeverity.HIGH, details
            
            return AdjustmentType.DIVIDEND, AdjustmentSeverity.NORMAL, details
        
        # キャピタルゲイン（ETF）
        try:
            cap_gains = ticker.capital_gains
            if len(cap_gains) > 0:
                recent_gains = cap_gains[cap_gains.index > str(check_date)]
                if not recent_gains.empty:
                    details["capital_gains"] = float(recent_gains.sum())
                    return AdjustmentType.CAPITAL_GAIN, AdjustmentSeverity.NORMAL, details
        except Exception:
            pass
        
        return AdjustmentType.UNKNOWN, AdjustmentSeverity.LOW, details
    
    async def detect_adjustments(
        self,
        session: AsyncSession,
        symbol: str
    ) -> Dict[str, Any]:
        """単一シンボルの調整を検出"""
        result = {
            "symbol": symbol,
            "needs_refresh": False,
            "events": [],
            "max_pct_diff": 0.0,
            "error": None
        }
        
        try:
            samples = await self.get_sample_prices(session, symbol)
            if len(samples) < 2:
                result["error"] = "Insufficient data"
                return result
            
            ticker = yf.Ticker(symbol)
            yf_hist = ticker.history(
                start=samples[0][0].strftime('%Y-%m-%d'),
                end=(samples[-1][0] + timedelta(days=1)).strftime('%Y-%m-%d'),
                auto_adjust=True
            )
            
            if yf_hist.empty:
                result["error"] = "No yfinance data"
                return result
            
            for check_date, db_close in samples:
                date_str = check_date.strftime('%Y-%m-%d')
                yf_row = yf_hist[yf_hist.index.strftime('%Y-%m-%d') == date_str]
                
                if yf_row.empty:
                    continue
                
                yf_close = float(yf_row['Close'].iloc[0])
                pct_diff, is_significant = self._compare_with_precision(db_close, yf_close)
                
                if is_significant:
                    event_type, severity, details = self._classify_event(
                        pct_diff, ticker, check_date
                    )
                    result["events"].append({
                        "type": event_type.value,
                        "severity": severity.value,
                        "pct_diff": round(pct_diff, 6),
                        "date": check_date.isoformat(),
                        "db_price": db_close,
                        "yf_price": yf_close,
                        "details": details
                    })
                    result["max_pct_diff"] = max(result["max_pct_diff"], pct_diff)
            
            result["needs_refresh"] = len(result["events"]) > 0
            
        except Exception as e:
            result["error"] = str(e)
        
        return result
```

#### 1.2 テスト

```python
# tests/test_adjustment_detector.py

import pytest
from unittest.mock import Mock, patch
from app.services.adjustment_detector import PrecisionAdjustmentDetector

class TestAdjustmentDetector:
    
    def test_threshold_defaults(self):
        detector = PrecisionAdjustmentDetector()
        assert detector.thresholds.min_detection_pct == 0.001
    
    def test_compare_with_precision_significant(self):
        detector = PrecisionAdjustmentDetector()
        pct, is_sig = detector._compare_with_precision(100.0, 99.0)
        assert pct == pytest.approx(1.0)
        assert is_sig is True
    
    def test_compare_with_precision_noise(self):
        detector = PrecisionAdjustmentDetector()
        pct, is_sig = detector._compare_with_precision(100.0, 99.99999)
        assert is_sig is False
```

### Phase 2: APIエンドポイント（1日）

```python
# app/api/v1/maintenance.py

from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List, Optional

from app.api.deps import get_db
from app.core.config import get_settings
from app.services.adjustment_detector import PrecisionAdjustmentDetector
from app.schemas.maintenance import (
    AdjustmentCheckRequest,
    AdjustmentCheckResponse
)

router = APIRouter(prefix="/v1/maintenance", tags=["maintenance"])


@router.post("/check-adjustments", response_model=AdjustmentCheckResponse)
async def check_adjustments(
    request: AdjustmentCheckRequest,
    x_cron_secret: str = Header(..., alias="X-Cron-Secret"),
    session: AsyncSession = Depends(get_db)
):
    """価格調整の必要性をチェック"""
    settings = get_settings()
    if x_cron_secret != settings.CRON_SECRET_TOKEN:
        raise HTTPException(status_code=401, detail="Invalid cron secret")
    
    detector = PrecisionAdjustmentDetector()
    # ... 実装
```

### Phase 3: Cron統合（0.5日）

```python
# app/api/v1/cron.py への追加

@router.post("/weekly-adjustment-check")
async def weekly_adjustment_check(
    x_cron_secret: str = Header(..., alias="X-Cron-Secret"),
    session: AsyncSession = Depends(get_db)
):
    """週次の調整チェック（Cron用）"""
    # 全アクティブシンボルをチェック
    # auto_fix=False でレポートのみ生成
    # 結果をログ出力
```

### Phase 4: ドキュメント更新（0.5日）

- `architecture.md` 更新
- `api-usage-guide.md` 更新
- `README.md` 更新

---

## 実装スケジュール

| Phase | 内容 | 工数 | 優先度 |
|-------|------|------|--------|
| 1 | 検出サービス | 2-3日 | 🔴 高 |
| 2 | APIエンドポイント | 1日 | 🔴 高 |
| 3 | Cron統合 | 0.5日 | 🟡 中 |
| 4 | ドキュメント | 0.5日 | 🟡 中 |
| **合計** | | **4-5日** | |

---

## リスクと対策

| リスク | 影響 | 対策 |
|--------|------|------|
| yfinance APIレート制限 | スキャン中断 | バッチ処理、レートリミッター |
| 大量シンボルでのタイムアウト | 完了しない | 分割実行、進捗保存 |
| 誤検出（データプロバイダ側の一時的な問題） | 不要な再取得 | 複数ポイント確認、確認待ち期間 |
| 本番データの意図しない削除 | データ損失 | auto_fix=False がデフォルト、確認プロセス |

---

## 成功指標

1. **検出精度**: 0.001%以上の乖離を100%検出
2. **誤検出率**: 5%未満（浮動小数点ノイズ除外）
3. **スキャン時間**: 100シンボル/5分以内
4. **データ精度**: 修正後の乖離 < 0.0001%
