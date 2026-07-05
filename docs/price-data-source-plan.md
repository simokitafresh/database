# 価格データソース多重化計画 — As-Is / To-Be 5W1H

作成: 2026-07-03 将軍 | 更新: 2026-07-06 00:45 Phase 0-3完了+本番適用+精度検証+GS再キャリブレーション計画+殿裁定を統合
発端: 殿指示「より正しい株価の取得」(2026-07-03 15:15) | 根拠調査: DM-Signal cmd_3676-3680(TECL/XLU反転)+cmd_3683(11ベンダー比較)

## 0. 経緯

| 日付 | 出来事 |
|------|--------|
| 7/1 | 7月シグナル確定。ユーザーに表示開始 |
| 7/3 01:11 UTC | yfinanceの6/30価格到着→recalculate→シン青龍-鉄壁TECL→XLU無音書換え。FoF連鎖50PF影響 |
| 7/3 12:52 | 殿裁定「月初シグナルは月内不変であるべき」。防御3本柱実装開始 |
| 7/4 | cmd_3685(全期間再取得)初回cron→過去シグナル426件変動 |
| 7/5 10:13-11:03 | SIGNAL CHANGE ALERT: 11,309件/42PF。yfinance遡及修正が毎日蓄積 |
| 7/5 19:32-23:42 | 殿との議論→「生値+自前調整」が根本解決→Phase 0-3を4時間で実装+本番適用 |
| 7/5 23:50 | 本番fullrecalculate完了。102PF中8件のシグナル変更(7/1比) |
| 7/6 00:25 | 精度検証(cmd_3691): 58,734行照合→配当分母修正+丸め除去→反転リスク解消→19テストPASS |
| 7/6 00:39 | 殿裁定: L0-L3 GS再キャリブレーションではWFを選別に使わない(in-sample最適化維持) |

**核心**: yfinanceの調整済み値を直接保存する限り、7日窓でも全期間でもシグナルは毎日変動する。根本解決=EODHD生値(不変)+確定済み配当/分割イベントで自前調整。

## 1. As-Is (移行前) — 5W1H

| | 移行前 |
|---|---|
| **Who** | Stockdata-API → yfinance単一ソース |
| **What** | 調整済みOHLCV。生値と調整イベントの分離なし |
| **When** | cron JST 01:00単発(移行前) |
| **Where** | `fetcher.py` `yf.download(auto_adjust=True)` |
| **Why** | 無料・手軽のため初期採用 |
| **How** | 調整済み値をそのままpricesへUPSERT |

**構造的弱点**: (1)単一ソースで誤値検知不能 (2)調整済み値直接保存=遡及再計算が毎日反映 (3)確定値の境界なし

## 2. To-Be (移行後・本番稼働中) — 5W1H

| | 移行後 |
|---|---|
| **Who** | **EODHD(プライマリ/$29.99mo)** + Tiingo(検証/無料) + Alpaca IEX(第三チェック/無料) |
| **What** | **生値(close)を正本保存** + 確定済み配当/分割イベントで自前調整値を導出。EODHDのadjusted_closeで検算 |
| **When** | cron **JST 08:00**(一次取得) + **JST 17:00**(確定取得+入力確定検証) |
| **Where** | Stockdata-API `raw_price_pipeline.py` + `prices_raw`/`corporate_events`テーブル |
| **Why** | 生値は不変→同じ入力は常に同じ出力→シグナル日次変動が原理的に消滅 |
| **How** | EODHD/Tiingo生値closeを突合(±0.01一致で採用)→自前調整→prices互換書込み |

## 3. フェーズ計画

### 3.1 価格ソース移行(完了)

| Phase | 内容 | cmd | 状態 |
|-------|------|-----|------|
| Phase 0 | APIキー発行+EODHDアップグレード | — | **完了** |
| Phase 1 | 4ソース×全コアシンボル×3月末の実測乖離 | cmd_3687 | **GATE CLEAR** |
| Phase 2 | EODHD/Tiingo突合cron(JST 08:00/17:00)+月初入力確定検証 | cmd_3688 | **GATE CLEAR** |
| Phase 3 | 生値正本化: prices_raw+corporate_events+自前調整導出 | cmd_3689 | **GATE CLEAR** |
| 本番適用 | バックアップ+マイグレーション+fullrecalculate+3レイヤー検証 | cmd_3690 | **GATE CLEAR** |
| 精度検証 | 58,734行照合+配当分母修正+丸め除去+エッジケース19テスト | cmd_3691 | **GATE CLEAR** |

