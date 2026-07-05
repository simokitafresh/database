# 価格データソース多重化計画 — As-Is / To-Be 5W1H

作成: 2026-07-03 将軍 | 更新: 2026-07-05 Phase 0完了+実測結果+イベントテーブル設計追加
発端: 殿指示「より正しい株価の取得」(2026-07-03 15:15) | 根拠調査: DM-Signal cmd_3676-3680(TECL/XLU反転の因果特定)+cmd_3683(11ベンダー比較)

## 0. 経緯(1分で読める要約)

2026-07-03、New Fund of Funds_copy_copyの7月確定ポジションが夜間に**TECL 100%→XLU 100%へ無音で書き換わった**。調査の結論:

- 計算コードは無変更(2忍者独立検証で確定)。バグではなく**入力価格の事後変化**が原因
- 機序: yfinanceを`auto_adjust=True`(調整済み値)で取得しつつ、再取得窓は**直近7日のみ**(`YF_REFETCH_DAYS=7`)。配当確定でyfinanceは過去全期間の調整値を再計算するが、7日より古い行は**古い調整係数のまま凍結**される。取得タイミングにより「同じ6/30終値」が異なる値になる
- さらにyfinanceは非公式API(確定値/暫定値の境界保証なし・検証手段なし・調整方式ブラックボックス)

**2026-07-05追記**: cmd_3685で全期間再取得に切り替えた結果、凍結ムラは解消したが別の問題が発生。毎日の全期間再取得でyfinanceの遡及修正を毎日拾い、確定済みシグナルが日々変動(7/4: 426件→7/5: 11,309件、26倍増大)。シン青龍-鉄壁はXLU(正)→TECLに再反転。**7日窓でも全期間でも、yfinanceの調整済み値を直接保存する限りこの問題は解決しない。**

## 1. As-Is (現状) — 5W1H

| | 現状 |
|---|---|
| **Who** | Stockdata-API(このリポジトリ)が唯一の取得者。DM-Signalは本APIの消費者 |
| **What** | yfinance**単一ソース**の調整済みOHLCV。^VIX含む13コアシンボル+全ユニバース |
| **When** | 毎晩cron(23:00 JST全期間+日次L0 01:00)。cmd_3685で全期間再取得に変更済み |
| **Where** | `app/services/fetcher.py` `yf.download(auto_adjust=True)` / `app/core/config.py:30 YF_REFETCH_DAYS=全期間` |
| **Why** | 無料・手軽・全銘柄対応のため初期採用 |
| **How** | 調整済み値をそのままpricesへUPSERT。**生値と調整イベントの分離なし・値履歴なし・検証ソースなし** |

**構造的弱点(3つ)**: (1)単一ソースで誤値を検知できない (2)調整済み値の直接保存=yfinanceの遡及再計算が毎日反映→シグナルが日々変動 (3)確定値の境界が存在しない→確定表示済みシグナルが事後に動く

## 2. To-Be (あるべき姿) — 5W1H

| | あるべき姿 |
|---|---|
| **Who** | **3ソース多数決**: Alpaca(SIP明言)+EODHD($19.99/mo)+Tiingo(無料)。^VIXは**CBOE公式CSV直取得**(無料・本番値と完全一致を実測済み) |
| **What** | **生値(無調整)を正本として保存**し、確定済み(ex-date通過済み)配当・分割イベントのみ自前適用して調整値を都度導出 |
| **When** | 月末最終営業日の市場終了後に確定値を取得→月初のリバランス判定はこの確定値のみ使用→**判定後は月内不変**(殿の不変量) |
| **Where** | Stockdata-API(このリポジトリ)に多重化層を実装。DM-Signal側は変更不要(APIの中身が強くなるだけ) |
| **Why** | 殿の要件「リバランス判定時点(月末open/close)で公式確定値+確定済み調整が揃えば、モメンタム計算は以後ずれない」を構造で保証するため |
| **How** | 毎晩3ソースの月末近傍open/closeを突合→**2/3以上一致で採用、不一致は警報**。生値は不変なので凍結ムラが原理的に消滅 |

## 3. 移行フェーズ計画

| Phase | 内容 | 担当 | 状態 |
|---|---|---|---|
| **Phase 0** | APIキー発行→`.env`へ記入 | 殿 | **完了(2026-07-05)** |
| **Phase 1** | 実測乖離測定: 4ソース(Alpaca/EODHD/Tiingo/yfinance)×全コアシンボル×直近月末open/closeを突合。未解決2点(Alpaca IEXフィードの精度/EODHDの終値方式)を実測で決着 | 忍者(cmd_3687) | **完了(2026-07-05)** |
| **Phase 2** | 多数決監視の実装: 毎晩3ソース突合+不一致警報。プライマリ切替の最終判断材料を蓄積 | 忍者 | Phase 1後 |
| **Phase 3** | 生値+自前調整への移行: §6のアーキテクチャ実装。DM-Signal APIの互換性維持 | 忍者(設計書→段階実装) | Phase 2後 |

