# fund_finder/management/commands/bulk_index_grants.py
from django.core.management.base import BaseCommand, CommandError
from django.db.models import Q
from fund_finder.models import GrantOpportunity
from fund_finder.tasks import index_grant_opportunity_task

class Command(BaseCommand):
    """
    Django management command to bulk-index existing GrantOpportunity records
    into the vector database using Celery.
    
    This is useful for initial data population or for re-indexing all grants
    after a change in the indexing logic. It iterates through grants in batches
    to avoid loading all records into memory at once.
    """
    help = 'Queues all active grant opportunities for RAG indexing.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--batch-size',
            type=int,
            help='The number of grants to process in each batch.',
            default=1000
        )
        parser.add_argument(
            '--reindex-all',
            action='store_true',
            help='Force re-indexing of all grants, not just active ones.'
        )

    def handle(self, *args, **options):
        batch_size = options['batch_size']
        reindex_all = options['reindex_all']

        self.stdout.write(self.style.SUCCESS("Starting bulk indexing of grant opportunities..."))

        if reindex_all:
            queryset = GrantOpportunity.objects.all()
            self.stdout.write(self.style.WARNING("Re-indexing ALL grants, including inactive ones."))
        else:
            queryset = GrantOpportunity.objects.filter(is_active=True)
            self.stdout.write("Indexing only ACTIVE grants.")
            
        total_grants = queryset.count()
        if total_grants == 0:
            self.stdout.write(self.style.WARNING("No grant opportunities found to index."))
            return

        self.stdout.write(f"Found {total_grants} grants to queue for indexing in batches of {batch_size}.")

        # Use iterator() to process in chunks and conserve memory
        for grant in queryset.iterator(chunk_size=batch_size):
            try:
                # Launch the same asynchronous task that the signal uses
                index_grant_opportunity_task.delay(str(grant.id))
            except Exception as e:
                self.stderr.write(self.style.ERROR(f"Failed to queue indexing task for grant ID {grant.id}: {e}"))
        
        self.stdout.write(self.style.SUCCESS(f"Successfully queued all {total_grants} grants for indexing."))
        self.stdout.write("You can now monitor your Celery worker logs for progress.")
