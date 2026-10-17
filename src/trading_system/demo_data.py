"""Clearly-labelled SYNTHETIC data for demo mode.

Nothing here is a real price and nothing here is a real headline.  Every
structure produced carries ``"source": "DEMO_SYNTHETIC"`` and every demo
headline is prefixed ``[DEMO]`` so it cannot be mistaken for a real one
further downstream.

Demo mode must be requested explicitly.  Without credentials AND without
``DEMO_MODE=true`` the system refuses to fetch rather than inventing prices —
see ``MarketDataUnavailable`` in ``alpaca_client.py``.
"""

from __future__ import annotations

import hashlib
from datetime import datetime, timedelta, timezone
from typing import Dict, Iterable, List

import numpy as np
import pandas as pd

DEMO_SOURCE = "DEMO_SYNTHETIC"
DEMO_PREFIX = "[DEMO]"

#: Rough annualised drift / vol per archetype.  Chosen to make demo runs
#: produce a believable mix of signals, not to predict anything.
_ARCHETYPES = [
    ("uptrend", 0.35, 0.28),
    ("high_beta_uptrend", 0.55, 0.55),
    ("downtrend", -0.30, 0.32),
    ("choppy", 0.02, 0.22),
    ("high_beta_crash", -0.55, 0.70),
]


def _seed_for(symbol: str) -> int:
    return int(hashlib.sha256(symbol.encode("utf-8")).hexdigest()[:8], 16)


def synthetic_bars(symbol: str, days: int = 400, end: datetime | None = None) -> pd.DataFrame:
    """A deterministic synthetic OHLCV series for one symbol.

    Deterministic per symbol so demo runs are reproducible and reviewable.
    """
    end = end or datetime.now(timezone.utc)
    rng = np.random.default_rng(_seed_for(symbol))
    name, mu, sigma = _ARCHETYPES[_seed_for(symbol) % len(_ARCHETYPES)]
    n = max(30, int(days))
    idx = pd.bdate_range(end=pd.Timestamp(end).normalize(), periods=n, tz="UTC")

    dt = 1.0 / 252.0
    shocks = rng.normal((mu - 0.5 * sigma**2) * dt, sigma * np.sqrt(dt), n)
    start_price = 20.0 + (_seed_for(symbol) % 380)
    close = pd.Series(start_price * np.exp(np.cumsum(shocks)), index=idx)

    intraday = np.abs(rng.normal(0.0, sigma * np.sqrt(dt) * 1.4, n))
    high = close * (1.0 + intraday)
    low = close * (1.0 - intraday)
    open_ = close.shift(1).fillna(close.iloc[0]) * (1.0 + rng.normal(0, 0.003, n))
    high = np.maximum.reduce([high.to_numpy(), open_.to_numpy(), close.to_numpy()])
    low = np.minimum.reduce([low.to_numpy(), open_.to_numpy(), close.to_numpy()])
    volume = rng.lognormal(14.5, 0.45, n)

    frame = pd.DataFrame(
        {
            "open": open_.to_numpy(),
            "high": high,
            "low": low,
            "close": close.to_numpy(),
            "volume": volume,
        },
        index=idx,
    )
    frame.attrs["source"] = DEMO_SOURCE
    frame.attrs["archetype"] = name
    return frame


def synthetic_bars_batch(
    symbols: Iterable[str], days: int = 400, end: datetime | None = None
) -> Dict[str, pd.DataFrame]:
    return {s.upper(): synthetic_bars(s.upper(), days, end) for s in symbols}


#: Fixed template headlines.  These are OBVIOUSLY synthetic and are prefixed
#: with [DEMO]; the system never invents a plausible-looking real headline.
_DEMO_HEADLINE_TEMPLATES = [
    "{sym} synthetic placeholder headline: results beat internal demo expectations",
    "{sym} synthetic placeholder headline: guidance lowered in this fabricated scenario",
    "{sym} synthetic placeholder headline: analyst upgrade (not a real analyst)",
    "{sym} synthetic placeholder headline: no material news in this demo window",
    "{sym} synthetic placeholder headline: fabricated volatility warning for testing",
]


def synthetic_news(symbol: str, limit: int = 5) -> List[dict]:
    """Synthetic, obviously-fake headlines for demo mode only."""
    rng = np.random.default_rng(_seed_for(symbol) + 11)
    now = datetime.now(timezone.utc)
    out = []
    for i in range(min(limit, len(_DEMO_HEADLINE_TEMPLATES))):
        tpl = _DEMO_HEADLINE_TEMPLATES[int(rng.integers(0, len(_DEMO_HEADLINE_TEMPLATES)))]
        out.append(
            {
                "symbol": symbol.upper(),
                "headline": f"{DEMO_PREFIX} " + tpl.format(sym=symbol.upper()),
                "summary": f"{DEMO_PREFIX} Synthetic text generated for demo mode. Not real news.",
                "created_at": (now - timedelta(hours=3 * (i + 1))).isoformat(),
                "source": DEMO_SOURCE,
                "url": "",
            }
        )
    return out


def synthetic_account(starting_equity: float = 100_000.0) -> dict:
    """A plausible but clearly-labelled synthetic account snapshot."""
    return {
        "source": DEMO_SOURCE,
        "account_number": "DEMO-ACCOUNT",
        "status": "ACTIVE",
        "currency": "USD",
        "equity": starting_equity,
        "last_equity": starting_equity,
        "cash": starting_equity,
        "buying_power": starting_equity * 2.0,
        "portfolio_value": starting_equity,
        "pattern_day_trader": False,
        "trading_blocked": False,
    }
