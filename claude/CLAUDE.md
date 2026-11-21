# Homelab – cross-repo context

Installed by homelab-engineering's `setup/install-claude-config.sh`; edit it there, not here.

This user runs a smart home and private cloud on Raspberry Pis (Debian/Raspberry Pi OS trixie, arm64), deployed with
Ansible and Docker Compose. Each repo's own `CLAUDE.md` is authoritative for work inside that repo; read it before
changing anything there. This file only covers what spans repos.

## Repos

| Repo | What | Runs on |
| --- | --- | --- |
| `infrastructure` | Host setup, Docker, nginx reverse proxy, Pi-hole, unbound, certificates, secrets (KeePass → `.env`), restic backups, monitoring | all Pis |
| `smart-home` | ioBroker, deCONZ, Mosquitto, InfluxDB, Telegraf, Grafana | raspi |
| `private-cloud` | OpenCloud, Paperless-ngx | dungeon |
| `homelab-engineering` | This shared Claude config: guard hook, hosts policy, shared skills and agents, environment setup | – |
| `renovate` | Renovate runs and shared Renovate config for the repos above | – |

**Dependencies point one way: the app repos depend on infrastructure, never the reverse.** infrastructure provides
the Docker networks (`siz`, `outbound`), nginx vhosts, Pi-hole records, certificate SANs, the secrets files and the
backups. An app change that needs any of these is a change in two repos; see the `cross-repo-changes` skill.

## Hosts

Production hosts and the test host are listed in `~/.claude/hooks/hosts.json` (source: homelab-engineering's
`claude/hooks/hosts.json`). The guard hook blocks ansible, ssh, scp and rsync against production, ansible without
`--limit`, pushes to `main`, force pushes, merges, and reading or committing secrets. Don't work around a block; hand
the user the command or propose the change.

The Pis are reachable only from the home network. In a cloud session, don't probe the LAN: rollouts to the test Pi and
to production are commands you hand the user, test host first (`--check --diff`, real run, second run with
`changed=0`).

## Working across repos

- One PR per repo. When a change spans repos, say which PR must be merged and deployed first (infrastructure, as a
  rule) and link the PRs to each other.
- Skills shared by all repos live in homelab-engineering (`ansible-role`, `cross-repo-changes`); repo-specific skills
  stay in the repo's `.claude/skills/`.
- When the same file or rule is copied into several repos and they drift, say so instead of fixing only one copy.
