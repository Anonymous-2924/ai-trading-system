"""Mission control: a read-only view of the team's paper-trading results.

This dashboard CANNOT TRADE. It has no order entry, no approval controls and
no execute mode — it reads what the pipeline has already done, from two
sources:

* the committed CSV logs in ``trading-logs/`` (daily equity, and the
  per-order ledger), which are pushed back to the repository after every run;
* optionally, the Alpaca paper account itself, for live positions and order
  status. Those credentials are read-only as far as this app is concerned:
  nothing here ever calls ``submit_order``.

Four tabs — the group, then one per member.

Run with:
    streamlit run dashboard/app.py
"""

from __future__ import annotations

import math
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional

import altair as alt
import pandas as pd
import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from trading_system import alpha as alpha_lib  # noqa: E402
from trading_system import alpha_log, daily_log, price_log, trade_ledger  # noqa: E402
from trading_system.alpaca_client import (  # noqa: E402
    AlpacaError,
    MarketDataUnavailable,
    build_client,
)
from trading_system.config import clean, load_config  # noqa: E402
from trading_system.paper_guard import PaperTradingViolation  # noqa: E402

st.set_page_config(
    page_title="Neon Desk — AI Paper Trading",
    page_icon="◢",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ---------------------------------------------------------------------------
# Palette. Deep indigo ground, cyan and magenta light.
# ---------------------------------------------------------------------------
INK = "#07040f"
PANEL = "#120d2b"
EDGE = "#2a1f5c"
CYAN = "#00e5ff"
MAGENTA = "#ff2d95"
VIOLET = "#a855f7"
LIME = "#39ff8b"
TEXT = "#e8e3ff"
MUTED = "#8d84c4"

st.markdown(
    f"""
<style>
  @import url('https://fonts.googleapis.com/css2?family=Orbitron:wght@500;700;900&family=Rajdhani:wght@400;600;700&display=swap');

  .stApp {{
    background:
      radial-gradient(1100px 620px at 12% -8%, rgba(168,85,247,.26), transparent 60%),
      radial-gradient(900px 520px at 88% 0%, rgba(255,45,149,.18), transparent 58%),
      radial-gradient(1000px 700px at 50% 108%, rgba(0,229,255,.14), transparent 60%),
      {INK};
    color: {TEXT};
    font-family: 'Rajdhani', system-ui, sans-serif;
  }}
  h1, h2, h3 {{ font-family: 'Orbitron', system-ui, sans-serif !important; letter-spacing: .5px; }}
  h1 {{
    color: #fff !important;
    text-shadow: 0 0 10px rgba(0,229,255,.75), 0 0 34px rgba(168,85,247,.55);
  }}
  h2, h3 {{ color: {CYAN} !important; text-shadow: 0 0 12px rgba(0,229,255,.45); }}
  p, label, span, div {{ color: {TEXT}; }}

  section[data-testid="stSidebar"] {{
    background: linear-gradient(180deg, #0c0820 0%, #0a0618 100%);
    border-right: 1px solid {EDGE};
  }}

  /* Tab bar — the main navigation */
  .stTabs [data-baseweb="tab-list"] {{
    gap: 6px; border-bottom: 1px solid {EDGE}; padding-bottom: 2px;
  }}
  .stTabs [data-baseweb="tab"] {{
    background: rgba(18,13,43,.75);
    border: 1px solid {EDGE};
    border-bottom: none;
    border-radius: 10px 10px 0 0;
    padding: 10px 22px;
    font-family: 'Orbitron', sans-serif;
    font-size: .82rem;
    letter-spacing: 1.4px;
    color: {MUTED};
  }}
  .stTabs [aria-selected="true"] {{
    background: linear-gradient(180deg, rgba(0,229,255,.20), rgba(168,85,247,.12));
    color: #fff !important;
    border-color: {CYAN};
    box-shadow: 0 -2px 20px rgba(0,229,255,.45), inset 0 1px 0 rgba(0,229,255,.6);
  }}

  /* Metric cards */
  .neon-card {{
    background: linear-gradient(160deg, rgba(18,13,43,.95), rgba(10,6,24,.95));
    border: 1px solid {EDGE};
    border-radius: 14px;
    padding: 16px 18px;
    position: relative;
    overflow: hidden;
    box-shadow: 0 0 22px rgba(0,229,255,.10), inset 0 1px 0 rgba(255,255,255,.05);
  }}
  .neon-card::before {{
    content: ""; position: absolute; left: 0; top: 0; height: 2px; width: 100%;
    background: linear-gradient(90deg, {CYAN}, {VIOLET}, {MAGENTA});
    box-shadow: 0 0 14px rgba(0,229,255,.85);
  }}
  .neon-label {{
    font-family: 'Orbitron', sans-serif; font-size: .64rem; letter-spacing: 2px;
    color: {MUTED}; text-transform: uppercase; margin-bottom: 6px;
  }}
  .neon-value {{
    font-family: 'Orbitron', sans-serif; font-size: 1.62rem; font-weight: 700;
    color: #fff; text-shadow: 0 0 16px rgba(0,229,255,.6); line-height: 1.15;
  }}
  .neon-sub {{ font-size: .86rem; margin-top: 4px; }}
  .up   {{ color: {LIME};    text-shadow: 0 0 12px rgba(57,255,139,.65); }}
  .down {{ color: {MAGENTA}; text-shadow: 0 0 12px rgba(255,45,149,.65); }}
  .flat {{ color: {MUTED}; }}

  .pill {{
    display: inline-block; padding: 3px 11px; border-radius: 999px;
    font-family: 'Orbitron', sans-serif; font-size: .6rem; letter-spacing: 1.6px;
    border: 1px solid {CYAN}; color: {CYAN};
    background: rgba(0,229,255,.08); box-shadow: 0 0 12px rgba(0,229,255,.28);
  }}
  .pill-warn {{ border-color: {MAGENTA}; color: {MAGENTA}; background: rgba(255,45,149,.08);
                box-shadow: 0 0 12px rgba(255,45,149,.3); }}

  .rule {{
    height: 1px; margin: 22px 0 14px;
    background: linear-gradient(90deg, transparent, {CYAN}, {VIOLET}, {MAGENTA}, transparent);
    opacity: .55;
  }}

  div[data-testid="stDataFrame"] {{
    border: 1px solid {EDGE}; border-radius: 12px;
    box-shadow: 0 0 20px rgba(0,229,255,.08);
  }}
  .stAlert {{ border-radius: 12px; border: 1px solid {EDGE}; }}
  #MainMenu, footer {{ visibility: hidden; }}
</style>
""",
    unsafe_allow_html=True,
)


def chart_theme():
    return {
        "config": {
            "background": "transparent",
            "view": {"stroke": "transparent"},
            "axis": {
                "domainColor": EDGE,
                "gridColor": "#1d1740",
                "tickColor": EDGE,
                "labelColor": MUTED,
                "titleColor": MUTED,
                "labelFont": "Rajdhani",
                "titleFont": "Orbitron",
                "titleFontSize": 10,
            },
            "legend": {
                "labelColor": TEXT,
                "titleColor": MUTED,
                "labelFont": "Rajdhani",
                "titleFont": "Orbitron",
            },
        }
    }


alt.themes.register("neon", chart_theme)
alt.themes.enable("neon")

SERIES_COLOURS = [CYAN, MAGENTA, VIOLET, LIME, "#ffd166", "#7dd3fc"]


# ---------------------------------------------------------------------------
# Small rendering helpers
# ---------------------------------------------------------------------------
def money(value: float) -> str:
    return "—" if value is None or not math.isfinite(value) else f"${value:,.2f}"


def pct(value: float) -> str:
    return "—" if value is None or not math.isfinite(value) else f"{value:+.2f}%"


def tone(value: float) -> str:
    if value is None or not math.isfinite(value) or abs(value) < 1e-9:
        return "flat"
    return "up" if value > 0 else "down"


def card(label: str, value: str, sub: str = "", sub_tone: str = "flat") -> str:
    sub_html = f'<div class="neon-sub {sub_tone}">{sub}</div>' if sub else ""
    return (
        f'<div class="neon-card"><div class="neon-label">{label}</div>'
        f'<div class="neon-value">{value}</div>{sub_html}</div>'
    )


def rule() -> None:
    st.markdown('<div class="rule"></div>', unsafe_allow_html=True)


def numeric(frame: pd.DataFrame, columns) -> pd.DataFrame:
    for column in columns:
        if column in frame:
            frame[column] = pd.to_numeric(frame[column], errors="coerce")
    return frame


# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------
cfg = load_config(str(ROOT / "config" / "config.yaml"))


@st.cache_data(ttl=120)
def load_daily(student_id: str, log_dir: str) -> pd.DataFrame:
    rows = daily_log.read_rows(student_id, log_dir)
    if not rows:
        return pd.DataFrame()
    frame = numeric(
        pd.DataFrame(rows),
        ("equity", "cash", "buying_power", "day_pl", "day_pl_pct", "total_pl",
         "total_pl_pct", "open_positions", "orders_submitted"),
    )
    frame["when"] = pd.to_datetime(frame["timestamp_utc"], errors="coerce", utc=True)
    return frame.dropna(subset=["equity"]).sort_values("when")


@st.cache_data(ttl=120)
def load_ledger(student_id: str, log_dir: str) -> pd.DataFrame:
    rows = trade_ledger.read_fills(student_id, log_dir)
    if not rows:
        return pd.DataFrame()
    frame = numeric(
        pd.DataFrame(rows),
        ("qty", "price", "notional", "composite", "volatility_scale",
         "natr_pct", "beta", "stop_loss", "take_profit"),
    )
    frame["when"] = pd.to_datetime(frame["timestamp_utc"], errors="coerce", utc=True)
    return frame.sort_values("when")


@st.cache_data(ttl=300, show_spinner=False)
def load_committed_prices(log_dir: str) -> Dict[str, pd.DataFrame]:
    """Closing prices straight from the repository.

    This is the default source, and it needs no credentials: every run saves
    the closes it fetched into `trading-logs/prices.csv`, which is committed
    like every other log. Keys only ever ADD to this.
    """
    try:
        return price_log.to_frames(log_dir)
    except Exception:
        return {}


@st.cache_data(ttl=300, show_spinner=False)
def load_prices(symbols: tuple, key: str, secret: str, demo: bool) -> Dict[str, pd.DataFrame]:
    """Daily bars for the traded symbols plus the benchmark. Cached."""
    if not symbols:
        return {}
    if not demo and not (key and secret):
        return {}
    student = cfg.students[0]
    import os

    previous = (os.environ.get("ALPACA_API_KEY"), os.environ.get("ALPACA_SECRET_KEY"))
    try:
        if key and secret:
            os.environ["ALPACA_API_KEY"] = key
            os.environ["ALPACA_SECRET_KEY"] = secret
        client = build_client(cfg, student, demo_override=demo)
        return client.get_bars(list(symbols), days=120)
    except (MarketDataUnavailable, AlpacaError, PaperTradingViolation):
        return {}
    finally:
        for name, value in zip(("ALPACA_API_KEY", "ALPACA_SECRET_KEY"), previous):
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value


# ---------------------------------------------------------------------------
# Sidebar — read-only controls only
# ---------------------------------------------------------------------------
with st.sidebar:
    st.markdown(
        f'<h2 style="margin-top:0">◢ NEON DESK</h2>'
        f'<div style="color:{MUTED};font-size:.8rem;letter-spacing:1px;">'
        "READ-ONLY TERMINAL</div>",
        unsafe_allow_html=True,
    )
    st.markdown('<div class="rule"></div>', unsafe_allow_html=True)

    st.markdown(
        f'<div style="color:{MUTED};font-size:.82rem;line-height:1.5">'
        "This terminal <b>cannot place trades</b>. It has no order entry and no "
        "execute mode. Trading happens in the GitHub Actions pipeline; this "
        "shows what it did.</div>",
        unsafe_allow_html=True,
    )
    st.markdown('<div class="rule"></div>', unsafe_allow_html=True)

    st.markdown("**Live market data** *(optional)*")
    st.caption(
        "Only used to price open positions and draw price charts. Held for "
        "this browser session, never written to disk."
    )
    api_key = clean(st.text_input("Alpaca key", type="password", key="k"))
    api_secret = clean(st.text_input("Alpaca secret", type="password", key="s"))
    demo_prices = st.checkbox(
        "Use synthetic prices instead", value=not (api_key and api_secret),
        help="Clearly-labelled fake data, so the charts render without keys.",
    )

    if st.button("↻ Refresh data", use_container_width=True):
        st.cache_data.clear()
        st.rerun()

    st.markdown('<div class="rule"></div>', unsafe_allow_html=True)
    st.caption(f"Logs: `{cfg.log_dir}`")
    st.caption(f"Page opened {datetime.now(timezone.utc):%H:%M UTC}")


# ---------------------------------------------------------------------------
# Gather everything once
# ---------------------------------------------------------------------------
daily_frames = {s.id: load_daily(s.id, cfg.log_dir) for s in cfg.students}
ledger_frames = {s.id: load_ledger(s.id, cfg.log_dir) for s in cfg.students}

def repository_state(log_dir: str) -> dict:
    """How current the files on disk are, and whether git has newer ones.

    This page reads FILES, not GitHub. A checkout that has not been pulled
    shows old numbers and looks broken when it is merely stale, so say so
    plainly rather than letting the reader guess.
    """
    import subprocess

    state = {"behind": 0, "head": "", "checked": False, "error": ""}
    try:
        root = Path(log_dir).resolve()
        root = root.parent if root.name == "trading-logs" else root
        def git(*args):
            return subprocess.run(
                ["git", "-C", str(root), *args],
                capture_output=True, text=True, timeout=20,
            )
        head = git("rev-parse", "--short", "HEAD")
        if head.returncode != 0:
            state["error"] = "not a git checkout"
            return state
        state["head"] = head.stdout.strip()
        branch = git("rev-parse", "--abbrev-ref", "HEAD").stdout.strip()
        fetch = git("fetch", "--quiet", "origin", branch)
        if fetch.returncode != 0:
            state["error"] = "could not reach GitHub"
            return state
        counts = git("rev-list", "--count", f"HEAD..origin/{branch}")
        if counts.returncode == 0 and counts.stdout.strip().isdigit():
            state["behind"] = int(counts.stdout.strip())
            state["checked"] = True
        state["branch"] = branch
    except Exception as exc:
        state["error"] = f"{type(exc).__name__}"
    return state


def freshness_banner(daily_frames: Dict[str, pd.DataFrame], log_dir: str):
    """Say how old these numbers are, and offer to pull newer ones."""
    stamps = [
        frame["when"].max() for frame in daily_frames.values()
        if not frame.empty and "when" in frame
    ]
    newest = max(stamps) if stamps else None

    left, right = st.columns([4, 1])
    with left:
        if newest is None:
            st.warning(
                "No run has been logged yet, so there is nothing to show. "
                "The numbers appear after the next scheduled run."
            )
        else:
            age = datetime.now(timezone.utc) - newest.to_pydatetime()
            hours = age.total_seconds() / 3600.0
            when = f"{newest:%d %b %H:%M} UTC"
            if hours < 14:
                st.markdown(
                    f'<span class="pill">LAST RUN {when}</span>',
                    unsafe_allow_html=True)
            else:
                st.warning(
                    f"These figures are from the last recorded run, {when} "
                    f"— about {int(hours)} hours ago. They are not live. "
                    "Your Alpaca account will have moved since then; this page "
                    "shows what the pipeline recorded, and updates after each run."
                )

    state = repository_state(log_dir)
    with right:
        if st.button("⟳ Sync from GitHub", use_container_width=True):
            import subprocess
            root = Path(log_dir).resolve()
            root = root.parent if root.name == "trading-logs" else root
            pull = subprocess.run(
                ["git", "-C", str(root), "pull", "--ff-only", "origin",
                 state.get("branch") or "HEAD"],
                capture_output=True, text=True, timeout=90,
            )
            if pull.returncode == 0:
                st.cache_data.clear()
                st.rerun()
            else:
                st.error("Could not pull: " + (pull.stderr or "unknown error").strip()[:300])

    if state.get("behind"):
        st.error(
            f"**This copy is {state['behind']} commit(s) behind GitHub.** "
            "The logs on GitHub are newer than the files on this machine, so "
            "everything below is out of date. Press *Sync from GitHub* above, "
            "or run `git pull` in the project folder."
        )
    elif state.get("error"):
        st.caption(f"Could not check GitHub for newer logs ({state['error']}).")


traded_symbols = sorted(
    {
        str(sym).upper()
        for frame in ledger_frames.values()
        if not frame.empty
        for sym in frame["symbol"].dropna().unique()
    }
)
price_universe = tuple(traded_symbols + [alpha_lib.BENCHMARK]) if traded_symbols else ()

# The repository is the baseline. Live keys, when supplied, only fill in
# symbols or days the committed history does not already cover -- they are
# never required for the page to work.
prices = dict(load_committed_prices(cfg.log_dir))
price_source = "repository" if prices else "none"
if api_key and api_secret or demo_prices:
    live = load_prices(price_universe, api_key, api_secret, demo_prices)
    if live:
        prices.update(live)
        price_source = "live feed" if not demo_prices else "synthetic"
closes = {
    sym: float(frame["close"].iloc[-1])
    for sym, frame in prices.items()
    if not frame.empty
}
benchmark_bars = prices.get(alpha_lib.BENCHMARK)


def positions_for(student_id: str) -> List[alpha_lib.Position]:
    """Attributed positions for one member, priced at the latest close."""
    rows = trade_ledger.read_fills(student_id, cfg.log_dir)
    if not rows:
        return []
    positions = alpha_lib.build_positions(rows, include_demo=True)
    alpha_lib.mark_open_positions(positions, closes)
    alpha_lib.attribute(positions, benchmark_bars)
    return positions


all_positions = {s.id: positions_for(s.id) for s in cfg.students}


def latest_row(student_id: str):
    frame = daily_frames[student_id]
    return None if frame.empty else frame.iloc[-1]


# ---------------------------------------------------------------------------
# Reusable sections
# ---------------------------------------------------------------------------
def equity_chart(frames: Dict[str, pd.DataFrame], names: Dict[str, str], height=330):
    curves = []
    for student_id, frame in frames.items():
        if frame.empty:
            continue
        curves.append(
            frame[["when", "equity"]]
            .assign(member=names[student_id])
            .rename(columns={"when": "time"})
        )
    if not curves:
        st.info("No equity history yet. It appears once the pipeline has run.")
        return
    combined = pd.concat(curves)
    low, high = float(combined["equity"].min()), float(combined["equity"].max())
    pad = max((high - low) * 0.15, 150.0)
    base = (
        alt.Chart(combined)
        .mark_line(point=alt.OverlayMarkDef(size=55, filled=True), strokeWidth=2.6)
        .encode(
            x=alt.X("time:T", title=None),
            y=alt.Y(
                "equity:Q",
                title="EQUITY (USD)",
                scale=alt.Scale(domain=[low - pad, high + pad], zero=False),
                axis=alt.Axis(format="$,.0f"),
            ),
            color=alt.Color(
                "member:N", title="MEMBER",
                scale=alt.Scale(range=SERIES_COLOURS),
            ),
            tooltip=[
                alt.Tooltip("member:N", title="Member"),
                alt.Tooltip("time:T", title="When"),
                alt.Tooltip("equity:Q", title="Equity", format="$,.2f"),
            ],
        )
    )
    start_line = (
        alt.Chart(pd.DataFrame({"y": [100000.0]}))
        .mark_rule(strokeDash=[7, 5], color=MUTED, opacity=0.8)
        .encode(y="y:Q")
    )
    st.altair_chart((base + start_line).properties(height=height), use_container_width=True)
    st.caption("Dashed line marks the $100,000 starting equity.")


def pnl_section(frame: pd.DataFrame, title="Daily profit and loss"):
    if frame.empty or "day_pl" not in frame:
        st.info("No profit and loss history yet.")
        return
    data = frame.dropna(subset=["day_pl"]).copy()
    if data.empty:
        st.info("No profit and loss history yet.")
        return
    data["day"] = data["when"].dt.strftime("%d %b %H:%M")
    data["direction"] = data["day_pl"].apply(lambda v: "profit" if v >= 0 else "loss")

    st.markdown(f"### {title}")
    bars = (
        alt.Chart(data)
        .mark_bar(size=26, cornerRadiusTopLeft=4, cornerRadiusTopRight=4)
        .encode(
            x=alt.X("day:N", title=None, sort=None),
            y=alt.Y("day_pl:Q", title="DAY P&L (USD)", axis=alt.Axis(format="$,.0f")),
            color=alt.Color(
                "direction:N",
                scale=alt.Scale(domain=["profit", "loss"], range=[LIME, MAGENTA]),
                legend=None,
            ),
            tooltip=[
                alt.Tooltip("day:N", title="Run"),
                alt.Tooltip("day_pl:Q", title="Day P&L", format="$,.2f"),
                alt.Tooltip("day_pl_pct:Q", title="Day %", format="+.2f"),
                alt.Tooltip("equity:Q", title="Equity", format="$,.2f"),
            ],
        )
        .properties(height=240)
    )
    st.altair_chart(bars, use_container_width=True)

    total = float(data["total_pl"].dropna().iloc[-1]) if data["total_pl"].notna().any() else float("nan")
    total_pct = float(data["total_pl_pct"].dropna().iloc[-1]) if data["total_pl_pct"].notna().any() else float("nan")
    best = data.loc[data["day_pl"].idxmax()] if len(data) else None
    worst = data.loc[data["day_pl"].idxmin()] if len(data) else None
    up = int((data["day_pl"] > 0).sum())
    down = int((data["day_pl"] < 0).sum())

    columns = st.columns(4)
    columns[0].markdown(
        card("Total P&L", money(total), pct(total_pct), tone(total)), unsafe_allow_html=True
    )
    columns[1].markdown(
        card("Best run", money(float(best["day_pl"])) if best is not None else "—",
             best["day"] if best is not None else "", "up"),
        unsafe_allow_html=True,
    )
    columns[2].markdown(
        card("Worst run", money(float(worst["day_pl"])) if worst is not None else "—",
             worst["day"] if worst is not None else "", "down"),
        unsafe_allow_html=True,
    )
    columns[3].markdown(
        card("Up / down runs", f"{up} / {down}",
             f"{len(data)} recorded", "flat"),
        unsafe_allow_html=True,
    )


def trajectory_chart(symbols: List[str], height=340):
    """Each traded stock rebased to 100 at the start of the window."""
    series = []
    for symbol in symbols:
        frame = prices.get(symbol)
        if frame is None or frame.empty:
            continue
        closes_s = frame["close"].dropna()
        if closes_s.empty:
            continue
        rebased = 100.0 * closes_s / float(closes_s.iloc[0])
        series.append(
            pd.DataFrame(
                {"time": closes_s.index, "value": rebased.to_numpy(), "symbol": symbol}
            )
        )
    if not series:
        st.info(
            "No price history yet. Every run saves the closes it fetched into "
            "`trading-logs/prices.csv`; this chart fills in from the next run "
            "onwards, with no keys needed."
        )
        return
    combined = pd.concat(series)
    chart = (
        alt.Chart(combined)
        .mark_line(strokeWidth=2.1, opacity=0.95)
        .encode(
            x=alt.X("time:T", title=None),
            y=alt.Y("value:Q", title="REBASED TO 100", scale=alt.Scale(zero=False)),
            color=alt.Color("symbol:N", title="SYMBOL",
                            scale=alt.Scale(scheme="turbo")),
            tooltip=[
                alt.Tooltip("symbol:N", title="Symbol"),
                alt.Tooltip("time:T", title="Date"),
                alt.Tooltip("value:Q", title="Rebased", format=".1f"),
            ],
        )
        .properties(height=height)
    )
    flat = (
        alt.Chart(pd.DataFrame({"y": [100.0]}))
        .mark_rule(strokeDash=[7, 5], color=MUTED, opacity=0.7)
        .encode(y="y:Q")
    )
    st.altair_chart(chart + flat, use_container_width=True)
    st.caption(
        "Every traded stock rebased to 100 at the window start, so their paths "
        "are comparable regardless of share price."
    )


def alpha_section(positions: List[alpha_lib.Position], heading="Alpha attribution"):
    st.markdown(f"### {heading}")
    if not positions:
        st.info(
            "No trades recorded yet. The ledger fills as orders are submitted — "
            "`trading-logs/trades_<member>.csv`."
        )
        return
    summary = alpha_lib.summarise(positions)

    columns = st.columns(4)
    columns[0].markdown(
        card("Excess vs SPY", pct(summary.mean_excess), "mean per trade",
             tone(summary.mean_excess)), unsafe_allow_html=True)
    columns[1].markdown(
        card("Jensen's alpha", pct(summary.mean_jensen), "risk-adjusted",
             tone(summary.mean_jensen)), unsafe_allow_html=True)
    columns[2].markdown(
        card("Signal IC", f"{summary.ic_return:+.3f}" if math.isfinite(summary.ic_return) else "—",
             "score vs outcome", tone(summary.ic_return)), unsafe_allow_html=True)
    columns[3].markdown(
        card("Win rate", pct(summary.win_rate).replace("+", "") if math.isfinite(summary.win_rate) else "—",
             f"{summary.trades} trades", "flat"), unsafe_allow_html=True)

    if not summary.meaningful:
        st.markdown(
            f'<div style="margin-top:10px"><span class="pill pill-warn">SMALL SAMPLE</span> '
            f'<span style="color:{MUTED}"> {summary.trades} trades. '
            f"Significance needs {alpha_lib.MEANINGFUL_SAMPLE}+, realistically "
            "hundreds. These numbers describe what happened; they do not yet "
            "establish whether the strategy works.</span></div>",
            unsafe_allow_html=True,
        )

    if summary.by_conviction:
        st.markdown("#### By conviction")
        st.caption(
            "If higher conviction does not earn more, the conviction mechanism "
            "is decorative."
        )
        st.dataframe(
            pd.DataFrame(
                [
                    {
                        "Conviction": level,
                        "Trades": stats["trades"],
                        "Mean return": pct(stats["mean_return"]),
                        "Mean excess": pct(stats["mean_excess"]),
                        "Mean Jensen": pct(stats["mean_jensen"]),
                    }
                    for level, stats in summary.by_conviction.items()
                ]
            ),
            use_container_width=True, hide_index=True,
        )

    with st.expander("Per-trade detail"):
        st.dataframe(
            pd.DataFrame([p.to_dict() for p in positions]).assign(
                return_pct=lambda d: d["return_pct"].map(pct),
                benchmark_pct=lambda d: d["benchmark_pct"].map(pct),
                excess_pct=lambda d: d["excess_pct"].map(pct),
                jensen_pct=lambda d: d["jensen_pct"].map(pct),
                entry_price=lambda d: d["entry_price"].map(money),
                mark_price=lambda d: d["mark_price"].map(money),
                pnl=lambda d: d["pnl"].map(money),
            ),
            use_container_width=True, hide_index=True,
        )


def alpha_history_section(student_id: str, student_name: str):
    """Every alpha reading recorded for this member, oldest run to newest.

    ``alpha_section`` above answers "where does the attribution stand right
    now". This answers "how has it moved", which is the one that shows
    whether a good number is a trend or a single lucky trade.
    """
    st.markdown(f"### Alpha history — {student_name}")
    rows = alpha_log.read_rows(student_id, cfg.log_dir)
    if not rows:
        st.info(
            "No alpha readings recorded yet. One is appended after every run "
            "to `trading-logs/alpha_"
            + student_id
            + ".csv`; readings for runs made before the log existed come from "
            "`scripts/backfill_ledger.py`."
        )
        return

    frame = pd.DataFrame(rows)
    for column in (
        "mean_return_pct", "mean_excess_pct", "mean_jensen_pct",
        "total_pnl", "win_rate_pct", "ic_return", "trades", "open_trades",
    ):
        if column in frame:
            frame[column] = pd.to_numeric(frame[column], errors="coerce")
    frame["when"] = pd.to_datetime(frame["timestamp_utc"], errors="coerce", utc=True)
    frame = frame.sort_values("when")

    latest = frame.iloc[-1]
    first = frame.iloc[0]
    moved = float(latest["mean_excess_pct"]) - float(first["mean_excess_pct"])

    columns = st.columns(4)
    columns[0].markdown(
        card("Readings", f"{len(frame)}", "one per run", "flat"),
        unsafe_allow_html=True)
    columns[1].markdown(
        card("Latest excess", pct(float(latest["mean_excess_pct"])),
             str(latest.get("run_label") or "run"),
             tone(float(latest["mean_excess_pct"]))), unsafe_allow_html=True)
    columns[2].markdown(
        card("Latest Jensen", pct(float(latest["mean_jensen_pct"])),
             "risk-adjusted", tone(float(latest["mean_jensen_pct"]))),
        unsafe_allow_html=True)
    columns[3].markdown(
        card("Moved since first", pct(moved) if math.isfinite(moved) else "—",
             "excess, first to latest", tone(moved)), unsafe_allow_html=True)

    plot = frame.dropna(subset=["when"])
    series = plot.melt(
        id_vars=["when", "run_label"],
        value_vars=[c for c in ("mean_excess_pct", "mean_jensen_pct", "mean_return_pct")
                    if c in plot],
        var_name="measure", value_name="value",
    ).dropna(subset=["value"])
    labels = {
        "mean_excess_pct": "Excess vs SPY",
        "mean_jensen_pct": "Jensen's alpha",
        "mean_return_pct": "Raw return",
    }
    series["measure"] = series["measure"].map(labels)

    if not series.empty:
        zero = alt.Chart(pd.DataFrame({"y": [0.0]})).mark_rule(
            color=MUTED, strokeDash=[4, 4], opacity=0.7).encode(y="y:Q")
        line = (
            alt.Chart(series)
            .mark_line(point=alt.OverlayMarkDef(size=55, filled=True), strokeWidth=2.4)
            .encode(
                x=alt.X("when:T", title=None),
                y=alt.Y("value:Q", title="percent"),
                color=alt.Color(
                    "measure:N", title=None,
                    scale=alt.Scale(
                        domain=["Excess vs SPY", "Jensen's alpha", "Raw return"],
                        range=[CYAN, MAGENTA, VIOLET]),
                ),
                tooltip=[
                    alt.Tooltip("when:T", title="run"),
                    alt.Tooltip("run_label:N", title="which"),
                    alt.Tooltip("measure:N", title="measure"),
                    alt.Tooltip("value:Q", title="percent", format="+.2f"),
                ],
            )
        )
        st.altair_chart(
            (zero + line).properties(height=300), use_container_width=True
        )

    if (frame["ic_return"].notna()).any():
        st.caption(
            "IC is blank for backfilled trades: the composite score at entry "
            "was never recorded for them, so there is nothing to correlate "
            "the return against. It is not a zero."
        )

    table = pd.DataFrame({
        "Date": frame["date"],
        "UTC": frame["timestamp_utc"].str.slice(11, 16),
        "Run": frame["run_label"],
        "Trades": frame["trades"],
        "Open": frame["open_trades"],
        "Return": frame["mean_return_pct"].map(pct),
        "Excess": frame["mean_excess_pct"].map(pct),
        "Jensen": frame["mean_jensen_pct"].map(pct),
        "Win rate": frame["win_rate_pct"].map(lambda v: pct(v).replace("+", "")),
        "IC": frame["ic_return"].map(
            lambda v: f"{v:+.3f}" if pd.notna(v) and math.isfinite(v) else "—"),
        "P&L": frame["total_pnl"].map(money),
        "Data": frame["data_source"],
    })
    st.dataframe(table.iloc[::-1], use_container_width=True, hide_index=True)

    notes = [n for n in frame.get("note", pd.Series(dtype=str)).fillna("") if str(n).strip()]
    if notes:
        with st.expander("Notes recorded with these readings"):
            for note in dict.fromkeys(notes[-10:]):
                st.markdown(f"- {note}")


def orders_section(student_id: str, student_name: str):
    st.markdown("### Orders")
    frame = ledger_frames[student_id]
    if frame.empty:
        st.info(
            "No orders recorded yet. The ledger is written when the pipeline "
            "runs in execute mode."
        )
    else:
        view = frame[
            [c for c in (
                "date", "run_label", "symbol", "side", "qty", "price", "notional",
                "conviction", "composite", "volatility_scale", "stop_loss",
                "take_profit", "bracket", "engine", "status",
            ) if c in frame.columns]
        ].copy()
        view = view.iloc[::-1]  # newest first
        st.dataframe(view, use_container_width=True, hide_index=True, height=320)

    # Live order state straight from Alpaca, when keys are present.
    if api_key and api_secret and not demo_prices:
        with st.expander("Live order status from Alpaca"):
            try:
                import os

                os.environ["ALPACA_API_KEY"] = api_key
                os.environ["ALPACA_SECRET_KEY"] = api_secret
                client = build_client(cfg, cfg.student(student_id), demo_override=False)
                live = client.get_orders(status="all", limit=50)
                if live:
                    st.dataframe(
                        pd.DataFrame(live)[
                            [c for c in ("symbol", "side", "qty", "filled_qty",
                                         "status", "order_class", "submitted_at")
                             if c in pd.DataFrame(live).columns]
                        ],
                        use_container_width=True, hide_index=True,
                    )
                else:
                    st.caption("Alpaca reports no orders on this account.")
            except (MarketDataUnavailable, AlpacaError, PaperTradingViolation) as exc:
                st.warning(f"Could not read live orders: {exc}")


def history_section(frame: pd.DataFrame):
    st.markdown("### Run history")
    if frame.empty:
        st.info("No runs recorded yet.")
        return
    view = frame[
        [c for c in (
            "date", "timestamp_utc", "equity", "cash", "buying_power", "day_pl",
            "day_pl_pct", "total_pl", "total_pl_pct", "open_positions",
            "buy_signals", "sell_signals", "hold_signals", "orders_submitted",
            "data_source", "engine", "mode",
        ) if c in frame.columns]
    ].copy().iloc[::-1]
    st.dataframe(view, use_container_width=True, hide_index=True, height=320)
    st.caption(
        "Synced from the committed logs in the repository — every scheduled run "
        "appends a row and pushes it back."
    )


# ---------------------------------------------------------------------------
# Header
# ---------------------------------------------------------------------------
st.markdown("# ◢ AI PAPER TRADING")
engines = [
    str(latest_row(s.id)["engine"]) for s in cfg.students if latest_row(s.id) is not None
]
sources = [
    str(latest_row(s.id)["data_source"]) for s in cfg.students if latest_row(s.id) is not None
]
st.markdown(
    f'<span class="pill">READ ONLY</span> &nbsp; '
    f'<span class="pill">PAPER</span> &nbsp; '
    f'<span class="pill">{len(cfg.students)} MEMBERS</span> &nbsp; '
    f'<span class="pill">{len(traded_symbols)} SYMBOLS TRADED</span> &nbsp; '
    f'<span class="pill">{sources[0] if sources else "NO DATA"}</span>',
    unsafe_allow_html=True,
)
rule()

names = {s.id: s.name for s in cfg.students}
tab_labels = ["◆ GROUP"] + [f"◇ {s.name.split()[0].upper()}" for s in cfg.students]
tabs = st.tabs(tab_labels)


# ---------------------------------------------------------------------------
# GROUP
# ---------------------------------------------------------------------------
with tabs[0]:
    freshness_banner(daily_frames, cfg.log_dir)
    st.markdown("## Team performance")

    total_equity = 0.0
    total_start = 0.0
    columns = st.columns(len(cfg.students))
    for column, student in zip(columns, cfg.students):
        row = latest_row(student.id)
        total_start += student.starting_equity
        if row is None:
            total_equity += student.starting_equity
            column.markdown(card(student.name, "no data", student.roll_no), unsafe_allow_html=True)
            continue
        equity = float(row["equity"])
        total_equity += equity
        total_pl = float(row["total_pl"]) if math.isfinite(float(row["total_pl"])) else 0.0
        column.markdown(
            card(
                student.name,
                money(equity),
                f"{money(total_pl)} &nbsp; {pct(float(row['total_pl_pct']))} &nbsp;·&nbsp; "
                f"{int(row['open_positions'])} open",
                tone(total_pl),
            ),
            unsafe_allow_html=True,
        )

    rule()
    group_pl = total_equity - total_start
    columns = st.columns(3)
    columns[0].markdown(card("Group equity", money(total_equity),
                             f"from {money(total_start)}", "flat"), unsafe_allow_html=True)
    columns[1].markdown(card("Group P&L", money(group_pl), "combined", tone(group_pl)),
                        unsafe_allow_html=True)
    columns[2].markdown(
        card("Group return",
             pct(group_pl / total_start * 100 if total_start else float("nan")),
             "since inception", tone(group_pl)),
        unsafe_allow_html=True,
    )

    rule()
    st.markdown("### Equity trajectory")
    equity_chart(daily_frames, names, height=360)

    counts = {s.name: len(daily_frames[s.id]) for s in cfg.students}
    if counts and max(counts.values()) - min(counts.values()) >= 2:
        behind = [n for n, c in counts.items() if c == min(counts.values())]
        st.warning(
            f"Uneven logging — {', '.join(behind)} has {min(counts.values())} run(s) "
            f"recorded against {max(counts.values())} for the others, so that "
            "figure may be stale."
        )

    rule()
    st.markdown("### Stock trajectory")
    trajectory_chart(traded_symbols)

    rule()
    st.markdown("### Combined daily profit and loss")
    combined_daily = pd.concat(
        [f for f in daily_frames.values() if not f.empty], ignore_index=True
    ) if any(not f.empty for f in daily_frames.values()) else pd.DataFrame()
    if combined_daily.empty:
        st.info("No profit and loss history yet.")
    else:
        grouped = (
            combined_daily.dropna(subset=["day_pl"])
            .groupby("date", as_index=False)[["day_pl", "total_pl"]]
            .sum()
        )
        grouped["direction"] = grouped["day_pl"].apply(
            lambda v: "profit" if v >= 0 else "loss"
        )
        st.altair_chart(
            alt.Chart(grouped)
            .mark_bar(size=34, cornerRadiusTopLeft=4, cornerRadiusTopRight=4)
            .encode(
                x=alt.X("date:N", title=None, sort=None),
                y=alt.Y("day_pl:Q", title="GROUP DAY P&L (USD)",
                        axis=alt.Axis(format="$,.0f")),
                color=alt.Color(
                    "direction:N",
                    scale=alt.Scale(domain=["profit", "loss"], range=[LIME, MAGENTA]),
                    legend=None,
                ),
                tooltip=[
                    alt.Tooltip("date:N", title="Date"),
                    alt.Tooltip("day_pl:Q", title="Group day P&L", format="$,.2f"),
                ],
            )
            .properties(height=250),
            use_container_width=True,
        )
        st.markdown(
            card("Group total P&L", money(group_pl),
                 f"across {len(grouped)} trading day(s)", tone(group_pl)),
            unsafe_allow_html=True,
        )


# ---------------------------------------------------------------------------
# One tab per member
# ---------------------------------------------------------------------------
for index, student in enumerate(cfg.students, start=1):
    with tabs[index]:
        row = latest_row(student.id)
        st.markdown(f"## {student.name}")
        st.markdown(
            f'<span class="pill">ROLL {student.roll_no}</span> &nbsp; '
            f'<span class="pill">{len(student.symbols)} SYMBOLS</span> &nbsp; '
            f'<span class="pill">{student.high_beta_pct:.0%} HIGH BETA</span>',
            unsafe_allow_html=True,
        )
        rule()

        if row is None:
            st.info("No runs recorded for this member yet.")
        else:
            equity = float(row["equity"])
            total_pl = float(row["total_pl"])
            day_pl = float(row["day_pl"]) if math.isfinite(float(row["day_pl"])) else float("nan")
            columns = st.columns(4)
            columns[0].markdown(card("Equity", money(equity),
                                     f"as of {row['date']}", "flat"), unsafe_allow_html=True)
            columns[1].markdown(card("Total P&L", money(total_pl),
                                     pct(float(row["total_pl_pct"])), tone(total_pl)),
                                unsafe_allow_html=True)
            columns[2].markdown(card("Last run P&L", money(day_pl),
                                     pct(float(row["day_pl_pct"])), tone(day_pl)),
                                unsafe_allow_html=True)
            columns[3].markdown(card("Open positions", str(int(row["open_positions"])),
                                     f"engine: {row['engine']}", "flat"),
                                unsafe_allow_html=True)

        rule()
        st.markdown("### Equity trajectory")
        equity_chart({student.id: daily_frames[student.id]}, names, height=300)

        rule()
        pnl_section(daily_frames[student.id])

        rule()
        st.markdown("### Stock trajectory")
        member_symbols = sorted(
            {
                str(s).upper()
                for s in (
                    ledger_frames[student.id]["symbol"].dropna().unique()
                    if not ledger_frames[student.id].empty
                    else []
                )
            }
        ) or student.symbols
        trajectory_chart([s for s in member_symbols if s in prices])

        rule()
        alpha_section(all_positions[student.id], f"Alpha attribution — {student.name}")

        rule()
        alpha_history_section(student.id, student.name)

        rule()
        orders_section(student.id, student.name)

        rule()
        history_section(daily_frames[student.id])
