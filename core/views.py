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

@api_view(["POST"])
@permission_classes([IsAuthenticated])
def edujob_view(request):
    prompt = request.data.get("prompt", "").strip()
    model_name = request.data.get("model", "").strip()
    temperature = request.data.get("temperature")

    if not prompt:
        return Response({"error": "Prompt is required."}, status=400)

    response_text = generate_gemini_response(
        prompt=prompt,
        model_name=model_name,
        temperature=temperature
    )

    return Response({
        #"used_model": model_name if model_name in ALLOWED_MODELS else DEFAULT_MODEL,
        #"used_temperature": temperature if temperature else DEFAULT_TEMPERATURE,
        "response": response_text
    })

