#!/usr/bin/env bash
set -euo pipefail

usage() {
  echo "Usage: $0 --project-dir PATH --env-file PATH --output PATH [--project-name NAME]" >&2
  exit 2
}

project_dir=""
env_file=""
output=""
project_name=""
while [[ $# -gt 0 ]]; do
  case "$1" in
    --project-dir) project_dir="${2:?missing value for --project-dir}"; shift 2 ;;
    --env-file) env_file="${2:?missing value for --env-file}"; shift 2 ;;
    --output) output="${2:?missing value for --output}"; shift 2 ;;
    --project-name) project_name="${2:?missing value for --project-name}"; shift 2 ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown argument: $1" >&2; usage ;;
  esac
done

[[ -n "$project_dir" && -d "$project_dir" ]] || { echo "--project-dir must name an existing directory" >&2; exit 1; }
[[ -n "$env_file" && -f "$env_file" ]] || { echo "--env-file must name an existing file" >&2; exit 1; }
[[ -n "$output" && "$output" == /* ]] || { echo "--output must be an absolute host path" >&2; exit 1; }
command -v docker >/dev/null || { echo "Docker is required" >&2; exit 1; }
docker compose version >/dev/null || { echo "Docker Compose v2 is required" >&2; exit 1; }

dotenv_value() {
  local key="$1"
  awk -F= -v key="$key" '$1 == key {print substr($0, index($0,"=")+1); exit}' "$env_file"
}

db_name="$(dotenv_value DJANGO_DB_NAME)"
db_user="$(dotenv_value DJANGO_DB_USER)"
project_name="${project_name:-$(dotenv_value COMPOSE_PROJECT_NAME)}"
db_name="${db_name:-msconnect}"
db_user="${db_user:-msconnect}"
project_name="${project_name:-$(basename "$project_dir")}"
mkdir -p "$(dirname "$output")"
temporary_output="${output}.tmp.$$"
cleanup() { rm -f -- "$temporary_output"; }
trap cleanup EXIT
umask 077

(
  cd "$project_dir"
  docker compose --env-file "$env_file" -p "$project_name" \
    -f docker-compose.msconnect2.server.yml \
    -f docker-compose.production.yml \
    exec -T postgres pg_dump --format=custom --no-owner --no-acl -U "$db_user" -d "$db_name" > "$temporary_output"
)

[[ -s "$temporary_output" ]] || { echo "pg_dump produced an empty backup" >&2; exit 1; }
mv -- "$temporary_output" "$output"
trap - EXIT
echo "Postgres backup written: $output ($(wc -c < "$output") bytes)"
