
Agents.md

0. この文書の目的

本プロジェクト（調整済OHLCV＋汎用データ提供API）を、複数のLLMエージェント（Planner / Coder / Tester / Reviewer / Migration / Docs）で 安全・一貫 して実装/保守するための運用規範。

公式仕様は architecture.md（全体設計・API・DDL・運用）と Master Task List.md / tasklist.md（受け入れ基準つき開発タスク）。本書はそれらを実行プロトコルに翻訳したもの。 



---

1. 公式ソース（Truth Sources）

エージェントが参照すべき順序と適用方針:

1. architecture.md … システム目的、エンドポイント（/healthz, /v1/symbols, /v1/prices, /v1/metrics）、DBスキーマ、1ホップのシンボル変更透過解決、直近N日（既定30）リフレッチ、デプロイ要点。矛盾時はこの文書を最優先。 


2. Master Task List.md … タスクID/依存関係/受け入れ基準(AC)／成果物ファイルを定義。PRは必ず対応タスクIDとAC充足を明記。 


3. tasklist.md … Master Task と同内容の実行用テンプレ。差異があれば Master を優先。 




---

2. 役割（Agents）と責務

2.1 Planner（計画）

入力：Master Task List.md の tasks。depends_on を解決して 次に着手すべき最小タスクを選定。

出力：作業計画メモ（対象タスクID・変更ファイル・想定テストケース）。

制約：仕様追加や逸脱を行わない。仕様差異は Reviewer にエスカレーション。 


2.2 Coder（実装）

入力：Plannerの計画。

出力：最小コミット（単一関心）、対応テスト、実装ノート。

制約：

外部ネットワーク依存のテストは必ずモック。DB統合はコードのみ用意（起動は不要）。 

