# core/admin.py
from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.utils.translation import gettext_lazy as _
from django.contrib.contenttypes.models import ContentType
from django.utils import timezone
import json # For serializing changes
import uuid # For checking instance type for AuditLog
from django.db import models # Import the models module from Django
from django.forms.models import model_to_dict # To get initial values
import secrets # For regenerating API keys

from .models import Organization, User, RegisteredApplication, BasePrompt, AuditLog

# Helper function to get client IP address
def get_client_ip(request):
    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded_for:
        ip = x_forwarded_for.split(',')[0]
    else:
        ip = request.META.get('REMOTE_ADDR')
    return ip

# Helper function to create an audit log entry
def create_audit_log_entry(user, instance, action_type, changes_dict=None, request=None, additional_info=None):
    ip_address = get_client_ip(request) if request else None
    user_agent = request.META.get('HTTP_USER_AGENT', '') if request else None
    
    object_id_int_val = None
    object_id_uuid_val = None
    
    if instance:
        if isinstance(instance._meta.pk, models.UUIDField):
            object_id_uuid_val = instance.pk
        else:
            object_id_int_val = instance.pk

    AuditLog.objects.create(
        user=user if user and user.is_authenticated else None,
        action_type=action_type,
        content_type=ContentType.objects.get_for_model(instance.__class__) if instance else None,
        object_id_int=object_id_int_val,
        object_id_uuid=object_id_uuid_val,
        object_repr=str(instance)[:255] if instance else "N/A",
        changes_json=changes_dict if changes_dict else None,
        ip_address=ip_address,
        user_agent=user_agent,
        additional_info=additional_info
    )

class AuditableModelAdmin(admin.ModelAdmin):
    readonly_fields = ('id', 'created_at', 'updated_at', 'created_by', 'updated_by')

    def _get_changed_data(self, form):
        changed_data = {}
        if form.changed_data:
            for field_name in form.changed_data:
                if 'password' in field_name.lower() or 'api_key' in field_name.lower():
                    changed_data[field_name] = {'old': '[SENSITIVE_FIELD]', 'new': '[SENSITIVE_FIELD]'}
                    continue
                initial_value = form.initial.get(field_name)
                cleaned_value = form.cleaned_data.get(field_name)
                if isinstance(initial_value, models.fields.files.FieldFile): initial_value = str(initial_value) if initial_value else None
                if isinstance(cleaned_value, models.fields.files.FieldFile): cleaned_value = str(cleaned_value) if cleaned_value else None
                if hasattr(initial_value, 'pk'): initial_value = initial_value.pk
                if hasattr(cleaned_value, 'pk'): cleaned_value = cleaned_value.pk
                changed_data[field_name] = {'old': str(initial_value) if initial_value is not None else None, 'new': str(cleaned_value) if cleaned_value is not None else None}
        return changed_data if changed_data else None

    def save_model(self, request, obj, form, change):
        is_new_object = not obj.pk
        if is_new_object and hasattr(obj, 'created_by'):
            if not getattr(obj, 'created_by', None):
                 obj.created_by = request.user
        if hasattr(obj, 'updated_by'):
            obj.updated_by = request.user
        action = 'CREATE' if is_new_object else 'UPDATE'
        changes_for_log = None
        if not is_new_object and change:
            changes_for_log = self._get_changed_data(form)
        super().save_model(request, obj, form, change)
        create_audit_log_entry(request.user, obj, action, changes_for_log, request)

    def delete_model(self, request, obj):
        create_audit_log_entry(request.user, obj, 'DELETE', request=request)
        super().delete_model(request, obj)

    def delete_queryset(self, request, queryset):
        for obj in queryset:
            create_audit_log_entry(request.user, obj, 'DELETE', request=request)
        super().delete_queryset(request, queryset)

@admin.register(Organization)
class OrganizationAdmin(AuditableModelAdmin):
    list_display = ('name', 'is_active', 'created_at', 'id')
    search_fields = ('name', 'description', 'id')
    list_filter = ('is_active', 'created_at')

