#!/usr/bin/env bash
set -euo pipefail

project_dir="${1:-/opt/msconnect2}"
env_file="${2:-$project_dir/.env}"
[[ "$(id -u)" == 0 ]] || { echo "run as root" >&2; exit 1; }
[[ -d "$project_dir" && -f "$env_file" ]] || { echo "project directory and env file are required" >&2; exit 1; }
command -v docker >/dev/null || { echo "Docker is required" >&2; exit 1; }
docker compose version >/dev/null || { echo "Docker Compose v2 is required" >&2; exit 1; }

for template in msconnect-alerts.service msconnect-alerts.timer; do
  sed -e "s|%E/MSCONNECT_PROJECT_DIR|$project_dir|g" -e "s|%E/MSCONNECT_ENV_FILE|$env_file|g" \
    "$(dirname "$0")/$template" > "/etc/systemd/system/$template"
done
systemctl daemon-reload
systemctl enable --now msconnect-alerts.timer
echo "Installed MSConnect alert timer (every 5 minutes)."
