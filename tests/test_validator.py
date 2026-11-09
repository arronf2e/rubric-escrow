"""
The validator half of the consensus block.

The leader runs with one set of mocks; then the mocks are swapped (or the
leader's output is replaced) to model a validator that fetched the page
separately or a leader that lied.
"""

from tests.conftest import DELIVERABLE, GOOD, PAGE, addr_hex, grades, mock_deliverable


def _leader_pass(escrow, bounty, vm, bob):
    mock_deliverable(vm, PAGE.format(addr=addr_hex(bob)), GOOD)
    vm.sender = bob
    escrow.submit(bounty, DELIVERABLE)


def _honest():
    return {
        "met": [True, True, True, False],
        "evidence": [
            "To run the indexer locally, clone the repo and run `make dev`",
            "DATABASE_URL sets the connection string, RPC_URL points at the node",
            "Troubleshooting: if the worker exits immediately",
            "",
        ],
        "claim_ok": True,
    }


def test_agrees_with_honest_leader(escrow, bounty, direct_vm, direct_bob):
    _leader_pass(escrow, bounty, direct_vm, direct_bob)
    assert direct_vm.run_validator() is True


def test_agrees_when_only_a_soft_criterion_differs(escrow, bounty, direct_vm, direct_bob):
    _leader_pass(escrow, bounty, direct_vm, direct_bob)
    direct_vm.clear_mocks()
    # validator's model also credits the Postgres criterion (wrongly, but with a
    # real quote): 100 vs 80 is inside the band and both runs pay out
    mock_deliverable(direct_vm, PAGE.format(addr=addr_hex(direct_bob)), grades(
        (True, "To run the indexer locally, clone the repo and run `make dev`"),
        (True, "DATABASE_URL sets the connection string, RPC_URL points at the node"),
        (True, "Troubleshooting: if the worker exits immediately"),
        (True, "which starts Postgres and the worker"),
    ))
    assert direct_vm.run_validator() is True


def test_rejects_when_payout_decision_differs(escrow, bounty, direct_vm, direct_bob):
    _leader_pass(escrow, bounty, direct_vm, direct_bob)
    direct_vm.clear_mocks()
    # validator does not credit the troubleshooting section: 80 vs 60 is
    # inside the band, but 60 is below pass_score, so the decision flips
    mock_deliverable(direct_vm, PAGE.format(addr=addr_hex(direct_bob)), grades(
        (True, "To run the indexer locally, clone the repo and run `make dev`"),
        (True, "DATABASE_URL sets the connection string, RPC_URL points at the node"),
        (False, ""),
        (False, ""),
    ))
    assert direct_vm.run_validator() is False


def test_rejects_leader_with_invented_quote(escrow, bounty, direct_vm, direct_bob):
    _leader_pass(escrow, bounty, direct_vm, direct_bob)
    forged = _honest()
    forged["met"][3] = True
    forged["evidence"][3] = "Supported Postgres versions: 14, 15 and 16"
    assert direct_vm.run_validator(leader_result=forged) is False


def test_rejects_leader_that_flips_a_required_criterion(escrow, bounty, direct_vm, direct_bob):
    _leader_pass(escrow, bounty, direct_vm, direct_bob)
    direct_vm.clear_mocks()
    # validator sees a page where env vars are no longer documented
    page = PAGE.format(addr=addr_hex(direct_bob)).replace(
        "Environment variables: DATABASE_URL sets the connection string, RPC_URL points at the node, LOG_LEVEL controls verbosity.\n",
        "",
    )
    mock_deliverable(direct_vm, page, GOOD)
    assert direct_vm.run_validator() is False


def test_rejects_claim_mismatch(escrow, bounty, direct_vm, direct_bob):
    _leader_pass(escrow, bounty, direct_vm, direct_bob)
    claimed = _honest()
    claimed["claim_ok"] = False
    assert direct_vm.run_validator(leader_result=claimed) is False


def test_rejects_malformed_leader_output(escrow, bounty, direct_vm, direct_bob):
    _leader_pass(escrow, bounty, direct_vm, direct_bob)
    assert direct_vm.run_validator(leader_result={"met": [True], "evidence": [], "claim_ok": True}) is False


def test_disputes_leader_error_when_page_is_fine(escrow, bounty, direct_vm, direct_bob):
    _leader_pass(escrow, bounty, direct_vm, direct_bob)
    assert direct_vm.run_validator(leader_error=Exception("deliverable is empty")) is False


def test_confirms_leader_error_when_page_is_down(escrow, bounty, direct_vm, direct_bob):
    _leader_pass(escrow, bounty, direct_vm, direct_bob)
    direct_vm.clear_mocks()
    direct_vm.mock_web(r".*gist\.github\.com.*", {"status": 200, "body": ""})
    assert direct_vm.run_validator(leader_error=Exception("deliverable is empty")) is True
