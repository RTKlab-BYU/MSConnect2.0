#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'EOF' >&2
Usage: apply-msconnect-release.sh RELEASE_VERSION IMAGE [DIGEST]

Environment:
  MSCONNECT_PROJECT_DIR       deployment checkout (default: script parent)
  MSCONNECT_ENV_FILE          dotenv file (default: PROJECT_DIR/.env)
  MSCONNECT_COMPOSE_PROJECT   Compose project name (default: env value or directory name)
  MSCONNECT_COMPOSE_SERVICES  space-separated services (default: web nginx)
EOF
  exit 2
}

[[ $# -ge 2 && $# -le 3 ]] || usage
release_version="$1"
image="$2"
digest="${3:-}"

[[ "$release_version" =~ ^[A-Za-z0-9._-]+$ ]] || { echo "invalid release version" >&2; exit 2; }
if printf '%s' "$image" | grep -q '[[:space:];|&]'; then
  echo "invalid image reference" >&2
  exit 2
fi
if [[ -n "$digest" && ! "$digest" =~ ^sha256:[0-9a-fA-F]{64}$ ]]; then
  echo "digest must be sha256:<64 hex characters>" >&2
  exit 2
fi

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
project_dir="${MSCONNECT_PROJECT_DIR:-$(cd "$script_dir/.." && pwd -P)}"
env_file="${MSCONNECT_ENV_FILE:-$project_dir/.env}"
[[ -d "$project_dir" ]] || { echo "project directory does not exist: $project_dir" >&2; exit 1; }
[[ -f "$env_file" ]] || { echo "env file does not exist: $env_file" >&2; exit 1; }
command -v docker >/dev/null || { echo "Docker is required" >&2; exit 1; }
docker compose version >/dev/null || { echo "Docker Compose v2 is required" >&2; exit 1; }

dotenv_value() {
  local wanted="$1"
  awk -v wanted="$wanted" '
    /^[[:space:]]*(export[[:space:]]+)?[A-Za-z_][A-Za-z0-9_]*[[:space:]]*=/ {
      line = $0
      sub(/^[[:space:]]*/, "", line)
      sub(/^export[[:space:]]+/, "", line)
      key = line
      sub(/[[:space:]]*=.*$/, "", key)
      gsub(/[[:space:]]/, "", key)
      if (key != wanted) next
      value = substr(line, index(line, "=") + 1)
      sub(/^[[:space:]]*/, "", value)
      sub(/[[:space:]]*$/, "", value)
      if (value ~ /^".*"$/ || value ~ /^'"'"'.*'"'"'$/) value = substr(value, 2, length(value) - 2)
      print value
      exit
    }
  ' "$env_file"
}

project_name="${MSCONNECT_COMPOSE_PROJECT:-$(dotenv_value COMPOSE_PROJECT_NAME)}"
project_name="${project_name:-$(basename "$project_dir")}"
[[ "$project_name" =~ ^[a-z0-9][a-z0-9_-]*$ ]] || { echo "invalid Compose project name" >&2; exit 2; }

services_text="${MSCONNECT_COMPOSE_SERVICES:-$(dotenv_value MSCONNECT_COMPOSE_SERVICES)}"
services_text="${services_text:-web nginx}"
read -r -a services <<< "$services_text"
[[ "${#services[@]}" -gt 0 ]] || { echo "at least one Compose service is required" >&2; exit 2; }
for service in "${services[@]}"; do
  [[ "$service" =~ ^[a-z0-9][a-z0-9_-]*$ ]] || { echo "invalid Compose service: $service" >&2; exit 2; }
done

production="$(dotenv_value MSCONNECT_PRODUCTION)"
compose_files=(-f docker-compose.msconnect2.server.yml)
if [[ "$production" == "1" || "$production" == "true" || "$production" == "yes" ]]; then
  [[ -x "$project_dir/scripts/check-production-env.sh" ]] || {
    echo "production preflight script is missing or not executable" >&2
    exit 1
  }
  "$project_dir/scripts/check-production-env.sh" "$env_file"
  compose_files+=(-f docker-compose.production.yml)
fi

image_ref="$image"
if [[ -n "$digest" && "$image_ref" != *@* ]]; then
  image_ref="${image_ref}@${digest}"
fi
previous_image="$(dotenv_value MSCONNECT_IMAGE)"
[[ -n "$previous_image" ]] || { echo "MSCONNECT_IMAGE is missing from env file" >&2; exit 1; }

backup_env="${env_file}.upgrade-backup.$$"
temporary_env="${env_file}.upgrade-tmp.$$"
cp -p -- "$env_file" "$backup_env"
cleanup() {
  rm -f -- "$temporary_env" "$backup_env"
}
rollback() {
  if [[ "${rollout_complete:-0}" != "1" ]]; then
    echo "Release rollout failed; restoring previous deployment configuration" >&2
    if [[ -f "$backup_env" ]]; then
      cp -p -- "$backup_env" "$env_file"
      (cd "$project_dir" && env MSCONNECT_IMAGE="$previous_image" docker compose --env-file "$env_file" -p "$project_name" \
        "${compose_files[@]}" up -d --no-build --remove-orphans "${services[@]}" >/dev/null 2>&1) || true
    fi
  fi
  cleanup
}
trap rollback EXIT

# Change only MSCONNECT_IMAGE and preserve the operator's comments and secrets.
awk -v replacement="$image_ref" '
  BEGIN { replaced = 0 }
  /^[[:space:]]*(export[[:space:]]+)?MSCONNECT_IMAGE[[:space:]]*=/ {
    print "MSCONNECT_IMAGE=" replacement
    replaced = 1
    next
  }
  { print }
  END { if (!replaced) print "MSCONNECT_IMAGE=" replacement }
' "$env_file" > "$temporary_env"
chmod --reference="$env_file" "$temporary_env" 2>/dev/null || true
mv -- "$temporary_env" "$env_file"

compose() {
  (cd "$project_dir" && env MSCONNECT_IMAGE="$image_ref" docker compose --env-file "$env_file" -p "$project_name" \
    "${compose_files[@]}" "$@")
}

echo "Pulling release ${release_version} (${image_ref})"
compose pull "${services[@]}"

if printf '%s\n' "${services[@]}" | grep -qx web; then
  if [[ "$production" == "1" || "$production" == "true" || "$production" == "yes" ]]; then
    compose up -d postgres
  fi
  compose run --rm --no-deps web python manage.py migrate --noinput
fi

compose up -d --no-build --remove-orphans "${services[@]}"

if printf '%s\n' "${services[@]}" | grep -qx web; then
  ready=0
  for _ in $(seq 1 60); do
    if compose exec -T web python -c "from urllib.request import urlopen; urlopen('http://127.0.0.1:8000/readyz/', timeout=5)" >/dev/null 2>&1; then
      ready=1
      break
    fi
    sleep 2
  done
  [[ "$ready" == "1" ]] || { echo "new web release did not become ready" >&2; exit 1; }
fi

rollout_complete=1
echo "Release ${release_version} applied successfully"
