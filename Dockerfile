FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    DJANGO_SETTINGS_MODULE=ainventory.settings

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

RUN addgroup --system app && adduser --system --ingroup app app

COPY requirement.txt .
RUN pip install --upgrade pip && \
    pip install -r requirement.txt

COPY . .

RUN chmod +x entrypoint.sh && \
    mkdir -p /app/staticfiles && \
    python manage.py collectstatic --noinput

RUN chown -R app:app /app

USER app

EXPOSE 7000

CMD ["./entrypoint.sh"]
