"""Thin Alpaca REST client: market data, news, account, positions, orders.

Design notes
------------
* **Batched OHLCV.** ``get_bars`` sends ONE request covering every symbol
  (``?symbols=AAPL,MSFT,...``).  Alpaca paginates large responses, so a long
  lookback over 45 symbols can span a few pages, but there is never one
  request per symbol.  ``last_request_count`` records how many HTTP calls a
  fetch actually took so tests can assert it.
* **Paper only.** Every order passes both guards in ``paper_guard`` — the
  hostname is validated by parsing, and the URL about to be requested is
  re-checked against an independent allowlist immediately before the POST.
* **No invention.** Without credentials and without demo mode the client
  raises ``MarketDataUnavailable`` instead of returning made-up prices.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Dict, Iterable, List, Optional, Sequence

import pandas as pd
import requests

from .config import clean
from .demo_data import (
    DEMO_SOURCE,
    synthetic_account,
    synthetic_bars_batch,
    synthetic_news,
)
from .paper_guard import assert_paper_mode, validate_paper_endpoint

log = logging.getLogger(__name__)

DEFAULT_DATA_URL = "https://data.alpaca.markets"
#: Alpaca caps the symbols-per-request on the multi-bar endpoint.  Chunking
#: at this size is still batched — 45 symbols is one request.
MAX_SYMBOLS_PER_REQUEST = 100


class MarketDataUnavailable(RuntimeError):
    """Raised instead of inventing data when there are no credentials.

    The system never fabricates prices or headlines.  Either supply Alpaca
    credentials, or opt in to clearly-labelled synthetic data with
    ``DEMO_MODE=true``.
    """


class AlpacaError(RuntimeError):
    """An Alpaca API call failed."""


@dataclass
class AlpacaClient:
    api_key: str = ""
    secret_key: str = ""
    base_url: str = "https://paper-api.alpaca.markets"
    data_url: str = DEFAULT_DATA_URL
    demo_mode: bool = False
    timeout: int = 30
    max_retries: int = 4
    starting_equity: float = 100_000.0
    session: Optional[requests.Session] = None
    last_request_count: int = 0
    notes: List[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        # Whitespace from a pasted key or a form field is stripped here, once.
        self.api_key = clean(self.api_key)
        self.secret_key = clean(self.secret_key)
        self.data_url = clean(self.data_url) or DEFAULT_DATA_URL
        # GUARD 1: parse the hostname and require an exact match over https.
        self.base_url = validate_paper_endpoint(clean(self.base_url))
        self.session = self.session or requests.Session()

    # ------------------------------------------------------------------
    @property
    def live(self) -> bool:
        """True when real credentials are present and demo mode is off."""
        return bool(self.api_key and self.secret_key) and not self.demo_mode

    @property
    def data_source(self) -> str:
        if self.demo_mode:
            return DEMO_SOURCE
        return "ALPACA_LIVE" if self.live else "UNAVAILABLE"

    def _require_data_access(self, what: str) -> None:
        if self.demo_mode or self.live:
            return
        raise MarketDataUnavailable(
            f"Refusing to produce {what} with no Alpaca credentials. "
            "This system never invents prices or headlines. Set "
            "ALPACA_API_KEY/ALPACA_SECRET_KEY, or set DEMO_MODE=true to use "
            "clearly-labelled synthetic data."
        )

    def _headers(self) -> Dict[str, str]:
        return {
            "APCA-API-KEY-ID": self.api_key,
            "APCA-API-SECRET-KEY": self.secret_key,
            "accept": "application/json",
        }

    def _request(self, method: str, url: str, **kwargs) -> dict:
        """One HTTP call with bounded retries on 429 / 5xx."""
        self.last_request_count += 1
        delay = 1.0
        last_err: Optional[Exception] = None
        for attempt in range(self.max_retries + 1):
            try:
                resp = self.session.request(
                    method,
                    url,
                    headers=self._headers(),
                    timeout=self.timeout,
                    **kwargs,
                )
            except requests.RequestException as exc:  # network blip
                last_err = exc
                if attempt >= self.max_retries:
                    raise AlpacaError(f"{method} {url} failed: {exc}") from exc
                time.sleep(delay)
                delay = min(delay * 2, 16.0)
                continue

            if resp.status_code == 429 or resp.status_code >= 500:
                retry_after = resp.headers.get("Retry-After")
                wait = float(retry_after) if (retry_after or "").strip().isdigit() else delay
                last_err = AlpacaError(f"{resp.status_code} from {url}: {resp.text[:300]}")
                if attempt >= self.max_retries:
                    raise last_err
                log.warning(
                    "Alpaca %s -> %s, retrying in %.1fs (attempt %d/%d)",
                    url,
                    resp.status_code,
                    wait,
                    attempt + 1,
                    self.max_retries,
                )
                time.sleep(wait)
                delay = min(delay * 2, 16.0)
                continue

            if resp.status_code >= 400:
                raise AlpacaError(
                    f"{method} {url} -> HTTP {resp.status_code}: {resp.text[:400]}"
                )
            if not resp.content:
                return {}
            try:
                return resp.json()
            except ValueError as exc:
                raise AlpacaError(f"non-JSON response from {url}: {resp.text[:200]}") from exc
        raise AlpacaError(str(last_err) if last_err else f"{method} {url} failed")

    # ------------------------------------------------------------------
    # Market data
    # ------------------------------------------------------------------
    def get_bars(
        self,
        symbols: Sequence[str],
        days: int = 400,
        timeframe: str = "1Day",
        feed: str = "iex",
    ) -> Dict[str, pd.DataFrame]:
        """Daily OHLCV for EVERY symbol in ONE request (plus pagination pages).

        Returns ``{symbol: DataFrame}`` with a UTC DatetimeIndex and columns
        open/high/low/close/volume.
        """
        syms = [clean(s).upper() for s in symbols if clean(s)]
        syms = list(dict.fromkeys(syms))
        if not syms:
            return {}
        self._require_data_access("OHLCV bars")
        self.last_request_count = 0

        if self.demo_mode:
            self.notes.append(f"{DEMO_SOURCE}: synthetic bars for {len(syms)} symbols")
            return synthetic_bars_batch(syms, days)

        end = datetime.now(timezone.utc) - timedelta(minutes=16)  # free-feed delay
        start = end - timedelta(days=int(days) * 2 + 10)  # calendar -> trading days
        frames: Dict[str, List[dict]] = {s: [] for s in syms}

        for chunk_start in range(0, len(syms), MAX_SYMBOLS_PER_REQUEST):
            chunk = syms[chunk_start : chunk_start + MAX_SYMBOLS_PER_REQUEST]
            params = {
                "symbols": ",".join(chunk),  # <- ALL symbols, ONE request
                "timeframe": timeframe,
                "start": start.strftime("%Y-%m-%dT%H:%M:%SZ"),
                "end": end.strftime("%Y-%m-%dT%H:%M:%SZ"),
                "limit": 10000,
                "adjustment": "all",
                "feed": feed,
                "sort": "asc",
            }
            page_token = None
            while True:
                if page_token:
                    params["page_token"] = page_token
                payload = self._request(
                    "GET", f"{self.data_url}/v2/stocks/bars", params=params
                )
                for sym, bars in (payload.get("bars") or {}).items():
                    frames.setdefault(sym.upper(), []).extend(bars or [])
                page_token = payload.get("next_page_token")
                if not page_token:
                    break

        out: Dict[str, pd.DataFrame] = {}
        for sym, bars in frames.items():
            if not bars:
                continue
            df = pd.DataFrame(bars)
            rename = {"t": "timestamp", "o": "open", "h": "high", "l": "low", "c": "close", "v": "volume"}
            df = df.rename(columns=rename)
            if "timestamp" not in df.columns:
                continue
            df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True, format="mixed")
            df = df.set_index("timestamp").sort_index()
            keep = [c for c in ("open", "high", "low", "close", "volume") if c in df.columns]
            df = df[keep].astype("float64")
            df = df[~df.index.duplicated(keep="last")].tail(int(days))
            df.attrs["source"] = "ALPACA_LIVE"
            out[sym] = df

        missing = sorted(set(syms) - set(out))
        if missing:
            self.notes.append(f"no bars returned for: {', '.join(missing)}")
        self.notes.append(
            f"fetched bars for {len(out)}/{len(syms)} symbols in "
            f"{self.last_request_count} HTTP request(s)"
        )
        return out

    def get_news(self, symbols: Sequence[str], hours: int = 48, limit: int = 50) -> List[dict]:
        """Recent news for all symbols in ONE request.  Never fabricated."""
        syms = [clean(s).upper() for s in symbols if clean(s)]
        syms = list(dict.fromkeys(syms))
        if not syms:
            return []
        self._require_data_access("news headlines")
        if self.demo_mode:
            out: List[dict] = []
            for s in syms:
                out.extend(synthetic_news(s, limit=3))
            return out

        start = datetime.now(timezone.utc) - timedelta(hours=int(hours))
        params = {
            "symbols": ",".join(syms),
            "start": start.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "limit": int(limit),
            "sort": "desc",
            "include_content": "false",
        }
        try:
            payload = self._request("GET", f"{self.data_url}/v1beta1/news", params=params)
        except AlpacaError as exc:
            self.notes.append(f"news unavailable ({exc}); sentiment treated as neutral")
            return []
        out = []
        for item in payload.get("news") or []:
            out.append(
                {
                    "symbol": ",".join(item.get("symbols") or []),
                    "headline": clean(item.get("headline")),
                    "summary": clean(item.get("summary"))[:400],
                    "created_at": clean(item.get("created_at")),
                    "source": clean(item.get("source")) or "alpaca",
                    "url": clean(item.get("url")),
                }
            )
        return out

    # ------------------------------------------------------------------
    # Account / positions / orders
    # ------------------------------------------------------------------
    def get_account(self) -> dict:
        if self.demo_mode:
            return synthetic_account(self.starting_equity)
        self._require_data_access("an account snapshot")
        raw = self._request("GET", f"{self.base_url}/v2/account")
        numeric = (
            "equity",
            "last_equity",
            "cash",
            "buying_power",
            "portfolio_value",
            "long_market_value",
            "short_market_value",
            "daytrading_buying_power",
            "regt_buying_power",
        )
        out = {"source": "ALPACA_LIVE"}
        for k, v in raw.items():
            out[k] = float(v) if k in numeric and v not in (None, "") else v
        return out

    def get_positions(self) -> List[dict]:
        if self.demo_mode:
            return []
        self._require_data_access("positions")
        raw = self._request("GET", f"{self.base_url}/v2/positions")
        if not isinstance(raw, list):
            return []
        out = []
        for p in raw:
            out.append(
                {
                    "symbol": clean(p.get("symbol")).upper(),
                    "qty": float(p.get("qty") or 0.0),
                    "side": clean(p.get("side")),
                    "avg_entry_price": float(p.get("avg_entry_price") or 0.0),
                    "current_price": float(p.get("current_price") or 0.0),
                    "market_value": float(p.get("market_value") or 0.0),
                    "cost_basis": float(p.get("cost_basis") or 0.0),
                    "unrealized_pl": float(p.get("unrealized_pl") or 0.0),
                    "unrealized_plpc": float(p.get("unrealized_plpc") or 0.0),
                }
            )
        return out

    def get_orders(self, status: str = "all", limit: int = 100) -> List[dict]:
        if self.demo_mode:
            return []
        self._require_data_access("orders")
        raw = self._request(
            "GET",
            f"{self.base_url}/v2/orders",
            params={"status": status, "limit": int(limit), "direction": "desc"},
        )
        return raw if isinstance(raw, list) else []

    def submit_order(
        self,
        symbol: str,
        qty: float,
        side: str,
        client_order_id: str,
        order_type: str = "market",
        time_in_force: str = "day",
        limit_price: Optional[float] = None,
    ) -> dict:
        """Submit a PAPER order.  Both guards run immediately before the POST."""
        url = f"{self.base_url}/v2/orders"
        # GUARD 2: independent re-check of the URL actually about to be used.
        assert_paper_mode(url)

        body = {
            "symbol": clean(symbol).upper(),
            "qty": str(round(float(qty), 6)),
            "side": clean(side).lower(),
            "type": clean(order_type).lower(),
            "time_in_force": clean(time_in_force).lower(),
            "client_order_id": clean(client_order_id)[:48],
        }
        if limit_price is not None:
            body["limit_price"] = str(round(float(limit_price), 2))

        if self.demo_mode:
            return {
                "source": DEMO_SOURCE,
                "status": "accepted_demo",
                "submitted": False,
                "note": "demo mode: order NOT sent to Alpaca",
                **body,
            }
        if not self.live:
            raise MarketDataUnavailable(
                "Refusing to submit an order without Alpaca credentials."
            )

        try:
            raw = self._request("POST", url, json=body)
        except AlpacaError as exc:
            msg = str(exc)
            # A duplicate client_order_id means this exact order already
            # exists — that is the dedupe working, not a failure.
            if "client_order_id" in msg and ("exists" in msg or "409" in msg):
                return {
                    "status": "duplicate_suppressed",
                    "submitted": False,
                    "note": "an order with this client_order_id already exists",
                    **body,
                }
            raise
        return {
            "source": "ALPACA_LIVE",
            "submitted": True,
            "id": raw.get("id"),
            "status": raw.get("status"),
            "filled_qty": raw.get("filled_qty"),
            **body,
        }


def build_client(cfg, student, demo_override: Optional[bool] = None) -> AlpacaClient:
    """Construct a client for one student from an AppConfig."""
    key, secret = student.credentials()
    demo = cfg.demo_mode if demo_override is None else bool(demo_override)
    return AlpacaClient(
        api_key=key,
        secret_key=secret,
        base_url=cfg.alpaca_base_url,
        data_url=cfg.alpaca_data_url,
        demo_mode=demo,
        starting_equity=student.starting_equity,
    )
