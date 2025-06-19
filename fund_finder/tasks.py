# fund_finder/tasks.py
from celery import shared_task
from django.core.management import call_command
import os
from langchain.text_splitter import RecursiveCharacterTextSplitter
from baserag.connection import embedding_model, vector_store
from .models import GrantOpportunity

@shared_task(bind=True)
def process_grant_file_task(self, file_path: str, original_filename: str, import_log_id: str = None):
    """
    A Celery task to process an uploaded grant data file (CSV or XML).
    This runs asynchronously to avoid blocking the web request.
    """
    # if provided, attach the Celery task ID to the import log
    if import_log_id:
        from .models import DataImportLog
        try:
            log = DataImportLog.objects.get(id=import_log_id)
            log.task_id = self.request.id
            log.status = 'PROCESSING'
            log.save(update_fields=['task_id','status'])
        except DataImportLog.DoesNotExist:
            pass
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
            
@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def index_grant_opportunity_task(self, grant_id: str):
    """
    Async Celery task to chunk, embed, and upsert a single GrantOpportunity
    into the vector store, then update its indexing_status.

    Retries up to 3 times on errors, with a 60s delay between attempts.
    """
    try:
        # 1. Mark as INDEXING via update() to avoid post_save signals
        GrantOpportunity.objects.filter(id=grant_id).update(indexing_status='INDEXING')
        print(f"[Celery] Grant {grant_id} indexing_status set to INDEXING")

        # 2. Fetch the freshly updated object
        grant = GrantOpportunity.objects.get(id=grant_id)

        # 2. Build the full text and base metadata
        document_text = (
            f"Title: {grant.title}\n\n"
            f"Description: {grant.description}\n\n"
            f"Eligibility: {grant.eligibility_criteria_text}"
        )
        base_meta = {
            'doc_type': 'grant_opportunity',
            'grant_id': str(grant.id),
            'funder_id': str(grant.funder.id),
            'title': grant.title,
            #'description': grant.description,
            'eligibility_criteria': grant.eligibility_criteria_text,
            'funder_name': grant.funder.name,
        }

        # 3. Chunk the document
        splitter = RecursiveCharacterTextSplitter(
            chunk_size=1000,
            chunk_overlap=100,
            separators=["\n\n", "\n", ".", "!", "?", " "],
        )
        chunks = splitter.split_text(document_text)

        # 4. Generate embeddings for each chunk
        embeddings = embedding_model.embed_documents(chunks)

        # 5. Add embeddings into the VertexAI vector store
        ids       = [f"{grant.id}-{i}" for i in range(len(chunks))]
        metadatas = [
            {**base_meta, 'chunk_index': i}
            for i in range(len(chunks))
        ]
        # use add_texts_with_embeddings (or add_texts) rather than upsert
        vector_store.add_texts_with_embeddings(
            texts=chunks,
            embeddings=embeddings,
            metadatas=metadatas,
            ids=ids
        )
        # confirmation print right after insertion
        print(f"[Celery] Added {len(chunks)} chunks to vector store for grant {grant_id} chunks added in vector store.")
        # 6. Mark success
        # grant.indexing_status = 'SUCCESS'
        # grant.save(update_fields=['indexing_status'])
        # print(f"[Celery] Indexed {len(chunks)} chunks for grant {grant.id}")
        # 6. Mark success without firing post_save
        GrantOpportunity.objects.filter(id=grant_id).update(indexing_status='SUCCESS')
        print(f"[Celery] Indexed {len(chunks)} chunks for grant {grant_id}")

    except GrantOpportunity.DoesNotExist:
        # Grant was deleted or never existed — nothing to retry
        print(f"[Celery] GrantOpportunity {grant_id} not found.")
    except Exception as e:
        # On any other error, mark as FAILED and retry
        GrantOpportunity.objects.filter(id=grant_id) \
                                  .update(indexing_status='FAILED')
        print(f"[Celery] Error indexing grant {grant_id}: {e}")
        raise self.retry(exc=e)