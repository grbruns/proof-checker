"""
Shared fixtures for proof checker tests.

Run against the PHP implementation (default):
    pytest tests/

Run against a Flask reimplementation:
    pytest tests/ --checker-url=http://localhost:5000/checkproof
"""

import json
import pytest
import requests


def pytest_addoption(parser):
    parser.addoption(
        "--checker-url",
        default="http://localhost:8000/checkproof.php",
        help="URL of the proof checker endpoint (default: PHP at localhost:8000)",
    )


@pytest.fixture(scope="session")
def checker_url(request):
    return request.config.getoption("--checker-url")


@pytest.fixture
def check_proof(checker_url):
    """
    Send a proof to the checker and return the JSON response.

    proof_data is a Python list mirroring the JSON that the browser sends:
      - Each top-level item is either a dict {wffstr, jstr} (a proof line)
        or a list of such dicts (a subproof).
      - Subproofs can be nested.
      - wffstr must use Unicode operators: ∧ ∨ → ↔ ¬ ⊥ ∀ ∃
      - jstr must use canonical rule names: ∧I, ∧E, →E, →I, ∨I, ∨E,
        ↔I, ↔E, MT, DS, Rep, DNE, DeM, RAA, IP, TND, ⊥I, ⊥E,
        Bicondition, Pr, Hyp, =I, =E, ∀E, ∀I, ∃I, ∃E, CQ
      - Line citations in jstr are 1-indexed: "→E,1,2" or "→I,2-3"

    Response JSON has two fields:
      - "issues": list of error strings (empty list means all lines are valid)
      - "concReached": bool, True if the wanted conclusion appears at top level
    """
    def _check(proof_data, num_prems, wanted_conc, predicate_settings=False):
        response = requests.post(
            checker_url,
            data={
                "proofData": json.dumps(proof_data),
                "numPrems": str(num_prems),
                "wantedConc": wanted_conc,
                "predicateSettings": "true" if predicate_settings else "false",
            },
        )
        response.raise_for_status()
        return response.json()

    return _check


# ── Assertion helpers ────────────────────────────────────────────────────────

def assert_valid(result):
    """Assert that every proof line was accepted and the conclusion was reached."""
    assert result["issues"] == [], f"Expected no issues, got: {result['issues']}"
    assert result["concReached"] is True, "Conclusion was not reached"


def assert_invalid(result):
    """Assert that at least one proof line was rejected."""
    assert len(result["issues"]) > 0, "Expected issues but got none"


def assert_issue_contains(result, text):
    """Assert that the combined issue text contains the given substring (case-insensitive)."""
    combined = " ".join(result["issues"]).lower()
    assert text.lower() in combined, (
        f"Expected '{text}' somewhere in issues: {result['issues']}"
    )
