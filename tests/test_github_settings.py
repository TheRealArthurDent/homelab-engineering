"""github/github-settings.sh keeps rulesets, repository settings and collaborators of a repo in files.

The tests run the script in a scratch repo against a fake `gh` that answers from fixtures and logs every call.
"""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "github" / "github-settings.sh"

FAKE_GH = r'''#!/usr/bin/env python3
import json, os, subprocess, sys
args = sys.argv[2:]  # drop "api"
method, path, jq, fields = "GET", None, None, {}
i = 0
while i < len(args):
    a = args[i]
    if a == "--method": method = args[i + 1]; i += 2; continue
    if a == "--jq": jq = args[i + 1]; i += 2; continue
    if a == "-f": k, v = args[i + 1].split("=", 1); fields[k] = v; i += 2; continue
    if a == "--input": i += 2; continue
    if a == "--paginate": i += 1; continue
    path = a; i += 1
with open(os.environ["GH_LOG"], "a") as log:
    log.write(json.dumps({"method": method, "path": path, "fields": fields}) + "\n")
fixtures = json.load(open(os.environ["GH_FIXTURES"]))
body = json.dumps(fixtures.get(f"{method} {path}", {}))
if jq:
    body = subprocess.run(["jq", "-rc", jq], input=body, capture_output=True, text=True, check=True).stdout
sys.stdout.write(body)
'''

COLLABORATORS = "repos/TheRealArthurDent/demo/collaborators?affiliation=direct"
INVITATIONS = "repos/TheRealArthurDent/demo/invitations"
OWNER = {"login": "TheRealArthurDent", "role_name": "admin"}


@pytest.fixture
def repo(tmp_path):
    work = tmp_path / "demo"
    (work / ".github").mkdir(parents=True)
    subprocess.run(["git", "init", "-q", str(work)], check=True)
    subprocess.run(["git", "-C", str(work), "remote", "add", "origin",
                    "https://github.com/TheRealArthurDent/demo.git"], check=True)
    (work / ".github" / "collaborators.json").write_text(json.dumps({"P4ranoidAndroid": "push"}))
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    (bin_dir / "gh").write_text(FAKE_GH.replace("/usr/bin/env python3", sys.executable, 1))
    (bin_dir / "gh").chmod(0o755)
    return work


def run(repo, command, fixtures):
    fixtures_file = repo.parent / "fixtures.json"
    fixtures_file.write_text(json.dumps(fixtures))
    log = repo.parent / "gh.log"
    log.write_text("")
    env = {**os.environ, "PATH": f"{repo.parent / 'bin'}:{os.environ['PATH']}", "GH_LOG": str(log),
           "GH_FIXTURES": str(fixtures_file)}
    env.pop("REPO", None)
    result = subprocess.run(["bash", str(SCRIPT), command], cwd=repo, env=env, capture_output=True, text=True)
    calls = [json.loads(line) for line in log.read_text().splitlines()]
    return result, calls


def puts(calls):
    return [c for c in calls if c["method"] != "GET"]


def test_apply_invites_a_missing_collaborator(repo):
    result, calls = run(repo, "apply", {f"GET {COLLABORATORS}": [OWNER], f"GET {INVITATIONS}": []})
    assert result.returncode == 0, result.stderr
    assert puts(calls) == [{"method": "PUT", "path": "repos/TheRealArthurDent/demo/collaborators/P4ranoidAndroid",
                            "fields": {"permission": "push"}}]
    assert "invite collaborator P4ranoidAndroid (push)" in result.stdout


def test_apply_keeps_a_collaborator_with_the_right_permission(repo):
    live = [OWNER, {"login": "P4ranoidAndroid", "role_name": "write"}]
    result, calls = run(repo, "apply", {f"GET {COLLABORATORS}": live, f"GET {INVITATIONS}": []})
    assert result.returncode == 0, result.stderr
    assert puts(calls) == []
    assert "keep   collaborator P4ranoidAndroid (push)" in result.stdout


