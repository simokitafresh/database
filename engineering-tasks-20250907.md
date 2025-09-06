# 株価データAPI修正 - エンジニアリングタスクリスト v2.0

## 📅 作成日: 2025年9月7日
## 🎯 目的: 外部アプリケーションからのAPI呼び出しエラーゼロ化
## 📦 対象リポジトリ: https://github.com/simokitafresh/database
## ⚠️ 注意: コーディングのみ実行。バックアップ・コメントアウト不要

---

## タスク進捗管理表

| タスクID | カテゴリ | ファイル | ステータス | 完了日時 | 検証結果 |
|----------|----------|----------|------------|----------|----------|
| FW-001 | Import追加 | fetch_worker.py | [ ] 未着手 | - | - |
| FW-002 | 関数修正1 | fetch_worker.py | [ ] 未着手 | - | - |
| FW-003 | 関数修正2 | fetch_worker.py | [ ] 未着手 | - | - |
| FW-004 | 関数修正3 | fetch_worker.py | [ ] 未着手 | - | - |
| FW-005 | 関数修正4 | fetch_worker.py | [ ] 未着手 | - | - |
| FW-006 | 削除1 | fetch_worker.py | [ ] 未着手 | - | - |
| FW-007 | 削除2 | fetch_worker.py | [ ] 未着手 | - | - |
| QR-001 | Import追加 | queries.py | [ ] 未着手 | - | - |
| QR-002 | 関数作成 | queries.py | [ ] 未着手 | - | - |
| QR-003 | 関数置換 | queries.py | [ ] 未着手 | - | - |
| QR-004 | except修正1 | queries.py | [ ] 未着手 | - | - |
| QR-005 | except修正2 | queries.py | [ ] 未着手 | - | - |
| PR-001 | 行削除 | prices.py | [ ] 未着手 | - | - |
| PR-002 | インデント修正 | prices.py | [ ] 未着手 | - | - |
| VF-001 | Syntax検証 | 全ファイル | [ ] 未着手 | - | - |
| VF-002 | Import検証 | 全ファイル | [ ] 未着手 | - | - |
| VF-003 | 起動テスト | Docker | [ ] 未着手 | - | - |
| VF-004 | APIテスト | エンドポイント | [ ] 未着手 | - | - |

---

## 🔧 Section 1: fetch_worker.py修正タスク

### FW-001: 必要なimport文を追加
**対象ファイル**: `app/services/fetch_worker.py`  
**対象行**: 1-10行目（ファイル先頭のimportセクション）  
**作業内容**: 
```python
# 以下の2行を既存のimport文の後に追加
from app.db.engine import create_engine_and_sessionmaker
from app.core.config import settings
```
**完了条件**: 上記2行のimportが存在すること  
**検証コマンド**: `grep "from app.db.engine import create_engine_and_sessionmaker" app/services/fetch_worker.py`

---

### FW-002: process_fetch_job関数のセッション作成部分を修正
**対象ファイル**: `app/services/fetch_worker.py`  
**対象行**: 59-61行目  
**作業内容**:
1. 59行目の`async for session in get_session():`を削除
2. 以下のコードに置き換え:
```python
    # 独立したセッションファクトリを作成
    _, SessionLocal = create_engine_and_sessionmaker(
        database_url=settings.DATABASE_URL,
        pool_size=settings.DB_POOL_SIZE,
        max_overflow=settings.DB_MAX_OVERFLOW,
        pool_pre_ping=settings.DB_POOL_PRE_PING,
        pool_recycle=settings.DB_POOL_RECYCLE,
        echo=settings.DB_ECHO
    )
    
    async with SessionLocal() as session:
        async with session.begin():
```
**完了条件**: SessionLocalが作成され、async withブロックが開始される  
**検証コマンド**: `grep -A5 "create_engine_and_sessionmaker" app/services/fetch_worker.py | head -10`

---

### FW-003: process_fetch_job関数のtryブロックインデントを調整
**対象ファイル**: `app/services/fetch_worker.py`  
**対象行**: 60-157行目  
**作業内容**:
1. 元の`try:`ブロック全体（60-156行目）のインデントを2レベル右に移動
2. `async with session.begin():`の内側に配置
3. 最後の`except Exception as e:`も同じインデントレベルに調整
**完了条件**: tryブロックが`async with session.begin():`の内側にある  
**検証コマンド**: `python -m py_compile app/services/fetch_worker.py`

---

### FW-004: fetch_symbol_data関数のupsert部分を修正
**対象ファイル**: `app/services/fetch_worker.py`  
**対象行**: 228-240行目  
**作業内容**:
1. 228行目の`async for session in get_session():`を削除
2. 以下のコードに置き換え:
```python
        # 独立したセッションを作成（単一タスク用）
        _, SessionLocal = create_engine_and_sessionmaker(
            database_url=settings.DATABASE_URL,
            pool_size=1,
            max_overflow=0,
            pool_pre_ping=settings.DB_POOL_PRE_PING,
            pool_recycle=settings.DB_POOL_RECYCLE,
            echo=False
        )
        
        async with SessionLocal() as session:
            async with session.begin():
```
**完了条件**: fetch_symbol_data内でSessionLocalが作成される  
**検証コマンド**: `grep -B2 -A8 "pool_size=1" app/services/fetch_worker.py`

