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

RUN mkdir -p /app/staticfiles && \
    python manage.py collectstatic --noinput

RUN chown -R app:app /app

USER app

EXPOSE 8000

CMD ["gunicorn", "ainventory.wsgi:application", \
     "--bind", "0.0.0.0:8000", \
     "--workers", "3", \
     "--threads", "2", \
     "--timeout", "120"]
