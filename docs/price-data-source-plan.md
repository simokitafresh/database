# 価格データソース多重化計画 — As-Is / To-Be 5W1H

作成: 2026-07-03 将軍 | 更新: 2026-07-05 22:51 全Phase状況+実測結果+殿裁定+エッジケース+運用修正を反映
発端: 殿指示「より正しい株価の取得」(2026-07-03 15:15) | 根拠調査: DM-Signal cmd_3676-3680(TECL/XLU反転の因果特定)+cmd_3683(11ベンダー比較)

## 0. 経緯(1分で読める要約)

2026-07-03、New Fund of Funds_copy_copyの7月確定ポジションが夜間に**TECL 100%→XLU 100%へ無音で書き換わった**。調査の結論:

- 計算コードは無変更(2忍者独立検証で確定)。バグではなく**入力価格の事後変化**が原因
- 機序: yfinanceを`auto_adjust=True`(調整済み値)で取得しつつ、再取得窓は**直近7日のみ**(`YF_REFETCH_DAYS=7`)。配当確定でyfinanceは過去全期間の調整値を再計算するが、7日より古い行は**古い調整係数のまま凍結**される。取得タイミングにより「同じ6/30終値」が異なる値になる
- さらにyfinanceは非公式API(確定値/暫定値の境界保証なし・検証手段なし・調整方式ブラックボックス)

**2026-07-05 事態の進展**: cmd_3685で全期間再取得に切り替えた結果、凍結ムラは解消したが別の問題が発生。毎日の全期間再取得でyfinanceの遡及修正を毎日拾い、確定済みシグナルが日々変動(7/4: 426件→7/5: 11,309件、26倍増大)。シン青龍-鉄壁はXLU(正)→TECLに再反転。**7日窓でも全期間でも、yfinanceの調整済み値を直接保存する限りこの問題は解決しない。** 殿との議論で根本解決は「生値+自前調整」と結論。本計画のPhase 0-2を同日中に完了し、Phase 3(生値正本化)に着手。

## 1. As-Is (現状) — 5W1H

| | 現状 |
|---|---|
| **Who** | Stockdata-API(このリポジトリ)が唯一の取得者。DM-Signalは本APIの消費者 |
| **What** | yfinance**単一ソース**の調整済みOHLCV。^VIX含む13コアシンボル+全ユニバース |
| **When** | cron JST 08:00(一次取得)+JST 17:00(確定取得)の2回(cmd_3688で01:00単発から変更)。全期間再取得(cmd_3685) |
| **Where** | `app/services/fetcher.py` `yf.download(auto_adjust=True)` / `app/core/config.py:30 YF_REFETCH_DAYS=全期間` |
| **Why** | 無料・手軽・全銘柄対応のため初期採用 |
| **How** | 調整済み値をそのままpricesへUPSERT。**生値と調整イベントの分離なし・値履歴なし・検証ソースなし** |

**構造的弱点(3つ)**: (1)単一ソースで誤値を検知できない (2)調整済み値の直接保存=yfinanceの遡及再計算が毎日反映→シグナルが日々変動 (3)確定値の境界が存在しない→確定表示済みシグナルが事後に動く

## 2. To-Be (あるべき姿) — 5W1H

| | あるべき姿 |
|---|---|
| **Who** | **EODHD(プライマリ)+Tiingo(独立検証)+Alpaca IEX(第三チェック)**。^VIXは**CBOE公式CSV直取得**(無料・本番値と完全一致を実測済み) |
| **What** | **生値(無調整)を正本として保存**し、確定済み(ex-date通過済み)配当・分割イベントのみ自前適用して調整値を都度導出。EODHDはclose(生値)とadjusted_close(調整済み)を同時に返すため、自前調整値の検算にも使える |
| **When** | cron JST 08:00(一次取得+暫定計算)+JST 17:00(確定取得+入力確定検証)。月末最終営業日の市場終了後に確定値取得→月初のリバランス判定はこの確定値のみ使用→**判定後は月内不変**(殿の不変量) |
| **Where** | Stockdata-API(このリポジトリ)に多重化層を実装。DM-Signal側は変更不要(APIの中身が強くなるだけ) |
| **Why** | 殿の要件「リバランス判定時点(月末open/close)で公式確定値+確定済み調整が揃えば、モメンタム計算は以後ずれない」を構造で保証するため |
| **How** | EODHD/Tiingoの生値closeを突合→一致(許容差±0.01)で採用、不一致は警報。生値は不変なので凍結ムラが原理的に消滅 |

