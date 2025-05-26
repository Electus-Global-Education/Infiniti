# infiniti/settings.py

import os
from pathlib import Path
import environ # Import django-environ
from datetime import timedelta      

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent # This should point to your project root (Infiniti/)

# Initialize django-environ
# Define default values and casting for environment variables
env = environ.Env(
    DEBUG=(bool, False),
    ALLOWED_HOSTS=(list, ['127.0.0.1', 'localhost']),
    CSRF_TRUSTED_ORIGINS=(list, ['http://localhost:8000', 'http://127.0.0.1:8000']), # Add your frontend origins for CSRF
    CORS_ALLOWED_ORIGINS=(list, ['http://localhost:3000', 'http://127.0.0.1:3000']), # Example for a React frontend on port 3000
)

# Attempt to read .env file from BASE_DIR.
# This is primarily for local development if you sometimes run `python manage.py` outside Docker.
# In Docker, docker-compose injects the environment variables directly from the specified env_file.
ENV_FILE_PATH = BASE_DIR / '.env.django' # Assuming .env.django is in your project root
if os.path.exists(ENV_FILE_PATH):
    print(f"Reading environment variables from: {ENV_FILE_PATH}")
    environ.Env.read_env(ENV_FILE_PATH)
elif os.path.exists(BASE_DIR / '.env'): # Fallback to a generic .env if .env.django not found
    print(f"Reading environment variables from: {BASE_DIR / '.env'}")
    environ.Env.read_env(BASE_DIR / '.env')
else:
    print("No .env file found. Relying on Docker-injected environment variables.")


# --- Security Settings ---
# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = env('SECRET_KEY', default='your_development_secret_key_please_change_me_if_not_set_in_env')

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = env('DEBUG')

ALLOWED_HOSTS = env.list('ALLOWED_HOSTS')
# If running behind a proxy that sets X-Forwarded-Host, you might need:
# USE_X_FORWARDED_HOST = True

# --- Application Definition ---
INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles', # Required for static files management
    'edujobs',

    # Third-party apps
    'rest_framework',
    'corsheaders',          # For Cross-Origin Resource Sharing
    'drf_spectacular',      # For API schema generation (Swagger/OpenAPI)

    # Your apps
    'core.apps.CoreConfig', # Or just 'core'
    # Add other apps here: 'your_app_name.apps.YourAppConfig' or 'your_app_name'
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware', # Whitenoise for static files, place high but after SecurityMiddleware
    'django.contrib.sessions.middleware.SessionMiddleware',
    'corsheaders.middleware.CorsMiddleware', # CORS middleware, place before CommonMiddleware if possible
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'infiniti.urls' # Assumes your project is named 'infiniti'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'], # Project-level templates directory
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
ASGI_APPLICATION = 'infiniti.asgi.application' # If you plan to use ASGI for Channels or async features

# --- Database ---
# https://docs.djangoproject.com/en/stable/ref/settings/#databases
print("Attempting to read DATABASE_URL from environment for DATABASES setting...")
DATABASE_URL_FROM_ENV_FOR_DB_CONFIG = os.getenv('DATABASE_URL') # For debugging
print(f"DATABASE_URL from os.getenv for DB config: {DATABASE_URL_FROM_ENV_FOR_DB_CONFIG}")

DATABASES = {
    'default': env.db_url(
        'DATABASE_URL',
        default=f'postgres://user:pass@localhost:5432/defaultdb_pleasesetenv' # Fallback default
    )
}
# Optional: Add connection pooling or other advanced settings
# DATABASES['default']['CONN_MAX_AGE'] = env.int('DB_CONN_MAX_AGE', default=60)

# Debug print for parsed database settings
if DATABASES['default']['NAME'] != 'defaultdb_pleasesetenv':
    print(f"DATABASES setting configured: DB Name='{DATABASES['default']['NAME']}', User='{DATABASES['default']['USER']}', Host='{DATABASES['default']['HOST']}', Port='{DATABASES['default']['PORT']}'")
else:
    print("Warning: DATABASES setting is using the fallback default. Ensure DATABASE_URL is set.")


