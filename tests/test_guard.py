"""The shared PreToolUse hook (claude/hooks/guard.py) blocks risky tool calls and lets everyday work through.

The command lists are the union of the three repos' test_guard_hook.py, minus the rules for the deleted deploy.sh,
plus dungeon, which infrastructure's own copy of the hook does not know about.
"""

import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
HOOK = ROOT / "claude" / "hooks" / "guard.py"
SETTINGS = ROOT / "claude" / "settings.json"


def run_hook(tool_name, tool_input, hook=HOOK):
    event = {"hook_event_name": "PreToolUse", "tool_name": tool_name, "tool_input": tool_input}
    return subprocess.run(
        [sys.executable, "-I", str(hook)], input=json.dumps(event), capture_output=True, text=True, check=False
    )


BLOCKED_COMMANDS = [
    # Production: raspi (smart home) and dungeon (private cloud, backup target)
    "ssh -p 1357 smarthome@192.168.1.2",
    "ssh smarthome@raspi -p 1357 'docker ps'",
    "scp install.tar smarthome@raspi:dev/smart-home",
    "rsync -a setup/ smarthome@192.168.1.2:dev/smart-home/setup/",
    "ssh pi@dungeon",
    "ssh -p 1359 dragon@192.168.1.5 'docker ps'",
    "scp backup.tar dragon@dungeon:",
    "rsync -a opencloud/ dragon@192.168.1.5:opencloud/",
    "cd ansible && ansible-playbook deploy.yaml --limit raspi",
    "ansible-playbook bootstrap.yaml -l raspi --check",
    "ansible-playbook bootstrap.yaml --limit dungeon",
    "bin/with-keepass ansible-playbook update.yaml -l dungeon",
    "KEEPASS_DB=x ansible-playbook setup-pihole.yaml -l raspi",
    "ansible-playbook deploy.yaml --limit=all",
    "ansible-playbook deploy.yaml --limit 'testbench,raspi'",
    "ansible-playbook deploy.yaml --limit 'testbench,dungeon'",
    "cd ansible && ../.venv/bin/ansible-playbook deploy.yaml",
    "ansible raspi -m ping",
    "ansible dungeon -m ping",
    # main branch
    "git push origin main",
    "git push origin HEAD:main",
    "git push --force origin feat/x",
    "git push -f origin claude/x",
    "git push --mirror",
    # Secrets
    "git add -f setup/.env",
    "git add .env",
    "git add -Af setup/",
    "git commit -m wip opencloud/.env",
    "git add ansible/inventory/group_vars/all/local.yaml",
    "cat setup/.env",
    "grep PASSWORD .env",
    "sudo cat /etc/docker/private-cloud/.env",
    "bin/with-keepass --store",
    "ansible/bin/with-keepass --forget",
    "echo $KEEPASS_PASSWORD",
    "printenv KEEPASS_PASSWORD",
    # The guardrails themselves: in a repo, installed user-wide, and at their source here
    "sed -i s/x/y/ .claude/settings.json",
    "rm .claude/hooks/guard.py",
    "echo '{}' > .claude/settings.local.json",
    "cp /tmp/guard.py ~/.claude/hooks/guard.py",
    "echo '{}' > ~/.claude/hooks/hosts.json",
    "sed -i s/dungeon/x/ claude/hooks/hosts.json",
    "ln -sf /dev/null homelab-engineering/claude/hooks/guard.py",
]

ALLOWED_COMMANDS = [
    "ansible-playbook bootstrap.yaml --limit testbench --check --diff",
    "cd ansible && ansible-playbook deploy.yaml --limit testbench --check --diff",
    "bin/with-keepass ansible-playbook bootstrap.yaml --limit testbench",
    "ANSIBLE_ROLES_PATH=roles ansible-playbook -i localhost, --syntax-check --limit localhost converge.yaml",
    ".venv/bin/ansible-lint --strict ansible/",
    "cd ansible && ../.venv/bin/molecule test",
    "ansible-galaxy collection install -r ansible/requirements.yaml",
    "pytest tests/test_limit_guard.py",
    ".venv/bin/pytest tests",
    "docker compose config --quiet",
    "ssh -p 4242 testuser@192.168.1.7",
    "grep -n ssh ansible/inventory/hosts.yaml | grep raspi",
    "grep -n dungeon ansible/inventory/hosts.yaml",
    "cat deploy.sh",
    "git commit -m 'fix: raspi nginx redirect'",
    "git add ansible/inventory/group_vars/all/local.example.yaml",
    "git add setup/.env.example",
    "git add .envrc.example",
    "cat opencloud/.env.example",
    "git push -u origin claude/project-thread-f75dkr",
    "git push --force-with-lease origin claude/x",
    "rm -f /tmp/x && git push origin claude/x",
    "git add -A && git commit -q -F msg.txt && git push -u origin claude/project-thread-v1246k",
    "cat .claude/settings.json",
    "cat ~/.claude/hooks/hosts.json",
    "git diff main -- .claude/hooks/guard.py claude/hooks/guard.py",
]


