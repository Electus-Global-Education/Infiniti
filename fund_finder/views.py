# fund_finder/views.py
from django.db.models import Q
from rest_framework import viewsets, status
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, IsAdminUser
from rest_framework.parsers import MultiPartParser, FormParser
from drf_spectacular.utils import extend_schema, OpenApiParameter, OpenApiTypes
import tempfile
import zipfile
import os
from django.core.management import call_command
import io
import contextlib
from .tasks import index_grant_opportunity_task
from .models import FunderType, FunderProfile, GrantOpportunity
from .serializers import (
    FunderTypeSerializer, FunderProfileSerializer, GrantOpportunitySerializer,
    FunderTypeWriteSerializer, FunderProfileWriteSerializer, GrantOpportunityWriteSerializer,
    GrantFileUploadSerializer, ErrorResponseSerializer
)
# from .services import FundFinderService # Commented out until it's ready
from core.models import Organization
from core.audit_utils import create_audit_log_entry

# --- Base ViewSet for Multi-Tenancy Logic ---

class ScopedViewSet(viewsets.ModelViewSet):
    """
    An abstract ViewSet that provides common multi-tenancy scoping logic.
    - Superusers can see all objects.
    - Org Admins (staff users) can see system-level/global objects plus objects
      belonging to their own organization.
    """
    permission_classes = [IsAuthenticated, IsAdminUser] # Require authenticated staff/superuser

    def get_queryset(self):
        user = self.request.user
        queryset = super().get_queryset() # Use super() to get the original queryset

        if user.is_superuser:
            return queryset
        
        if user.is_staff and hasattr(user, 'organization') and user.organization:
            # Org Admins can see global objects (organization is null) AND objects belonging to their organization
            return queryset.filter(Q(organization__isnull=True) | Q(organization=user.organization))

        # Staff without an organization see nothing by default
        return queryset.none()

    def perform_create(self, serializer):
        """
        Automatically assign the user's organization when an Org Admin creates an object.
        Superusers can assign any organization.
        """
        user = self.request.user
        # For models that have an 'organization' field.
        if 'organization' in serializer.validated_data:
            if user.is_staff and not user.is_superuser and hasattr(user, 'organization') and user.organization:
                # Org Admins can only create objects for their own organization
                serializer.save(created_by=user, updated_by=user, organization=user.organization)
            else:
                # Superuser can specify the organization in the request body
                serializer.save(created_by=user, updated_by=user)
        else:
            # For models without an 'organization' field (none in this app currently for writes)
             serializer.save(created_by=user, updated_by=user)

# --- CRUD ViewSets for Models ---

@extend_schema(tags=['Fund Finder - Funder Types'])
class FunderTypeViewSet(ScopedViewSet):
    """
    API endpoints for managing Funder Types.
    
    Provides CRUD operations for funder categories. Org Admins can create
    types scoped to their organization, and can view both their own types
    and system-level types. Superusers have full access.
    """
    queryset = FunderType.objects.all()
    
    def get_serializer_class(self):
        if self.action in ['create', 'update', 'partial_update']:
            return FunderTypeWriteSerializer
        return FunderTypeSerializer


@extend_schema(tags=['Fund Finder - Funder Profiles'])
class FunderProfileViewSet(ScopedViewSet):
    """
    API endpoints for managing Funder Profiles.
    
    Provides CRUD for funding organizations. Org Admins can create funder
    profiles scoped to their organization and view global profiles.
    Superusers have full access.
    """
    queryset = FunderProfile.objects.select_related('funder_type', 'organization').all()

    def get_serializer_class(self):
        if self.action in ['create', 'update', 'partial_update']:
            return FunderProfileWriteSerializer
        return FunderProfileSerializer


@extend_schema(tags=['Fund Finder - Grant Opportunities'])
class GrantOpportunityViewSet(viewsets.ModelViewSet):
    """
    API endpoints for managing Grant Opportunities.

    - **List & Retrieve:** Any authenticated user can view grant opportunities.
    - **Create, Update, Delete:** Restricted to staff users (Admins).
    """
    queryset = GrantOpportunity.objects.select_related('funder', 'funder__funder_type').all().filter(is_active=True)
    permission_classes = [IsAuthenticated]

    def get_serializer_class(self):
        # For write operations, dynamically lock this down to staff only
        if self.action in ['create', 'update', 'partial_update', 'destroy']:
            self.permission_classes = [IsAdminUser] 
            return GrantOpportunityWriteSerializer
        
        # For read operations (list, retrieve), IsAuthenticated is used.
        return GrantOpportunitySerializer

    def perform_create(self, serializer):
        # When creating manually via API, set the source to 'MANUAL'
        serializer.save(created_by=self.request.user, updated_by=self.request.user, source_name='MANUAL')


