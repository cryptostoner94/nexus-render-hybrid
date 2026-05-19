#!/usr/bin/env bash
set -Eeuo pipefail

# sonar-auto-remedy.sh
# Free SonarCloud issue pull + native local auto-fix loop for Python/Node projects.
# No tokens are written to disk. Logs are written under .sonar-auto-remedy/.

ROOT_START="$(pwd)"
SONAR_HOST_URL="${SONAR_HOST_URL:-https://sonarcloud.io}"
LOG_ROOT_NAME=".sonar-auto-remedy"
ALLOW_UNSAFE_FIXES="${ALLOW_UNSAFE_FIXES:-0}"
AUTO_NPM_INSTALL="${AUTO_NPM_INSTALL:-0}"
AUTO_PUSH="${AUTO_PUSH:-0}"

say() { printf "\n\033[1;36m==>\033[0m %s\n" "$*"; }
warn() { printf "\n\033[1;33mWARN:\033[0m %s\n" "$*" >&2; }
fail() { printf "\n\033[1;31mERROR:\033[0m %s\n" "$*" >&2; exit 1; }

need_cmd() {
  command -v "$1" >/dev/null 2>&1 || fail "Missing required command: $1"
}

find_python() {
  if command -v python3 >/dev/null 2>&1; then
    echo "python3"
  elif command -v python >/dev/null 2>&1; then
    echo "python"
  else
    fail "Python is required for clean JSON merging. Install Python 3 or run inside your project venv."
  fi
}

json_get_total() {
  "$PYTHON_BIN" - "$1" <<'PY'
import json, sys
p=sys.argv[1]
try:
    data=json.load(open(p, encoding="utf-8"))
    print(int(data.get("paging", {}).get("total", 0)))
except Exception:
    print(0)
PY
}

json_get_page_size() {
  "$PYTHON_BIN" - "$1" <<'PY'
import json, sys
p=sys.argv[1]
try:
    data=json.load(open(p, encoding="utf-8"))
    print(int(data.get("paging", {}).get("pageSize", 500)))
except Exception:
    print(500)
PY
}

json_merge_pages() {
  local out="$1"; shift
  "$PYTHON_BIN" - "$out" "$@" <<'PY'
import json, sys, os
out=sys.argv[1]
files=sys.argv[2:]
issues=[]
seen=set()
meta={}
for f in files:
    try:
        data=json.load(open(f, encoding="utf-8"))
    except Exception as e:
        continue
    if not meta:
        meta={k:v for k,v in data.items() if k!="issues"}
    for issue in data.get("issues", []):
        key=issue.get("key") or json.dumps(issue, sort_keys=True)
        if key not in seen:
            seen.add(key)
            issues.append(issue)
result={
    "source": "sonarcloud",
    "generated_by": "sonar-auto-remedy.sh",
    "issue_count": len(issues),
    "issues": issues,
    "raw_metadata": meta
}
os.makedirs(os.path.dirname(out), exist_ok=True)
with open(out, "w", encoding="utf-8") as fh:
    json.dump(result, fh, indent=2, ensure_ascii=False)
    fh.write("\n")
print(len(issues))
PY
}

urlencode_fetch_page() {
  local project_param="$1"
  local project_key="$2"
  local page="$3"
  local outfile="$4"
  local http_code

  http_code="$(
    curl -sS -w "%{http_code}" -o "$outfile" -G \
      "${SONAR_HOST_URL%/}/api/issues/search" \
      -H "Authorization: Bearer ${SONAR_TOKEN}" \
      -H "Accept: application/json" \
      --data-urlencode "${project_param}=${project_key}" \
      --data-urlencode "resolved=false" \
      --data-urlencode "ps=500" \
      --data-urlencode "p=${page}" \
      --data-urlencode "additionalFields=_all" || true
  )"

  if [[ "$http_code" =~ ^2[0-9][0-9]$ ]]; then
    if "$PYTHON_BIN" - "$outfile" >/dev/null 2>&1 <<'PY'
import json, sys
data=json.load(open(sys.argv[1], encoding="utf-8"))
if isinstance(data, dict) and "errors" in data:
    raise SystemExit(1)
PY
    then
      return 0
    fi
  fi

  return 1
}

guess_project_key() {
  local repo_dir="$1"
  local key=""

  if [[ -f "$repo_dir/sonar-project.properties" ]]; then
    key="$(grep -E '^[[:space:]]*sonar\.projectKey[[:space:]]*=' "$repo_dir/sonar-project.properties" | tail -n1 | sed 's/^[^=]*=//' | xargs || true)"
  fi

  if [[ -z "$key" && -d "$repo_dir/.git" ]]; then
    local remote=""
    remote="$(git -C "$repo_dir" remote get-url origin 2>/dev/null || true)"
    if [[ "$remote" =~ github.com[:/]+([^/]+)/([^/.]+)(\.git)?$ ]]; then
      key="${BASH_REMATCH[1]}_${BASH_REMATCH[2]}"
    fi
  fi

  if [[ -z "$key" ]]; then
    key="$(basename "$repo_dir")"
  fi

  echo "$key"
}

