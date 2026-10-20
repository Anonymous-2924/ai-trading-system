# student_1 — daily trading log

Appended once per run by the trading pipeline and committed back to the repository by GitHub Actions, so the 15-20 day history survives the runner.

## Summary

| Metric | Value |
| --- | --- |
| Runs recorded | 3 |
| Latest equity | $100,277.99 |
| Total P&L | $277.99 |
| Total P&L % | +0.28% |
| Best day | +0.28% on 2026-10-20 |
| Worst day | +0.00% on 2026-10-17 |
| Peak equity | $100,277.99 on 2026-10-20 |
| Up days | 2 |
| Down days | 0 |
| Flat days | 1 |
| Last data source | ALPACA_LIVE |
| Last engine | deterministic_rule_engine |

## Daily history

**Signals B/S/H** counts the recommendation made for each symbol in the universe, not trades. A SELL signal on a symbol that is not held is no action — this book is long-only and never shorts — so the SELL count is usually larger than the number of sell orders actually sent. **Orders sent** is what reached Alpaca.

| Date | UTC time | Equity | Cash | Buying power | Day P&L | Day % | Total P&L | Total % | Held | Signals B/S/H | Orders sent | Data | Engine | Mode |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 2026-10-17 | 13:58 | $100,000.00 | $100,000.00 | $400,000.00 | $0.00 | +0.00% | $0.00 | +0.00% | 0 | 7/5/2 | 7 | ALPACA_LIVE | crewai_agents | execute |
| 2026-10-19 | 22:58 | $100,226.87 | $24,302.38 | $293,965.25 | $226.87 | +0.23% | $226.87 | +0.23% | 7 | 7/4/3 | 3 | ALPACA_LIVE | crewai_agents | execute |
| 2026-10-20 | 00:31 | $100,277.99 | $24,302.38 | $294,120.57 | $277.99 | +0.28% | $277.99 | +0.28% | 7 | 7/5/2 | 0 | ALPACA_LIVE | deterministic_rule_engine | analyse |

## Notes

- OHLCV for 14/14 symbols in 1 HTTP request(s); 50 news article(s) in the last 48h; JNJ: LLM overrode the rule engine SELL -> BUY (MEDIUM) — Sized BUY candidate with MEDIUM conviction overrides rule engine SELL.; high-beta sleeve is 0% of this run's entries, below the 30% mandate — the signal engine did not produce enough high-beta BUYs today; the mandate is measured on the whole book over the trading period, not on a single run
- OHLCV for 14/14 symbols in 1 HTTP request(s); 50 news article(s) in the last 48h; XOM: LLM overrode the rule engine BUY -> HOLD (VERY_HIGH) — Already held; no additional BUY order generated.; COIN: LLM overrode the rule engine SELL -> BUY (MEDIUM) — Risk‑capped sizing selects COIN as a BUY despite rule engine signal.; exits processed first; $7,828 of freed capital is available to this run's entries; high-beta sleeve is 100% of this run's entries
- OHLCV for 14/14 symbols in 1 HTTP request(s); 50 news article(s) in the last 48h; LLM disabled for this run (provider=none or --no-llm); the deterministic rule engine decides everything.; exits processed first; $7,828 of freed capital is available to this run's entries; high-beta sleeve is 100% of this run's entries; orders NOT submitted: mode=analyse, require_human_approval=True. Submission needs mode=execute AND REQUIRE_HUMAN_APPROVAL=false.
