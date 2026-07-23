FROM msconnect:local

ARG DIANN_LINUX_URL=""

USER root

RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates curl unzip \
    && rm -rf /var/lib/apt/lists/* \
    && if [ -n "$DIANN_LINUX_URL" ]; then \
      curl -fsSL "$DIANN_LINUX_URL" -o /tmp/diann.zip \
      && mkdir -p /opt/diann \
      && unzip /tmp/diann.zip -d /opt/diann \
      && find /opt/diann -type f -name "diann*" -exec chmod +x {} \; \
      && ln -sf "$(find /opt/diann -type f -name 'diann*' | head -n 1)" /usr/local/bin/diann; \
    else \
      printf '#!/bin/sh\necho "DIA-NN binary not installed. Build with DIANN_LINUX_URL." >&2\nexit 127\n' > /usr/local/bin/diann \
      && chmod +x /usr/local/bin/diann; \
    fi

USER appuser

CMD ["python", "manage.py", "run_processor_agent"]
