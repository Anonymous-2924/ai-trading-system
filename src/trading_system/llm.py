"""LLM provider selection and health checking.

Every provider is reached through an **OpenAI-compatible endpoint**, on
purpose.  CrewAI injects an internal ``cache_breakpoint`` key into messages.
A helper ``strip_cache_breakpoint()`` exists in ``crewai/llms/cache.py`` but
nothing calls it — verified in the installed crewai 1.15.28 — and the LiteLLM
fallback path does not strip it either, so providers reached through a
litellm-style prefix reject the request.  Passing ``custom_openai=True`` with
an explicit ``base_url`` forces CrewAI's native OpenAI provider, which builds
its payload from scratch and therefore never leaks the key.

Concretely that means:

* Groq -> ``https://api.groq.com/openai/v1``, never ``groq/<model>``.
* Ollama Cloud (CI) -> ``https://ollama.com/v1`` with ``OLLAMA_API_KEY`` and
  the PLAIN model id (no ``-cloud`` suffix).
* Ollama local daemon -> ``http://localhost:11434/v1`` after ``ollama signin``;
  cloud models there DO carry the ``-cloud`` suffix and do NOT appear in
  ``/api/tags``, so a missing entry there is not evidence the model is absent.

No model name is ever hardcoded as the only option, and the failure message
tells the user how to list the models their own account can see.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Any, List, Optional

import requests

from .config import LLMConfig, clean

log = logging.getLogger(__name__)

#: Message CrewAI raises when a small model loops and then returns nothing.
EMPTY_RESPONSE_MARKERS = (
    "invalid response from llm call",
    "none or empty",
    "empty response",
)


class LLMUnavailable(RuntimeError):
    """The LLM cannot be used.  Always carries an actionable message."""


def is_empty_response_error(exc: BaseException) -> bool:
    """True for CrewAI's "Invalid response from LLM call - None or empty".

    Small models sometimes loop over a tool and then return empty content.
    That is a model failure, not a bug in the pipeline, and it must downgrade
    to the rule engine rather than abort the run.
    """
    text = f"{type(exc).__name__}: {exc}".lower()
    return any(marker in text for marker in EMPTY_RESPONSE_MARKERS)


def list_models_hint(cfg: LLMConfig) -> str:
    """How THIS user lists the models their own account can see."""
    provider = (cfg.provider or "").lower()
    if provider == "ollama_cloud":
        return (
            "List your account's models with:\n"
            f"    curl -s -H \"Authorization: Bearer $OLLAMA_API_KEY\" "
            f"{cfg.base_url or 'https://ollama.com/v1'}/models | python3 -m json.tool\n"
            "Model availability varies per account — use an id from that list."
        )
    if provider == "ollama_local":
        return (
            "Locally installed models:  ollama list\n"
            "Cloud models are NOT in that list and do NOT appear in /api/tags; "
            "they end in -cloud (e.g. gpt-oss:120b-cloud) and work after "
            "`ollama signin`. A model missing from `ollama list` is not "
            "evidence that it is unavailable.\n"
            "The OpenAI-compatible view is:\n"
            f"    curl -s {cfg.base_url or 'http://localhost:11434/v1'}/models | python3 -m json.tool"
        )
    if provider == "groq":
        return (
            "List your account's models with:\n"
            f"    curl -s -H \"Authorization: Bearer $GROQ_API_KEY\" "
            f"{cfg.base_url or 'https://api.groq.com/openai/v1'}/models | python3 -m json.tool"
        )
    return (
        "List the endpoint's models with:\n"
        f"    curl -s -H \"Authorization: Bearer $OPENAI_COMPATIBLE_API_KEY\" "
        f"{cfg.base_url or '<base-url>'}/models | python3 -m json.tool"
    )


@dataclass
class ProviderStatus:
    reachable: bool = False
    authorised: bool = False
    models: List[str] = field(default_factory=list)
    model_listed: Optional[bool] = None
    detail: str = ""

    def to_dict(self) -> dict:
        return {
            "reachable": self.reachable,
            "authorised": self.authorised,
            "model_listed": self.model_listed,
            "model_count": len(self.models),
            "detail": self.detail,
        }


def probe_provider(cfg: LLMConfig, timeout: int = 20) -> ProviderStatus:
    """Hit ``GET {base_url}/models``.  Cheap, and it answers in a second."""
    status = ProviderStatus()
    base = clean(cfg.base_url)
    if not base:
        status.detail = f"no base_url resolved for provider {cfg.provider!r}"
        return status

    headers = {"accept": "application/json"}
    if cfg.api_key:
        headers["Authorization"] = f"Bearer {clean(cfg.api_key)}"
    try:
        resp = requests.get(f"{base.rstrip('/')}/models", headers=headers, timeout=timeout)
    except requests.RequestException as exc:
        status.detail = f"cannot reach {base}: {exc}"
        return status

    status.reachable = True
    if resp.status_code in (401, 403):
        status.detail = (
            f"{base} returned HTTP {resp.status_code}. The API key is missing, "
            "wrong, or has whitespace in it (keys are stripped on load, but "
            "check the secret itself)."
        )
        return status
    if resp.status_code >= 400:
        status.detail = f"{base}/models -> HTTP {resp.status_code}: {resp.text[:200]}"
        return status

    status.authorised = True
    try:
        payload = resp.json()
    except ValueError:
        status.detail = "model list was not JSON"
        return status

    data = payload.get("data") if isinstance(payload, dict) else None
    status.models = [
        clean(m.get("id")) for m in (data or []) if isinstance(m, dict) and m.get("id")
    ]
    if status.models:
        wanted = clean(cfg.model)
        # The local daemon lists cloud models with the -cloud suffix; the
        # hosted endpoint lists them without it.  Match either way.
        candidates = {wanted, wanted.removesuffix("-cloud"), f"{wanted}-cloud"}
        status.model_listed = any(m in candidates for m in status.models)
    status.detail = f"{len(status.models)} model(s) visible to this account"
    return status


def build_crew_llm(cfg: LLMConfig) -> Any:
    """Construct a CrewAI ``LLM`` bound to the OpenAI-compatible endpoint."""
    if (cfg.provider or "").lower() == "none":
        raise LLMUnavailable("LLM_PROVIDER=none: the rule engine runs on its own.")
    base = clean(cfg.base_url)
    model = clean(cfg.model)
    if not base:
        raise LLMUnavailable(
            f"No base URL for provider {cfg.provider!r}. Set the matching "
            "*_BASE_URL environment variable."
        )
    if not model:
        raise LLMUnavailable("LLM_MODEL is empty. " + list_models_hint(cfg))
    provider = (cfg.provider or "").lower()
    if not cfg.api_key and provider != "ollama_local":
        env_var = {
            "ollama_cloud": "OLLAMA_API_KEY",
            "groq": "GROQ_API_KEY",
            "openai_compatible": "OPENAI_COMPATIBLE_API_KEY",
        }.get(provider, "the provider's API key environment variable")
        extra = ""
        if provider == "ollama_cloud":
            extra = (
                " On a CI runner there is no browser, so `ollama signin` is not "
                "an option and the key is required."
            )
        raise LLMUnavailable(
            f"No API key for provider {cfg.provider!r}. Set {env_var}.{extra}"
        )

    try:
        from crewai import LLM  # type: ignore
    except ImportError as exc:
        raise LLMUnavailable(f"crewai is not installed: {exc}") from exc

    try:
        return LLM(
            model=model,
            # custom_openai forces CrewAI's NATIVE OpenAI provider rather than
            # the LiteLLM fallback, so cache_breakpoint never reaches the wire.
            custom_openai=True,
            base_url=base,
            api_key=clean(cfg.api_key) or "ollama",
            temperature=float(cfg.temperature),
            # The OpenAI SDK honours Retry-After on 429, which free tiers
            # return constantly once the per-minute token cap is hit.
            max_retries=max(8, int(cfg.max_retries)),
            timeout=float(cfg.timeout_seconds),
        )
    except Exception as exc:
        raise LLMUnavailable(
            f"could not construct the LLM for model {model!r} at {base}: {exc}\n"
            + list_models_hint(cfg)
        ) from exc


def plain_completion(cfg: LLMConfig, prompt: str, timeout: int = 60) -> str:
    """One raw chat completion against the OpenAI-compatible endpoint.

    Used by ``scripts/test_llm.py`` so provider reachability can be checked
    without constructing a whole crew — and so the exact payload being sent
    can be printed rather than assumed.
    """
    base = clean(cfg.base_url).rstrip("/")
    headers = {"content-type": "application/json"}
    if cfg.api_key:
        headers["Authorization"] = f"Bearer {clean(cfg.api_key)}"
    body = {
        "model": clean(cfg.model),
        "messages": [{"role": "user", "content": prompt}],
        "temperature": float(cfg.temperature),
        "stream": False,
    }
    log.debug("POST %s/chat/completions body=%s", base, json.dumps(body)[:500])
    resp = requests.post(
        f"{base}/chat/completions", headers=headers, json=body, timeout=timeout
    )
    if resp.status_code >= 400:
        raise LLMUnavailable(
            f"{base}/chat/completions -> HTTP {resp.status_code}: {resp.text[:300]}\n"
            + list_models_hint(cfg)
        )
    payload = resp.json()
    choices = payload.get("choices") or []
    if not choices:
        raise LLMUnavailable(f"no choices in response: {json.dumps(payload)[:300]}")
    content = (choices[0].get("message") or {}).get("content") or ""
    if not clean(content):
        # Exactly the failure mode small models exhibit: they loop, then
        # return empty content.
        raise LLMUnavailable(
            "the model returned EMPTY content. Small models loop and then "
            "return nothing; the pipeline treats this as an LLM failure and "
            "falls back to the deterministic rule engine."
        )
    return content
