# infiniti/urls.py
from django.contrib import admin
from django.urls import path, include # Make sure to import include
from django.conf import settings
from django.conf.urls.static import static
from drf_spectacular.views import SpectacularAPIView, SpectacularRedocView, SpectacularSwaggerView

urlpatterns = [
    path('admin/', admin.site.urls),

    # Include URLs from your 'core' app, mounted at the project root
    path('', include('core.urls', namespace='core')),

    # Django REST framework and auth URLs (if you use them)
    path('api-auth/', include('rest_framework.urls', namespace='rest_framework')),

    # API Schema for drf-spectacular:
    path('api/schema/', SpectacularAPIView.as_view(), name='schema'),
    path('api/schema/swagger-ui/', SpectacularSwaggerView.as_view(url_name='schema'), name='swagger-ui'),
    path('api/schema/redoc/', SpectacularRedocView.as_view(url_name='schema'), name='redoc'),

    # Django's built-in auth views for login/logout (if not using DRF for all auth)
    # These URL names ('login', 'logout') are used in the _top_navbar.html
    path('accounts/', include('django.contrib.auth.urls')),
]

# Serve media files during development
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    # In development, Django's runserver can serve static files if DEBUG=True and
    # 'django.contrib.staticfiles' is in INSTALLED_APPS.
    # Whitenoise is more for production, but this ensures static files are served in dev too.
    # urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT) # Usually not needed if using runserver in DEBUG
