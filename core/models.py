# core/models.py
from django.db import models
from django.conf import settings # To potentially link to the user who registered it
import uuid # For generating API keys
import secrets # For more cryptographically secure tokens

class RegisteredApplication(models.Model):
    """
    Model to store information about external applications
    that will integrate with the Infiniti platform.
    """
    name = models.CharField(max_length=200, unique=True, help_text="Unique name of the external application.")
    description = models.TextField(blank=True, null=True, help_text="A brief description of the application.")
    
    # The user who registered this application (optional, could be a superuser or staff)
    # If you have a specific "Organization" model that these apps belong to, you might link to that instead.
    registered_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL, # Or models.PROTECT if you don't want to delete apps if user is deleted
        null=True,
        blank=True,
        related_name='registered_applications',
        help_text="User who registered this application."
    )
    
    base_url = models.URLField(max_length=255, blank=True, null=True, help_text="Base URL of the external application (for reference or callbacks).")
    
    # API Key: Generated automatically, should be shown once upon creation.
    # For security, consider storing a hash of the API key if you need to verify it without storing the raw key.
    # However, for third-party apps, they need the raw key.
    # We will generate a secure token.
    api_key = models.CharField(
        max_length=128, # Increased length for secure tokens
        unique=True,
        editable=False, # Not directly editable after creation
        help_text="Generated API key for this application. Treat this like a password."
    )
    
    is_active = models.BooleanField(default=True, help_text="Is this application currently active and allowed to use the API?")
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        if not self.api_key:
            # Generate a new API key only if one doesn't exist (i.e., on creation)
            # Using secrets.token_urlsafe for a more secure, URL-friendly token
            self.api_key = secrets.token_urlsafe(48) # Generates a 64-character URL-safe string
        super().save(*args, **kwargs)

    class Meta:
        verbose_name = "Registered Application"
        verbose_name_plural = "Registered Applications"
        ordering = ['name']
