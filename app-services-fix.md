

---

調査スコープと前提

対象: app/services 配下のモジュール（少なくとも fetcher.py, metrics.py、およびそれらを利用する呼び出し箇所）

fetcher.py のリトライ/バックオフ実装は app/core/config.py の設定を参照しています。

metrics.py は共通営業日インデックスの扱いを修正しています。


呼び出し側: app/api/v1/prices.py の async def get_prices(...) が fetcher.fetch_prices(...) を直接呼び、DB への書き込み/読み出しを行っています。

CLI では from app.services import normalize を行っているため、app/services のパッケージ解決が前提です。



---

クリティカル/高リスクな指摘（根拠付き）

1. 非同期エンドポイント内でのブロッキング I/O（イベントループ阻害）



GET /v1/prices の実装は async def にも関わらず、同期関数の fetcher.fetch_prices(...) をそのまま呼び出しています。
一方 fetcher は内部で time.sleep を使ったバックオフを行うため、イベントループがブロックされる可能性が高いです（高負荷でスループット低下・タイムアウト誘発）。


2. HTTP エラー種別の取り扱いが不統一で、リトライ条件を取り逃す恐れ



fetcher.py の例外ハンドリングが HTTPError（urllib.error.HTTPError 想定）と TimeoutError を束ねていますが、Yahoo 側の 429/999 等で requests.exceptions.HTTPError が来た場合、exc.code ではなく exc.response.status_code になるため、429 をリトライ対象として認識できないケースが起こり得ます。
実装は exc.code in {429, 999} を前提にしており、requests 系を取りこぼす懸念があります。


3. 設定値の未活用（FETCH_TIMEOUT_SECONDS）



設定に FETCH_TIMEOUT_SECONDS が定義されていますが、yfinance.download へ timeout を渡している形跡が見当たりません。サードパーティの実装事情はありますが、サポートされる範囲で タイムアウトを確実に適用すべきです（本番障害の火種）。


4. （改善）メトリクス計算の空/1 日データの扱いは改善済みだが、NaN/inf の最終保証が弱い



metrics.py は「共通営業日 <= 1」の場合にゼロで返すよう修正され健全ですが、価格 0 や欠損が混じると log 計算に -inf/NaN が混入し得ます。最終出力の数値健全性をユニットテストで保証すると安全です。


> 参考: 既存テストには fetch リトライ（タイムアウト）や共通営業日の交差などが含まれます。




---

修正タスクリスト（小さく・検証可能・単一関心／進捗チェック可）

> 記法:

ID は一意。

完了条件 はすべて「テストで確認可能」です。

担当 や 日付 は空欄のままでも OK（Codex 実装後に記入）。




A. イベントループ阻害の解消（最優先）

[x] A-01: fetcher の呼び出しをスレッドプールでオフロード
目的: async ルートでのブロッキング回避。
変更: app/api/v1/prices.py の fetcher.fetch_prices(...) 呼び出しを from starlette.concurrency import run_in_threadpool に置き換え、await run_in_threadpool(fetcher.fetch_prices, actual, fetch_start, seg_to, settings=settings) とする。
完了条件: 既存の tests/unit/test_prices_* がすべて GREEN。高負荷時でもイベントループを塞がない（コード上でブロッキング呼び出しが消えること）。
根拠: ルートは async def / fetcher は time.sleep を利用。
変更ファイル: app/api/v1/prices.py

[x] A-02: 逐次化されているシンボル処理に並行度制限を導入（任意だが効果大）
目的: 上流 API 呼び出しのスループット最適化と過負荷抑制。
変更: settings.YF_REQ_CONCURRENCY を用い、anyio.Semaphore でシンボルごとの run_in_threadpool を gather しながら同時実行数を制御。
完了条件: ユニットテストで同時実行数上限（モックで sleep）を検証（最大 N 回以上同時に呼ばれない）。
根拠: 設定に YF_REQ_CONCURRENCY が存在。
変更ファイル: app/api/v1/prices.py, （必要なら）app/core/config.py


B. HTTP エラー判定の互換性強化

[x] B-01: requests.exceptions.HTTPError にも対応
目的: 429/999 を確実にリトライ対象にする。
変更: app/services/fetcher.py で from urllib.error import HTTPError as URLlibHTTPError および from requests.exceptions import HTTPError as RequestsHTTPError をインポートし、
except (URLlibHTTPError, RequestsHTTPError, TimeoutError) as exc: のように束ねる。
判定: status = getattr(exc, "code", None) or getattr(getattr(exc, "response", None), "status_code", None) を導出し、status in {429, 999} をリトライ判定に使う。
完了条件: 新規テスト

