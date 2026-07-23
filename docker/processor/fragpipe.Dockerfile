FROM msconnect:local

ARG FRAGPIPE_URL=""

USER root

RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates curl unzip openjdk-17-jre-headless \
    && rm -rf /var/lib/apt/lists/* \
    && if [ -n "$FRAGPIPE_URL" ]; then \
      curl -fsSL "$FRAGPIPE_URL" -o /tmp/fragpipe.zip \
      && mkdir -p /opt/fragpipe \
      && unzip /tmp/fragpipe.zip -d /opt/fragpipe \
      && find /opt/fragpipe -type f -name "fragpipe" -exec chmod +x {} \; \
      && ln -sf "$(find /opt/fragpipe -type f -name 'fragpipe' | head -n 1)" /usr/local/bin/fragpipe; \
    else \
      printf '#!/bin/sh\necho "FragPipe is not installed. Build with FRAGPIPE_URL." >&2\nexit 127\n' > /usr/local/bin/fragpipe \
      && chmod +x /usr/local/bin/fragpipe; \
    fi

USER appuser

CMD ["python", "manage.py", "run_processor_agent"]
