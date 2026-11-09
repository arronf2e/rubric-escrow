"""Deterministic grading rules, tested without any web or LLM mocks."""

import pytest


@pytest.fixture
def mod(direct_deploy):
    direct_deploy("contracts/rubric_escrow.py")
    import sys

    for m in list(sys.modules.values()):
        if hasattr(m, "RubricEscrow") and hasattr(m, "check_against_page"):
            return m
    raise RuntimeError("contract module not found")


def test_normalize_handles_typography(mod):
    assert mod.normalize("It\u2019s  \n DONE\u2014really") == "it's done-really"


def test_grounding_requires_verbatim_quote(mod):
    page = mod.normalize("The CLI exposes a --dry-run flag for safe testing.")
    assert mod.is_grounded("exposes a --dry-run flag", page)
    assert mod.is_grounded("EXPOSES   a --dry-run   FLAG", page)
    assert not mod.is_grounded("supports a dry run mode", page)  # paraphrase
    assert not mod.is_grounded("flag", page)  # too short to mean anything


def test_weighted_score_rounding(mod):
    assert mod.weighted_score([True, False, False], [1, 1, 1]) == 33
    assert mod.weighted_score([True, True, False], [1, 1, 1]) == 67
    assert mod.weighted_score([], []) == 0


def test_decide_respects_required(mod):
    weights = [50, 50]
    assert mod.decide([True, True], weights, [True, False], 60)
    assert not mod.decide([False, True], weights, [True, False], 10)
    assert not mod.decide([True, False], weights, [True, False], 60)


def test_parse_grades_is_defensive(mod):
    answer = {
        "criteria": [
            {"id": "1", "met": True, "evidence": "quoted"},
            {"id": 7, "met": True, "evidence": "out of range"},
            {"id": 0, "met": "yes", "evidence": "not a bool"},
            "garbage",
        ]
    }
    assert mod.parse_grades(answer, 2) == [(False, "not a bool"), (True, "quoted")]
    assert mod.parse_grades("nonsense", 2) == [(False, ""), (False, "")]


def test_check_against_page_downgrades_fabrications(mod):
    page = "Run make dev to start everything."
    out = mod.check_against_page(
        [(True, "Run make dev to start"), (True, "Run docker compose up")], page, ""
    )
    assert out["met"] == [True, False]
    assert out["evidence"][1] == ""


def test_missing_claim_voids_everything(mod):
    page = "Run make dev to start everything."
    out = mod.check_against_page([(True, "Run make dev to start")], page, "0xabc")
    assert out == {"met": [False], "evidence": [""], "claim_ok": False}
