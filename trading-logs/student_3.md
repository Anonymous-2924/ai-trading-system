# student_3 — daily trading log

Appended once per run by the trading pipeline and committed back to the repository by GitHub Actions, so the 15-20 day history survives the runner.

## Summary

| Metric | Value |
| --- | --- |
| Runs recorded | 26 |
| Latest equity | $102,745.93 |
| Total P&L | $2,745.93 |
| Total P&L % | +2.75% |
| Best day | +3.20% on 2026-11-05 |
| Worst day | -3.53% on 2026-11-06 |
| Peak equity | $106,451.69 on 2026-11-05 |
| Up days | 16 |
| Down days | 9 |
| Flat days | 1 |
| Last data source | ALPACA_LIVE |
| Last engine | deterministic_rule_engine |

## Daily history

**Signals B/S/H** counts the recommendation made for each symbol in the universe, not trades. A SELL signal on a symbol that is not held is no action — this book is long-only and never shorts — so the SELL count is usually larger than the number of sell orders actually sent. **Orders sent** is what reached Alpaca.

| Date | UTC time | Equity | Cash | Buying power | Day P&L | Day % | Total P&L | Total % | Held | Signals B/S/H | Orders sent | Data | Engine | Mode |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 2026-10-17 | 14:03 | $100,000.00 | $100,000.00 | $400,000.00 | $0.00 | +0.00% | $0.00 | +0.00% | 0 | 8/3/3 | 5 | ALPACA_LIVE | deterministic_rule_engine | execute |
| 2026-10-19 | 23:02 | $100,079.47 | $42,855.91 | $323,772.86 | $79.47 | +0.08% | $79.47 | +0.08% | 5 | 7/4/3 | 1 | ALPACA_LIVE | crewai_agents | execute |
| 2026-10-20 | 00:33 | $100,135.28 | $42,855.91 | $323,917.31 | $135.28 | +0.14% | $135.28 | +0.14% | 5 | 7/4/3 | 0 | ALPACA_LIVE | deterministic_rule_engine | analyse |
| 2026-10-20 | 22:35 | $100,573.68 | $34,923.39 | $315,628.71 | $495.50 | +0.50% | $573.68 | +0.57% | 6 | 1/3/10 | 1 | ALPACA_LIVE | crewai_agents | execute |
| 2026-10-21 | 00:04 | $100,510.68 | $34,923.39 | $315,464.85 | $432.50 | +0.43% | $510.68 | +0.51% | 6 | 7/3/4 | 0 | ALPACA_LIVE | deterministic_rule_engine | analyse |
| 2026-10-21 | 22:39 | $100,504.73 | $27,061.76 | $288,932.57 | $-184.39 | -0.18% | $504.73 | +0.50% | 7 | 3/0/11 | 3 | ALPACA_LIVE | crewai_agents | execute |
| 2026-10-22 | 00:09 | $100,521.83 | $27,061.76 | $289,135.83 | $-167.29 | -0.17% | $521.83 | +0.52% | 7 | 8/2/4 | 0 | ALPACA_LIVE | deterministic_rule_engine | analyse |
| 2026-10-22 | 22:37 | $101,608.25 | $2,619.84 | $287,646.92 | $1,000.66 | +0.99% | $1,608.25 | +1.61% | 10 | 7/2/5 | 2 | ALPACA_LIVE | crewai_agents | execute |
| 2026-10-23 | 00:07 | $101,554.85 | $2,619.84 | $287,497.39 | $947.26 | +0.94% | $1,554.85 | +1.55% | 10 | 7/4/3 | 0 | ALPACA_LIVE | deterministic_rule_engine | analyse |
| 2026-10-23 | 22:31 | $100,939.92 | $20,735.06 | $299,538.78 | $-802.01 | -0.79% | $939.92 | +0.94% | 8 | 1/0/13 | 1 | ALPACA_LIVE | crewai_agents | execute |
| 2026-10-23 | 23:58 | $100,963.10 | $20,735.06 | $299,541.30 | $-778.84 | -0.77% | $963.10 | +0.96% | 8 | 7/4/3 | 0 | ALPACA_LIVE | deterministic_rule_engine | analyse |
| 2026-10-27 | 00:43 | $101,311.61 | $12,798.18 | $299,030.31 | $386.14 | +0.38% | $1,311.61 | +1.31% | 9 | 7/5/2 | 0 | ALPACA_LIVE | deterministic_rule_engine | analyse |
| 2026-10-28 | 00:42 | $101,577.18 | $12,798.17 | $299,773.92 | $224.74 | +0.22% | $1,577.18 | +1.58% | 9 | 7/3/4 | 0 | ALPACA_LIVE | deterministic_rule_engine | analyse |
| 2026-10-29 | 01:11 | $101,972.18 | $12,798.17 | $300,879.91 | $338.26 | +0.33% | $1,972.18 | +1.97% | 9 | 7/2/5 | 0 | ALPACA_LIVE | deterministic_rule_engine | analyse |
| 2026-10-30 | 01:17 | $103,894.46 | $12,798.17 | $306,262.30 | $2,238.00 | +2.20% | $3,894.46 | +3.89% | 9 | 9/2/3 | 0 | ALPACA_LIVE | deterministic_rule_engine | analyse |
| 2026-10-31 | 00:59 | $103,547.59 | $12,798.17 | $305,291.04 | $15.18 | +0.01% | $3,547.59 | +3.55% | 9 | 9/4/1 | 0 | ALPACA_LIVE | deterministic_rule_engine | analyse |
| 2026-11-03 | 03:03 | $104,464.33 | $12,798.17 | $307,857.92 | $861.61 | +0.83% | $4,464.33 | +4.46% | 9 | 8/5/1 | 0 | ALPACA_LIVE | deterministic_rule_engine | analyse |
| 2026-11-04 | 01:37 | $102,921.83 | $12,798.17 | $303,538.92 | $-1,440.48 | -1.38% | $2,921.83 | +2.92% | 9 | 8/5/1 | 0 | ALPACA_LIVE | deterministic_rule_engine | analyse |
| 2026-11-05 | 01:41 | $106,451.69 | $12,798.17 | $313,422.54 | $3,298.52 | +3.20% | $6,451.69 | +6.45% | 9 | 9/5/0 | 0 | ALPACA_LIVE | deterministic_rule_engine | analyse |
| 2026-11-06 | 01:45 | $102,552.53 | $12,798.17 | $302,504.89 | $-3,754.20 | -3.53% | $2,552.53 | +2.55% | 9 | 8/6/0 | 0 | ALPACA_LIVE | deterministic_rule_engine | analyse |
| 2026-11-07 | 01:05 | $102,839.33 | $12,798.17 | $303,307.93 | $-804.79 | -0.78% | $2,839.33 | +2.84% | 9 | 7/6/1 | 0 | ALPACA_LIVE | deterministic_rule_engine | analyse |
| 2026-11-10 | 03:45 | $104,209.07 | $12,798.17 | $307,143.19 | $1,384.19 | +1.35% | $4,209.07 | +4.21% | 9 | 8/6/0 | 0 | ALPACA_LIVE | deterministic_rule_engine | analyse |
| 2026-11-11 | 01:25 | $103,521.79 | $12,798.17 | $305,218.82 | $-724.09 | -0.69% | $3,521.79 | +3.52% | 9 | 8/6/0 | 0 | ALPACA_LIVE | deterministic_rule_engine | analyse |
| 2026-11-12 | 02:26 | $103,995.18 | $12,798.17 | $306,544.32 | $371.29 | +0.36% | $3,995.18 | +4.00% | 9 | 7/3/4 | 0 | ALPACA_LIVE | deterministic_rule_engine | analyse |
| 2026-11-13 | 02:04 | $102,762.02 | $12,798.17 | $303,091.45 | $-1,258.19 | -1.21% | $2,762.02 | +2.76% | 9 | 7/5/2 | 0 | ALPACA_LIVE | deterministic_rule_engine | analyse |
| 2026-11-14 | 01:37 | $102,745.93 | $12,798.17 | $303,046.42 | $114.73 | +0.11% | $2,745.93 | +2.75% | 9 | 7/5/2 | 0 | ALPACA_LIVE | deterministic_rule_engine | analyse |

