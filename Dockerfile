# Dockerfile
# Use an official Python runtime based on Debian (e.g., slim-buster or slim-bullseye)
FROM python:3.11-slim-bullseye # Bullseye is a newer Debian version than Buster

# Set environment variables to prevent Python from writing .pyc files to disc and to buffer output
ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1

# Set the working directory in the container
WORKDIR /app

# Install system dependencies using apt-get
# - postgresql-client: for Django to connect to PostgreSQL (e.g., for `psql` or `pg_isready`)
# - build-essential, libpq-dev: might be needed if psycopg2-binary isn't used or has issues,
#   or for other packages that need C extensions.
# - libjpeg-dev, zlib1g-dev: examples if you were using Pillow for image processing
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
       bash \ # Good to have for shell access and some scripts
       postgresql-client \
       # Add other system dependencies as needed, for example:
       # build-essential \
       # libpq-dev \
       # libjpeg-dev \
       # zlib1g-dev \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Create a non-root user and group for security
# Using standard Debian commands
RUN groupadd -r appgroup && useradd --no-log-init -r -g appgroup -d /app -s /bin/bash appuser
# The /app directory will be created by WORKDIR.

# Copy only requirements.txt first to leverage Docker cache for dependencies
COPY requirements.txt /app/

# Install Python dependencies
# Ensure permissions are correct if running pip as root and then switching user.
# Alternatively, create user first, then copy files and run pip as that user.
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the application code into the container
# This will be largely overridden by the volume mount in docker-compose.yml for development,
# but it's good practice for building standalone images.
COPY . /app/

# Change ownership of the app directory to the appuser
# This is important if you are not mounting a volume from the host that overrides these permissions.
RUN chown -R appuser:appgroup /app

# Switch to the non-root user for running the application
USER appuser

# Expose the port Gunicorn will run on (default for Django dev server is also 8000)
EXPOSE 8000

# Default command to run the application.
# For development, we'll override this in docker-compose.yml to use Django's runserver.
# For production, you'd use Gunicorn here.
# CMD ["gunicorn", "--bind", "0.0.0.0:8000", "infiniti.wsgi:application"]
# For now, let's make it run the dev server if no command is specified in docker-compose.
# Replace 'your_project_name' with your actual Django project name.
CMD ["python", "manage.py", "runserver", "0.0.0.0:8000"]
