# fund_finder/models.py
from django.db import models
from core.models import AuditableModel, Organization, User
import uuid

class FunderType(AuditableModel):
    """
    Represents a category for funders (e.g., "Federal Government", "Private Foundation", "Corporate CSR").
    """
    name = models.CharField(max_length=100, help_text="Name of the funder type (e.g., Private Foundation).")
    organization = models.ForeignKey(
        Organization,
        on_delete=models.CASCADE,
        null=True, blank=True, # Null for system-wide types
        related_name='funder_types',
        help_text="The organization that created and can use this type. Null for system-level types."
    )
    is_active = models.BooleanField(default=True, help_text="Is this funder type available for use?")
    
    def __str__(self):
        if self.organization:
            return f"{self.name} ({self.organization.name})"
        return f"{self.name} (System)"

    class Meta(AuditableModel.Meta):
        verbose_name = "Funder Type"
        verbose_name_plural = "Funder Types"
        ordering = ['organization__name', 'name']
        unique_together = [['organization', 'name']]


class FunderProfile(AuditableModel):
    """
    Represents a funding organization (e.g., Ford Foundation, Google.org).
    """
    name = models.CharField(max_length=255, unique=True, help_text="Official name of the funding organization.")
    agency_code = models.CharField(max_length=50, blank=True, null=True, help_text="Agency code, e.g., 'DOL-ETA' from Grants.gov.")
    description = models.TextField(blank=True, null=True, help_text="A brief description of the funder's mission and history.")
    website = models.URLField(blank=True, null=True)
    funder_type = models.ForeignKey(
        FunderType,
        on_delete=models.PROTECT,
        null=True, blank=True,
        related_name='funders'
    )
    contact_info = models.TextField(blank=True, null=True, help_text="Contact person, phone, or email for the funder.")
    geographic_focus = models.CharField(max_length=255, blank=True, help_text="e.g., National, State of California, Local (Urban)")
    program_areas = models.TextField(blank=True, help_text="Comma-separated list of focus areas (e.g., STEM, Arts, Financial Literacy)")
    is_active = models.BooleanField(default=True, help_text="Is this funder profile currently active and visible?")
    organization = models.ForeignKey(
        Organization,
        on_delete=models.CASCADE,
        null=True, blank=True, # Null for system-wide/global funders
        related_name='funder_profiles',
        help_text="The organization that entered this funder profile. Null for global funders."
    )

    def __str__(self):
        return self.name

    class Meta(AuditableModel.Meta):
        verbose_name = "Funder Profile"
        verbose_name_plural = "Funder Profiles"
        ordering = ['name']


class GrantOpportunity(AuditableModel):
    """
    Represents a specific grant or funding opportunity from a Funder.
    """
    STATUS_CHOICES = [('POSTED', 'Posted'), ('FORECASTED', 'Forecasted'), ('CLOSED', 'Closed'), ('ARCHIVED', 'Archived')]
    COST_SHARING_CHOICES = [('Yes', 'Yes'), ('No', 'No'), ('Not Specified', 'Not Specified')]
    
    funder = models.ForeignKey(FunderProfile, on_delete=models.PROTECT, related_name='grant_opportunities')
    title = models.CharField(max_length=255)
    description = models.TextField(help_text="Full funding description of the grant.")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='POSTED')
    
    source_name = models.CharField(max_length=50, default='MANUAL')
    source_id = models.CharField(max_length=100, null=True, blank=True, help_text="The unique opportunity number/ID from the source.")
    source_url = models.URLField(blank=True, null=True)
    version = models.CharField(max_length=50, blank=True, null=True, help_text="Version from the source, e.g., 'Synopsis 1'.")

    estimated_total_funding = models.DecimalField(max_digits=15, decimal_places=2, null=True, blank=True)
    award_floor = models.DecimalField(max_digits=15, decimal_places=2, null=True, blank=True)
    award_ceiling = models.DecimalField(max_digits=15, decimal_places=2, null=True, blank=True)
    expected_number_of_awards = models.PositiveIntegerField(null=True, blank=True)
    cost_sharing_requirement = models.CharField(max_length=20, choices=COST_SHARING_CHOICES, default='Not Specified')
    
    funding_instrument_type = models.CharField(max_length=255, blank=True, null=True)
    funding_activity_category = models.CharField(max_length=255, blank=True, null=True)
    assistance_listings = models.CharField(max_length=255, blank=True, null=True)
    
    posted_date = models.DateTimeField(null=True, blank=True)
    close_date = models.DateTimeField(null=True, blank=True)
    last_updated_date = models.DateTimeField(null=True, blank=True)
    
    is_active = models.BooleanField(default=True, help_text="Is this grant opportunity considered active in our system?")
    eligibility_criteria_text = models.TextField(blank=True, null=True, help_text="Specific eligibility requirements for applicants.")
    tags = models.TextField(blank=True, help_text="Comma-separated keywords for this grant (e.g., youth, STEM, at-risk).")
    
    def __str__(self):
        return self.title

    class Meta(AuditableModel.Meta):
        verbose_name = "Grant Opportunity"
        verbose_name_plural = "Grant Opportunities"
        ordering = ['-close_date', '-posted_date', 'title']
        unique_together = [['source_name', 'source_id']]
