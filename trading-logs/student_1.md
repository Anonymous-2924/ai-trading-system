# student_1 — daily trading log

Appended once per run by the trading pipeline and committed back to the repository by GitHub Actions, so the 15-20 day history survives the runner.

## Summary

| Metric | Value |
| --- | --- |
| Runs recorded | 26 |
| Latest equity | $101,253.89 |
| Total P&L | $1,253.89 |
| Total P&L % | +1.25% |
| Best day | +2.05% on 2026-11-10 |
| Worst day | -3.80% on 2026-11-06 |
| Peak equity | $102,097.71 on 2026-10-30 |
| Up days | 15 |
| Down days | 10 |
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
| 2026-10-20 | 22:29 | $100,882.59 | $16,528.06 | $282,754.13 | $646.16 | +0.64% | $882.59 | +0.88% | 8 | 3/2/9 | 3 | ALPACA_LIVE | crewai_agents | execute |
| 2026-10-21 | 00:02 | $100,740.31 | $16,528.06 | $282,252.72 | $503.88 | +0.50% | $740.31 | +0.74% | 8 | 5/4/5 | 0 | ALPACA_LIVE | deterministic_rule_engine | analyse |
| 2026-10-21 | 22:34 | $100,699.14 | $5,127.78 | $277,034.26 | $-225.27 | -0.22% | $699.14 | +0.70% | 9 | 1/3/10 | 3 | ALPACA_LIVE | crewai_agents | execute |
| 2026-10-22 | 00:06 | $100,833.15 | $5,127.78 | $277,538.26 | $-91.26 | -0.09% | $833.15 | +0.83% | 9 | 8/3/3 | 0 | ALPACA_LIVE | deterministic_rule_engine | analyse |
| 2026-10-22 | 22:32 | $101,129.41 | $12,607.02 | $289,545.00 | $208.87 | +0.21% | $1,129.41 | +1.13% | 8 | 6/4/4 | 0 | ALPACA_LIVE | crewai_agents | execute |
| 2026-10-23 | 00:04 | $101,197.31 | $12,607.02 | $289,719.90 | $276.77 | +0.27% | $1,197.31 | +1.20% | 8 | 8/4/2 | 0 | ALPACA_LIVE | deterministic_rule_engine | analyse |
| 2026-10-23 | 22:26 | $100,571.87 | $12,606.62 | $277,422.48 | $-584.34 | -0.58% | $571.87 | +0.57% | 8 | 1/4/9 | 1 | ALPACA_LIVE | crewai_agents | execute |
| 2026-10-23 | 23:55 | $100,597.60 | $12,606.62 | $277,498.17 | $-558.61 | -0.55% | $597.60 | +0.60% | 8 | 6/4/4 | 0 | ALPACA_LIVE | deterministic_rule_engine | analyse |
| 2026-10-27 | 00:41 | $100,938.83 | $1,922.05 | $275,695.52 | $361.24 | +0.36% | $938.83 | +0.94% | 9 | 8/4/2 | 0 | ALPACA_LIVE | deterministic_rule_engine | analyse |
| 2026-10-28 | 00:39 | $101,057.33 | $1,922.04 | $275,726.33 | $128.53 | +0.13% | $1,057.33 | +1.06% | 9 | 9/4/1 | 0 | ALPACA_LIVE | deterministic_rule_engine | analyse |
| 2026-10-29 | 01:09 | $101,712.77 | $1,922.04 | $277,695.40 | $491.62 | +0.49% | $1,712.77 | +1.71% | 9 | 10/4/0 | 0 | ALPACA_LIVE | deterministic_rule_engine | analyse |
| 2026-10-30 | 01:15 | $102,097.71 | $1,922.04 | $278,940.60 | $1,197.75 | +1.19% | $2,097.71 | +2.10% | 9 | 10/4/0 | 0 | ALPACA_LIVE | deterministic_rule_engine | analyse |
| 2026-10-31 | 00:57 | $101,115.87 | $1,922.04 | $276,049.41 | $-718.69 | -0.71% | $1,115.87 | +1.12% | 9 | 7/4/3 | 0 | ALPACA_LIVE | deterministic_rule_engine | analyse |
| 2026-11-03 | 03:00 | $99,686.24 | $1,922.04 | $271,945.89 | $-1,392.50 | -1.38% | $-313.76 | -0.31% | 9 | 7/5/2 | 0 | ALPACA_LIVE | deterministic_rule_engine | analyse |
| 2026-11-04 | 01:34 | $98,693.19 | $1,922.04 | $269,606.49 | $-1,647.49 | -1.64% | $-1,306.81 | -1.31% | 9 | 6/5/3 | 0 | ALPACA_LIVE | deterministic_rule_engine | analyse |
| 2026-11-05 | 01:39 | $101,541.25 | $1,922.04 | $277,709.99 | $1,837.93 | +1.84% | $1,541.25 | +1.54% | 9 | 8/5/1 | 0 | ALPACA_LIVE | deterministic_rule_engine | analyse |
| 2026-11-06 | 01:42 | $97,756.00 | $1,922.04 | $267,889.28 | $-3,862.41 | -3.80% | $-2,244.00 | -2.24% | 9 | 5/6/3 | 0 | ALPACA_LIVE | deterministic_rule_engine | analyse |
| 2026-11-07 | 01:02 | $98,520.82 | $1,922.04 | $269,740.12 | $524.82 | +0.54% | $-1,479.18 | -1.48% | 9 | 3/6/5 | 0 | ALPACA_LIVE | deterministic_rule_engine | analyse |
| 2026-11-10 | 03:43 | $100,459.98 | $1,922.04 | $274,774.56 | $2,013.89 | +2.05% | $459.98 | +0.46% | 9 | 5/6/3 | 0 | ALPACA_LIVE | deterministic_rule_engine | analyse |
| 2026-11-11 | 01:23 | $100,498.07 | $1,922.04 | $274,743.38 | $-18.27 | -0.02% | $498.07 | +0.50% | 9 | 7/6/1 | 0 | ALPACA_LIVE | deterministic_rule_engine | analyse |
| 2026-11-12 | 02:24 | $100,920.47 | $1,922.04 | $275,777.02 | $494.72 | +0.49% | $920.47 | +0.92% | 9 | 6/6/2 | 0 | ALPACA_LIVE | deterministic_rule_engine | analyse |
| 2026-11-13 | 02:02 | $101,405.31 | $1,922.04 | $276,829.61 | $533.16 | +0.53% | $1,405.31 | +1.41% | 9 | 7/5/2 | 0 | ALPACA_LIVE | deterministic_rule_engine | analyse |
| 2026-11-14 | 01:35 | $101,253.89 | $1,922.04 | $276,743.18 | $-3.13 | -0.00% | $1,253.89 | +1.25% | 9 | 7/5/2 | 0 | ALPACA_LIVE | deterministic_rule_engine | analyse |