---

### FW-005: fetch_symbol_data関数のインデント調整
**対象ファイル**: `app/services/fetch_worker.py`  
**対象行**: 229-243行目  
**作業内容**:
1. 元のupsert処理コード（229-243行目）のインデントを2レベル右に移動
2. `async with session.begin():`の内側に配置
**完了条件**: upsert処理が正しいインデントレベルにある  
**検証コマンド**: `python -m py_compile app/services/fetch_worker.py`

---

### FW-006: get_job_queue_status関数のセッション処理修正
**対象ファイル**: `app/services/fetch_worker.py`  
**対象行**: 261-263行目  
**作業内容**:
1. 261行目の`async for session in get_session():`を削除
2. 以下のコードに置き換え:
```python
    _, SessionLocal = create_engine_and_sessionmaker(
        database_url=settings.DATABASE_URL,
        pool_size=1,
        max_overflow=0
    )
    
    async with SessionLocal() as session:
```
**完了条件**: get_job_queue_status内でSessionLocalが作成される  
**検証コマンド**: `grep -A3 "def get_job_queue_status" app/services/fetch_worker.py`

---

### FW-007: get_job_queue_status関数のインデント調整
**対象ファイル**: `app/services/fetch_worker.py`  
**対象行**: 264-287行目  
**作業内容**:
1. SQLクエリ実行部分（264-287行目）のインデントを1レベル右に移動
2. `async with SessionLocal() as session:`の内側に配置
**完了条件**: クエリ実行コードが正しいインデントレベルにある  
**検証コマンド**: `python -m py_compile app/services/fetch_worker.py`

---

## 🔧 Section 2: queries.py修正タスク

### QR-001: run_in_threadpoolのimportを追加
**対象ファイル**: `app/db/queries.py`  
**対象行**: 1-10行目（importセクション）  
**作業内容**:
```python
# 既存のimport文の後に追加
from starlette.concurrency import run_in_threadpool
```
**完了条件**: run_in_threadpoolがimportされている  
**検証コマンド**: `grep "from starlette.concurrency import run_in_threadpool" app/db/queries.py`

---

### QR-002: _sync_find_earliest内部関数を作成
**対象ファイル**: `app/db/queries.py`  
**対象行**: 239-276行目（find_earliest_available_date関数）  
**作業内容**:
1. 関数内容を以下に完全置換:
```python
async def find_earliest_available_date(symbol: str, target_date: date) -> date:
    """効率的に最古の利用可能日を探索（非同期対応）"""
    logger = logging.getLogger(__name__)
    
    def _sync_find_earliest() -> date:
        """同期処理を別スレッドで実行"""
        import yfinance as yf
        from datetime import timedelta
        
        test_dates = [
            date(1970, 1, 1),
            date(1980, 1, 1),
            date(1990, 1, 1),
            date(2000, 1, 1),
            date(2010, 1, 1),
        ]
        
        for test_date in test_dates:
            if test_date >= target_date:
                try:
                    df = yf.download(
                        symbol,
                        start=test_date,
                        end=test_date + timedelta(days=30),
                        progress=False,
                        timeout=5
                    )
                    if not df.empty:
                        return df.index[0].date()
                except Exception as e:
                    logger.debug(f"Test date {test_date} failed for {symbol}: {e}")
                    continue
        
        return max(target_date, date(2000, 1, 1))
    
    # 別スレッドで実行
    return await run_in_threadpool(_sync_find_earliest)
```
**完了条件**: 関数が内部関数_sync_find_earliestを持つ  
**検証コマンド**: `grep "def _sync_find_earliest" app/db/queries.py`

---

### QR-003: loggerの追加確認
**対象ファイル**: `app/db/queries.py`  
**対象行**: 6行目付近  
**作業内容**:
1. ファイル先頭でloggingがimportされているか確認
2. されていない場合は追加: `import logging`
**完了条件**: loggingモジュールがimportされている  
**検証コマンド**: `grep "^import logging" app/db/queries.py`

---

### QR-004: 裸のexcept節を修正（1箇所目）
**対象ファイル**: `app/db/queries.py`  
**対象行**: 264行目（新しい関数内では異なる可能性）  
**作業内容**:
1. `except:`を検索
2. `except Exception as e:`に置換
3. 次の行に`logger.debug(f"Error: {e}")`を追加（インデント注意）
**完了条件**: 裸のexcept節が存在しない  
**検証コマンド**: `! grep -n "except:$" app/db/queries.py`

---

