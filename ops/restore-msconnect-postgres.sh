#!/usr/bin/env bash
set -euo pipefail

usage() {
  echo "Usage: $0 --project-dir PATH --env-file PATH --input PATH --target-database NAME [--project-name NAME]" >&2
  exit 2
}

project_dir=""
env_file=""
input=""
target_database=""
project_name=""
while [[ $# -gt 0 ]]; do
  case "$1" in
    --project-dir) project_dir="${2:?missing value for --project-dir}"; shift 2 ;;
    --env-file) env_file="${2:?missing value for --env-file}"; shift 2 ;;
    --input) input="${2:?missing value for --input}"; shift 2 ;;
    --target-database) target_database="${2:?missing value for --target-database}"; shift 2 ;;
    --project-name) project_name="${2:?missing value for --project-name}"; shift 2 ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown argument: $1" >&2; usage ;;
  esac
done

[[ -n "$project_dir" && -d "$project_dir" ]] || { echo "--project-dir must name an existing directory" >&2; exit 1; }
[[ -n "$env_file" && -f "$env_file" ]] || { echo "--env-file must name an existing file" >&2; exit 1; }
[[ -n "$input" && -f "$input" && -s "$input" ]] || { echo "--input must name a non-empty backup file" >&2; exit 1; }
[[ "$target_database" =~ ^[A-Za-z_][A-Za-z0-9_]*$ ]] || {
  echo "--target-database must be a simple PostgreSQL identifier" >&2
  exit 1
}
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
[[ "$target_database" != "$db_name" ]] || {
  echo "Refusing to restore over the configured live database; choose a new target database" >&2
  exit 1
}

compose() {
  (cd "$project_dir" && docker compose --env-file "$env_file" -p "$project_name" \
    -f docker-compose.msconnect2.server.yml \
    -f docker-compose.production.yml "$@")
}

container_dump="/tmp/msconnect-restore-$$.dump"
cleanup() { compose exec -T postgres rm -f "$container_dump" >/dev/null 2>&1 || true; }
trap cleanup EXIT

compose exec -T postgres sh -c "cat > '$container_dump'" < "$input"
compose exec -T postgres createdb -U "$db_user" "$target_database"
compose exec -T postgres pg_restore --exit-on-error --no-owner --no-acl -U "$db_user" -d "$target_database" "$container_dump"
echo "Postgres restore completed into new database: $target_database"
