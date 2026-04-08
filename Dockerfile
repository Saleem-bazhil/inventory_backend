FROM python:3.11-slim

# Environment variables
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    DJANGO_SETTINGS_MODULE=ainventory.settings

# Set work directory
WORKDIR /app

# Install system dependencies (important for psycopg2, Pillow, etc.)
RUN apt-get update && apt-get install -y \
    build-essential \
    libpq-dev \
    && apt-get clean

# Create non-root user
RUN addgroup --system app && adduser --system --ingroup app app

# Install Python dependencies
COPY requirements.txt .
RUN pip install --upgrade pip && \
    pip install -r requirements.txt

# Copy project
COPY . .

# Create static directory BEFORE collectstatic
RUN mkdir -p /app/staticfiles && \
    python manage.py collectstatic --noinput

# Set ownership
RUN chown -R app:app /app

USER app

EXPOSE 8000

CMD ["gunicorn", "ainventory.wsgi:application", \
     "--bind", "0.0.0.0:8000", \
     "--workers", "3", \
     "--threads", "2", \
     "--timeout", "120"]