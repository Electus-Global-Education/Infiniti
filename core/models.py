# core/models.py
import uuid # For UUID primary keys
from django.db import models
from django.conf import settings # For AUTH_USER_MODEL
from django.contrib.auth.models import AbstractUser
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
import secrets

# --- Auditing Abstract Model ---
class AuditableModel(models.Model):
    """
    An abstract base class model that provides a UUID primary key,
    self-updating 'created_at' and 'updated_at' fields (timezone-aware if USE_TZ=True),
    and links to creating/updating users.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    created_at = models.DateTimeField(auto_now_add=True, editable=False)
    updated_at = models.DateTimeField(auto_now=True, editable=False)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        related_name='%(app_label)s_%(class)s_created', # Ensures unique related_name
        on_delete=models.SET_NULL,
        null=True, blank=True, editable=False
    )
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        related_name='%(app_label)s_%(class)s_updated', # Ensures unique related_name
        on_delete=models.SET_NULL,
        null=True, blank=True, editable=False
    )

    class Meta:
        abstract = True
        ordering = ['-created_at'] # Default ordering

# --- Core Models ---
class Organization(AuditableModel):
    name = models.CharField(max_length=255, unique=True, help_text="Official name of the organization.")
    description = models.TextField(blank=True, null=True)
    is_active = models.BooleanField(default=True, help_text="Is this organization currently active on the platform?")

    def __str__(self):
        return self.name

    class Meta(AuditableModel.Meta): # Inherit Meta options like ordering
        verbose_name = "Organization"
        verbose_name_plural = "Organizations"
        # ordering = ['name'] # Can override default ordering if needed


class User(AbstractUser): # Standard User model with Integer PK
    """
    Custom User model. Each user (except perhaps superusers) belongs to an Organization.
    Keeps integer PK for compatibility with Django auth, adds a UUID for external reference.
    Also adds created_at/updated_at manually as AbstractUser doesn't have them by default.
    """
    # id field is inherited from AbstractUser (AutoIncrementing Integer PK)
    uuid = models.UUIDField(default=uuid.uuid4, editable=False, unique=True, help_text="Publicly visible unique identifier.")
    organization = models.ForeignKey(
        Organization,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='users',
        help_text="The organization this user belongs to."
    )
    # Manually adding audit fields as AbstractUser doesn't have them by default
    # and we are not inheriting AuditableModel directly to preserve int PK for User.
    created_at = models.DateTimeField(auto_now_add=True, editable=False, null=True, blank=True) # Nullable for existing users
    updated_at = models.DateTimeField(auto_now=True, editable=False, null=True, blank=True) # Nullable for existing users
    # created_by and updated_by could be added here too if desired for User model specifically

    def __str__(self):
        return self.username

    class Meta:
        verbose_name = "User"
        verbose_name_plural = "Users"
        ordering = ['username']


class RegisteredApplication(AuditableModel):
    organization = models.ForeignKey(
        Organization,
        on_delete=models.PROTECT,
        related_name='registered_applications',
        help_text="The organization that owns this application."
    )
    name = models.CharField(max_length=200, help_text="Name of the application (unique within an organization).")
    description = models.TextField(blank=True, null=True)
    base_url = models.URLField(max_length=255, blank=True, null=True, help_text="Base URL of the external application.")
    api_key = models.CharField(
        max_length=128,
        unique=True,
        editable=False,
        help_text="Generated API key for this application."
    )
    is_active = models.BooleanField(default=True, help_text="Is this application currently active?")

    def __str__(self):
        return f"{self.name} ({self.organization.name})"

    def save(self, *args, **kwargs):
        if not self.api_key:
            self.api_key = secrets.token_urlsafe(48)
        super().save(*args, **kwargs)

    class Meta(AuditableModel.Meta):
        verbose_name = "Registered Application"
        verbose_name_plural = "Registered Applications"
        ordering = ['organization__name', 'name']
        unique_together = [['organization', 'name']]


class BasePrompt(AuditableModel):
    PROMPT_TYPE_CHOICES = [
        ('SYSTEM', 'System Level'),
        ('ORG', 'Organization Specific'),
    ]
    title = models.CharField(max_length=255)
    description = models.TextField(blank=True, null=True)
    prompt_text = models.TextField(help_text="The base prompt text. Use {{placeholders}} for variables.")
    prompt_type = models.CharField(max_length=10, choices=PROMPT_TYPE_CHOICES, default='ORG')
    application = models.ForeignKey(
        RegisteredApplication,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='prompts',
        help_text="Application this prompt belongs to (for ORG type prompts)."
    )
    is_active = models.BooleanField(default=True)
    version = models.PositiveIntegerField(default=1)

    def __str__(self):
        if self.application:
            return f"{self.title} ({self.application.name} - {self.get_prompt_type_display()})"
        return f"{self.title} (SYSTEM)"

    def clean(self):
        from django.core.exceptions import ValidationError
        if self.prompt_type == 'ORG' and not self.application:
            raise ValidationError({'application': 'Organization-specific prompts must be linked to a registered application.'})
        if self.prompt_type == 'SYSTEM' and self.application:
            self.application = None

    class Meta(AuditableModel.Meta):
        verbose_name = "Base Prompt"
        verbose_name_plural = "Base Prompts"
        ordering = ['prompt_type', 'application__organization__name', 'application__name', 'title']


class AuditLog(models.Model): # Does not inherit AuditableModel to avoid self-auditing loop
    """
    Logs CRUD operations and other significant events across the application.
    """
    ACTION_CHOICES = [
        ('CREATE', 'Create'),
        ('UPDATE', 'Update'),
        ('DELETE', 'Delete'),
        ('READ', 'Read'), # Log significant read operations if necessary
        ('LOGIN_SUCCESS', 'Login Success'),
        ('LOGIN_FAILED', 'Login Failed'),
        ('LOGOUT', 'Logout'),
        ('API_CALL_SUCCESS', 'API Call Success'),
        ('API_CALL_FAILED', 'API Call Failed'),
        ('PASSWORD_RESET_REQUEST', 'Password Reset Request'),
        ('PASSWORD_RESET_COMPLETE', 'Password Reset Complete'),
        ('PERMISSION_CHANGE', 'Permission Change'), # Example of other specific actions
        ('SYSTEM_EVENT', 'System Event'), # For automated system actions
    ]
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False) # UUID PK for AuditLog
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        help_text="User who performed the action, or system if null."
    )
    action_type = models.CharField(max_length=30, choices=ACTION_CHOICES, help_text="Type of action performed.")
    timestamp = models.DateTimeField(auto_now_add=True, help_text="When the action occurred (timezone-aware if USE_TZ=True).")
    
    # Generic relation to the object being acted upon (optional for some log types like LOGIN)
    content_type = models.ForeignKey(
        ContentType,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        help_text="The model of the object that was affected."
    )
    object_id_int = models.IntegerField(null=True, blank=True, help_text="The integer PK of the object (if applicable).") # For User model
    object_id_uuid = models.UUIDField(null=True, blank=True, help_text="The UUID PK of the object (if applicable).")
    # content_object = GenericForeignKey('content_type', 'object_id') # This needs careful handling with two possible object_id fields

    object_repr = models.CharField(max_length=255, blank=True, null=True, help_text="A string representation of the object at the time of logging.")
    changes_json = models.JSONField(null=True, blank=True, help_text="JSON representation of changes made (e.g., for UPDATE actions). Field diffs.")
    ip_address = models.GenericIPAddressField(null=True, blank=True, help_text="IP address of the request origin.")
    user_agent = models.TextField(blank=True, null=True, help_text="User agent string of the client.")
    additional_info = models.TextField(blank=True, null=True, help_text="Any other relevant information for this log entry (e.g., API endpoint called, parameters).")

    def __str__(self):
        user_str = str(self.user) if self.user else "System/Anonymous"
        return f"{self.timestamp} - {user_str} - {self.action_type} on {self.object_repr or self.content_type or 'System'}"

    class Meta:
        verbose_name = "Audit Log"
        verbose_name_plural = "Audit Logs"
        ordering = ['-timestamp']
        indexes = [
            models.Index(fields=['content_type', 'object_id_int']),
            models.Index(fields=['content_type', 'object_id_uuid']),
            models.Index(fields=['user', 'action_type']),
        ]
