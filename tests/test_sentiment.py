"""News sentiment: lexicon scoring, negation, and the no-fabrication policy."""

import pytest

from trading_system.sentiment import (
    NO_DATA,
    analyse_batch,
    analyse_symbol,
    label_for,
    score_text,
)


def article(symbol, headline, summary=""):
    return {"symbol": symbol, "headline": headline, "summary": summary,
            "source": "test", "created_at": "2026-01-01T00:00:00Z"}


class TestLexicon:
    def test_positive_headline_scores_positive(self):
        score, hits = score_text("Shares surge after the company beats estimates")
        assert score > 0 and hits

    def test_negative_headline_scores_negative(self):
        score, _ = score_text("Stock plunges on an SEC probe and a downgrade")
        assert score < 0

    def test_negation_flips_the_polarity(self):
        plain, _ = score_text("company beats estimates")
        negated, _ = score_text("company does not beat estimates")
        assert plain > 0 > negated

    def test_intensifier_amplifies(self):
        plain, _ = score_text("shares decline")
        sharp, _ = score_text("shares sharply decline")
        assert sharp < plain

    def test_neutral_text_scores_zero(self):
        assert score_text("The company will hold its annual meeting") == (0.0, [])

    def test_empty_text_is_safe(self):
        assert score_text("") == (0.0, [])
        assert score_text(None) == (0.0, [])

    @pytest.mark.parametrize(
        "score,label",
        [(0.9, "BULLISH"), (0.2, "MILDLY_BULLISH"), (0.0, "NEUTRAL"),
         (-0.2, "MILDLY_BEARISH"), (-0.9, "BEARISH")],
    )
    def test_labels(self, score, label):
        assert label_for(score) == label


class TestAggregation:
    def test_bullish_cluster(self):
        arts = [
            article("AAPL", "Apple beats estimates and raises guidance"),
            article("AAPL", "Analyst upgrade on record demand"),
            article("AAPL", "Shares rally to a record high"),
        ]
        r = analyse_symbol("AAPL", arts)
        assert r.label in {"BULLISH", "MILDLY_BULLISH"}
        assert r.has_data and r.article_count == 3

    def test_bearish_cluster(self):
        arts = [
            article("XYZ", "XYZ plunges after a profit warning"),
            article("XYZ", "Downgrade follows the disappointing results"),
        ]
        assert analyse_symbol("XYZ", arts).score < 0

    def test_score_is_bounded(self):
        arts = [article("X", "surge soar rally upgrade record breakthrough")] * 20
        assert -1.0 <= analyse_symbol("X", arts).score <= 1.0

    def test_confidence_scales_with_article_count(self):
        one = analyse_symbol("A", [article("A", "shares surge on a record upgrade")])
        many = analyse_symbol(
            "A", [article("A", "shares surge on a record upgrade")] * 6
        )
        assert many.score > one.score

    def test_only_the_symbols_own_articles_count(self):
        arts = [article("MSFT", "MSFT plunges after a fraud probe")]
        assert analyse_symbol("AAPL", arts).has_data is False

    def test_multi_symbol_articles_are_matched(self):
        arts = [article("AAPL,MSFT", "Both beat estimates and surge")]
        assert analyse_symbol("MSFT", arts).has_data is True

    def test_max_articles_is_respected(self):
        arts = [article("A", "shares surge")] * 50
        assert analyse_symbol("A", arts, max_articles=5).article_count == 5


class TestNoFabrication:
    def test_no_news_is_reported_as_no_data_not_guessed(self):
        r = analyse_symbol("ZZZZ", [])
        assert r.has_data is False
        assert r.source == NO_DATA
        assert r.score == 0.0
        assert r.headlines == []

    def test_batch_marks_every_missing_symbol(self):
        out = analyse_batch(["AAA", "BBB"], [article("AAA", "beats estimates")])
        assert out["AAA"].has_data is True
        assert out["BBB"].has_data is False and out["BBB"].source == NO_DATA

    def test_the_result_only_echoes_supplied_headlines(self):
        arts = [article("A", "A specific headline that was supplied")]
        r = analyse_symbol("A", arts)
        assert r.headlines == ["A specific headline that was supplied"]