# --- File Upload API View ---

@extend_schema(tags=['Fund Finder - Data Ingestion'])
class GrantFileUploadAPIView(APIView):
    """
    API endpoint for uploading a CSV, XML, or ZIP file to bulk-import grants.

    This endpoint is intended for administrative use (e.g., by Superusers or Org Admins
    with special permissions) to populate the grant knowledge base.
    """
    permission_classes = [IsAdminUser] # Only staff/superusers can upload
    parser_classes = (MultiPartParser, FormParser)

    @extend_schema(
        request={"multipart/form-data": GrantFileUploadSerializer},
        responses={
            200: {"description": "File processing complete. See log for details."}, 
            400: ErrorResponseSerializer
        },
        description="Upload a file for processing. The response will contain a log of the import process. Note: This is a synchronous operation for MVP and may time out on very large files."
    )
    def post(self, request, *args, **kwargs):
        serializer = GrantFileUploadSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        
        file = serializer.validated_data['file']
        
        # This will block the HTTP request until processing is done.
        # For a production system, this should be offloaded to a background task queue (e.g., Celery).
        log_output = self._process_uploaded_file(file)
        
        return Response({
            "status": "Processing complete.",
            "log": log_output.splitlines() # Return log as a list of strings
        }, status=status.HTTP_200_OK)

    def _process_file(self, file_path, user):
        """Helper method to run a single management command and capture its output."""
        output_buffer = io.StringIO()
        command_to_run = ''
        filename = os.path.basename(file_path)

        if filename.endswith('.csv'): command_to_run = 'import_grants_from_csv'
        elif filename.endswith('.xml'): command_to_run = 'import_grants_from_xml'
        
        if command_to_run:
            with contextlib.redirect_stdout(output_buffer), contextlib.redirect_stderr(output_buffer):
                try:
                    # Note: Management commands don't have access to the request object.
                    # We can't automatically log the user from there. Logging would need to be
                    # added to the command itself or handled here.
                    call_command(command_to_run, file_path, stdout=output_buffer, stderr=output_buffer)
                except Exception as e:
                    output_buffer.write(f"\nCRITICAL ERROR: Command failed with exception: {e}")
            return output_buffer.getvalue()
        return f"Skipping unsupported file: {filename}"

    def _process_uploaded_file(self, file):
        """Handles single or zipped file processing."""
        if file.name.endswith('.zip'):
            log_entries = [f"Processing ZIP archive: {file.name}"]
            try:
                with tempfile.TemporaryDirectory() as temp_dir:
                    with zipfile.ZipFile(file, 'r') as zip_ref:
                        zip_ref.extractall(temp_dir)
                    
                    for extracted_filename in sorted(os.listdir(temp_dir)):
                        full_file_path = os.path.join(temp_dir, extracted_filename)
                        if os.path.isfile(full_file_path):
                            log_entries.append(self._process_file(full_file_path, self.request.user))
            except Exception as e:
                log_entries.append(f"Error processing ZIP file: {e}")
            return "\n---\n".join(log_entries)
        else: # Handle single CSV/XML
            from django.core.files.storage import FileSystemStorage
            fs = FileSystemStorage()
            filename = fs.save(file.name, file)
            uploaded_file_path = fs.path(filename)
            try:
                return self._process_file(uploaded_file_path, self.request.user)
            finally:
                fs.delete(filename)

class IngestGrantOpportunitiesAPIView(APIView):
    """
    API view to trigger background indexing of all GrantOpportunity records
    whose indexing_status is not already "SUCCESS".

    POST /api/ingest-grants/
      - Enqueues a Celery task (index_grant_opportunity_task) for each grant
        needing indexing.
      - Returns JSON: {
            "triggered_count": <int>,
            "triggered_ids": [<grant_id>, …]
        }

    Permissions:
      - IsAuthenticated
      - IsAdminUser
    """
    permission_classes = [IsAuthenticated, IsAdminUser]

    def post(self, request, *args, **kwargs):
        # Find all grants not yet indexed
        pending = GrantOpportunity.objects.filter(~Q(indexing_status='SUCCESS'))

        triggered_ids = []
        for grant in pending:
            index_grant_opportunity_task.delay(str(grant.id))
            triggered_ids.append(str(grant.id))

        return Response(
            {
                'triggered_count': len(triggered_ids),
                'triggered_ids': triggered_ids,
            },
            status=status.HTTP_200_OK
        )