test_fetcher_retries_on_requests_http_error_429: requests.exceptions.HTTPError(response.status_code=429) をモック→規定回数リトライ後成功/失敗が期待通り。
既存 test_fetcher_retry_timeout.py を壊さない。
変更ファイル: app/services/fetcher.py, tests/unit/test_fetcher_retry_timeout.py（または新規）


[x] B-02: 「999」も確実に拾う（Yahoo のレート制御）
目的: HTTP 999 を見逃さない。
変更: 上記 B-01 の status in {429, 999} 判定で網羅。
完了条件: 999 をステータスとする例外のモックテストを追加し、リトライ実施が確認できること。
変更ファイル: 同上


C. タイムアウト適用の徹底

[x] C-01: yfinance へ timeout を明示的に伝播
目的: 行儀の悪い応答でハングしないようにする。
変更: fetcher.fetch_prices の yf.download(...) に timeout=settings.FETCH_TIMEOUT_SECONDS を kwargs で渡す（サポートされていれば）。非対応なら requests セッションの Timeout を yfinance の内部呼び出しで反映させる代替策をコメントで残す。
完了条件: 新規テストで yf.download の呼び出し引数に timeout=... が含まれることをモックで検証。
根拠: 設定項目は既に存在。
変更ファイル: app/services/fetcher.py, tests/unit/test_fetcher_retry_timeout.py（または新規）


D. 返却データ整形の堅牢化（改善）

[x] D-01: 列名正規化のテスト強化
目的: ["Open","High","Low","Close","Volume"]/"Adj Close" など yfinance 側の差異を安定して正規化。
変更: 既存の整形ロジックを前提に、Adj Close → adj_close 除去、および 最終的に小文字列 ["open","high","low","close","volume"] で返ることを確認するユニットテストを追加。
完了条件: テストが通ること（既存の test_fetcher_retry_timeout のカラム検証と整合）。
変更ファイル: tests/unit/test_fetcher_*


E. metrics の数値健全性（改善）

[x] E-01: NaN/inf サニタイズの最終保証
目的: ログ収益率の演算で例外値が出ても API は常に有限実数を返す。
変更: compute_metrics の最終計算後に np.isfinite チェックを入れ、非有限は 0.0 など安全値にフォールバック。
完了条件: 新規テスト test_metrics_returns_finite_values_even_with_zeros を追加し、0/欠損/一定系列でも float 有限値が返ること。
参考: 空/1 日は既に安全化済み。
変更ファイル: app/services/metrics.py, tests/unit/test_metrics_*


F. パッケージ解決の安定化（小改善）

[x] F-01: app/services/__init__.py の存在確認と __all__ 定義
目的: from app.services import normalize などの 明示的 import がどの環境でも安定するようにする（PEP 420 の名前空間パッケージでも動くが、明示初期化で事故を減らす）。
変更: __init__.py が無ければ作成し、__all__ = ["fetcher","metrics","normalize","resolver","upsert"] を宣言。
完了条件: ユニットテストで importlib.reload(app.services); from app.services import normalize が成功すること。
根拠: CLI で from app.services import normalize を使用。
変更ファイル: app/services/__init__.py, tests/unit/test_import_services.py（新規）



---

影響範囲と互換性

A 系（スレッドプール化）は 外部仕様を変えず にスループットと安定性を向上。既存ユニットテストはそのまま Green になる想定です（I/O の実行方法のみ変更）。

B/C 系は 例外経路の網羅性強化 で、本番でのリトライ漏れ/ハング低減に直結。

D/E/F は品質/保守性の底上げ（API 仕様やテーブルスキーマは不変）。



---

参考（根拠リンク）

fetcher.py のリトライ・バックオフと Settings 参照（FETCH_MAX_RETRIES, FETCH_BACKOFF_MAX_SECONDS）— time.sleep によるブロッキングが存在。

prices.py は async def ルートの中で fetcher.fetch_prices(...) を直接呼んでいます。

metrics.py の「共通営業日 <= 1 の場合は安全値で返す」修正。

CLI は from app.services import normalize をインポート。



---

実行手順（Codex 用メモ）

1. タスク A/B/C/D/E/F を上から順に適用。


2. 既存テスト + 追加テストを実行： make test（または pytest -q）。リグレッションが出たら該当タスクに戻って修正。




---


