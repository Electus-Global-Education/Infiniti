# core/views.py
from django.shortcuts import render
from django.views.generic import TemplateView

class LandingPageView(TemplateView):
    """
    Serves the main landing page of the application.
    This view extends the project's base.html.
    """
    template_name = 'core/landing_page.html' # Path to the app-specific template

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['page_heading'] = "Welcome to the Infiniti Platform"
        context['featured_message'] = "Discover amazing things here."
        # Add any other context data your landing page might need
        return context

