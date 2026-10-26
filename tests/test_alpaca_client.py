"""Alpaca client: batching, refusal-to-invent, and the order guards."""

import json

import pytest

from trading_system.alpaca_client import AlpacaClient, AlpacaError, MarketDataUnavailable
from trading_system.demo_data import DEMO_PREFIX, DEMO_SOURCE
from trading_system.paper_guard import PaperTradingViolation


class FakeResponse:
    def __init__(self, payload, status=200, headers=None):
        self._payload = payload
        self.status_code = status
        self.headers = headers or {}
        self.content = json.dumps(payload).encode()
        self.text = json.dumps(payload)

    def json(self):
        return self._payload


class RecordingSession:
    """Captures every request and replays canned responses."""

    def __init__(self, responses=None):
        self.calls = []
        self.responses = list(responses or [])

    def request(self, method, url, **kwargs):
        self.calls.append({"method": method, "url": url, **kwargs})
        if self.responses:
            return self.responses.pop(0)
        return FakeResponse({})


def bars_payload(symbols, n=5):
    return {
        "bars": {
            s: [
                {
                    "t": f"2026-01-{d + 1:02d}T00:00:00Z",
                    "o": 100.0 + d, "h": 101.0 + d, "l": 99.0 + d,
                    "c": 100.5 + d, "v": 1_000_000.0,
                }
                for d in range(n)
            ]
            for s in symbols
        },
        "next_page_token": None,
    }


class TestBatching:
    def test_all_symbols_go_out_in_one_request(self):
        symbols = [f"SYM{i}" for i in range(45)]
        session = RecordingSession([FakeResponse(bars_payload(symbols))])
        client = AlpacaClient(api_key="k", secret_key="s", session=session)
        client.get_bars(symbols, days=30)

        assert len(session.calls) == 1, (
            f"expected ONE batched request, got {len(session.calls)} "
            "(never one call per symbol)"
        )
        sent = session.calls[0]["params"]["symbols"].split(",")
        assert sorted(sent) == sorted(symbols)
        assert client.last_request_count == 1

    def test_pagination_adds_pages_not_per_symbol_calls(self):
        symbols = ["AAA", "BBB"]
        page1 = bars_payload(symbols, 3)
        page1["next_page_token"] = "tok"
        session = RecordingSession([FakeResponse(page1), FakeResponse(bars_payload(symbols, 2))])
        client = AlpacaClient(api_key="k", secret_key="s", session=session)
        client.get_bars(symbols, days=30)
        assert len(session.calls) == 2
        for call in session.calls:
            assert len(call["params"]["symbols"].split(",")) == 2

    def test_news_is_one_request_for_all_symbols(self):
        session = RecordingSession([FakeResponse({"news": []})])
        client = AlpacaClient(api_key="k", secret_key="s", session=session)
        client.get_news(["AAA", "BBB", "CCC"])
        assert len(session.calls) == 1
        assert session.calls[0]["params"]["symbols"] == "AAA,BBB,CCC"

    def test_duplicate_symbols_are_collapsed(self):
        session = RecordingSession([FakeResponse(bars_payload(["AAA"]))])
        client = AlpacaClient(api_key="k", secret_key="s", session=session)
        client.get_bars(["AAA", "aaa", "AAA"], days=30)
        assert session.calls[0]["params"]["symbols"] == "AAA"

    def test_frames_come_back_with_the_expected_columns(self):
        session = RecordingSession([FakeResponse(bars_payload(["AAA"], 5))])
        client = AlpacaClient(api_key="k", secret_key="s", session=session)
        frames = client.get_bars(["AAA"], days=30)
        assert list(frames["AAA"].columns) == ["open", "high", "low", "close", "volume"]
        assert str(frames["AAA"].index.tz) == "UTC"

    def test_empty_symbol_list_makes_no_request(self):
        session = RecordingSession()
        client = AlpacaClient(api_key="k", secret_key="s", session=session)
        assert client.get_bars([]) == {}
        assert session.calls == []


class TestRefusalToInvent:
    def test_no_credentials_and_no_demo_refuses_bars(self):
        client = AlpacaClient()
        with pytest.raises(MarketDataUnavailable, match="never invents"):
            client.get_bars(["AAPL"])

    def test_no_credentials_and_no_demo_refuses_news(self):
        with pytest.raises(MarketDataUnavailable):
            AlpacaClient().get_news(["AAPL"])

    def test_no_credentials_and_no_demo_refuses_the_account(self):
        with pytest.raises(MarketDataUnavailable):
            AlpacaClient().get_account()

    def test_no_credentials_and_no_demo_refuses_orders(self):
        with pytest.raises(MarketDataUnavailable):
            AlpacaClient().submit_order("AAPL", 1, "buy", "coid")

    def test_demo_mode_is_explicit_and_labelled(self):
        client = AlpacaClient(demo_mode=True)
        assert client.data_source == DEMO_SOURCE
        frames = client.get_bars(["AAPL"], days=100)
        assert frames["AAPL"].attrs["source"] == DEMO_SOURCE
        assert client.get_account()["source"] == DEMO_SOURCE

    def test_demo_headlines_are_obviously_fake(self):
        for article in AlpacaClient(demo_mode=True).get_news(["AAPL"]):
            assert article["headline"].startswith(DEMO_PREFIX)
            assert article["source"] == DEMO_SOURCE

    def test_demo_mode_never_sends_an_order(self):
        session = RecordingSession()
        client = AlpacaClient(demo_mode=True, session=session)
        result = client.submit_order("AAPL", 1, "buy", "coid")
        assert result["submitted"] is False
        assert session.calls == []


