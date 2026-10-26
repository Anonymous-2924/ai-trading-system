# student_1 — alpha history

Appended once per run, beside the daily log. Measures whether the trades we made actually earned anything:

- **Excess return** — our return minus the benchmark's over the same window. Did we beat the market on the names we picked?
- **Jensen's alpha** — our return minus beta x the benchmark's. Did we beat it *after adjusting for the risk taken*? The stricter test, and the honest one for a deliberately high-beta book.
- **Information coefficient (IC)** — correlation between the composite score at entry and the realised return. Do the indicators predict anything?

## Latest

| Metric | Value |
| --- | --- |
| Trades measured | 12 (8 still open) |
| Mean return | +0.54% |
| Mean excess vs SPY | +1.26% |
| Mean Jensen's alpha | +1.65% |
| Total P&L on these trades | $582.80 |
| Win rate | 66.67% |
| Signal IC | n/a |

> **Small sample.** 12 trades. Significance needs 30+ as a bare minimum and realistically hundreds, and beta is itself noisy over a short period. These numbers describe what happened; they do not establish whether the strategy works.

## History

| Date | UTC | Run | Trades | Open | Mean return | Excess | Jensen | Win rate | IC | Total P&L | Data |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 2026-10-26 | 10:29 | backfill | 12 | 8 | +0.54% | +1.26% | +1.65% | 66.67% | n/a | $582.80 | ALPACA_LIVE |

## Notes

- backfilled from Alpaca order history: the composite score at entry was not recorded for these trades, so the information coefficient cannot be computed for them
