#!/usr/bin/env bash
set -euo pipefail

DIANN_IMAGE="${MSCONNECT_DIANN_IMAGE:-msconnect-processor-diann:2.0}"
FRAGPIPE_IMAGE="${MSCONNECT_FRAGPIPE_IMAGE:-msconnect-processor-fragpipe:local}"
PWIZ_IMAGE="${MSCONNECT_PWIZ_IMAGE:-msconnect-processor-pwiz:local}"
SKYLINE_IMAGE="${MSCONNECT_SKYLINE_IMAGE:-msconnect-processor-skyline:26.1}"

for image in "$DIANN_IMAGE" "$FRAGPIPE_IMAGE" "$PWIZ_IMAGE" "$SKYLINE_IMAGE"; do
  docker image inspect "$image" >/dev/null
done

echo "DIA-NN:"
docker run --rm --entrypoint diann "$DIANN_IMAGE" --version 2>&1 | sed -n '1,3p'
echo "ProteoWizard:"
docker run --rm --entrypoint sh "$PWIZ_IMAGE" -c 'command -v msconvert && test -x /usr/local/bin/msconvert'
set +e
docker run --rm --entrypoint msconvert "$PWIZ_IMAGE" --help >/tmp/msconnect-msconvert-help.out 2>&1
pwiz_status=$?
set -e
if [ "$pwiz_status" -ne 0 ] && [ "$pwiz_status" -ne 1 ]; then
  cat /tmp/msconnect-msconvert-help.out
  exit "$pwiz_status"
fi
sed -n '1,2p' /tmp/msconnect-msconvert-help.out
echo "SkylineCmd wrapper:"
docker run --rm --entrypoint sh "$SKYLINE_IMAGE" -c 'command -v SkylineCmd && test -x /usr/local/bin/SkylineCmd'
echo "FragPipe:"
docker run --rm --entrypoint sh "$FRAGPIPE_IMAGE" -c 'command -v fragpipe && test -x "$(command -v fragpipe)"'
set +e
docker run --rm --entrypoint fragpipe "$FRAGPIPE_IMAGE" --help >/tmp/msconnect-fragpipe-help.out 2>&1
fragpipe_status=$?
set -e
if [ "$fragpipe_status" -ne 0 ] && [ "$fragpipe_status" -ne 1 ]; then
  cat /tmp/msconnect-fragpipe-help.out
  exit "$fragpipe_status"
fi
sed -n '1,4p' /tmp/msconnect-fragpipe-help.out

echo "Image digests:"
docker image inspect "$DIANN_IMAGE" "$FRAGPIPE_IMAGE" "$PWIZ_IMAGE" "$SKYLINE_IMAGE" \
  --format '{{index .RepoTags 0}} {{.Id}}'