class TestOrdering:
    def test_a_real_order_posts_to_the_paper_endpoint(self):
        session = RecordingSession([FakeResponse({"id": "abc", "status": "accepted"})])
        client = AlpacaClient(api_key="k", secret_key="s", session=session)
        out = client.submit_order("AAPL", 2.5, "buy", "coid-1")
        call = session.calls[0]
        assert call["method"] == "POST"
        assert call["url"] == "https://paper-api.alpaca.markets/v2/orders"
        assert call["json"]["client_order_id"] == "coid-1"
        assert call["json"]["qty"] == "2.5"
        assert out["submitted"] is True

    def test_keys_are_stripped_before_they_reach_the_headers(self):
        session = RecordingSession([FakeResponse({"id": "a"})])
        client = AlpacaClient(api_key=" k \n", secret_key=" s \n", session=session)
        client.submit_order("AAPL", 1, "buy", "coid")
        headers = session.calls[0].get("headers") or client._headers()
        assert headers["APCA-API-KEY-ID"] == "k"
        assert headers["APCA-API-SECRET-KEY"] == "s"

    def test_a_duplicate_client_order_id_is_reported_not_raised(self):
        session = RecordingSession(
            [FakeResponse({"message": "client_order_id already exists"}, status=422)]
        )
        client = AlpacaClient(api_key="k", secret_key="s", session=session, max_retries=0)
        out = client.submit_order("AAPL", 1, "buy", "coid")
        assert out["status"] == "duplicate_suppressed"
        assert out["submitted"] is False

    def test_a_mutated_base_url_is_blocked_by_guard_two(self):
        client = AlpacaClient(api_key="k", secret_key="s", session=RecordingSession())
        client.base_url = "https://evil.test"
        with pytest.raises(PaperTradingViolation):
            client.submit_order("AAPL", 1, "buy", "coid")


class TestRetries:
    def test_429_is_retried_honouring_retry_after(self, monkeypatch):
        slept = []
        monkeypatch.setattr("trading_system.alpaca_client.time.sleep", slept.append)
        session = RecordingSession(
            [
                FakeResponse({"message": "rate limited"}, 429, {"Retry-After": "3"}),
                FakeResponse(bars_payload(["AAA"])),
            ]
        )
        client = AlpacaClient(api_key="k", secret_key="s", session=session)
        frames = client.get_bars(["AAA"], days=30)
        assert "AAA" in frames
        assert slept == [3.0]

    def test_a_4xx_that_is_not_429_raises_immediately(self):
        session = RecordingSession([FakeResponse({"message": "forbidden"}, 403)])
        client = AlpacaClient(api_key="k", secret_key="s", session=session)
        with pytest.raises(AlpacaError, match="403"):
            client.get_bars(["AAA"], days=30)
        assert len(session.calls) == 1


class TestOrderHistoryPaging:
    """The backfill needs EVERY past order, but /v2/orders returns at most a
    page at a time, so it has to page backwards with `until`."""

    def client(self, orders, page_size_seen):
        from trading_system.alpaca_client import AlpacaClient

        c = AlpacaClient(
            api_key="k", secret_key="s",
            base_url="https://paper-api.alpaca.markets",
            data_url="https://data.alpaca.markets",
        )

        def fake_request(method, url, **kwargs):
            params = kwargs.get("params", {})
            page_size_seen.append(int(params["limit"]))
            rows = sorted(orders, key=lambda o: o["submitted_at"], reverse=True)
            if params.get("until"):
                rows = [o for o in rows if o["submitted_at"] < params["until"]]
            return rows[: int(params["limit"])]

        c._request = fake_request
        return c

    def orders(self, count):
        return [
            {"id": f"ord-{n}", "symbol": "NVDA", "side": "buy",
             "submitted_at": f"2026-10-{20 + n // 24:02d}T{n % 24:02d}:00:00Z"}
            for n in range(count)
        ]

    def test_it_pages_until_everything_is_collected(self):
        seen = []
        orders = self.orders(10)
        got = self.client(orders, seen).get_order_history(page_size=3)
        assert len(got) == 10
        assert {o["id"] for o in got} == {o["id"] for o in orders}
        assert len(seen) > 1, "one page means it never paged"

    def test_the_result_is_oldest_first(self):
        got = self.client(self.orders(10), []).get_order_history(page_size=3)
        stamps = [o["submitted_at"] for o in got]
        assert stamps == sorted(stamps)

    def test_a_single_short_page_stops_immediately(self):
        seen = []
        got = self.client(self.orders(2), seen).get_order_history(page_size=500)
        assert len(got) == 2 and len(seen) == 1

    def test_no_orders_is_not_an_error(self):
        assert self.client([], []).get_order_history() == []

    def test_a_stuck_cursor_cannot_loop_forever(self):
        """Two orders sharing a timestamp would otherwise page endlessly,
        because `until` can never move past them."""
        from trading_system.alpaca_client import AlpacaClient

        same = [
            {"id": f"ord-{n}", "symbol": "NVDA", "submitted_at": "2026-10-20T14:00:00Z"}
            for n in range(5)
        ]
        c = AlpacaClient(api_key="k", secret_key="s",
                         base_url="https://paper-api.alpaca.markets",
                         data_url="https://data.alpaca.markets")
        calls = []

        def fake_request(method, url, **kwargs):
            calls.append(1)
            assert len(calls) < 50, "it paged forever"
            return same[:2]

        c._request = fake_request
        got = c.get_order_history(page_size=2)
        assert len(got) == 2

    def test_demo_mode_reads_nothing(self):
        from trading_system.alpaca_client import AlpacaClient

        c = AlpacaClient(api_key="", secret_key="",
                         base_url="https://paper-api.alpaca.markets",
                         data_url="https://data.alpaca.markets", demo_mode=True)
        assert c.get_order_history() == []
