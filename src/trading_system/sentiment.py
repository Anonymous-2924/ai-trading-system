"""News sentiment from real headlines, scored by a transparent lexicon.

Why a lexicon rather than an LLM call per headline: the sentiment input is one
of six weighted inputs to the composite, it has to work when the LLM is
unavailable (that is the whole point of the deterministic fallback), and it
has to be auditable — every score here can be traced back to the words that
produced it.  When an LLM *is* available the sentiment agent reviews the same
headlines and its read is recorded alongside this one.

The lexicon never invents news.  With no credentials and no demo mode the
caller gets no headlines at all and the score is an explicit "no data"
neutral, not a guess.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from typing import Dict, Iterable, List, Mapping, Sequence

POSITIVE: Dict[str, float] = {
    "beat": 1.0, "beats": 1.0, "surge": 1.2, "surges": 1.2, "soar": 1.3, "soars": 1.3,
    "jump": 0.9, "jumps": 0.9, "rally": 1.0, "rallies": 1.0, "upgrade": 1.2,
    "upgrades": 1.2, "upgraded": 1.2, "outperform": 1.0, "record": 0.9, "profit": 0.7,
    "profits": 0.7, "growth": 0.7, "strong": 0.8, "stronger": 0.8, "raises": 0.9,
    "raised": 0.8, "boost": 0.9, "boosts": 0.9, "expands": 0.6, "expansion": 0.6,
    "approval": 1.0, "approved": 1.0, "wins": 0.9, "win": 0.8, "awarded": 0.8,
    "partnership": 0.6, "buyback": 0.9, "dividend": 0.5, "bullish": 1.1,
    "optimistic": 0.7, "momentum": 0.6, "breakthrough": 1.1, "accelerating": 0.8,
    "exceeds": 1.0, "exceeded": 1.0, "topped": 0.9, "rebound": 0.8, "recovery": 0.7,
    "launch": 0.5, "launches": 0.5, "demand": 0.5, "guidance": 0.0,
}

NEGATIVE: Dict[str, float] = {
    "miss": -1.0, "misses": -1.0, "missed": -1.0, "plunge": -1.3, "plunges": -1.3,
    "crash": -1.4, "crashes": -1.4, "tumble": -1.1, "tumbles": -1.1, "slump": -1.0,
    "slumps": -1.0, "downgrade": -1.2, "downgrades": -1.2, "downgraded": -1.2,
    "underperform": -1.0, "loss": -0.9, "losses": -0.9, "weak": -0.8, "weaker": -0.8,
    "cuts": -0.9, "cut": -0.8, "slash": -1.1, "slashes": -1.1, "warns": -1.1,
    "warning": -1.0, "lawsuit": -0.9, "probe": -0.9, "investigation": -1.0,
    "recall": -1.0, "bankruptcy": -1.6, "fraud": -1.5, "sec": -0.4, "fine": -0.7,
    "fined": -0.9, "layoffs": -0.8, "layoff": -0.8, "resigns": -0.7, "resign": -0.7,
    "delay": -0.7, "delayed": -0.7, "halt": -0.9, "halted": -0.9, "bearish": -1.1,
    "decline": -0.8, "declines": -0.8, "falls": -0.8, "fell": -0.8, "drops": -0.8,
    "sinks": -1.0, "shortfall": -1.0, "disappointing": -1.1, "concerns": -0.6,
    "risk": -0.4, "risks": -0.4, "selloff": -1.0, "short": -0.4, "subpoena": -1.1,
}

#: Words that flip the polarity of the next scored token.
NEGATORS = {"no", "not", "never", "without", "despite", "fails", "fail", "failed", "less"}

#: Words that amplify the next scored token.
INTENSIFIERS = {"very": 1.4, "sharply": 1.5, "massively": 1.6, "slightly": 0.6,
                "modestly": 0.7, "record": 1.3, "steeply": 1.5}

_TOKEN_RE = re.compile(r"[a-z']+")

NO_DATA = "NO_NEWS_DATA"


@dataclass
class SentimentResult:
    symbol: str
    score: float = 0.0            # [-1, +1]
    label: str = "NEUTRAL"
    article_count: int = 0
    has_data: bool = False
    source: str = NO_DATA
    top_terms: List[str] = field(default_factory=list)
    headlines: List[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "symbol": self.symbol,
            "score": round(self.score, 4),
            "label": self.label,
            "article_count": self.article_count,
            "has_data": self.has_data,
            "source": self.source,
            "top_terms": self.top_terms,
            "headlines": self.headlines[:5],
        }


def score_text(text: str) -> tuple[float, List[str]]:
    """Score one headline.  Returns (raw score, the terms that fired)."""
    tokens = _TOKEN_RE.findall((text or "").lower())
    total = 0.0
    hits: List[str] = []
    negate = False
    amplify = 1.0
    for tok in tokens:
        if tok in NEGATORS:
            negate = True
            continue
        if tok in INTENSIFIERS and tok not in POSITIVE and tok not in NEGATIVE:
            amplify = INTENSIFIERS[tok]
            continue
        weight = POSITIVE.get(tok, 0.0) or NEGATIVE.get(tok, 0.0)
        if weight:
            value = weight * amplify * (-1.0 if negate else 1.0)
            total += value
            hits.append(f"{tok}{'(neg)' if negate else ''}{value:+.1f}")
        if weight or tok in INTENSIFIERS:
            negate = False
            amplify = 1.0
    return total, hits


def label_for(score: float) -> str:
    if score >= 0.35:
        return "BULLISH"
    if score >= 0.12:
        return "MILDLY_BULLISH"
    if score <= -0.35:
        return "BEARISH"
    if score <= -0.12:
        return "MILDLY_BEARISH"
    return "NEUTRAL"


def analyse_symbol(
    symbol: str, articles: Sequence[Mapping], max_articles: int = 12
) -> SentimentResult:
    """Aggregate sentiment for one symbol from its own articles."""
    sym = (symbol or "").upper()
    relevant = [
        a
        for a in articles
        if sym in {s.strip().upper() for s in str(a.get("symbol", "")).split(",") if s.strip()}
    ][: int(max_articles)]

    if not relevant:
        return SentimentResult(symbol=sym, score=0.0, label="NEUTRAL", source=NO_DATA)

    scores: List[float] = []
    terms: List[str] = []
    headlines: List[str] = []
    for art in relevant:
        text = f"{art.get('headline', '')} {art.get('summary', '')}"
        raw, hits = score_text(text)
        scores.append(raw)
        terms.extend(hits)
        headlines.append(str(art.get("headline", ""))[:160])

    mean = sum(scores) / len(scores)
    # tanh keeps a single hysterical headline from pinning the score at +-1
    normalised = math.tanh(mean / 1.5)
    # Confidence scales with how much news there actually is.
    confidence = min(1.0, len(relevant) / 4.0)
    final = max(-1.0, min(1.0, normalised * (0.5 + 0.5 * confidence)))

    source = str(relevant[0].get("source") or "alpaca")
    return SentimentResult(
        symbol=sym,
        score=final,
        label=label_for(final),
        article_count=len(relevant),
        has_data=True,
        source=source,
        top_terms=terms[:8],
        headlines=headlines,
    )


def analyse_batch(
    symbols: Iterable[str], articles: Sequence[Mapping], max_articles: int = 12
) -> Dict[str, SentimentResult]:
    return {
        s.upper(): analyse_symbol(s, articles, max_articles)
        for s in (x.upper() for x in symbols)
    }