def assert_blocked(result):
    assert result.returncode == 2, result
    assert "Blocked by guard.py" in result.stderr


@pytest.mark.parametrize("command", BLOCKED_COMMANDS)
def test_blocks_risky_command(command):
    assert_blocked(run_hook("Bash", {"command": command}))


@pytest.mark.parametrize("command", ALLOWED_COMMANDS)
def test_allows_everyday_command(command):
    result = run_hook("Bash", {"command": command})
    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize(
    "path",
    [
        "/home/user/smart-home/.claude/settings.json",
        "/home/user/infrastructure/.claude/hooks/guard.py",
        "/root/.claude/settings.json",
        "/root/.claude/hooks/hosts.json",
        "/home/user/homelab-engineering/claude/hooks/guard.py",
        "/home/user/homelab-engineering/claude/hooks/hosts.json",
        "/home/user/homelab-engineering/claude/settings.json",
        "/home/user/private-cloud/opencloud/.env",
        "/home/user/keys/raspberry.kdbx",
    ],
)
def test_blocks_editing_guardrails_and_secret_files(path):
    for tool in ("Edit", "Write"):
        assert_blocked(run_hook(tool, {"file_path": path}))


@pytest.mark.parametrize(
    "path",
    [
        "/home/user/smart-home/docker-compose.yaml",
        "/home/user/private-cloud/opencloud/.env.example",
        "/home/user/homelab-engineering/claude/CLAUDE.md",
        "/home/user/homelab-engineering/claude/skills/ansible-role/SKILL.md",
        "/root/.claude/skills/x/SKILL.md",
    ],
)
def test_allows_editing_other_files(path):
    assert run_hook("Write", {"file_path": path}).returncode == 0


def test_blocks_github_writes_to_main_and_merges():
    assert_blocked(run_hook("mcp__github__merge_pull_request", {"pullNumber": 1}))
    assert_blocked(run_hook("mcp__github__enable_pr_auto_merge", {"pullNumber": 1}))
    assert_blocked(run_hook("mcp__github__push_files", {"branch": "main"}))
    assert_blocked(run_hook("mcp__github__create_or_update_file", {"branch": "refs/heads/main"}))


def test_allows_github_feature_branch_work():
    assert run_hook("mcp__github__push_files", {"branch": "claude/x"}).returncode == 0
    assert run_hook("mcp__github__create_pull_request", {"base": "main"}).returncode == 0


def test_fails_closed_without_hosts_json(tmp_path):
    hook = tmp_path / "guard.py"
    shutil.copy(HOOK, hook)
    assert_blocked(run_hook("Bash", {"command": "ssh -p 4242 testuser@192.168.1.7"}, hook=hook))
    assert_blocked(run_hook("Bash", {"command": "ansible-playbook x.yaml --limit testbench"}, hook=hook))
    assert run_hook("Bash", {"command": "pytest tests"}, hook=hook).returncode == 0


def test_settings_route_all_guarded_tools_through_the_hook():
    settings = json.loads(SETTINGS.read_text())
    groups = settings["hooks"]["PreToolUse"]
    matchers = " ".join(g["matcher"] for g in groups)
    for tool in ("Bash", "Edit", "Write", "MultiEdit", "NotebookEdit", "merge_pull_request", "push_files"):
        assert tool in matchers
    for group in groups:
        assert group["hooks"] == [{"type": "command", "command": 'python3 "$HOME"/.claude/hooks/guard.py'}]


def test_settings_deny_reading_secrets():
    deny = json.loads(SETTINGS.read_text())["permissions"]["deny"]
    for rule in ("Read(**/.env)", "Read(**/*.kdbx)", "Read(**/inventory/group_vars/all/local.yaml)"):
        assert rule in deny
