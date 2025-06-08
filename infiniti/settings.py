# infiniti/settings.py

import os
from pathlib import Path
import environ
from datetime import timedelta

# --- 1. Base Directory and Environment Setup ---
BASE_DIR = Path(__file__).resolve().parent.parent

# Initialize django-environ correctly, only once.
# Define schema and default values for all environment variables.
env = environ.Env(
    DEBUG=(bool, False),
    ALLOWED_HOSTS=(list, []),
    CSRF_TRUSTED_ORIGINS=(list, []),
    CORS_ALLOWED_ORIGINS=(list, []),
    CELERY_BROKER_URL=(str, 'redis://redis:6379/0'), # Default for docker-compose
    CELERY_RESULT_BACKEND=(str, 'redis://redis:6379/0'), # Default for docker-compose
    GOOGLE_APPLICATION_CREDENTIALS=(str, ''), # Default to empty for build-time safety
    SECURE_SSL_REDIRECT=(bool, False),
    SESSION_COOKIE_SECURE=(bool, False),
    CSRF_COOKIE_SECURE=(bool, False),
    SECURE_HSTS_SECONDS=(int, 0)
)

# Load environment variables from .env.django first, if it exists.
# This file should contain all primary settings for an environment.
ENV_FILE_PATH = BASE_DIR / '.env.django'
if os.path.exists(ENV_FILE_PATH):
    print(f"INFO: Reading environment variables from: {ENV_FILE_PATH}")
    env.read_env(ENV_FILE_PATH)

# Load any additional, separate .env files if they exist.
# These are also loaded by docker-compose for runtime.
env_files_to_check = [".env.gemini", ".env.vectorstore"]
for f_path in env_files_to_check:
    if os.path.exists(BASE_DIR / f_path):
        print(f"INFO: Reading additional environment variables from: {f_path}")
        env.read_env(os.path.join(BASE_DIR, f_path), overwrite=True)

# --- 2. Core Django Settings ---
SECRET_KEY = env('SECRET_KEY') # This MUST be in your .env.django
DEBUG = env('DEBUG')
ALLOWED_HOSTS = env.list('ALLOWED_HOSTS') # Reads the list directly from your .env file
ROOT_URLCONF = 'infiniti.urls'
WSGI_APPLICATION = 'infiniti.wsgi.application'
ASGI_APPLICATION = 'infiniti.asgi.application'
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'
AUTH_USER_MODEL = 'core.User'


# --- 3. Production / HTTPS Proxy Settings ---
# These settings should be enabled in your .env.django when DEBUG=False
if not DEBUG:
    SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
    SECURE_SSL_REDIRECT = env.bool('SECURE_SSL_REDIRECT', default=True)
    SESSION_COOKIE_SECURE = env.bool('SESSION_COOKIE_SECURE', default=True)
    CSRF_COOKIE_SECURE = env.bool('CSRF_COOKIE_SECURE', default=True)
    # Optional HSTS settings
    SECURE_HSTS_SECONDS = env.int('SECURE_HSTS_SECONDS', default=0)
    if SECURE_HSTS_SECONDS > 0:
        SECURE_HSTS_INCLUDE_SUBDOMAINS = True
        SECURE_HSTS_PRELOAD = True


# --- 4. Application Definition ---
INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'whitenoise.runserver_nostatic',
    'django.contrib.staticfiles',
    # 3rd Party Apps
    'rest_framework',
    'corsheaders',
    'drf_spectacular',
    'rest_framework_simplejwt',
    # Your Apps
    'core.apps.CoreConfig',
    'fund_finder.apps.FundFinderConfig',
    'edujobs',
    'baserag',
    'fini',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'corsheaders.middleware.CorsMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

# --- 5. Templates, Database, Passwords ---
TEMPLATES = [
    {'BACKEND': 'django.template.backends.django.DjangoTemplates', 'DIRS': [BASE_DIR / 'templates'], 'APP_DIRS': True,
     'OPTIONS': {'context_processors': ['django.template.context_processors.debug', 'django.template.context_processors.request', 'django.contrib.auth.context_processors.auth', 'django.contrib.messages.context_processors.messages']}}
]
DATABASES = {'default': env.db_url('DATABASE_URL')}
AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

