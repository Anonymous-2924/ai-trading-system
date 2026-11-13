# student_2 — daily trading log

Appended once per run by the trading pipeline and committed back to the repository by GitHub Actions, so the 15-20 day history survives the runner.

## Summary

| Metric | Value |
| --- | --- |
| Runs recorded | 25 |
| Latest equity | $102,834.91 |
| Total P&L | $2,834.91 |
| Total P&L % | +2.83% |
| Best day | +3.47% on 2026-11-05 |
| Worst day | -2.77% on 2026-10-23 |
| Peak equity | $104,698.47 on 2026-11-10 |
| Up days | 14 |
| Down days | 10 |
| Flat days | 1 |
| Last data source | ALPACA_LIVE |
| Last engine | deterministic_rule_engine |

## Daily history

**Signals B/S/H** counts the recommendation made for each symbol in the universe, not trades. A SELL signal on a symbol that is not held is no action — this book is long-only and never shorts — so the SELL count is usually larger than the number of sell orders actually sent. **Orders sent** is what reached Alpaca.

| Date | UTC time | Equity | Cash | Buying power | Day P&L | Day % | Total P&L | Total % | Held | Signals B/S/H | Orders sent | Data | Engine | Mode |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 2026-10-17 | 14:01 | $100,000.00 | $100,000.00 | $400,000.00 | $0.00 | +0.00% | $0.00 | +0.00% | 0 | 4/4/6 | 4 | ALPACA_LIVE | crewai_agents | execute |
| 2026-10-19 | 23:00 | $100,193.31 | $38,760.01 | $292,172.14 | $193.31 | +0.19% | $193.31 | +0.19% | 4 | 6/5/3 | 2 | ALPACA_LIVE | crewai_agents | execute |
| 2026-10-20 | 00:32 | $100,163.63 | $38,760.01 | $292,129.24 | $163.63 | +0.16% | $163.63 | +0.16% | 4 | 6/5/3 | 0 | ALPACA_LIVE | deterministic_rule_engine | analyse |
| 2026-10-20 | 22:33 | $101,253.87 | $22,877.11 | $282,751.91 | $1,110.13 | +1.11% | $1,253.87 | +1.25% | 6 | 1/0/13 | 1 | ALPACA_LIVE | crewai_agents | execute |
| 2026-10-21 | 00:03 | $101,073.89 | $22,877.11 | $282,266.31 | $930.15 | +0.93% | $1,073.89 | +1.07% | 6 | 7/4/3 | 0 | ALPACA_LIVE | deterministic_rule_engine | analyse |
| 2026-10-21 | 22:37 | $101,622.42 | $14,939.87 | $268,977.98 | $296.30 | +0.29% | $1,622.42 | +1.62% | 7 | 3/2/9 | 2 | ALPACA_LIVE | crewai_agents | execute |
| 2026-10-22 | 00:08 | $101,720.09 | $14,939.87 | $269,199.00 | $393.97 | +0.39% | $1,720.09 | +1.72% | 7 | 8/4/2 | 0 | ALPACA_LIVE | deterministic_rule_engine | analyse |
| 2026-10-22 | 22:35 | $99,160.29 | $2,084.36 | $263,088.04 | $-2,516.33 | -2.47% | $-839.71 | -0.84% | 9 | 2/4/8 | 1 | ALPACA_LIVE | crewai_agents | execute |
| 2026-10-23 | 00:06 | $98,863.14 | $2,084.36 | $262,663.22 | $-2,813.48 | -2.77% | $-1,136.86 | -1.14% | 9 | 7/5/2 | 0 | ALPACA_LIVE | deterministic_rule_engine | analyse |
| 2026-10-23 | 22:29 | $98,756.84 | $1,984.96 | $261,763.31 | $-655.17 | -0.66% | $-1,243.16 | -1.24% | 10 | 6/4/4 | 3 | ALPACA_LIVE | crewai_agents | execute |
| 2026-10-23 | 23:57 | $98,801.11 | $1,984.96 | $261,883.71 | $-610.90 | -0.61% | $-1,198.89 | -1.20% | 10 | 6/5/3 | 0 | ALPACA_LIVE | deterministic_rule_engine | analyse |
| 2026-10-27 | 00:42 | $98,014.45 | $17,586.08 | $279,059.70 | $-611.66 | -0.62% | $-1,985.55 | -1.99% | 7 | 6/5/3 | 0 | ALPACA_LIVE | deterministic_rule_engine | analyse |
| 2026-10-28 | 00:41 | $98,117.25 | $17,585.74 | $278,594.03 | $-146.55 | -0.15% | $-1,882.75 | -1.88% | 7 | 6/5/3 | 0 | ALPACA_LIVE | deterministic_rule_engine | analyse |
| 2026-10-29 | 01:10 | $99,245.23 | $17,585.74 | $280,938.09 | $1,013.95 | +1.03% | $-754.77 | -0.75% | 7 | 6/4/4 | 0 | ALPACA_LIVE | deterministic_rule_engine | analyse |
| 2026-10-30 | 01:16 | $100,900.42 | $17,585.74 | $285,277.74 | $2,288.01 | +2.32% | $900.42 | +0.90% | 7 | 7/5/2 | 0 | ALPACA_LIVE | deterministic_rule_engine | analyse |
| 2026-10-31 | 00:58 | $101,158.44 | $17,585.74 | $285,790.77 | $765.11 | +0.76% | $1,158.44 | +1.16% | 7 | 7/6/1 | 0 | ALPACA_LIVE | deterministic_rule_engine | analyse |
| 2026-11-03 | 03:02 | $101,540.06 | $17,585.74 | $286,974.91 | $402.55 | +0.40% | $1,540.06 | +1.54% | 7 | 8/5/1 | 0 | ALPACA_LIVE | deterministic_rule_engine | analyse |
| 2026-11-04 | 01:35 | $100,824.41 | $17,585.74 | $284,578.18 | $-811.11 | -0.80% | $824.41 | +0.82% | 7 | 7/4/3 | 0 | ALPACA_LIVE | deterministic_rule_engine | analyse |
| 2026-11-05 | 01:40 | $104,635.22 | $17,585.74 | $292,240.14 | $3,513.48 | +3.47% | $4,635.22 | +4.64% | 7 | 9/3/2 | 0 | ALPACA_LIVE | deterministic_rule_engine | analyse |
| 2026-11-06 | 01:43 | $102,007.43 | $17,585.74 | $286,618.13 | $-2,184.61 | -2.10% | $2,007.43 | +2.01% | 7 | 8/4/2 | 0 | ALPACA_LIVE | deterministic_rule_engine | analyse |
| 2026-11-07 | 01:04 | $103,238.89 | $17,585.74 | $288,649.04 | $831.81 | +0.81% | $3,238.89 | +3.24% | 7 | 6/5/3 | 0 | ALPACA_LIVE | deterministic_rule_engine | analyse |
| 2026-11-10 | 03:44 | $104,698.47 | $17,585.74 | $291,745.38 | $1,697.16 | +1.65% | $4,698.47 | +4.70% | 7 | 8/5/1 | 0 | ALPACA_LIVE | deterministic_rule_engine | analyse |
| 2026-11-11 | 01:24 | $103,989.26 | $17,585.74 | $291,001.12 | $-741.40 | -0.71% | $3,989.26 | +3.99% | 7 | 8/5/1 | 0 | ALPACA_LIVE | deterministic_rule_engine | analyse |
| 2026-11-12 | 02:25 | $103,866.53 | $17,585.74 | $291,239.70 | $350.48 | +0.34% | $3,866.53 | +3.87% | 7 | 7/5/2 | 0 | ALPACA_LIVE | deterministic_rule_engine | analyse |
| 2026-11-13 | 02:03 | $102,834.91 | $17,585.74 | $289,632.89 | $-1,055.03 | -1.02% | $2,834.91 | +2.83% | 7 | 7/4/3 | 0 | ALPACA_LIVE | deterministic_rule_engine | analyse |