## Notes

- OHLCV for 14/14 symbols (plus 2 benchmark(s)) in 1 HTTP request(s); intraday bars for 14 symbol(s); 50 news article(s) in the last 48h; LLM disabled for this run (provider=none or --no-llm); the deterministic rule engine decides everything.; exits processed first; $5,665 of freed capital is available to this run's entries; orders NOT submitted: mode=analyse, require_human_approval=True. Submission needs mode=execute AND REQUIRE_HUMAN_APPROVAL=false.; alpha logged: 10 trade(s), mean excess +1.96%
- OHLCV for 14/14 symbols (plus 2 benchmark(s)) in 1 HTTP request(s); intraday bars for 14 symbol(s); 50 news article(s) in the last 48h; LLM disabled for this run (provider=none or --no-llm); the deterministic rule engine decides everything.; orders NOT submitted: mode=analyse, require_human_approval=True. Submission needs mode=execute AND REQUIRE_HUMAN_APPROVAL=false.; alpha logged: 10 trade(s), mean excess +1.55%
- OHLCV for 14/14 symbols (plus 2 benchmark(s)) in 1 HTTP request(s); intraday bars for 14 symbol(s); 50 news article(s) in the last 48h; LLM disabled for this run (provider=none or --no-llm); the deterministic rule engine decides everything.; orders NOT submitted: mode=analyse, require_human_approval=True. Submission needs mode=execute AND REQUIRE_HUMAN_APPROVAL=false.; alpha logged: 10 trade(s), mean excess +1.41%
- OHLCV for 14/14 symbols (plus 2 benchmark(s)) in 1 HTTP request(s); intraday bars for 14 symbol(s); 50 news article(s) in the last 48h; LLM disabled for this run (provider=none or --no-llm); the deterministic rule engine decides everything.; high-beta sleeve is 0% of this run's entries, below the 30% mandate — the signal engine did not produce enough high-beta BUYs today; the mandate is measured on the whole book over the trading period, not on a single run; orders NOT submitted: mode=analyse, r
- OHLCV for 14/14 symbols (plus 2 benchmark(s)) in 1 HTTP request(s); intraday bars for 14 symbol(s); 50 news article(s) in the last 48h; LLM disabled for this run (provider=none or --no-llm); the deterministic rule engine decides everything.; high-beta sleeve is 0% of this run's entries, below the 30% mandate — the signal engine did not produce enough high-beta BUYs today; the mandate is measured on the whole book over the trading period, not on a single run; orders NOT submitted: mode=analyse, r
- OHLCV for 14/14 symbols (plus 2 benchmark(s)) in 1 HTTP request(s); intraday bars for 14 symbol(s); 50 news article(s) in the last 48h; LLM disabled for this run (provider=none or --no-llm); the deterministic rule engine decides everything.; exits processed first; $5,255 of freed capital is available to this run's entries; high-beta sleeve is 0% of this run's entries, below the 30% mandate — the signal engine did not produce enough high-beta BUYs today; the mandate is measured on the whole book 
- OHLCV for 14/14 symbols (plus 2 benchmark(s)) in 1 HTTP request(s); intraday bars for 14 symbol(s); 50 news article(s) in the last 48h; LLM disabled for this run (provider=none or --no-llm); the deterministic rule engine decides everything.; exits processed first; $5,267 of freed capital is available to this run's entries; high-beta sleeve is 0% of this run's entries, below the 30% mandate — the signal engine did not produce enough high-beta BUYs today; the mandate is measured on the whole book 
- OHLCV for 14/14 symbols (plus 2 benchmark(s)) in 1 HTTP request(s); intraday bars for 14 symbol(s); 50 news article(s) in the last 48h; LLM disabled for this run (provider=none or --no-llm); the deterministic rule engine decides everything.; exits processed first; $5,760 of freed capital is available to this run's entries; high-beta sleeve is 0% of this run's entries, below the 30% mandate — the signal engine did not produce enough high-beta BUYs today; the mandate is measured on the whole book 
- OHLCV for 14/14 symbols (plus 2 benchmark(s)) in 1 HTTP request(s); intraday bars for 14 symbol(s); 50 news article(s) in the last 48h; LLM disabled for this run (provider=none or --no-llm); the deterministic rule engine decides everything.; exits processed first; $13,343 of freed capital is available to this run's entries; high-beta sleeve is 0% of this run's entries, below the 30% mandate — the signal engine did not produce enough high-beta BUYs today; the mandate is measured on the whole book
- OHLCV for 14/14 symbols (plus 2 benchmark(s)) in 1 HTTP request(s); intraday bars for 14 symbol(s); 50 news article(s) in the last 48h; LLM disabled for this run (provider=none or --no-llm); the deterministic rule engine decides everything.; exits processed first; $13,110 of freed capital is available to this run's entries; high-beta sleeve is 0% of this run's entries, below the 30% mandate — the signal engine did not produce enough high-beta BUYs today; the mandate is measured on the whole book
- OHLCV for 14/14 symbols (plus 2 benchmark(s)) in 1 HTTP request(s); intraday bars for 14 symbol(s); 50 news article(s) in the last 48h; LLM disabled for this run (provider=none or --no-llm); the deterministic rule engine decides everything.; exits processed first; $13,197 of freed capital is available to this run's entries; high-beta sleeve is 0% of this run's entries, below the 30% mandate — the signal engine did not produce enough high-beta BUYs today; the mandate is measured on the whole book
- OHLCV for 14/14 symbols (plus 2 benchmark(s)) in 1 HTTP request(s); intraday bars for 14 symbol(s); 50 news article(s) in the last 48h; LLM disabled for this run (provider=none or --no-llm); the deterministic rule engine decides everything.; exits processed first; $12,505 of freed capital is available to this run's entries; high-beta sleeve is 0% of this run's entries, below the 30% mandate — the signal engine did not produce enough high-beta BUYs today; the mandate is measured on the whole book
- OHLCV for 14/14 symbols (plus 2 benchmark(s)) in 1 HTTP request(s); intraday bars for 14 symbol(s); 50 news article(s) in the last 48h; LLM disabled for this run (provider=none or --no-llm); the deterministic rule engine decides everything.; exits processed first; $12,758 of freed capital is available to this run's entries; high-beta sleeve is 0% of this run's entries, below the 30% mandate — the signal engine did not produce enough high-beta BUYs today; the mandate is measured on the whole book
- OHLCV for 14/14 symbols (plus 2 benchmark(s)) in 1 HTTP request(s); intraday bars for 14 symbol(s); 50 news article(s) in the last 48h; LLM disabled for this run (provider=none or --no-llm); the deterministic rule engine decides everything.; exits processed first; $12,187 of freed capital is available to this run's entries; high-beta sleeve is 0% of this run's entries, below the 30% mandate — the signal engine did not produce enough high-beta BUYs today; the mandate is measured on the whole book
- OHLCV for 14/14 symbols (plus 2 benchmark(s)) in 1 HTTP request(s); intraday bars for 14 symbol(s); 50 news article(s) in the last 48h; LLM disabled for this run (provider=none or --no-llm); the deterministic rule engine decides everything.; exits processed first; $12,202 of freed capital is available to this run's entries; high-beta sleeve is 0% of this run's entries, below the 30% mandate — the signal engine did not produce enough high-beta BUYs today; the mandate is measured on the whole book
