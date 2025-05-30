# core/signals.py
from django.contrib.auth.signals import user_logged_in, user_logged_out, user_login_failed
from django.dispatch import receiver
from django.contrib.contenttypes.models import ContentType
from .models import AuditLog, User # Import your custom User model
import uuid # Ensure uuid is imported if you use it for object_id_uuid

def get_client_ip_for_signal(request):
    if request:
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            return x_forwarded_for.split(',')[0]
        return request.META.get('REMOTE_ADDR')
    return None

def get_user_agent_for_signal(request):
    return request.META.get('HTTP_USER_AGENT', '') if request else None

@receiver(user_logged_in)
def log_user_logged_in(sender, request, user, **kwargs):
    """
    Logs successful user login events.
    """
    AuditLog.objects.create(
        user=user,
        action_type='LOGIN_SUCCESS', # Using string directly or from AuditLog.ACTION_CHOICES
        ip_address=get_client_ip_for_signal(request),
        user_agent=get_user_agent_for_signal(request),
        object_repr=f"User: {user.username}",
        content_type=ContentType.objects.get_for_model(User),
        object_id_int=user.pk # User model uses integer PK
    )

@receiver(user_logged_out)
def log_user_logged_out(sender, request, user, **kwargs):
    """
    Logs user logout events.
    The 'user' object might be None if the session timed out before explicit logout,
    but Django's user_logged_out signal usually provides it.
    """
    if user: # Proceed only if user object is available
        AuditLog.objects.create(
            user=user,
            action_type='LOGOUT',
            ip_address=get_client_ip_for_signal(request),
            user_agent=get_user_agent_for_signal(request),
            object_repr=f"User: {user.username}",
            content_type=ContentType.objects.get_for_model(User),
            object_id_int=user.pk
        )

@receiver(user_login_failed)
def log_user_login_failed(sender, credentials, request, **kwargs):
    """
    Logs failed user login attempts.
    'credentials' is a dict, e.g., {'username': 'attempted_username'}
    """
    username = credentials.get('username', 'N/A')
    AuditLog.objects.create(
        user=None, # No authenticated user for a failed login
        action_type='LOGIN_FAILED',
        ip_address=get_client_ip_for_signal(request),
        user_agent=get_user_agent_for_signal(request),
        object_repr=f"Failed login attempt for username: {username}",
        additional_info=f"Attempted username: {username}"
        # For failed login, content_object might not be relevant or could point to a general system log
    )
