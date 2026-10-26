"""Streamlit control panel for the paper-trading system.

Credentials entered here are held in ``st.session_state`` for the life of the
browser session ONLY.  They are never written to disk, never placed in
``st.secrets``, and never logged.  Closing the tab discards them.

Run with:
    streamlit run dashboard/app.py
"""

from __future__ import annotations

import io
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import altair as alt
import pandas as pd
import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from trading_system import daily_log  # noqa: E402
from trading_system.alpaca_client import (  # noqa: E402
    AlpacaClient,
    AlpacaError,
    MarketDataUnavailable,
)
from trading_system.config import clean, load_config  # noqa: E402
from trading_system.features import DIMENSIONS  # noqa: E402
from trading_system.paper_guard import PaperTradingViolation  # noqa: E402
from trading_system.pipeline import run_for_student  # noqa: E402
from trading_system.risk import plan_orders  # noqa: E402
from trading_system.rule_engine import run_rule_engine  # noqa: E402

st.set_page_config(page_title="AI Paper Trading", page_icon="📈", layout="wide")

SESSION_KEYS = ("alpaca_key", "alpaca_secret", "llm_key")


def session_defaults() -> None:
    for key in SESSION_KEYS:
        st.session_state.setdefault(key, "")
    st.session_state.setdefault("last_run", None)
    st.session_state.setdefault("approved", set())
    st.session_state.setdefault("running", False)


session_defaults()


# ---------------------------------------------------------------------------
# Sidebar: credentials (session only) and strategy configuration
# ---------------------------------------------------------------------------
with st.sidebar:
    st.header("Credentials")
    st.caption(
        "Held in this browser session only. Never written to disk, never "
        "logged. Closing the tab discards them."
    )
    st.session_state["alpaca_key"] = st.text_input(
        "Alpaca API key (paper)", value=st.session_state["alpaca_key"], type="password"
    )
    st.session_state["alpaca_secret"] = st.text_input(
        "Alpaca secret key", value=st.session_state["alpaca_secret"], type="password"
    )
    st.session_state["llm_key"] = st.text_input(
        "LLM API key (optional)", value=st.session_state["llm_key"], type="password"
    )
    if st.button("Clear credentials"):
        for key in SESSION_KEYS:
            st.session_state[key] = ""
        st.rerun()

    # Whitespace is stripped here, at the single point of entry: a key pasted
    # with a trailing newline is rejected by Alpaca as invalid.
    alpaca_key = clean(st.session_state["alpaca_key"])
    alpaca_secret = clean(st.session_state["alpaca_secret"])
    llm_key = clean(st.session_state["llm_key"])
    have_creds = bool(alpaca_key and alpaca_secret)

    st.divider()
    st.header("Run")
    demo_mode = st.checkbox(
        "Demo mode (clearly-labelled synthetic data)", value=not have_creds
    )
    if not have_creds and not demo_mode:
        st.error(
            "No credentials and demo mode is off. The system will REFUSE to "
            "fetch rather than invent prices."
        )
    use_llm = st.checkbox("Use the LLM agent crew", value=bool(llm_key))
    mode = st.radio("Mode", ["analyse", "execute"], horizontal=True)
    if mode == "execute":
        st.warning("Execute mode submits orders to the Alpaca PAPER account.")
    require_approval = st.checkbox(
        "Require my approval before any order is sent", value=True
    )

    st.divider()
    st.header("Strategy")
    aggression = st.slider(
        "Aggression", 0.0, 1.0, 0.75, 0.05,
        help="0.0 = textbook-timid, 1.0 = maximal. The brief asks for risk-taking.",
    )
    buy_threshold = st.slider("BUY threshold", 0.05, 0.60, 0.18, 0.01)
    sell_threshold = st.slider("SELL threshold", -0.60, -0.05, -0.18, 0.01)
    max_llm_symbols = st.number_input("Max symbols sent to the crew", 1, 45, 12)

    st.subheader("Dimension weights")
    weights = {}
    defaults = {"trend": 0.28, "momentum": 0.24, "volume": 0.14,
                "volatility": 0.12, "statistics": 0.12, "sentiment": 0.10}
    for name, default in defaults.items():
        weights[name] = st.slider(name, 0.0, 0.5, default, 0.01, key=f"w_{name}")

    st.subheader("Indicator dimensions in play")
    enabled_dims = st.multiselect(
        "Dimensions", DIMENSIONS + ["sentiment"], default=DIMENSIONS + ["sentiment"]
    )
    for name in list(weights):
        if name not in enabled_dims:
            weights[name] = 0.0