# --- Password Validation ---
# https://docs.djangoproject.com/en/stable/ref/settings/#auth-password-validators
AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

# --- Internationalization ---
# https://docs.djangoproject.com/en/stable/topics/i18n/
LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'UTC' # Or your preferred timezone, e.g., 'Asia/Karachi'
USE_I18N = True
USE_TZ = True # Recommended to store datetimes in UTC in the database

# --- Static files (CSS, JavaScript, Images) ---
# https://docs.djangoproject.com/en/stable/howto/static-files/
STATIC_URL = '/static/'
# This is where Django's `collectstatic` will gather all static files.
STATIC_ROOT = BASE_DIR / 'staticfiles'
# Add directories where Django should look for static files in addition to each app's 'static' directory.
STATICFILES_DIRS = [
    BASE_DIR / "static", # Project-level static files directory
]
# For Whitenoise, to serve compressed static files (e.g., .gz, .br) if available
STATICFILES_STORAGE = 'whitenoise.storage.CompressedManifestStaticFilesStorage'

# --- Media files (User-uploaded files) ---
MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'mediafiles' # Directory where user-uploaded files will be stored

# --- Default primary key field type ---
# https://docs.djangoproject.com/en/stable/ref/settings/#default-auto-field
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# --- Email Configuration ---
EMAIL_BACKEND = env('EMAIL_BACKEND', default='django.core.mail.backends.console.EmailBackend') # Prints emails to console by default
if EMAIL_BACKEND == 'django.core.mail.backends.smtp.EmailBackend':
    EMAIL_HOST = env('EMAIL_HOST', default='localhost')
    EMAIL_PORT = env.int('EMAIL_PORT', default=25)
    EMAIL_USE_TLS = env.bool('EMAIL_USE_TLS', default=False)
    EMAIL_USE_SSL = env.bool('EMAIL_USE_SSL', default=False)
    EMAIL_HOST_USER = env('EMAIL_HOST_USER', default='')
    EMAIL_HOST_PASSWORD = env('EMAIL_HOST_PASSWORD', default='')
    DEFAULT_FROM_EMAIL = env('DEFAULT_FROM_EMAIL', default='webmaster@localhost')
    SERVER_EMAIL = env('SERVER_EMAIL', default=DEFAULT_FROM_EMAIL) # For error reporting emails

# --- Django REST Framework Settings ---
# https://www.django-rest-framework.org/api-guide/settings/
REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': [
        'rest_framework.authentication.SessionAuthentication', # For browsable API and session-based auth
        # 'rest_framework.authentication.TokenAuthentication', # Example: For token-based auth
        'rest_framework_simplejwt.authentication.JWTAuthentication', # Example: For JWT
    ],
    'DEFAULT_PERMISSION_CLASSES': [
        'rest_framework.permissions.IsAuthenticatedOrReadOnly', # Or IsAuthenticated, AllowAny, etc.
    ],
    'DEFAULT_PAGINATION_CLASS': 'rest_framework.pagination.PageNumberPagination',
    'PAGE_SIZE': 10,
    'DEFAULT_SCHEMA_CLASS': 'drf_spectacular.openapi.AutoSchema', # For drf-spectacular
    # 'DEFAULT_RENDERER_CLASSES': (
    #     'rest_framework.renderers.JSONRenderer', # Default
    #     'rest_framework.renderers.BrowsableAPIRenderer', # For browsable API in DEBUG mode
    # ),
    # 'DEFAULT_PARSER_CLASSES': (
    #     'rest_framework.parsers.JSONParser',
    # ),
}
SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(days=1),   # default is 5 mins
    "REFRESH_TOKEN_LIFETIME": timedelta(days=1),
    "ROTATE_REFRESH_TOKENS": False,
    "BLACKLIST_AFTER_ROTATION": True,
    "ALGORITHM": "HS256",
    "AUTH_HEADER_TYPES": ("Bearer",),
}
# --- drf-spectacular Settings (API Documentation) ---
# https://drf-spectacular.readthedocs.io/en/latest/settings.html
SPECTACULAR_SETTINGS = {
    'TITLE': 'Infiniti Project API',
    'DESCRIPTION': 'API documentation for the Infiniti project.',
    'VERSION': '1.0.0',
    'SERVE_INCLUDE_SCHEMA': False, # Usually False for production
    # 'SWAGGER_UI_DIST': 'SIDECAR',  # Serve Swagger UI from a CDN
    # 'SWAGGER_UI_FAVICON_HREF': 'SIDECAR',
    # 'REDOC_DIST': 'SIDECAR',  # Serve Redoc from a CDN
}

