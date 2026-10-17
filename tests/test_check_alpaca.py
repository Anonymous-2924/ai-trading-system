"""Student selection in scripts/check_alpaca.py.

The first real use of the diagnose workflow printed "0/0 accounts" because
`all` was typed into the students box and only a blank was accepted — while
the trading workflow's equivalent input defaults to `all`.
"""

import runpy
import sys
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "check_alpaca.py"


def run(monkeypatch, capsys, config_path, students):
    """Run the script with Alpaca unreachable; we only assert on selection."""
    monkeypatch.setattr(
        sys, "argv", ["check_alpaca.py", "--config", config_path, "--students", students]
    )
    for n in (1, 2, 3):
        monkeypatch.delenv(f"ALPACA_API_KEY_{n}", raising=False)
        monkeypatch.delenv(f"ALPACA_SECRET_KEY_{n}", raising=False)
    monkeypatch.delenv("ALPACA_API_KEY", raising=False)
    monkeypatch.delenv("ALPACA_SECRET_KEY", raising=False)
    try:
        runpy.run_path(str(SCRIPT), run_name="__main__")
        code = 0
    except SystemExit as exc:
        code = exc.code or 0
    return code, capsys.readouterr().out


@pytest.mark.parametrize("value", ["", "all", "ALL", "*", "universe", "  all  "])
def test_these_all_select_every_student(monkeypatch, capsys, config_path, value):
    code, out = run(monkeypatch, capsys, config_path, value)
    assert "student_1" in out and "student_2" in out and "student_3" in out
    assert "0/0" not in out, "every student must be selected"
    assert code != 2, out


def test_a_single_id_selects_just_that_student(monkeypatch, capsys, config_path):
    _, out = run(monkeypatch, capsys, config_path, "student_2")
    assert "student_2" in out
    assert "student_1  (" not in out


def test_an_unknown_id_is_named_and_the_valid_ones_listed(monkeypatch, capsys, config_path):
    code, out = run(monkeypatch, capsys, config_path, "student_9")
    assert code == 2
    assert "unknown student id(s): student_9" in out
    assert "student_1" in out and "student_3" in out


def test_the_header_says_where_the_config_came_from(monkeypatch, capsys, config_path):
    _, out = run(monkeypatch, capsys, config_path, "all")
    assert "config loaded from" in out
    assert "students defined" in out


def test_missing_credentials_are_reported_per_student(monkeypatch, capsys, config_path):
    _, out = run(monkeypatch, capsys, config_path, "all")
    assert "NO CREDENTIALS" in out
    assert "ALPACA_API_KEY_1" in out
