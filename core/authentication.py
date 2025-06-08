# core/authentication.py
from urllib.parse import urlparse
from rest_framework.authentication import BaseAuthentication
from rest_framework.exceptions import AuthenticationFailed
from drf_spectacular.extensions import OpenApiAuthenticationExtension

from .models import RegisteredApplication

class APIKeyAuthentication(BaseAuthentication):
    """
    Custom authentication for validating requests from registered applications.
    Authenticates against an API key in the 'Authorization' header.
    Example: `Authorization: Api-Key sk_123...`
    Also validates the request's Origin/Referer against the app's registered base_url.
    """
    keyword = 'Api-Key'

    def authenticate(self, request):
        auth_header = request.META.get('HTTP_AUTHORIZATION')

        if not auth_header or not auth_header.startswith(self.keyword + ' '):
            return None

        try:
            api_key = auth_header.split(' ')[1]
        except IndexError:
            raise AuthenticationFailed('Malformed API Key header. Expected "Api-Key <key>".')

        try:
            application = RegisteredApplication.objects.select_related('organization', 'created_by').get(api_key=api_key)
        except RegisteredApplication.DoesNotExist:
            raise AuthenticationFailed('Invalid API Key. Application not found.')

        if not application.is_active or not application.organization.is_active:
            raise AuthenticationFailed('Application or its organization is inactive.')

        request_origin = self._get_request_origin(request)
        if application.base_url and request_origin:
            if not self._is_origin_allowed(request_origin, application.base_url):
                raise AuthenticationFailed(f'Request origin "{request_origin}" does not match the registered base URL.')
        
        # On success, associate the request with the user who created the application
        # or a primary staff member of the organization.
        user = application.created_by or application.organization.users.filter(is_staff=True).first()
        if not user:
             raise AuthenticationFailed('No valid user associated with the authenticated application.')

        return (user, application) # Success: request.user and request.auth

    def _get_request_origin(self, request):
        http_origin = request.META.get('HTTP_ORIGIN')
        if http_origin: return http_origin
        
        http_referer = request.META.get('HTTP_REFERER')
        if http_referer: return f"{urlparse(http_referer).scheme}://{urlparse(http_referer).netloc}"
        return None

    def _is_origin_allowed(self, request_origin, registered_base_url):
        try:
            req_parsed = urlparse(request_origin)
            reg_parsed = urlparse(registered_base_url)
            return req_parsed.scheme == reg_parsed.scheme and req_parsed.netloc == reg_parsed.netloc
        except Exception:
            return False

    def authenticate_header(self, request):
        return self.keyword

# --- drf-spectacular Extension for Swagger/ReDoc Documentation ---
class APIKeyAuthenticationScheme(OpenApiAuthenticationExtension):
    target_class = 'core.authentication.APIKeyAuthentication'
    name = 'APIKeyAuth' # This name is referenced in settings.SPECTACULAR_SETTINGS

    def get_security_definition(self, auto_schema):
        return {
            'type': 'apiKey',
            'in': 'header',
            'name': 'Authorization',
            'description': (
                "API Key authentication for external applications. "
                "The value should be formatted as `Api-Key <YOUR_API_KEY>`. "
                "API Keys can be generated in the admin panel under 'Registered Applications'."
            ),
        }

# Also define one for Bearer token for completeness in documentation
class JWTAuthenticationScheme(OpenApiAuthenticationExtension):
    target_class = 'rest_framework_simplejwt.authentication.JWTAuthentication'
    name = 'BearerAuth' # This name is referenced in settings.SPECTACULAR_SETTINGS

    def get_security_definition(self, auto_schema):
        return {
            'type': 'http',
            'scheme': 'bearer',
            'description': (
                "JWT-based authentication for individual human users. "
                "The value should be formatted as `Bearer <YOUR_JWT_ACCESS_TOKEN>`."
            )
        }
