# student_2 — daily trading log

Appended once per run by the trading pipeline and committed back to the repository by GitHub Actions, so the 15-20 day history survives the runner.

## Summary

| Metric | Value |
| --- | --- |
| Runs recorded | 4 |
| Latest equity | $101,720.09 |
| Total P&L | $1,720.09 |
| Total P&L % | +1.72% |
| Best day | +1.11% on 2026-10-20 |
| Worst day | +0.00% on 2026-10-17 |
| Peak equity | $101,720.09 on 2026-10-22 |
| Up days | 3 |
| Down days | 0 |
| Flat days | 1 |
| Last data source | ALPACA_LIVE |
| Last engine | deterministic_rule_engine |

## Daily history

**Signals B/S/H** counts the recommendation made for each symbol in the universe, not trades. A SELL signal on a symbol that is not held is no action — this book is long-only and never shorts — so the SELL count is usually larger than the number of sell orders actually sent. **Orders sent** is what reached Alpaca.

| Date | UTC time | Equity | Cash | Buying power | Day P&L | Day % | Total P&L | Total % | Held | Signals B/S/H | Orders sent | Data | Engine | Mode |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 2026-10-17 | 14:01 | $100,000.00 | $100,000.00 | $400,000.00 | $0.00 | +0.00% | $0.00 | +0.00% | 0 | 4/4/6 | 4 | ALPACA_LIVE | crewai_agents | execute |
| 2026-10-20 | 00:32 | $100,163.63 | $38,760.01 | $292,129.24 | $163.63 | +0.16% | $163.63 | +0.16% | 4 | 6/5/3 | 0 | ALPACA_LIVE | deterministic_rule_engine | analyse |
| 2026-10-20 | 22:33 | $101,253.87 | $22,877.11 | $282,751.91 | $1,110.13 | +1.11% | $1,253.87 | +1.25% | 6 | 1/0/13 | 1 | ALPACA_LIVE | crewai_agents | execute |
| 2026-10-22 | 00:08 | $101,720.09 | $14,939.87 | $269,199.00 | $393.97 | +0.39% | $1,720.09 | +1.72% | 7 | 8/4/2 | 0 | ALPACA_LIVE | deterministic_rule_engine | analyse |

## Notes

- OHLCV for 14/14 symbols in 1 HTTP request(s); 50 news article(s) in the last 48h; HD: LLM overrode the rule engine BUY -> HOLD (LOW) — Low conviction prevents opening a position, so the recommendation is to hold.; 9 symbol(s) not covered by the crew kept their rule-engine decision: AMD, AMZN, BAC, DKNG, ENPH, GOOGL, HON, MRK, RIVN; high-beta sleeve is 25% of this run's entries, below the 30% mandate — the signal engine did not produce enough high-beta BUYs today; the mandate is measured on the w
- OHLCV for 14/14 symbols in 1 HTTP request(s); 37 news article(s) in the last 48h; LLM disabled for this run (provider=none or --no-llm); the deterministic rule engine decides everything.; high-beta sleeve is 0% of this run's entries, below the 30% mandate — the signal engine did not produce enough high-beta BUYs today; the mandate is measured on the whole book over the trading period, not on a single run; orders NOT submitted: mode=analyse, require_human_approval=True. Submission needs mode=exec
- OHLCV for 14/14 symbols in 1 HTTP request(s); 50 news article(s) in the last 48h; MRNA: LLM overrode the rule engine BUY -> HOLD (VERY_HIGH) — already held; no new position; RIVN: LLM overrode the rule engine SELL -> HOLD (VERY_HIGH) — sell signal but not held, no action; CVX: LLM overrode the rule engine BUY -> HOLD (VERY_HIGH) — already held; no new position; BAC: LLM overrode the rule engine SELL -> HOLD (VERY_HIGH) — sell signal but not held, no action; KO: LLM overrode the rule engine BUY -
- OHLCV for 14/14 symbols in 1 HTTP request(s); 50 news article(s) in the last 48h; LLM disabled for this run (provider=none or --no-llm); the deterministic rule engine decides everything.; high-beta sleeve is 0% of this run's entries, below the 30% mandate — the signal engine did not produce enough high-beta BUYs today; the mandate is measured on the whole book over the trading period, not on a single run; orders NOT submitted: mode=analyse, require_human_approval=True. Submission needs mode=exec
