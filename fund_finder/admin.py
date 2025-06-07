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
    search_fields = ('name', 'description', 'id', 'agency_code')
    list_filter = ('is_active', 'funder_type', 'organization__name')
    
    fieldsets = (
        ('Funder Information', {
            'fields': ('name', 'agency_code', 'description', 'website', 'funder_type', 'is_active', 'contact_info')
        }),
        ('Categorization & Scope', {
            'fields': ('geographic_focus', 'program_areas', 'organization')
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
    list_display = ('title', 'funder', 'close_date', 'status', 'is_active', 'source_name')
    search_fields = ('title', 'description', 'funder__name', 'source_id', 'id', 'assistance_listings')
    list_filter = ('is_active', 'status', 'source_name', 'funder__name', 'close_date')
    list_select_related = ('funder',)
    date_hierarchy = 'close_date'
    
    fieldsets = (
        ('Grant Information', {
            'fields': ('title', 'funder', 'description', 'is_active', 'status')
        }),
        ('Funding Details', {
            'fields': ('estimated_total_funding', 'award_floor', 'award_ceiling', 'expected_number_of_awards', 'cost_sharing_requirement')
        }),
        ('Categorization', {
            'fields': ('funding_instrument_type', 'funding_activity_category', 'assistance_listings')
        }),
        ('Dates & Version', {
            'fields': ('posted_date', 'close_date', 'last_updated_date', 'version')
        }),
        ('Source Information', {
            'fields': ('source_name', 'source_id', 'source_url')
        }),
        ('Auditing', {
            'fields': AuditableModelAdmin.readonly_fields,
            'classes': ('collapse',),
        }),
    )
