# student_1 — alpha history

Appended once per run, beside the daily log. Measures whether the trades we made actually earned anything:

- **Excess return** — our return minus the benchmark's over the same window. Did we beat the market on the names we picked?
- **Jensen's alpha** — our return minus beta x the benchmark's. Did we beat it *after adjusting for the risk taken*? The stricter test, and the honest one for a deliberately high-beta book.
- **Information coefficient (IC)** — correlation between the composite score at entry and the realised return. Do the indicators predict anything?

## Latest

| Metric | Value |
| --- | --- |
| Trades measured | 12 (8 still open) |
| Mean return | +0.72% |
| Mean excess vs SPY | +0.35% |
| Mean Jensen's alpha | +0.87% |
| Total P&L on these trades | $758.72 |
| Win rate | 83.33% |
| Signal IC | n/a |

> **Small sample.** 12 trades. Significance needs 30+ as a bare minimum and realistically hundreds, and beta is itself noisy over a short period. These numbers describe what happened; they do not establish whether the strategy works.

## History

| Date | UTC | Run | Trades | Open | Mean return | Excess | Jensen | Win rate | IC | Total P&L | Data |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 2026-10-26 | 10:29 | backfill | 12 | 8 | +0.54% | +1.26% | +1.65% | 66.67% | n/a | $582.80 | ALPACA_LIVE |
| 2026-10-27 | 00:41 | snapshot | 12 | 8 | +0.87% | +1.11% | +1.56% | 83.33% | n/a | $921.41 | ALPACA_LIVE |
| 2026-10-28 | 00:39 | snapshot | 12 | 8 | +0.98% | +0.83% | +1.32% | 83.33% | n/a | $1,129.82 | ALPACA_LIVE |
| 2026-10-29 | 01:09 | snapshot | 12 | 8 | +0.72% | +0.35% | +0.87% | 83.33% | n/a | $758.72 | ALPACA_LIVE |

## Notes

- backfilled from Alpaca order history: the composite score at entry was not recorded for these trades, so the information coefficient cannot be computed for them
