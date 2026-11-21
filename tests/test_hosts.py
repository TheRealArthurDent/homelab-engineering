"""hosts.json, the guard's production policy, covers every host in the repos' inventories with the right address.

Runs against the sibling checkouts (infrastructure, smart-home, private-cloud next to this repo, as in the cloud
environment); a repo that isn't checked out is skipped.
"""

import json
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
HOSTS = json.loads((ROOT / "claude" / "hooks" / "hosts.json").read_text())
REPOS = ("infrastructure", "smart-home", "private-cloud")


def known_hosts():
    known = {}
    for kind in ("production", "test"):
        for name, host in HOSTS[kind].items():
            for alias in [name, *host.get("aliases", [])]:
                known[alias] = (kind, host["address"])
    return known


def test_no_address_is_both_production_and_test():
    prod = {h["address"] for h in HOSTS["production"].values()}
    test = {h["address"] for h in HOSTS["test"].values()}
    assert not prod & test


@pytest.mark.parametrize("repo", REPOS)
def test_inventory_hosts_are_classified(repo):
    inventory = ROOT.parent / repo / "ansible" / "inventory" / "hosts.yaml"
    if not inventory.exists():
        pytest.skip(f"{repo} not checked out next to homelab-engineering")
    hosts = yaml.safe_load(inventory.read_text())["all"]["hosts"]
    known = known_hosts()
    for name, values in hosts.items():
        assert name in known, f"{repo}: host {name} missing in hosts.json"
        assert values["ansible_host"] == known[name][1], f"{repo}: {name} has another address than in hosts.json"
