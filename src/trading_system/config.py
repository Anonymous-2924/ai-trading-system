"""Configuration loading: YAML file + environment overrides.

Every string read from the environment or from a form field is passed through
``clean()``.  An API key pasted with a trailing newline is rejected by Alpaca
as invalid, and the error it returns ("forbidden") does not hint at
whitespace, so this is stripped at the single point of entry.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional

import yaml

DEFAULT_CONFIG_PATH = "config/config.yaml"
TRUE_VALUES = {"1", "true", "yes", "y", "on"}
FALSE_VALUES = {"0", "false", "no", "n", "off"}


def clean(value: Any) -> str:
    """Strip whitespace (including a stray trailing newline) from a value.

    Returns '' for None.  Used for every API key, secret and endpoint.
    """
    if value is None:
        return ""
    return str(value).strip().strip("\r\n").strip()


def env_str(name: str, default: str = "") -> str:
    return clean(os.environ.get(name, default)) or clean(default)


def env_bool(name: str, default: bool) -> bool:
    raw = clean(os.environ.get(name, "")).lower()
    if raw in TRUE_VALUES:
        return True
    if raw in FALSE_VALUES:
        return False
    return default


def env_int(name: str, default: int) -> int:
    raw = clean(os.environ.get(name, ""))
    try:
        return int(raw)
    except (TypeError, ValueError):
        return default


def env_float(name: str, default: float) -> float:
    raw = clean(os.environ.get(name, ""))
    try:
        return float(raw)
    except (TypeError, ValueError):
        return default


def lerp(timid: float, aggressive: float, aggression: float) -> float:
    a = max(0.0, min(1.0, float(aggression)))
    return timid + (aggressive - timid) * a


@dataclass
class StudentConfig:
    id: str
    name: str
    key_env: str
    secret_env: str
    starting_equity: float
    high_beta: List[str] = field(default_factory=list)
    diversified: List[str] = field(default_factory=list)

    @property
    def symbols(self) -> List[str]:
        seen, out = set(), []
        for s in list(self.high_beta) + list(self.diversified):
            u = clean(s).upper()
            if u and u not in seen:
                seen.add(u)
                out.append(u)
        return out

    @property
    def high_beta_pct(self) -> float:
        total = len(self.symbols)
        if not total:
            return 0.0
        hb = {clean(s).upper() for s in self.high_beta}
        return len(hb & set(self.symbols)) / total

    def credentials(self) -> tuple[str, str]:
        """(key, secret) for this student, whitespace-stripped.

        Falls back to the single-account ALPACA_API_KEY / ALPACA_SECRET_KEY so
        one person can run the system without inventing three accounts.
        """
        key = env_str(self.key_env) or env_str("ALPACA_API_KEY")
        secret = env_str(self.secret_env) or env_str("ALPACA_SECRET_KEY")
        return key, secret

    def has_credentials(self) -> bool:
        key, secret = self.credentials()
        return bool(key and secret)


@dataclass
class RiskConfig:
    starting_equity: float = 100_000.0
    position_pct: float = 0.14
    conviction_multipliers: Dict[str, float] = field(default_factory=dict)
    max_positions: int = 15
    max_gross_exposure: float = 1.35
    max_position_pct: float = 0.22
    max_sector_pct: float = 0.45
    atr_stop_multiple: float = 2.8
    atr_target_multiple: float = 6.0
    min_cash_buffer_pct: float = 0.02
    min_order_notional: float = 50.0
    min_high_beta_pct: float = 0.30


@dataclass
class LLMConfig:
    provider: str = "ollama_cloud"
    model: str = "gpt-oss:120b"
    temperature: float = 0.2
    max_retries: int = 8
    timeout_seconds: int = 180
    fallback_to_rule_engine: bool = True
    base_url: str = ""
    api_key: str = ""


@dataclass
class AppConfig:
    raw: Dict[str, Any] = field(default_factory=dict)
    mode: str = "analyse"
    require_human_approval: bool = True
    demo_mode: bool = False
    max_llm_symbols: int = 12
    lookback_days: int = 400
    model_run_dir: str = "model-run"
    log_dir: str = "trading-logs"
    aggression: float = 0.75
    risk: RiskConfig = field(default_factory=RiskConfig)
    llm: LLMConfig = field(default_factory=LLMConfig)
    students: List[StudentConfig] = field(default_factory=list)
    sectors: Dict[str, str] = field(default_factory=dict)
    signals: Dict[str, Any] = field(default_factory=dict)
    sentiment: Dict[str, Any] = field(default_factory=dict)
    alpaca_base_url: str = "https://paper-api.alpaca.markets"
    alpaca_data_url: str = "https://data.alpaca.markets"

    def student(self, student_id: str) -> StudentConfig:
        key = clean(student_id).lower()
        for s in self.students:
            if s.id.lower() == key:
                return s
        raise KeyError(
            f"unknown student {student_id!r}; known: {[s.id for s in self.students]}"
        )

    def sector_of(self, symbol: str) -> str:
        return self.sectors.get(clean(symbol).upper(), "unknown")

    @property
    def execute(self) -> bool:
        """True only when the run is allowed to submit orders by itself."""
        return self.mode == "execute" and not self.require_human_approval


def _load_dotenv(path: str = ".env") -> None:
    """Load .env if present.  Values are whitespace-stripped.

    Uses python-dotenv when installed and falls back to a tiny parser so the
    system still starts on a bare runner.
    """
    p = Path(path)
    if not p.is_file():
        return
    try:
        from dotenv import load_dotenv  # type: ignore

        load_dotenv(p, override=False)
    except Exception:
        for line in p.read_text(encoding="utf-8", errors="replace").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, _, v = line.partition("=")
            os.environ.setdefault(clean(k), clean(v).strip("'\""))
    # Re-strip whatever landed in the environment.
    for k, v in list(os.environ.items()):
        if isinstance(v, str) and v != v.strip():
            os.environ[k] = v.strip()


def resolve_llm(cfg_block: Mapping[str, Any]) -> LLMConfig:
    """Pick the provider and resolve its OpenAI-compatible base URL + key.

    All providers are reached through OpenAI-compatible endpoints on purpose.
    CrewAI injects an internal ``cache_breakpoint`` key into messages; its
    ``strip_cache_breakpoint()`` helper exists but the LiteLLM fallback path
    never calls it, so providers reached via a litellm prefix reject every
    request.  The native OpenAI path does strip it, so we always hand CrewAI
    an ``openai/``-style client with an explicit ``base_url``.
    """
    llm = LLMConfig(
        provider=env_str("LLM_PROVIDER", str(cfg_block.get("provider", "ollama_cloud"))),
        model=env_str("LLM_MODEL", str(cfg_block.get("model", "gpt-oss:120b"))),
        temperature=env_float("LLM_TEMPERATURE", float(cfg_block.get("temperature", 0.2))),
        max_retries=env_int("LLM_MAX_RETRIES", int(cfg_block.get("max_retries", 8))),
        timeout_seconds=env_int(
            "LLM_TIMEOUT_SECONDS", int(cfg_block.get("timeout_seconds", 180))
        ),
        fallback_to_rule_engine=env_bool(
            "LLM_FALLBACK_TO_RULE_ENGINE",
            bool(cfg_block.get("fallback_to_rule_engine", True)),
        ),
    )
    provider = llm.provider.lower()

    if provider == "groq":
        # OpenAI-compatible base URL, NOT litellm's "groq/" prefix.
        llm.base_url = env_str("GROQ_BASE_URL", "https://api.groq.com/openai/v1")
        llm.api_key = env_str("GROQ_API_KEY")
    elif provider == "ollama_local":
        # The local daemon after `ollama signin`: no API key needed.  Cloud
        # model ids end in -cloud here and do NOT appear in /api/tags.
        llm.base_url = env_str("OLLAMA_LOCAL_BASE_URL", "http://localhost:11434/v1")
        llm.api_key = env_str("OLLAMA_API_KEY") or "ollama"
    elif provider == "ollama_cloud":
        # CI path: no browser on a runner, so talk to the hosted
        # OpenAI-compatible endpoint with a plain (no -cloud suffix) model id.
        llm.base_url = env_str("OLLAMA_CLOUD_BASE_URL", "https://ollama.com/v1")
        llm.api_key = env_str("OLLAMA_API_KEY")
    elif provider == "openai_compatible":
        llm.base_url = env_str("OPENAI_COMPATIBLE_BASE_URL")
        llm.api_key = env_str("OPENAI_COMPATIBLE_API_KEY") or env_str("OPENAI_API_KEY")
    elif provider == "none":
        llm.base_url = ""
        llm.api_key = ""
    else:
        raise ValueError(
            f"unknown LLM_PROVIDER {llm.provider!r}; expected one of "
            "ollama_cloud, ollama_local, groq, openai_compatible, none"
        )
    return llm


def load_config(path: Optional[str] = None, load_env: bool = True) -> AppConfig:
    """Read the YAML config, then let environment variables override it."""
    if load_env:
        _load_dotenv()
    cfg_path = clean(path) or env_str("CONFIG_PATH", DEFAULT_CONFIG_PATH)
    raw: Dict[str, Any] = {}
    p = Path(cfg_path)
    if p.is_file():
        raw = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
    elif clean(path):
        raise FileNotFoundError(f"config file not found: {cfg_path}")

    run = raw.get("run", {}) or {}
    aggression = env_float("AGGRESSION", float(raw.get("aggression", 0.75)))
    aggression = max(0.0, min(1.0, aggression))
    r = raw.get("risk", {}) or {}

    risk = RiskConfig(
        starting_equity=env_float(
            "STARTING_EQUITY", float(r.get("starting_equity", 100_000.0))
        ),
        position_pct=lerp(
            float(r.get("position_pct_timid", 0.03)),
            float(r.get("position_pct_aggressive", 0.14)),
            aggression,
        ),
        conviction_multipliers={
            str(k).upper(): float(v)
            for k, v in (
                r.get("conviction_multipliers")
                or {"LOW": 0.0, "MEDIUM": 0.7, "HIGH": 1.0, "VERY_HIGH": 1.35}
            ).items()
        },
        max_positions=int(
            round(
                lerp(
                    float(r.get("max_positions_timid", 8)),
                    float(r.get("max_positions_aggressive", 15)),
                    aggression,
                )
            )
        ),
        max_gross_exposure=lerp(
            float(r.get("max_gross_exposure_timid", 0.60)),
            float(r.get("max_gross_exposure_aggressive", 1.35)),
            aggression,
        ),
        max_position_pct=lerp(
            float(r.get("max_position_pct_timid", 0.08)),
            float(r.get("max_position_pct_aggressive", 0.22)),
            aggression,
        ),
        max_sector_pct=lerp(
            float(r.get("max_sector_pct_timid", 0.25)),
            float(r.get("max_sector_pct_aggressive", 0.45)),
            aggression,
        ),
        atr_stop_multiple=lerp(
            float(r.get("atr_stop_multiple_timid", 1.5)),
            float(r.get("atr_stop_multiple_aggressive", 2.8)),
            aggression,
        ),
        atr_target_multiple=lerp(
            float(r.get("atr_target_multiple_timid", 2.5)),
            float(r.get("atr_target_multiple_aggressive", 6.0)),
            aggression,
        ),
        min_cash_buffer_pct=float(r.get("min_cash_buffer_pct", 0.02)),
        min_order_notional=float(r.get("min_order_notional", 50.0)),
        min_high_beta_pct=float(r.get("min_high_beta_pct", 0.30)),
    )

    students = [
        StudentConfig(
            id=clean(s.get("id")),
            name=clean(s.get("name")) or clean(s.get("id")),
            key_env=clean(s.get("key_env")),
            secret_env=clean(s.get("secret_env")),
            starting_equity=float(s.get("starting_equity", risk.starting_equity)),
            high_beta=[clean(x).upper() for x in (s.get("high_beta") or [])],
            diversified=[clean(x).upper() for x in (s.get("diversified") or [])],
        )
        for s in (raw.get("students") or [])
    ]

    cfg = AppConfig(
        raw=raw,
        mode=env_str("RUN_MODE", str(run.get("mode", "analyse"))).lower(),
        require_human_approval=env_bool(
            "REQUIRE_HUMAN_APPROVAL", bool(run.get("require_human_approval", True))
        ),
        demo_mode=env_bool("DEMO_MODE", bool(run.get("demo_mode", False))),
        max_llm_symbols=env_int("MAX_LLM_SYMBOLS", int(run.get("max_llm_symbols", 12))),
        lookback_days=env_int("LOOKBACK_DAYS", int(run.get("lookback_days", 400))),
        model_run_dir=env_str("MODEL_RUN_DIR", str(run.get("model_run_dir", "model-run"))),
        log_dir=env_str("TRADING_LOG_DIR", str(run.get("log_dir", "trading-logs"))),
        aggression=aggression,
        risk=risk,
        llm=resolve_llm(raw.get("llm", {}) or {}),
        students=students,
        sectors={clean(k).upper(): clean(v) for k, v in (raw.get("sectors") or {}).items()},
        signals=raw.get("signals", {}) or {},
        sentiment=raw.get("sentiment", {}) or {},
        alpaca_base_url=env_str(
            "ALPACA_BASE_URL", "https://paper-api.alpaca.markets"
        ),
        alpaca_data_url=env_str("ALPACA_DATA_URL", "https://data.alpaca.markets"),
    )
    if cfg.mode not in {"analyse", "analyze", "execute"}:
        raise ValueError(f"RUN_MODE must be analyse or execute, got {cfg.mode!r}")
    if cfg.mode == "analyze":
        cfg.mode = "analyse"
    return cfg
