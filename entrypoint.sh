#!/bin/bash
set -e

echo "Running migrations..."
python manage.py migrate --noinput

echo "Creating superuser if not exists..."
python manage.py shell -c "
from django.contrib.auth.models import User
from authenticate.models import UserProfile
import os
username = os.environ.get('DJANGO_SUPERUSER_USERNAME', 'admin')
password = os.environ.get('DJANGO_SUPERUSER_PASSWORD', 'admin123')
email = os.environ.get('DJANGO_SUPERUSER_EMAIL', 'admin@example.com')
if not User.objects.filter(username=username).exists():
    user = User.objects.create_superuser(username=username, email=email, password=password)
    UserProfile.objects.get_or_create(user=user, defaults={'role': 'super_admin'})
    print(f'Superuser \"{username}\" created.')
else:
    print(f'Superuser \"{username}\" already exists.')
"

echo "Starting gunicorn..."
exec gunicorn ainventory.wsgi:application \
    --bind 0.0.0.0:7000 \
    --workers 3 \
    --threads 2 \
    --timeout 120
