# fund_finder/admin.py
from django.contrib import admin, messages
from django.urls import path
from django.shortcuts import render, redirect
from django.core.management import call_command
from django import forms
from .models import FunderProfile, GrantOpportunity, FunderType
from core.admin import AuditableModelAdmin
from django.db.models import Q
import io
import contextlib
import zipfile
import tempfile
import os
import shutil

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

    def _process_file(self, file_path, request):
        """Helper method to process a single file (CSV or XML)."""
        output_buffer = io.StringIO()
        command_to_run = ''
        filename = os.path.basename(file_path)

        if filename.endswith('.csv'):
            command_to_run = 'import_grants_from_csv'
        elif filename.endswith('.xml'):
            command_to_run = 'import_grants_from_xml'
        
        if command_to_run:
            with contextlib.redirect_stdout(output_buffer), contextlib.redirect_stderr(output_buffer):
                call_command(command_to_run, file_path, stdout=output_buffer, stderr=output_buffer)
            
            output_str = output_buffer.getvalue()
            self.message_user(request, f"<pre>Processing Log for: {filename}\n\n{output_str}</pre>", messages.INFO, extra_tags='safe')
        else:
            self.message_user(request, f"Skipping unsupported file: {filename}", messages.WARNING)


    def upload_grants_view(self, request):
        if request.method == 'POST':
            form = DataUploadForm(request.POST, request.FILES)
            if form.is_valid():
                file = request.FILES['file']
                
                # --- ZIP file handling logic ---
                if file.name.endswith('.zip'):
                    try:
                        # Use a temporary directory for safe extraction
                        with tempfile.TemporaryDirectory() as temp_dir:
                            with zipfile.ZipFile(file, 'r') as zip_ref:
                                zip_ref.extractall(temp_dir)
                            
                            self.message_user(request, f"Successfully extracted '{file.name}'. Processing contents...", messages.SUCCESS)
                            
                            # Process each file found in the zip archive
                            for extracted_filename in sorted(os.listdir(temp_dir)):
                                full_file_path = os.path.join(temp_dir, extracted_filename)
                                if os.path.isfile(full_file_path):
                                    self._process_file(full_file_path, request)
                                    
                    except zipfile.BadZipFile:
                        self.message_user(request, "Error: The uploaded file is not a valid zip file.", messages.ERROR)
                    except Exception as e:
                        self.message_user(request, f"An error occurred during zip file processing: {e}", messages.ERROR)
                
                # --- Single CSV/XML file handling logic ---
                else:
                    from django.core.files.storage import FileSystemStorage
                    fs = FileSystemStorage()
                    filename = fs.save(file.name, file)
                    uploaded_file_path = fs.path(filename)
                    
                    try:
                        self._process_file(uploaded_file_path, request)
                    except Exception as e:
                        self.message_user(request, f"A critical error occurred while trying to process the file: {e}", messages.ERROR)
                    finally:
                        fs.delete(filename) # Clean up the temporary file
                
                return redirect('.') # Redirect back to this same upload page to see the messages
        else:
            form = DataUploadForm()
            
        context = dict(
           self.admin_site.each_context(request),
           title="Upload Grant Data",
           form=form,
           opts=self.model._meta,
        )
        return render(request, "admin/fund_finder/upload_grants.html", context)