APIは /v1/*、DBは symbols/symbol_changes/prices と定義通り。1ホップのティッカー変更と直近N=30日の再取得を前提。 



2.3 Tester（テスト作成）

役割：各タスクの ACを満たす最小テスト を先に作る（または同時）。

ポリシー：pytest、外部I/Oはモック、数値は pytest.approx 許容。 


2.4 Reviewer（レビュー）

チェック項目：

仕様準拠（APIエンドポイント、メトリクス定義：CAGR = exp(sum(r)*252/N)-1, STDEV = std(r,ddof=1)*sqrt(252), MaxDD 算出） 

スキーマ/DDL整合（PK (symbol,date), CHECK 制約, FK, get_prices_resolved 関数存在）。 

タスクAC・差分ファイル・テストの網羅（MasterのACに一致）。 



2.5 Migration（マイグレーション）

役割：Alembicスクリプト（001_init, 002_fn_prices_resolved…）の生成・更新。起動時 alembic upgrade head を前提。 


2.6 Docs（ドキュメント）

役割：API/データ定義ドキュメントの反映（docs/）。

変更が architecture.md の仕様に影響する場合は 要合議。 



---

3. 作業プロトコル（Pull Request 基準）

3.1 ブランチ／コミット

feat/TID-説明 / fix/TID-説明（例：feat/T052-metrics）。

1PR=1タスク原則。コミットは小さく・可逆・テスト同梱。PR本文に TID と ACの充足証跡（テスト名/出力抜粋）を記載。 


3.2 PRチェックリスト

[ ] タスクID / 目的 / 変更ファイルが Masterの記載と一致。 

[ ] 仕様遵守：エンドポイント、スキーマ、解決関数・1ホップ境界、N日リフレッチ。 

[ ] テスト：外部I/Oモック／数値近似／失敗系（429/タイムアウト）。 

[ ] ログ/ミドルウェア（X-Request-ID）の期待動作がユニットで確認できる。 

[ ] Alembic スクリプト追加/更新、ダウングレード手順あり。 



---

4. 重要仕様の要点（開発に影響するもののみ抜粋）

API：/healthz, /v1/symbols, /v1/prices, /v1/metrics。レスポンス形状は architecture.md の定義に準拠。 

DBスキーマ：symbols / symbol_changes（UNIQUE(new_symbol)で1ホップ保証）/ prices（PK (symbol,date), volume BIGINT, last_updated TIMESTAMPTZ DEFAULT now(), 値域CHECK）。 

シンボル変更の透過解決：1ホップ（例：FB→META）。get_prices_resolved(symbol, from, to) 関数で区間分割（date < change_dateは旧、>=は新）し、レスポンスは現行シンボル名（行に source_symbol 任意）。 

直近N日リフレッチ：配当/分割の遅延反映に備え、毎回 last_date - 30日 から再取得しUPSERT。Nは環境変数で調整。 

メトリクス：終値は調整後、r_t=ln(P_t/P_{t-1})、CAGR = exp(sum(r)*252/N)-1、STDEV = std(r,ddof=1)*sqrt(252)、最大DDは累積対数リターンから算出。欠損日はスキップ、共通営業日の交差で整列。 

デプロイ：Docker + Render。起動時 alembic upgrade head、/healthz をヘルスチェック。 

テスト方針：外部ネットワークは全モック、DB統合はコードのみ、CIで pytest を実行。 



---

5. ディレクトリ規約（作成・変更の指針）

ルート／app/ 以下の構成は architecture.md の推奨構成に一致させる（core/, api/v1/, db/, services/, schemas/, migrations/, management/, tests/）。新規ファイルは該当レイヤに置く。 



---

6. エージェント用標準プロンプト（雛形）

6.1 Planner

> System: あなたはソフトウェア開発のプランナーです。
User: Master Task List.md の tasks を読み、未完タスクのうち依存関係を満たす最小単位を1つ特定し、変更ファイル・関数シグネチャ・想定テスト名を列挙してください。仕様は architecture.md を最優先してください。



6.2 Coder

> System: あなたはコード専門エージェントです。
User: 指定タスクIDに対し、最小差分で実装し、同一PRにユニットテストを追加してください。外部I/Oはモックにします。architecture.md の仕様（API・DDL・1ホップ解決・N=30リフレッチ・メトリクス式）に厳密に従ってください。



6.3 Tester

> System: あなたはテストエージェントです。
User: タスクの受け入れ基準(AC)を満たす最小テストを作成し、失敗系（429/タイムアウト、検証エラー）も含めて提示してください。



6.4 Reviewer

> System: あなたはコードレビューワです。
User: 差分が仕様/DDL/式に適合しているか、PR本文にタスクIDとACの照合があるか、テストがモックで自立しているかを判定し、必要なら差し戻してください。



6.5 Migration

> System: あなたはDBマイグレーション担当です。
User: 変更に伴う Alembic スクリプト（アップ/ダウン）を生成し、alembic upgrade head で適用可能か（文字列上の整合）を確認してください。



6.6 Docs

> System: あなたはドキュメントエージェントです。
User: エンドポイントやデータ定義の差分を docs/ に反映し、architecture.md と矛盾がないか確認してください。




---

7. 作業ステップ（1タスク実行の定型）

1. 仕様確認：対象タスクと architecture.md の該当章を確認（エンドポイント/DDL/関数/式）。 


2. テスト先行：ACから最小ユニットテストを作成（I/Oはモック）。 


3. 実装：最小差分で関数/ルータ/DDLを追加。

/v1/prices は 解決区間→不足検知→取得→UPSERT→確定SELECT の順序を守る。 



4. セルフレビュー：PRチェックリストを満たすか確認。


5. PR作成：タイトルに TID、本文に AC照合 と テスト結果 を記載。




---

8. 品質ゲート（自動/手動）

静的規約：Black/Isort/Flake（任意）を推奨。

I/Oモック必須：yfinance、DB接続、スリープ/バックオフはモック。 

仕様一致：

DDLの制約（CHECK/PK/FK）。

get_prices_resolved の1ホップ区間分割。

直近30日の再取得起点。

メトリクス式と共通営業日の交差。 


E2E疑似：/v1/prices と /v1/metrics の契約テスト（全面モック）。 



---

9. よくある落とし穴と対策

複合PKとインデックスの二重化：(symbol,date) のPKがBTreeを持つため重複索引を作らない。 

日付境界：change_date 当日を新シンボルとして扱う（<旧 / >=新）。 

体感的な年率式の取り違え：exp(sum(r))^(252/N) と exp(sum(r)*252/N) は等価。実装は後者で一貫。 

外部I/O混入：テストで実通信/実スリープを入れない。 



---

10. 変更が仕様に影響する場合の手順

1. Reviewerが architecture.md の該当項目を特定し、影響度を整理。


2. Plannerが変更案を作成（互換/破壊を明記）。


3. Docsが architecture.md と docs/ を更新し、ソースの優先順位（§1）を保ったまま合意形成。 




---

11. 付録：主要仕様のクイックリファレンス

API：/healthz, /v1/symbols, /v1/prices, /v1/metrics。 

DDL：symbols / symbol_changes(UNIQUE(new_symbol)) / prices(PK(symbol,date), volume BIGINT, last_updated TIMESTAMPTZ, CHECK群)、get_prices_resolved(...) 関数。 

実装パイプライン：Resolver → Gap検知 → Fetcher（N=30, backoff） → UPSERT → 最終SELECT。 

メトリクス：CAGR=exp(sum(r)*252/N)-1, STDEV=std(r)*sqrt(252), MaxDD は累積対数から。 

テスト原則：外部I/Oモック、DBはコードのみ。CIで pytest。 



---

最後に

本Agents.mdは運用プロトコルであり、仕様の正本ではありません。必ず architecture.md と Master Task List.md を併読してください。 



---

参考ソース

リポジトリのアーキテクチャ／API／DDL／運用方針：architecture.md。 

タスクリスト／受け入れ基準：Master Task List.md。 

実行用タスクリストテンプレ：tasklist.md。 



---

