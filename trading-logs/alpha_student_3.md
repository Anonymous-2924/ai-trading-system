# student_3 — alpha history

Appended once per run, beside the daily log. Measures whether the trades we made actually earned anything:

- **Excess return** — our return minus the benchmark's over the same window. Did we beat the market on the names we picked?
- **Jensen's alpha** — our return minus beta x the benchmark's. Did we beat it *after adjusting for the risk taken*? The stricter test, and the honest one for a deliberately high-beta book.
- **Information coefficient (IC)** — correlation between the composite score at entry and the realised return. Do the indicators predict anything?

## Latest

| Metric | Value |
| --- | --- |
| Trades measured | 10 (8 still open) |
| Mean return | +3.37% |
| Mean excess vs SPY | +4.70% |
| Mean Jensen's alpha | +4.22% |
| Total P&L on these trades | $3,205.12 |
| Win rate | 70.00% |
| Signal IC | n/a |

> **Small sample.** 10 trades. Significance needs 30+ as a bare minimum and realistically hundreds, and beta is itself noisy over a short period. These numbers describe what happened; they do not establish whether the strategy works.

## History

| Date | UTC | Run | Trades | Open | Mean return | Excess | Jensen | Win rate | IC | Total P&L | Data |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 2026-10-26 | 10:29 | backfill | 10 | 8 | +1.08% | +1.98% | +1.72% | 60.00% | n/a | $932.20 | ALPACA_LIVE |
| 2026-10-27 | 00:43 | snapshot | 10 | 8 | +1.62% | +1.96% | +2.00% | 70.00% | n/a | $1,410.42 | ALPACA_LIVE |
| 2026-10-28 | 00:42 | snapshot | 10 | 8 | +1.68% | +1.55% | +1.82% | 50.00% | n/a | $1,319.69 | ALPACA_LIVE |
| 2026-10-29 | 01:11 | snapshot | 10 | 8 | +1.81% | +1.41% | +1.82% | 50.00% | n/a | $1,314.20 | ALPACA_LIVE |
| 2026-10-30 | 01:17 | snapshot | 10 | 8 | +3.60% | +3.49% | +3.76% | 70.00% | n/a | $2,984.36 | ALPACA_LIVE |
| 2026-10-31 | 00:59 | snapshot | 10 | 8 | +3.37% | +4.70% | +4.22% | 70.00% | n/a | $3,205.12 | ALPACA_LIVE |

## Notes

- backfilled from Alpaca order history: the composite score at entry was not recorded for these trades, so the information coefficient cannot be computed for them
