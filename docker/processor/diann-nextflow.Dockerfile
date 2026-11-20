ARG DOTNET_SDK_IMAGE=mcr.microsoft.com/dotnet/sdk:8.0-bookworm-slim
FROM ${DOTNET_SDK_IMAGE} AS dotnet

FROM python:3.12-slim-bookworm
ARG DIANN_VERSION=2.7.0
ARG NEXTFLOW_VERSION=26.10.6
ARG DIANN_LINUX_URL=https://github.com/vdemichev/DiaNN/releases/download/2.0/DIA-NN-2.7.0-Academia-Linux.zip
ARG DIANN_SHA256=246ca8baf2e9f308854976f94b8761e452275a97b3632070e275a2b4401cb223
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    DOTNET_ROOT=/usr/share/dotnet \
    DOTNET_SYSTEM_GLOBALIZATION_INVARIANT=1 \
    NXF_VER=${NEXTFLOW_VERSION} \
    MSCONNECT_PROCESSOR_ENGINE=diann \
    MSCONNECT_PROCESSOR_ENGINE_VERSION=${DIANN_VERSION} \
    MSCONNECT_PROCESSOR_ENGINE_PROFILE=diann:${DIANN_VERSION} \
    DIANN_VERSION=${DIANN_VERSION} \
    NXF_WORK_DIR=/scratch/nxf-work
ENV PATH="${PATH}:/usr/share/dotnet"

COPY --from=dotnet /usr/share/dotnet /usr/share/dotnet
RUN sed -i 's|http://deb.debian.org|https://deb.debian.org|g' /etc/apt/sources.list.d/debian.sources \
    && apt-get update && apt-get install -y --no-install-recommends \
      ca-certificates curl unzip openjdk-17-jre-headless libgomp1 libunwind8 \
      libicu72 libssl3 zlib1g procps \
    && rm -rf /var/lib/apt/lists/* \
    && adduser --disabled-password --gecos "" appuser \
    && mkdir -p /opt/diann/${DIANN_VERSION} /opt/msconnect/nextflow/diann /data/raw /data/results /data/shared /scratch/nxf-work \
    && chown -R appuser:appuser /data /scratch

RUN test -n "${DIANN_SHA256}" \
    && curl -fL --retry 5 --retry-all-errors "${DIANN_LINUX_URL}" -o /tmp/diann.zip \
    && echo "${DIANN_SHA256}  /tmp/diann.zip" | sha256sum -c - \
    && unzip -q /tmp/diann.zip -d /opt/diann/${DIANN_VERSION} \
    && rm /tmp/diann.zip \
    && DIANN_BIN="$(find /opt/diann/${DIANN_VERSION} -type f -name 'diann-linux' -print -quit)" \
    && test -n "${DIANN_BIN}" \
    && chmod +x "${DIANN_BIN}" \
    && printf '#!/bin/sh\nexport LD_LIBRARY_PATH="%s:${LD_LIBRARY_PATH:-}"\nexec "%s" "$@"\n' "$(dirname "${DIANN_BIN}")" "${DIANN_BIN}" > /usr/local/bin/diann \
    && chmod +x /usr/local/bin/diann

RUN curl -fsSL https://get.nextflow.io | bash \
    && install -m 0755 nextflow /usr/local/bin/nextflow \
    && rm -f nextflow \
    && nextflow -version | grep -F "${NEXTFLOW_VERSION}"

WORKDIR /app
COPY requirements.txt ./
RUN pip install --no-cache-dir --timeout 120 --retries 5 -r requirements.txt
COPY . /app/
COPY core/processing/diann_search.py /opt/msconnect/diann_search.py
COPY nextflow/diann/ /opt/msconnect/nextflow/diann/
RUN python -c "import json,pathlib,os; p=pathlib.Path('/opt/msconnect/nextflow/diann/versions.json'); d=json.loads(p.read_text()); v=os.environ['DIANN_VERSION']; d['versions']={v:{'distribution':f'DIA-NN-{v}-Academia-Linux.zip','executable':'/usr/local/bin/diann','conda_env':None,'tested':True,'validation':'DIA-NN 2.7.0 + Nextflow 26.10.6 end-to-end smoke with mzML and one-protein FASTA','archive_sha256':'${DIANN_SHA256}','nextflow_version':os.environ['NXF_VER'],'release_channel':'main'}}; p.write_text(json.dumps(d,indent=2)+'\\n')" \
    && python -c "import subprocess; subprocess.run(['diann'],check=True,stdout=subprocess.DEVNULL)" \
    && mkdir -p /app/data /data/raw /data/results /data/shared /scratch/nxf-work \
    && chown -R appuser:appuser /app /data /scratch /opt/msconnect
USER appuser
CMD ["python", "manage.py", "run_processor_agent", "--engine", "diann"]
