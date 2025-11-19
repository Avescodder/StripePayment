import os
from django.conf import settings

def admin_url(request):
    """Добавляет ADMIN_URL во все шаблоны"""
    return {
        'admin_url': os.getenv('ADMIN_URL', 'admin/')
    }