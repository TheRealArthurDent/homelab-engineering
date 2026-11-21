# homelab-engineering

Shared Claude Code config for [infrastructure](https://github.com/TheRealArthurDent/infrastructure),
[smart-home](https://github.com/TheRealArthurDent/smart-home) and
[private-cloud](https://github.com/TheRealArthurDent/private-cloud).

The three repos each carry their own copy of the guard hook, its settings and its tests, and the copies have drifted:
infrastructure's `guard.py` does not block `dungeon` (production, backup target), still points to the old host name `testbed` and still has
rules for the deleted `deploy.sh`. And in a cloud session with several repos checked out, only the settings of the
repo the session starts in apply, if any. This repo keeps **one** guard and **one** hosts policy and installs them
user-wide, so they apply in every session, whatever repo it starts in.

How the homelab itself fits together (hosts, shared services, stacks, repos): [ARCHITECTURE.md](ARCHITECTURE.md).

## What's in it

| Path | Installed to | What |
| --- | --- | --- |
| `claude/hooks/guard.py` | `~/.claude/hooks/` | The union of the three repos' guards, production hosts read from `hosts.json`; fails closed without it |
| `claude/hooks/hosts.json` | `~/.claude/hooks/` | Production (`raspi`, `dungeon`) and test (`testbench`) hosts |
| `claude/settings.json` | merged into `~/.claude/settings.json` | Hook wiring and deny rules for secrets |
| `claude/CLAUDE.md` | `~/.claude/homelab/CLAUDE.md`, imported from `~/.claude/CLAUDE.md` | Cross-repo context: repo map, dependency direction, hosts |
| `claude/skills/ansible-role/` | `~/.claude/skills/` | Moved from infrastructure; smart-home and private-cloud already point to it |
| `claude/skills/cross-repo-changes/` | `~/.claude/skills/` | What an app change needs in infrastructure, and in which order |
| `claude/agents/homelab-reviewer.md` | `~/.claude/agents/` | Read-only review with a fresh context before a PR |

Repo-specific skills (`working-with-ansible`, `working-with-the-stack`) stay in their repos.

Besides the Claude config, `github/github-settings.sh` keeps a repo's GitHub settings in files, for every homelab
repo: rulesets (`.github/rulesets/`), repository settings (`.github/repo-settings.json`) and collaborators
(`.github/collaborators.json`, e.g. the Renovate bot). Run it from inside the repo; it takes the repo from `origin`:

```sh
cd ~/dev/smart-home && ~/dev/homelab-engineering/github/github-settings.sh diff   # or apply, export [--force]
```

`apply` only invites a new collaborator; the invitee accepts under their own login (see the script's header).

## Setup

**Cloud environment** (claude.ai/code): add all four repos to the environment, allow network access to github.com,
pypi.org, files.pythonhosted.org and galaxy.ansible.com, and set the setup script to

```sh
bash "$(find / -maxdepth 5 -path '*/homelab-engineering/setup/cloud-environment.sh' 2>/dev/null | head -n1)"
```

It installs the config, creates each repo's `.venv` with its tooling and installs Superpowers. Only the config install
is mandatory; the rest warns and continues when a package index is blocked.

**WSL**: `bash setup/install-claude-config.sh` from this checkout; again after every pull.

**Check that the guard is active** in a new session, by asking Claude to run `ansible-playbook x.yaml --limit raspi`.
It must answer with "Blocked by guard.py". If it doesn't, the session didn't load `~/.claude/settings.json`.

## Rollout, step by step

1. Create the repo, push this content, then apply its own settings: `github/github-settings.sh apply` from this
   checkout (rulesets, auto merge, secret scanning, `P4ranoidAndroid` as collaborator for Renovate).
2. Set up the cloud environment as above and run the guard check.
3. **Now, independently of the rest:** fix infrastructure's own `guard.py` (dungeon, `testbench`, no `deploy.sh`).
   Until step 5 it is the only guard in local WSL sessions started in infrastructure.
4. Rename the last uses of the old name `testbed` in private-cloud (inventory, CLAUDE.md, README, guard) to `testbench`.
5. Once the shared guard has run for a while: in each repo, replace `.claude/hooks/guard.py`, its settings entries and
   `test_guard_hook.py` with a pointer to this repo, and delete `ansible-role` from infrastructure. One PR per repo.
6. Replace each repo's `scripts/github-settings.sh` with this repo's `github/github-settings.sh` (the copies differ
   only in their default `REPO`), and add a `.github/collaborators.json` where the Renovate bot needs access. The
   repos' `test_repo_settings.py` check for their own script and need adjusting in the same PR.
7. Later, if the drift keeps costing time: move the other copied files here too (lint configs, `test_rulesets.py`,
   `test_repo_hygiene.py`) and sync them with a script.

## Development

```sh
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/pytest          # needs infrastructure, smart-home, private-cloud checked out next to this repo
```
