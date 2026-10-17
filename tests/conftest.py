import os
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

os.environ.setdefault("CONFIG_PATH", str(ROOT / "config" / "config.yaml"))


@pytest.fixture
def project_root() -> Path:
    return ROOT


@pytest.fixture
def config_path(project_root) -> str:
    return str(project_root / "config" / "config.yaml")


def make_frame(n=300, seed=0, drift=0.0005, vol=0.02, end_multiplier=None):
    """A synthetic OHLCV frame.  `end_multiplier` forces a total return."""
    idx = pd.date_range("2024-01-01", periods=n, freq="B", tz="UTC")
    rng = np.random.default_rng(seed)
    if end_multiplier is not None:
        trend = np.linspace(0.0, np.log(end_multiplier), n)
        noise = np.cumsum(rng.normal(0, 0.006, n))
        close = pd.Series(100 * np.exp(trend + noise - noise[0]), index=idx)
    else:
        close = pd.Series(
            100 * np.cumprod(1 + rng.normal(drift, vol, n)), index=idx
        )
    return pd.DataFrame(
        {
            "open": close.shift(1).bfill(),
            "high": close * 1.015,
            "low": close * 0.985,
            "close": close,
            "volume": rng.integers(1_000_000, 5_000_000, n).astype(float),
        },
        index=idx,
    )


@pytest.fixture
def frame_factory():
    return make_frame
