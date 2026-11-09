import json
import sys

import pytest

CONTRACT = "contracts/rubric_escrow.py"
DELIVERABLE = "https://gist.github.com/someone/abc123"

CRITERIA = [
    {"text": "Explains how to run the indexer locally", "weight": 30, "required": True},
    {"text": "Documents every environment variable", "weight": 30, "required": True},
    {"text": "Includes a troubleshooting section", "weight": 20, "required": False},
    {"text": "Mentions the supported Postgres versions", "weight": 20, "required": False},
]

PAGE = """Indexer setup guide
To run the indexer locally, clone the repo and run `make dev`, which starts Postgres and the worker.
Environment variables: DATABASE_URL sets the connection string, RPC_URL points at the node, LOG_LEVEL controls verbosity.
Troubleshooting: if the worker exits immediately, check that RPC_URL is reachable from the container.
Signed by {addr}
"""


def warp(vm, ts: str) -> None:
    """Keep gl.message_raw['datetime'] in sync with the direct-mode clock."""
    vm.warp(ts)
    gl = sys.modules.get("genlayer.gl")
    if gl is not None and getattr(gl, "message_raw", None) is not None:
        gl.message_raw["datetime"] = ts


def grades(*rows):
    """rows: (met, evidence) per criterion, in order."""
    return json.dumps(
        {"criteria": [{"id": i, "met": m, "evidence": e} for i, (m, e) in enumerate(rows)]}
    )


GOOD = grades(
    (True, "To run the indexer locally, clone the repo and run `make dev`"),
    (True, "DATABASE_URL sets the connection string, RPC_URL points at the node"),
    (True, "Troubleshooting: if the worker exits immediately"),
    (False, ""),
)


def mock_deliverable(vm, page: str, answer: str) -> None:
    vm.mock_web(r".*gist\.github\.com.*", {"status": 200, "body": page})
    vm.mock_llm(r".*reviewing a deliverable.*", answer)


def addr_hex(raw) -> str:
    if hasattr(raw, "as_hex"):
        return raw.as_hex
    from genlayer.py.types import Address

    return Address(raw).as_hex


@pytest.fixture
def escrow(direct_vm, direct_deploy, direct_alice):
    direct_vm.check_pickling = True
    direct_vm.sender = direct_alice
    c = direct_deploy(CONTRACT)
    warp(direct_vm, "2026-11-01T12:00:00Z")
    return c


@pytest.fixture
def bounty(escrow, direct_vm, direct_alice):
    """A funded bounty posted by alice: 1000 units, pass at 70, claim required."""
    direct_vm.sender = direct_alice
    direct_vm.value = 1000
    bid = escrow.create_bounty(
        "Write a setup guide for the indexer",
        "A single page that gets a new contributor from clone to running indexer.",
        CRITERIA,
        70,
        2,
        True,
        1793620800,  # 2026-11-03T12:00:00Z
    )
    direct_vm.value = 0
    return bid
