"""Per-agent run artefacts written to ``model-run/``.

Filename format required by the brief::

    model-run/agentNameDDMMYYYY-HH-MM.md

Each file records the timestamp, the indicators that fed the step, the
decisions it produced, the result, any errors, and the full experiment
configuration, so a run can be reconstructed from the artefacts alone.
"""

from __future__ import annotations

import json
import logging
import os
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

log = logging.getLogger(__name__)

_SAFE = re.compile(r"[^A-Za-z0-9_]+")


def safe_agent_name(name: str) -> str:
    """``Technical Analysis Agent`` -> ``technicalAnalysisAgent``."""
    parts = [p for p in _SAFE.sub(" ", str(name or "agent")).split() if p]
    if not parts:
        return "agent"
    head, *rest = parts
    return head[:1].lower() + head[1:] + "".join(p[:1].upper() + p[1:] for p in rest)


def run_stamp(when: Optional[datetime] = None) -> str:
    """``DDMMYYYY-HH-MM`` in UTC."""
    when = when or datetime.now(timezone.utc)
    return when.strftime("%d%m%Y-%H-%M")


@dataclass
class RunLogger:
    directory: str = "model-run"
    run_id: str = field(default_factory=run_stamp)
    config_snapshot: Dict[str, Any] = field(default_factory=dict)
    written: List[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        Path(self.directory).mkdir(parents=True, exist_ok=True)

    def path_for(self, agent_name: str) -> Path:
        return Path(self.directory) / f"{safe_agent_name(agent_name)}{self.run_id}.md"

    def write(
        self,
        agent_name: str,
        *,
        summary: str = "",
        indicators: Any = None,
        decisions: Any = None,
        results: Any = None,
        errors: Any = None,
        extra: Optional[Dict[str, Any]] = None,
    ) -> Optional[Path]:
        """Write one agent artefact.  Never raises: a logging failure must not
        break a trading run."""
        try:
            path = self.path_for(agent_name)
            now = datetime.now(timezone.utc)
            blocks: List[str] = [
                f"# {agent_name}",
                "",
                f"- **Run id:** `{self.run_id}`",
                f"- **Written (UTC):** {now.isoformat(timespec='seconds')}",
                f"- **Artefact:** `{path.as_posix()}`",
                "",
            ]
            if summary:
                blocks += ["## Summary", "", str(summary).strip(), ""]
            for title, payload in (
                ("Indicators used", indicators),
                ("Decisions", decisions),
                ("Results", results),
                ("Errors", errors),
            ):
                if payload in (None, "", [], {}):
                    if title == "Errors":
                        blocks += ["## Errors", "", "_none_", ""]
                    continue
                blocks += [f"## {title}", "", _render(payload), ""]
            if extra:
                blocks += ["## Additional detail", "", _render(extra), ""]
            blocks += [
                "## Experiment configuration",
                "",
                _render(self.config_snapshot or {"note": "no configuration snapshot"}),
                "",
            ]
            path.write_text("\n".join(blocks), encoding="utf-8")
            self.written.append(path.as_posix())
            log.info("wrote agent artefact %s", path)
            return path
        except Exception:  # pragma: no cover - logging must never break a run
            log.exception("failed to write artefact for %s", agent_name)
            return None


def _render(payload: Any) -> str:
    if isinstance(payload, str):
        return payload.strip()
    try:
        return "```json\n" + json.dumps(payload, indent=2, default=str) + "\n```"
    except (TypeError, ValueError):
        return "```\n" + str(payload) + "\n```"
