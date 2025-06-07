# fund_finder/admin.py
from django.contrib import admin, messages
from django.urls import path
from django.shortcuts import render, redirect
from django.core.management import call_command
from django import forms
from .models import FunderProfile, GrantOpportunity, FunderType
from core.admin import AuditableModelAdmin
from django.db.models import Q

# --- File Upload Form ---
class DataUploadForm(forms.Form):
    file = forms.FileField(help_text="Upload a CSV or XML file from Grants.gov.")

    def clean_file(self):
        file = self.cleaned_data['file']
        if not file.name.endswith(('.csv', '.xml')):
            raise forms.ValidationError("Invalid file type. Please upload a .csv or .xml file.")
        return file


@admin.register(FunderType)
class FunderTypeAdmin(AuditableModelAdmin):
    list_display = ('name', 'organization_display', 'is_active', 'updated_at')
    search_fields = ('name', 'organization__name')
    list_filter = ('is_active', 'organization__name')

    def organization_display(self, obj):
        return obj.organization.name if obj.organization else "System-Level"
    organization_display.short_description = "Scope"

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        if request.user.is_superuser: return qs
        if request.user.is_staff and hasattr(request.user, 'organization') and request.user.organization:
            return qs.filter(Q(organization__isnull=True) | Q(organization=request.user.organization))
        return qs.none()

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
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
        ('Funder Information', { 'fields': ('name', 'agency_code', 'description', 'website', 'funder_type', 'is_active', 'contact_info') }),
        ('Categorization & Scope', { 'fields': ('geographic_focus', 'program_areas', 'organization') }),
        ('Auditing', { 'fields': AuditableModelAdmin.readonly_fields, 'classes': ('collapse',) }),
    )

    def organization_display(self, obj):
        return obj.organization.name if obj.organization else "Global"
    organization_display.short_description = "Scope"

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        if request.user.is_superuser: return qs
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
        ('Grant Information', { 'fields': ('title', 'funder', 'description', 'is_active', 'status') }),
        ('Funding Details', { 'fields': ('estimated_total_funding', 'award_floor', 'award_ceiling', 'expected_number_of_awards', 'cost_sharing_requirement') }),
        ('Categorization', { 'fields': ('funding_instrument_type', 'funding_activity_category', 'assistance_listings') }),
        ('Dates & Version', { 'fields': ('posted_date', 'close_date', 'last_updated_date', 'version') }),
        ('Source Information', { 'fields': ('source_name', 'source_id', 'source_url') }),
        ('Auditing', { 'fields': AuditableModelAdmin.readonly_fields, 'classes': ('collapse',) }),
    )

    # --- Custom URL and View for File Upload ---
    def get_urls(self):
        urls = super().get_urls()
        custom_urls = [
            path('upload-grants/', self.admin_site.admin_view(self.upload_grants_view), name='fund_finder_grantopportunity_upload_grants'),
        ]
        return custom_urls + urls

    def upload_grants_view(self, request):
        if request.method == 'POST':
            form = DataUploadForm(request.POST, request.FILES)
            if form.is_valid():
                file = request.FILES['file']
                
                # Save the uploaded file temporarily to a secure location
                from django.core.files.storage import FileSystemStorage
                fs = FileSystemStorage()
                filename = fs.save(file.name, file)
                uploaded_file_path = fs.path(filename)
                
                try:
                    # Determine which management command to call based on file extension
                    if filename.endswith('.csv'):
                        call_command('import_grants_from_csv', uploaded_file_path)
                    elif filename.endswith('.xml'):
                        call_command('import_grants_from_xml', uploaded_file_path)
                    
                    self.message_user(request, f"Successfully processed file: {filename}", messages.SUCCESS)
                except Exception as e:
                    self.message_user(request, f"Error processing file: {e}", messages.ERROR)
                finally:
                    # Clean up the temporary file
                    fs.delete(filename)
                
                return redirect('..') # Redirect back to the GrantOpportunity changelist
        else:
            form = DataUploadForm()
            
        context = dict(
           self.admin_site.each_context(request),
           title="Upload Grant Data",
           form=form,
           opts=self.model._meta, # Pass model options for breadcrumbs
        )
        return render(request, "admin/fund_finder/upload_grants.html", context)

