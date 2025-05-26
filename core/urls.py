# core/urls.py
from django.urls import path
from .views import LandingPageView # Import your view

app_name = 'core'  # Namespace for this app's URLs

urlpatterns = [
    path('', LandingPageView.as_view(), name='landing_page'),
    # Add other core app URLs here
]