# Environment overrides are applied before the config is read so the derived
# risk numbers are recomputed from the sliders.
os.environ["AGGRESSION"] = str(aggression)
os.environ["RUN_MODE"] = mode
os.environ["DEMO_MODE"] = "true" if demo_mode else "false"
os.environ["REQUIRE_HUMAN_APPROVAL"] = "true" if require_approval else "false"
os.environ["MAX_LLM_SYMBOLS"] = str(int(max_llm_symbols))
if alpaca_key:
    os.environ["ALPACA_API_KEY"] = alpaca_key
    os.environ["ALPACA_SECRET_KEY"] = alpaca_secret
if llm_key:
    os.environ.setdefault("OLLAMA_API_KEY", llm_key)

cfg = load_config(str(ROOT / "config" / "config.yaml"))
cfg.signals = dict(cfg.signals or {})
cfg.signals["buy_threshold"] = buy_threshold
cfg.signals["sell_threshold"] = sell_threshold
cfg.signals["dimension_weights"] = weights

st.title("AI Paper Trading — control panel")
badge = "DEMO (synthetic data)" if demo_mode else ("LIVE paper data" if have_creds else "NO DATA ACCESS")
st.caption(
    f"**{badge}** · mode `{cfg.mode}` · aggression `{cfg.aggression:.2f}` · "
    f"auto-execute `{cfg.execute}` · paper endpoint `{cfg.alpaca_base_url}`"
)

tabs = st.tabs(
    ["Group overview", "Run", "Recommendations", "Positions & P&L",
     "Execution history", "Daily logs"]
)

student_ids = [s.id for s in cfg.students]


def _series(student) -> pd.DataFrame:
    """That member's committed daily log as a frame, newest last."""
    rows = daily_log.read_rows(student.id, cfg.log_dir)
    if not rows:
        return pd.DataFrame()
    frame = pd.DataFrame(rows)
    for col in ("equity", "day_pl", "day_pl_pct", "total_pl", "total_pl_pct"):
        if col in frame:
            frame[col] = pd.to_numeric(frame[col], errors="coerce")
    frame["when"] = pd.to_datetime(frame["timestamp_utc"], errors="coerce", utc=True)
    return frame.dropna(subset=["equity"]).sort_values("when")


