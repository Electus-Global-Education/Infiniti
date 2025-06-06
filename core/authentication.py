# core/authentication.py
from urllib.parse import urlparse
from rest_framework.authentication import BaseAuthentication
from rest_framework.exceptions import AuthenticationFailed
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
            # Find the application associated with the provided API key
            application = RegisteredApplication.objects.select_related('organization', 'created_by').get(api_key=api_key)
        except RegisteredApplication.DoesNotExist:
            raise AuthenticationFailed('Invalid API Key. Application not found.')

        if not application.is_active:
            raise AuthenticationFailed('This application is inactive.')
        
        if not application.organization.is_active:
            raise AuthenticationFailed('The organization for this application is inactive.')

        # --- Origin/URL Validation ---
        # This provides an extra layer of security for client-side requests (e.g., from a browser)
        # For server-to-server communication, these headers might not be present.
        # We'll make this check optional or handle cases where headers are absent.
        request_origin = self.get_request_origin(request)
        
        if application.base_url and request_origin:
            if not self.is_origin_allowed(request_origin, application.base_url):
                raise AuthenticationFailed(f'Request origin "{request_origin}" does not match the registered base URL.')
        
        # If authentication is successful, we can return the user who created the app
        # or a generic service user. Returning the app's creator can be useful for permissions.
        # For now, we'll associate the request with the user who created the application.
        # This user will be available as `request.user`. The application itself will be on `request.auth`.
        user = application.created_by or application.organization.users.filter(is_staff=True).first()

        if not user:
             # Fallback if no specific user is linked. This is a critical design decision.
             # We should not proceed without a user context.
             raise AuthenticationFailed('No valid user associated with the authenticated application.')

        return (user, application) # Success. `request.user` will be the user, `request.auth` will be the application.
    
    def get_request_origin(self, request):
        # HTTP_ORIGIN is typically sent by browsers for CORS requests.
        # HTTP_REFERER is less reliable but can be a fallback.
        http_origin = request.META.get('HTTP_ORIGIN')
        if http_origin:
            return http_origin
        
        http_referer = request.META.get('HTTP_REFERER')
        if http_referer:
            # The referer includes the path, so we only want the scheme and netloc (domain)
            return f"{urlparse(http_referer).scheme}://{urlparse(http_referer).netloc}"
            
        return None

    def is_origin_allowed(self, request_origin, registered_base_url):
        # Compare the scheme and netloc (domain + port) of the origins
        try:
            req_parsed = urlparse(request_origin)
            reg_parsed = urlparse(registered_base_url)
            
            # Check if domain and scheme match
            return req_parsed.scheme == reg_parsed.scheme and req_parsed.netloc == reg_parsed.netloc
        except Exception:
            return False

    def authenticate_header(self, request):
        return self.keyword
