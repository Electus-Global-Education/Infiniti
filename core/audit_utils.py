# core/audit_utils.py
from django.contrib.contenttypes.models import ContentType
from django.conf import settings
from .models import AuditLog # Assuming AuditLog is in core.models
import uuid # For checking instance type

def get_client_ip(request):
    """
    Helper function to extract the client's real IP address from the request object,
    accounting for proxies.
    """
    if not request:
        return None
    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded_for:
        ip = x_forwarded_for.split(',')[0]
    else:
        ip = request.META.get('REMOTE_ADDR')
    return ip

def create_audit_log_entry(user, instance, action_type, changes_dict=None, request=None, additional_info=None):
    """
    Creates a centralized AuditLog entry for any action in the system.

    Args:
        user (User): The user performing the action (can be None for system actions).
        instance (Model): The model instance being acted upon.
        action_type (str): The type of action (e.g., 'CREATE', 'UPDATE', 'LOGIN_SUCCESS').
        changes_dict (dict, optional): A dictionary of changed fields for UPDATE actions.
        request (HttpRequest, optional): The request object to extract IP and User-Agent.
        additional_info (str, optional): Any other relevant text for the log entry.
    """
    from django.db import models # Local import to avoid potential circular dependencies

    ip_address = get_client_ip(request) if request else None
    user_agent = request.META.get('HTTP_USER_AGENT', '') if request else None
    
    object_id_int_val = None
    object_id_uuid_val = None
    content_type_val = None
    object_repr_val = "N/A"
    
    if instance: # If there is a model instance related to the action
        # Determine which object_id field to use based on the model's primary key type
        if isinstance(instance._meta.pk, models.UUIDField):
            object_id_uuid_val = instance.pk
        else: 
            object_id_int_val = instance.pk
        
        content_type_val = ContentType.objects.get_for_model(instance.__class__)
        object_repr_val = str(instance)[:255] # Get a string representation, truncated if too long

    AuditLog.objects.create(
        user=user if user and user.is_authenticated else None,
        action_type=action_type,
        content_type=content_type_val,
        object_id_int=object_id_int_val,
        object_id_uuid=object_id_uuid_val,
        object_repr=object_repr_val,
        changes_json=changes_dict if changes_dict else None,
        ip_address=ip_address,
        user_agent=user_agent,
        additional_info=additional_info
    )
