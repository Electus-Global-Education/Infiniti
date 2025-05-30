# core/admin.py
from django.contrib import admin
from .models import RegisteredApplication

@admin.register(RegisteredApplication)
class RegisteredApplicationAdmin(admin.ModelAdmin):
    list_display = ('name', 'is_active', 'registered_by', 'created_at', 'updated_at')
    list_filter = ('is_active', 'created_at')
    search_fields = ('name', 'description', 'registered_by__username')
    readonly_fields = ('api_key', 'created_at', 'updated_at') # Make api_key read-only in admin
    
    fieldsets = (
        (None, {
            'fields': ('name', 'description', 'base_url', 'is_active')
        }),
        ('API Key (Generated Automatically)', {
            'fields': ('api_key',),
            'classes': ('collapse',), # Optionally keep it collapsed by default
        }),
        ('Auditing', {
            'fields': ('registered_by', 'created_at', 'updated_at'),
            'classes': ('collapse',),
        }),
    )

    # If you want to automatically set the registered_by field to the current user when creating via admin
    def save_model(self, request, obj, form, change):
        if not obj.pk: # i.e., if creating a new object
            obj.registered_by = request.user
        super().save_model(request, obj, form, change)

# This admin configuration allows you to manage RegisteredApplication objects in the Django admin interface.