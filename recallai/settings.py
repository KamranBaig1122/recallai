"""
Django settings for recallai project.
"""

import os
from pathlib import Path
from dotenv import load_dotenv
from urllib.parse import unquote

load_dotenv()

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent

# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = os.getenv('SECRET', 'django-insecure-change-this-in-production')

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = os.getenv('NODE_ENV', 'development') == 'development'

ALLOWED_HOSTS = ['*']  # For development with ngrok

# Get PUBLIC_URL early for CSRF settings
PUBLIC_URL = os.getenv('PUBLIC_URL', 'http://localhost:3003')

# CSRF trusted origins - add ngrok URL here
CSRF_TRUSTED_ORIGINS = [
    'http://localhost:3003',
    'http://127.0.0.1:3003',
]
if PUBLIC_URL:
    CSRF_TRUSTED_ORIGINS.append(PUBLIC_URL)
    # Handle both http and https versions
    if PUBLIC_URL.startswith('https://'):
        CSRF_TRUSTED_ORIGINS.append(PUBLIC_URL.replace('https://', 'http://'))
    elif PUBLIC_URL.startswith('http://'):
        CSRF_TRUSTED_ORIGINS.append(PUBLIC_URL.replace('http://', 'https://'))

# Application definition
INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'channels',  # Django Channels for WebSocket support
    'app',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    'app.middleware.auth_middleware.AuthMiddleware',
    'app.middleware.notice_middleware.NoticeMiddleware',
]

ROOT_URLCONF = 'recallai.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'recallai.wsgi.application'

# Database - Supabase (PostgreSQL)
# Support both URI format and individual environment variables (matching Supabase template)
db_uri = os.getenv('SUPABASE_DB_URI', '')
if db_uri:
    # Parse the URI - handle various formats
    from urllib.parse import urlparse, unquote
    
    try:
        # Try standard URL parsing first
        parsed = urlparse(db_uri)
        db_user = parsed.username or 'postgres'
        db_password = parsed.password or ''
        db_host = parsed.hostname or ''
        db_port = str(parsed.port) if parsed.port else '5432'
        db_name = parsed.path.lstrip('/') if parsed.path else 'postgres'
    except Exception as e:
        print(f"Warning: Could not parse SUPABASE_DB_URI: {e}")
        db_user = os.getenv('user') or os.getenv('SUPABASE_DB_USER') or 'postgres'
        db_password = os.getenv('password') or os.getenv('SUPABASE_DB_PASSWORD') or ''
        db_host = os.getenv('host') or os.getenv('SUPABASE_DB_HOST') or ''
        db_port = os.getenv('port') or os.getenv('SUPABASE_DB_PORT') or '5432'
        db_name = os.getenv('dbname') or os.getenv('SUPABASE_DB_NAME') or 'postgres'
else:
    # Use individual environment variables (matching Supabase template format)
    db_user = os.getenv('user') or os.getenv('SUPABASE_DB_USER') or 'postgres'
    db_password = os.getenv('password') or os.getenv('SUPABASE_DB_PASSWORD') or ''
    db_host = os.getenv('host') or os.getenv('SUPABASE_DB_HOST') or ''
    # Prioritize DB-specific port, avoid Django PORT conflict
    db_port = os.getenv('SUPABASE_DB_PORT') or (os.getenv('port') if os.getenv('port') != os.getenv('PORT') else None) or '5432'
    db_name = os.getenv('dbname') or os.getenv('SUPABASE_DB_NAME') or 'postgres'

# Configure database connection with SSL (required for Supabase)
# For Supabase Session Pooler: Set CONN_MAX_AGE to 0 to prevent connection exhaustion
# Session Pooler has limited pool_size, so we need to close connections after each request
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': db_name,
        'USER': db_user,
        'PASSWORD': unquote(db_password) if db_uri else db_password,
        'HOST': db_host,
        'PORT': db_port,
        'OPTIONS': {
            'sslmode': 'require',
            'connect_timeout': 10,  # Connection timeout in seconds
        },
        # CONN_MAX_AGE: 0 = Close connection after each request (prevents pool exhaustion)
        # This is recommended for Supabase Session Pooler with limited pool_size
        'CONN_MAX_AGE': 0,
    }
}

# Password validation
AUTH_PASSWORD_VALIDATORS = [
    {
        'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator',
    },
]

# Internationalization
LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'UTC'
USE_I18N = True
USE_TZ = True

# Static files (CSS, JavaScript, Images)
STATIC_URL = 'static/'
STATICFILES_DIRS = [BASE_DIR / 'static'] if (BASE_DIR / 'static').exists() else []

# Default primary key field type
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# Django Channels configuration
ASGI_APPLICATION = 'recallai.asgi.application'

# Channels layer configuration (for WebSocket support)
# Using in-memory channel layer for development
# For production, use Redis: CHANNEL_LAYERS = {...}
CHANNEL_LAYERS = {
    'default': {
        'BACKEND': 'channels.layers.InMemoryChannelLayer'
    },
}

# Custom settings (PUBLIC_URL already defined above for CSRF settings)
PORT = int(os.getenv('PORT', '3003'))

# Recall API settings
RECALL_API_KEY = os.getenv('RECALL_API_KEY')
RECALL_API_HOST = os.getenv('RECALL_API_HOST', 'https://api.recall.ai')

# OAuth settings
GOOGLE_CALENDAR_OAUTH_CLIENT_ID = os.getenv('GOOGLE_CALENDAR_OAUTH_CLIENT_ID')
GOOGLE_CALENDAR_OAUTH_CLIENT_SECRET = os.getenv('GOOGLE_CALENDAR_OAUTH_CLIENT_SECRET')
MICROSOFT_OUTLOOK_OAUTH_CLIENT_ID = os.getenv('MICROSOFT_OUTLOOK_OAUTH_CLIENT_ID')
MICROSOFT_OUTLOOK_OAUTH_CLIENT_SECRET = os.getenv('MICROSOFT_OUTLOOK_OAUTH_CLIENT_SECRET')
REQUEST_ONLY_CALENDAR_SCOPES = os.getenv('REQUEST_ONLY_CALENDAR_SCOPES', '').lower() == 'true'

# Redis for background tasks (optional - can use Django Q or Celery)
REDIS_URL = os.getenv('REDIS_URL', 'redis://localhost:6379')

