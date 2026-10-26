"""The deterministic rule engine.

This produces the SAME decisions with no LLM involved at all.  It is not a
degraded mode bolted on as an afterthought — it is the reference
implementation, and the agent crew is an interpretive layer on top of it.
Whenever the LLM is unavailable, unauthorised, rate-limited, or returns empty
content, the pipeline falls back here and ANNOUNCES it: every fallback is
written to the run log, printed to stdout and recorded in the per-member daily
log's ``engine`` column.  There is no silent fallback.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Dict, List, Mapping, Optional, Sequence

import pandas as pd

from .config import AppConfig, StudentConfig
from .features import FeatureSet, extract_features
from .scoring import Signal, score_featureset
from .sentiment import SentimentResult, analyse_batch

log = logging.getLogger(__name__)

ENGINE_NAME = "deterministic_rule_engine"


@dataclass
class RuleEngineResult:
    engine: str = ENGINE_NAME
    signals: List[Signal] = field(default_factory=list)
    features: Dict[str, FeatureSet] = field(default_factory=dict)
    sentiment: Dict[str, SentimentResult] = field(default_factory=dict)
    skipped: Dict[str, str] = field(default_factory=dict)
    notes: List[str] = field(default_factory=list)

    @property
    def counts(self) -> Dict[str, int]:
        out = {"BUY": 0, "SELL": 0, "HOLD": 0}
        for s in self.signals:
            out[s.action] = out.get(s.action, 0) + 1
        return out

    def by_symbol(self) -> Dict[str, Signal]:
        return {s.symbol: s for s in self.signals}

    def atr_map(self) -> Dict[str, float]:
        """ATR per symbol, for stop and target sizing.

        Reads ``diagnostics``, not ``values``: ATR is carried as a diagnostic
        because it has no direction and is not scored. Reading the wrong one
        silently yields NaN, and the risk module then falls back to a flat 2%
        band — a stop that looks real and is not.
        """
        return {
            sym: fs.diagnostics.get("atr14", float("nan"))
            for sym, fs in self.features.items()
        }

    def intraday_atr_map(self) -> Dict[str, float]:
        """Intraday ATR where 15-minute bars were available.

        Tighter than the daily ATR, which is what the intraday playbook asks
        for. Falls back to the daily value per symbol when absent.
        """
        out: Dict[str, float] = {}
        for sym, fs in self.features.items():
            value = fs.diagnostics.get("atr_intraday", float("nan"))
            out[sym] = value if value == value else fs.diagnostics.get("atr14", float("nan"))
        return out

    def beta_map(self) -> Dict[str, float]:
        """Beta per symbol, for volatility-adjusted position sizing."""
        return {
            sym: fs.diagnostics.get("beta60", float("nan"))
            for sym, fs in self.features.items()
        }

    def natr_map(self) -> Dict[str, float]:
        """Normalised ATR (percent of price) per symbol, for sizing."""
        return {
            sym: fs.values.get("natr14", float("nan"))
            for sym, fs in self.features.items()
        }

    def price_map(self) -> Dict[str, float]:
        return {sym: fs.close for sym, fs in self.features.items()}

    def to_dict(self) -> dict:
        return {
            "engine": self.engine,
            "counts": self.counts,
            "signals": [s.to_dict() for s in self.signals],
            "sentiment": {k: v.to_dict() for k, v in self.sentiment.items()},
            "skipped": self.skipped,
            "notes": self.notes,
        }


def run_rule_engine(
    symbols: Sequence[str],
    bars: Mapping[str, pd.DataFrame],
    articles: Sequence[Mapping] = (),
    cfg: Optional[AppConfig] = None,
    benchmarks: Optional[Mapping[str, pd.DataFrame]] = None,
    intraday: Optional[Mapping[str, pd.DataFrame]] = None,
) -> RuleEngineResult:
    """Features -> ensemble score -> BUY/SELL/HOLD, for every symbol.

    ``benchmarks`` (SPY, QQQ daily frames) powers relative strength and beta.
    ``intraday`` maps each symbol to its 15-minute frame and powers the
    opening-range and relative-volume features. Both optional: without them
    those features are neutral rather than fatal.
    """
    sig_cfg = (cfg.signals if cfg else {}) or {}
    sen_cfg = (cfg.sentiment if cfg else {}) or {}
    sentiment_enabled = bool(sen_cfg.get("enabled", True))
    max_articles = int(sen_cfg.get("max_articles_per_symbol", 12))

    result = RuleEngineResult()
    syms = [str(s).upper() for s in symbols]

    sentiment_map: Dict[str, SentimentResult] = {}
    if sentiment_enabled and articles:
        sentiment_map = analyse_batch(syms, articles, max_articles)
    elif sentiment_enabled:
        result.notes.append(
            "no news articles available; sentiment contributes a neutral 0.0 "
            "(headlines are never fabricated)"
        )
    result.sentiment = sentiment_map

    for sym in syms:
        df = bars.get(sym)
        if df is None or len(df) < 30:
            have = 0 if df is None else len(df)
            result.skipped[sym] = f"insufficient history ({have} bars, need 30+)"
            continue
        try:
            fs = extract_features(
                sym, df,
                benchmarks=benchmarks,
                intraday=(intraday or {}).get(sym),
            )
        except Exception as exc:  # a malformed frame must not kill the run
            result.skipped[sym] = f"feature extraction failed: {exc}"
            log.exception("feature extraction failed for %s", sym)
            continue
        result.features[sym] = fs

        sen = sentiment_map.get(sym)
        sen_score = sen.score if (sen and sen.has_data) else 0.0

        signal = score_featureset(
            fs,
            sentiment=sen_score,
            dimension_weights=sig_cfg.get("dimension_weights"),
            buy_threshold=float(sig_cfg.get("buy_threshold", 0.18)),
            sell_threshold=float(sig_cfg.get("sell_threshold", -0.18)),
            conviction_thresholds=sig_cfg.get("conviction_thresholds") or {},
            macd_budget=float(sig_cfg.get("macd_budget", 0.10)),
        )
        if sen and sen.has_data:
            signal.rationale.append(
                f"  news: {sen.label} ({sen.article_count} article(s), score {sen.score:+.2f})"
            )
        else:
            signal.rationale.append("  news: no data in window -> neutral")
        result.signals.append(signal)

    result.signals.sort(key=lambda s: -abs(s.composite))
    return result