並行して DM-Signal 側は実装済み: 確定シグナル変更の即時警報(cmd_3679)・計算入力スナップショット+月初夕方再計算(cmd_3681)・Next Signal欄化(cmd_3682)・通知バッチ化(cmd_3686)。

## 4. Phase 0 完了記録

### 4.1 発行済みキー(2026-07-05)

| サービス | 環境変数 | 状態 |
|---------|---------|------|
| Alpaca Markets | `ALPACA_API_KEY_ID`, `ALPACA_API_SECRET_KEY` | ✅ Paper Trading, Account ACTIVE |
| EODHD | `EODHD_API_TOKEN` | ✅ 無料枠(20call/日) |
| Tiingo | `TIINGO_API_TOKEN` | ✅ 無料枠 |

### 4.2 接続検証結果(2026-07-05 20:39 JST)

LQD 6/30の4ソース突合:

| ソース | open | close(生値) | close(調整済) | volume |
|--------|------|------------|-------------|--------|
| **Stockdata(yfinance)** | 109.116 | — | **108.688** | 32,665,400 |
| **Alpaca(IEX)** | 109.515 | **109.06** | — | 2,831,752 |
| **EODHD** | 109.50 | **109.07** | 108.688 | 32,665,400 |
| **Tiingo** | 109.50 | **109.07** | 108.688 | 32,665,351 |

**発見:**
- Stockdata(yfinance)は`auto_adjust=True`のため、保存値=調整済み値(108.688)。生値(109.07)は保存されていない
- EODHD/Tiingoの生値close=109.07で一致。調整済みclose=108.688でも一致
- Alpaca IEXフィードのclose=109.06は1セント差(IEX=部分取引所のため)。SIPフィード(有料)なら一致する可能性大
- yfinanceの調整済み値(108.688)はEODHD/Tiingoの調整済み値(108.688)と一致 — **現時点では調整計算は正しいが、取得タイミングで変わりうるのが問題**

## 4.3 Phase 1 実測結果(cmd_3687, 2026-07-05)

対象: LQD, TECL, XLU, QQQ, GLD, SPY, TQQQ, TMV, GDX, QLD, TMF, VIX × 2026-04-30 / 2026-05-29 / 2026-06-30 × Alpaca / EODHD / Tiingo / Stockdata(yfinance) のopen/close。

成果物:
- `scripts/compare_price_sources.py`
- `reports/price_source_comparison/price_source_raw.csv` (144取得ポイント)
- `reports/price_source_comparison/price_source_summary.csv` (36 symbol-date行)
- `reports/price_source_comparison/price_source_summary.md`

主要数値:
- source_points_ok: 138/144
- raw_source_rows_with_2plus_sources: 33/36
- EODHD/Tiingo raw close 0.01ドル以内一致: 33/33
- Alpaca IEX raw close vs raw median 0.01ドル以内一致: 6/33
- 最大raw close乖離: 0.33ドル(QQQ 2026-06-30)
- yfinance adjusted vs EODHD adjusted 最大乖離: 0.411289746ドル
- yfinance adjusted vs Tiingo adjusted 最大乖離: 0.411954441ドル

未解決2点の決着:
- Alpaca IEXフィード: `feed=iex` + `adjustment=raw`で実測。無料IEXは多数決の第三チェックには使えるが、33比較行中6行しか0.01ドル以内に収まらず、SIP相当の正本候補とは扱わない。
- EODHDの終値方式: VIXを除く33比較行でTiingo raw closeと完全一致(0.00差分)。EODHDは月$19.99のprimary候補、Tiingoは独立検証候補として妥当。

制約:
- VIXはAlpaca stock bars非対応、Tiingo daily `^VIX` は404。EODHD `VIX.INDX` とyfinance `^VIX` は取得できたが、VIXはCBOE公式CSV等の別公式ソースを分岐採用する必要がある。

推薦:
- Primary候補: EODHD
- Independent verifier: Tiingo
- Third check: Alpaca IEX(無料枠)。SIP同等性を要求するなら有料SIPの別裁定が必要
- yfinance/Stockdata: adjusted参照値として残すが、生値正本にはしない

## 5. 判断済み事項と保留事項

| 事項 | 状態 |
|---|---|
| Stockdata-API側の全期間差分ログ | **見送り**(殿裁定2026-07-03 14:50。スナップショットで監査十分・後から追加可) |
| Norgate/CSI/Stooq | **不採用**(Linux常駐不可×2・ボット遮断×1) |
| 予算 | 月$100以内(殿裁定)。現推奨構成は**約$20/mo**(EODHD)+無料×2 |
| プライマリ最終確定 | **保留** — Phase 1実測ではEODHD primary候補/Tiingo verifier候補を推薦。最終採用は殿裁定 |
| yfinanceの扱い | Phase 2までは現行維持(第4の参照値として突合に残す)。Phase 3で生値正本化と同時に役割再定義 |
| Alpaca IEX vs SIPフィード | **Phase 1で実測決着** — IEXは多数決の第三チェック用途。SIP相当の正本候補にはしない |

## 6. 生値+自前調整アーキテクチャ(Phase 3設計)