detect_repos() {
  local repos=()

  if [[ -d "$ROOT_START/.git" || -f "$ROOT_START/package.json" || -f "$ROOT_START/pyproject.toml" || -f "$ROOT_START/requirements.txt" ]]; then
    repos+=("$ROOT_START")
  else
    [[ -d "$ROOT_START/nexus-render-hybrid" ]] && repos+=("$ROOT_START/nexus-render-hybrid")
    [[ -d "$ROOT_START/agentflow-relay" ]] && repos+=("$ROOT_START/agentflow-relay")
  fi

  if [[ "${#repos[@]}" -eq 0 ]]; then
    fail "No repo detected. Run this from a project root or from the parent folder containing nexus-render-hybrid and agentflow-relay."
  fi

  printf '%s\n' "${repos[@]}"
}

has_py_files() {
  find "$1" \
    -path "$1/.git" -prune -o \
    -path "$1/.venv" -prune -o \
    -path "$1/venv" -prune -o \
    -path "$1/node_modules" -prune -o \
    -name '*.py' -print -quit | grep -q .
}

has_node_files() {
  [[ -f "$1/package.json" ]] && return 0
  find "$1" \
    -path "$1/.git" -prune -o \
    -path "$1/node_modules" -prune -o \
    \( -name '*.js' -o -name '*.jsx' -o -name '*.ts' -o -name '*.tsx' \) -print -quit | grep -q .
}

run_python_fixers() {
  local repo_dir="$1"
  local python_cmd="$PYTHON_BIN"

  say "Python detected: running Ruff/compile checks in $(basename "$repo_dir")"
  cd "$repo_dir"

  local ruff_cmd=""
  if [[ -x ".venv/bin/ruff" ]]; then
    ruff_cmd=".venv/bin/ruff"
  elif command -v ruff >/dev/null 2>&1; then
    ruff_cmd="ruff"
  elif "$python_cmd" -m ruff --version >/dev/null 2>&1; then
    ruff_cmd="$python_cmd -m ruff"
  fi

  if [[ -n "$ruff_cmd" ]]; then
    if [[ "$ALLOW_UNSAFE_FIXES" == "1" ]]; then
      eval "$ruff_cmd check . --fix --unsafe-fixes"
    else
      eval "$ruff_cmd check . --fix"
    fi
    eval "$ruff_cmd format ."
  else
    warn "Ruff not installed for this repo. Skipping Python auto-fix. Install free with: python3 -m pip install --user ruff"
  fi

  "$python_cmd" -m compileall -q . || warn "Python compile check found syntax/import-path issues that need manual review."
}

npm_script_exists() {
  local script_name="$1"
  node -e "
const fs=require('fs');
const p=JSON.parse(fs.readFileSync('package.json','utf8'));
process.exit(p.scripts && p.scripts['$script_name'] ? 0 : 1);
" >/dev/null 2>&1
}

run_node_fixers() {
  local repo_dir="$1"

  say "Node/JS/TS detected: running ESLint/Prettier/TypeScript checks in $(basename "$repo_dir")"
  cd "$repo_dir"

  if [[ -f "package.json" ]]; then
    if [[ ! -d "node_modules" && "$AUTO_NPM_INSTALL" == "1" ]]; then
      if [[ -f "package-lock.json" ]]; then
        npm ci
      elif [[ -f "pnpm-lock.yaml" ]] && command -v pnpm >/dev/null 2>&1; then
        pnpm install --frozen-lockfile
      elif [[ -f "yarn.lock" ]] && command -v yarn >/dev/null 2>&1; then
        yarn install --frozen-lockfile
      else
        npm install
      fi
    fi

    if [[ -x "node_modules/.bin/eslint" ]]; then
      ./node_modules/.bin/eslint . --fix || warn "ESLint completed with remaining issues."
    elif command -v npx >/dev/null 2>&1; then
      npx --no-install eslint . --fix || warn "ESLint not installed locally or remaining issues exist."
    fi

    if [[ -x "node_modules/.bin/prettier" ]]; then
      ./node_modules/.bin/prettier . --write || warn "Prettier completed with warnings."
    elif command -v npx >/dev/null 2>&1; then
      npx --no-install prettier . --write || true
    fi

    if [[ -x "node_modules/.bin/tsc" ]]; then
      ./node_modules/.bin/tsc --noEmit || warn "TypeScript check found remaining issues."
    elif npm_script_exists "typecheck"; then
      npm run typecheck || warn "npm typecheck found remaining issues."
    fi

    if npm_script_exists "lint"; then
      npm run lint -- --fix || true
    fi

    if npm_script_exists "test"; then
      npm test -- --watch=false || warn "Tests found remaining issues or use a different test command."
    fi
  else
    warn "JS/TS files found but no package.json exists. Skipping Node fixers."
  fi
}

