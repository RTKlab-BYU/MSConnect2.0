FROM msconnect:local

USER root

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        ca-certificates \
        curl \
        unzip \
        openjdk-17-jre-headless \
    && rm -rf /var/lib/apt/lists/*

USER appuser

CMD ["python", "manage.py", "run_processor_agent"]
