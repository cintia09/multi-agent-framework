"""E2E-P-009 — table-test the documented tick exit-code contract.

Contract:
    0  phase advanced or task complete (or benign waiting on role output)
    2  entry-question pending (status=blocked + missing field)
    3  HITL gate pending (status=waiting on hitl)
    1  actual error (cancelled / error / blocked-without-recovery)
"""
from __future__ import annotations

import pytest

import _tick


@pytest.mark.parametrize(
    "summary, expected",
    [
        ({"status": "advanced", "next_action": "dispatched designer"}, 0),
        ({"status": "done", "next_action": "noop"}, 0),
        ({"status": "waiting", "next_action": "awaiting clarifier"}, 0),
        ({"status": "waiting", "next_action": "hitl:design_signoff"}, 3),
        ({"status": "blocked", "next_action": "missing: dual_mode",
          "missing": ["dual_mode"]}, 2),
        ({"status": "blocked", "next_action": "max_iterations exceeded"}, 1),
        ({"status": "error", "next_action": "no phases defined"}, 1),
        ({"status": "cancelled", "next_action": "noop"}, 1),
    ],
)
def test_exit_code_contract(summary, expected):
    assert _tick._exit_for(summary) == expected
