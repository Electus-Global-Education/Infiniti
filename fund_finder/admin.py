# fund_finder/admin.py
from django.contrib import admin
from .models import FunderProfile, GrantOpportunity, FunderType
from core.admin import AuditableModelAdmin # Import the centralized AuditableModelAdmin from your core app
from django.db.models import Q

@admin.register(FunderType)
class FunderTypeAdmin(AuditableModelAdmin):
    """
    Admin interface for managing Funder Types.
    Org Admins can manage their own types, Superusers can manage all.
    """
    list_display = ('name', 'organization_display', 'is_active', 'updated_at')
    search_fields = ('name', 'organization__name')
    list_filter = ('is_active', 'organization__name')

    def organization_display(self, obj):
        return obj.organization.name if obj.organization else "System-Level"
    organization_display.short_description = "Scope"

    def get_queryset(self, request):
        """
        Filters the queryset to show only relevant Funder Types.
        - Superusers see all.
        - Org Admins see system-level types AND types for their own organization.
        """
        qs = super().get_queryset(request)
        if request.user.is_superuser:
            return qs
        if request.user.is_staff and hasattr(request.user, 'organization') and request.user.organization:
            return qs.filter(Q(organization__isnull=True) | Q(organization=request.user.organization))
        return qs.none()

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        """
        Restricts the 'organization' field dropdown for non-superusers.
        """
        if db_field.name == "organization":
            if not request.user.is_superuser and hasattr(request.user, 'organization') and request.user.organization:
                kwargs["queryset"] = request.user.organization.__class__.objects.filter(id=request.user.organization.id)
                kwargs["initial"] = request.user.organization.id
                kwargs["help_text"] = "As an Org Admin, you can only create types for your own organization."
        return super().formfield_for_foreignkey(db_field, request, **kwargs)

@admin.register(FunderProfile)
class FunderProfileAdmin(AuditableModelAdmin):
    list_display = ('name', 'funder_type', 'is_active', 'organization_display', 'updated_at')
    search_fields = ('name', 'description', 'id')
    list_filter = ('is_active', 'funder_type', 'organization__name')
    
    fieldsets = (
        ('Funder Information', {
            'fields': ('name', 'description', 'website', 'funder_type', 'is_active')
        }),
        ('Categorization & Scope', {
            'fields': ('geographic_focus', 'program_areas', 'past_funding_notes', 'organization')
        }),
        ('Auditing', {
            'fields': AuditableModelAdmin.readonly_fields,
            'classes': ('collapse',),
        }),
    )

    def organization_display(self, obj):
        return obj.organization.name if obj.organization else "Global"
    organization_display.short_description = "Scope"

    def get_queryset(self, request):
        """
        - Superusers see all.
        - Org Admins see global funders and any funders they have created for their org.
        """
        qs = super().get_queryset(request)
        if request.user.is_superuser:
            return qs
        if request.user.is_staff and hasattr(request.user, 'organization') and request.user.organization:
            return qs.filter(Q(organization__isnull=True) | Q(organization=request.user.organization))
        return qs.none()

@admin.register(GrantOpportunity)
class GrantOpportunityAdmin(AuditableModelAdmin):
    list_display = ('title', 'funder', 'application_deadline', 'is_active', 'source_name', 'updated_at')
    search_fields = ('title', 'description', 'funder__name', 'source_id', 'id', 'tags')
    list_filter = ('is_active', 'source_name', 'funder__name', 'application_deadline')
    list_select_related = ('funder',)
    date_hierarchy = 'application_deadline'
    
    fieldsets = (
        ('Grant Information', {
            'fields': ('title', 'funder', 'description', 'is_active')
        }),
        ('Funding Details', {
            'fields': ('min_amount', 'max_amount', 'application_deadline', 'funding_instrument_type', 'funding_activity_category', 'eligibility_criteria_text', 'tags')
        }),
        ('Source Information', {
            'fields': ('source_name', 'source_id', 'source_url')
        }),
        ('Auditing', {
            'fields': AuditableModelAdmin.readonly_fields,
            'classes': ('collapse',),
        }),
    )