@admin.register(User)
class UserAdmin(BaseUserAdmin):
    list_display = ('username', 'email', 'first_name', 'last_name', 'is_staff', 'organization', 'uuid', 'created_at', 'updated_at')
    list_filter = BaseUserAdmin.list_filter + ('organization', 'is_staff', 'is_superuser', 'is_active')
    search_fields = BaseUserAdmin.search_fields + ('organization__name', 'uuid')
    readonly_fields = ('uuid', 'last_login', 'date_joined', 'created_at', 'updated_at')
    fieldsets = (
        (None, {"fields": ("username", "password")}),
        (_("Personal info"), {"fields": ("first_name", "last_name", "email")}),
        (_("Organization & Identifiers"), {"fields": ("organization", "uuid")}),
        (_("Permissions"), {"fields": ("is_active", "is_staff", "is_superuser", "groups", "user_permissions",)}),
        (_("Important dates"), {"fields": ("last_login", "date_joined", "created_at", "updated_at")}),
    )
    add_fieldsets = BaseUserAdmin.add_fieldsets + ((_("Organization"), {'fields': ('organization',)}),)
    
    def _get_user_changed_data(self, form):
        changed_data = {}
        if form.changed_data:
            for field_name in form.changed_data:
                if 'password' in field_name.lower():
                    changed_data[field_name] = {'old': '[PASSWORD_CHANGED]', 'new': '[PASSWORD_CHANGED]'}
                    continue
                initial_value = form.initial.get(field_name)
                cleaned_value = form.cleaned_data.get(field_name)
                if hasattr(initial_value, 'pk'): initial_value = initial_value.pk
                if hasattr(cleaned_value, 'pk'): cleaned_value = cleaned_value.pk
                changed_data[field_name] = {'old': str(initial_value) if initial_value is not None else None, 'new': str(cleaned_value) if cleaned_value is not None else None}
        return changed_data if changed_data else None

    def save_model(self, request, obj, form, change):
        is_new_object = not obj.pk
        action = 'CREATE' if is_new_object else 'UPDATE'
        changes_for_log = None
        if not is_new_object and change: changes_for_log = self._get_user_changed_data(form)
        super().save_model(request, obj, form, change)
        create_audit_log_entry(request.user, obj, action, changes_for_log, request)

    def delete_model(self, request, obj):
        create_audit_log_entry(request.user, obj, 'DELETE', request=request)
        super().delete_model(request, obj)

    def delete_queryset(self, request, queryset):
        for obj in queryset: create_audit_log_entry(request.user, obj, 'DELETE', request=request)
        super().delete_queryset(request, queryset)

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        if request.user.is_superuser: return qs
        if request.user.is_staff and hasattr(request.user, 'organization') and request.user.organization: return qs.filter(organization=request.user.organization)
        return qs.none()

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if db_field.name == "organization":
            if not request.user.is_superuser and hasattr(request.user, 'organization') and request.user.organization:
                kwargs["queryset"] = Organization.objects.filter(id=request.user.organization.id)
                kwargs["initial"] = request.user.organization.id
        return super().formfield_for_foreignkey(db_field, request, **kwargs)

@admin.register(RegisteredApplication)
class RegisteredApplicationAdmin(AuditableModelAdmin):
    list_display = ('name', 'organization', 'api_key_short', 'is_active', 'created_at', 'id')
    list_filter = ('is_active', 'organization__name', 'created_at')
    search_fields = ('name', 'organization__name', 'description', 'id', 'api_key')
    readonly_fields = AuditableModelAdmin.readonly_fields + ('api_key',) 
    actions = ['regenerate_api_keys'] # Add the new action

    fieldsets = (
        (None, {'fields': ('organization', 'name', 'description', 'base_url', 'is_active')}),
        ('API Key Information', {'fields': ('api_key',), 'description': "The API key is generated automatically upon creation and can be regenerated via the 'Actions' dropdown."}),
        ('Auditing', {'fields': ('id', 'created_by', 'created_at', 'updated_by', 'updated_at'), 'classes': ('collapse',),}),
    )

    def api_key_short(self, obj):
        return f"{obj.api_key[:8]}...{obj.api_key[-4:]}" if obj.api_key else "N/A"
    api_key_short.short_description = "API Key (Short)"

    @admin.action(description='Regenerate API key(s) for selected applications')
    def regenerate_api_keys(self, request, queryset):
        for app in queryset:
            old_key_preview = self.api_key_short(app)
            new_key = secrets.token_urlsafe(48)
            app.api_key = new_key
            app.save(update_fields=['api_key', 'updated_by', 'updated_at']) # Efficiently save only what's needed

            # Explicitly log the regeneration event for clarity
            create_audit_log_entry(
                request.user, 
                app, 
                'UPDATE', 
                changes_dict={'api_key': {'old': f'Key ending in ...{old_key_preview[-4:]}', 'new': 'New key generated'}},
                request=request,
                additional_info="API Key was manually regenerated via admin action."
            )
        self.message_user(request, f"Successfully regenerated API keys for {queryset.count()} application(s).")

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        if request.user.is_superuser: return qs
        if request.user.is_staff and hasattr(request.user, 'organization') and request.user.organization: return qs.filter(organization=request.user.organization)
        return qs.none()

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if db_field.name == "organization":
            if not request.user.is_superuser and hasattr(request.user, 'organization') and request.user.organization:
                kwargs["queryset"] = Organization.objects.filter(id=request.user.organization.id)
                kwargs["initial"] = request.user.organization.id
                kwargs["disabled"] = True
        return super().formfield_for_foreignkey(db_field, request, **kwargs)

