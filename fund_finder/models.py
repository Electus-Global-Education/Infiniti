# fund_finder/models.py
from django.db import models
from core.models import AuditableModel, Organization # Import from core app
import uuid

class FunderType(AuditableModel):
    """
    Represents a category for funders (e.g., "Federal Government", "Private Foundation", "Corporate CSR").
    Can be system-wide (organization=None) or specific to an organization.
    """
    name = models.CharField(max_length=100, help_text="Name of the funder type (e.g., Private Foundation).")
    organization = models.ForeignKey(
        Organization,
        on_delete=models.CASCADE,
        null=True, blank=True, # Null for system-wide types
        related_name='funder_types',
        help_text="The organization that created and can use this type. Null for system-level types."
    )
    
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
    Can be system-wide (global) or specific to an organization's view.
    """
    name = models.CharField(max_length=255, unique=True, help_text="Official name of the funding organization.")
    description = models.TextField(blank=True, null=True, help_text="A brief description of the funder's mission and history.")
    website = models.URLField(blank=True, null=True)
    
    funder_type = models.ForeignKey(
        FunderType,
        on_delete=models.PROTECT, # Don't delete a type if it's in use
        null=True, blank=True,
        related_name='funders'
    )
    
    geographic_focus = models.CharField(max_length=255, blank=True, help_text="e.g., National, State of California, Local (Urban)")
    program_areas = models.TextField(blank=True, help_text="Comma-separated list of focus areas (e.g., STEM, Arts, Financial Literacy)")
    past_funding_notes = models.TextField(blank=True, null=True, help_text="Notes on past funding history or priorities.")
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
    SOURCE_CHOICES = [
        ('GRANTS_GOV', 'Grants.gov'),
        ('MANUAL', 'Manual Entry'),
        ('XML_UPLOAD', 'XML Upload'),
    ]
    
    funder = models.ForeignKey(
        FunderProfile,
        on_delete=models.PROTECT,
        related_name='grant_opportunities',
        help_text="The funding organization offering this grant."
    )
    title = models.CharField(max_length=255, help_text="The official title of the grant.")
    description = models.TextField(help_text="Detailed description of the grant, its goals, and eligibility criteria.")
    
    # --- Source Information ---
    source_name = models.CharField(max_length=50, choices=SOURCE_CHOICES, default='MANUAL', help_text="The original source of this grant data.")
    source_id = models.CharField(max_length=100, null=True, blank=True, help_text="The unique identifier from the source (e.g., opportunityId from Grants.gov).")
    source_url = models.URLField(blank=True, null=True, help_text="Direct URL to the grant application or information page.")

    # --- Key Details (Improved) ---
    min_amount = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    max_amount = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    application_deadline = models.DateTimeField(null=True, blank=True)
    
    funding_instrument_type = models.CharField(max_length=100, blank=True, help_text="e.g., Grant, Cooperative Agreement, Loan.")
    funding_activity_category = models.CharField(max_length=255, blank=True, help_text="e.g., Education, Health, Community Development.")
    
    eligibility_criteria_text = models.TextField(blank=True, null=True, help_text="Specific eligibility requirements for applicants.")
    # You could later expand eligibility with ManyToManyFields to specific applicant types
    
    is_active = models.BooleanField(default=True, help_text="Is this grant currently open for applications?")
    
    # Keywords/Tags for better filtering and matching
    tags = models.TextField(blank=True, help_text="Comma-separated keywords for this grant (e.g., youth, STEM, at-risk).")

    def __str__(self):
        return f"{self.title} ({self.funder.name})"

    class Meta(AuditableModel.Meta):
        verbose_name = "Grant Opportunity"
        verbose_name_plural = "Grant Opportunities"
        ordering = ['-application_deadline', 'title']
        unique_together = [['source_name', 'source_id']]
