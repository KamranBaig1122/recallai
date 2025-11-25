"""
ASGI config for recallai project.
"""

import os

from django.core.asgi import get_asgi_application

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'recallai.settings')

application = get_asgi_application()

