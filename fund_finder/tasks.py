# fund_finder/tasks.py
from celery import shared_task
from django.core.management import call_command
import os

@shared_task(bind=True)
def process_grant_file_task(self, file_path: str, original_filename: str):
    """
    A Celery task to process an uploaded grant data file (CSV or XML).
    This runs asynchronously to avoid blocking the web request.
    """
    command_to_run = ''
    if original_filename.endswith('.csv'):
        command_to_run = 'import_grants_from_csv'
    elif original_filename.endswith('.xml'):
        command_to_run = 'import_grants_from_xml'

    if command_to_run:
        try:
            print(f"Celery task starting: Running {command_to_run} on {file_path}")
            # Note: The output of call_command won't be sent back to the user in this async model.
            # It will appear in the Celery worker's logs.
            # For more advanced feedback, you would store the result in the database.
            call_command(command_to_run, file_path)
            print(f"Celery task finished successfully for {original_filename}")
        except Exception as e:
            print(f"Celery task failed for {original_filename}: {e}")
        finally:
            # Clean up the temporary file after processing
            if os.path.exists(file_path):
                os.remove(file_path)
                print(f"Cleaned up temporary file: {file_path}")
    else:
        print(f"Celery task: No command to run for file {original_filename}")
        if os.path.exists(file_path):
            os.remove(file_path)