@admin.register(BasePrompt)
class BasePromptAdmin(AuditableModelAdmin):
    list_display = ('title', 'prompt_type', 'application_display', 'is_active', 'version', 'created_at', 'id')
    list_filter = ('prompt_type', 'is_active', 'application__organization__name', 'application__name')
    search_fields = ('title', 'description', 'prompt_text', 'application__name', 'application__organization__name', 'id')
    actions = ['activate_prompts', 'deactivate_prompts']
    fieldsets = (
        (None, {'fields': ('title', 'description', 'prompt_text', 'prompt_type', 'application', 'is_active', 'version')}),
        ('Auditing', {'fields': ('id', 'created_by', 'created_at', 'updated_by', 'updated_at'), 'classes': ('collapse',),}),
    )
    def application_display(self, obj):
        if obj.application: return f"{obj.application.name} ({obj.application.organization.name})"
        return "N/A (System Prompt)"
    application_display.short_description = "Application (Org)"
    application_display.admin_order_field = 'application__name'
    def get_queryset(self, request):
        qs = super().get_queryset(request)
        if request.user.is_superuser: return qs
        if request.user.is_staff and hasattr(request.user, 'organization') and request.user.organization:
            organization = request.user.organization
            return qs.filter(models.Q(prompt_type='SYSTEM') | models.Q(application__organization=organization, prompt_type='ORG'))
        return qs.none()
    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if db_field.name == "application":
            if not request.user.is_superuser and hasattr(request.user, 'organization') and request.user.organization: kwargs["queryset"] = RegisteredApplication.objects.filter(organization=request.user.organization)
        return super().formfield_for_foreignkey(db_field, request, **kwargs)
    def activate_prompts(self, request, queryset):
        queryset.update(is_active=True)
        for obj in queryset: create_audit_log_entry(request.user, obj, 'UPDATE', {'is_active': {'old': 'False', 'new': 'True'}}, request)
        self.message_user(request, "Selected prompts have been activated.")
    activate_prompts.short_description = "Activate selected prompts"
    def deactivate_prompts(self, request, queryset):
        queryset.update(is_active=False)
        for obj in queryset: create_audit_log_entry(request.user, obj, 'UPDATE', {'is_active': {'old': 'True', 'new': 'False'}}, request)
        self.message_user(request, "Selected prompts have been deactivated.")
    deactivate_prompts.short_description = "Deactivate selected prompts"

@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    list_display = ('timestamp', 'user_display', 'action_type', 'content_type_display', 'object_link', 'ip_address', 'id', 'formatted_changes')
    list_filter = ('action_type', 'timestamp', ('user', admin.RelatedOnlyFieldListFilter), 'content_type')
    search_fields = ('user__username', 'object_repr', 'ip_address', 'additional_info', 'id', 'object_id_uuid', 'object_id_int', 'changes_json')
    readonly_fields = [f.name for f in AuditLog._meta.fields]
    date_hierarchy = 'timestamp'
    fieldsets = (
        ('Log Details', {'fields': ('timestamp', 'user', 'action_type', 'ip_address', 'user_agent')}),
        ('Affected Object', {'fields': ('content_type', 'object_id_int', 'object_id_uuid', 'object_repr')}),
        ('Change Data', {'fields': ('formatted_changes_display', 'additional_info')}),
    )
    def user_display(self, obj):
        return str(obj.user) if obj.user else "System/Anonymous"
    user_display.short_description = "User"
    user_display.admin_order_field = 'user__username'
    def content_type_display(self, obj):
        return str(obj.content_type) if obj.content_type else "N/A"
    content_type_display.short_description = "Object Type"
    content_type_display.admin_order_field = 'content_type__model'
    def object_link(self, obj):
        from django.urls import reverse
        from django.utils.html import format_html
        if obj.content_type:
            model_pk_field = obj.content_type.model_class()._meta.pk
            object_id_to_use = None
            if isinstance(model_pk_field, models.UUIDField): object_id_to_use = obj.object_id_uuid
            elif isinstance(model_pk_field, (models.AutoField, models.BigAutoField, models.IntegerField)): object_id_to_use = obj.object_id_int
            if object_id_to_use:
                try:
                    admin_url_name = f'admin:{obj.content_type.app_label}_{obj.content_type.model}_change'
                    admin_url = reverse(admin_url_name, args=[object_id_to_use])
                    return format_html('<a href="{}">{}</a>', admin_url, obj.object_repr or object_id_to_use)
                except Exception: return obj.object_repr or object_id_to_use or "Link Error"
        return obj.object_repr or "N/A"
    object_link.short_description = "Object"
    def formatted_changes(self, obj):
        if obj.changes_json:
            try:
                changes = obj.changes_json
                return "\n".join([f"'{field}': from '{data.get('old')}' to '{data.get('new')}'" for field, data in changes.items()])
            except json.JSONDecodeError: return obj.changes_json
        return "N/A"
    formatted_changes.short_description = "Changes"
    def formatted_changes_display(self, obj):
        from django.utils.html import format_html
        if obj.changes_json:
            try:
                changes = obj.changes_json
                html_output = "<ul>"
                for field, data in changes.items(): html_output += f"<li><strong>{field}:</strong> from '<code>{data.get('old', 'N/A')}</code>' to '<code>{data.get('new', 'N/A')}</code>'</li>"
                html_output += "</ul>"
                return format_html(html_output)
            except json.JSONDecodeError: return obj.changes_json
        return "No changes logged or N/A"
    formatted_changes_display.short_description = "Detailed Changes"
    def has_add_permission(self, request): return False
    def has_change_permission(self, request, obj=None): return False
    def has_delete_permission(self, request, obj=None): return False
