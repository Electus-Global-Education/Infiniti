# Dockerfile (Simpler Single-Stage for GCP Deployment)

# Use an official Python runtime based on Debian Bookworm
FROM python:3.13-slim-bookworm

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV DJANGO_SETTINGS_MODULE=infiniti.settings
ENV PYTHONIOENCODING=UTF-8

# Set the working directory in the container
WORKDIR /app

# Install system dependencies
# Includes build tools and runtime libraries needed by Django and common packages.
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
       bash \
       build-essential \
       libpq-dev \
       libjpeg-dev \
       zlib1g-dev \
       gettext \
       postgresql-client \
       ffmpeg \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Create a non-root user and group for security
# RUN groupadd -r appgroup --gid 1001 && \
#     useradd --no-log-init -r -g appgroup --uid 1001 -d /app -s /bin/bash appuser
ARG APP_USER_UID=1000
ARG APP_GROUP_GID=1000
RUN groupadd -r appgroup --gid ${APP_GROUP_GID} && \
    useradd --no-log-init -r -g appgroup --uid ${APP_USER_UID} -d /app -s /bin/bash appuser

# Copy requirements.txt first to leverage Docker cache for this layer if requirements don't change
COPY requirements.txt ./

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the application code into the container
# Ensure you have a .dockerignore file to exclude unnecessary files/folders
# (e.g., .git, .venv, __pycache__, local .env files, IDE folders)
COPY . .

# Collect static files
# This command needs to run as a user who can write to STATIC_ROOT.
# If STATIC_ROOT is within /app, and /app is owned by root before this,
# it might fail. We'll chown /app to appuser before collectstatic.
# Alternatively, run collectstatic before chown, then chown everything.
# For simplicity here, we chown first then run collectstatic as appuser.

# Create mediafiles and staticfiles directories if they don't exist from COPY . .
# and ensure appuser owns the /app directory and its contents.
RUN mkdir -p /app/staticfiles /app/mediafiles && \
    chown -R appuser:appgroup /app

# Switch to the non-root user
USER appuser

# Expose the port Gunicorn will run on
EXPOSE 8000

# Command to run the application using Gunicorn
# Adjust --workers based on your server's CPU cores (typically 2-4 workers per core)
CMD ["gunicorn", "--workers", "8", "--bind", "0.0.0.0:8000", "infiniti.wsgi:application"]