## 3. 移行フェーズ計画

| Phase | 内容 | 担当 | 状態 |
|---|---|---|---|
| **Phase 0** | APIキー発行→`.env`記入+EODHDアップグレード | 殿 | **完了(2026-07-05)** |
| **Phase 1** | 実測乖離測定: 4ソース×全コアシンボル×直近3月末のopen/close突合 | cmd_3687 | **完了(2026-07-05)** |
| **Phase 2** | 多数決監視+入力確定検証: EODHD/Tiingo突合cron(JST 08:00/17:00)+月初入力確定検証+不一致警報 | cmd_3688 | **完了(2026-07-05)** |
| **Phase 3** | 生値+自前調整への移行: §6のアーキテクチャ実装。DM-Signal APIの互換性維持 | cmd_3689 | ★今ここ |

並行してDM-Signal側は実装済み: 確定シグナル変更の即時警報(cmd_3679)・計算入力スナップショット+月初夕方再計算(cmd_3681)・Next Signal欄化(cmd_3682)・通知バッチ化(cmd_3686)。

## 4. 完了記録

### 4.1 Phase 0: APIキー発行+アップグレード(2026-07-05)

| サービス | 環境変数 | プラン | 状態 |
|---------|---------|-------|------|
| Alpaca Markets | `ALPACA_API_KEY_ID`, `ALPACA_API_SECRET_KEY` | Paper Trading(無料) | ✅ Account ACTIVE |
| EODHD | `EODHD_API_TOKEN` | **EOD+Intraday All World Extended($29.99/mo)** | ✅ アップグレード済み(殿操作2026-07-05 21:24) |
| Tiingo | `TIINGO_API_TOKEN` | 無料 | ✅ |

### 4.2 Phase 0: 接続検証(2026-07-05 20:39 JST)

LQD 6/30の4ソース突合:

| ソース | open | close(生値) | close(調整済) | volume |
|--------|------|------------|-------------|--------|
| **Stockdata(yfinance)** | 109.116 | — | **108.688** | 32,665,400 |
| **Alpaca(IEX)** | 109.515 | **109.06** | — | 2,831,752 |
| **EODHD** | 109.50 | **109.07** | 108.688 | 32,665,400 |
| **Tiingo** | 109.50 | **109.07** | 108.688 | 32,665,351 |

**重要な発見:**
- **EODHDはclose(生値)とadjusted_close(調整済み)を同時に返す** — 生値を正本保存しつつ、EODHDのadjusted_closeで自前調整値を検算できる
- Stockdata(yfinance)は`auto_adjust=True`のため、保存値=調整済み値(108.688)。**生値(109.07)は保存されていない**
- EODHD/Tiingoの生値close=109.07で完全一致。調整済みclose=108.688でも完全一致
- Alpaca IEXフィードのclose=109.06は1セント差(IEX=部分取引所)

### 4.3 Phase 0: Alpaca IEX精度(全コアシンボル実測 2026-07-05 21:06 JST)

| 銘柄 | IEX vs EODHD乖離 |
|------|-----------------|
| XLU, GLD | **0.0bp**(完全一致) |
| LQD | **0.9bp**(1セント差) |
| SPY, TQQQ | **1.2-1.6bp** |
| QQQ | **4.5bp** |
| **TECL, TMV** | **10.8-11.7bp**(レバレッジETFで差大) |

結論: Alpaca IEXは無料の第三チェック用途。SIP(年$1,000)は不要。

### 4.4 Phase 0: EODHD配当API実証(2026-07-05 21:08 JST)

```
LQD 2026H1配当: 5件取得成功
直近: ex_date=2026-06-01, value=$0.41325/月, period=Monthly
```

EODHD `/api/div/{symbol}` で全履歴取得可能。Phase 3のcorporate_eventsテーブル構築に利用する。

### 4.5 Phase 1: 実測乖離測定(cmd_3687, 2026-07-05)

対象: LQD, TECL, XLU, QQQ, GLD, SPY, TQQQ, TMV, GDX, QLD, TMF, VIX × 2026-04/05/06月末 × 4ソース

成果物: `scripts/compare_price_sources.py`, `reports/price_source_comparison/`

