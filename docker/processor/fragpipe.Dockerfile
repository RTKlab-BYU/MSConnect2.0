FROM eclipse-temurin:21-jre AS java

FROM msconnect:local

ARG FRAGPIPE_URL=""

COPY --from=java /opt/java/openjdk /opt/java/openjdk

ENV JAVA_HOME=/opt/java/openjdk
ENV PATH="${JAVA_HOME}/bin:${PATH}"

USER root

RUN if [ -n "$FRAGPIPE_URL" ]; then \
      mkdir -p /opt/fragpipe \
      && python -c "import pathlib, urllib.request, zipfile; target=pathlib.Path('/tmp/fragpipe.zip'); urllib.request.urlretrieve('${FRAGPIPE_URL}', target); zipfile.ZipFile(target).extractall('/opt/fragpipe')" \
      && test -d /opt/fragpipe \
      && find /opt/fragpipe -type f -name "fragpipe" -exec chmod +x {} \; \
      && FRAGPIPE_BIN="$(find /opt/fragpipe -type f -name 'fragpipe' -print -quit)" \
      && test -n "$FRAGPIPE_BIN" \
      && ln -sf "$FRAGPIPE_BIN" /usr/local/bin/fragpipe; \
    else \
      printf '#!/bin/sh\necho "FragPipe is not installed. Build with FRAGPIPE_URL." >&2\nexit 127\n' > /usr/local/bin/fragpipe \
      && chmod +x /usr/local/bin/fragpipe; \
    fi

USER appuser

CMD ["python", "manage.py", "run_processor_agent"]
