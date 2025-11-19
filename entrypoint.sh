#!/bin/bash
set -e

echo "======================================"
echo "🚀 Starting Django Application"
echo "======================================"

echo "⏳ Waiting for PostgreSQL..."
python - << END
import time
import socket
import sys

max_retries = 30
retry_count = 0

while retry_count < max_retries:
    try:
        s = socket.create_connection(("db", 5432), timeout=2)
        s.close()
        print("✅ PostgreSQL is ready!")
        sys.exit(0)
    except Exception as e:
        retry_count += 1
        if retry_count >= max_retries:
            print(f"❌ Failed to connect to PostgreSQL after {max_retries} attempts")
            sys.exit(1)
        print(f"⏳ PostgreSQL not ready yet, attempt {retry_count}/{max_retries}...")
        time.sleep(1)
END

echo "⏳ Waiting for Redis..."
python - << END
import time
import socket
import sys

max_retries = 30
retry_count = 0

while retry_count < max_retries:
    try:
        s = socket.create_connection(("redis", 6379), timeout=2)
        s.close()
        print("✅ Redis is ready!")
        sys.exit(0)
    except Exception as e:
        retry_count += 1
        if retry_count >= max_retries:
            print(f"❌ Failed to connect to Redis after {max_retries} attempts")
            sys.exit(1)
        print(f"⏳ Redis not ready yet, attempt {retry_count}/{max_retries}...")
        time.sleep(1)
END

echo "📊 Running database migrations..."
python manage.py migrate --noinput
if [ $? -eq 0 ]; then
    echo "✅ Migrations completed successfully"
else
    echo "❌ Migrations failed"
    exit 1
fi

echo "📦 Collecting static files..."
python manage.py collectstatic --noinput --clear
if [ $? -eq 0 ]; then
    echo "✅ Static files collected successfully"
else
    echo "❌ Static files collection failed"
    exit 1
fi

echo "👤 Checking superuser..."
python manage.py shell << END
from django.contrib.auth import get_user_model
import os

User = get_user_model()

username = os.environ.get('DJANGO_SUPERUSER_USERNAME', 'admin')
email = os.environ.get('DJANGO_SUPERUSER_EMAIL', 'admin@example.com')
password = os.environ.get('DJANGO_SUPERUSER_PASSWORD', 'admin')

if not User.objects.filter(username=username).exists():
    User.objects.create_superuser(username, email, password)
    print(f'✅ Superuser created: {username}')
else:
    print(f'ℹ️  Superuser already exists: {username}')
END

echo "📁 Creating directories..."
mkdir -p /app/logs /app/media /app/staticfiles
echo "✅ Directories created"

echo "🔍 Validating environment..."
python - << END
import os
import sys

required_vars = [
    'SECRET_KEY',
    'POSTGRES_DB',
    'POSTGRES_USER',
    'POSTGRES_PASSWORD',
    'STRIPE_PUBLISHABLE_KEY_USD',
    'STRIPE_SECRET_KEY_USD',
    'STRIPE_PUBLISHABLE_KEY_EUR',
    'STRIPE_SECRET_KEY_EUR',
]

missing_vars = [var for var in required_vars if not os.environ.get(var)]

if missing_vars:
    print(f"❌ Missing required environment variables: {', '.join(missing_vars)}")
    sys.exit(1)

# Check DEBUG mode
debug = os.environ.get('DEBUG', 'False').lower() in ('true', '1', 't')
if debug:
    print("⚠️  WARNING: Running in DEBUG mode!")
else:
    print("✅ Running in production mode (DEBUG=False)")

# Check Stripe keys
stripe_pub = os.environ.get('STRIPE_PUBLISHABLE_KEY_USD', '')
stripe_sec = os.environ.get('STRIPE_SECRET_KEY_USD', '')

print("✅ Environment validation passed")
END

if [ $? -ne 0 ]; then
    echo "❌ Environment validation failed"
    exit 1
fi

echo "======================================"
echo "✅ Initialization complete"
echo "🚀 Starting server..."
echo "======================================"

exec "$@"