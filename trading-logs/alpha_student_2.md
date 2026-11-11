# student_2 — alpha history

Appended once per run, beside the daily log. Measures whether the trades we made actually earned anything:

- **Excess return** — our return minus the benchmark's over the same window. Did we beat the market on the names we picked?
- **Jensen's alpha** — our return minus beta x the benchmark's. Did we beat it *after adjusting for the risk taken*? The stricter test, and the honest one for a deliberately high-beta book.
- **Information coefficient (IC)** — correlation between the composite score at entry and the realised return. Do the indicators predict anything?

## Latest

| Metric | Value |
| --- | --- |
| Trades measured | 10 (10 still open) |
| Mean return | +5.41% |
| Mean excess vs SPY | +7.58% |
| Mean Jensen's alpha | +7.16% |
| Total P&L on these trades | $4,143.01 |
| Win rate | 90.00% |
| Signal IC | n/a |

> **Small sample.** 10 trades. Significance needs 30+ as a bare minimum and realistically hundreds, and beta is itself noisy over a short period. These numbers describe what happened; they do not establish whether the strategy works.

## History

| Date | UTC | Run | Trades | Open | Mean return | Excess | Jensen | Win rate | IC | Total P&L | Data |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 2026-10-26 | 10:29 | backfill | 10 | 10 | -0.91% | -0.03% | -0.23% | 50.00% | n/a | $-1,378.05 | ALPACA_LIVE |
| 2026-10-27 | 00:42 | snapshot | 10 | 10 | -1.72% | -1.54% | -1.63% | 50.00% | n/a | $-1,798.38 | ALPACA_LIVE |
| 2026-10-28 | 00:41 | snapshot | 10 | 10 | -1.26% | -1.67% | -1.66% | 50.00% | n/a | $-1,685.74 | ALPACA_LIVE |
| 2026-10-29 | 01:10 | snapshot | 10 | 10 | -1.04% | -1.79% | -1.72% | 40.00% | n/a | $-1,204.36 | ALPACA_LIVE |
| 2026-10-30 | 01:16 | snapshot | 10 | 10 | +0.01% | -0.37% | -0.37% | 50.00% | n/a | $263.39 | ALPACA_LIVE |
| 2026-10-31 | 00:58 | snapshot | 10 | 10 | +0.75% | +2.16% | +1.87% | 70.00% | n/a | $752.38 | ALPACA_LIVE |
| 2026-11-03 | 03:02 | snapshot | 10 | 10 | +2.37% | +4.27% | +3.90% | 70.00% | n/a | $1,359.45 | ALPACA_LIVE |
| 2026-11-04 | 01:35 | snapshot | 10 | 10 | +2.04% | +3.63% | +3.31% | 70.00% | n/a | $984.89 | ALPACA_LIVE |
| 2026-11-05 | 01:40 | snapshot | 10 | 10 | +6.31% | +6.28% | +6.23% | 90.00% | n/a | $4,851.01 | ALPACA_LIVE |
| 2026-11-06 | 01:43 | snapshot | 10 | 10 | +3.35% | +7.67% | +6.90% | 60.00% | n/a | $2,611.23 | ALPACA_LIVE |
| 2026-11-07 | 01:04 | snapshot | 10 | 10 | +3.91% | +7.98% | +7.25% | 60.00% | n/a | $3,117.49 | ALPACA_LIVE |
| 2026-11-10 | 03:44 | snapshot | 10 | 10 | +6.36% | +8.16% | +7.81% | 90.00% | n/a | $5,246.10 | ALPACA_LIVE |
| 2026-11-11 | 01:24 | snapshot | 10 | 10 | +5.41% | +7.58% | +7.16% | 90.00% | n/a | $4,143.01 | ALPACA_LIVE |

## Notes

- backfilled from Alpaca order history: the composite score at entry was not recorded for these trades, so the information coefficient cannot be computed for them