# ---------------------------------------------------------------------------
# Group overview — the whole team on one screen.
# ---------------------------------------------------------------------------
with tabs[0]:
    st.subheader("Team performance")

    frames = {s.id: _series(s) for s in cfg.students}
    latest, total_equity, total_start = {}, 0.0, 0.0
    for student in cfg.students:
        frame = frames[student.id]
        total_start += student.starting_equity
        if frame.empty:
            latest[student.id] = None
            total_equity += student.starting_equity
        else:
            row = frame.iloc[-1]
            latest[student.id] = row
            total_equity += float(row["equity"])

    columns = st.columns(len(cfg.students))
    for col, student in zip(columns, cfg.students):
        row = latest[student.id]
        with col:
            st.caption(f"**{student.name}**  \n`{student.roll_no}`")
            if row is None:
                st.metric("Equity", "no data", "")
                st.caption("No runs recorded yet.")
                continue
            pl = float(row["total_pl"])
            st.metric(
                "Equity",
                f"${float(row['equity']):,.2f}",
                f"{pl:+,.2f} ({float(row['total_pl_pct']):+.2f}%)",
            )
            st.caption(
                f"{row['open_positions']} positions · {len(frames[student.id])} runs "
                f"logged · as of {str(row['date'])}"
            )

    st.divider()
    group_pl = total_equity - total_start
    a, b, c = st.columns(3)
    a.metric("Group equity", f"${total_equity:,.2f}")
    b.metric("Group P&L", f"${group_pl:+,.2f}")
    c.metric("Group return", f"{(group_pl / total_start * 100) if total_start else 0:+.2f}%")

    # Equity curves, all three on one chart.
    curves = []
    for student in cfg.students:
        frame = frames[student.id]
        if frame.empty:
            continue
        curves.append(
            frame[["when", "equity"]].assign(member=student.name).rename(
                columns={"when": "time"}
            )
        )
    if curves:
        st.subheader("Equity over time")
        combined = pd.concat(curves)
        # A zero-based axis squashes four days of sub-1% movement into a flat
        # line, so the scale is zoomed to the data with a small pad and the
        # $100,000 starting line is drawn in for reference.
        low = float(combined["equity"].min())
        high = float(combined["equity"].max())
        pad = max((high - low) * 0.15, 150.0)
        chart = (
            alt.Chart(combined)
            .mark_line(point=True, strokeWidth=2.5)
            .encode(
                x=alt.X("time:T", title=None),
                y=alt.Y(
                    "equity:Q",
                    title="Equity (USD)",
                    scale=alt.Scale(domain=[low - pad, high + pad], zero=False),
                    axis=alt.Axis(format="$,.0f"),
                ),
                color=alt.Color("member:N", title="Member"),
                tooltip=[
                    alt.Tooltip("member:N", title="Member"),
                    alt.Tooltip("time:T", title="When"),
                    alt.Tooltip("equity:Q", title="Equity", format="$,.2f"),
                ],
            )
        )
        baseline = (
            alt.Chart(pd.DataFrame({"y": [100000.0]}))
            .mark_rule(strokeDash=[6, 4], color="#888")
            .encode(y="y:Q")
        )
        st.altair_chart((chart + baseline).properties(height=340),
                        use_container_width=True)
        st.caption("Dashed line marks the $100,000 starting equity.")
    else:
        st.info("No committed daily logs yet. Run the pipeline to populate this.")

    # Staleness is worth surfacing: a member whose job keeps failing silently
    # falls behind and the number above stops meaning anything.
    counts = {s.name: len(frames[s.id]) for s in cfg.students}
    if counts and max(counts.values()) - min(counts.values()) >= 2:
        behind = [n for n, c in counts.items() if c == min(counts.values())]
        st.warning(
            f"Uneven logging: {', '.join(behind)} has {min(counts.values())} run(s) "
            f"recorded against {max(counts.values())} for the others, so that "
            "figure may be stale."
        )

    with st.expander("Universe and high-beta allocation"):
        st.dataframe(
            pd.DataFrame([
                {
                    "Member": s.name,
                    "Roll no.": s.roll_no,
                    "Symbols": len(s.symbols),
                    "High-beta": f"{s.high_beta_pct:.0%}",
                    "High-beta names": ", ".join(s.high_beta),
                }
                for s in cfg.students
            ]),
            use_container_width=True, hide_index=True,
        )


