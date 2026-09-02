#!/usr/bin/env bash
set -euo pipefail

# Install a role-specific systemd unit. This deliberately delegates recovery to
# Docker Compose restart policies while systemd owns boot ordering and upgrades.

usage() {
  cat <<'EOF'
Usage: install-msconnect-node.sh --role ROLE --project-dir PATH --env-file PATH

ROLE must be one of: server, watcher, processor, archive
The env file may define MSCONNECT_COMPOSE_SERVICES; otherwise a safe default is used.
Run as root on a Linux host with Docker Compose v2 installed.
EOF
}

role=""
project_dir=""
env_file=""
while [[ $# -gt 0 ]]; do
  case "$1" in
    --role) role="${2:?missing value for --role}"; shift 2 ;;
    --project-dir) project_dir="${2:?missing value for --project-dir}"; shift 2 ;;
    --env-file) env_file="${2:?missing value for --env-file}"; shift 2 ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown argument: $1" >&2; usage >&2; exit 2 ;;
  esac
done

case "$role" in
  server) default_services="web nginx" ;;
  watcher) default_services="watcher" ;;
  processor) default_services="processor" ;;
  archive) default_services="archive-worker" ;;
  *) echo "--role must be server, watcher, processor, or archive" >&2; exit 2 ;;
esac

[[ "$(id -u)" == 0 ]] || { echo "run as root" >&2; exit 1; }
[[ -d "$project_dir" ]] || { echo "project directory does not exist: $project_dir" >&2; exit 1; }
[[ -f "$env_file" ]] || { echo "env file does not exist: $env_file" >&2; exit 1; }
command -v docker >/dev/null || { echo "Docker is required" >&2; exit 1; }
docker compose version >/dev/null || { echo "Docker Compose v2 is required" >&2; exit 1; }

# Read only the optional service list; the env file remains owned by the caller.
compose_services="$(awk -F= '$1 == "MSCONNECT_COMPOSE_SERVICES" {print substr($0, index($0,"=")+1); exit}' "$env_file")"
compose_services="${compose_services:-$default_services}"
[[ "$compose_services" != *";"* && "$compose_services" != *"&&"* ]] || {
  echo "invalid MSCONNECT_COMPOSE_SERVICES" >&2; exit 2;
}

unit="/etc/systemd/system/msconnect-${role}.service"
sed \
  -e "s|%i|$role|g" \
  -e "s|%E/MSCONNECT_PROJECT_DIR|$project_dir|g" \
  -e "s|%E/MSCONNECT_ENV_FILE|$env_file|g" \
  -e "s|%E/MSCONNECT_COMPOSE_SERVICES|$compose_services|g" \
  "$(dirname "$0")/msconnect-node.service" > "$unit"

systemctl daemon-reload
systemctl enable "msconnect-${role}.service"
systemctl restart "msconnect-${role}.service"
echo "Installed and started $unit"
echo "Check: systemctl status msconnect-${role}.service"
