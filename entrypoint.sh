#!/bin/bash
set -e

echo "======================================"
echo "🚀 Starting Django Application"
echo "======================================"

echo "⏳ Waiting for PostgreSQL..."
max_retries=30
retry_count=0

while [ $retry_count -lt $max_retries ]; do
    if pg_isready -h db -p 5432 -U "${POSTGRES_USER:-stripe_user}" > /dev/null 2>&1; then
        echo "✅ PostgreSQL is ready!"
        break
    fi
    retry_count=$((retry_count + 1))
    if [ $retry_count -eq $max_retries ]; then
        echo "❌ Failed to connect to PostgreSQL after ${max_retries} attempts"
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
        echo "❌ Failed to connect to Redis after ${max_retries} attempts"
        exit 1
    fi
    sleep 1
done

echo "🔍 Validating environment..."
python << 'PYEOF'
import os
import sys

required = [
    'SECRET_KEY', 'POSTGRES_DB', 'POSTGRES_USER', 'POSTGRES_PASSWORD',
    'STRIPE_PUBLISHABLE_KEY_USD', 'STRIPE_SECRET_KEY_USD',
    'STRIPE_PUBLISHABLE_KEY_EUR', 'STRIPE_SECRET_KEY_EUR',
]

missing = [v for v in required if not os.getenv(v)]
if missing:
    print(f"❌ Missing: {', '.join(missing)}")
    sys.exit(1)

debug = os.getenv('DEBUG', 'False').lower() in ('true', '1', 't')
print("⚠️  DEBUG mode" if debug else "✅ Production mode")

# Проверяем формат Stripe ключей только в production
if not debug:
    keys_to_check = [
        ('STRIPE_PUBLISHABLE_KEY_USD', 'pk_live_'),
        ('STRIPE_SECRET_KEY_USD', 'sk_live_'),
        ('STRIPE_PUBLISHABLE_KEY_EUR', 'pk_live_'),
        ('STRIPE_SECRET_KEY_EUR', 'sk_live_'),
    ]
    
    for key_name, prefix in keys_to_check:
        key_val = os.getenv(key_name, '')
        if not key_val.startswith(prefix):
            print(f"⚠️  WARNING: {key_name} should start with {prefix} in production!")

print("✅ Environment OK")
PYEOF

if [ $? -ne 0 ]; then
    echo "❌ Environment validation failed"
    exit 1
fi

mkdir -p /app/logs /app/media /app/staticfiles

echo "📊 Running migrations..."
if python manage.py migrate --noinput; then
    echo "✅ Migrations OK"
else
    echo "❌ Migrations failed"
    exit 1
fi

# Static
echo "📦 Collecting static..."
if python manage.py collectstatic --noinput --clear; then
    echo "✅ Static files OK"
else
    echo "❌ Static collection failed"
    exit 1
fi

echo "👤 Creating superuser if needed..."
python manage.py shell << 'PYEOF'
from django.contrib.auth import get_user_model
import os

User = get_user_model()
username = os.getenv('DJANGO_SUPERUSER_USERNAME', 'admin')
email = os.getenv('DJANGO_SUPERUSER_EMAIL', 'admin@example.com')
password = os.getenv('DJANGO_SUPERUSER_PASSWORD', 'admin')

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