# ---------------------------------------------------------------------------
with tabs[1]:
    st.subheader("Select a student and the symbols to analyse")
    student_id = st.selectbox("Student", student_ids)
    student = cfg.student(student_id)
    picked = st.multiselect(
        "Stocks", student.symbols, default=student.symbols,
        help="High-beta names are part of the mandated 30% sleeve.",
    )
    st.caption(
        f"High-beta sleeve: {', '.join(student.high_beta)} "
        f"({student.high_beta_pct:.0%} of the universe)"
    )

    col_start, col_stop = st.columns(2)
    start = col_start.button("Start analysis", type="primary", use_container_width=True)
    if col_stop.button("Stop / clear", use_container_width=True):
        st.session_state["last_run"] = None
        st.session_state["approved"] = set()
        st.rerun()

    if start:
        if not picked:
            st.error("Pick at least one symbol.")
        else:
            with st.spinner("Running the pipeline..."):
                try:
                    result = run_for_student(cfg, student_id, picked, use_llm=use_llm)
                    st.session_state["last_run"] = result
                    st.session_state["approved"] = set()
                except MarketDataUnavailable as exc:
                    st.error(str(exc))
                except PaperTradingViolation as exc:
                    st.error(f"Paper-trading guard: {exc}")
                except Exception as exc:  # noqa: BLE001
                    st.exception(exc)

    result = st.session_state.get("last_run")
    if result:
        st.success(f"Run complete — engine: `{result.engine}`")
        for fallback in result.fallbacks:
            st.warning(f"FALLBACK: {fallback}")
        for err in result.errors:
            st.error(err)
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("BUY", result.counts.get("BUY", 0))
        c2.metric("SELL", result.counts.get("SELL", 0))
        c3.metric("HOLD", result.counts.get("HOLD", 0))
        c4.metric("Data", result.data_source)
        with st.expander("Run notes"):
            for note in result.notes:
                st.write("-", note)
        with st.expander("Agent artefacts written to model-run/"):
            for path in result.artefacts:
                st.code(path, language=None)


# ---------------------------------------------------------------------------
with tabs[2]:
    result = st.session_state.get("last_run")
    if not result or not result.signals:
        st.info("Run an analysis first.")
    else:
        st.subheader("Recommendations")
        frame = pd.DataFrame(
            [
                {
                    "symbol": s["symbol"],
                    "action": s["action"],
                    "conviction": s["conviction"],
                    "composite": s["composite"],
                    "close": s["close"],
                    **{f"dim.{k}": v for k, v in s["dimension_scores"].items()},
                    "sentiment": s["sentiment_score"],
                }
                for s in result.signals
            ]
        )
        st.dataframe(frame, use_container_width=True, hide_index=True)

        with st.expander("Per-symbol rationale"):
            for s in result.signals:
                st.markdown(f"**{s['symbol']} — {s['action']} ({s['conviction']})**")
                for line in s["rationale"]:
                    st.text(line)

        st.subheader("Approve trades")
        if not result.plan or not result.plan.orders:
            st.info("The risk engine planned no orders this run.")
        else:
            st.caption(
                "Exits are listed first — their proceeds already fund the entries below."
            )
            approved = set(st.session_state.get("approved", set()))
            for order in result.plan.orders:
                key = order.client_order_id
                label = (
                    f"{order.side.upper()} {order.symbol} — {order.qty:.3f} sh "
                    f"≈ ${order.notional:,.0f} ({order.conviction})"
                    + (f" · stop ${order.stop_loss:,.2f} · target ${order.take_profit:,.2f}"
                       if order.stop_loss else "")
                )
                if st.checkbox(label, key=f"ap_{key}", value=key in approved):
                    approved.add(key)
                else:
                    approved.discard(key)
                st.caption(f"    {order.reason}")
            st.session_state["approved"] = approved

            st.divider()
            if not approved:
                st.info("Tick the orders you want to send.")
            elif not have_creds:
                st.error("Credentials are required to submit orders.")
            elif demo_mode:
                st.info("Demo mode: orders are simulated and never leave this machine.")
            if st.button(
                f"Submit {len(approved)} approved order(s) to the PAPER account",
                type="primary",
                disabled=not approved,
            ):
                client = AlpacaClient(
                    api_key=alpaca_key,
                    secret_key=alpaca_secret,
                    base_url=cfg.alpaca_base_url,
                    data_url=cfg.alpaca_data_url,
                    demo_mode=demo_mode,
                    starting_equity=student.starting_equity,
                )
                for order in result.plan.orders:
                    if order.client_order_id not in approved:
                        continue
                    try:
                        out = client.submit_order(
                            order.symbol, order.qty, order.side, order.client_order_id
                        )
                        result.submitted.append(out)
                        st.success(f"{order.symbol}: {out.get('status')}")
                    except (PaperTradingViolation, MarketDataUnavailable, AlpacaError) as exc:
                        st.error(f"{order.symbol}: {exc}")