fetch_sonar_issues_for_repo() {
  local repo_dir="$1"
  local repo_name project_guess project_key log_dir raw_dir final_json param=""
  repo_name="$(basename "$repo_dir")"
  project_guess="$(guess_project_key "$repo_dir")"

  printf "\nSonarCloud project key for %s [%s]: " "$repo_name" "$project_guess"
  read -r project_key
  project_key="${project_key:-$project_guess}"

  [[ -n "$project_key" ]] || fail "Empty Sonar project key for $repo_name"

  log_dir="$repo_dir/$LOG_ROOT_NAME"
  raw_dir="$log_dir/raw"
  final_json="$log_dir/${repo_name}-sonar-open-issues.json"
  mkdir -p "$raw_dir"

  say "Pulling unresolved SonarCloud issues for $repo_name / $project_key"

  for candidate in "projectKeys" "componentKeys" "projects"; do
    if urlencode_fetch_page "$candidate" "$project_key" "1" "$raw_dir/page-1-${candidate}.json"; then
      param="$candidate"
      cp "$raw_dir/page-1-${candidate}.json" "$raw_dir/page-1.json"
      break
    fi
  done

  [[ -n "$param" ]] || {
    warn "Could not fetch Sonar issues for $repo_name. Check SONAR_TOKEN, project key, organization access, and SONAR_HOST_URL."
    return 0
  }

  local total page_size pages p files=()
  total="$(json_get_total "$raw_dir/page-1.json")"
  page_size="$(json_get_page_size "$raw_dir/page-1.json")"
  [[ "$page_size" -lt 1 ]] && page_size=500
  pages=$(( (total + page_size - 1) / page_size ))
  [[ "$pages" -lt 1 ]] && pages=1

  files+=("$raw_dir/page-1.json")

  if [[ "$pages" -gt 1 ]]; then
    for ((p=2; p<=pages; p++)); do
      if urlencode_fetch_page "$param" "$project_key" "$p" "$raw_dir/page-${p}.json"; then
        files+=("$raw_dir/page-${p}.json")
      else
        warn "Failed to fetch page $p for $repo_name; continuing with downloaded pages."
      fi
    done
  fi

  local merged_count
  merged_count="$(json_merge_pages "$final_json" "${files[@]}")"
  say "Saved $merged_count unresolved Sonar issues to: $final_json"

  if [[ -d "$repo_dir/.git" ]]; then
    {
      echo "$LOG_ROOT_NAME/raw/"
      echo "$LOG_ROOT_NAME/*.tmp"
    } >> "$repo_dir/.git/info/exclude" 2>/dev/null || true
  fi
}

commit_optionally() {
  local repo_dir="$1"
  cd "$repo_dir"

  if [[ ! -d ".git" ]]; then
    return 0
  fi

  say "Git diff summary for $(basename "$repo_dir")"
  git status --short || true

  if [[ "$AUTO_PUSH" == "1" ]]; then
    local branch
    branch="$(git branch --show-current 2>/dev/null || echo main)"
    git add -A
    if git diff --cached --quiet; then
      say "No changes to commit for $(basename "$repo_dir")"
    else
      git commit -m "fix: auto-remediate SonarQube issues"
      git push origin "$branch"
      say "Pushed fixes to origin/$branch. Render push-to-deploy should start automatically."
    fi
  else
    say "AUTO_PUSH is off. Review changes, then run: git add -A && git commit -m 'fix: remediate SonarQube issues' && git push"
  fi
}

main() {
  need_cmd curl
  PYTHON_BIN="$(find_python)"

  if [[ -z "${SONAR_TOKEN:-}" ]]; then
    printf "Enter SonarCloud token: "
    stty -echo
    read -r SONAR_TOKEN
    stty echo
    printf "\n"
  fi

  [[ -n "${SONAR_TOKEN:-}" ]] || fail "SONAR_TOKEN cannot be empty."
  export SONAR_TOKEN
  export SONARQUBE_TOKEN="$SONAR_TOKEN"

  if [[ -z "${SONAR_ORG:-}" && -z "${SONARQUBE_ORG:-}" ]]; then
    printf "Enter SonarCloud organization key for MCP use, or press Enter to skip API-only mode: "
    read -r SONAR_ORG || true
  fi

  SONAR_ORG="${SONAR_ORG:-${SONARQUBE_ORG:-}}"
  if [[ -n "$SONAR_ORG" ]]; then
    export SONAR_ORG
    export SONARQUBE_ORG="$SONAR_ORG"
  fi

  mapfile -t REPOS < <(detect_repos)

  say "Detected ${#REPOS[@]} repo root(s)"
  printf '%s\n' "${REPOS[@]}"

  for repo in "${REPOS[@]}"; do
    [[ -d "$repo" ]] || continue

    fetch_sonar_issues_for_repo "$repo"

    if has_py_files "$repo"; then
      run_python_fixers "$repo"
    fi

    if has_node_files "$repo"; then
      run_node_fixers "$repo"
    fi

    commit_optionally "$repo"
  done

  say "Done. Remaining Sonar issues are now logged under each repo's .sonar-auto-remedy folder."
  say "Next: open Windsurf Cascade with SonarQube MCP enabled and paste the Phase 3 prompt."
}

main "$@"