| 指標 | 値 |
|------|---|
| source_points_ok | 138/144 |
| EODHD/Tiingo raw close ±0.01一致 | **33/33(100%)** |
| Alpaca IEX vs median ±0.01一致 | 6/33(18%) |
| yfinance adj vs EODHD adj 最大乖離 | 0.412ドル |

**未解決2点の決着:**
- Alpaca IEX: SIP相当の正本候補にはしない(精度不足)
- EODHD終値: Tiingoと33/33完全一致。プライマリとして妥当

### 4.6 Phase 2: 多数決監視+入力確定検証(cmd_3688, 2026-07-05)

- EODHD/Tiingo 2ソース突合cron(JST 08:00/17:00)
- 月初入力確定検証(前月最終営業日の全コアシンボル行存在検証)
- 不一致時ntfy警報

### 4.7 Render cronジョブ環境変数修正(2026-07-05 22:30 JST)

新規追加された2つのcronジョブにADMIN_USER/ADMIN_PASSが未設定だった(401エラーの原因):
- `dm-signal-precompute-raw` (crn-d92qh8daeets73agabjg) — 修正済み
- `dm-signal-month-start-evening-recalculate` (crn-d93n6flckfvc738rbp20) — 修正済み

根因: Render cronジョブはbackendサービスと環境変数を共有しない。各ジョブに個別設定が必要。

## 5. 判断済み事項と保留事項

| 事項 | 状態 |
|---|---|
| Stockdata-API側の全期間差分ログ | **見送り**(殿裁定2026-07-03 14:50) |
| Norgate/CSI/Stooq | **不採用**(Linux常駐不可×2・ボット遮断×1) |
| 予算 | 月$100以内(殿裁定)。**採用: EODHD EOD+Intraday All World Extended($29.99/mo)**+Tiingo(無料)+Alpaca IEX(無料)。年$360 |
| プライマリ | **EODHD確定**(殿裁定2026-07-05)。EOD+Intradayプランはリバランサーアプリにも活用可能 |
| EODHDプラン | **EOD+Intraday All World Extended**($29.99/mo=$299.90/年)。EOD価格+配当/分割API+調整済み値+イントラデイ |
| Calendar API | **不要**。未確定イベントは調整に使わない。Fundamentals($59.99+)不要 |
| yfinanceの扱い | Phase 3で生値正本化後、第4の参照値(adjusted検算用)に降格 |
| Alpaca SIPフィード | **不要**。年$1,000。IEX無料枠で第三チェック十分 |

## 6. 生値+自前調整アーキテクチャ(Phase 3設計)

### 6.1 データモデル

```
prices_raw (新テーブル — 正本・不変)
├─ PK: (symbol, date, source)
├─ open, high, low, close, volume
├─ fetched_at (取得時刻)
└─ consensus_close (多数決確定値。EODHD/Tiingo ±0.01一致で採用)

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
└─ 値は prices_raw.consensus_close × corporate_events から導出
    導出結果をキャッシュ(確定イベント追加時に再計算)
```

### 6.2 調整値導出フロー

```
1. prices_raw に EODHD/Tiingo/Alpaca の生値を保存(毎晩cron JST 08:00/17:00)
2. 多数決: EODHD/Tiingo close比較
   - ±0.01以内一致 → consensus_close確定(Phase 1で33/33=100%一致実証済み)
   - 不一致 → ntfy警報+手動確認待ち(consensus_close=NULL)
3. corporate_events に配当/分割を保存(EODHD /api/div, /api/splits から取得)
   - ex_date通過済みイベントのみconfirmed
   - pending(未到来)イベントは参考記録のみ、調整には使わない
4. 調整値導出: consensus_close × 確定済みイベントの累積調整係数
   - 配当: cumulative_factor *= (1 - dividend / close_before_ex)
   - 分割: cumulative_factor *= split_ratio
5. 導出結果をEODHDのadjusted_closeと照合(検算)
6. prices テーブルに書き込み(DM-Signal API互換)
```

### 6.3 イベント取得ソース

| ソース | 配当API | 分割API | 備考 |
|--------|--------|--------|------|
| EODHD(プライマリ) | `/api/div/{symbol}` | `/api/splits/{symbol}` | 全履歴取得可能。LQD 5件実証済み |
| Tiingo(検証) | `divCash`/`splitFactor` in daily prices | 同上 | 日次価格に含まれる |
| Alpaca(参考) | Corporate Actions API | 同上 | SIP確定データ。無料 |

