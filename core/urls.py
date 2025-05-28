# core/urls.py
from django.urls import path
from .views import LandingPageView, DashboardView, edujob_view



app_name = 'core'  

urlpatterns = [
    path('', LandingPageView.as_view(), name='landing_page'),
    path('dashboard/', DashboardView.as_view(), name='dashboard'),
    path("edujob/", edujob_view, name="edujob"),
]
