FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

COPY src /app/src
COPY data /app/data
COPY models /app/models
COPY docker/entrypoint.sh /entrypoint.sh

RUN chmod +x /entrypoint.sh && mkdir -p /app/backups

EXPOSE 5000

ENTRYPOINT ["/entrypoint.sh"]