# --- 6. Internationalization & Static/Media Files ---
LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'UTC'
USE_I18N = True
USE_TZ = True
STATIC_URL = '/static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'
STATICFILES_DIRS = [BASE_DIR / "static"]
STATICFILES_STORAGE = 'whitenoise.storage.CompressedManifestStaticFilesStorage'
MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'mediafiles'

# --- 7. Third-Party App Configurations (DRF, Celery, etc.) ---

# REST Framework
REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': (
        'core.authentication.APIKeyAuthentication',
        'rest_framework.authentication.SessionAuthentication',
        'rest_framework_simplejwt.authentication.JWTAuthentication',
    ),
    'DEFAULT_PERMISSION_CLASSES': ('rest_framework.permissions.IsAuthenticated',),
    'DEFAULT_PAGINATION_CLASS': 'rest_framework.pagination.PageNumberPagination',
    'PAGE_SIZE': 10,
    'DEFAULT_SCHEMA_CLASS': 'drf_spectacular.openapi.AutoSchema',
}

# Simple JWT
SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(days=1),
    "REFRESH_TOKEN_LIFETIME": timedelta(days=1),
    "ALGORITHM": "HS256",
    "AUTH_HEADER_TYPES": ("Bearer",),
}

# drf-spectacular
SPECTACULAR_SETTINGS = {'TITLE': 'Infiniti Project API', 'DESCRIPTION': 'API documentation for the Infiniti project.', 'VERSION': '1.0.0'}

# CORS
CORS_ALLOW_CREDENTIALS = True
CORS_ALLOWED_ORIGINS = env.list('CORS_ALLOWED_ORIGINS', default=[])
if not DEBUG and 'https://app.lifehubinfiniti.ai' not in CORS_ALLOWED_ORIGINS:
    CORS_ALLOWED_ORIGINS.append('https://app.lifehubinfiniti.ai')
CSRF_TRUSTED_ORIGINS = env.list('CSRF_TRUSTED_ORIGINS', default=[])
if not DEBUG and 'https://app.lifehubinfiniti.ai' not in CSRF_TRUSTED_ORIGINS:
    CSRF_TRUSTED_ORIGINS.append('https://app.lifehubinfiniti.ai')

# Celery
CELERY_BROKER_URL = env('CELERY_BROKER_URL')
CELERY_RESULT_BACKEND = env('CELERY_RESULT_BACKEND') # Note: Renamed from your original CELERY_BACKEND_URL
CELERY_ACCEPT_CONTENT = ['json']
CELERY_TASK_SERIALIZER = 'json'
CELERY_RESULT_SERIALIZER = 'json'
CELERY_TIMEZONE = TIME_ZONE

# --- 8. Authentication & Custom App Settings ---
LOGIN_URL = 'login'
LOGIN_REDIRECT_URL = 'core:dashboard'
LOGOUT_REDIRECT_URL = 'core:landing_page'

# Google Credentials
# This is set at runtime by docker-compose, but this line ensures os.environ is updated if read from a file.
os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = env("GOOGLE_APPLICATION_CREDENTIALS")

# --- 9. Logging ---
LOGGING = {
    'version': 1, 'disable_existing_loggers': False,
    'formatters': {
        'verbose': {'format': '{levelname} {asctime} {module} {message}', 'style': '{'},
        'simple': {'format': '{levelname} {message}', 'style': '{'},
    },
    'handlers': {'console': {'class': 'logging.StreamHandler', 'formatter': 'simple'}},
    'root': {'handlers': ['console'], 'level': 'INFO'},
    'loggers': {
        'django': {'handlers': ['console'], 'level': os.getenv('DJANGO_LOG_LEVEL', 'INFO'), 'propagate': False},
        'django.db.backends': {'handlers': ['console'], 'level': 'DEBUG' if DEBUG else 'INFO', 'propagate': False},
    },
}

# --- Final Sanity Check Print ---
print(f"--- Django Settings Initialized ---")
print(f"DEBUG: {DEBUG}")
print(f"ALLOWED_HOSTS: {ALLOWED_HOSTS}")
print(f"CELERY_BROKER_URL: {CELERY_BROKER_URL}")
print("--- End of Django Settings Initialization ---")
