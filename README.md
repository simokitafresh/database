# 調整済OHLCV API (MVP)

このリポジトリは、Yahoo Financeから取得した調整済み株価データをPostgreSQLに格納し、FastAPIベースのREST APIで提供するサービスです。シンボル変更（例: FB→META）を透過的に解決し、直近N日分のリフレッシュをサポートします。

## 特徴

- **同期オンデマンド取得**: 不足データがある場合にのみYahoo Financeから取得
- **1ホップのシンボル変更透過解決**: 過去のシンボル変更を自動的に解決
- **直近N日リフレッシュ**: 分割・配当反映の遅延に備えた定期更新
- **調整済OHLCV**: 株式分割・配当を反映した価格データ
- **メトリクス計算**: CAGR, 標準偏差, 最大ドローダウン
- **Docker & Render対応**: ポータブルなデプロイ環境

## API エンドポイント

### ヘルスチェック
- `GET /healthz` - DB接続確認

### シンボル管理
- `GET /v1/symbols?active=true` - 利用可能シンボル一覧

### 価格データ
- `GET /v1/prices?symbols=AAPL,MSFT&from=2021-01-01&to=2023-12-31` - OHLCVデータ取得

### メトリクス計算
- `GET /v1/metrics?symbols=AAPL,MSFT&from=2021-01-01&to=2023-12-31` - 投資指標計算

## クイックスタート

### 1. 環境準備

```bash
# Python 3.11+ を推奨
python --version

# リポジトリをクローン
git clone https://github.com/simokitafresh/database.git
cd database
```

### 2. 依存関係インストール

```bash
# 仮想環境作成（推奨）
python -m venv .venv
# Windows
.venv\Scripts\activate
# Linux/Mac
source .venv/bin/activate

# 依存関係インストール
pip install -r requirements.txt
```

### 3. 環境変数設定

`.env` ファイルを作成：

```bash
# データベース接続
DATABASE_URL=postgresql+asyncpg://user:password@localhost:5432/stock_db

# アプリケーション設定
APP_ENV=dev
API_MAX_SYMBOLS=50
API_MAX_ROWS=1000000
YF_REFETCH_DAYS=30
CORS_ALLOW_ORIGINS=https://your-frontend.example.com
```

### 4. データベース設定

```bash
# Docker ComposeでPostgreSQL起動（開発時）
docker-compose up -d postgres

# マイグレーション実行
alembic upgrade head
```

### 5. アプリケーション起動

```bash
# 開発サーバー起動
uvicorn app.main:app --reload

# またはDocker使用
docker-compose up
```

APIドキュメント: http://localhost:8000/docs

## 開発環境

### テスト実行

```bash
# 全テスト実行
pytest

# カバレッジ付き
pytest --cov=app --cov-report=html

# 特定のテスト
pytest tests/unit/test_fetcher.py
```

### コード品質チェック

```bash
# Lint
ruff check .

# 自動修正
ruff check . --fix

# フォーマット
black .

# 型チェック
mypy app
```

### 管理CLI

```bash
# シンボル追加
python -m app.management.cli add-symbol --symbol AAPL

# シンボル変更適用
python -m app.management.cli apply-symbol-change --old FB --new META --date 2022-06-09

# シンボル検証
python -m app.management.cli verify-symbol --symbol TSLA
```

## プロジェクト構造

```
database/
├── app/
│   ├── main.py                 # FastAPIアプリケーション
│   ├── core/                   # 設定・ロギング・CORS
│   ├── api/v1/                 # APIエンドポイント
│   ├── db/                     # データベースモデル・クエリ
│   ├── services/               # ビジネスロジック
│   ├── schemas/                # Pydanticモデル
│   ├── migrations/             # Alembicマイグレーション
│   └── management/             # CLIツール
├── tests/                      # テストコード
├── docker/                     # Docker設定
├── docker-compose.yml          # 開発環境
├── render.yaml                 # Renderデプロイ設定
└── pyproject.toml              # プロジェクト設定
```

## デプロイ

### Render

1. GitHubリポジトリをRenderに接続
2. `render.yaml` の設定を使用
3. 環境変数を設定:
   - `DATABASE_URL`
   - `CORS_ALLOW_ORIGINS`
   - その他の設定

### Docker

```bash
# ビルド
docker build -f docker/Dockerfile -t stock-api .

# 実行
docker run -p 8000:8000 -e DATABASE_URL=... stock-api
```

## 環境変数

| 変数 | 説明 | デフォルト |
|------|------|-----------|
| `DATABASE_URL` | PostgreSQL接続URL | 必須 |
| `APP_ENV` | 環境(dev/prod) | dev |
| `API_MAX_SYMBOLS` | 1リクエストあたりの最大シンボル数 | 50 |
| `API_MAX_ROWS` | レスポンスの最大行数 | 1000000 |
| `YF_REFETCH_DAYS` | 直近リフレッシュ日数 | 30 |
| `CORS_ALLOW_ORIGINS` | CORS許可オリジン（カンマ区切り） | "" |
| `LOG_LEVEL` | ログレベル | INFO |

## データモデル

### symbols
- `symbol`: ティッカーシンボル（主キー）
- `name`: 会社名
- `exchange`: 取引所
- `currency`: 通貨
- `is_active`: アクティブフラグ
- `first_date`: 初回データ日
- `last_date`: 最終データ日

### symbol_changes
- `old_symbol`: 旧シンボル
- `new_symbol`: 新シンボル
- `change_date`: 変更日
- `reason`: 変更理由

### prices
- `symbol`: シンボル（外部キー）
- `date`: 日付
- `open/high/low/close`: OHLC価格
- `volume`: 出来高
- `source`: データソース
- `last_updated`: 更新日時

## テスト方針

- **ネットワークモック**: 外部API（Yahoo Finance）への実通信を避ける
- **DBモック**: テスト用DBを使用
- **単体・統合・E2E**: 3層のテストカバレッジ
- **CI/CD**: GitHub Actionsで自動テスト

## 貢献方法

1. Issueを作成
2. ブランチを作成: `git checkout -b feature/your-feature`
3. 変更を実装・テスト
4. PRを作成

### コーディング標準
- Blackでフォーマット
- ruffでLint
- mypyで型チェック
- テストカバレッジ80%以上

## ライセンス

MIT License

## サポート

- [APIドキュメント](http://localhost:8000/docs) (ローカル実行時)
- [アーキテクチャドキュメント](./architecture.md)
- [運用ドキュメント](./docs/operations.md)
