# infiniti/urls.py
from django.contrib import admin
from django.urls import path, include # 
from django.conf import settings
from django.conf.urls.static import static
from drf_spectacular.views import SpectacularAPIView, SpectacularRedocView, SpectacularSwaggerView
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView

urlpatterns = [
    # Admin site
    path('admin/', admin.site.urls),

    # Core app (landing page, dashboard, etc.) - Mounted at the project root
    path('', include('core.urls', namespace='core')),

    # Your new API URLs
    path("api/edujob/", include("edujobs.urls")), # 'edujobs' is an app with its own urls.py
    path("api/vector/", include("baserag.urls")), # 'baserag' is an app
    path("api/fini/", include("fini.urls")),       # 'fini' is an app
    path("api/", include(('core.urls', 'core_api'), namespace='core_api')), # 'core' is an app with its own urls.py
    

    # JWT Token Authentication
    path('api/token/', TokenObtainPairView.as_view(), name='token_obtain_pair'),
    path('api/token/refresh/', TokenRefreshView.as_view(), name='token_refresh'),

    # Django REST framework browsable API auth (optional, but useful for development)
    path('api-auth/', include('rest_framework.urls', namespace='rest_framework')),

    # API Schema & Documentation (drf-spectacular for Swagger/ReDoc)
    path('api/schema/', SpectacularAPIView.as_view(), name='schema'),
    path('api/schema/swagger-ui/', SpectacularSwaggerView.as_view(url_name='schema'), name='swagger-ui'),
    path('api/schema/redoc/', SpectacularRedocView.as_view(url_name='schema'), name='redoc'),

    # Django's built-in authentication views (login, logout, password management)
    # These URL names ('login', 'logout', etc.) are used in _top_navbar.html and login.html
    path('accounts/', include('django.contrib.auth.urls')),

]

# Serve media files during development (if DEBUG is True)
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    # Static files are typically served by Django's runserver in DEBUG mode
    # or by Whitenoise. Explicitly adding staticfiles_urlpatterns is usually not needed here
    # if 'django.contrib.staticfiles' is in INSTALLED_APPS and configured correctly.
    # urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
