#!/usr/bin/env bash
# Keeps a repository's GitHub settings in files, for all homelab repos. Run it from inside the repo to manage:
#
#   .github/rulesets/<name>.json  one file per ruleset, in the format GitHub uses to export and import rulesets
#   .github/repo-settings.json    other settings (auto merge, branch cleanup, secret scanning, ...), in the format
#                                 of `PATCH /repos/{owner}/{repo}`; settings not in the file are left alone
#   .github/collaborators.json    collaborators and their permission ({"<login>": "pull|triage|push|maintain|admin"});
#                                 collaborators not in the file are left alone
#
#   github-settings.sh export [--force]  # write the live settings to the files
#   github-settings.sh diff              # show how the files differ from GitHub
#   github-settings.sh apply             # send the files to GitHub
#
# A ruleset file matches a ruleset by its "name". export skips files that already exist unless --force is given,
# so it never overwrites local edits; for repo-settings.json it exports the fields the file already lists. apply
# leaves rulesets without a file alone; delete those in the UI. A missing file skips its part.
#
# apply only invites a new collaborator: the invitee accepts it under their own login (for a bot, with its token:
# `gh api user/repository_invitations`, then `gh api --method PATCH user/repository_invitations/<id>`).
#
# The repo is taken from the `origin` remote; set REPO=<owner>/<name> to override.
# Needs gh, logged in as a repository admin, and jq.
set -euo pipefail
shopt -s nullglob

ROOT="$(git rev-parse --show-toplevel)"
if [[ -z "${REPO:-}" ]]; then
  REPO="$(git -C "$ROOT" remote get-url origin | sed -E 's#\.git$##; s#.*[:/]([^/]+/[^/]+)$#\1#')"
fi
OWNER="${REPO%%/*}"
RULESETS_DIR="$ROOT/.github/rulesets"
SETTINGS_FILE="$ROOT/.github/repo-settings.json"
COLLABORATORS_FILE="$ROOT/.github/collaborators.json"

# The fields GitHub accepts when creating or updating a ruleset.
FIELDS='{name, target, enforcement, conditions, rules, bypass_actors}'

# --- rulesets ---------------------------------------------------------------

live_ids() {
  gh api "repos/$REPO/rulesets?includes_parents=false" --paginate --jq '.[].id'
}

live_ruleset() {
  gh api "repos/$REPO/rulesets/$1" | jq --sort-keys "$FIELDS"
}

id_by_name() {
  gh api "repos/$REPO/rulesets?includes_parents=false" --paginate \
    --jq ".[] | select(.name == \"$1\") | .id"
}

rulesets_export() {
  local force="${1:-}"
  mkdir -p "$RULESETS_DIR"
  for id in $(live_ids); do
    local json name file
    json="$(live_ruleset "$id")"
    name="$(jq -r .name <<<"$json")"
    file="$RULESETS_DIR/$name.json"
    if [[ -e "$file" && "$force" != "--force" ]]; then
      echo "skip   ruleset $name (file exists, use --force to overwrite)"
      continue
    fi
    jq . <<<"$json" >"$file"
    echo "export ruleset $name -> ${file#"$ROOT/"}"
  done
}

