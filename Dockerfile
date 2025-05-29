# Dockerfile (Production Ready)

# --- Builder Stage ---
# This stage installs build dependencies, Python packages, copies app code,
# and collects static files.
FROM python:3.13-slim-bookworm AS builder

# Set environment variables to prevent Python from writing .pyc files to disc and to buffer output
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
# It's good practice to set DJANGO_SETTINGS_MODULE here too if any manage.py commands need it
ENV DJANGO_SETTINGS_MODULE=infiniti.settings

WORKDIR /app

# Install build-time system dependencies (for compiling Python packages)
# and core runtime dependencies that might be needed by Python packages during installation.
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
       build-essential \
       libpq-dev \
       libjpeg-dev \
       zlib1g-dev \
       gettext \
       bash \
       # postgresql-client is useful for manage.py dbshell or custom scripts,
       # but not strictly required if only psycopg2 is used by the app.
       # If included, ensure libpq5 is in the final stage.
       postgresql-client \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements.txt and install Python dependencies
# These will be installed into the system Python of this builder stage.
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Copy the entire application source code
# Ensure you have a .dockerignore file to exclude unnecessary files/folders
# (e.g., .git, .venv, __pycache__, local .env files, IDE folders)
COPY . .

# Collect static files
# This will gather static files into the directory specified by STATIC_ROOT in settings.py
# (which should be something like /app/staticfiles).
RUN python manage.py collectstatic --noinput --clear


# --- Final Runtime Stage ---
# This stage builds the final, smaller image with only runtime necessities.
FROM python:3.13-slim-bookworm AS final

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV DJANGO_SETTINGS_MODULE=infiniti.settings
ENV PYTHONIOENCODING=UTF-8

WORKDIR /app

# Install only essential runtime system dependencies
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
       libpq5 \
       gettext \
       bash \
       # Add other minimal runtime dependencies if absolutely necessary
       # e.g., libjpeg (libjpeg62-turbo) if Pillow needs it and it's not statically linked
       # Usually, Python wheels handle this, or they were linked in the builder stage.
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Create a non-root user and group for security
RUN groupadd -r appgroup --gid 1001 && \
    useradd --no-log-init -r -g appgroup --uid 1001 -d /app -s /bin/bash appuser

# Copy installed Python packages from the builder stage
COPY --from=builder /usr/local/lib/python3.13/site-packages /usr/local/lib/python3.13/site-packages
# Copy executables installed by pip (like gunicorn) from the builder stage
COPY --from=builder /usr/local/bin /usr/local/bin

# Copy the application code (which now includes collected static files) from the builder stage
COPY --from=builder /app /app

# Create mediafiles directory if it doesn't exist and ensure appuser owns app directories
# staticfiles directory should have been created by collectstatic and copied from builder.
RUN mkdir -p /app/mediafiles && \
    chown -R appuser:appgroup /app

# Switch to the non-root user
USER appuser

# Expose the port Gunicorn will run on
EXPOSE 8000

# Command to run the application using Gunicorn
# Adjust --workers based on your server's CPU cores (typically 2-4 workers per core)
# For a typical small server, 2-4 workers might be a good start.
# Ensure infiniti.wsgi:application points to your WSGI application object.
CMD ["gunicorn", "--workers", "3", "--bind", "0.0.0.0:8000", "infiniti.wsgi:application"]
