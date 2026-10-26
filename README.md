# AI-Powered Algorithmic Paper-Trading System

Live **paper** trading on Alpaca for a team of three students, each with
$100,000 and a 14-stock universe. A 29-feature technical ensemble plus news
sentiment produces BUY / SELL / HOLD with a conviction; a CrewAI agent crew
interprets that through a local MCP server; a deterministic rule engine
produces the same decisions with no LLM at all and takes over automatically —
and loudly — whenever the LLM is unavailable.

> **Paper trading only.** Two independent guards keep every order on
> `https://paper-api.alpaca.markets`. There is no live-trading code path.

---

## Contents

- [Quick start (Ubuntu)](#quick-start-ubuntu)
- [Aggression — what was chosen and why](#aggression--what-was-chosen-and-why)
- [The universe](#the-universe)
- [Features (29 across five dimensions)](#features-29-across-five-dimensions)
- [The ensemble, and the MACD 60/40 rule](#the-ensemble-and-the-macd-6040-rule)
- [Architecture](#architecture)
- [The MCP server and its tool-schema rules](#the-mcp-server-and-its-tool-schema-rules)
- [LLM providers](#llm-providers)
- [Risk management](#risk-management)
- [Paper-trading guards](#paper-trading-guards)
- [Per-member daily logs](#per-member-daily-logs)
- [GitHub Actions](#github-actions)
- [Dashboard](#dashboard)
- [Demo mode and the refusal to invent](#demo-mode-and-the-refusal-to-invent)
- [Testing](#testing)
- [Integration failures this build handles](#integration-failures-this-build-handles)
- [What I verified, and what I could not](#what-i-verified-and-what-i-could-not)

---

## Quick start (Ubuntu)

```bash
sudo apt update
sudo apt install -y python3.12 python3.12-venv python3-pip git

git clone https://github.com/Anonymous-2924/ai-trading-system.git
cd ai-trading-system

python3.12 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip

# --ignore-installed PyYAML avoids the Debian/Ubuntu PyYAML RECORD error
# that otherwise aborts the install.
pip install --ignore-installed PyYAML -r requirements.txt

cp .env.example .env    # then fill it in; .env is gitignored
```

The fastest thing that proves the install works — no keys needed:

```bash
python scripts/run_trading.py --demo --no-llm
```

Then, with real Alpaca paper keys in `.env`:

```bash
python scripts/test_llm.py                      # ~1 min provider check
python scripts/run_trading.py --students student_1
streamlit run dashboard/app.py
pytest
```

### Entry points

| Command | What it does |
| --- | --- |
| `python scripts/run_trading.py` | Run the pipeline for every student |
| `python scripts/run_trading.py --demo --no-llm` | Synthetic data, rule engine only |
| `python scripts/run_trading.py --mode execute` | Submit orders (also needs `REQUIRE_HUMAN_APPROVAL=false`) |
| `python scripts/test_llm.py` | Four-stage LLM check in about a minute |
| `python scripts/test_llm.py --list-models` | List the models **your** account can see |
| `python scripts/run_mcp_server.py` | Run the MCP server on stdio |
| `python scripts/alpha_report.py` | Attribute performance: excess return, Jensen's alpha, signal IC |
| `python scripts/backfill_ledger.py --dry-run` | Recover trades made before the ledger existed, from Alpaca order history |
| `python scripts/await_market_window.py --window open` | Wait for the right point in the session |
| `python scripts/check_alpaca.py` | Show which Alpaca account each key pair belongs to |
| `streamlit run dashboard/app.py` | The control panel |
| `pytest` | 428 tests |

---

## Aggression — what was chosen and why

The brief is explicit: *"You are all young and MUST take risks. A conservative
or cautious approach will not do."* So the defaults here are deliberately well
above textbook. `AGGRESSION` is a single 0.0–1.0 dial that interpolates every
risk parameter between a timid and an aggressive end, and **the default is
0.75**.

| Parameter | Timid (0.0) | **Default (0.75)** | Maximal (1.0) | Textbook retail advice |
| --- | --- | --- | --- | --- |
| Base position size | 3% of equity | **11.3%** | 14% | 1–2% |
| Max concurrent positions | 8 | **13** | 15 | 10–20 |
| Max gross exposure | 0.60× | **1.16×** | 1.35× | ≤ 1.0× (no margin) |
| Max single name | 8% | **18.5%** | 22% | 5% |
| Max single sector | 25% | **40%** | 45% | 20–25% |
| ATR stop multiple | 1.5× | **2.47×** | 2.8× | 1.5–2× |
| ATR target multiple | 2.5× | **5.12×** | 6.0× | 2–3× |

Why these numbers:

- **11.3% base size, up to 18.5% on a VERY_HIGH conviction.** With a 15-stock
  universe and a 15–20 day horizon there is no time for a 1%-per-trade book to
  express a view. At 1% sizing a 20% winner moves the account 0.2%; the whole
  exercise would be noise.
- **1.16× gross exposure.** Alpaca paper accounts grant 2× intraday / 1×
  overnight Reg-T margin on equities, so this uses leverage without running
  into the overnight limit. (I believe those are the current Reg-T terms for
  a margin-enabled Alpaca paper account — worth confirming on your own
  account before relying on it.)
- **40% sector cap, not 20%.** The high-beta sleeve is concentrated in
  technology by construction. A 20% cap would make the mandated 30% high-beta
  allocation impossible to fill.
- **Wide ATR stops (2.47×) with even wider targets (5.12×).** High-beta names
  have large daily ranges; a 1.5× ATR stop on a stock with a 6% daily range is
  stopped out by ordinary noise. The ~1:2 stop-to-target ratio means the
  strategy can be right less than half the time and still make money.
- **LOW conviction opens nothing.** Aggression is about sizing the trades you
  believe in, not about taking more trades. The conviction multipliers are
  LOW 0.0, MEDIUM 0.7, HIGH 1.0, VERY_HIGH 1.35.

Change it per run without touching the config:

```bash
python scripts/run_trading.py --aggression 1.0     # maximal
AGGRESSION=0.3 python scripts/run_trading.py       # or via the environment
```

**This is a paper account and a student exercise.** These settings would be
inappropriate for real money without a great deal more thought about drawdown
tolerance, and a 15–20 day window is far too short to tell skill from luck.

---

## The universe

42 unique symbols across the group, 14 per student, **35.7% high-beta each**
(the brief requires at least 30%).

| | High-beta sleeve (5) | Diversified basket (9) |
| --- | --- | --- |
| **student_1** | TSLA, NVDA, PLTR, COIN, SMCI | AAPL, MSFT, JNJ, JPM, XOM, PG, V, CAT, UNH |
| **student_2** | AMD, MRNA, ENPH, RIVN, DKNG | GOOGL, AMZN, KO, BAC, CVX, HD, MRK, HON, COST |
| **student_3** | MARA, AFRM, UPST, CCL, ON | META, ORCL, PEP, WFC, LMT, DIS, ABBV, NKE, WMT |

A note on sourcing: the high-beta names are chosen as *representative* of the
S&P High Beta Index style — large-cap US equities with persistently high beta
to the S&P 500. **I did not verify these against the current published index
constituents**, which are rebalanced quarterly by S&P Dow Jones Indices and
which I cannot fetch from this environment. If your assignment is graded on
exact index membership, check the current constituent list and edit
`config/config.yaml` — the universe is entirely config-driven and nothing in
the code hardcodes a ticker.

Every symbol is also mapped to a sector in `config/config.yaml`, which the
sector-exposure cap uses. An unmapped symbol falls into a shared `unknown`
bucket, so it is treated conservatively rather than escaping the cap.

---

## Features (29 across five dimensions)

All implemented directly in pandas/numpy in `src/trading_system/indicators.py`.
**`pandas_ta` is deliberately not a dependency** — it imports `numpy.NaN`,
removed in numpy 2.0, so it breaks on any current install. A test asserts it is
neither imported nor in `requirements.txt`.

| Dimension | Features | Count |
| --- | --- | --- |
| **Trend** | `ema20_rel`, `ema50_rel`, `ema200_rel`, `ema20_50_spread`, `ema50_200_spread`, `adx`, `di_bias`, `macd_line` | 8 |
| **Momentum** | `rsi14`, `macd_hist_pct`, `roc12`, `tsi`, `rs_spy20`, `rs_qqq20` | 6 |
| **Volume** | `cmf20`, `obv_slope20`, `mfi14`, `rvol` | 4 |
| **Volatility** | `natr14`, `natr_z60`, `bb_width`, `bb_pct_b`, `donchian_pos20`, `orb_pos` | 6 |
| **Statistics** | `zscore20`, `ret5`, `ret20`, `ret60`, `skew60`, `beta60` | 6 |

**Relative strength** (`rs_spy20`, `rs_qqq20`) is the stock's 20-day return
minus the benchmark's. Without it every other feature happily buys a stock up
3% on a day the market is up 4% — which is underperformance dressed as a gain.
The benchmarks ride along in the same batched request, so they cost no extra
round trip.

`orb_pos` and `rvol` are the daily-bar translation of the opening-range and
relative-volume ideas from intraday trading: the position of price within the
session's first 15-minute range, and volume so far today against the same
point in prior sessions. Both need 15-minute bars and are neutral without
them. **`rvol` is scored as a weak confirmation and never as a gate**, because
Alpaca's free IEX feed sees only a small slice of consolidated volume.

ATR is computed but **not scored** — it has no direction. It is carried as a
diagnostic for stop sizing, alongside beta and the raw opening range.

Plus news sentiment as a sixth weighted input.

### Wilder's smoothing

RSI, ATR and ADX use Wilder's smoothing **seeded with the SMA of the first
`period` observations**, not an EWM seed:

```
seed = mean(x[0 : period])
s[t] = s[t-1] + (x[t] - s[t-1]) / period
```

`Series.ewm(alpha=1/period, adjust=False)` seeds with the *first observation
alone* and disagrees with every charting package for hundreds of bars. Both
are checked against hand calculations in `tests/test_indicators.py`:

```
RSI(3) over closes 10, 11, 12, 11, 13, 12, 14
  gains  = 1, 1, 0, 2, 0, 2        losses = 0, 0, 1, 0, 1, 0
  seedG  = (1+1+0)/3 = 0.666667    seedL  = (0+0+1)/3 = 0.333333
  avgG   = 1.111111, 0.740741, 1.160494
  avgL   = 0.222222, 0.481481, 0.320988
  RS     = 3.615385  ->  RSI = 78.333333    # the implementation agrees exactly

ATR(3) over TR 2, 2, 2, 2, 3
  seed = 2  ->  2  ->  2.333333              # likewise
```

---

## The ensemble, and the MACD 60/40 rule

Each feature maps to a sub-score in `[-1, +1]`. Sub-scores are averaged within
their dimension; dimensions combine with configurable weights:

| Input | Weight |
| --- | --- |
| Trend | 0.28 |
| Momentum | 0.24 |
| Volume | 0.14 |
| Volatility | 0.12 |
| Statistics | 0.12 |
| News sentiment | 0.10 |

The composite maps to an action (`BUY ≥ +0.18`, `SELL ≤ −0.18`, else `HOLD`)
and a conviction (`|composite|`: ≥0.22 MEDIUM, ≥0.38 HIGH, ≥0.55 VERY_HIGH).

### MACD: the line is trend, the histogram is momentum

The MACD **line versus zero** is a *trend* statement; the **histogram** is a
*momentum* statement. They are weighted **60/40 in favour of the line**.

This matters because during a sustained decline the histogram turns positive
on every bounce. Scoring the histogram alone makes a severe drawdown read
BULLISH. The weights are derived at runtime so the 60/40 split survives any
re-weighting of the dimensions themselves:

```python
w_line = macd_budget * 0.60 / dimension_weight["trend"]
w_hist = macd_budget * 0.40 / dimension_weight["momentum"]
```

`tests/test_scoring.py` pins both the ratio and the behaviour. On a 68%
decline ending in a mild dead-cat bounce:

```
macd_line      = -0.390   ->  score -0.254   (bearish trend)
macd_hist_pct  = +0.464   ->  score +0.649   (bullish momentum)
ensemble       = HOLD at composite -0.080    (NOT a BUY)
```

The same decline with no bounce reads `SELL` at `-0.558`, VERY_HIGH.
Measured behaviour across regimes:

| Regime | Action | Composite |
| --- | --- | --- |
| Sustained decline, no bounce | SELL | −0.558 |
| Sustained decline + bounce | HOLD | −0.080 |
| Flat | HOLD | +0.133 |
| Sustained uptrend | BUY | +0.491 |

---

## Architecture

```
scripts/run_trading.py
        │
        ▼
 pipeline.run_for_student
        │
        ├── alpaca_client ── ONE batched /v2/stocks/bars request for ALL symbols
        │                 └─ ONE /v1beta1/news request for ALL symbols
        │
        ├── rule_engine (ALWAYS runs — the reference decision)
        │      features.extract_features  →  29 features
        │      sentiment.analyse_batch    →  lexicon score over real headlines
        │      scoring.score_featureset   →  composite → BUY/SELL/HOLD + conviction
        │
        ├── agents.run_crew (if an LLM is configured)
        │      CrewAI × 6 agents ──► mcp_client ──► LOCAL stdio MCP server
        │      market data → technical → quantitative → news → risk → decision
        │      ⚠ any failure → announced fallback to the rule engine
        │
        ├── risk.plan_orders   exits FIRST, then entries with the freed capital
        ├── alpaca_client.submit_order   only if mode=execute AND no approval needed
        ├── run_logger  → model-run/agentNameDDMMYYYY-HH-MM.md
        └── daily_log   → trading-logs/student_N.csv + .md   (always, even on failure)
```

### Module map

| File | Responsibility |
| --- | --- |
| `indicators.py` | Every indicator, in pandas/numpy. Wilder smoothing. |
| `features.py` | OHLCV → 29 named features for the latest bar |
| `scoring.py` | Weighted ensemble → composite, action, conviction, rationale |
| `sentiment.py` | Lexicon sentiment over real headlines; never fabricates |
| `rule_engine.py` | The deterministic reference engine |
| `agents.py` | Six CrewAI agents, tasks, and failure→fallback handling |
| `mcp_server.py` | The local stdio MCP server and its 10 tools |
| `mcp_client.py` | Stdio client + the CrewAI `MCPServerAdapter` bridge |
| `llm.py` | Provider selection, probing, the empty-response detector |
| `alpaca_client.py` | Batched market data, news, account, positions, orders |
| `paper_guard.py` | The two independent paper-trading guards |
| `risk.py` | Sizing, caps, ATR stops, exits-first, deterministic order ids |
| `daily_log.py` | Per-member CSV + Markdown logs |
| `run_logger.py` | `model-run/` agent artefacts |
| `pipeline.py` | Orchestration |
| `config.py` | YAML + environment, whitespace stripping, aggression lerp |
| `demo_data.py` | Clearly-labelled synthetic data |

---

## The MCP server and its tool-schema rules

A **local** stdio MCP server (`src/trading_system/mcp_server.py`), launched as
a subprocess. Alpaca's hosted MCP server is deliberately not used.

| Tool | Parameters |
| --- | --- |
| `get_run_configuration` | `scope` |
| `list_universe` | `student_id` |
| `get_account_snapshot` | `student_id` |
| `get_positions` | `student_id` |
| `get_batched_ohlcv` | `student_id`, `symbols` |
| `compute_indicators` | `student_id`, `symbols` |
| `get_news_sentiment` | `student_id`, `symbols` |
| `evaluate_rule_engine` | `student_id`, `symbols` |
| `size_position` | `student_id`, `symbol`, `conviction` |
| `place_paper_order` | `student_id`, `symbol`, `side`, `quantity` |

### Two schema rules, forced by CrewAI

CrewAI advertises tools in OpenAI **strict** mode. Both of these are verified
against the installed crewai 1.15.28 and re-checked on the wire by
`tests/test_crewai_integration.py`:

1. **No tool may have zero parameters.** Strict providers reject it.
   `get_run_configuration` genuinely needs no input, so it takes one required
   dummy argument, `scope`, documented as *"always pass 'all'"*.

2. **No tool may have an optional parameter.** `ensure_all_properties_required`
   in `crewai/utilities/pydantic_schema_utils.py` copies **every** property
   into `required`, Python defaults included — so an "optional" parameter is
   not expressible; the provider demands it anyway and the model invents a
   value. All tuning values therefore come from `config.yaml`, never from a
   tool argument.

Both rules are enforced three ways: at the source (no signature declares a
default), in the generated schema, and in the JSON actually sent to a provider.

```
$ python scripts/run_mcp_server.py          # stdio
10 tools advertised; properties == required on all of them
```

---

## LLM providers

Every provider is reached through an **OpenAI-compatible endpoint**, which
forces CrewAI's native OpenAI path (`custom_openai=True`) rather than the
LiteLLM fallback.

| `LLM_PROVIDER` | Base URL | Key | Model id |
| --- | --- | --- | --- |
| `ollama_cloud` *(default)* | `https://ollama.com/v1` | `OLLAMA_API_KEY` | plain, e.g. `gpt-oss:120b` |
| `ollama_local` | `http://localhost:11434/v1` | none, after `ollama signin` | `-cloud` suffix, e.g. `gpt-oss:120b-cloud` |
| `groq` | `https://api.groq.com/openai/v1` | `GROQ_API_KEY` | e.g. `llama-3.3-70b-versatile` |
| `openai_compatible` | `OPENAI_COMPATIBLE_BASE_URL` | `OPENAI_COMPATIBLE_API_KEY` | anything the endpoint serves |
| `none` | — | — | rule engine only |

Two things about Ollama specifically:

- **Local daemon.** After `ollama signin`, cloud models work through
  `localhost:11434`. Their ids end in `-cloud` and they do **not** appear in
  `/api/tags` — so a model missing from `ollama list` is not evidence it is
  unavailable, and this system never reports it as "not installed".
- **CI.** A runner has no browser, so `ollama signin` is not an option. Use the
  hosted OpenAI-compatible endpoint with `OLLAMA_API_KEY` and the **plain**
  model id (no suffix).

**No model name is hardcoded as the only option.** When a model fails, the
error tells you how to list the models your own account can see:

```bash
python scripts/test_llm.py --list-models
# or directly:
curl -s -H "Authorization: Bearer $OLLAMA_API_KEY" https://ollama.com/v1/models | python3 -m json.tool
```

### `scripts/test_llm.py` — four stages, about a minute

A full pipeline run takes minutes. This does not:

```
$ python scripts/test_llm.py
provider=ollama_cloud  model=gpt-oss:120b  base_url=https://ollama.com/v1  api_key=set  max_retries=8
[PASS] a) reach the provider           0.4s  12 model(s) visible to this account
[PASS] b) answer a plain prompt        1.9s  'READY'
[PASS] c) call an MCP tool             2.3s  10 tools, all strict-mode safe; list_universe -> 14 symbols
[PASS] d) return structured JSON       3.1s  2 decision(s)
4/4 stages passed in 7.7s
```

Each stage has its own timeout (`--timeout`), and a failure prints the
`--list-models` hint. Stage (c) runs with no provider at all, so it still
validates the MCP layer when the LLM is down.

### Rate limits and empty responses

- `max_retries` defaults to 8 and is passed to the OpenAI SDK, which honours
  `Retry-After` on 429 — free tiers return them constantly.
- `MAX_LLM_SYMBOLS` (default 8) caps how many symbols reach the crew. The
  crew costs roughly **2 requests per symbol + 4**, so 8 symbols ≈ 20
  requests, about 60 across the three students. At 12 each, the student who
  ran last was starved of quota. Symbols beyond the cap keep their
  rule-engine decision.
- `crew_budget_seconds` (default 420) is a **hard wall-clock budget** for the
  whole crew, per student. When a provider rate-limits, 8 retries at up to
  180s each can outlast the CI job's own timeout, and the job is then killed
  *before* it writes its daily-log row — which is how one team member
  silently stopped being logged for three days. Exceeding the budget
  abandons the crew and falls back, so a run always finishes and always
  logs.
- Small models loop and then return empty content, which CrewAI raises as
  *"Invalid response from LLM call - None or empty"*. `llm.is_empty_response_error`
  detects it and the run falls back rather than failing.

---

## Risk management

`src/trading_system/risk.py`.

- **Position sizing** — base % of equity × conviction multiplier ×
  **volatility scale**, clipped by the single-name cap. Equal-dollar sizing
  meant a stock swinging 9% a day carried roughly four times the risk of one
  swinging 2%, so the jumpiest names quietly dominated the book. Size is now
  divided by the stock's NATR relative to a reference (beta is the fallback),
  so each position contributes roughly equal *risk* rather than equal
  *dollars*:

  | Profile | NATR | Scale | Position on $100k, HIGH |
  | --- | --- | --- | --- |
  | Very calm (KO-like) | 1.2% | 1.40× | $15,750 |
  | Normal | 3.0% | 1.00× | $11,250 |
  | High-beta (TSLA-like) | 8.0% | 0.38× | $4,219 |
  | Extreme (MARA-like) | 14.0% | 0.35× | $3,938 |

  An unknown volatility scores 1.0×, so a missing input never silently shrinks
  a position to nothing.
- **Exits before entries.** SELLs are planned first and their proceeds are
  added to the cash available to the same run's BUYs, so freed capital is
  recycled immediately instead of idling for a day.
- **Long only.** A SELL on a symbol that is not held is **no action**, never a
  short. Enforced in the planner *and* in the `place_paper_order` MCP tool.
- **Caps** — max positions, gross exposure, single name, single sector, and a
  minimum cash buffer. Each rejection records which cap bound it.
- **ATR stops and targets, sent as real bracket orders.** Both are ATR
  multiples, so a volatile name gets a proportionally wider stop — and both
  are now attached to the entry at Alpaca (`order_class: bracket`), so the
  stop protects the position **between runs**. Previously they were computed
  and logged but never submitted, which meant an overnight gap had nothing
  standing in its way. The stop prefers the intraday ATR where 15-minute bars
  exist, since the daily ATR gives a very wide stop on a high-beta name.
  Alpaca rejects fractional bracket orders, so a bracketed entry is rounded
  **down** to whole shares; anything that rounds below one share is skipped
  rather than sent unprotected.
- **Buying-power checks** against the live account.
- **Deterministic `client_order_id`s** — `sha256(student|symbol|side|qty|UTC date)`.
  Re-running the same day produces the same id, Alpaca rejects the duplicate,
  and the client reports `duplicate_suppressed` rather than treating it as a
  failure.

```
$ python scripts/run_trading.py --demo --no-llm --students student_1
SELL SMCI  100.000 @ ~$40.00   ($4,000)
BUY  TSLA   16.000 @ ~$250.00  ($4,000, VERY_HIGH)  stop 220.30  target 311.50
  XOM   no action  — SELL on a symbol that is not held (long-only; never a short)
  NVDA  rejected   — buying power / cash buffer
  AAPL  rejected   — LOW conviction does not open a position
notes: exits processed first; $4,000 of freed capital is available to this run's entries
```

---

## Paper-trading guards

Two **independent** guards, sharing no state.

**Guard 1 — `validate_paper_endpoint`.** Parses the URL and requires
`scheme == https` and `hostname == "paper-api.alpaca.markets"` **exactly**,
with no userinfo, no port override and no path.

A substring check is not enough. `https://evil.test/paper-api.alpaca.markets`
*contains* the paper hostname and routes every order to an attacker's server.
All of these are rejected, and all are in `tests/test_paper_guard.py`:

```
https://evil.test/paper-api.alpaca.markets        ← the hostname is in the PATH
https://paper-api.alpaca.markets.evil.test        ← suffix attack
https://paper-api.alpaca.markets@evil.test        ← userinfo attack; host is evil.test
https://notpaper-api.alpaca.markets               ← prefix attack
https://evil.test/?host=paper-api.alpaca.markets  ← in the query string
http://paper-api.alpaca.markets                   ← downgraded scheme
https://paper-api.alpaca.markets:8443             ← non-default port
https://api.alpaca.markets                        ← LIVE trading; real money
```

**Guard 2 — `assert_paper_mode`.** Runs immediately before every order POST.
It re-parses the URL *actually about to be requested* against its own separate
allowlist, and refuses outright if `ALLOW_LIVE_TRADING` is set. A `base_url`
mutated after construction is caught here even though it bypassed guard 1
entirely — there is a test for exactly that.

---

## Per-member daily logs

```
trading-logs/student_1.csv   trading-logs/student_1.md
trading-logs/student_2.csv   trading-logs/student_2.md
trading-logs/student_3.csv   trading-logs/student_3.md
```

**These are committed to git deliberately.** The workflow pushes them back
after every run, so a 15–20 day history accumulates in the repository instead
of evaporating with the runner.

One row per run: UTC timestamp, date, equity, cash, buying power, **day P&L**
(the move since the previous close, from Alpaca's `last_equity`) and day P&L %,
**total P&L** and % (against the $100,000 start), open positions, BUY/SELL/HOLD
counts, orders submitted, whether the data was live or demo, which engine
decided, the mode, and notes.

The `.md` mirror adds total P&L, best day, worst day, up days vs down days,
peak equity, and renders as a table on GitHub:

| Metric | Value |
| --- | --- |
| Runs recorded | 4 |
| Latest equity | $107,500.00 |
| Total P&L | $7,500.00 |
| Total P&L % | +7.50% |
| Best day | +8.59% on 2026-10-04 |
| Worst day | −4.81% on 2026-10-03 |
| Up days | 2 |
| Down days | 1 |

Two guarantees, both tested:

- **A run that cannot read the account still appends a row**, with
  `data_source=UNAVAILABLE` and a note, so a gap shows up *as a row* rather
  than as a missing day.
- **A logging failure never breaks a trading run.** Every function catches its
  own exceptions and returns a status.

---

## GitHub Actions

### `.github/workflows/trading-analysis.yml`

- **Schedule:** two trading runs plus a snapshot every weekday. The crons
  fire EARLY and the job then waits for its real target, because a fixed UTC
  cron cannot express "30 minutes before the close": that is 19:30 UTC in US
  daylight time and 20:30 UTC in standard time, and GitHub's scheduler has
  fired one of our runs **over three hours late**.

  | Cron (UTC) | Waits until | US Eastern | What it does |
  | --- | --- | --- | --- |
  | `0 14 * * 1-5` | 10:05 ET | 35 min after the open | Morning trading run. The 09:30–09:45 opening range has formed and settled past the feed delay, and we are in the opening power hour rather than the opening auction. |
  | `25 19 * * 1-5` | 15:30 ET | 30 min before the close | Afternoon trading run, in the closing power hour. |
  | `30 21 * * 1-5` | — | after the close | Closing-equity snapshot. `--no-llm`, no orders, zero LLM quota. |

  `scripts/await_market_window.py` asks Alpaca's calendar when the session
  actually opens and closes, so the 1 November clock change cannot break it.
  If the scheduler fires so late that the window is gone, the run is skipped
  with a notice rather than trading at the wrong time. Both runs avoid the
  11:30–13:30 ET midday lull entirely.

  Plus `workflow_dispatch` with inputs for `mode`, `students`, `model`,
  `max_llm_symbols` and `aggression`.
- **Matrix** over the three students with **`max-parallel: 1`**, so each uses
  its own Alpaca account and parallel jobs cannot exhaust the LLM allowance.
- **Secrets:** `OLLAMA_API_KEY`, `ALPACA_API_KEY_1/2/3`,
  `ALPACA_SECRET_KEY_1/2/3`. Each is whitespace-stripped and passed to
  `::add-mask::` **before** being exported. A student whose secrets are absent
  is **skipped with a warning**, not failed.
- **Artifacts:** `model-run/` and the run log, 30-day retention; the run
  summary is printed to the job page.
- **A separate `commit-logs` job after the matrix** commits the logs back, so
  the matrix jobs cannot race each other pushing. The merge appends only rows
  the committed file does not already contain, so a re-run cannot duplicate a
  day, and it rebuilds the Markdown mirrors from the merged CSVs.

**Only `mode=execute` sets `REQUIRE_HUMAN_APPROVAL=false`**, and the workflow
decides that in exactly one place:

```bash
if [ "$RUN_MODE" = "execute" ]; then
  REQUIRE_HUMAN_APPROVAL=false
else
  REQUIRE_HUMAN_APPROVAL=true
fi
```

Orders are submitted only when **both** conditions hold. `RUN_MODE` is chosen
by this precedence:

1. The 21:30 snapshot is **always** `analyse` — it can never trade, whatever
   else is configured.
2. A manual *Run workflow* uses whichever `mode` the human picked.
3. Otherwise the 19:30 trading cron uses the repository variable
   `SCHEDULED_MODE`, defaulting to **`execute`**.

**To pause automatic trading** without touching the code, add a repository
variable `SCHEDULED_MODE` = `analyse` (Settings → Secrets and variables →
Actions → **Variables**). Delete it, or set it to `execute`, to resume.

### `.github/workflows/tests.yml`

- `pytest` (428 tests) on Python **3.11 and 3.12**, on every push and PR.
- Runs the **demo pipeline end to end** and asserts the agent artefacts and
  all six log files were produced, and that no demo artefact claims live data.
- Starts the **MCP server** and asserts every tool is strict-mode safe.
- Confirms the **refusal path** when there are no credentials.
- **Fails the build** if a `.env` is tracked, if `.env` is missing from
  `.gitignore`, if anything key-shaped is committed (Alpaca `PK…`/`AK…`,
  `gsk_…`, `sk-…`, `ghp_…`, PEM private keys), or if a credential is
  hardcoded instead of read from the environment.

### Required repository secrets

| Secret | Purpose |
| --- | --- |
| `ALPACA_API_KEY_1` / `ALPACA_SECRET_KEY_1` | student_1's paper account |
| `ALPACA_API_KEY_2` / `ALPACA_SECRET_KEY_2` | student_2's paper account |
| `ALPACA_API_KEY_3` / `ALPACA_SECRET_KEY_3` | student_3's paper account |
| `OLLAMA_API_KEY` | Ollama Cloud (optional — without it the rule engine runs) |

**Keys are never in the code.** `.env` is gitignored; `.env.example` is tracked.

---

## Dashboard

```bash
streamlit run dashboard/app.py
```

A **read-only** terminal with a neon/cyberpunk theme. It has **no order
entry, no approval controls and no execute mode** — trading happens in the
GitHub Actions pipeline, and this shows what the pipeline did. Four tabs:

| Tab | Shows |
| --- | --- |
| **Group** | All three members side by side, group equity/P&L/return, a combined equity trajectory, every traded stock rebased to 100, and combined daily P&L with the running total. No alpha section: alpha is per member. |
| **Shivika / Kanika / Sharvi** | That member's equity trajectory, daily P&L bars with best/worst run, their stocks' trajectory, their own alpha attribution, **their alpha history across every run**, the full order ledger, and the complete run history. |

Data comes from the committed CSV logs in `trading-logs/`, so the history is
always in sync with what the pipeline pushed. Alpha is recomputed from the
ledger on every load, so it reflects the most recent trade rather than a
stale snapshot.

Alpaca keys in the sidebar are **optional and read-only** — used only to
price open positions and draw price charts. They are held for the browser
session and never written to disk. Without them, tick "use synthetic prices"
and the charts still render from clearly-labelled fake data.

## Demo mode and the refusal to invent

```bash
python scripts/run_trading.py --demo        # or DEMO_MODE=true
```

Demo data is deterministic per symbol, carries `"source": "DEMO_SYNTHETIC"`,
and every synthetic headline is prefixed `[DEMO]` and says so in its own text.

**Without credentials and without demo mode the system refuses to fetch:**

```
MarketDataUnavailable: Refusing to produce OHLCV bars with no Alpaca
credentials. This system never invents prices or headlines. Set
ALPACA_API_KEY/ALPACA_SECRET_KEY, or set DEMO_MODE=true to use
clearly-labelled synthetic data.
```

Sentiment follows the same rule: a symbol with no headlines in the window is
reported as `NO_NEWS_DATA` with a neutral 0.0 score. No headline is ever
invented, and the news agent's instructions say so explicitly.

---

## Alpha attribution

`trading-logs/trades_<student>.csv` records one row per order with the signal
that caused it — composite score, conviction, engine, volatility scale, beta.
`scripts/alpha_report.py` joins those rows against later prices and writes
`analysis/alpha_report.md`, which CI commits back to the repository:

| Measure | Question it answers |
| --- | --- |
| **Excess return** (stock − SPY) | Did we beat the market on the names we picked? |
| **Jensen's alpha** (stock − β×SPY) | Did we beat it *after adjusting for the risk taken*? The stricter test, and the honest one for a deliberately high-beta book. |
| **Signal IC** | Does the composite score correlate with the realised return at all? |

It also breaks results down by conviction — if VERY_HIGH does not beat MEDIUM,
the conviction mechanism is decorative — and by engine, comparing the agent
crew against the deterministic fallback.

```bash
python scripts/alpha_report.py                  # real trades
python scripts/alpha_report.py --demo --include-demo   # preview the shape
```

**Read the caveat it prints.** Over a handful of trading days every one of
these numbers is dominated by noise. It is a framework for judging the
strategy, not yet a judgement of it.

### Per-member alpha history

A single alpha number at the end of the project cannot tell you whether it
was a trend or one lucky trade. So every run also appends one row per member
to `trading-logs/alpha_<student>.csv`, with `alpha_<student>.md` rendered
beside it as a GitHub table:

| | |
| --- | --- |
| **Written** | After every run — both daily runs, plus the end-of-day snapshot |
| **By** | `pipeline._record_alpha`, straight after the ledger is written, so the run's own orders are counted |
| **Holds** | Trades measured, open vs closed, mean return, excess, Jensen's alpha, win rate, IC, total P&L, benchmark, data source |
| **Committed** | By the `commit-logs` job, exactly like the daily logs |
| **Shown** | In the dashboard, on each member's own tab — Shivika, Kanika, Sharvi — as cards, a line chart of the three measures over time, and the full table |

There is deliberately **no group alpha section**: alpha is a per-member
measure, and averaging three different books hides exactly the differences
the report exists to show.

As with every other log, a failure to measure is reported on the run result
and never raised — a measurement problem must not take a trading run down.

### Recovering alpha for earlier runs

The trade ledger only started recording on 2026-10-25. Trades made before
that are still on record at Alpaca, so they can be recovered:

**On GitHub:** Actions → *Backfill alpha from Alpaca* → Run workflow. Leave
*dry run* ticked first to see what it would recover; run it again unticked to
write and commit the rows.

**Locally:**

```bash
python scripts/backfill_ledger.py --dry-run        # show, write nothing
python scripts/backfill_ledger.py                  # write the rows
python scripts/backfill_ledger.py --students student_1,student_3
```

It is safe to run repeatedly: an order already in the ledger is skipped by
its Alpaca order id.

**What comes back, and what does not.** Alpaca knows symbol, side, quantity,
average fill price and time — everything the return, the excess return and
Jensen's alpha need. Beta was never recorded either, but unlike the rest it
can be *measured* rather than guessed: 60-day rolling beta against SPY as of
the entry date, computed exactly as the live path computes it.

The composite score and conviction are gone. They lived only in that run's
`model-run/` artefact, which is gitignored and expires after 30 days. So:

> **The information coefficient cannot be computed for backfilled trades.**
> There is no score to correlate the return against. Those rows leave
> `composite` empty and are marked `engine=backfilled_from_alpaca`, and the
> alpha log carries the caveat in its note. An invented score would corrupt
> the one statistic the ledger exists to produce, so none is invented.

## Testing

```bash
pytest                      # 428 tests
pytest -m slow              # the live MCP server and the real-crew integration
```

| File | Covers |
| --- | --- |
| `test_indicators.py` | Hand calculations for Wilder RSI/ATR, ADX, MACD, bounds, no `pandas_ta` |
| `test_scoring.py` | 29 features, the MACD 60/40 ratio, the sustained-decline regression |
| `test_paper_guard.py` | 21 hostile URLs against both guards |
| `test_risk.py` | Sizing, every cap, exits-first, long-only, dedupe |
| `test_config.py` | Whitespace stripping, aggression lerp, the execution gate, the universe |
| `test_alpaca_client.py` | One batched request, refusal-to-invent, 429 + `Retry-After` |
| `test_mcp_server.py` | Strict-mode rules, every tool body, a live stdio round trip |
| `test_sentiment.py` | Lexicon, negation, the no-fabrication policy |
| `test_daily_log.py` | Columns, P&L arithmetic, the gap row, the Markdown mirror |
| `test_pipeline.py` | End-to-end runs, artefacts, the announced fallback |
| `test_crewai_integration.py` | A **real crew** against a local mock provider; payload inspection |

---

## Integration failures this build handles

Each was checked against the installed packages rather than taken on trust.

| # | Failure | How it is handled | Status here |
| --- | --- | --- | --- |
| 1a | Strict mode rejects a zero-parameter tool | Every tool takes ≥1 argument; `get_run_configuration` takes a documented dummy `scope` | Rule applied; `strict: true` confirmed on the wire |
| 1b | Strict mode forces every parameter into `required` | No tool has an optional parameter; tuning comes from config | **Confirmed present** — `ensure_all_properties_required` in crewai 1.15.28 |
| 2 | `cache_breakpoint` is never stripped on the LiteLLM path | `custom_openai=True` + explicit `base_url` forces the native OpenAI path | **Confirmed present** — `strip_cache_breakpoint` is defined in `crewai/llms/cache.py` and called nowhere. Verified absent from the payload |
| 3 | `crewai-tools` needs the `[mcp]` extra | `requirements.txt` pins `crewai-tools[mcp]`; the import error explains the fix | Documented and handled |
| 4 | `FastMCP` vs `MCPServer`; PyYAML RECORD error | The server imports either class; every install uses `--ignore-installed PyYAML` | `FastMCP` resolved from mcp 1.28.1 |
| 5 | Whitespace in keys and endpoints | `config.clean()` at every entry point — env, `.env`, the dashboard, and CI before `::add-mask::` | Tested |
| 6 | Free-tier token caps | `max_retries=8` on the SDK (honours `Retry-After`); `MAX_LLM_SYMBOLS` caps the crew | `max_retries=8` confirmed on the SDK client |
| 7 | Small models return empty content | `is_empty_response_error` detects CrewAI's message; the run falls back | Tested |

---

## What I verified, and what I could not

I built this in a sandbox whose egress policy blocks every external host.
`api.groq.com`, `ollama.com`, `api.openai.com`, `data.alpaca.markets` and
`paper-api.alpaca.markets` all fail at the proxy with `403 Forbidden`. So:

### Verified by actually running it

- **428 tests pass** on Python 3.12.
- **Indicators against hand calculations.** RSI(3) = 78.333333 and ATR(3) =
  2.333333 on worked examples, matching to 1e-6.
- **The MCP server started as a real subprocess** and all 10 tools called over
  stdio, including the error paths.
- **A real CrewAI crew ran end to end** against a local mock OpenAI-compatible
  endpoint that recorded every request body verbatim. From that capture:
  `strict: true` and `additionalProperties: false` on all 10 tools,
  `required == properties` on every one, **no `cache_breakpoint` anywhere in
  the payload**, and `Authorization: Bearer <key>` with no whitespace.
- **The OpenAI SDK client** resolves to `base_url = https://api.groq.com/openai/v1/`
  and `max_retries = 8` — checked on the constructed client object.
- **The dashboard** loaded in headless Chromium with no JS or Python errors; I
  clicked *Start analysis*, got `Run complete — engine: deterministic_rule_engine`,
  and the recommendations table and per-trade approval checkboxes rendered.
- **Both paper guards** against 21 hostile URLs, including the exact
  `https://evil.test/paper-api.alpaca.markets` case.
- **Every CI step run locally**, verbatim: the secret scan (which I also
  confirmed *catches* planted secrets rather than passing vacuously), the demo
  pipeline, the MCP step, the refusal path, and the log-merge dedupe.

### NOT verified — you should check these first

- **No real Alpaca call was ever made.** Batching, pagination, retry and order
  submission are tested against a recording fake session that replays Alpaca's
  documented response shapes. The field names (`t`/`o`/`h`/`l`/`c`/`v`,
  `next_page_token`, `last_equity`) come from my knowledge of the v2 API, which
  may be out of date. **Run `python scripts/run_trading.py --students student_1`
  in analyse mode with real keys before trusting a single number.**
- **No real LLM call was ever made.** Everything provider-facing was validated
  against a local mock. Run `python scripts/test_llm.py` with your key as the
  first thing you do; it takes about a minute and will tell you precisely which
  of the four stages fails.
- **Ollama Cloud specifics** — that cloud model ids are plain on
  `https://ollama.com/v1` and `-cloud`-suffixed on the local daemon, and that
  they are absent from `/api/tags` — is implemented from the brief's
  description. I could not confirm it against the live service.
- **The GitHub Actions workflows have never run on GitHub.** The YAML parses
  and every shell step runs locally, but `actions/upload-artifact@v4` ordering,
  the `inputs.*` fallbacks on a `schedule` event, and the push permissions are
  unexercised. Expect to iterate on the first run.
- **The high-beta list is representative, not index-verified** — see
  [The universe](#the-universe).
- **No backtest.** Nothing here establishes that the strategy makes money. The
  ensemble is checked for *sanity* (a crash reads SELL, an uptrend reads BUY),
  not for edge. A 15–20 day paper window cannot distinguish skill from luck.