rulesets_diff() {
  local changed=0
  for file in "$RULESETS_DIR"/*.json; do
    local name id
    name="$(jq -r .name "$file")"
    id="$(id_by_name "$name")"
    if [[ -z "$id" ]]; then
      echo "new    ruleset $name (not on GitHub yet)"
      changed=1
      continue
    fi
    if ! diff -u --label "github/ruleset/$name" --label "file/ruleset/$name" \
      <(live_ruleset "$id") <(jq --sort-keys "$FIELDS" "$file"); then
      changed=1
    fi
  done
  return "$changed"
}

rulesets_apply() {
  for file in "$RULESETS_DIR"/*.json; do
    local name id
    name="$(jq -r .name "$file")"
    id="$(id_by_name "$name")"
    if [[ -z "$id" ]]; then
      jq "$FIELDS" "$file" | gh api --method POST "repos/$REPO/rulesets" --input - >/dev/null
      echo "create ruleset $name"
    else
      jq "$FIELDS" "$file" | gh api --method PUT "repos/$REPO/rulesets/$id" --input - >/dev/null
      echo "update ruleset $name"
    fi
  done
}

# --- repository settings ----------------------------------------------------

# The live values of exactly the fields the file sets, nested ones included.
live_settings() {
  gh api "repos/$REPO" | jq --sort-keys --slurpfile want "$SETTINGS_FILE" '
    . as $live
    | [$want[0] | paths(scalars)] as $paths
    | reduce $paths[] as $p ({}; setpath($p; $live | getpath($p)))'
}

settings_export() {
  if [[ ! -e "$SETTINGS_FILE" ]]; then
    echo "skip   repo-settings.json (no file: list the fields to manage in it first)"
    return
  fi
  if [[ "${1:-}" != "--force" ]]; then
    echo "skip   repo-settings.json (file exists, use --force to overwrite)"
    return
  fi
  local live
  live="$(live_settings)"
  jq . <<<"$live" >"$SETTINGS_FILE"
  echo "export repo settings -> ${SETTINGS_FILE#"$ROOT/"}"
}

settings_diff() {
  [[ -e "$SETTINGS_FILE" ]] || return 0
  diff -u --label "github/repo-settings" --label "file/repo-settings" \
    <(live_settings) <(jq --sort-keys . "$SETTINGS_FILE")
}

settings_apply() {
  [[ -e "$SETTINGS_FILE" ]] || return 0
  gh api --method PATCH "repos/$REPO" --input "$SETTINGS_FILE" >/dev/null
  echo "update repo settings"
}

# --- collaborators ----------------------------------------------------------

# Live permissions as {"<login>": "<permission>"}: direct collaborators, then pending invitations ("<permission>
# (invited)"), without the owner. GitHub reports read/write where the API takes pull/push; mapped back here.
live_collaborators() {
  {
    gh api "repos/$REPO/collaborators?affiliation=direct" --paginate \
      --jq '.[] | {(.login): .role_name}'
    gh api "repos/$REPO/invitations" --paginate \
      --jq '.[] | {(.invitee.login): "\(.permissions) (invited)"}'
  } | jq -s --sort-keys --arg owner "$OWNER" '
      add // {} | del(.[$owner])
      | map_values(sub("^read"; "pull") | sub("^write"; "push"))'
}

# The live values of exactly the logins the file lists ("absent" for those without access).
live_listed_collaborators() {
  live_collaborators | jq --sort-keys --slurpfile want "$COLLABORATORS_FILE" '
    . as $live | $want[0] | with_entries(.value = ($live[.key] // "absent"))'
}

collaborators_export() {
  if [[ -e "$COLLABORATORS_FILE" && "${1:-}" != "--force" ]]; then
    echo "skip   collaborators.json (file exists, use --force to overwrite)"
    return
  fi
  live_collaborators | jq 'map_values(sub(" \\(invited\\)$"; ""))' >"$COLLABORATORS_FILE"
  echo "export collaborators -> ${COLLABORATORS_FILE#"$ROOT/"}"
}

collaborators_diff() {
  [[ -e "$COLLABORATORS_FILE" ]] || return 0
  diff -u --label "github/collaborators" --label "file/collaborators" \
    <(live_listed_collaborators) <(jq --sort-keys . "$COLLABORATORS_FILE")
}

collaborators_apply() {
  [[ -e "$COLLABORATORS_FILE" ]] || return 0
  local live login permission
  live="$(live_collaborators)"
  while IFS=$'\t' read -r login permission; do
    case "$(jq -r --arg l "$login" '.[$l] // ""' <<<"$live")" in
      "$permission") echo "keep   collaborator $login ($permission)" ;;
      "$permission (invited)") echo "wait   collaborator $login ($permission, invitation not accepted yet)" ;;
      *)
        # PUT invites a new collaborator, or changes the permission of an existing one or of an invitation.
        gh api --method PUT "repos/$REPO/collaborators/$login" -f permission="$permission" >/dev/null
        echo "invite collaborator $login ($permission)"
        ;;
    esac
  done < <(jq -r 'to_entries[] | "\(.key)\t\(.value)"' "$COLLABORATORS_FILE")
}

# --- commands ---------------------------------------------------------------

cmd_diff() {
  local changed=0
  rulesets_diff || changed=1
  settings_diff || changed=1
  collaborators_diff || changed=1
  [[ "$changed" == 0 ]] && echo "GitHub matches the files"
  return "$changed"
}

case "${1:-}" in
  export)
    rulesets_export "${2:-}"
    settings_export "${2:-}"
    collaborators_export "${2:-}"
    ;;
  diff) cmd_diff ;;
  apply)
    rulesets_apply
    settings_apply
    collaborators_apply
    ;;
  *)
    echo "usage: $0 export [--force] | diff | apply" >&2
    exit 2
    ;;
esac
