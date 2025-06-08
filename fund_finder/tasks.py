# fund_finder/tasks.py
from celery import shared_task
from django.core.management import call_command
import os

@shared_task(bind=True)
def process_grant_file_task(self, file_path: str, original_filename: str, log_id: str):
    # ... (existing code for this task) ...
    pass

@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def index_grant_opportunity_task(self, grant_id: str):
    """
    Asynchronous task to index a single GrantOpportunity into the vector database
    and update its status in the PostgreSQL database.
    """
    from .models import GrantOpportunity
    try:
        from baserag.services import index_document
    except ImportError:
        def index_document(document_id, text, metadata):
            print(f"DUMMY INDEXING: doc_id '{document_id}'")
            return True

    try:
        grant = GrantOpportunity.objects.get(id=grant_id)
        # Mark as 'INDEXING' to prevent duplicate processing
        grant.indexing_status = 'INDEXING'
        grant.save(update_fields=['indexing_status'])

        # Prepare text and metadata
        document_text = f"Title: {grant.title}\n\nDescription: {grant.description}\n\nEligibility: {grant.eligibility_criteria_text}"
        metadata = {
            'doc_type': 'grant_opportunity',
            'grant_id': str(grant.id),
            'funder_id': str(grant.funder.id),
        }
        
        # Call your centralized RAG indexing service
        success = index_document(document_id=str(grant.id), text=document_text, metadata=metadata)
        
        if success:
            grant.indexing_status = 'SUCCESS'
            print(f"Successfully indexed grant: {grant.title} (ID: {grant.id})")
        else:
            grant.indexing_status = 'FAILED'
            print(f"Failed to index grant: {grant.title} (ID: {grant.id})")
        
        grant.save(update_fields=['indexing_status'])

    except GrantOpportunity.DoesNotExist:
        print(f"Error: GrantOpportunity with ID {grant_id} not found for indexing.")
    except Exception as e:
        # If any error occurs, mark the grant as failed and retry the task
        GrantOpportunity.objects.filter(id=grant_id).update(indexing_status='FAILED')
        print(f"An unexpected error occurred during grant indexing for ID {grant_id}: {e}")
        self.retry(exc=e)
