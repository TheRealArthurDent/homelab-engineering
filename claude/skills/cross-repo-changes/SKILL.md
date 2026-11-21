---
name: cross-repo-changes
description: Use when a change in smart-home or private-cloud needs something from infrastructure (a new secret or env key, a new web UI or hostname, a new Docker volume that must be backed up and restored, a new outbound connection, a new app or stack), when moving an app to another Pi, or when a change in infrastructure could break the app stacks (networks, nginx, secrets role, restic). Lists what goes where and in which order to merge and roll out.
---

# Changes that span repos

The app repos (`smart-home`, `private-cloud`) depend on `infrastructure`; infrastructure never depends on them. Most
app features are therefore two PRs: the infrastructure part first, the app part second. Before starting, check each
repo's open issues for the area and each repo's CLAUDE.md for its current layout: role names below may have moved.

## Checklist by change

| Change in the app repo | Also needed in infrastructure |
| --- | --- |
| New secret / env key | Key in the app's `.env.example` (or a Compose secret file for new apps, like Paperless); the line in the `secrets` role (`no_log: true`); the KeePass lookup and the entry name in `ansible/README.md`. The app references `${VAR}` only. |
| New web UI | nginx vhost (`reverse_proxy` role), Pi-hole record (`configs/pihole.yaml`), the name in the certificate SANs (`certificate_check_subdomains`). The container joins network `siz` in the app repo. |
| Container needs the internet | Network `outbound` in the app's compose file; for a new destination, allow it in the outbound Pi-hole (`configs/pihole.yaml`). |
| New volume with state | The app's restore list (`smart_home_restore_volumes` and its test, or the app role's defaults); after the first deployment wrote its marker, the stack in `resticprofile_backup_stacks` in the host's `host_vars` (older READMEs call it `stack_backup_stacks`). Volumes that must not be backed up (database files that are dumped instead) go into the `resticprofile` excludes. |
| Trusts the private root CA | Mount `/etc/ssl/certs/rootCA.pem`, label the container `root-ca.restart-on-change`. |
| New app / stack on a Pi | Everything above, plus the stack in the host's `host_vars` where the components are switched. |

## Order of work

1. **One branch and PR per repo.** Link the PRs to each other and to the issue(s).
2. **infrastructure first**: its PR is merged and rolled out (test host, then production) before the app PR is
   deployed. Say so explicitly in both PR descriptions; CI in the app repo cannot detect a missing vhost or secret.
3. **Keep the docs that describe the contract in sync**: the app README's "what infrastructure has to provide" table
   and the infrastructure README's KeePass entry list.
4. **Hand the user the rollout in order**, e.g.:

```sh
# 1. infrastructure (user's machine, WSL), same three steps as in its working-with-ansible skill
cd ansible && ansible-playbook bootstrap.yaml --limit testbench --check --diff
# 2. then the app repo
cd ansible && ansible-playbook deploy.yaml --limit testbench --check --diff
# each: --check --diff, real run, second real run with changed=0; production only after the user says so
```

## Changes in infrastructure that can break the apps

Renaming or removing the networks `siz` or `outbound`, changing the `.env` paths or quoting the `secrets` role
writes (`dotenv_quote`), the `restic-restore` helper's interface, or the root CA handling. Before such a change,
grep the app repos (they are checked out next to infrastructure in the cloud environment) and list the affected
files in the PR.
