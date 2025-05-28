# core/views.py
from django.shortcuts import render
from django.views.generic import TemplateView
from django.contrib.auth.mixins import LoginRequiredMixin # For Class-Based Views that require login
# from django.contrib.auth.decorators import login_required # For Function-Based Views that require login
from django.shortcuts import render
from .utils import generate_gemini_response

# Create your views here.
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from .utils import generate_gemini_response, ALLOWED_MODELS, DEFAULT_MODEL, DEFAULT_TEMPERATURE


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

# Decorator to mark this function as a Django REST framework API view for POST requests only
@api_view(["POST"])
# Only allow authenticated users to access this view
@permission_classes([IsAuthenticated])
def edujob_view(request):
    """
    View for generating responses to education job-related prompts
    using Google's Gemini language models.

    Requires user authentication and a POST request with the prompt
    and optional model/temperature parameters.
    """
    # Extract and validate input data
    # Get the prompt from the request body and strip whitespace
    prompt = request.data.get("prompt", "").strip()
    # Optionally get the requested model name and temperature
    model_name = request.data.get("model", "").strip()
    temperature = request.data.get("temperature")

    if not prompt:
        return Response({"error": "Prompt is required."}, status=400)
    # Call the utility function with prompt, model, and temperature
    response_text = generate_gemini_response(
        prompt=prompt,
        model_name=model_name,
        temperature=temperature
    )
    # Return the response to the client as JSON
    return Response({
        #"used_model": model_name if model_name in ALLOWED_MODELS else DEFAULT_MODEL,
        #"used_temperature": temperature if temperature else DEFAULT_TEMPERATURE,
        "response": response_text
    })

