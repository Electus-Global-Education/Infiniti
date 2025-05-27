# core/urls.py
from django.urls import path
from .views import LandingPageView, DashboardView # Import your views

app_name = 'core'  # Namespace for this app's URLs

urlpatterns = [
    path('', LandingPageView.as_view(), name='landing_page'),
    path('dashboard/', DashboardView.as_view(), name='dashboard'),
    # Add other core app URLs here
]