## Notes

- OHLCV for 14/14 symbols (plus 2 benchmark(s)) in 1 HTTP request(s); intraday bars for 14 symbol(s); 50 news article(s) in the last 48h; LLM disabled for this run (provider=none or --no-llm); the deterministic rule engine decides everything.; orders NOT submitted: mode=analyse, require_human_approval=True. Submission needs mode=execute AND REQUIRE_HUMAN_APPROVAL=false.; alpha logged: 12 trade(s), mean excess +1.11%
- OHLCV for 14/14 symbols (plus 2 benchmark(s)) in 1 HTTP request(s); intraday bars for 14 symbol(s); 50 news article(s) in the last 48h; LLM disabled for this run (provider=none or --no-llm); the deterministic rule engine decides everything.; orders NOT submitted: mode=analyse, require_human_approval=True. Submission needs mode=execute AND REQUIRE_HUMAN_APPROVAL=false.; alpha logged: 12 trade(s), mean excess +0.83%
- OHLCV for 14/14 symbols (plus 2 benchmark(s)) in 1 HTTP request(s); intraday bars for 14 symbol(s); 50 news article(s) in the last 48h; LLM disabled for this run (provider=none or --no-llm); the deterministic rule engine decides everything.; orders NOT submitted: mode=analyse, require_human_approval=True. Submission needs mode=execute AND REQUIRE_HUMAN_APPROVAL=false.; alpha logged: 12 trade(s), mean excess +0.35%
- OHLCV for 14/14 symbols (plus 2 benchmark(s)) in 1 HTTP request(s); intraday bars for 14 symbol(s); 50 news article(s) in the last 48h; LLM disabled for this run (provider=none or --no-llm); the deterministic rule engine decides everything.; orders NOT submitted: mode=analyse, require_human_approval=True. Submission needs mode=execute AND REQUIRE_HUMAN_APPROVAL=false.; alpha logged: 12 trade(s), mean excess +1.09%
- OHLCV for 14/14 symbols (plus 2 benchmark(s)) in 1 HTTP request(s); intraday bars for 14 symbol(s); 50 news article(s) in the last 48h; LLM disabled for this run (provider=none or --no-llm); the deterministic rule engine decides everything.; orders NOT submitted: mode=analyse, require_human_approval=True. Submission needs mode=execute AND REQUIRE_HUMAN_APPROVAL=false.; alpha logged: 12 trade(s), mean excess +1.67%
- OHLCV for 14/14 symbols (plus 2 benchmark(s)) in 1 HTTP request(s); intraday bars for 14 symbol(s); 50 news article(s) in the last 48h; LLM disabled for this run (provider=none or --no-llm); the deterministic rule engine decides everything.; exits processed first; $7,254 of freed capital is available to this run's entries; orders NOT submitted: mode=analyse, require_human_approval=True. Submission needs mode=execute AND REQUIRE_HUMAN_APPROVAL=false.; alpha logged: 12 trade(s), mean excess +1.32%
- OHLCV for 14/14 symbols (plus 2 benchmark(s)) in 1 HTTP request(s); intraday bars for 14 symbol(s); 50 news article(s) in the last 48h; LLM disabled for this run (provider=none or --no-llm); the deterministic rule engine decides everything.; exits processed first; $7,128 of freed capital is available to this run's entries; orders NOT submitted: mode=analyse, require_human_approval=True. Submission needs mode=execute AND REQUIRE_HUMAN_APPROVAL=false.; alpha logged: 12 trade(s), mean excess +0.68%
- OHLCV for 14/14 symbols (plus 2 benchmark(s)) in 1 HTTP request(s); intraday bars for 14 symbol(s); 50 news article(s) in the last 48h; LLM disabled for this run (provider=none or --no-llm); the deterministic rule engine decides everything.; exits processed first; $6,979 of freed capital is available to this run's entries; high-beta sleeve is 0% of this run's entries, below the 30% mandate — the signal engine did not produce enough high-beta BUYs today; the mandate is measured on the whole book 
- OHLCV for 14/14 symbols (plus 2 benchmark(s)) in 1 HTTP request(s); intraday bars for 14 symbol(s); 50 news article(s) in the last 48h; LLM disabled for this run (provider=none or --no-llm); the deterministic rule engine decides everything.; exits processed first; $16,364 of freed capital is available to this run's entries; orders NOT submitted: mode=analyse, require_human_approval=True. Submission needs mode=execute AND REQUIRE_HUMAN_APPROVAL=false.; alpha logged: 12 trade(s), mean excess +0.53
- OHLCV for 14/14 symbols (plus 2 benchmark(s)) in 1 HTTP request(s); intraday bars for 14 symbol(s); 50 news article(s) in the last 48h; LLM disabled for this run (provider=none or --no-llm); the deterministic rule engine decides everything.; exits processed first; $17,015 of freed capital is available to this run's entries; orders NOT submitted: mode=analyse, require_human_approval=True. Submission needs mode=execute AND REQUIRE_HUMAN_APPROVAL=false.; alpha logged: 12 trade(s), mean excess +0.69
- OHLCV for 14/14 symbols (plus 2 benchmark(s)) in 1 HTTP request(s); intraday bars for 14 symbol(s); 50 news article(s) in the last 48h; LLM disabled for this run (provider=none or --no-llm); the deterministic rule engine decides everything.; exits processed first; $14,127 of freed capital is available to this run's entries; orders NOT submitted: mode=analyse, require_human_approval=True. Submission needs mode=execute AND REQUIRE_HUMAN_APPROVAL=false.; alpha logged: 12 trade(s), mean excess +0.60
- OHLCV for 14/14 symbols (plus 2 benchmark(s)) in 1 HTTP request(s); intraday bars for 14 symbol(s); 50 news article(s) in the last 48h; LLM disabled for this run (provider=none or --no-llm); the deterministic rule engine decides everything.; exits processed first; $14,100 of freed capital is available to this run's entries; high-beta sleeve is 0% of this run's entries, below the 30% mandate — the signal engine did not produce enough high-beta BUYs today; the mandate is measured on the whole book
- OHLCV for 14/14 symbols (plus 2 benchmark(s)) in 1 HTTP request(s); intraday bars for 14 symbol(s); 50 news article(s) in the last 48h; LLM disabled for this run (provider=none or --no-llm); the deterministic rule engine decides everything.; exits processed first; $14,343 of freed capital is available to this run's entries; orders NOT submitted: mode=analyse, require_human_approval=True. Submission needs mode=execute AND REQUIRE_HUMAN_APPROVAL=false.; alpha logged: 12 trade(s), mean excess +0.38
- OHLCV for 14/14 symbols (plus 2 benchmark(s)) in 1 HTTP request(s); intraday bars for 14 symbol(s); 50 news article(s) in the last 48h; LLM disabled for this run (provider=none or --no-llm); the deterministic rule engine decides everything.; exits processed first; $6,972 of freed capital is available to this run's entries; orders NOT submitted: mode=analyse, require_human_approval=True. Submission needs mode=execute AND REQUIRE_HUMAN_APPROVAL=false.; alpha logged: 12 trade(s), mean excess +0.83%
- OHLCV for 14/14 symbols (plus 2 benchmark(s)) in 1 HTTP request(s); intraday bars for 14 symbol(s); 50 news article(s) in the last 48h; LLM disabled for this run (provider=none or --no-llm); the deterministic rule engine decides everything.; exits processed first; $6,832 of freed capital is available to this run's entries; orders NOT submitted: mode=analyse, require_human_approval=True. Submission needs mode=execute AND REQUIRE_HUMAN_APPROVAL=false.; alpha logged: 12 trade(s), mean excess +1.13%
