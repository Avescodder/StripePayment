#!/bin/bash
echo "Waiting for PostgreSQL..."

python - << END
import time, socket

while True:
    try:
        s = socket.create_connection(("db", 5432), 1)
        s.close()
        break
    except Exception:
        time.sleep(0.1)
END

echo "PostgreSQL started"

echo "Running migrations..."
python manage.py migrate --noinput

echo "Collecting static files..."
python manage.py collectstatic --noinput

echo "Creating superuser if doesn't exist..."
python manage.py shell << END
from django.contrib.auth import get_user_model
User = get_user_model()
if not User.objects.filter(username='admin').exists():
    User.objects.create_superuser('admin', 'admin@example.com', 'admin')
    print('Superuser created: admin/admin')
else:
    print('Superuser already exists')
END

echo "Starting server..."
exec "$@"