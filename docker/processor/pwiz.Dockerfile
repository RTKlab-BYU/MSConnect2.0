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
    && apt-get install -y --no-install-recommends libc6-i386 libstdc++6:i386 zlib1g:i386 libfreetype6 libfreetype6:i386 libgnutls30 libgnutls30:i386 libfontconfig1 libfontconfig1:i386 xvfb \
    && rm -rf /var/lib/apt/lists/* \
    && ln -sfn /opt/wine-staging/lib/wine /usr/lib/wine \
    && printf '#!/bin/sh\nexport WINEPREFIX=/wineprefix64\nexport WINEDEBUG=-all\nexec xvfb-run -a -s "-screen 0 1280x1024x24" wine /wineprefix64/drive_c/pwiz/skyline/msconvert.exe "$@"\n' > /usr/local/bin/msconvert \
    && chmod +x /usr/local/bin/msconvert \
    && mkdir -p /app/data /app/media /app/staticfiles /data/raw /data/results \
    && chown -R appuser:appuser /app /data

USER appuser

CMD ["python", "manage.py", "run_processor_agent"]
