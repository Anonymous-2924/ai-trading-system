# AI-Powered Algorithmic Paper Trading System

### Project Progress Report

**Submitted to:** [Professor's name]
**Date:** 26 October 2026
**Repository:** https://github.com/Anonymous-2924/ai-trading-system

**Team**

| Role | Name | Roll No. |
|---|---|---|
| Student 1 | Shivika Khanna | 065049 |
| Student 2 | Kanika Mittal | 065030 |
| Student 3 | Sharvi Sood | 065047 |

---

## 1. Introduction

This report covers the algorithmic paper trading system we built for this assignment. The system trades US equities on Alpaca's paper trading platform, where each of us was given a simulated account of $100,000. It runs by itself on a schedule, decides what to buy and sell using a mix of technical analysis and AI agents, places the trades, and keeps a daily record of how each of our portfolios is doing.

We have been trading since 17 October. This report explains what we built, how it works, what the results look like so far, and what problems we ran into along the way.

We want to say at the start that we have deliberately included the things that went wrong as well as the things that worked. Several of our bugs were only found because the system was running live, and we think how we found and fixed them is one of the more useful parts of this project.

## 2. Objectives

What we set out to do:

1. Build a system that analyses a fixed basket of stocks every trading day and produces a clear buy, sell or hold decision for each one.
2. Use a wide range of technical indicators rather than relying on any single signal.
3. Add AI agents on top of the technical analysis so the decisions get a layer of reasoning, not just arithmetic.
4. Make sure the system keeps working when the AI is unavailable, since we are using free services that fail often.
5. Manage risk properly: position sizing, stop losses, exposure limits.
6. Run everything automatically, and keep a permanent daily record of profit and loss for each team member.
7. Take real risks with position sizing, as the brief required, rather than defaulting to very cautious textbook limits.

## 3. Portfolio Allocation

Each of us has 14 stocks, 42 across the group. The brief required at least 30% of each portfolio to be in high-beta growth stocks (stocks that move much more than the overall market), with the rest diversified. We allocated 5 high-beta and 9 diversified names each, which works out to about 36%.

| Member | High-beta (5) | Diversified (9) |
|---|---|---|
| Shivika Khanna | TSLA, NVDA, PLTR, COIN, SMCI | AAPL, MSFT, JNJ, JPM, XOM, PG, V, CAT, UNH |
| Kanika Mittal | AMD, MRNA, ENPH, RIVN, DKNG | GOOGL, AMZN, KO, BAC, CVX, HD, MRK, HON, COST |
| Sharvi Sood | MARA, AFRM, UPST, CCL, ON | META, ORCL, PEP, WFC, LMT, DIS, ABBV, NKE, WMT |

We picked the high-beta names to be representative of the kind of stock in the S&P High Beta Index — large US companies whose share prices swing a lot more than the market average. We should be honest that we did not check these against the official published index membership, which is updated every quarter. If exact index membership matters for marking, this is easy to correct, because the stock lists live in a configuration file and nothing is hard-coded in the program.

## 4. How the System Works

Every run follows the same six steps for each team member.

**Step 1 — Get the data.** The system asks Alpaca for about 400 days of daily price history for all 14 stocks. Importantly, this is a single request covering every stock, not 14 separate requests. It also pulls recent news headlines for those stocks in the same way.

**Step 2 — Measure the stocks.** It calculates 29 different indicators for each stock. These are grouped into five categories, so that no single type of signal dominates:

| Category | What it measures | Indicators used |
|---|---|---|
| Trend | Which direction the stock is moving | EMA 20/50/200, ADX, MACD line |
| Momentum | How fast it is moving, and how it compares with the market | RSI, MACD histogram, ROC, TSI, **relative strength vs SPY and QQQ** |
| Volume | Whether real buying or selling is behind the move | CMF, OBV, MFI, **relative volume** |
| Volatility | How much the stock swings, and where it sits in today's range | NATR, Bollinger width and %B, Donchian, **opening-range position** |
| Statistics | How unusual today is compared with the stock's own history | Z-score, 5/20/60-day returns, skew, **beta** |

The five highlighted features were added after reviewing a set of intraday
trading guidelines. We will be honest that those guidelines assume
minute-by-minute monitoring, which a system running twice a day cannot do, so
we adopted the parts that survive translation to our timeframes and did not
attempt the parts that do not. Relative strength is the most important
addition: without it, every other indicator will happily buy a stock that is
up 3% on a day when the market is up 4%, which is underperformance dressed up
as a gain.

**Step 3 — Score them.** Each of the 29 measurements is converted into a score between −1 (very bearish) and +1 (very bullish). Scores are averaged within their category, and the five categories are then combined along with a news sentiment score using fixed weights:

- Trend 28%, Momentum 24%, Volume 14%, Volatility 12%, Statistics 12%, News sentiment 10%

This produces one final number per stock. If it is above +0.18 the system buys, below −0.18 it sells, otherwise it holds. How far past the threshold the score goes decides the conviction level (medium, high or very high), which in turn decides how much money to put in.

**Step 4 — AI review.** Six AI agents then look at the same information and can change the decision. They work in a chain: market data, then technical analysis, then quantitative analysis, then news and sentiment, then risk management, then a final decision agent that produces the answer in a structured format.

**Step 5 — Size and place the trades.** The risk module works out how many shares to buy, sets a stop loss and a profit target for each position, checks the decisions against exposure limits, and then submits the orders to Alpaca.

**Step 6 — Record everything.** Each team member's equity, profit and loss, positions and signal counts are written to a log file and saved permanently.

### A worked example

To make this concrete, here is an actual decision the system produced for COIN, taken from our output:

```
Price: $145.89

  8.2% above its 20-day moving average      →  +0.99
  17.4% above its 200-day moving average    →  +0.82
  MACD line well above zero                 →  +0.99
  RSI at 60.5 (strong, not overbought)      →  +0.53
  +20.4% over the last 12 days              →  +0.99
  Money flow slightly negative              →  −0.32
  Near the top of its Bollinger band        →  +0.74

  Trend +0.79 | Momentum +0.74 | Volume −0.25
  Volatility +0.57 | Statistics +0.71 | Sentiment 0.00

  Final score: +0.52  →  BUY, conviction HIGH
```

The volume category voted against buying, and the system bought anyway because the other four categories outweighed it. This is the whole point of combining signals rather than relying on any one of them.

## 5. Technical Implementation

### 5.1 Indicators

We wrote all 29 indicators ourselves using pandas and numpy, rather than importing a technical analysis library. We had to do this: the most popular library for this, `pandas_ta`, is broken with current versions of numpy because it uses `numpy.NaN`, which was removed in numpy version 2.0. Writing them ourselves also meant we understood exactly what each one was doing.

Three of the indicators — RSI, ATR and ADX — use a specific smoothing method developed by Welles Wilder. There is a common mistake in coding this where people use the built-in exponential moving average function, which starts the calculation from a single value instead of an average of the first several. The results then disagree with every charting platform for hundreds of data points.

We implemented it correctly and checked it by hand. For a seven-day price series of 10, 11, 12, 11, 13, 12, 14 we worked out RSI with a period of 3 manually:

```
gains  = 1, 1, 0, 2, 0, 2
losses = 0, 0, 1, 0, 1, 0
seed average gain = (1+1+0)/3 = 0.666667
seed average loss = (0+0+1)/3 = 0.333333
after smoothing:  avg gain = 1.160494, avg loss = 0.320988
RS  = 3.615385
RSI = 100 − 100/(1+3.615385) = 78.333333
```

Our code returns 78.333333 for the same input. We did the same for ATR. Both checks are saved as automated tests so they run every time we change anything.

### 5.2 The MACD problem

This is worth explaining separately because it is the one place where a naive implementation gives badly wrong answers.

MACD produces two numbers: a line, and a histogram (the gap between that line and its own average). Most simple strategies just look at whether the histogram is positive. The problem is that during a long decline, the histogram turns positive on every small bounce. A stock that has fallen 70% will look bullish again and again.

We treat the two numbers as saying different things. The MACD line's position relative to zero is a statement about trend. The histogram is a statement about momentum. We weight them 60% to the line and 40% to the histogram.

We tested this on a simulated stock that falls 68% and then has a small bounce at the end:

```
MACD line     = −0.390  →  score −0.25  (bearish trend)
MACD histogram = +0.464  →  score +0.65  (bullish momentum)
Final decision: HOLD (score −0.08), not BUY
```

The histogram on its own says buy. Our system does not. The same decline without the bounce gives a clear SELL at −0.56. This is saved as a permanent test so we cannot accidentally break it later.

### 5.3 AI agents and the MCP server

The AI layer uses CrewAI with six agents. For the agents to actually do anything useful they need tools they can call, and the standard way of providing these is the Model Context Protocol (MCP).

The brief specified that we build our own MCP server rather than using Alpaca's hosted one, so we wrote one. It runs as a local program and provides ten tools: fetching the stock list, getting account details, getting positions, fetching price data for all stocks at once, computing indicators, getting news sentiment, running the rule engine, sizing a position, placing a paper order, and reading the run configuration.

Two constraints shaped how we wrote these tools, and both caused us real problems before we understood them:

1. CrewAI describes tools to the AI model in something called "strict mode". In this mode, a tool with no parameters at all is rejected. One of our tools genuinely needs no input, so we gave it a single dummy parameter documented as "always pass 'all'".

2. Strict mode also copies every parameter into the required list, even ones with default values. This means optional parameters are impossible — the model will be forced to supply a value and will invent one. So none of our tools has an optional parameter, and all tuning values come from the configuration file instead.

We confirmed both of these by reading the installed CrewAI source code rather than guessing.

### 5.4 The fallback engine

This is the part of the design we are most pleased with.

The entire decision process — all 29 indicators, the scoring, the thresholds — works without any AI at all. It is pure arithmetic and always gives the same answer for the same input. The AI agents sit on top of it as an interpretation layer.

The reason this matters is that free AI services fail constantly. They hit rate limits, they time out, and small models sometimes get stuck in a loop and return an empty answer. If our system depended on the AI, a bad day would mean no trading at all and a gap in our records.

Instead, when the AI fails the arithmetic takes over and the day continues normally. This has already happened to us in a live run. From Sharvi's log on 17 October:

```
LLM path unavailable, using the deterministic rule engine: the model
returned empty content (CrewAI: 'Invalid response from LLM call -
None or empty'). Small models loop over a tool and then return nothing.
Falling back to the deterministic rule engine.
```

She still received 8 buy, 3 sell and 3 hold decisions that day.

Equally important is that the fallback is never silent. It is recorded in three separate places: the run log, the console output, and a column in the daily CSV file showing which engine made that day's decisions. Anyone reading our records can tell exactly which days were AI-driven and which were not. A system that quietly degrades without telling you is worse than one that fails loudly.

### 5.5 Risk management

Deciding what to buy is only half the problem. The risk module handles how much, and when to get out.

**Position sizing.** Each position is a percentage of the account, multiplied by the conviction level. Low conviction opens no position at all.

**Stops and targets based on ATR, attached to the order.** ATR measures how much a stock typically moves in a day. We set the stop loss at about 2.5 times ATR below the entry price and the profit target at about 5 times ATR above it. Using ATR rather than a fixed percentage means a volatile stock gets a proportionally wider stop and is not thrown out by its own ordinary movement. The roughly 1:2 ratio between stop and target means the strategy can be right less than half the time and still make money.

These are now sent to Alpaca as bracket orders, which means the broker holds the stop and the target itself. Until we fixed this, the stop was calculated and written into our records but never actually submitted, so the only real exit was the next scheduled run noticing that the score had fallen. Between runs the position was unprotected, and an overnight gap had nothing standing in its way. Alpaca does not accept fractional quantities on bracket orders, so a bracketed entry is rounded down to whole shares, and anything that rounds below one share is skipped rather than sent without protection.

**Position size scaled by volatility.** Previously every position was the same percentage of the account whether it was Procter & Gamble or a crypto miner. Since a stock that swings 9% a day carries roughly four times the risk of one that swings 2%, this meant the jumpiest names quietly dominated the portfolio's risk even though they took up the same amount of money. Position size is now divided by the stock's own volatility relative to a reference level, so each holding contributes roughly equal risk rather than equal dollars. On a $100,000 account at high conviction, a very calm stock is now allocated about $15,750 while an extremely volatile one gets about $3,900.

**Limits.** No single stock above about 18% of the account, no single sector above 40%, total exposure capped at about 1.16 times equity, and a minimum cash buffer that is always preserved.

**Exits before entries.** The system plans all its sells first, then adds that money to what is available for the buys in the same run. Without this, money freed up by a sale would sit idle for a day.

**Long only.** If the system decides to sell a stock we do not own, that is simply no action. It never opens a short position. Shorting carries unlimited loss potential and we deliberately excluded it. This rule is enforced in two separate places in the code.

### 5.6 Aggression setting

The brief was explicit that a cautious approach was not acceptable, so we made the risk appetite a single adjustable setting from 0 to 1 and set it at 0.75. This produces noticeably larger positions than standard retail advice:

| Parameter | Timid (0.0) | Ours (0.75) | Maximum (1.0) | Typical textbook advice |
|---|---|---|---|---|
| Position size | 3% | 11.3% | 14% | 1–2% |
| Maximum positions | 8 | 13 | 15 | 10–20 |
| Total exposure | 0.60× | 1.16× | 1.35× | 1.0× or less |
| Single stock limit | 8% | 18.5% | 22% | 5% |
| Sector limit | 25% | 40% | 45% | 20–25% |
| Stop loss (× ATR) | 1.5 | 2.47 | 2.8 | 1.5–2 |
| Profit target (× ATR) | 2.5 | 5.12 | 6.0 | 2–3 |

Our reasoning for the main choices:

- With only 14 stocks and a trading window of under a month, a portfolio sized at 1% per trade cannot express a view. A 20% gain on a 1% position moves the account by 0.2%, which would be indistinguishable from noise.
- We allowed a 40% sector cap rather than the usual 20% because our high-beta allocation is concentrated in technology by nature. A tighter cap would have made the required 30% high-beta allocation impossible to fill.
- We used wide stops because high-beta stocks have large daily ranges. A tight stop on a stock that routinely moves 6% in a day gets triggered by normal noise rather than by a genuine reversal.

We should be clear that these settings would not be appropriate for real money without a great deal more thought about how much loss we could tolerate.

### 5.7 Safety: paper trading only

Since the system places orders automatically, we took care that it cannot possibly reach a real-money account. There are two independent checks.

The first parses the web address and requires the hostname to be exactly `paper-api.alpaca.markets` over HTTPS. A simple text search for that name is not enough, which is a genuine security issue rather than a theoretical one. An address like `https://evil.test/paper-api.alpaca.markets` contains the correct text but would send every order to someone else's server. Our check rejects that, along with similar tricks such as `paper-api.alpaca.markets.evil.test` and `paper-api.alpaca.markets@evil.test`. We wrote tests covering 21 such hostile addresses.

The second check runs immediately before every single order is submitted. It independently re-examines the address actually about to be used, against its own separate list. The two checks share no code, so a mistake in one does not disable the other. We tested that an address changed after the first check is still caught by the second.

API keys are never stored in the code. They are kept as GitHub encrypted secrets, and our automated tests fail the build if anything resembling a key is ever committed to the repository.

### 5.8 Automation

Everything runs on GitHub Actions without anyone starting it. There are two scheduled runs each weekday:

| Cron (UTC) | Acts at (US Eastern) | Purpose |
|---|---|---|
| 14:00 | 10:05, 35 min after the open | Morning trading run |
| 19:25 | 15:30, 30 min before the close | Afternoon trading run |
| 21:30 | after the close | Records closing equity only; cannot trade |

The crons fire early and the job then waits for its real target. This is
necessary for two reasons. First, the US close moves by an hour when the
clocks change on 1 November, so "30 minutes before the close" is a different
UTC time in summer and winter. Second, GitHub's scheduler is only best-effort
and delayed one of our runs by more than three hours. The job asks Alpaca's
calendar when the session actually opens and closes, waits for the right
moment, and if the delay has been so long that the window has passed it skips
the run rather than trading at the wrong time. Both runs sit inside the busy
opening and closing hours and avoid the quiet midday period.

The trading run is timed to fall inside US market hours so that orders fill in the same session rather than queuing overnight. We chose times that stay on the correct side of the opening and closing bells in both US daylight and standard time, since the US clocks change in early November during our trading period. We also placed the trading run early in the session rather than late, because GitHub's scheduler is only best-effort and delayed one of our runs by more than three hours; starting at 14:45 UTC leaves about five hours of margin before the market closes.

The three accounts run one at a time rather than together. Each uses its own Alpaca keys, and running them simultaneously would exhaust the free AI quota immediately.

The clever part is how the records survive. A cloud server is wiped after each job, so anything written there would normally be lost. After every run, the system commits the updated profit and loss files back into our GitHub repository. This means the full history is stored in version control, timestamped, with a complete audit trail of every change. A separate job handles this after all three accounts have finished, so they cannot interfere with each other.

### 5.9 Measuring whether any of it works

Our daily log records where each account stands, but it cannot say whether a particular trade was a good one, or whether the indicators predict anything at all, because it only stores daily totals.

We therefore added a trade ledger that records one row for every order, carrying the signal that caused it: the composite score, the conviction level, which engine decided, and the volatility scaling used. A separate analysis script joins those rows against later prices and produces three measures:

- **Excess return** — the stock's return minus the market's over the same period. Did we beat the market on the names we chose?
- **Jensen's alpha** — the stock's return minus its beta multiplied by the market's return. Did we beat the market after adjusting for the extra risk we took? This is the stricter and more honest test for a portfolio that is deliberately high-beta, because a stock that rises 3% while the market rises 4% has actually underperformed what its risk should have paid.
- **Information coefficient** — the correlation between our composite score at entry and the return that followed. Do the indicators predict anything?

It also breaks the results down by conviction level. If our VERY_HIGH conviction trades do not outperform our MEDIUM ones, then the conviction mechanism is decorative and we should say so.

We want to be clear that over a handful of trading days all of these numbers are dominated by noise. This is a framework for judging the strategy rather than a judgement of it, and the report says so in its own output.

A single alpha figure at the end of the project would also be misleading, because it could not tell us whether a good number was a genuine trend or one lucky trade. So after every run the system appends one row per member to a personal alpha log, recording all three measures as they stood at that moment. Each of us has our own file, committed to the repository alongside the daily log, and the measures can therefore be watched moving rather than read once at the end.

We deliberately did not produce a combined alpha figure for the group. Alpha is a per-portfolio measure, and averaging three different sets of holdings would hide exactly the differences between us that the analysis exists to reveal.

One honest limitation is worth recording. The trade ledger was added part-way through the project, so the trades made in the first week were not captured with the score that caused them. We wrote a recovery script that reads our order history back from Alpaca and rebuilds those rows, which restores enough to compute the return, the excess return and Jensen's alpha for every trade we have ever made. Beta is not stored by Alpaca either, but unlike the rest it can be measured from price history rather than guessed, so the script computes it the same way the live system does.

The composite score, however, is genuinely gone for those early trades: it existed only in the run's working files, which are not kept permanently. This means the information coefficient cannot be calculated for the recovered trades. We considered estimating a score for them and decided against it, because the information coefficient is precisely the correlation between that score and the outcome — inventing the score would have corrupted the one statistic the ledger exists to produce. Those rows are marked as recovered, their score field is left empty rather than filled with a zero, and the alpha log states the limitation in its own notes.

### 5.10 Dashboard

We also built a Streamlit dashboard, which presents the results in a dark, neon-lit terminal style. It is deliberately **read-only**: it has no order entry, no execute mode and no ability to place a trade. All trading happens in the automated GitHub Actions pipeline, and the dashboard's only job is to show what that pipeline did. Alpaca keys may be entered to price open positions and draw live price charts, and are held for the browser session only, never written to disk.

It has four tabs. The first shows the group: all three accounts side by side, combined equity, the trajectory of every stock we hold, and combined daily profit and loss with a running total. The remaining three — one each for Shivika, Kanika and Sharvi — show that member's equity trajectory, their daily profit and loss with their best and worst days, the price trajectory of their own stocks, their current alpha attribution, their alpha history across every run that has taken place, their complete order ledger, and their full run history.

## 6. Results So Far

Trading began on 17 October. The figures below are as of 26 October, covering five completed trading days.

| Member | Starting | Current equity | Profit / Loss | Return | Positions | Days logged |
|---|---|---|---|---|---|---|
| Shivika Khanna | $100,000 | $100,571.87 | +$571.87 | +0.57% | 8 | 7 |
| Kanika Mittal | $100,000 | $98,801.11 | −$1,198.89 | −1.20% | 10 | 6 |
| Sharvi Sood | $100,000 | $100,135.28 | +$135.28 | +0.14% | 5 | 2 |
| **Group** | **$300,000** | **$299,508.26** | **−$491.74** | **−0.16%** | **23** | |

The group as a whole is close to flat, slightly below where it started. Shivika's portfolio is up about half a percent, Kanika's is down just over one percent, and Sharvi's is marginally up.

Kanika's account was up $1,720 on 22 October and then lost $2,813 in a single day, which is what moved it into negative territory. This is the aggressive position sizing working in the direction we did not want. With roughly 11% of the account in each position, a bad day in two or three holdings produces a swing of this size. We expected this volatility when we chose the settings; seeing it actually happen is a useful reminder of what the aggression setting means in practice.

Two honest caveats about these numbers:

Sharvi's account has only two logged days compared with seven and six for the others, so her figure of $100,135 is from 20 October and is stale. Her actual current position is almost certainly different. This was a logging problem rather than a trading problem — her positions and orders are real and visible in her Alpaca account. We have now found and fixed the cause, which is described in section 7; her log should fill in from the next scheduled run onwards.

More importantly, four trading days tells us essentially nothing about whether the strategy is any good. The differences between the three of us at this point are much more likely to reflect which stocks happened to be in whose portfolio than any difference in skill. We would not draw conclusions about performance from this sample.

## 7. Problems We Encountered

We think this section is worth including in full, because several of these were only found by running the system live.

**The ON Semiconductor bug.** This was the most interesting one. After our first live run, Sharvi's log contained the line `TRUE: order failed`. There is no stock with the ticker symbol TRUE.

The cause was in the YAML configuration format we use for the stock lists. YAML version 1.1 treats a bare `ON` as the boolean value true, in the same way as `YES` and `NO`. Sharvi's high-beta list contained `ON` for ON Semiconductor, which was read as the value true and then converted to the text "TRUE". The system was trying to buy a stock that does not exist.

It had two effects. Sharvi was actually trading 13 stocks rather than 14, and because the sector lookup was also affected, ON was escaping the technology sector exposure limit.

We fixed it by quoting every stock symbol in the configuration file, and by making the program refuse outright to accept a boolean where a stock symbol should be, with an error message explaining how to fix it. We added eight tests, including one that checks every symbol in the configuration file reads as text.

We would not have found this without running live. All our tests passed beforehand.

**One team member silently stopped being logged.** This was the most serious problem we found, and the hardest to see, because nothing reported an error.

Sharvi's log stopped updating after 20 October while the other two carried on. Her trades were still happening and were visible in her Alpaca account, but no daily record was being written.

The cause turned out to be a chain of three things. The three accounts run one after another in a fixed order, sharing a single free AI quota. Shivika runs first and uses most of it. By the time Sharvi's turn came, every AI request was being rate-limited, and our retry settings — eight attempts, each allowed up to 180 seconds — meant her run could spend well over half an hour simply waiting. The automation job has its own 40-minute limit, so GitHub killed the job before it ever reached the step that writes the log.

We had designed the system so that a run which cannot read the account still writes a row, precisely so gaps would be visible. That protection was useless here, because the process was killed outright rather than failing gracefully.

We fixed it in three ways. First, we added a hard time budget for the AI stage — if it has not finished within seven minutes, it is abandoned and the deterministic engine takes over, so a run can no longer overrun its job. Second, we reduced the number of stocks sent to the AI from 12 to 8 per person, which brings the whole team inside the free quota instead of starving whoever goes last. Third, we gave each scheduled run its own queue so a delayed trading run no longer blocks the evening snapshot behind it.

We verified the fix by simulating a crew that hangs indefinitely and confirming that the run still completed, still fell back with an announcement, and still wrote its log row.

**Market closed on the first run.** Our first run was on a Saturday. Alpaca accepted all 16 orders across the three accounts but they stayed queued until Monday's open. For a while we thought the system was broken because nothing appeared to be happening. It was working correctly; we were just looking at it on a non-trading day.

**Looking at the wrong Alpaca account.** Related to the above, one of us checked an Alpaca dashboard that showed no orders at all while another showed them correctly. The orders had gone to a different paper account than the one open in the browser. To settle questions like this quickly we wrote a diagnostic tool that prints, for each set of keys, the exact Alpaca account number those keys belong to along with every order on file and its status. It is read-only and places no orders.

**Scheduled runs arriving late.** GitHub's scheduler is best-effort and can be significantly delayed under load. Our 19:30 run on 20 October actually started at 22:58, by which time the US market had closed, so those orders queued overnight instead of filling the same day. We are planning to move the trading run earlier to leave more headroom before the market closes.

**The daily log table not displaying.** Our run summary page was showing the table heading but no rows. The data was present in the file all along; the preview was cut off at exactly the line between the table heading and the separator line that Markdown needs to render a table. A display bug rather than a data loss, but it took some time to work out.

**Missing dependency in a workflow.** When writing the diagnostic tool's automated job, we listed its dependencies by hand to keep it fast and forgot pandas, so it crashed immediately. We had checked the configuration file was valid but had not actually run it. We now have a step that checks the program can start before the real work begins.

**Student selection not accepting "all".** The diagnostic reported "0 of 0 accounts read successfully" and gave no reason. The students field had been given the value `all`, which our main trading workflow accepts, but the diagnostic only accepted a blank field. It selected nothing and then reported success over an empty list. We fixed the input handling and also made the configuration loader refuse to load silently when the configuration file is missing, which was a related trap.

**AI running out of quota.** Free AI services have both per-session and weekly limits. Our crew uses roughly 28 requests per person per run, so about 84 per run across the three accounts. We added a configurable cap on how many stocks are sent to the AI, and the fallback engine handles whatever is left over.

## 8. Testing

We have 462 automated tests covering the indicators (including the hand calculations), the scoring logic, the MACD behaviour on declining stocks, the paper trading safety checks against 21 hostile addresses, the risk limits, the configuration loading, the MCP server tools, the sentiment scoring, the daily logging, the per-member alpha log and the recovery of earlier trades, and the full pipeline from end to end.

Beyond the unit tests we also:

- Started the MCP server as a real program and called all ten of its tools over the actual connection.
- Ran a complete six-agent crew against a local stub server that recorded every request, so we could inspect exactly what was being sent rather than assuming.
- Loaded the dashboard in an automated browser, clicked through a full run, and confirmed the recommendations table and trade approval screens worked.
- Ran every step of our automated workflows locally before relying on them, including confirming that our secret scanner actually detects deliberately planted fake credentials rather than passing by default.

## 9. Limitations

We want to be clear about what this project does and does not demonstrate.

**We have not shown the strategy is profitable.** We have tested that the system behaves sensibly — a crashing stock produces a sell, a rising stock produces a buy, a flat stock produces a hold. We have not backtested it over historical data, and four trading days cannot distinguish skill from luck. Nothing in our results should be read as evidence that this approach beats the market.

**The high-beta stock list is representative rather than verified.** As noted in section 3, we have not checked it against the official index membership.

**One account has incomplete logging.** Sharvi's log has gaps on days where the job did not reach the logging stage. Her trading is unaffected but her recorded history is thinner than the others'.

**The sentiment analysis is simple.** It scores news headlines using a word list rather than a language model. We chose this deliberately so it keeps working when the AI is unavailable and so every score can be traced back to the words that produced it, but it is less sophisticated than it could be.

**We are dependent on free service tiers** for both market data and AI, which limits how often we can run and how many stocks the AI can review.

## 10. Conclusion

The system is complete and running without manual intervention. It analyses 42 stocks across the three of us using 29 indicators each, combines them into clear decisions, places trades automatically, and keeps a permanent audit trail of every run.

The design decision we would most like to highlight is the deterministic fallback. Because every decision can be made without AI, a failure of the AI service degrades the system rather than stopping it, and the degradation is always visible in the records. This has already saved runs for us in practice.

The results so far are close to flat overall, and we do not think four days of data supports any conclusion about the strategy's quality. What we can say with confidence is that the system works correctly, fails safely, and that every decision it has made can be traced and explained.

We are happy to demonstrate the system running, or to walk through any part of the code, at your convenience.

---

## Appendix A — Repository Structure

```
src/trading_system/
    indicators.py     all 29 indicators, written in pandas/numpy
    features.py       turns price data into the 29 measurements
    scoring.py        the weighted ensemble and buy/sell/hold decision
    sentiment.py      news headline scoring
    rule_engine.py    the deterministic decision engine
    agents.py         the six CrewAI agents
    mcp_server.py     our MCP server and its ten tools
    mcp_client.py     connects the server to CrewAI
    llm.py            AI provider selection and health checks
    alpaca_client.py  market data, news, account and orders
    paper_guard.py    the two paper-trading safety checks
    risk.py           sizing, limits, stops, order management
    daily_log.py      the per-member profit and loss records
    pipeline.py       ties everything together
    config.py         configuration loading

scripts/              command line tools
dashboard/app.py      the Streamlit dashboard
config/config.yaml    stock lists, weights and all settings
tests/                272 automated tests
trading-logs/         our daily profit and loss records
.github/workflows/    the automation
```

## Appendix B — Running the System

```bash
git clone -b claude/ai-paper-trading-system-cd20m9 \
  https://github.com/Anonymous-2924/ai-trading-system.git
cd ai-trading-system
python3 -m venv .venv && source .venv/bin/activate
pip install --ignore-installed PyYAML -r requirements.txt
```

Demonstration using clearly labelled simulated data, requiring no credentials:

```bash
python scripts/run_trading.py --demo --no-llm
```

Run the test suite:

```bash
python -m pytest
```

Start the dashboard:

```bash
streamlit run dashboard/app.py
```

Check whether a given AI model can drive the system (takes about one minute):

```bash
python scripts/test_llm.py
```

The daily profit and loss records are in the `trading-logs` folder of the repository, where the `.md` files display as formatted tables.