Stockdata APIに既存の`/v1/events`基盤(dividends/splits/confirm/ignore)を活用。

### 6.4 DM-Signal側の変更

**変更ゼロ。** DM-Signalは`STOCK_API_BASE_URL`経由でStockdata APIの`/v1/prices`を呼ぶだけ。Stockdata API内部が生値→調整値導出に変わっても、返すデータのスキーマは同一。

### 6.5 移行時の結果変化

- 自前調整値 vs yfinance調整値: 同じイベント(配当額/分割比率)を適用する限り**理論上一致**
- Phase 1実測でyfinance adj vs EODHD/Tiingo adjの最大乖離は0.412ドル。これはyfinanceの取得タイミングによる調整係数差であり、**同一時点のEODHD/Tiingo adjusted_closeは完全一致(33/33)**
- 移行後はEODHD adjusted_closeで検算するため、自前調整の正確性を継続的に検証可能

## 7. 月末月初シグナル確定のエッジケース(2026-07-05追加)

殿との議論(2026-07-05 21:37)で洗い出したエッジケース一覧。Phase 2-3の実装で全て対処する。

| エッジケース | 発生条件 | リスク | 対処 |
|-------------|---------|-------|------|
| 配当落ち日=月末最終営業日 | LQD ex_date=6/30等 | 調整計算に当日配当を含めるか否かで結果分岐 | ルール: ex_date ≤ 月末最終営業日 → 調整に含める。翌月ex_date → 含めない |
| 月末最終営業日の価格が翌日まで未確定 | JST 08:00 cronで前日close取得するがEODHD更新は市場終了後数時間 | 前日データで誤計算 | **入力確定検証**: 全コアシンボルの前月最終営業日行存在検証。不在→pending維持+警報(Phase 2で実装済み) |
| 月初が休日(1/1等) | cronが「毎月1日」固定だと祝日に走らない | シグナル計算されない | 毎日実行+月変わり検知で対応(現行設計) |
| 分割が月末に発生 | TECL分割 ex_date=6/30 | 過去closeと当日closeに不連続 | 生値+自前調整: 分割ratio適用で過去値を調整 |
| ソース間の最終営業日判定不一致 | 半日取引(感謝祭翌日等) | 月末closeが1日ずれる | 多数決: EODHD/Tiingo一致する日を採用 |
| UTC/JST日跨ぎ | 米国市場close 16:00 ET = 翌日05:00 JST | 早朝cronが市場close前に走る | JST 08:00(市場close+2-3h後)+JST 17:00(確定)の2回cron(Phase 2で実装済み) |
| **複合: 配当落ち日=月末 × UTC/JST日跨ぎ** | 7/3 TECL/XLU事件の再現パターン | 最も危険 | 入力確定検証 + 夕方再計算 + 多数決の三重防御 |

**設計原則(殿裁定2026-07-03 12:52):** 月初シグナルは前月最終営業日のopen/close確定値で計算し月内不変であるべき。

## 8. APIキー取得ガイド

※ Phase 0完了済み(2026-07-05)。記録として残す。

### 8.1 Alpaca Markets (無料・クレカ不要・約3分)

1. https://app.alpaca.markets/signup を開く
2. メールアドレスとパスワードを入力して「Sign up」
3. 確認メール認証 → Paper Trading環境を選ぶ(実口座不要)
4. API Keys → Generate New Keys → API Key ID + Secret Key をコピー
5. `.env` の `ALPACA_API_KEY_ID=` と `ALPACA_API_SECRET_KEY=` に貼り付け

### 8.2 EODHD ($29.99/mo・クレカ要)

1. https://eodhd.com/register → 登録 → ダッシュボードのAPI Token取得
2. Pricing → **EOD+Intraday All World Extended**($29.99/mo)にアップグレード
3. `.env` の `EODHD_API_TOKEN=` に貼り付け

### 8.3 Tiingo (無料・クレカ不要・約2分)

1. https://www.tiingo.com/ → Sign-up → 確認メール認証
2. https://www.tiingo.com/account/api/token でAPI Token取得
3. `.env` の `TIINGO_API_TOKEN=` に貼り付け
