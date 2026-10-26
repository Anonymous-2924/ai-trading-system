#!/usr/bin/env python3
"""Put back the daily-log rows that the artifact merge threw away.

THE BUG THIS REPAIRS
--------------------
Each student's job uploads the whole ``trading-logs/`` directory, so all
three artifacts of a run contain all three CSVs -- that student's fresh one
plus the other two exactly as checked out, without the new row. The commit
job downloaded them with ``merge-multiple``, which flattens same-named files
into one directory and lets whichever was extracted last win. Two of the
three students' rows were discarded on every run, at random, while every job
reported success.

The runs themselves were fine, and each one uploaded its own correct file.
So the lost rows still exist, inside the per-run artifacts, until those
expire seven days after the run.

This script walks every past run of the trading workflow, downloads every
``trading-log-*`` artifact, and merges the union of all the rows it finds
back into the committed logs. Running it twice changes nothing the second
time: rows are keyed on their UTC timestamp, so a row already present is
recognised rather than duplicated.

WHAT IT CANNOT DO
-----------------
An artifact expires seven days after its run. Rows from a run older than
that are genuinely gone -- they were never anywhere else. The script says
exactly which runs it could not read rather than quietly skipping them.

Run it from GitHub Actions, where GITHUB_TOKEN is already available:

    Actions -> "Recover lost log rows" -> Run workflow

or locally with a token that can read Actions artifacts:

    GITHUB_TOKEN=... GITHUB_REPOSITORY=owner/repo python scripts/recover_logs.py
"""

from __future__ import annotations

import argparse
import csv
import io
import os
import sys
import zipfile
from pathlib import Path
from typing import Dict, List, Tuple

import requests

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from trading_system import alpha_log, daily_log, price_log, trade_ledger  # noqa: E402

API = "https://api.github.com"
WORKFLOW = "trading-analysis.yml"
ARTIFACT_PREFIX = "trading-log-"

#: Which column identifies a row uniquely, per file kind.
KEY_COLUMN = {
    "daily": "timestamp_utc",
    "alpha": "timestamp_utc",
    "ledger": "timestamp_utc",
}


def kind_of(name: str) -> str:
    if name.startswith("alpha_"):
        return "alpha"
    if name.startswith("trades_"):
        return "ledger"
    if name == "prices":
        return "prices"
    return "daily"


def session(token: str) -> requests.Session:
    s = requests.Session()
    s.headers.update(
        {
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }
    )
    return s


def list_runs(s: requests.Session, repo: str) -> List[dict]:
    runs: List[dict] = []
    page = 1
    while page <= 10:
        r = s.get(
            f"{API}/repos/{repo}/actions/workflows/{WORKFLOW}/runs",
            params={"per_page": 100, "page": page},
            timeout=60,
        )
        r.raise_for_status()
        batch = r.json().get("workflow_runs", [])
        if not batch:
            break
        runs.extend(batch)
        if len(batch) < 100:
            break
        page += 1
    return runs


def artifacts_for(s: requests.Session, repo: str, run_id: int) -> List[dict]:
    r = s.get(
        f"{API}/repos/{repo}/actions/runs/{run_id}/artifacts",
        params={"per_page": 100},
        timeout=60,
    )
    r.raise_for_status()
    return [
        a for a in r.json().get("artifacts", [])
        if str(a.get("name", "")).startswith(ARTIFACT_PREFIX)
    ]


def rows_from_artifact(s: requests.Session, artifact: dict) -> Dict[str, List[dict]]:
    """``{stem: [row, ...]}`` for every CSV inside one artifact zip."""
    out: Dict[str, List[dict]] = {}
    r = s.get(artifact["archive_download_url"], timeout=180)
    r.raise_for_status()
    with zipfile.ZipFile(io.BytesIO(r.content)) as zf:
        for member in zf.namelist():
            if not member.endswith(".csv"):
                continue
            stem = Path(member).stem
            try:
                text = zf.read(member).decode("utf-8")
            except Exception:
                continue
            out.setdefault(stem, []).extend(csv.DictReader(io.StringIO(text)))
    return out