### 6.1 データモデル

```
prices_raw (新テーブル — 正本・不変)
├─ PK: (symbol, date, source)
├─ open, high, low, close, volume
├─ fetched_at (取得時刻)
└─ consensus_close (多数決確定値。2/3一致で採用)

corporate_events (新テーブル — 確定後追加のみ)
├─ PK: (symbol, event_date, event_type)
├─ event_type: 'dividend' | 'split'
├─ dividend_amount / split_ratio
├─ ex_date, record_date, pay_date
├─ confirmed_at (確定時刻)
├─ source_count (何ソースで確認したか)
└─ sources_json (各ソースの値)

prices (既存テーブル — 互換性維持)
├─ 従来通りのスキーマ
└─ 値は prices_raw.consensus_close × corporate_events から都度導出
    または導出結果をキャッシュ(確定イベント追加時に再計算)
```

### 6.2 調整値導出フロー

```
1. prices_raw に3ソースの生値を保存(毎晩cron)
2. 多数決: 同一(symbol, date)に対し3ソースのcloseを比較
   - 2/3以上一致(許容差0.01) → consensus_close確定
   - 不一致 → 警報+手動確認待ち(consensus_close=NULL)
3. corporate_events に配当/分割を保存(3ソースのイベントAPIから取得)
   - ex_date通過済みイベントのみconfirmed
   - pending(未到来)イベントは参考記録のみ、調整には使わない
4. 調整値導出: consensus_close × 確定済みイベントの累積調整係数
   - 配当: cumulative_factor *= (1 - dividend / close_before_ex)
   - 分割: cumulative_factor *= split_ratio
5. prices テーブルに導出結果を書き込み(DM-Signal API互換)
```

### 6.3 イベント取得ソース

| ソース | 配当API | 分割API | 備考 |
|--------|--------|--------|------|
| Alpaca | Corporate Actions API | 同上 | SIP確定データ。無料 |
| EODHD | `/api/div/{symbol}` | `/api/splits/{symbol}` | 全履歴取得可能 |
| Tiingo | `divCash`/`splitFactor` in daily prices | 同上 | 日次価格に含まれる |

Stockdata APIに既存の`/v1/events`基盤(dividends/splits/confirm/ignore)を活用。3ソースから取得→多数決→confirm/ignoreのワークフロー。

### 6.4 DM-Signal側の変更

**変更ゼロ。** DM-Signalは`STOCK_API_BASE_URL`経由でStockdata APIの`/v1/prices`を呼ぶだけ。Stockdata API内部が生値→調整値導出に変わっても、返すデータのスキーマは同一。

### 6.5 移行時の結果変化

- 自前調整値 vs yfinance調整値は、同じイベント(配当額/分割比率)を適用する限り**理論上一致**
- 差が出るケース: yfinanceが未確定の配当予測を先取りして調整に含めている場合のみ
- Phase 1で4ソースの調整済み値も含めて突合済み。yfinance adjusted vs EODHD/Tiingo adjustedの最大乖離は約0.412ドル
- 差が許容範囲(全コアシンボルで±0.01以内)なら移行による結果変化は実質ゼロ

## 7. APIキー取得ステップバイステップガイド

※ Phase 0完了済み(2026-07-05)。以下は記録として残す。

### 7.1 Alpaca Markets (無料・クレカ不要・約3分)

1. https://app.alpaca.markets/signup を開く
2. メールアドレスとパスワードを入力して「Sign up」(Googleアカウントでも可)
3. 確認メールが届く → メール内のリンクをクリックして認証
4. ログイン後、左メニューまたは右上から **「Paper Trading」** 環境を選ぶ(実口座開設・入金は**不要**。Paper環境のキーでMarket Data APIが使える)
5. ダッシュボード右側の **「API Keys」** セクションで「Generate New Keys」をクリック
6. **API Key ID** と **Secret Key** の2つが表示される(Secretはこの画面でしか見られないので即コピー)
7. `.env` の `ALPACA_API_KEY_ID=` と `ALPACA_API_SECRET_KEY=` に貼り付け

### 7.2 EODHD (無料枠で実測可・クレカ不要・約2分)

1. https://eodhd.com/register を開く
2. メールアドレスを入力して登録(Google連携でも可)
3. 確認メール内のリンクで認証 → 自動でダッシュボードへ
4. ダッシュボード上部に **「API Token」** が最初から表示されている(発行操作は不要)
5. `.env` の `EODHD_API_TOKEN=` に貼り付け
- 備考: 無料枠は20call/日+限定銘柄。Phase 1実測ではprimary候補として妥当と判定。本採用時は「EOD Historical Data — All World」($19.99/mo)へアップグレードする

### 7.3 Tiingo (無料・クレカ不要・約2分)

1. https://www.tiingo.com/ を開き右上「Sign-up」
2. メールアドレス・ユーザー名・パスワードを入力して登録
3. 確認メール内のリンクで認証
4. ログイン後 https://www.tiingo.com/account/api/token を開くと **API Token** が表示されている
5. `.env` の `TIINGO_API_TOKEN=` に貼り付け
