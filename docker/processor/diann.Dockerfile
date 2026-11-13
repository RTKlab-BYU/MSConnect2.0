# DIA-NN worker: independent of the web/frontend and vendor conversion images.
ARG DIANN_SOURCE_IMAGE=download
ARG DOTNET_SDK_IMAGE=mcr.microsoft.com/dotnet/sdk:8.0-bookworm-slim
FROM ${DOTNET_SDK_IMAGE} AS dotnet
FROM python:3.12-slim-bookworm AS download
ARG DIANN_LINUX_URL=""
RUN mkdir -p /opt/diann && if [ -n "$DIANN_LINUX_URL" ]; then \
    python -c "import urllib.request,zipfile; urllib.request.urlretrieve('${DIANN_LINUX_URL}', '/tmp/diann.zip'); zipfile.ZipFile('/tmp/diann.zip').extractall('/opt/diann')" \
    && rm /tmp/diann.zip; fi
# Optional reuse of an approved engine image; only /opt/diann is copied.
FROM ${DIANN_SOURCE_IMAGE} AS engine
FROM python:3.12-slim-bookworm
ARG DIANN_LINUX_URL=""
ARG DIANN_VERSION="2.0"
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 \
    DOTNET_ROOT=/usr/share/dotnet DOTNET_SYSTEM_GLOBALIZATION_INVARIANT=1
ENV PATH="${PATH}:/usr/share/dotnet"
COPY --from=dotnet /usr/share/dotnet /usr/share/dotnet
RUN sed -i 's|http://deb.debian.org|https://deb.debian.org|g' /etc/apt/sources.list.d/debian.sources \
    && apt-get update && apt-get install -y --no-install-recommends libgomp1 libunwind8 libicu72 libssl3 zlib1g ca-certificates \
    && rm -rf /var/lib/apt/lists/* \
    && adduser --disabled-password --gecos "" appuser
WORKDIR /app
COPY requirements.txt ./
RUN pip install --no-cache-dir --timeout 120 --retries 5 -r requirements.txt
COPY --from=engine /opt/diann /opt/diann
RUN test -d /opt/diann \
    && find /opt/diann -type f -name 'diann*' -exec chmod +x {} \; \
    && DIANN_BIN="$(find /opt/diann -type f -name 'diann-linux' | head -n 1)" \
    && test -n "$DIANN_BIN" \
    && printf '#!/bin/sh\nexport LD_LIBRARY_PATH="%s:${LD_LIBRARY_PATH:-}"\nexec "%s" "$@"\n' "$(dirname "$DIANN_BIN")" "$DIANN_BIN" > /usr/local/bin/diann \
    && chmod +x /usr/local/bin/diann \
    && diann
COPY . /app/
RUN mkdir -p /app/data /data/raw /data/results /data/shared \
    && chown -R appuser:appuser /app /data
ENV MSCONNECT_PROCESSOR_ENGINE=diann
USER appuser
CMD ["python", "manage.py", "run_processor_agent", "--engine", "diann"]
