"""The two paper-trading guards, including the hostile-hostname cases."""

import pytest

from trading_system.paper_guard import (
    ALLOWED_PAPER_URLS,
    PAPER_HOST,
    PaperTradingViolation,
    assert_paper_mode,
    is_paper_endpoint,
    validate_paper_endpoint,
)

#: Every one of these CONTAINS the paper hostname as a substring, or otherwise
#: looks safe at a glance, and every one of them routes orders somewhere else.
HOSTILE_URLS = [
    # The case named in the brief: the paper host is in the PATH.
    "https://evil.test/paper-api.alpaca.markets",
    "https://evil.test/paper-api.alpaca.markets/v2/orders",
    # Suffix attack: the real host is evil.test.
    "https://paper-api.alpaca.markets.evil.test",
    "https://paper-api.alpaca.markets.evil.test/v2/orders",
    # Userinfo attack: urlparse resolves the host to evil.test.
    "https://paper-api.alpaca.markets@evil.test",
    "https://user:pass@paper-api.alpaca.markets.evil.test",
    # Prefix attack.
    "https://notpaper-api.alpaca.markets",
    "https://xpaper-api.alpaca.markets",
    # In the query string.
    "https://evil.test/?host=paper-api.alpaca.markets",
    "https://evil.test#paper-api.alpaca.markets",
    # Downgraded scheme — a MITM can read the keys.
    "http://paper-api.alpaca.markets",
    "ftp://paper-api.alpaca.markets",
    "//paper-api.alpaca.markets",
    # Non-default port.
    "https://paper-api.alpaca.markets:8443",
    "https://paper-api.alpaca.markets:80",
    # LIVE trading — real money.
    "https://api.alpaca.markets",
    "https://api.alpaca.markets/v2/orders",
    # Empty / nonsense.
    "",
    "   ",
    "not-a-url",
    "https://",
]


class TestGuardOneHostnameParsing:
    @pytest.mark.parametrize("url", HOSTILE_URLS)
    def test_hostile_urls_are_rejected(self, url):
        with pytest.raises(PaperTradingViolation):
            validate_paper_endpoint(url)
        assert is_paper_endpoint(url) is False

    def test_the_substring_trap_specifically(self):
        """A naive `if 'paper-api.alpaca.markets' in url` accepts this one."""
        url = "https://evil.test/paper-api.alpaca.markets"
        assert PAPER_HOST in url, "this URL does contain the paper hostname"
        with pytest.raises(PaperTradingViolation, match="host must be exactly"):
            validate_paper_endpoint(url)

    def test_none_is_rejected(self):
        with pytest.raises(PaperTradingViolation):
            validate_paper_endpoint(None)

    @pytest.mark.parametrize(
        "url",
        [
            "https://paper-api.alpaca.markets",
            "https://paper-api.alpaca.markets/",
            "  https://paper-api.alpaca.markets  ",
            "https://paper-api.alpaca.markets\n",
            "https://PAPER-API.ALPACA.MARKETS",
            "https://paper-api.alpaca.markets:443",
        ],
    )
    def test_the_real_paper_endpoint_is_accepted_and_normalised(self, url):
        assert validate_paper_endpoint(url) == "https://paper-api.alpaca.markets"

    def test_the_live_endpoint_gets_its_own_message(self):
        with pytest.raises(PaperTradingViolation, match="LIVE Alpaca endpoint"):
            validate_paper_endpoint("https://api.alpaca.markets")


class TestGuardTwoIndependentRecheck:
    def test_allows_the_paper_order_url(self):
        assert_paper_mode("https://paper-api.alpaca.markets/v2/orders")

    @pytest.mark.parametrize(
        "url",
        [
            "https://evil.test/v2/orders",
            "https://evil.test/paper-api.alpaca.markets/v2/orders",
            "https://paper-api.alpaca.markets.evil.test/v2/orders",
            "https://paper-api.alpaca.markets@evil.test/v2/orders",
            "http://paper-api.alpaca.markets/v2/orders",
            "https://paper-api.alpaca.markets:8443/v2/orders",
            "https://api.alpaca.markets/v2/orders",
            "",
        ],
    )
    def test_blocks_everything_else(self, url):
        with pytest.raises(PaperTradingViolation):
            assert_paper_mode(url)

    def test_refuses_when_live_trading_is_flagged_on(self, monkeypatch):
        monkeypatch.setenv("ALLOW_LIVE_TRADING", "true")
        with pytest.raises(PaperTradingViolation, match="does not support live trading"):
            assert_paper_mode("https://paper-api.alpaca.markets/v2/orders")

    def test_the_two_guards_are_independent(self):
        """Guard 2 uses its own allowlist, not guard 1's hostname comparison."""
        assert isinstance(ALLOWED_PAPER_URLS, frozenset)
        assert all(u.startswith("https://paper-api.alpaca.markets") for u in ALLOWED_PAPER_URLS)


class TestClientIsGuarded:
    def test_client_construction_rejects_a_hostile_base_url(self):
        from trading_system.alpaca_client import AlpacaClient

        with pytest.raises(PaperTradingViolation):
            AlpacaClient(base_url="https://evil.test/paper-api.alpaca.markets")

    def test_client_cannot_be_pointed_at_live(self):
        from trading_system.alpaca_client import AlpacaClient

        with pytest.raises(PaperTradingViolation):
            AlpacaClient(base_url="https://api.alpaca.markets")

    def test_order_submission_is_blocked_if_the_base_url_is_mutated(self):
        """Guard 2 catches a base_url swapped AFTER construction."""
        from trading_system.alpaca_client import AlpacaClient

        client = AlpacaClient(api_key="k", secret_key="s")
        client.base_url = "https://evil.test"  # bypasses guard 1 entirely
        with pytest.raises(PaperTradingViolation):
            client.submit_order("AAPL", 1, "buy", "coid-1")
