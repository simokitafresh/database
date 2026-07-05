# Price Source Comparison Summary

- generated_at_utc: 2026-07-05T12:26:16+00:00
- symbols: 12
- month_ends: 2026-04-30, 2026-05-29, 2026-06-30
- source_points_ok: 138/144
- raw_source_rows_with_2plus_sources: 33/36
- eodhd_tiingo_close_within_0.01: 33/33
- alpaca_close_vs_raw_median_within_0.01: 6/33
- max_raw_close_diff_abs: 0.32999999999992724
- max_yfinance_adjusted_vs_eodhd_adjusted_abs: 0.41128974609374325
- max_yfinance_adjusted_vs_tiingo_adjusted_abs: 0.41195444079374965

## Interpretation

- Alpaca rows use `feed=iex` and `adjustment=raw`; this measures the free IEX feed, not paid SIP.
- EODHD and Tiingo raw close agreement is the strongest free-source proxy for exchange EOD close.
- Stockdata/yfinance is recorded as adjusted close because the current service stores adjusted OHLCV.

## Non-OK Points

- VIX 2026-04-30 alpaca: unsupported (VIX index is not a stock bar symbol on Alpaca)
- VIX 2026-05-29 alpaca: unsupported (VIX index is not a stock bar symbol on Alpaca)
- VIX 2026-06-30 alpaca: unsupported (VIX index is not a stock bar symbol on Alpaca)
- VIX 2026-04-30 tiingo: error (HTTPStatusError: Client error '404 Not Found' for url 'https://api.tiingo.com/tiingo/daily/%5EVIX/prices?startDate=2026-04-30&endDate=2026-06-30&token=<redacted>'
For more information check: https://developer.mozilla.org/en-US/docs/Web/HTTP/Status/404)
- VIX 2026-05-29 tiingo: error (HTTPStatusError: Client error '404 Not Found' for url 'https://api.tiingo.com/tiingo/daily/%5EVIX/prices?startDate=2026-04-30&endDate=2026-06-30&token=<redacted>'
For more information check: https://developer.mozilla.org/en-US/docs/Web/HTTP/Status/404)
- VIX 2026-06-30 tiingo: error (HTTPStatusError: Client error '404 Not Found' for url 'https://api.tiingo.com/tiingo/daily/%5EVIX/prices?startDate=2026-04-30&endDate=2026-06-30&token=<redacted>'
For more information check: https://developer.mozilla.org/en-US/docs/Web/HTTP/Status/404)

## Source Recommendation

- Primary candidate: EODHD, with Tiingo as independent verifier. Rationale: EODHD/Tiingo raw closes match within $0.01 on most comparable rows.
- Alpaca IEX: useful as a third check, but IEX-only coverage should not be treated as full-market SIP unless paid SIP access is confirmed.
- yfinance/Stockdata: keep as reference only; adjusted values can agree numerically while still being unsuitable as the immutable raw source.
