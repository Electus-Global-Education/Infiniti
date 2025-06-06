# infiniti/settings.py

import os
from pathlib import Path
import environ # Import django-environ
from datetime import timedelta
from django.core.exceptions import ImproperlyConfigured # Import this

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent # This should point to your project root (Infiniti/)

# Initialize django-environ
# Define default values and casting for environment variables
env = environ.Env(
    DEBUG=(bool, False),
    ALLOWED_HOSTS=(list, ['127.0.0.1', 'localhost',"35.208.164.184"]),
    CSRF_TRUSTED_ORIGINS=(list, ['http://localhost:8000', 'http://127.0.0.1:8000']),
    CORS_ALLOWED_ORIGINS=(list, ['http://localhost:3000', 'http://127.0.0.1:3000']),
    CELERY_BROKER_URL=(str, "redis://redis:6379/0"),
    CELERY_BACKEND_URL=(str, "redis://redis:6379/1"),
    # Add a default for GOOGLE_APPLICATION_CREDENTIALS for build time.
    # The runtime value will be set by docker-compose's environment directive.
    # An empty string should be fine if it's not strictly needed for settings.py to load
    # or for apps to initialize during collectstatic.
    GOOGLE_APPLICATION_CREDENTIALS=(str, '')
)

AUTH_USER_MODEL = 'core.User'
# --- Authentication Settings ---
LOGIN_URL = 'login'
LOGIN_REDIRECT_URL = 'core:dashboard'
LOGOUT_REDIRECT_URL = 'core:landing_page'

# --- Environment Variables ---
# Attempt to read .env.django file from BASE_DIR.
ENV_FILE_PATH = BASE_DIR / '.env.django'
if os.path.exists(ENV_FILE_PATH):
    print(f"INFO: Reading environment variables from: {ENV_FILE_PATH}")
    environ.Env.read_env(ENV_FILE_PATH) # Reads into os.environ and django-environ's cache

CELERY_BROKER_URL     = env("CELERY_BROKER_URL")
CELERY_RESULT_BACKEND = env("CELERY_BACKEND_URL")

# Load other .env files like .env.gemini, .env.vectorstore IF THEY EXIST
# These files must be copied into the Docker image if they are expected during build
# and contain variables needed for settings.py to parse (like GOOGLE_APPLICATION_CREDENTIALS if not defaulted above).
env_files_to_check = [
    os.path.join(BASE_DIR, ".env.gemini"),
    os.path.join(BASE_DIR, ".env.vectorstore"),
]
for f_path in env_files_to_check:
    if os.path.exists(f_path):
        print(f"INFO: Reading additional environment variables from: {f_path}")
        # Load these into django-environ's cache. If they define GOOGLE_APPLICATION_CREDENTIALS,
        # the env() call later will pick it up.
        env.read_env(f_path, overwrite=True)


# --- Security Settings ---
SECRET_KEY = env('SECRET_KEY', default='your_development_secret_key_please_change_me_if_not_set_in_env')
DEBUG = env('DEBUG')
ALLOWED_HOSTS = env.list('ALLOWED_HOSTS')
if not DEBUG and 'app.lifehubinfiniti.ai' not in ALLOWED_HOSTS: # Example production domain
    ALLOWED_HOSTS.append('app.lifehubinfiniti.ai')


# --- Application Definition ---
INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'whitenoise.runserver_nostatic',
    'django.contrib.staticfiles',
    'edujobs',
    'baserag',
    'fini',
    'rest_framework',
    'corsheaders',
    'drf_spectacular',
    'rest_framework_simplejwt',
    'core.apps.CoreConfig',
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

ROOT_URLCONF = 'infiniti.urls'

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

WSGI_APPLICATION = 'infiniti.wsgi.application'
ASGI_APPLICATION = 'infiniti.asgi.application'

# --- Database ---
DATABASES = {
    'default': env.db_url(
        'DATABASE_URL',
        default=f'postgres://user:pass@localhost:5432/defaultdb_pleasesetenv'
    )
}

AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'UTC'
USE_I18N = True
USE_TZ = True

STATIC_URL = '/static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'
STATICFILES_DIRS = [
    BASE_DIR / "static",
]
STATICFILES_STORAGE = 'whitenoise.storage.CompressedManifestStaticFilesStorage'

MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'mediafiles'

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

