ARG DOTNET_SDK_IMAGE=mcr.microsoft.com/dotnet/sdk:8.0-bookworm-slim
FROM ${DOTNET_SDK_IMAGE} AS dotnet

FROM msconnect:local

ARG DIANN_LINUX_URL=""
ARG DIANN_VERSION="2.0"

ENV DOTNET_ROOT=/usr/share/dotnet
ENV DOTNET_SYSTEM_GLOBALIZATION_INVARIANT=1
ENV PATH="${PATH}:/usr/share/dotnet"

COPY --from=dotnet /usr/share/dotnet /usr/share/dotnet

USER root

RUN apt-get update \
    && apt-get install -y --no-install-recommends libgomp1 \
    && rm -rf /var/lib/apt/lists/* \
    && ln -sf /usr/share/dotnet/dotnet /usr/local/bin/dotnet \
    && if [ -n "$DIANN_LINUX_URL" ]; then \
      mkdir -p /opt/diann \
      && python -c "import pathlib, urllib.request, zipfile; url='${DIANN_LINUX_URL}'; target=pathlib.Path('/tmp/diann.zip'); urllib.request.urlretrieve(url, target); zipfile.ZipFile(target).extractall('/opt/diann')" \
      && find /opt/diann -type f -name "diann*" -exec chmod +x {} \; \
      && DIANN_BIN="$(find /opt/diann -type f -name 'diann*' ! -name '*.dll' ! -name '*.json' | sort | head -n 1)" \
      && test -n "$DIANN_BIN" \
      && ln -sf "$DIANN_BIN" /usr/local/bin/diann \
      && diann; \
    else \
      printf '#!/bin/sh\necho "DIA-NN %s binary not installed. Build with DIANN_LINUX_URL pointing at the approved Linux DIA-NN ZIP." >&2\nexit 127\n' "$DIANN_VERSION" > /usr/local/bin/diann \
      && chmod +x /usr/local/bin/diann; \
    fi

USER appuser

CMD ["python", "manage.py", "run_processor_agent"]
