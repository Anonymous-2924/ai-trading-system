"""The wall-clock budget that keeps a stalled crew from killing the run.

Background: with three students sharing one free LLM tier, the student who
ran last was rate-limited for so long that the CI job hit its own timeout and
was killed BEFORE writing its daily-log row. One team member silently stopped
being logged for three days. Bounding the crew fixes that at the root.
"""

import time

import pytest

from trading_system.agents import CrewBudgetExceeded, kickoff_within_budget
from trading_system.config import load_config


class FakeCrew:
    def __init__(self, seconds=0.0, result="ok", error=None):
        self.seconds, self.result, self.error = seconds, result, error
        self.started = False

    def kickoff(self):
        self.started = True
        time.sleep(self.seconds)
        if self.error:
            raise self.error
        return self.result


class TestBudget:
    def test_a_fast_crew_returns_its_result(self):
        assert kickoff_within_budget(FakeCrew(0.1, "decisions"), 60) == "decisions"

    def test_a_stalled_crew_is_abandoned(self):
        started = time.monotonic()
        with pytest.raises(CrewBudgetExceeded):
            kickoff_within_budget(FakeCrew(600), 1)
        # Clamped to the 30s floor, so it must not wait anywhere near 600s.
        assert time.monotonic() - started < 90

    def test_the_message_explains_the_fallback(self):
        with pytest.raises(CrewBudgetExceeded, match="deterministic rule engine"):
            kickoff_within_budget(FakeCrew(600), 1)

    def test_the_message_reports_the_effective_budget(self):
        """A 1s request is clamped to the 30s floor; say 30, not 1."""
        with pytest.raises(CrewBudgetExceeded, match="30s budget"):
            kickoff_within_budget(FakeCrew(600), 1)

    def test_an_inner_error_propagates_rather_than_being_swallowed(self):
        with pytest.raises(ValueError, match="provider exploded"):
            kickoff_within_budget(FakeCrew(0.1, error=ValueError("provider exploded")), 60)

    def test_the_budget_has_a_floor(self):
        """A misconfigured zero or negative budget must not abandon instantly."""
        assert kickoff_within_budget(FakeCrew(0.1, "ok"), 0) == "ok"
        assert kickoff_within_budget(FakeCrew(0.1, "ok"), -5) == "ok"


class TestConfiguration:
    def test_the_budget_is_configured(self, config_path):
        cfg = load_config(config_path)
        assert cfg.llm.crew_budget_seconds >= 60

    def test_the_budget_can_be_overridden(self, monkeypatch, config_path):
        monkeypatch.setenv("LLM_CREW_BUDGET_SECONDS", "123")
        assert load_config(config_path).llm.crew_budget_seconds == 123

    def test_three_students_fit_inside_one_ci_job_timeout(self, config_path):
        """The budget exists to keep the matrix under GitHub's job timeout.

        Each student's job is separate, so the bound that matters is one
        student's crew against one job's 40-minute allowance.
        """
        cfg = load_config(config_path)
        assert cfg.llm.crew_budget_seconds < 40 * 60

    def test_the_symbol_cap_leaves_quota_for_everyone(self, config_path):
        """Crew cost is roughly 2 requests per symbol + 4. Three students must
        fit inside a free tier without starving whoever runs last."""
        cfg = load_config(config_path)
        per_student = 2 * cfg.max_llm_symbols + 4
        assert per_student * len(cfg.students) <= 72, (
            f"{per_student} requests x {len(cfg.students)} students is too many"
        )


class TestStudentIdentity:
    def test_every_student_has_a_name_and_roll_number(self, config_path):
        for student in load_config(config_path).students:
            assert student.name and student.name != student.id
            assert student.roll_no.isdigit()

    def test_label_combines_name_and_roll(self, config_path):
        student = load_config(config_path).student("student_1")
        assert student.name in student.label and student.roll_no in student.label
