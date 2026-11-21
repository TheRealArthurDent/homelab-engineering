"""setup/install-claude-config.sh installs the shared config into ~/.claude without clobbering what is there."""

import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "setup" / "install-claude-config.sh"
IMPORT = "@~/.claude/homelab/CLAUDE.md"


def install(dest):
    subprocess.run(["bash", str(SCRIPT)], env={"CLAUDE_CONFIG_DIR": str(dest), "PATH": "/usr/bin:/bin:/usr/local/bin",
                   "HOME": str(dest.parent)}, check=True, capture_output=True)


def test_installs_into_an_empty_config_dir(tmp_path):
    dest = tmp_path / ".claude"
    install(dest)
    assert (dest / "hooks" / "guard.py").read_text() == (ROOT / "claude" / "hooks" / "guard.py").read_text()
    assert (dest / "hooks" / "hosts.json").exists()
    assert (dest / "skills" / "ansible-role" / "SKILL.md").exists()
    assert (dest / "skills" / "cross-repo-changes" / "SKILL.md").exists()
    assert (dest / "agents" / "homelab-reviewer.md").exists()
    assert IMPORT in (dest / "CLAUDE.md").read_text().splitlines()
    settings = json.loads((dest / "settings.json").read_text())
    assert len(settings["hooks"]["PreToolUse"]) == 3


def test_keeps_existing_settings_and_is_idempotent(tmp_path):
    dest = tmp_path / ".claude"
    dest.mkdir()
    (dest / "CLAUDE.md").write_text("# My own rules\n- be brief\n")
    own_hook = {"matcher": "Bash", "hooks": [{"type": "command", "command": "my-hook"}]}
    (dest / "settings.json").write_text(json.dumps({
        "model": "opus",
        "hooks": {"PreToolUse": [own_hook]},
        "permissions": {"allow": ["Bash(ls:*)"], "deny": ["Read(**/.env)"]},
    }))

    install(dest)
    install(dest)

    claude_md = (dest / "CLAUDE.md").read_text()
    assert claude_md.startswith("# My own rules\n- be brief\n")
    assert claude_md.splitlines().count(IMPORT) == 1
    settings = json.loads((dest / "settings.json").read_text())
    assert settings["model"] == "opus"
    assert settings["permissions"]["allow"] == ["Bash(ls:*)"]
    assert settings["permissions"]["deny"].count("Read(**/.env)") == 1
    assert settings["hooks"]["PreToolUse"][0] == own_hook
    assert len(settings["hooks"]["PreToolUse"]) == 4
    assert (dest / "settings.json.bak").exists()
