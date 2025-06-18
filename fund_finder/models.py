# fund_finder/models.py
from django.db import models
from core.models import AuditableModel, Organization, User
import uuid


class FunderType(AuditableModel):
    # ... (content remains the same, not shown for brevity)
    name = models.CharField(max_length=100, help_text="Name of the funder type.")
    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, null=True, blank=True, related_name='funder_types')
    is_active = models.BooleanField(default=True, help_text="Is this funder type available for use?")
    def __str__(self): return f"{self.name} ({self.organization.name})" if self.organization else f"{self.name} (System)"
    class Meta(AuditableModel.Meta):
        verbose_name = "Funder Type"; verbose_name_plural = "Funder Types"; ordering = ['organization__name', 'name']; unique_together = [['organization', 'name']]

class FunderProfile(AuditableModel):
    # ... (content remains the same, not shown for brevity)
    name = models.CharField(max_length=255, unique=True, help_text="Official name of the funding organization.")
    agency_code = models.CharField(max_length=50, blank=True, null=True)
    description = models.TextField(blank=True, null=True)
    website = models.URLField(blank=True, null=True)
    funder_type = models.ForeignKey(FunderType, on_delete=models.PROTECT, null=True, blank=True, related_name='funders')
    contact_info = models.TextField(blank=True, null=True)
    geographic_focus = models.CharField(max_length=255, blank=True)
    program_areas = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, null=True, blank=True, related_name='funder_profiles')
    def __str__(self): return self.name
    class Meta(AuditableModel.Meta):
        verbose_name = "Funder Profile"; verbose_name_plural = "Funder Profiles"; ordering = ['name']

class GrantOpportunity(AuditableModel):
    
    INDEXING_STATUS_CHOICES = [
        ('PENDING',  'Pending'),
        ('INDEXING', 'Indexing'),
        ('SUCCESS',  'Success'),
        ('FAILED',   'Failed'),
    ]
    indexing_status = models.CharField(
        max_length=10,
        choices=INDEXING_STATUS_CHOICES,
        default='PENDING',
        db_index=True,
        help_text="Vector-store ingestion status: Pending → Indexing → Success/Failed"
    )
    STATUS_CHOICES = [('POSTED', 'Posted'), ('FORECASTED', 'Forecasted'), ('CLOSED', 'Closed'), ('ARCHIVED', 'Archived')]
    COST_SHARING_CHOICES = [('Yes', 'Yes'), ('No', 'No'), ('Not Specified', 'Not Specified')]
    
    funder = models.ForeignKey(FunderProfile, on_delete=models.PROTECT, related_name='grant_opportunities')
    title = models.CharField(max_length=255)
    description = models.TextField(help_text="Full funding description of the grant.")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='POSTED')
    
    source_name = models.CharField(max_length=50, default='MANUAL')
    source_id = models.CharField(max_length=100, null=True, blank=True)
    source_url = models.URLField(blank=True, null=True)
    version = models.CharField(max_length=50, blank=True, null=True)

    estimated_total_funding = models.DecimalField(max_digits=15, decimal_places=2, null=True, blank=True)
    award_floor = models.DecimalField(max_digits=15, decimal_places=2, null=True, blank=True)
    award_ceiling = models.DecimalField(max_digits=15, decimal_places=2, null=True, blank=True)
    expected_number_of_awards = models.PositiveIntegerField(null=True, blank=True)
    cost_sharing_requirement = models.CharField(max_length=20, choices=COST_SHARING_CHOICES, default='Not Specified')
    
    # --- CORRECTED FIELDS TO ALLOW NULLS ---
    funding_instrument_type = models.CharField(max_length=255, blank=True, null=True) # Allow null
    funding_activity_category = models.CharField(max_length=255, blank=True, null=True) # Allow null
    assistance_listings = models.CharField(max_length=255, blank=True, null=True) # Allow null
    
    posted_date = models.DateTimeField(null=True, blank=True)
    close_date = models.DateTimeField(null=True, blank=True)
    last_updated_date = models.DateTimeField(null=True, blank=True)
    
    is_active = models.BooleanField(default=True)
    eligibility_criteria_text = models.TextField(blank=True, null=True)
    tags = models.TextField(blank=True, help_text="Comma-separated keywords for this grant.")
    
    def __str__(self): return self.title
    class Meta(AuditableModel.Meta):
        verbose_name = "Grant Opportunity"; verbose_name_plural = "Grant Opportunities"; ordering = ['-close_date', '-posted_date', 'title']; unique_together = [['source_name', 'source_id']]

class DataImportLog(AuditableModel):
    """
    Tracks the status and results of asynchronous data import tasks (e.g., from CSV/XML).
    """
    STATUS_CHOICES = [('PENDING', 'Pending'), ('PROCESSING', 'Processing'), ('COMPLETED', 'Completed'), ('FAILED', 'Failed'), ('CANCELED', 'Canceled')]
    
    original_filename = models.CharField(max_length=255)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='PENDING')
    task_id = models.CharField(max_length=255, null=True, blank=True, help_text="Celery task ID for this import.")
    
    # Statistics
    records_processed = models.PositiveIntegerField(default=0)
    records_created = models.PositiveIntegerField(default=0)
    records_updated = models.PositiveIntegerField(default=0)
    records_failed = models.PositiveIntegerField(default=0)
    
    log_output = models.TextField(blank=True, null=True, help_text="Detailed log of successes and failures during the import.")
    
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    # Note: 'id', 'created_at', 'updated_at', 'created_by', 'updated_by' are inherited from AuditableModel
    
    def __str__(self):
        return f"Import of '{self.original_filename}' - {self.status}"
    
    class Meta(AuditableModel.Meta):
        verbose_name = "Data Import Log"
        verbose_name_plural = "Data Import Logs"
