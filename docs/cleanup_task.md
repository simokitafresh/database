# クリーンアップタスク

## 概要
appディレクトリ内の不要なコードをクリーンアップするタスク。実装完了済みのシステムから、未使用のファイルやコードを削除してコードベースを整理する。

## 最終更新: 2025年12月1日

---

## 現在の状況

### テスト結果
```
109 tests collected
107 passed, 2 failed, 42 warnings (2.12s)
```

### ディレクトリ構成
- **app/**: 7サブディレクトリ（api, core, db, migrations, monitoring, profiling, schemas, services, utils）
- **tests/**: 15ファイル（フラット構成）
- **空ディレクトリ**: `app/monitoring/`, `app/profiling/`

---

## Task 1: 未使用ファイルの削除

### 1.1 未使用サービスファイル
| ファイル | 状態 | 理由 |
|---------|------|------|
| `app/services/resolver.py` | ⬜ 削除候補 | どこからもインポートされていない（architecture.mdでのみ言及） |

### 1.2 空ディレクトリ
| ディレクトリ | 状態 | 対処 |
|-------------|------|------|
| `app/monitoring/` | ⬜ 削除候補 | 中身が空 |
| `app/profiling/` | ⬜ 削除候補 | 中身が空 |

---

## Task 2: テストの修正

### 2.1 失敗テスト

#### `test_cron_endpoint.py::test_daily_economic_update`
- **状態**: ⬜ 要修正
- **原因**: モックされたセッションがSQLAlchemy `result.one()` を正しく返さない
- **対処**: `session.execute` の戻り値モックを追加

#### `test_fetch_job_creation.py::test_fetch_job_creation_triggers_background`
- **状態**: ⬜ 要修正
- **原因**: テストが `max_concurrency=2` を期待するが、実装は `max_concurrency=1` を渡す
- **対処**: テストの期待値を `max_concurrency=1` に修正

---

## Task 3: 非推奨コードの更新

### 3.1 `datetime.utcnow()` → `datetime.now(timezone.utc)`

| ファイル | 行 | 状態 |
|---------|-----|------|
| `app/services/fetch_jobs.py` | 50, 66, 391, 411 | ⬜ 要修正 |
| `app/services/fetch_worker.py` | 58, 148, 156, 226, 324 | ⬜ 要修正 |
| `app/services/coverage.py` | 268 | ⬜ 要修正 |
| `app/api/v1/maintenance.py` | 368 | ⬜ 要修正 |
| `app/api/v1/cron.py` | 361 | ⬜ 要修正 |

### 3.2 Pydantic V1 `@validator` → V2 `@field_validator`

| ファイル | 行 | 状態 |
|---------|-----|------|
| `app/schemas/fetch_jobs.py` | 17, 34, 53, 64, 71, 88 | ⬜ 要修正 |
| `app/schemas/cron.py` | 28 | ⬜ 要修正 |

---

## Task 4: その他の警告対応

### 4.1 httpx deprecation
- **警告**: `The 'app' shortcut is now deprecated. Use ASGITransport(app=...) instead`
- **対象**: `tests/conftest.py` の `AsyncClient` 使用箇所
- **状態**: ⬜ 要修正

### 4.2 python-multipart import
- **警告**: `Please use import python_multipart instead`
- **対象**: サードパーティ（starlette）の問題、対処不要
- **状態**: ✅ 対処不要

### 4.3 Pydantic class-based config
- **警告**: `Support for class-based config is deprecated, use ConfigDict instead`
- **対象**: Pydantic モデルの `Config` クラス
- **状態**: ⬜ 要調査

---

## タスクリスト

### Priority: High（テスト修正）
- [ ] `test_fetch_job_creation.py` の `max_concurrency` 期待値を修正
- [ ] `test_cron_endpoint.py` のモックを修正

### Priority: Medium（コード品質）
- [ ] `datetime.utcnow()` を `datetime.now(timezone.utc)` に一括置換（10箇所）
- [ ] Pydantic `@validator` → `@field_validator` 移行（7箇所）
- [ ] `tests/conftest.py` の AsyncClient を ASGITransport 形式に更新

### Priority: Low（クリーンアップ）
- [ ] `app/services/resolver.py` の削除（architecture.md更新必要）
- [ ] `app/monitoring/` 空ディレクトリ削除
- [ ] `app/profiling/` 空ディレクトリ削除

---

## 有効なファイル一覧

### app/services/ （16ファイル - 全て使用中 ※resolverを除く）
```
adjustment_detector.py  ← cron.py, maintenance.py
auto_register.py        ← prices.py
cache.py                ← prefetch_service.py, debug.py, prices.py
coverage.py             ← api/v1/coverage.py
fetch_jobs.py           ← fetch_worker.py, fetch.py
fetch_worker.py         ← fetch.py
fred_service.py         ← cron.py
normalize.py            ← auto_register.py, prices.py
prefetch_service.py     ← main.py
profiling.py            ← prices.py
query_optimizer.py      ← services/coverage.py
redis_utils.py          ← cache.py, db/utils.py, db/queries.py
resolver.py             ← 未使用（削除候補）
symbol_validator.py     ← auto_register.py
upsert.py               ← fetch_worker.py, db/queries.py
fetcher.py              ← prefetch_service.py, db/queries.py
```

### tests/ （15ファイル）
```
conftest.py                  ← pytest設定
test_adjustment_config.py    ← 設定テスト
test_adjustment_detector.py  ← 検出器テスト
test_coverage_invalid_sort.py ← カバレッジテスト
test_cron_adjustment.py      ← cron調整テスト
test_cron_endpoint.py        ← cronエンドポイント（⚠️1件失敗）
test_fetch_job_creation.py   ← フェッチジョブ（⚠️1件失敗）
test_fred_service_mock.py    ← FREDサービス
test_healthz_endpoint.py     ← ヘルスチェック
test_maintenance_api.py      ← メンテナンスAPI
test_maintenance_schemas.py  ← スキーマ
test_root_endpoint.py        ← ルート
test_symbols_endpoint.py     ← シンボル
test_symbols_list.py         ← シンボルリスト
test_v1_health.py            ← v1ヘルス
```

---

## 注意事項
- 削除前にGitでバックアップ確認
- `resolver.py` 削除時は `architecture.md` の参照を更新
- Pydantic移行は段階的に実施（breaking changeの可能性）
- 本番環境への影響なし（テスト・警告のみ）</content>
<parameter name="filePath">c:\Python_app\database\cleanup_task.md