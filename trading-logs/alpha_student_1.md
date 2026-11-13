# student_1 — alpha history

Appended once per run, beside the daily log. Measures whether the trades we made actually earned anything:

- **Excess return** — our return minus the benchmark's over the same window. Did we beat the market on the names we picked?
- **Jensen's alpha** — our return minus beta x the benchmark's. Did we beat it *after adjusting for the risk taken*? The stricter test, and the honest one for a deliberately high-beta book.
- **Information coefficient (IC)** — correlation between the composite score at entry and the realised return. Do the indicators predict anything?

## Latest

| Metric | Value |
| --- | --- |
| Trades measured | 12 (8 still open) |
| Mean return | -0.11% |
| Mean excess vs SPY | +0.83% |
| Mean Jensen's alpha | +1.21% |
| Total P&L on these trades | $556.27 |
| Win rate | 58.33% |
| Signal IC | n/a |

> **Small sample.** 12 trades. Significance needs 30+ as a bare minimum and realistically hundreds, and beta is itself noisy over a short period. These numbers describe what happened; they do not establish whether the strategy works.

## History

| Date | UTC | Run | Trades | Open | Mean return | Excess | Jensen | Win rate | IC | Total P&L | Data |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 2026-10-26 | 10:29 | backfill | 12 | 8 | +0.54% | +1.26% | +1.65% | 66.67% | n/a | $582.80 | ALPACA_LIVE |
| 2026-10-27 | 00:41 | snapshot | 12 | 8 | +0.87% | +1.11% | +1.56% | 83.33% | n/a | $921.41 | ALPACA_LIVE |
| 2026-10-28 | 00:39 | snapshot | 12 | 8 | +0.98% | +0.83% | +1.32% | 83.33% | n/a | $1,129.82 | ALPACA_LIVE |
| 2026-10-29 | 01:09 | snapshot | 12 | 8 | +0.72% | +0.35% | +0.87% | 83.33% | n/a | $758.72 | ALPACA_LIVE |
| 2026-10-30 | 01:15 | snapshot | 12 | 8 | +1.22% | +1.09% | +1.58% | 75.00% | n/a | $1,470.81 | ALPACA_LIVE |
| 2026-10-31 | 00:57 | snapshot | 12 | 8 | +0.60% | +1.67% | +2.02% | 66.67% | n/a | $795.71 | ALPACA_LIVE |
| 2026-11-03 | 03:00 | snapshot | 12 | 8 | -0.07% | +1.32% | +1.65% | 50.00% | n/a | $189.63 | ALPACA_LIVE |
| 2026-11-04 | 01:34 | snapshot | 12 | 8 | -0.51% | +0.68% | +1.03% | 50.00% | n/a | $-335.14 | ALPACA_LIVE |
| 2026-11-05 | 01:39 | snapshot | 12 | 8 | +0.39% | +0.50% | +0.97% | 66.67% | n/a | $1,228.12 | ALPACA_LIVE |
| 2026-11-06 | 01:42 | snapshot | 12 | 8 | -2.47% | +0.53% | +0.68% | 50.00% | n/a | $-2,246.47 | ALPACA_LIVE |
| 2026-11-07 | 01:02 | snapshot | 12 | 8 | -2.15% | +0.69% | +0.86% | 50.00% | n/a | $-1,959.43 | ALPACA_LIVE |
| 2026-11-10 | 03:43 | snapshot | 12 | 8 | -0.73% | +0.60% | +0.93% | 58.33% | n/a | $-120.50 | ALPACA_LIVE |
| 2026-11-11 | 01:23 | snapshot | 12 | 8 | -0.78% | +0.80% | +1.10% | 66.67% | n/a | $-169.93 | ALPACA_LIVE |
| 2026-11-12 | 02:24 | snapshot | 12 | 8 | -0.33% | +0.38% | +0.78% | 58.33% | n/a | $292.17 | ALPACA_LIVE |
| 2026-11-13 | 02:02 | snapshot | 12 | 8 | -0.11% | +0.83% | +1.21% | 58.33% | n/a | $556.27 | ALPACA_LIVE |

## Notes

- backfilled from Alpaca order history: the composite score at entry was not recorded for these trades, so the information coefficient cannot be computed for them
