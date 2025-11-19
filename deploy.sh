#!/bin/bash

set -e

echo "======================================"
echo "🚀 Django + Stripe Deployment Script"
echo "======================================"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' 

if [ "$EUID" -eq 0 ]; then 
    echo -e "${RED}❌ Please do not run this script as root${NC}"
    exit 1
fi

if [ ! -f .env ]; then
    echo -e "${RED}❌ .env file not found!${NC}"
    echo "Please create .env file from .env.production template"
    exit 1
fi

source .env

echo "🔍 Validating environment variables..."
REQUIRED_VARS=(
    "SECRET_KEY"
    "POSTGRES_DB"
    "POSTGRES_USER"
    "POSTGRES_PASSWORD"
    "STRIPE_PUBLISHABLE_KEY_USD"
    "STRIPE_SECRET_KEY_USD"
    "STRIPE_PUBLISHABLE_KEY_EUR"
    "STRIPE_SECRET_KEY_EUR"
    "ALLOWED_HOSTS"
)

MISSING_VARS=()
for var in "${REQUIRED_VARS[@]}"; do
    if [ -z "${!var}" ]; then
        MISSING_VARS+=("$var")
    fi
done

if [ ${#MISSING_VARS[@]} -ne 0 ]; then
    echo -e "${RED}❌ Missing required environment variables:${NC}"
    printf '%s\n' "${MISSING_VARS[@]}"
    exit 1
fi

echo -e "${GREEN}✅ Environment variables validated${NC}"

if [ "$DEBUG" = "True" ] || [ "$DEBUG" = "true" ]; then
    echo -e "${YELLOW}⚠️  WARNING: DEBUG mode is enabled!${NC}"
    read -p "Continue anyway? (y/N): " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        exit 1
    fi
fi

if ! command -v docker &> /dev/null; then
    echo -e "${RED}❌ Docker is not installed${NC}"
    exit 1
fi

if ! command -v docker-compose &> /dev/null; then
    echo -e "${RED}❌ Docker Compose is not installed${NC}"
    exit 1
fi

echo -e "${GREEN}✅ Docker and Docker Compose found${NC}"

if [ ! -f nginx/ssl/cert.pem ] || [ ! -f nginx/ssl/key.pem ]; then
    echo -e "${YELLOW}⚠️  SSL certificates not found in nginx/ssl/${NC}"
    echo "Do you want to generate self-signed certificates? (only for testing)"
    read -p "Generate self-signed SSL? (y/N): " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        echo "🔐 Generating self-signed SSL certificates..."
        mkdir -p nginx/ssl
        openssl req -x509 -nodes -days 365 -newkey rsa:2048 \
            -keyout nginx/ssl/key.pem \
            -out nginx/ssl/cert.pem \
            -subj "/C=US/ST=State/L=City/O=Organization/CN=localhost"
        echo -e "${GREEN}✅ Self-signed certificates generated${NC}"
    else
        echo "Please add SSL certificates to nginx/ssl/ directory"
        exit 1
    fi
fi

echo "📁 Creating directories..."
mkdir -p nginx/ssl nginx/logs nginx/conf.d logs

echo "🛑 Stopping existing containers..."
docker-compose down

if [ -d .git ]; then
    echo "📥 Pulling latest changes from git..."
    git pull
fi

echo "🏗️  Building Docker images..."
docker-compose build --no-cache

echo "🚀 Starting containers..."
docker-compose up -d

echo "⏳ Waiting for services to be healthy..."
sleep 10

if ! docker-compose ps | grep -q "Up"; then
    echo -e "${RED}❌ Some services failed to start${NC}"
    docker-compose logs
    exit 1
fi

echo -e "${GREEN}✅ All services started${NC}"

echo "📊 Running database migrations..."
docker-compose exec -T web python manage.py migrate --noinput

echo "📦 Collecting static files..."
docker-compose exec -T web python manage.py collectstatic --noinput --clear

echo ""
echo -e "${YELLOW}Would you like to create a superuser?${NC}"
read -p "Create superuser? (y/N): " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    docker-compose exec web python manage.py createsuperuser
fi

echo "🏥 Testing health endpoint..."
sleep 5
if curl -sf http://localhost:8000/health/ > /dev/null; then
    echo -e "${GREEN}✅ Health check passed${NC}"
else
    echo -e "${RED}❌ Health check failed${NC}"
    docker-compose logs web
    exit 1
fi

echo ""
echo "======================================"
echo -e "${GREEN}✅ Deployment completed successfully!${NC}"
echo "======================================"
echo ""
echo "📊 Service Status:"
docker-compose ps
echo ""
echo "🌐 Application URLs:"
echo "   - HTTP:  http://localhost"
echo "   - HTTPS: https://localhost"
echo "   - Admin: https://localhost/${ADMIN_URL:-admin/}"
echo ""
echo "📋 Useful commands:"
echo "   - View logs:        docker-compose logs -f"
echo "   - Stop services:    docker-compose down"
echo "   - Restart services: docker-compose restart"
echo "   - Shell access:     docker-compose exec web bash"
echo ""
echo "⚠️  Next steps:"
echo "   1. Configure your domain DNS to point to this server"
echo "   2. Update nginx/conf.d/default.conf with your domain"
echo "   3. Setup Let's Encrypt SSL certificates"
echo "   4. Configure Stripe webhooks at https://dashboard.stripe.com/webhooks"
echo "   5. Setup monitoring and backups"
echo ""
echo -e "${YELLOW}🔐 Don't forget to change default admin password!${NC}"
echo "======================================"