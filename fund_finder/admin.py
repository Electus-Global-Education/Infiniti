# fund_finder/admin.py
from django.contrib import admin
from .models import FunderProfile, GrantOpportunity
from core.admin import AuditableModelAdmin # Import the centralized AuditableModelAdmin from your core app

@admin.register(FunderProfile)
class FunderProfileAdmin(AuditableModelAdmin):
    """
    Admin interface for managing Funder Profiles.
    
    This is a global resource, typically managed by superusers. It inherits
    from AuditableModelAdmin to get automatic audit logging for all changes.
    """
    list_display = ('name', 'funder_type', 'is_active', 'updated_at', 'id')
    search_fields = ('name', 'description', 'id')
    list_filter = ('funder_type', 'is_active', 'created_at')
    
    # readonly_fields are inherited from AuditableModelAdmin, providing a consistent
    # view for auditing fields (id, created_at, updated_at, created_by, updated_by).
    fieldsets = (
        (None, {
            'fields': ('name', 'description', 'website', 'funder_type', 'is_active')
        }),
        ('Auditing', {
            'fields': AuditableModelAdmin.readonly_fields,
            'classes': ('collapse',),
        }),
    )

@admin.register(GrantOpportunity)
class GrantOpportunityAdmin(AuditableModelAdmin):
    """
    Admin interface for managing Grant Opportunities.

    Allows superusers to manually create, edit, and review grant data, including
    data ingested from external sources like Grants.gov. Inherits from
    AuditableModelAdmin for automatic logging of all CRUD operations.
    """
    list_display = ('title', 'funder', 'application_deadline', 'is_active', 'source_name', 'updated_at')
    search_fields = ('title', 'description', 'funder__name', 'source_id', 'id')
    list_filter = ('is_active', 'source_name', 'funder__name', 'application_deadline')
    list_select_related = ('funder',) # Optimizes query for funder name in list display
    date_hierarchy = 'application_deadline' # Adds date-based navigation
    
    fieldsets = (
        ('Grant Information', {
            'fields': ('title', 'funder', 'description', 'is_active')
        }),
        ('Funding Details', {
            'fields': ('min_amount', 'max_amount', 'application_deadline', 'eligibility_criteria')
        }),
        ('Source Information', {
            'fields': ('source_name', 'source_id', 'source_url')
        }),
        ('Auditing', {
            'fields': AuditableModelAdmin.readonly_fields,
            'classes': ('collapse',),
        }),
    )
    # readonly_fields from AuditableModelAdmin are inherited automatically.
