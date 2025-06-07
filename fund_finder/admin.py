# fund_finder/admin.py
from django.contrib import admin, messages
from django.urls import path
from django.shortcuts import render, redirect
from django.conf import settings
from django import forms
import zipfile
import tempfile
import os
import io

from .models import FunderProfile, GrantOpportunity, FunderType
from .tasks import process_grant_file_task # Import our new Celery task
from core.admin import AuditableModelAdmin
from django.db.models import Q

# --- File Upload Form ---
class DataUploadForm(forms.Form):
    # Update the form to accept .zip files
    file = forms.FileField(help_text="Upload a CSV, XML, or a ZIP file containing multiple CSV/XML files.")

    def clean_file(self):
        file = self.cleaned_data['file']
        # Update validation to include .zip
        if not file.name.endswith(('.csv', '.xml', '.zip')):
            raise forms.ValidationError("Invalid file type. Please upload a .csv, .xml, or .zip file.")
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
        """
        Handles the file upload form. Saves the file to a temporary location
        and dispatches a Celery task to process it asynchronously.
        """
        if request.method == 'POST':
            form = DataUploadForm(request.POST, request.FILES)
            if form.is_valid():
                file = request.FILES['file']
                
                # Use a temporary directory for safe file handling
                # We save the file here first, then pass its path to Celery.
                # Celery worker needs access to this path (shared volume).
                # A simple approach for Docker is to use a subdir in a shared volume like media.
                from django.core.files.storage import FileSystemStorage
                temp_upload_dir = os.path.join(settings.MEDIA_ROOT, 'temp_uploads')
                fs = FileSystemStorage(location=temp_upload_dir)
                
                if file.name.endswith('.zip'):
                    try:
                        with zipfile.ZipFile(file, 'r') as zip_ref:
                            # We extract and save each valid file individually to pass to Celery
                            extracted_files_count = 0
                            for filename_in_zip in zip_ref.namelist():
                                if filename_in_zip.startswith('__') or filename_in_zip.endswith('/'):
                                    continue
                                if not (filename_in_zip.endswith('.csv') or filename_in_zip.endswith('.xml')):
                                    continue

                                file_data = zip_ref.read(filename_in_zip)
                                # Save the extracted file to our temp location
                                saved_filename = fs.save(os.path.basename(filename_in_zip), io.BytesIO(file_data))
                                uploaded_file_path = fs.path(saved_filename)
                                
                                # Launch Celery task for each valid file
                                process_grant_file_task.delay(uploaded_file_path, os.path.basename(filename_in_zip))
                                extracted_files_count += 1

                        self.message_user(request, f"ZIP file '{file.name}' accepted. {extracted_files_count} file(s) are being processed in the background. Check Celery worker logs for progress.", messages.SUCCESS)

                    except Exception as e:
                        self.message_user(request, f"An error occurred during zip file handling: {e}", messages.ERROR)
                
                else: # Handle single CSV/XML
                    saved_filename = fs.save(file.name, file)
                    uploaded_file_path = fs.path(saved_filename)
                    
                    # Launch the Celery task
                    process_grant_file_task.delay(uploaded_file_path, file.name)
                    self.message_user(request, f"File '{file.name}' accepted and is being processed in the background. Check Celery worker logs for progress.", messages.SUCCESS)
                
                return redirect('.') # Redirect back to the same upload page
        else:
            form = DataUploadForm()
            
        context = dict(
           self.admin_site.each_context(request),
           title="Upload Grant Data",
           form=form,
           opts=self.model._meta,
        )
        return render(request, "admin/fund_finder/upload_grants.html", context)
