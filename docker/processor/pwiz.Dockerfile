FROM proteowizard/pwiz-skyline-i-agree-to-the-vendor-licenses:latest AS vendor

FROM msconnect:local

USER root

WORKDIR /app

COPY --from=vendor /opt/wine-staging /opt/wine-staging
COPY --from=vendor /usr/bin/wine /usr/bin/wine
COPY --from=vendor /usr/bin/wineserver /usr/bin/wineserver
COPY --from=vendor /wineprefix64 /wineprefix64

RUN id -u appuser >/dev/null 2>&1 || useradd --create-home --shell /bin/sh appuser \
    && mkdir -p /usr/lib \
    && dpkg --add-architecture i386 \
    && apt-get update \
    && apt-get install -y --no-install-recommends libc6-i386 libstdc++6:i386 zlib1g:i386 \
    && rm -rf /var/lib/apt/lists/* \
    && ln -sfn /opt/wine-staging/lib/wine /usr/lib/wine \
    && printf '#!/bin/sh\nexec wine /wineprefix64/drive_c/pwiz/skyline/msconvert.exe "$@"\n' > /usr/local/bin/msconvert \
    && chmod +x /usr/local/bin/msconvert \
    && mkdir -p /app/data /app/media /app/staticfiles /data/raw /data/results \
    && chown -R appuser:appuser /app /data

USER appuser

CMD ["python", "manage.py", "run_processor_agent"]
