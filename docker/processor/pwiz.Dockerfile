FROM proteowizard/pwiz-skyline-i-agree-to-the-vendor-licenses:latest AS vendor

FROM msconnect:local

USER root

WORKDIR /app

COPY --from=vendor /opt/wine-staging /opt/wine-staging
COPY --from=vendor /usr/bin/wine /usr/bin/wine
COPY --from=vendor /usr/bin/wineserver /usr/bin/wineserver
COPY --from=vendor /usr/bin/Xvfb /usr/bin/Xvfb
COPY --from=vendor /usr/bin/xvfb-run /usr/bin/xvfb-run
COPY --from=vendor /usr/bin/xauth /usr/bin/xauth
COPY --from=vendor /wineprefix64 /wineprefix64

RUN id -u appuser >/dev/null 2>&1 || useradd --create-home --shell /bin/sh appuser \
    && mkdir -p /usr/lib \
    && dpkg --add-architecture i386 \
    && sed -i 's|http://deb.debian.org|https://deb.debian.org|g' /etc/apt/sources.list.d/debian.sources \
    && apt-get -o Acquire::By-Hash=force update \
    && (apt-get -o Acquire::By-Hash=force install -y --no-install-recommends libc6-i386 libstdc++6:i386 zlib1g:i386 libfreetype6 libfreetype6:i386 libgnutls30 libgnutls30:i386 libfontconfig1 libfontconfig1:i386 libx11-6 libxau6 libxdmcp6 libxcb1 libxext6 libxfont2 libpixman-1-0 libfontenc1 libxmu6 libgcrypt20 libunwind8 libgl1 || (rm -rf /var/lib/apt/lists/* && apt-get -o Acquire::By-Hash=force update && apt-get -o Acquire::By-Hash=force install -y --no-install-recommends libc6-i386 libstdc++6:i386 zlib1g:i386 libfreetype6 libfreetype6:i386 libgnutls30 libgnutls30:i386 libfontconfig1 libfontconfig1:i386 libx11-6 libxau6 libxdmcp6 libxcb1 libxext6 libxfont2 libpixman-1-0 libfontenc1 libxmu6 libgcrypt20 libunwind8 libgl1)) \
    && apt-get -o Acquire::By-Hash=force install -y --no-install-recommends libxmuu1 \
    && rm -rf /var/lib/apt/lists/* \
    && ln -sfn /opt/wine-staging/lib/wine /usr/lib/wine \
    && printf '#!/bin/sh\nexport WINEPREFIX=/wineprefix64\nexport WINEDEBUG=-all\nxvfb-run -a -s "-screen 0 1280x1024x24" wine /wineprefix64/drive_c/pwiz/skyline/msconvert.exe "$@"\nrc=$?\n[ "$rc" -eq 1 ] && exit 0\nexit "$rc"\n' > /usr/local/bin/msconvert \
    && chmod +x /usr/local/bin/msconvert \
    && mkdir -p /app/data /app/media /app/staticfiles /data/raw /data/results \
    && chown -R appuser:appuser /app /data /wineprefix64

USER appuser

CMD ["python", "manage.py", "run_processor_agent"]
