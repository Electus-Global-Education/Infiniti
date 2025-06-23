# fund_finder/urls.py
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    FunderTypeViewSet,
    FunderProfileViewSet,
    GrantOpportunityViewSet,
    GrantFileUploadAPIView,
    IngestGrantOpportunitiesAPIView,
    RetrieveGrantChunksAPIView,
    GrantRecommendationAPIView,
    GenerateProposalAsyncAPIView,
    ProposalStatusAPIView,
    # FundFinderMatchAPIView # Add this back when its service is ready
)

# Create a router and register our viewsets with it.
router = DefaultRouter()
router.register(r'funder-types', FunderTypeViewSet, basename='fundertype')
router.register(r'funders', FunderProfileViewSet, basename='funderprofile')
router.register(r'grants', GrantOpportunityViewSet, basename='grantopportunity')

# The API URLs are now determined automatically by the router.
# This will create URLs like:
# - /api/fund_finder/funder-types/
# - /api/fund_finder/funder-types/{id}/
# - /api/fund_finder/funders/
# - /api/fund_finder/grants/
# etc.

urlpatterns = [
    # Include the router-generated URLs
    path('', include(router.urls)),
    
    # Add the custom file upload endpoint
    path('upload-grants/', GrantFileUploadAPIView.as_view(), name='grant-file-upload'),
    path('ingest-grants-vectorstore/', IngestGrantOpportunitiesAPIView.as_view(), name='ingest-grants'),
    path('retrieve-chunks/',RetrieveGrantChunksAPIView.as_view(),name='retrieve-grant-chunks'),
    path("recommend-grants/", GrantRecommendationAPIView.as_view(),name="recommend-grants"),
    path("generate-proposal/",GenerateProposalAsyncAPIView.as_view(),name="generate-grant-proposal"),
    path("proposal-status/",ProposalStatusAPIView.as_view(),name="proposal-status"),


]