# ---------------------------------------------------------------------------
with tabs[3]:
    st.subheader("Account and positions")
    student_id = st.selectbox("Student", student_ids, key="pos_student")
    student = cfg.student(student_id)
    if not have_creds and not demo_mode:
        st.info("Enter credentials or switch on demo mode.")
    else:
        try:
            client = AlpacaClient(
                api_key=alpaca_key,
                secret_key=alpaca_secret,
                base_url=cfg.alpaca_base_url,
                data_url=cfg.alpaca_data_url,
                demo_mode=demo_mode,
                starting_equity=student.starting_equity,
            )
            account = client.get_account()
            positions = client.get_positions()
            equity = float(account.get("equity") or 0.0)
            last_equity = float(account.get("last_equity") or equity)
            start_equity = student.starting_equity
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("Equity", f"${equity:,.2f}",
                      f"{equity - last_equity:+,.2f} today")
            c2.metric("Cash", f"${float(account.get('cash') or 0):,.2f}")
            c3.metric("Buying power", f"${float(account.get('buying_power') or 0):,.2f}")
            c4.metric(
                "Total P&L", f"${equity - start_equity:+,.2f}",
                f"{(equity / start_equity - 1) * 100:+.2f}%" if start_equity else "",
            )
            if positions:
                st.dataframe(pd.DataFrame(positions), use_container_width=True,
                             hide_index=True)
            else:
                st.info("No open positions.")
        except (MarketDataUnavailable, PaperTradingViolation, AlpacaError) as exc:
            st.error(str(exc))


# ---------------------------------------------------------------------------
with tabs[4]:
    st.subheader("Execution history")
    result = st.session_state.get("last_run")
    if result and result.submitted:
        st.dataframe(pd.DataFrame(result.submitted), use_container_width=True,
                     hide_index=True)
    else:
        st.caption("Nothing submitted in this session.")

    if have_creds and not demo_mode:
        if st.button("Fetch recent orders from Alpaca"):
            try:
                client = AlpacaClient(
                    api_key=alpaca_key, secret_key=alpaca_secret,
                    base_url=cfg.alpaca_base_url, data_url=cfg.alpaca_data_url,
                )
                orders = client.get_orders(limit=50)
                st.dataframe(pd.DataFrame(orders), use_container_width=True,
                             hide_index=True)
            except (MarketDataUnavailable, AlpacaError) as exc:
                st.error(str(exc))


# ---------------------------------------------------------------------------
with tabs[5]:
    st.subheader("Per-member daily logs")
    st.caption(
        f"Read from `{cfg.log_dir}/`. These files are committed to git by the "
        "GitHub Actions workflow so the 15-20 day history accumulates."
    )
    for sid in student_ids:
        rows = daily_log.read_rows(sid, cfg.log_dir)
        with st.expander(f"{sid} — {len(rows)} run(s)", expanded=bool(rows)):
            if not rows:
                st.caption("No runs recorded yet.")
                continue
            frame = pd.DataFrame(rows)
            for col in ("equity", "day_pl", "day_pl_pct", "total_pl", "total_pl_pct"):
                if col in frame:
                    frame[col] = pd.to_numeric(frame[col], errors="coerce")
            st.dataframe(frame, use_container_width=True, hide_index=True)
            if "equity" in frame and frame["equity"].notna().any():
                chart = frame.dropna(subset=["equity"]).set_index("date")[["equity"]]
                st.line_chart(chart)
            md_path = Path(cfg.log_dir) / f"{sid}.md"
            if md_path.exists():
                st.download_button(
                    f"Download {sid}.md", md_path.read_text(encoding="utf-8"),
                    file_name=f"{sid}.md", key=f"dl_{sid}",
                )
