# core/authentication.py
from urllib.parse import urlparse
from rest_framework.authentication import BaseAuthentication
from rest_framework.exceptions import AuthenticationFailed
from drf_spectacular.extensions import OpenApiAuthenticationExtension
from drf_spectacular.plumbing import build_bearer_security_scheme_object

from .models import RegisteredApplication, User

class APIKeyAuthentication(BaseAuthentication):
    """
    Custom authentication class for validating requests from registered applications.
    
    Authenticates against an API key provided in the 'Authorization' header.
    Example Header: `Authorization: Api-Key sk_123abc...`

    Optionally, it also validates that the request's Origin or Referer
    matches the `base_url` registered for the application.
    """
    keyword = 'Api-Key'

    def authenticate(self, request):
        auth_header = request.META.get('HTTP_AUTHORIZATION')

        if not auth_header or not auth_header.startswith(self.keyword + ' '):
            return None # Authentication not attempted

        try:
            api_key = auth_header.split(' ')[1]
        except IndexError:
            raise AuthenticationFailed('Malformed API Key header. Expected "Api-Key <key>".')

        try:
            application = RegisteredApplication.objects.select_related('organization').get(api_key=api_key)
        except RegisteredApplication.DoesNotExist:
            raise AuthenticationFailed('Invalid API Key. Application not found.')

        if not application.is_active:
            raise AuthenticationFailed('This application is inactive.')
        
        if not application.organization.is_active:
            raise AuthenticationFailed('The organization for this application is inactive.')

        request_origin = self.get_request_origin(request)
        
        if application.base_url and request_origin:
            if not self.is_origin_allowed(request_origin, application.base_url):
                raise AuthenticationFailed(f'Request origin "{request_origin}" does not match the registered base URL.')
        
        # Associate the request with a user from the application's organization.
        # This could be the app creator or a designated service account user.
        user = application.created_by or application.organization.users.filter(is_staff=True).first()

        if not user:
             raise AuthenticationFailed('No valid user associated with the authenticated application.')

        return (user, application)
    
    def get_request_origin(self, request):
        http_origin = request.META.get('HTTP_ORIGIN')
        if http_origin:
            return http_origin
        
        http_referer = request.META.get('HTTP_REFERER')
        if http_referer:
            return f"{urlparse(http_referer).scheme}://{urlparse(http_referer).netloc}"
            
        return None

    def is_origin_allowed(self, request_origin, registered_base_url):
        try:
            req_parsed = urlparse(request_origin)
            reg_parsed = urlparse(registered_base_url)
            return req_parsed.scheme == reg_parsed.scheme and req_parsed.netloc == reg_parsed.netloc
        except Exception:
            return False

    def authenticate_header(self, request):
        return self.keyword


# --- drf-spectacular Extension for our Custom Auth ---
# This class tells the documentation generator how to represent our auth scheme.
class APIKeyAuthenticationScheme(OpenApiAuthenticationExtension):
    target_class = 'core.authentication.APIKeyAuthentication'  # Path to your custom auth class
    name = 'APIKeyAuth'  # A name for the security scheme in the OpenAPI spec

    def get_security_definition(self, auto_schema):
        # Describes how the API key is passed (in the header)
        return {
            'type': 'apiKey',
            'in': 'header',
            'name': 'Authorization',
            'description': "API Key authentication. Value should be formatted as 'Api-Key &lt;YOUR_API_KEY&gt;'.",
        }
