#!/usr/bin/env python3
"""PreToolUse guard for Claude Code, shared by infrastructure, smart-home and private-cloud.

Installed user-wide (~/.claude/hooks/guard.py) by setup/install-claude-config.sh, so it applies whichever repo a
session starts in, including cloud sessions with several repos checked out side by side.

Reads the hook event (JSON) on stdin. Exit 2 blocks the tool call and shows stderr to Claude; exit 0 lets it
through. Prose rules in CLAUDE.md can be overlooked, this can't. Which hosts are production comes from hosts.json
next to this file; if it is missing or broken, every ansible/ssh call is blocked (fail closed).
"""
import json
import re
import sys
from pathlib import Path

event = json.load(sys.stdin)
tool = event.get("tool_name", "")
args = event.get("tool_input", {}) or {}


def block(reason):
    print(f"Blocked by guard.py: {reason}", file=sys.stderr)
    sys.exit(2)


def load_hosts():
    try:
        hosts = json.loads((Path(__file__).resolve().parent / "hosts.json").read_text())
        return hosts["production"], hosts["test"]
    except (OSError, ValueError, KeyError):
        return None, None


production, test = load_hosts()
if production:
    names = [re.escape(n) for n in production]
    addresses = [re.escape(h["address"]) for h in production.values()]
    PROD = r"(" + "|".join(rf"\b{x}\b" for x in names + addresses) + r")"
    PROD_LABEL = " or ".join(production)
    TEST_HOST = next(iter(test), "testbench")
else:
    PROD = r"(.)"  # unknown policy: treat every target as production
    PROD_LABEL = "production (hosts.json missing or broken)"
    TEST_HOST = "testbench"

# -f, --force, or -f among combined short flags (-Af); not --force-with-lease.
FORCE = r"\s(-[a-zA-Z]*f[a-zA-Z]*|--force)(?=\s|$)"
# .env files on the host and in the repos, not .env.example or .envrc.example.
ENV_FILE = r"(^|[\s/'\"])\.env(?=[\s'\";|&)]|$)"
# Local-only files that hold secrets or point at them.
SECRET_FILE = ENV_FILE + r"|local\.yaml(\s|$)|\.kdbx(\s|$)|\.keyx?(\s|$)"
# The guardrails: this hook, its hosts.json and Claude's settings, both installed (~/.claude/, <repo>/.claude/)
# and at their source in homelab-engineering (claude/).
GUARDRAILS = r"\.?claude/(settings[^/\s]*\.json|hooks/)"


def runs(program):
    """Regex for `program` run as a command (also via a path, sudo, bash, env vars or bin/with-keepass),
    not merely named as an argument like `cat deploy.yaml` or `ansible/`."""
    return (
        r"(?:^|[;&|(]|\$\()\s*(?:\w+=\S*\s+)*(?:(?:sudo|bash|sh|exec|\S*with-keepass)\s+)*(?:\S*/)?"
        + program
        + r"(?=\s|$|[;&|)])"
    )


if tool == "Bash":
    cmd = args.get("command", "")

    # 1. Production: the user runs everything against production hosts.
    if re.search(runs(r"(?:ssh|scp|rsync|sftp)"), cmd) and re.search(PROD, cmd):
        block(f"direct access to {PROD_LABEL} (production). Hand the user the command instead.")
    if re.search(runs(r"ansible(?:-playbook)?"), cmd):
        if not re.search(r"(--limit|-l)[ =]", cmd):
            block(f"ansible without --limit. Use --limit {TEST_HOST}.")
        if re.search(r"(--limit|-l)[ =]['\"]?[^ ]*(" + PROD[1:-1] + r"|\ball\b|\*)", cmd):
            block(f"ansible against {PROD_LABEL} (production) or all hosts. Hand the user the command instead.")

    # 2. main branch: work on a branch, PR into main.
    # Flags are checked per command, so `rm -f x && git push` or a branch named `...-f75dkr` don't count.
    for part in re.split(r"&&|\|\||[;|\n]", cmd):
        if re.search(r"\bgit\s+push\b", part):
            if re.search(r"(\s|:)(refs/heads/)?main\b", part) or re.search(r"\s(--mirror|--all)\b", part):
                block("push to main. Push your feature branch and open a PR.")
            if re.search(FORCE, part):
                block("force push. Use --force-with-lease on your own branch, if at all.")
        if re.search(r"\bgit\s+add\b", part) and re.search(FORCE, part):
            block("git add --force bypasses .gitignore (local.yaml, .env).")
        if re.search(r"\bgit\s+(add|commit)\b", part) and re.search(SECRET_FILE, part):
            block("committing secrets or local KeePass config (.env, local.yaml, KeePass files).")

    # 3. Secrets: never print .env files, never touch the KeePass master password.
    if re.search(ENV_FILE, cmd) and not re.search(r"\bgit\s+(add|commit|rm|check-ignore)\b", cmd):
        block("reading a .env file prints the stack's passwords. Use the .env.example files for the keys.")
    if re.search(r"with-keepass\s+--(store|forget)", cmd):
        block("with-keepass --store/--forget is the user's job.")
    if re.search(r"KEEPASS_PASSWORD", cmd) and re.search(r"\b(echo|printf|printenv|env|set|cat|export)\b", cmd):
        block("touching KEEPASS_PASSWORD. The user types it into the prompt.")

    # 4. Guardrails protect themselves.
    if re.search(GUARDRAILS, cmd) and re.search(
        r"(>|\bsed\s+-i|\brm\b|\bmv\b|\bcp\b|\bln\b|\btee\b|\bchmod\b|\btruncate\b)", cmd
    ):
        block("changing Claude's own guardrails from the shell. Propose the change to the user.")

elif tool in ("Edit", "Write", "MultiEdit", "NotebookEdit"):
    path = args.get("file_path", "") or args.get("notebook_path", "")
    if re.search(GUARDRAILS, path):
        block("editing Claude's own guardrails. Propose the change to the user.")
    if re.search(r"(/|^)\.env$|\.kdbx$|\.keyx?$", path):
        block("writing secret files (.env, KeePass).")

elif tool.startswith("mcp__github__"):
    # GitHub MCP tools write without git, so the git push rule doesn't see them.
    if tool.endswith(("merge_pull_request", "enable_pr_auto_merge")):
        block("merging is the user's decision.")
    if tool.endswith(("push_files", "create_or_update_file", "delete_file")):
        if args.get("branch") in ("main", "refs/heads/main"):
            block("writing to main through the GitHub API.")

sys.exit(0)
