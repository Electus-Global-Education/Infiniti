# fund_finder/tasks.py
from celery import shared_task
from django.core.management import call_command
import os

@shared_task(bind=True)
def process_grant_file_task(self, file_path: str, original_filename: str):
    """
    A Celery task to process an uploaded grant data file (CSV or XML).
    This runs asynchronously in a Celery worker to avoid blocking the web request.
    """
    command_to_run = ''
    if original_filename.endswith('.csv'):
        command_to_run = 'import_grants_from_csv'
    elif original_filename.endswith('.xml'):
        command_to_run = 'import_grants_from_xml'

    if command_to_run:
        try:
            print(f"CELERY TASK STARTING: Running {command_to_run} on {file_path}")
            # The output of call_command will now appear in the Celery worker's logs,
            # not the Django web server's logs.
            call_command(command_to_run, file_path)
            print(f"CELERY TASK FINISHED SUCCESSFULLY for {original_filename}")
        except Exception as e:
            print(f"CELERY TASK FAILED for {original_filename}: {e}")
        finally:
            # Clean up the temporary file after processing is complete
            if os.path.exists(file_path):
                os.remove(file_path)
                print(f"Cleaned up temporary file: {file_path}")
    else:
        print(f"Celery task: No command to run for file {original_filename}")
        if os.path.exists(file_path):
            os.remove(file_path)
