#!/usr/bin/env bash
set -euo pipefail

usage() {
  echo "Usage: $0 [env-file]" >&2
  exit 2
}

env_file="${1:-.env}"
[[ "${env_file}" != -* ]] || usage
if [[ ! -f "${env_file}" ]]; then
  echo "Production env file not found: ${env_file}" >&2
  exit 1
fi

# Read simple Compose dotenv assignments without sourcing the file. A
# deployment env file is operator-controlled input and must not be able to
# execute command substitutions or other shell code during preflight.
dotenv_value() {
  local wanted="$1"
  awk -v wanted="${wanted}" '
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
      if (value ~ /^".*"$/ || value ~ /^'"'"'.*'"'"'$/) {
        value = substr(value, 2, length(value) - 2)
      }
      print value
      exit
    }
  ' "${env_file}"
}

required=(
  DJANGO_SECRET_KEY
  DJANGO_ALLOWED_HOSTS
  DJANGO_CSRF_TRUSTED_ORIGINS
  DJANGO_DB_ENGINE
  DJANGO_DB_PASSWORD
  MSCONNECT_PRODUCTION
  POSTGRES_DATA_HOST_PATH
  MSCONNECT_WATCHER_TOKEN
  MSCONNECT_PROCESSOR_TOKEN
  MSCONNECT_IMAGE
  MSCONNECT_DATA_HOST_PATH
  MSCONNECT_MEDIA_HOST_PATH
  MSCONNECT_STATIC_HOST_PATH
  INCOMING_RAW_HOST_PATH
  RAW_STORAGE_HOST_PATH
  RESULTS_HOST_PATH
  PROCESSOR_SHARED_HOST_PATH
  ARCHIVE_HOST_PATH
  BACKUP_HOST_PATH
)

for name in "${required[@]}"; do
  value="$(dotenv_value "${name}")"
  if [[ -z "${value}" ]]; then
    echo "Missing required production variable: ${name}" >&2
    exit 1
  fi
done

msconnect_image="$(dotenv_value MSCONNECT_IMAGE)"
if [[ "${msconnect_image}" == *":local" || "${msconnect_image}" == "msconnect:site" ]]; then
  echo "MSCONNECT_IMAGE must reference an approved release image, not a local/default tag" >&2
  exit 1
fi

for name in DJANGO_SECRET_KEY DJANGO_DB_PASSWORD MSCONNECT_WATCHER_TOKEN MSCONNECT_PROCESSOR_TOKEN; do
  value="$(dotenv_value "${name}")"
  case "${value}" in
    change-me|watcher-token|processor-token|replace-me|replace-with-*|*-local-only)
      echo "${name} still contains a development placeholder" >&2
      exit 1
      ;;
  esac
done

django_debug="$(dotenv_value DJANGO_DEBUG)"
if [[ "${django_debug}" != "0" ]]; then
  echo "DJANGO_DEBUG must be 0 for production" >&2
  exit 1
fi
django_db_engine="$(dotenv_value DJANGO_DB_ENGINE)"
if [[ "${django_db_engine}" != "django.db.backends.postgresql" ]]; then
  echo "DJANGO_DB_ENGINE must be django.db.backends.postgresql for production" >&2
  exit 1
fi
msconnect_production="$(dotenv_value MSCONNECT_PRODUCTION)"
if [[ "${msconnect_production}" != "1" ]]; then
  echo "MSCONNECT_PRODUCTION must be 1 for production" >&2
  exit 1
fi

for name in POSTGRES_DATA_HOST_PATH MSCONNECT_DATA_HOST_PATH MSCONNECT_MEDIA_HOST_PATH MSCONNECT_STATIC_HOST_PATH INCOMING_RAW_HOST_PATH RAW_STORAGE_HOST_PATH RESULTS_HOST_PATH PROCESSOR_SHARED_HOST_PATH ARCHIVE_HOST_PATH BACKUP_HOST_PATH; do
  value="$(dotenv_value "${name}")"
  if [[ "${value}" != /* ]]; then
    echo "${name} must be an absolute durable host path" >&2
    exit 1
  fi
done

echo "Production environment preflight passed (${env_file})."