# --- CORS (Cross-Origin Resource Sharing) Settings ---
# https://github.com/adamchainz/django-cors-headers
# CORS_ALLOWED_ORIGINS = env.list('CORS_ALLOWED_ORIGINS', default=[]) # Already defined with env
# Or, for more flexibility:
# CORS_ALLOW_ALL_ORIGINS = env.bool('CORS_ALLOW_ALL_ORIGINS', default=False) # Be careful with this in production
CORS_ALLOW_CREDENTIALS = True # If your frontend needs to send cookies/auth headers
# CORS_ALLOW_METHODS = ['DELETE', 'GET', 'OPTIONS', 'PATCH', 'POST', 'PUT']
# CORS_ALLOW_HEADERS = ['accept', 'authorization', 'content-type', 'user-agent', 'x-csrftoken', 'x-requested-with']

# --- CSRF Settings ---
CSRF_TRUSTED_ORIGINS = env.list('CSRF_TRUSTED_ORIGINS', default=[]) # Already defined with env
# Ensure your frontend's domain (including scheme and port if not standard) is listed here if it makes POST/PUT/DELETE requests.
# Load Gemini settings
from dotenv import load_dotenv
load_dotenv(dotenv_path=os.path.join(BASE_DIR, ".env_gemini"))

# --- Logging Configuration (Example) ---
# https://docs.djangoproject.com/en/stable/topics/logging/
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
            'formatter': 'simple' if not DEBUG else 'verbose', # More verbose in DEBUG
        },
        # 'file': {
        #     'level': 'DEBUG',
        #     'class': 'logging.FileHandler',
        #     'filename': BASE_DIR / 'debug.log',
        #     'formatter': 'verbose',
        # },
    },
    'root': {
        'handlers': ['console'], # Add 'file' here if you uncomment the file handler
        'level': 'INFO' if not DEBUG else 'DEBUG', # More logging in DEBUG
    },
    'loggers': {
        'django': {
            'handlers': ['console'],
            'level': os.getenv('DJANGO_LOG_LEVEL', 'INFO'),
            'propagate': False,
        },
        'django.db.backends': { # To see SQL queries in DEBUG mode
            'handlers': ['console'],
            'level': 'DEBUG' if DEBUG else 'INFO',
            'propagate': False,
        },
    },
}

# --- Debugging Print Statements ---
# These were added for debugging the DATABASE_URL issue.
# You might want to remove or comment them out for cleaner logs once the issue is resolved.
print("--- Django Settings Loaded ---")
print(f"DEBUG: {DEBUG}")
print(f"ALLOWED_HOSTS: {ALLOWED_HOSTS}")
print(f"DATABASE_URL from os.getenv at settings load: {os.getenv('DATABASE_URL')}")
if DATABASES['default']['NAME'] != 'defaultdb_pleasesetenv':
    print(f"Final DB Config: Name='{DATABASES['default']['NAME']}', User='{DATABASES['default']['USER']}', Host='{DATABASES['default']['HOST']}', Port='{DATABASES['default']['PORT']}'")
else:
    print("CRITICAL WARNING: Database is using fallback default. DATABASE_URL not properly set or read.")
print("--- End of Django Settings ---")


# ... other settings ...

LOGIN_URL = 'login'  # This is the name of the URL pattern for the login page (provided by django.contrib.auth.urls)
LOGIN_REDIRECT_URL = 'core:dashboard'  # After successful login, redirect to the dashboard
LOGOUT_REDIRECT_URL = 'core:landing_page' # After logout, redirect to the landing page