## Notes

- OHLCV for 14/14 symbols in 1 HTTP request(s); 50 news article(s) in the last 48h; LLM disabled for this run (provider=none or --no-llm); the deterministic rule engine decides everything.; exits processed first; $15,515 of freed capital is available to this run's entries; orders NOT submitted: mode=analyse, require_human_approval=True. Submission needs mode=execute AND REQUIRE_HUMAN_APPROVAL=false.
- OHLCV for 14/14 symbols (plus 2 benchmark(s)) in 1 HTTP request(s); intraday bars for 14 symbol(s); 50 news article(s) in the last 48h; LLM disabled for this run (provider=none or --no-llm); the deterministic rule engine decides everything.; orders NOT submitted: mode=analyse, require_human_approval=True. Submission needs mode=execute AND REQUIRE_HUMAN_APPROVAL=false.; alpha logged: 10 trade(s), mean excess -1.54%
- OHLCV for 14/14 symbols (plus 2 benchmark(s)) in 1 HTTP request(s); intraday bars for 14 symbol(s); 50 news article(s) in the last 48h; LLM disabled for this run (provider=none or --no-llm); the deterministic rule engine decides everything.; exits processed first; $7,629 of freed capital is available to this run's entries; orders NOT submitted: mode=analyse, require_human_approval=True. Submission needs mode=execute AND REQUIRE_HUMAN_APPROVAL=false.; alpha logged: 10 trade(s), mean excess -1.67%
- OHLCV for 14/14 symbols (plus 2 benchmark(s)) in 1 HTTP request(s); intraday bars for 14 symbol(s); 50 news article(s) in the last 48h; LLM disabled for this run (provider=none or --no-llm); the deterministic rule engine decides everything.; orders NOT submitted: mode=analyse, require_human_approval=True. Submission needs mode=execute AND REQUIRE_HUMAN_APPROVAL=false.; alpha logged: 10 trade(s), mean excess -1.79%
- OHLCV for 14/14 symbols (plus 2 benchmark(s)) in 1 HTTP request(s); intraday bars for 14 symbol(s); 50 news article(s) in the last 48h; LLM disabled for this run (provider=none or --no-llm); the deterministic rule engine decides everything.; orders NOT submitted: mode=analyse, require_human_approval=True. Submission needs mode=execute AND REQUIRE_HUMAN_APPROVAL=false.; alpha logged: 10 trade(s), mean excess -0.37%
- OHLCV for 14/14 symbols (plus 2 benchmark(s)) in 1 HTTP request(s); intraday bars for 14 symbol(s); 50 news article(s) in the last 48h; LLM disabled for this run (provider=none or --no-llm); the deterministic rule engine decides everything.; orders NOT submitted: mode=analyse, require_human_approval=True. Submission needs mode=execute AND REQUIRE_HUMAN_APPROVAL=false.; alpha logged: 10 trade(s), mean excess +2.16%
- OHLCV for 14/14 symbols (plus 2 benchmark(s)) in 1 HTTP request(s); intraday bars for 14 symbol(s); 50 news article(s) in the last 48h; LLM disabled for this run (provider=none or --no-llm); the deterministic rule engine decides everything.; high-beta sleeve is 100% of this run's entries; orders NOT submitted: mode=analyse, require_human_approval=True. Submission needs mode=execute AND REQUIRE_HUMAN_APPROVAL=false.; alpha logged: 10 trade(s), mean excess +4.27%
- OHLCV for 14/14 symbols (plus 2 benchmark(s)) in 1 HTTP request(s); intraday bars for 14 symbol(s); 50 news article(s) in the last 48h; LLM disabled for this run (provider=none or --no-llm); the deterministic rule engine decides everything.; high-beta sleeve is 100% of this run's entries; orders NOT submitted: mode=analyse, require_human_approval=True. Submission needs mode=execute AND REQUIRE_HUMAN_APPROVAL=false.; alpha logged: 10 trade(s), mean excess +3.63%
- OHLCV for 14/14 symbols (plus 2 benchmark(s)) in 1 HTTP request(s); intraday bars for 14 symbol(s); 50 news article(s) in the last 48h; LLM disabled for this run (provider=none or --no-llm); the deterministic rule engine decides everything.; high-beta sleeve is 42% of this run's entries; orders NOT submitted: mode=analyse, require_human_approval=True. Submission needs mode=execute AND REQUIRE_HUMAN_APPROVAL=false.; alpha logged: 10 trade(s), mean excess +6.28%
- OHLCV for 14/14 symbols (plus 2 benchmark(s)) in 1 HTTP request(s); intraday bars for 14 symbol(s); 50 news article(s) in the last 48h; LLM disabled for this run (provider=none or --no-llm); the deterministic rule engine decides everything.; high-beta sleeve is 55% of this run's entries; orders NOT submitted: mode=analyse, require_human_approval=True. Submission needs mode=execute AND REQUIRE_HUMAN_APPROVAL=false.; alpha logged: 10 trade(s), mean excess +7.67%
- OHLCV for 14/14 symbols (plus 2 benchmark(s)) in 1 HTTP request(s); intraday bars for 14 symbol(s); 50 news article(s) in the last 48h; LLM disabled for this run (provider=none or --no-llm); the deterministic rule engine decides everything.; orders NOT submitted: mode=analyse, require_human_approval=True. Submission needs mode=execute AND REQUIRE_HUMAN_APPROVAL=false.; alpha logged: 10 trade(s), mean excess +7.98%
- OHLCV for 14/14 symbols (plus 2 benchmark(s)) in 1 HTTP request(s); intraday bars for 14 symbol(s); 50 news article(s) in the last 48h; LLM disabled for this run (provider=none or --no-llm); the deterministic rule engine decides everything.; high-beta sleeve is 43% of this run's entries; orders NOT submitted: mode=analyse, require_human_approval=True. Submission needs mode=execute AND REQUIRE_HUMAN_APPROVAL=false.; alpha logged: 10 trade(s), mean excess +8.16%
- OHLCV for 14/14 symbols (plus 2 benchmark(s)) in 1 HTTP request(s); intraday bars for 14 symbol(s); 50 news article(s) in the last 48h; LLM disabled for this run (provider=none or --no-llm); the deterministic rule engine decides everything.; high-beta sleeve is 33% of this run's entries; orders NOT submitted: mode=analyse, require_human_approval=True. Submission needs mode=execute AND REQUIRE_HUMAN_APPROVAL=false.; alpha logged: 10 trade(s), mean excess +7.58%
- OHLCV for 14/14 symbols (plus 2 benchmark(s)) in 1 HTTP request(s); intraday bars for 14 symbol(s); 50 news article(s) in the last 48h; LLM disabled for this run (provider=none or --no-llm); the deterministic rule engine decides everything.; exits processed first; $14,397 of freed capital is available to this run's entries; high-beta sleeve is 34% of this run's entries; orders NOT submitted: mode=analyse, require_human_approval=True. Submission needs mode=execute AND REQUIRE_HUMAN_APPROVAL=false
- OHLCV for 14/14 symbols (plus 2 benchmark(s)) in 1 HTTP request(s); intraday bars for 14 symbol(s); 50 news article(s) in the last 48h; LLM disabled for this run (provider=none or --no-llm); the deterministic rule engine decides everything.; high-beta sleeve is 34% of this run's entries; orders NOT submitted: mode=analyse, require_human_approval=True. Submission needs mode=execute AND REQUIRE_HUMAN_APPROVAL=false.; alpha logged: 10 trade(s), mean excess +5.03%
