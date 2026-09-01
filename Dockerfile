FROM node:22-slim AS frontend-build

WORKDIR /app

COPY frontend/package*.json /app/frontend/

WORKDIR /app/frontend

RUN npm ci

WORKDIR /app

COPY frontend /app/frontend
COPY ui /app/ui

WORKDIR /app/frontend

RUN npm run build

FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

RUN adduser --disabled-password --gecos "" appuser

COPY requirements.txt /app/
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r requirements.txt

COPY . /app/
COPY --from=frontend-build /app/ui/static/app /app/ui/static/app

RUN mkdir -p /app/data /app/media /app/staticfiles /data/incoming /data/raw /data/results \
    && chown -R appuser:appuser /app /data

USER appuser

EXPOSE 8000

CMD ["python", "/app/docker/web_entrypoint.py"]
