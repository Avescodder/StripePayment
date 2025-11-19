#!/bin/bash
set -e

echo "======================================"
echo "🚀 Starting Django Application"
echo "======================================"

echo "⏳ Waiting for PostgreSQL..."
max_retries=30
retry_count=0

while [ $retry_count -lt $max_retries ]; do
    if pg_isready -h db -p 5432 -U stripe_user > /dev/null 2>&1; then
        echo "✅ PostgreSQL is ready!"
        break
    fi
    retry_count=$((retry_count + 1))
    if [ $retry_count -eq $max_retries ]; then
        echo "❌ Failed to connect to PostgreSQL"
        exit 1
    fi
    sleep 1
done

echo "⏳ Waiting for Redis..."
retry_count=0

while [ $retry_count -lt $max_retries ]; do
    if timeout 1 bash -c "echo > /dev/tcp/redis/6379" 2>/dev/null; then
        echo "✅ Redis is ready!"
        break
    fi
    retry_count=$((retry_count + 1))
    if [ $retry_count -eq $max_retries ]; then
        echo "❌ Failed to connect to Redis"
        exit 1
    fi
    sleep 1
done

echo "🔍 Validating environment..."
uv run python - << 'PYEOF'
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
    print(f"❌ Missing: {', '.join(missing_vars)}")
    sys.exit(1)

debug = os.environ.get('DEBUG', 'False').lower() in ('true', '1', 't')
print("⚠️  DEBUG mode" if debug else "✅ Production mode")
print("✅ Environment OK")
PYEOF

if [ $? -ne 0 ]; then
    exit 1
fi

mkdir -p /app/logs /app/media /app/staticfiles

echo "📊 Running migrations..."
if uv run python manage.py migrate --noinput; then
    echo "✅ Migrations OK"
else
    echo "❌ Migrations failed"
    exit 1
fi

echo "📦 Collecting static..."
if uv run python manage.py collectstatic --noinput --clear; then
    echo "✅ Static files OK"
else
    echo "❌ Static collection failed"
    exit 1
fi

echo "👤 Creating superuser..."
uv run python manage.py shell << 'PYEOF'
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
    print(f'ℹ️  Superuser exists: {username}')
PYEOF

echo "======================================"
echo "✅ Ready to start"
echo "======================================"

exec "$@"