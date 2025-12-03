# リファクタリング調査結果

本ドキュメントは、コードベースの分析結果と、コード品質、保守性、パフォーマンスを向上させるためのリファクタリング案をまとめたものです。

## 1. `app/db/queries.py` のリファクタリング

**現状:**
- ファイルが過大（665行）であり、単一責任の原則（SRP）に違反しています。
- 低レベルのデータベース操作、ロック機構、カバレッジロジック、データ取得のオーケストレーションが混在しています。
- `ensure_coverage` と `ensure_coverage_parallel` の間でコードが重複しています。
- SQLクエリが文字列として埋め込まれており、保守が困難です。

**推奨事項:**
- **カバレッジロジックの抽出:** `_get_coverage`、`ensure_coverage` および関連ロジックを専用のサービス（例: `app/services/coverage_service.py`）に移動します。
- **ロックロジックの抽出:** `with_symbol_lock` および関連するロック機構を `app/core/locking.py` または `app/utils/locking.py` に移動します。
- **クエリのモジュール化:** `queries.py` をエンティティごとに小さなモジュールに分割します（例: `app/db/queries/prices.py`, `app/db/queries/symbols.py`）。
- **カバレッジロジックの統一:** `ensure_coverage` と `ensure_coverage_parallel` をリファクタリングし、共通のコア実装を共有させて重複を削減します。

## 2. `app/services/fetcher.py` のリファクタリング

**現状:**
- `RateLimiter` や `ExponentialBackoff` などのユーティリティクラスが含まれていますが、これらは一般的で有用なものの、fetcherと結合しています。
- `fetch_prices` がデータの取得とクリーニング/リネームの両方を処理しています。
- 同期コードと非同期コードが混在しています。

**推奨事項:**
- **ユーティリティの抽出:** `RateLimiter` と `ExponentialBackoff` を `app/core/rate_limit.py` または `app/utils/rate_limit.py` に移動し、再利用可能にします。
- **関心の分離:** `DataCleaner` などのヘルパーを作成して DataFrame のクリーニングとリネームを処理させ、`fetcher.py` はネットワーク操作に集中させます。

## 3. `app/api/v1/prices.py` のリファクタリング

**現状:**
- `get_prices` エンドポイントに、バリデーション、自動登録、キャッシュチェック、レスポンス整形などの重要なビジネスロジックが含まれています。
- これにより、エンドポイントハンドラのテストと保守が困難になっています。

**推奨事項:**
- **サービス層の抽出:** `get_prices` のコアロジックを `PriceService`（例: `app/services/price_service.py`）に抽出します。エンドポイントは主にリクエストの解析とレスポンスのシリアライズを処理するようにします。
- **依存性の注入:** `PriceService` をルーターに注入します。

## 4. `app/api/v1/cron.py` のリファクタリング

**現状:**
- `daily_update` 関数が非常に長く、複雑なオーケストレーションロジック、エラー処理、レポート作成を含んでいます。
- HTTPレスポンスの関心事とバックグラウンド処理のロジックが混在しています。

**推奨事項:**
- **更新ロジックの抽出:** 日次更新のオーケストレーションロジックを `DailyUpdateService` または `CronService` に移動します。
- **エンドポイントの簡素化:** エンドポイントはサービスに処理を委譲し、結果を返すだけにします。

## 5. `app/services/adjustment_detector.py` のリファクタリング

**現状:**
- `PrecisionAdjustmentDetector` クラスが大きく、検出、分類、自動修正を処理しています。
- `auto_fix_symbol` がデータベースと直接対話してデータを削除し、ジョブを作成しています。

**推奨事項:**
- **自動修正ロジックの分離:** `auto_fix_symbol` を別の `AdjustmentFixer` または `MaintenanceService` に移動し、検出と修正を分離します。
- **DB操作の分離:** サービス内で直接セッションを実行する代わりに、リポジトリパターンまたは専用のクエリ関数の使用を検討します。

## 提案される変更の概要

| コンポーネント | 現状の問題 | 提案される解決策 | 優先度 |
| :--- | :--- | :--- | :--- |
| `app/db/queries.py` | 過大、関心の混在 | `coverage_service.py` とモジュール化されたクエリへの分割 | 高 |
| `app/api/v1/prices.py` | コントローラー内のビジネスロジック | `PriceService` の抽出 | 中 |
| `app/api/v1/cron.py` | コントローラー内の複雑なロジック | `DailyUpdateService` の抽出 | 中 |
| `app/services/fetcher.py` | ユーティリティとロジックの混在 | `rate_limit.py` の抽出 | 低 |
| `app/services/adjustment_detector.py` | 検出と修正ロジックの混在 | `AdjustmentFixer` の分離 | 低 |