### 3.2 GS再キャリブレーション(次フェーズ)

入力価格がyfinance調整値→EODHD生値+自前調整に変わったため、全レイヤーのGS(グリッドサーチ)を再実行しチャンピオンを再選出する必要がある。

**殿裁定(2026-07-06 00:39)**: L0含め全レイヤーでWFは選別に使わない。in-sample最適化でチャンピオン選出。理由=動的にポジションを切り替える戦略では、特定の市場環境に尖ったパラメータにこそ価値がある。

設計書: `/mnt/c/Python_app/DM-signal/docs/design/gs-recalibration-plan.md`
gist: https://gist.github.com/simokitafresh/aba673b4902fd20cee833687406f73dc

| Phase | 内容 | パターン数 | 状態 |
|-------|------|----------|------|
| Phase A | L0(シン四神)GS再実行+チャンピオン選出 | 191,796 | 未着手 |
| Phase B | L1(シン忍法)GS ×7忍法直列 | 361,603 | 未着手 |
| Phase C | L1チャンピオン選出+本番PF更新 | — | 未着手 |
| Phase D | L2(奥義)GS ×7忍法直列 | 3,484,075 | 未着手 |
| Phase E | L2チャンピオン選出+本番PF更新 | — | 未着手 |
| Phase F | L3(秘奥義)GS ×7忍法直列 | 同上規模 | 未着手 |
| Phase G | L3チャンピオン選出+本番PF更新 | — | 未着手 |
| Phase H | 全102PF 3レイヤー検証 | — | 未着手 |

制約: 各忍法GSは直列1CMD(OOM防止。L3 RSS最大14.9GB/16GB環境)。道具磨きを先に行い所要時間を最小化する(殿方針)。

## 4. 実測データ

### 4.1 4ソース突合(LQD 6/30)

| ソース | close(生値) | close(調整済) | volume |
|--------|------------|-------------|--------|
| Stockdata(yfinance) | — | 108.688 | 32,665,400 |
| Alpaca(IEX) | 109.06 | — | 2,831,752 |
| **EODHD** | **109.07** | **108.688** | 32,665,400 |
| **Tiingo** | **109.07** | **108.688** | 32,665,351 |

### 4.2 Phase 1実測(全コアシンボル×3月末×4ソース)

| 指標 | 値 |
|------|---|
| EODHD/Tiingo raw close ±0.01一致 | **33/33(100%)** |
| Alpaca IEX vs median ±0.01一致 | 6/33(18%) |
| yfinance adj vs EODHD adj 最大乖離 | 0.412ドル |

### 4.3 Alpaca IEX精度(全コアシンボル)

| 乖離 | 銘柄 |
|------|------|
| 0.0bp | XLU, GLD |
| 0.9-1.6bp | LQD, SPY, TQQQ |
| 4.5bp | QQQ |
| 10.8-11.7bp | TECL, TMV(レバレッジETF) |

結論: Alpaca IEXは無料の第三チェック用途。SIP(年$1,000)は不要。

### 4.4 精度検証(cmd_3691)

- 全コアシンボル×全期間58,734行照合
- 配当分母修正+丸め除去で反転リスク1件解消
- 自前調整値 vs EODHD adjusted_close: IEEE 754ノイズ以下(最大0.000024)
- エッジケース19テスト全PASS

### 4.5 7/1→現在のシグナル変更(102PF全数確認)

| 区分 | PF数 |
|------|------|
| 7/1から変更あり | 11 |
| 7/1と同じ | 91 |

変更PF: DM-safe, DM-safe-2, DM2, DM2-test(生値切替) + GSシン加速R-激攻, GSシン変わり身-激攻, GSシン追い風-常勝(7/3変更維持) + FoF連鎖4件
**シン四神12体・奥義21体・秘奥義28体は全て7/1と不変。シン青龍-鉄壁は7/1のTECLに戻った。**

