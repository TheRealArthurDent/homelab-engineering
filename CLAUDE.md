# homelab-engineering – shared Claude Code config for the homelab repos

Holds what infrastructure, smart-home and private-cloud share: the guard hook and its hosts policy, the user-level
CLAUDE.md, shared skills and agents, and the setup scripts that install them into `~/.claude`. See README.md.

## Layout

- `claude/` – what gets installed: `hooks/guard.py`, `hooks/hosts.json`, `settings.json`, `CLAUDE.md`, `skills/`,
  `agents/`
- `setup/install-claude-config.sh` – copies `claude/` into `~/.claude` and merges the settings
- `setup/cloud-environment.sh` – setup script of the Claude Code cloud environment
- `tests/` – pytest: guard rules, hosts policy against the sibling repos' inventories, installer

## Rules

- `claude/hooks/` and `claude/settings.json` are guardrails: the guard blocks edits to them, here as in the repos.
  Propose the change to the user, with the test cases for `tests/test_guard.py`.
- A guard rule change comes with blocked and allowed cases in `tests/test_guard.py`; run `pytest` (needs the sibling
  repos checked out next to this one for `tests/test_hosts.py`).
- Only what all three repos share goes here. A skill that only one repo needs stays in that repo.
- Never commit or push to `main`; branch, PR, the user merges. Conventional commits. Everything in English.