def test_apply_waits_for_a_pending_invitation(repo):
    invitation = [{"invitee": {"login": "P4ranoidAndroid"}, "permissions": "write"}]
    result, calls = run(repo, "apply", {f"GET {COLLABORATORS}": [OWNER], f"GET {INVITATIONS}": invitation})
    assert result.returncode == 0, result.stderr
    assert puts(calls) == []
    assert "invitation not accepted yet" in result.stdout


def test_apply_changes_a_wrong_permission(repo):
    live = [OWNER, {"login": "P4ranoidAndroid", "role_name": "read"}]
    result, calls = run(repo, "apply", {f"GET {COLLABORATORS}": live, f"GET {INVITATIONS}": []})
    assert result.returncode == 0, result.stderr
    assert [c["fields"] for c in puts(calls)] == [{"permission": "push"}]


def test_diff_reports_a_missing_collaborator_and_ignores_unlisted_ones(repo):
    live = [OWNER, {"login": "someone-else", "role_name": "admin"}]
    result, _ = run(repo, "diff", {f"GET {COLLABORATORS}": live, f"GET {INVITATIONS}": []})
    assert result.returncode == 1
    assert '-  "P4ranoidAndroid": "absent"' in result.stdout
    assert "someone-else" not in result.stdout


def test_diff_is_clean_when_github_matches(repo):
    live = [OWNER, {"login": "P4ranoidAndroid", "role_name": "write"}]
    result, _ = run(repo, "diff", {f"GET {COLLABORATORS}": live, f"GET {INVITATIONS}": []})
    assert result.returncode == 0, result.stdout + result.stderr
    assert "GitHub matches the files" in result.stdout


def test_export_writes_collaborators_without_the_owner(repo):
    (repo / ".github" / "collaborators.json").unlink()
    live = [OWNER, {"login": "P4ranoidAndroid", "role_name": "write"}]
    invitation = [{"invitee": {"login": "LunaticGardener"}, "permissions": "read"}]
    result, _ = run(repo, "export", {f"GET {COLLABORATORS}": live, f"GET {INVITATIONS}": invitation})
    assert result.returncode == 0, result.stderr
    assert json.loads((repo / ".github" / "collaborators.json").read_text()) == {
        "LunaticGardener": "pull", "P4ranoidAndroid": "push"}


def test_missing_files_are_skipped(repo):
    (repo / ".github" / "collaborators.json").unlink()
    result, calls = run(repo, "apply", {})
    assert result.returncode == 0, result.stderr
    assert calls == []


# --- this repo's own settings files --------------------------------------------------------------------------------

def test_own_collaborators_use_api_permissions():
    """Renovate runs as a GitHub App, so this repo needs no collaborator file; if one comes back, it uses API names."""
    path = ROOT / ".github" / "collaborators.json"
    if not path.exists():
        return
    collaborators = json.loads(path.read_text())
    assert set(collaborators.values()) <= {"pull", "triage", "push", "maintain", "admin"}


def test_required_checks_exist_and_run_on_every_pr():
    """Every required check is a job of some workflow that runs on every PR. A context no job reports, or one skipped
    by a paths filter, would block every merge."""
    ruleset = json.loads((ROOT / ".github" / "rulesets" / "require-green-checks.json").read_text())
    required = {c["context"] for c in ruleset["rules"][0]["parameters"]["required_status_checks"]}
    jobs = {}
    for path in sorted((ROOT / ".github" / "workflows").glob("*.yaml")):
        workflow = yaml.safe_load(path.read_text())
        triggers = workflow.get("on", workflow.get(True))
        for key, job in workflow["jobs"].items():
            jobs[job.get("name", key)] = (path.name, triggers)
    assert required <= set(jobs), f"required checks without a job: {sorted(required - set(jobs))}"
    for context in required:
        workflow, triggers = jobs[context]
        assert "pull_request" in triggers, f"{context} ({workflow}) doesn't run on pull requests"
        assert "paths" not in (triggers["pull_request"] or {}), f"{context} ({workflow}) has a paths filter"