EMAIL_BACKEND = env('EMAIL_BACKEND', default='django.core.mail.backends.console.EmailBackend')
if EMAIL_BACKEND == 'django.core.mail.backends.smtp.EmailBackend':
    EMAIL_HOST = env('EMAIL_HOST', default='localhost')
    EMAIL_PORT = env.int('EMAIL_PORT', default=25)
    EMAIL_USE_TLS = env.bool('EMAIL_USE_TLS', default=False)
    EMAIL_USE_SSL = env.bool('EMAIL_USE_SSL', default=False)
    EMAIL_HOST_USER = env('EMAIL_HOST_USER', default='')
    EMAIL_HOST_PASSWORD = env('EMAIL_HOST_PASSWORD', default='')
    DEFAULT_FROM_EMAIL = env('DEFAULT_FROM_EMAIL', default='webmaster@localhost')
    SERVER_EMAIL = env('SERVER_EMAIL', default=DEFAULT_FROM_EMAIL)

REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': [
        # 'rest_framework.authentication.SessionAuthentication',
        # 'rest_framework_simplejwt.authentication.JWTAuthentication',
        'core.authentication.APIKeyAuthentication', 
        'rest_framework.authentication.SessionAuthentication'
    ],
    'DEFAULT_PERMISSION_CLASSES': [
        'rest_framework.permissions.IsAuthenticated'
        # 'rest_framework.permissions.IsAuthenticatedOrReadOnly',
    ],
    'DEFAULT_PAGINATION_CLASS': 'rest_framework.pagination.PageNumberPagination',
    'PAGE_SIZE': 10,
    'DEFAULT_SCHEMA_CLASS': 'drf_spectacular.openapi.AutoSchema',
}

SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(days=1),
    "REFRESH_TOKEN_LIFETIME": timedelta(days=1),
    "ROTATE_REFRESH_TOKENS": False,
    "BLACKLIST_AFTER_ROTATION": True,
    "ALGORITHM": "HS256",
    "AUTH_HEADER_TYPES": ("Bearer",),
}

SPECTACULAR_SETTINGS = {
    'TITLE': 'Infiniti Project API',
    'DESCRIPTION': 'API documentation for the Infiniti project.',
    'VERSION': '1.0.0',
    'SERVE_INCLUDE_SCHEMA': False,
}

CORS_ALLOWED_ORIGINS = env.list('CORS_ALLOWED_ORIGINS', default=[])
CORS_ALLOW_CREDENTIALS = True

CSRF_TRUSTED_ORIGINS = env.list('CSRF_TRUSTED_ORIGINS', default=[])
if not DEBUG and 'https://app.lifehubinfiniti.ai' not in CSRF_TRUSTED_ORIGINS: # Example
    CSRF_TRUSTED_ORIGINS.append('https://app.lifehubinfiniti.ai')


# --- Google Application Credentials Handling ---
# This will now use the default '' if GOOGLE_APPLICATION_CREDENTIALS is not found
# in OS environment or any loaded .env files.
# The actual path will be provided by docker-compose at runtime.
gac_path_from_env = env('GOOGLE_APPLICATION_CREDENTIALS')
if gac_path_from_env: # If a non-empty path is found (from env var or a loaded .env file)
    os.environ['GOOGLE_APPLICATION_CREDENTIALS'] = gac_path_from_env
    print(f"INFO: GOOGLE_APPLICATION_CREDENTIALS set during settings load to: {gac_path_from_env}")
else:
    # This means GAC was not in .env.django, .env.gemini, .env.vectorstore, or OS env
    # and defaulted to ''. This is fine for collectstatic if not strictly needed for app imports.
    # The runtime container will get the proper one from docker-compose's environment setting.
    print("WARNING: GOOGLE_APPLICATION_CREDENTIALS resolved to an empty string during settings load. Relies on runtime injection for actual use.")


LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'verbose': {
            'format': '{levelname} {asctime} {module} {process:d} {thread:d} {message}',
            'style': '{',
        },
        'simple': {
            'format': '{levelname} {message}',
            'style': '{',
        },
    },
    'handlers': {
        'console': {
            'class': 'logging.StreamHandler',
            'formatter': 'simple' if not DEBUG else 'verbose',
        },
    },
    'root': {
        'handlers': ['console'],
        'level': 'INFO' if not DEBUG else 'DEBUG',
    },
    'loggers': {
        'django': {
            'handlers': ['console'],
            'level': os.getenv('DJANGO_LOG_LEVEL', 'INFO'),
            'propagate': False,
        },
        'django.db.backends': {
            'handlers': ['console'],
            'level': 'DEBUG' if DEBUG else 'INFO',
            'propagate': False,
        },
    },
}

print(f"--- Django Settings Initialized (settings.py) ---")
# Add other debug prints if needed, but the GAC one above is key for this issue.
print(f"DEBUG: {DEBUG}")
print(f"STATIC_ROOT: {STATIC_ROOT}")
print("--- End of Django Settings Initialization ---")
