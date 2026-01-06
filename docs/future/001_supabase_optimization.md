# 001: Supabase活用最適化調査レポート

**調査日**: 2026-01-06
**ステータス**: 調査完了・提案段階

---

## 概要

現在のシステムは **Supabase Transaction Pooler (PgBouncer)** を前提とした過剰な制約が多数存在し、Supabaseの本来の機能を活用できていません。これにより、パフォーマンスと開発効率が大幅に制限されています。

---

## 発見された問題点

### 1. NullPool強制による接続効率の低下

**ファイル**: `app/db/engine.py` (L86-96)

```python
if "supabase.com" in database_url or "pgbouncer" in database_url.lower() or pool_size <= 1:
    poolclass = NullPool
    pool_pre_ping = False
    pool_recycle = -1
```

**問題**:
- 毎リクエストで新規接続を作成→破棄（オーバーヘッド大）
- コネクションプール機能が完全に無効化
- `pool_pre_ping`が使えないため接続検証も不可

---

### 2. 並行処理=1の強制

**ファイル**: `app/services/fetch_worker.py` (L29)

```python
max_concurrency=1  # Reduced to 1 for Supabase NullPool compatibility
```

**ファイル**: `app/api/v1/fetch.py` (L92)

```python
max_concurrency=1  # Reduced to 1 for Supabase NullPool compatibility
```

**問題**:
- 135シンボルのフェッチが**直列処理**（非常に遅い）
- I/O待ち時間を並行処理で隠蔽できない
- Transaction Pooler制約のための回避策が過剰

---

### 3. プリフェッチサービスの無効化

**ファイル**: `app/main.py` (L57-82)

```python
# プリフェッチサービス開始（ENABLE_CACHEがTrueで、Supabase環境でない場合のみ）
# SupabaseのNullPool環境では並行処理が許可されていないため無効化
if settings.ENABLE_CACHE and not is_supabase:
    # フルプリフェッチ
elif is_supabase and settings.ENABLE_CACHE:
    # 起動時1回だけの軽量キャッシュウォーム（劣化版）
```

**問題**:
- Supabase環境ではバックグラウンドプリフェッチが完全無効
- 起動時の1回限りのウォームアップのみ
- キャッシュヒット率が大幅に低下

---

### 4. 接続リトライの過剰設定

**ファイル**: `app/api/deps.py` (L20-22)

```python
# Increased for Supabase Pooler stability
MAX_SESSION_RETRIES = 5
RETRY_DELAY_SECONDS = 0.5
```

**問題**:
- Transaction Pooler特有の接続切断に対する回避策
- レイテンシ増加（最大5回×0.5秒〜のリトライ待ち）
- 根本原因（接続タイプ）を解決すれば不要

---

## 根本原因

### Supabase接続モードの選択ミス

Supabaseには3つの接続モードがあります：

| モード | ポート | 特徴 | 現状 |
|--------|--------|------|------|
| **Direct** | 5432 | 直接PostgreSQL接続、制限なし | ❌ 未使用 |
| **Session Pooler** | 5432 (pooler) | セッション維持、プリペアドステートメント可 | ❌ 未使用 |
| **Transaction Pooler** | 6543 | トランザクション単位、最も制限大 | ✅ 現在使用中 |

**現在の問題**: Transaction Poolerを使用しているため、以下の制約が発生：
- プリペアドステートメント使用不可
- LISTEN/NOTIFY使用不可
- Advisory Lock使用不可（一時的なものに限る）
- 長時間トランザクション非推奨

---

## 提案する改善策

### Option A: Session Poolerへの移行（推奨）

**変更点**:
1. DATABASE_URLのポートを`6543`から`5432`（Session Pooler）に変更
2. `pooler.supabase.com`のまま使用（IPv4互換性維持）

**メリット**:
- セッション維持によりプリペアドステートメント使用可
- 既存のConnectionプール設定が有効化
- プリフェッチサービスが完全に動作

**期待される改善**:
- フェッチ並行処理：1 → 4〜8
- プリフェッチ：無効 → 有効（バックグラウンド更新）
- 接続効率：毎回新規 → プール再利用

---

### Option B: Direct接続への移行

**変更点**:
1. DATABASE_URLを`db.{project-ref}.supabase.co:5432`形式に変更
2. IPv6対応環境が必要

**メリット**:
- 完全なPostgreSQL機能
- 最高のパフォーマンス
- すべての制約解除

**デメリット**:
- Renderなど一部PaaSがIPv6非対応の場合接続不可

---

## 削除可能なコード（Option A採用時）

| ファイル | 変更内容 |
|----------|----------|
| `engine.py` | NullPool強制ロジック削除（L86-96） |
| `fetch_worker.py` | `max_concurrency=1`を`4`以上に変更 |
| `fetch.py` | `max_concurrency=1`を`4`以上に変更 |
| `main.py` | `is_supabase`分岐を簡略化、フルプリフェッチ有効化 |
| `deps.py` | リトライ回数を適正化（5→3） |
| `migrations/env.py` | Transaction Pooler専用URL変換ロジック削除 |

---

## 期待される効果

| 指標 | Before（Transaction Pooler） | After（Session Pooler） |
|------|------------------------------|-------------------------|
| 135シンボルフェッチ時間 | ~30分（直列） | ~5分（並行8） |
| 接続オーバーヘッド | 高（毎回新規） | 低（プール再利用） |
| プリフェッチ | 起動時1回のみ | 5分間隔バックグラウンド |
| キャッシュヒット率 | 低 | 高 |
| コード複雑度 | 高（分岐多数） | 低（統一処理） |

---

## 確認が必要な事項

1. **Supabase管理画面**で現在の接続URLの確認
2. **Render環境変数**の`DATABASE_URL`の値
3. Session Poolerへの変更後の**接続テスト**
4. 既存の**Advisory Lock使用箇所**の確認

---

## 次のステップ

1. [ ] Supabase Dashboardで接続URLを確認
2. [ ] Session Pooler URLを取得
3. [ ] ローカル環境でテスト接続
4. [ ] engine.py、fetch_worker.pyの制約解除
5. [ ] ステージング環境でテスト
6. [ ] 本番環境への展開