影響レポート: https://gist.github.com/simokitafresh/6b59a57cfd11b77c30fbea8365a23b5f

## 5. 判断済み事項

| 事項 | 状態 |
|---|---|
| プライマリ | **EODHD確定**(殿裁定2026-07-05) |
| EODHDプラン | **EOD+Intraday All World Extended**($29.99/mo)。リバランサーアプリにも活用可能 |
| 予算 | **年$360**(EODHD $29.99/mo + Tiingo無料 + Alpaca IEX無料) |
| Calendar API | **不要**。未確定イベントは調整に使わない |
| Alpaca SIP | **不要**(年$1,000)。IEX無料枠で第三チェック十分 |
| yfinance | adjusted参照値(検算用)に降格 |
| EODHD配当API | 実証済み(LQD 2026H1 5件取得成功)。corporate_eventsテーブル構築に使用 |
| Redis | フォールバックあり(未接続時はロック省略+warning)。デプロイブロッカーではない |
| PREFETCH_SYMBOLS | 過不足なし(DM-Signal全ticker⊆PREFETCH 確認済み) |
| GS選別方式 | **in-sample最適化**(殿裁定2026-07-06)。WFは選別に使わない |
| Render cronジョブ | 各ジョブに個別にADMIN_USER/PASS設定必要(backendと共有されない) |

## 6. 生値+自前調整アーキテクチャ(本番稼働中)

### 6.1 データモデル

```
prices_raw (正本・不変)
├─ PK: (symbol, date, source)
├─ open, high, low, close, volume, fetched_at
└─ consensus_close (EODHD/Tiingo ±0.01一致で採用)

corporate_events (確定後追加のみ)
├─ PK: (symbol, event_date, event_type)
├─ dividend_amount / split_ratio
├─ ex_date, confirmed_at, source_count, sources_json
└─ ex_date通過済みのみconfirmed。未到来は参考記録

prices (互換維持)
└─ prices_raw.consensus_close × corporate_events から導出
```

### 6.2 調整値導出フロー

1. EODHD/Tiingo/Alpacaの生値をprices_rawに保存(JST 08:00/17:00)
2. EODHD/Tiingo close比較→±0.01一致で確定、不一致→ntfy警報
3. EODHD /api/div, /api/splits からイベント取得→corporate_events(ex_date通過済みのみ)
4. consensus_close × 累積調整係数 → 調整値導出
5. EODHDのadjusted_closeと照合(検算)
6. pricesテーブルに書込み(DM-Signal API互換)

### 6.3 DM-Signal側の変更

**変更ゼロ。** Stockdata APIの中身が変わっただけ。返すスキーマは同一。

## 7. エッジケース(実装+テスト済み)

| エッジケース | 対処 | テスト |
|-------------|------|--------|
| 配当落ち日=月末最終営業日 | ex_date ≤ 月末 → 調整に含める | ✅ |
| 月末価格未確定 | 入力確定検証: 全シンボル行存在確認→不在ならpending | ✅ |
| 月初が休日 | 毎日実行+月変わり検知 | ✅ |
| 月末分割 | 生値+自前調整: split ratio適用 | ✅ |
| ソース間最終営業日不一致 | EODHD/Tiingo一致する日を採用 | ✅ |
| UTC/JST日跨ぎ | JST 08:00+17:00の2回cron | ✅ |
| 複合(配当落ち×日跨ぎ) | 入力確定検証+夕方再計算+多数決の三重防御 | ✅ |

## 8. APIキー取得ガイド(Phase 0完了済み・記録)

### 8.1 Alpaca Markets (無料)
Paper Trading → API Keys → `.env` ALPACA_API_KEY_ID / ALPACA_API_SECRET_KEY

### 8.2 EODHD ($29.99/mo)
登録 → EOD+Intraday All World Extended → `.env` EODHD_API_TOKEN

### 8.3 Tiingo (無料)
登録 → https://www.tiingo.com/account/api/token → `.env` TIINGO_API_TOKEN
