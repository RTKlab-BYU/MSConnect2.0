#!/usr/bin/env bash
set -euo pipefail

# Build the processor images used by a production node.  DIA-NN and FragPipe
# must be supplied as approved, checksummed site artifacts; an empty URL is
# intentionally rejected instead of producing a placeholder worker.
: "${DIANN_LINUX_URL:?Set DIANN_LINUX_URL to the approved DIA-NN Linux archive URL}"
: "${FRAGPIPE_URL:?Set FRAGPIPE_URL to the approved FragPipe archive URL}"

DIANN_ENGINE_VERSION="${DIANN_ENGINE_VERSION:-2.0}"
DIANN_ENGINE_PROFILE="${DIANN_ENGINE_PROFILE:-diann:${DIANN_ENGINE_VERSION}}"
FRAGPIPE_ENGINE_VERSION="${FRAGPIPE_ENGINE_VERSION:-site-pinned}"
FRAGPIPE_ENGINE_PROFILE="${FRAGPIPE_ENGINE_PROFILE:-fragpipe:${FRAGPIPE_ENGINE_VERSION}}"
PWIZ_BASE_IMAGE="${PWIZ_BASE_IMAGE:-proteowizard/pwiz-skyline-i-agree-to-the-vendor-licenses:latest}"
SKYLINE_BASE_IMAGE="${SKYLINE_BASE_IMAGE:-proteowizard/pwiz-skyline-i-agree-to-the-vendor-licenses:skyline_26.1.0.057-c07debd}"

export DIANN_ENGINE_VERSION DIANN_ENGINE_PROFILE FRAGPIPE_ENGINE_VERSION FRAGPIPE_ENGINE_PROFILE
export DIANN_LINUX_URL FRAGPIPE_URL PWIZ_BASE_IMAGE SKYLINE_BASE_IMAGE

docker compose --profile engines --profile conversion build \
  processor-diann processor-fragpipe processor-pwiz processor-skyline

echo "Processor images built. Run the following checks before publishing:"
echo "  docker compose --profile engines --profile conversion config"
echo "  docker compose --profile engines --profile conversion up -d processor-diann processor-fragpipe processor-pwiz processor-skyline"
echo "Publish only immutable tags/digests after the node health checks report ready."
