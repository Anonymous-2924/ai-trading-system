# student_3 — daily trading log

Appended once per run by the trading pipeline and committed back to the repository by GitHub Actions, so the 15-20 day history survives the runner.

## Summary

| Metric | Value |
| --- | --- |
| Runs recorded | 2 |
| Latest equity | $100,135.28 |
| Total P&L | $135.28 |
| Total P&L % | +0.14% |
| Best day | +0.14% on 2026-10-20 |
| Worst day | +0.00% on 2026-10-17 |
| Peak equity | $100,135.28 on 2026-10-20 |
| Up days | 1 |
| Down days | 0 |
| Flat days | 1 |
| Last data source | ALPACA_LIVE |
| Last engine | deterministic_rule_engine |

## Daily history

**Signals B/S/H** counts the recommendation made for each symbol in the universe, not trades. A SELL signal on a symbol that is not held is no action — this book is long-only and never shorts — so the SELL count is usually larger than the number of sell orders actually sent. **Orders sent** is what reached Alpaca.

| Date | UTC time | Equity | Cash | Buying power | Day P&L | Day % | Total P&L | Total % | Held | Signals B/S/H | Orders sent | Data | Engine | Mode |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 2026-10-17 | 14:03 | $100,000.00 | $100,000.00 | $400,000.00 | $0.00 | +0.00% | $0.00 | +0.00% | 0 | 8/3/3 | 5 | ALPACA_LIVE | deterministic_rule_engine | execute |
| 2026-10-20 | 00:33 | $100,135.28 | $42,855.91 | $323,917.31 | $135.28 | +0.14% | $135.28 | +0.14% | 5 | 7/4/3 | 0 | ALPACA_LIVE | deterministic_rule_engine | analyse |

## Notes

- LLM path unavailable, using the deterministic rule engine: the model returned empty content (CrewAI: 'Invalid response from LLM call - None or empty'). Small models loop over a tool and then return nothing. Falling back to the deterministic rule engine.; TRUE: order failed POST https://paper-api.alpaca.markets/v2/orders -> HTTP 422: {"code":40010001,"message":"asset TRUE is not active"}; OHLCV for 14/14 symbols in 1 HTTP request(s); 48 news article(s) in the last 48h; high-beta sleeve is 28% of 
- OHLCV for 14/14 symbols in 1 HTTP request(s); 34 news article(s) in the last 48h; LLM disabled for this run (provider=none or --no-llm); the deterministic rule engine decides everything.; high-beta sleeve is 0% of this run's entries, below the 30% mandate — the signal engine did not produce enough high-beta BUYs today; the mandate is measured on the whole book over the trading period, not on a single run; orders NOT submitted: mode=analyse, require_human_approval=True. Submission needs mode=exec
