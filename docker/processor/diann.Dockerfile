ARG PWIZ_BASE_IMAGE=proteowizard/pwiz-skyline-i-agree-to-the-vendor-licenses:latest
ARG DOTNET_SDK_IMAGE=mcr.microsoft.com/dotnet/sdk:8.0-bookworm-slim

FROM ${DOTNET_SDK_IMAGE} AS dotnet

FROM ${PWIZ_BASE_IMAGE} AS pwiz

FROM msconnect:local

ARG DIANN_LINUX_URL=""
ARG DIANN_VERSION="2.0"

ENV DOTNET_ROOT=/usr/share/dotnet
ENV DOTNET_SYSTEM_GLOBALIZATION_INVARIANT=1
ENV PATH="${PATH}:/usr/share/dotnet"

COPY --from=dotnet /usr/share/dotnet /usr/share/dotnet
COPY --from=pwiz /opt/wine-staging /opt/wine-staging
COPY --from=pwiz /usr/bin/wine /usr/bin/wine
COPY --from=pwiz /usr/bin/wineserver /usr/bin/wineserver
COPY --from=pwiz /usr/bin/Xvfb /usr/bin/Xvfb
COPY --from=pwiz /usr/bin/xvfb-run /usr/bin/xvfb-run
COPY --from=pwiz /usr/bin/xauth /usr/bin/xauth
COPY --from=pwiz /wineprefix64 /wineprefix64

USER root

RUN apt-get update \
    && dpkg --add-architecture i386 \
    && sed -i 's|http://deb.debian.org|https://deb.debian.org|g' /etc/apt/sources.list.d/debian.sources \
    && apt-get -o Acquire::By-Hash=force update \
    && (apt-get -o Acquire::By-Hash=force install -y --no-install-recommends libgomp1 libc6-i386 libstdc++6:i386 zlib1g:i386 libfreetype6 libfreetype6:i386 libgnutls30 libgnutls30:i386 libfontconfig1 libfontconfig1:i386 libx11-6 libxau6 libxdmcp6 libxcb1 libxext6 libxfont2 libpixman-1-0 libfontenc1 libxmu6 libgcrypt20 libunwind8 libgl1 || (rm -rf /var/lib/apt/lists/* && apt-get -o Acquire::By-Hash=force update && apt-get -o Acquire::By-Hash=force install -y --no-install-recommends libgomp1 libc6-i386 libstdc++6:i386 zlib1g:i386 libfreetype6 libfreetype6:i386 libgnutls30 libgnutls30:i386 libfontconfig1 libfontconfig1:i386 libx11-6 libxau6 libxdmcp6 libxcb1 libxext6 libxfont2 libpixman-1-0 libfontenc1 libxmu6 libgcrypt20 libunwind8 libgl1)) \
    && apt-get -o Acquire::By-Hash=force install -y --no-install-recommends libxmuu1 \
    && rm -rf /var/lib/apt/lists/* \
    && ln -sf /usr/share/dotnet/dotnet /usr/local/bin/dotnet \
    && ln -sfn /opt/wine-staging/lib/wine /usr/lib/wine \
    && printf '#!/bin/sh\nexport WINEPREFIX=/wineprefix64\nexport WINEDEBUG=-all\nexec xvfb-run -a -s "-screen 0 1280x1024x24" wine /wineprefix64/drive_c/pwiz/skyline/msconvert.exe "$@"\n' > /usr/local/bin/msconvert \
    && chmod +x /usr/local/bin/msconvert \
    && if [ -n "$DIANN_LINUX_URL" ]; then \
      mkdir -p /opt/diann \
      && python -c "import pathlib, urllib.request, zipfile, tarfile; url='${DIANN_LINUX_URL}'; target=pathlib.Path('/tmp/diann.download'); urllib.request.urlretrieve(url, target); (zipfile.ZipFile(target).extractall('/opt/diann') if zipfile.is_zipfile(target) else tarfile.open(target).extractall('/opt/diann'))" \
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
