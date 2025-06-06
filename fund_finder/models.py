# fund_finder/models.py
from django.db import models
from core.models import AuditableModel # Import the centralized AuditableModel from core app
import uuid

class FunderProfile(AuditableModel):
    """
    Represents a funding organization (e.g., foundation, corporation, government agency).
    This is a global resource.
    """
    name = models.CharField(max_length=255, unique=True, help_text="Official name of the funding organization.")
    description = models.TextField(blank=True, null=True, help_text="A brief description of the funder's mission and history.")
    website = models.URLField(blank=True, null=True)
    funder_type = models.CharField(max_length=50, blank=True, null=True, help_text="e.g., Foundation, Corporate, Government")
    
    def __str__(self):
        return self.name

    class Meta(AuditableModel.Meta):
        verbose_name = "Funder Profile"
        verbose_name_plural = "Funder Profiles"
        ordering = ['name']


class GrantOpportunity(AuditableModel):
    """
    Represents a specific grant or funding opportunity from a Funder.
    This is a global resource that organizations will be matched against.
    """
    SOURCE_CHOICES = [
        ('GRANTS_GOV', 'Grants.gov'),
        ('MANUAL', 'Manual Entry'),
        ('XML_UPLOAD', 'XML Upload'),
        # Add other sources as you integrate them
    ]
    
    funder = models.ForeignKey(
        FunderProfile,
        on_delete=models.PROTECT, # Prevent deleting a funder if grants are linked
        related_name='grant_opportunities',
        help_text="The funding organization offering this grant."
    )
    title = models.CharField(max_length=255, help_text="The official title of the grant.")
    description = models.TextField(help_text="Detailed description of the grant, its goals, and eligibility criteria.")
    
    # --- Source Information ---
    source_name = models.CharField(max_length=50, choices=SOURCE_CHOICES, default='MANUAL', help_text="The original source of this grant data.")
    source_id = models.CharField(max_length=100, null=True, blank=True, help_text="The unique identifier from the original source (e.g., opportunityId from Grants.gov).")

    # --- Key Details ---
    min_amount = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    max_amount = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    application_deadline = models.DateTimeField(null=True, blank=True)
    eligibility_criteria = models.TextField(blank=True, null=True, help_text="Specific eligibility requirements for applicants.")
    
    is_active = models.BooleanField(default=True, help_text="Is this grant currently open for applications?")
    source_url = models.URLField(blank=True, null=True, help_text="Direct URL to the grant application or information page.")
    
    def __str__(self):
        return f"{self.title} ({self.funder.name})"

    class Meta(AuditableModel.Meta):
        verbose_name = "Grant Opportunity"
        verbose_name_plural = "Grant Opportunities"
        ordering = ['-application_deadline', 'title']
        # Ensure that grants from the same source have a unique ID
        unique_together = [['source_name', 'source_id']]