### QR-005: ensure_coverage_with_auto_fetch内の裸のexcept節を修正
**対象ファイル**: `app/db/queries.py`  
**対象行**: 344行目付近  
**作業内容**:
1. ensure_coverage_with_auto_fetch関数内の`except:`を検索
2. 見つかった場合、`except Exception:`に置換
**完了条件**: ensure_coverage_with_auto_fetch内に裸のexcept節がない  
**検証コマンド**: `python -m py_compile app/db/queries.py`

---

## 🔧 Section 3: prices.py修正タスク

### PR-001: 二重トランザクション開始行を削除
**対象ファイル**: `app/api/v1/prices.py`  
**対象行**: 68行目  
**作業内容**:
1. 68行目の`async with session.begin():`を完全に削除
2. 行自体を削除（空行にしない）
**完了条件**: `async with session.begin():`が存在しない  
**検証コマンド**: `! grep "async with session.begin():" app/api/v1/prices.py`

---

### PR-002: インデントレベルを修正
**対象ファイル**: `app/api/v1/prices.py`  
**対象行**: 69-95行目  
**作業内容**:
1. 69行目から95行目までのすべての行のインデントを1レベル左に移動
2. 具体的には各行の先頭の空白4つを削除
3. 元のインデントレベル（関数本体と同じ）に戻す
**完了条件**: if文が関数本体と同じインデントレベルにある  
**検証コマンド**: `python -m py_compile app/api/v1/prices.py`

---

## 🔧 Section 4: 検証タスク

### VF-001: Python構文検証
**対象ファイル**: 修正した3ファイル  
**作業内容**:
```bash
python -m py_compile app/services/fetch_worker.py
python -m py_compile app/db/queries.py
python -m py_compile app/api/v1/prices.py
```
**完了条件**: 3ファイルすべてでエラーが出ない  
**検証コマンド**: `echo $?` （0が返る）

---

### VF-002: 必要なimportの存在確認
**対象ファイル**: 修正したファイル  
**作業内容**:
```bash
# 以下のコマンドをすべて実行し、結果を確認
grep "from app.db.engine import create_engine_and_sessionmaker" app/services/fetch_worker.py
grep "from starlette.concurrency import run_in_threadpool" app/db/queries.py
grep "import logging" app/db/queries.py
```
**完了条件**: すべてのgrepコマンドが該当行を返す  
**検証コマンド**: 上記コマンド群

---

### VF-003: Dockerコンテナ起動テスト
**作業内容**:
```bash
# Dockerコンテナをビルドして起動
docker-compose down
docker-compose build
docker-compose up -d
sleep 10
docker-compose ps
```
**完了条件**: api_1とpostgres_1が両方Upステータス  
**検証コマンド**: `docker-compose ps | grep Up | wc -l` （2が返る）

---

### VF-004: APIエンドポイント動作確認
**作業内容**:
```bash
# ヘルスチェック
curl -s http://localhost:8000/healthz

# 価格データ取得（基本）
curl -s "http://localhost:8000/v1/prices?symbols=AAPL&from=2024-01-01&to=2024-01-31"

# フェッチジョブ作成（修正の主要確認点）
curl -s -X POST http://localhost:8000/v1/fetch \
  -H "Content-Type: application/json" \
  -d '{"symbols":["MSFT"],"date_from":"2024-01-01","date_to":"2024-01-31"}'
```
**完了条件**: すべてのcurlコマンドが200 OKを返す  
**検証コマンド**: 各curlコマンドの後に`echo $?`で0を確認

---

## 📋 実装時の注意事項

### 重要な原則
1. **バックアップファイルを作成しない**
2. **コメントアウトで古いコードを残さない**
3. **各タスクは独立して実行可能**
4. **インデント変更は慎重に（Pythonは空白に敏感）**

### エラー時の対処
- 構文エラーが出た場合、インデントを再確認
- import エラーが出た場合、パスとモジュール名を確認
- 実行時エラーが出た場合、該当箇所のログを確認

### 完了基準
- すべてのタスクのステータスが「[x] 完了」
- VF-001〜VF-004の検証がすべてPASS
- 外部アプリケーションからcurlでAPIを叩いてエラーが出ない

---

## 🎯 最終確認チェックリスト

- [ ] fetch_worker.pyの全セッション処理が独立型に変更された
- [ ] queries.pyのyf.downloadが非同期化された
- [ ] prices.pyの二重トランザクションが解消された
- [ ] すべての裸のexcept節が修正された
- [ ] 3ファイルすべてが構文エラーなくコンパイルされる
- [ ] Dockerコンテナが正常に起動する
- [ ] /v1/fetchエンドポイントがエラーを返さない
- [ ] 外部からのAPI呼び出しが100%成功する

---

**作成者**: Stock Data Engineering Team  
**最終更新**: 2025年9月7日  
**用途**: エンジニアリングLLM実行用タスクリスト