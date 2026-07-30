ARG SKYLINE_BASE_IMAGE=proteowizard/pwiz-skyline-i-agree-to-the-vendor-licenses:skyline_26.1.0.057-c07debd
FROM python:3.12-slim-bullseye AS python-runtime

WORKDIR /app
COPY requirements.txt /app/
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r requirements.txt

FROM ${SKYLINE_BASE_IMAGE}

USER root

WORKDIR /app

COPY --from=python-runtime /usr/local /usr/local

COPY . /app/

RUN id -u appuser >/dev/null 2>&1 || useradd --create-home --shell /bin/sh appuser \
    && printf '#!/bin/sh\nexec wine /wineprefix64/drive_c/pwiz/skyline/SkylineCmd.exe "$@"\n' > /usr/local/bin/SkylineCmd \
    && chmod +x /usr/local/bin/SkylineCmd \
    && mkdir -p /app/data /app/media /app/staticfiles /data/raw /data/results /data/shared \
    && chown -R appuser:appuser /app /data /wineprefix64

USER appuser

CMD ["python3", "manage.py", "run_processor_agent", "--engine", "skyline"]
