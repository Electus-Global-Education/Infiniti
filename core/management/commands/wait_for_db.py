# your_django_app/management/commands/wait_for_db.py
# Create this file structure:
# your_project_root/
#  ├── your_django_app_name/  <-- This is one of your Django apps
#  │   ├── __init__.py
#  │   ├── management/
#  │   │   ├── __init__.py
#  │   │   └── commands/
#  │   │       ├── __init__.py
#  │   │       └── wait_for_db.py
#  │   ├── apps.py
#  │   ├── models.py
#  │   └── ...
#  ├── your_project_name/     <-- This is your Django project directory (contains settings.py)
#  │   ├── __init__.py
#  │   ├── settings.py
#  │   ├── urls.py
#  │   └── wsgi.py
#  └── manage.py

import time
import os
from django.core.management.base import BaseCommand
from django.db import connections
from django.db.utils import OperationalError

class Command(BaseCommand):
    """Django command to pause execution until database is available"""

    def handle(self, *args, **options):
        self.stdout.write(self.style.WARNING("Waiting for database..."))
        db_conn = None
        
        # Get retry parameters from environment variables or use defaults
        max_retries = int(os.getenv('DB_MAX_RETRIES', 15))
        retry_delay = int(os.getenv('DB_RETRY_DELAY', 5)) # seconds

        retries = 0
        while retries < max_retries:
            try:
                # Attempt to get the default database connection
                db_conn = connections['default']
                # Try to establish a connection by getting a cursor
                db_conn.cursor()
                self.stdout.write(self.style.SUCCESS("Database available!"))
                break  # Exit the loop if connection is successful
            except OperationalError:
                retries += 1
                self.stdout.write(
                    f"Database unavailable, waiting {retry_delay} seconds... "
                    f"(Attempt {retries}/{max_retries})"
                )
                time.sleep(retry_delay)
            except Exception as e:
                # Catch any other unexpected errors during connection attempt
                retries += 1
                self.stdout.write(self.style.ERROR(f"An unexpected error occurred: {e}. Retrying..."))
                time.sleep(retry_delay)
        
        if retries == max_retries:
            self.stdout.write(self.style.ERROR("Database connection failed after multiple retries. Exiting."))
            exit(1) # Exit with an error code if DB is not available after all retries
