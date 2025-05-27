# core/views.py
from django.shortcuts import render
from django.views.generic import TemplateView
from django.contrib.auth.mixins import LoginRequiredMixin # For Class-Based Views that require login
# from django.contrib.auth.decorators import login_required # For Function-Based Views that require login

class LandingPageView(TemplateView):
    """
    Serves the main landing page of the application.
    This view extends the project's base.html.
    """
    template_name = 'core/landing_page.html' # Path to the app-specific template

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['page_heading'] = "Welcome to the Infiniti Ecosystem"
        context['featured_message'] = "Empowering Your Journey with Intelligent Tools."
        # Add any other context data your landing page might need
        return context

class DashboardView(LoginRequiredMixin, TemplateView):
    """
    Serves the user's dashboard page after login.
    Requires user to be authenticated.
    """
    template_name = 'core/dashboard.html'
    # login_url = '/accounts/login/' # Or use settings.LOGIN_URL; Django's default is /accounts/login/
                                   # If LOGIN_URL is set in settings.py, this line is not strictly needed here.

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['page_heading'] = f"Dashboard for {self.request.user.username}"
        # You can add more context specific to the logged-in user
        # For example, recent activity, notifications, etc.
        return context