def merge(existing: List[dict], incoming: List[dict], key: str) -> Tuple[List[dict], int]:
    """Union, keyed on `key`, oldest first. Existing rows always win."""
    seen = {str(row.get(key, "")) for row in existing if row.get(key)}
    added = 0
    merged = list(existing)
    for row in incoming:
        identifier = str(row.get(key, ""))
        if not identifier or identifier in seen:
            continue
        seen.add(identifier)
        merged.append(row)
        added += 1
    merged.sort(key=lambda r: str(r.get(key, "")))
    return merged, added


def read_csv(path: Path) -> List[dict]:
    if not path.exists():
        return []
    with path.open(newline="", encoding="utf-8") as fh:
        return [dict(r) for r in csv.DictReader(fh)]


def write_csv(path: Path, rows: List[dict], columns: List[str]) -> None:
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=columns)
        writer.writeheader()
        for row in rows:
            writer.writerow({c: row.get(c, "") for c in columns})


COLUMNS_FOR = {
    "daily": lambda: daily_log.COLUMNS,
    "alpha": lambda: alpha_log.COLUMNS,
    "ledger": lambda: trade_ledger.COLUMNS,
}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--log-dir", default="trading-logs")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    token = os.environ.get("GITHUB_TOKEN", "").strip()
    repo = os.environ.get("GITHUB_REPOSITORY", "").strip()
    if not token or not repo:
        print("GITHUB_TOKEN and GITHUB_REPOSITORY must both be set", file=sys.stderr)
        return 2

    s = session(token)
    log_dir = Path(args.log_dir)
    log_dir.mkdir(parents=True, exist_ok=True)

    runs = list_runs(s, repo)
    print(f"Workflow runs found : {len(runs)}")

    collected: Dict[str, List[dict]] = {}
    price_rows: List[dict] = []
    read_ok, expired = 0, []

    for run in sorted(runs, key=lambda r: str(r.get("created_at", ""))):
        try:
            artifacts = artifacts_for(s, repo, run["id"])
        except requests.RequestException as exc:
            print(f"  ! run {run['id']}: could not list artifacts ({exc})")
            continue
        if not artifacts:
            continue
        alive = [a for a in artifacts if not a.get("expired")]
        if not alive:
            expired.append(str(run.get("created_at", ""))[:10])
            continue
        for artifact in alive:
            try:
                found = rows_from_artifact(s, artifact)
            except requests.RequestException as exc:
                print(f"  ! {artifact['name']}: download failed ({exc})")
                continue
            read_ok += 1
            for stem, rows in found.items():
                if kind_of(stem) == "prices":
                    price_rows.extend(rows)
                else:
                    collected.setdefault(stem, []).extend(rows)

    print(f"Artifacts read      : {read_ok}")
    if expired:
        print(
            "Runs whose artifacts have expired (their rows are unrecoverable): "
            + ", ".join(sorted(set(expired)))
        )
    print()

    total_added = 0
    for stem in sorted(collected):
        kind = kind_of(stem)
        columns = COLUMNS_FOR[kind]()
        path = log_dir / f"{stem}.csv"
        existing = read_csv(path)
        merged, added = merge(existing, collected[stem], KEY_COLUMN[kind])
        total_added += added
        print(f"  {stem+'.csv':28s} {len(existing):4d} -> {len(merged):4d}  (+{added})")
        if added and not args.dry_run:
            write_csv(path, merged, columns)

    if price_rows and not args.dry_run:
        status = price_log.append_closes(price_rows, str(log_dir))
        print(f"  prices.csv                   {status.get('rows', 0)} row(s)")

    if not args.dry_run and total_added:
        print()
        for stem in sorted(collected):
            kind = kind_of(stem)
            if kind == "daily":
                print("  rebuilt", daily_log.write_markdown(stem, str(log_dir)))
            elif kind == "alpha":
                print("  rebuilt",
                      alpha_log.write_markdown(stem[len("alpha_"):], str(log_dir)))

    print()
    print(f"Rows recovered: {total_added}"
          + (" (dry run, nothing written)" if args.dry_run else ""))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
