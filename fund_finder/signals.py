# fund_finder/signals.py
from django.db.models.signals import post_save
from django.dispatch import receiver
from .models import GrantOpportunity
from .tasks import index_grant_opportunity_task

@receiver(post_save, sender=GrantOpportunity)
def schedule_grant_opportunity_indexing(sender, instance, created, **kwargs):
    """
    A signal receiver that triggers an asynchronous Celery task to index
    a GrantOpportunity whenever it is created or updated.
    """
    if instance.is_active:
        print(f"Signal received: GrantOpportunity '{instance.title}' was saved. Scheduling for indexing.")
        # We launch the task with a short delay to ensure the database transaction has committed.
        index_grant_opportunity_task.apply_async(args=[str(instance.id)], countdown=5)
    else:
        # Optional: If a grant is made inactive, you might want to trigger a task to remove it from the index.
        # from .tasks import deindex_grant_opportunity_task
        # deindex_grant_opportunity_task.delay(str(instance.id))
        print(f"Signal received: GrantOpportunity '{instance.title}' is inactive. Skipping indexing.")

