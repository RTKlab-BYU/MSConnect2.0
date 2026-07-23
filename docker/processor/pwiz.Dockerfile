FROM proteowizard/pwiz-skyline-i-agree-to-the-vendor-licenses:latest

USER root

RUN apt-get update \
    && apt-get install -y --no-install-recommends python3 python3-pip python3-venv \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt /app/
RUN python3 -m pip install --break-system-packages --no-cache-dir -r requirements.txt

COPY . /app/

RUN id -u appuser >/dev/null 2>&1 || useradd --create-home --shell /bin/sh appuser \
    && printf '#!/bin/sh\nexec wine msconvert "$@"\n' > /usr/local/bin/msconvert \
    && chmod +x /usr/local/bin/msconvert \
    && mkdir -p /app/data /app/media /app/staticfiles /data/raw /data/results \
    && chown -R appuser:appuser /app /data

USER appuser

CMD ["python3", "manage.py", "run_processor_agent"]
