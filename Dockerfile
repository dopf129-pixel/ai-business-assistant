FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app/app \
    AI_ASSISTANT_STORAGE_ROOT=/var/lib/ai-business-assistant

WORKDIR /app

COPY requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app

VOLUME ["/var/lib/ai-business-assistant"]

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD ["python", "-m", "runtime_healthcheck"]

STOPSIGNAL SIGTERM

CMD ["python", "-m", "telegram_api_bot"]
