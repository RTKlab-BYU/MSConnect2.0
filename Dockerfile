FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

RUN adduser --disabled-password --gecos "" appuser

COPY requirements.txt /app/
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r requirements.txt

COPY . /app/

RUN mkdir -p /app/data /app/media /app/staticfiles /data/incoming /data/raw \
    && chown -R appuser:appuser /app /data

USER appuser

EXPOSE 8000

CMD ["gunicorn", "msconnect.wsgi:application", "--bind", "0.0.0.0:8000"]

