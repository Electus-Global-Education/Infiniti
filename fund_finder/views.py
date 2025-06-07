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

from .models import FunderType, FunderProfile, GrantOpportunity
from .serializers import (
    FunderTypeSerializer, FunderProfileSerializer, GrantOpportunitySerializer,
    FunderTypeWriteSerializer, FunderProfileWriteSerializer, GrantOpportunityWriteSerializer,
    GrantFileUploadSerializer
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
        if 'organization' in serializer.validated_data:
            if user.is_staff and not user.is_superuser and hasattr(user, 'organization') and user.organization:
                # Org Admins can only create objects for their own organization
                serializer.save(created_by=user, updated_by=user, organization=user.organization)
            else:
                # Superuser can specify the organization in the request body
                serializer.save(created_by=user, updated_by=user)
        else:
             serializer.save(created_by=user, updated_by=user)

# --- CRUD ViewSets for Models ---

@extend_schema(tags=['Fund Finder - Funder Types'])
class FunderTypeViewSet(ScopedViewSet):
    queryset = FunderType.objects.all()
    
    def get_serializer_class(self):
        if self.action in ['create', 'update', 'partial_update']:
            return FunderTypeWriteSerializer
        return FunderTypeSerializer


@extend_schema(tags=['Fund Finder - Funder Profiles'])
class FunderProfileViewSet(ScopedViewSet):
    queryset = FunderProfile.objects.select_related('funder_type', 'organization').all()

    def get_serializer_class(self):
        if self.action in ['create', 'update', 'partial_update']:
            return FunderProfileWriteSerializer
        return FunderProfileSerializer


@extend_schema(tags=['Fund Finder - Grant Opportunities'])
class GrantOpportunityViewSet(viewsets.ModelViewSet):
    queryset = GrantOpportunity.objects.select_related('funder', 'funder__funder_type').all()
    
    # --- PERMISSION CHANGE ---
    # Changed from IsAdminUser to IsAuthenticated to allow any logged-in user to VIEW grants.
    # Write permissions (POST, PUT, DELETE) will be restricted to staff/admins inside get_serializer_class.
    permission_classes = [IsAuthenticated]

    def get_serializer_class(self):
        # For write operations, lock this down to staff only
        if self.action in ['create', 'update', 'partial_update', 'destroy']:
            # This dynamically applies a stricter permission check for write actions.
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
    permission_classes = [IsAdminUser]
    parser_classes = (MultiPartParser, FormParser)

    @extend_schema(
        request={"multipart/form-data": GrantFileUploadSerializer},
        responses={200: {"description": "File processing complete. See log for details."}, 400: "Invalid file or request."},
        description="Upload a file for processing. The response will contain a log of the import process."
    )
    def post(self, request, *args, **kwargs):
        serializer = GrantFileUploadSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        
        file = serializer.validated_data['file']
        log_output = self._process_uploaded_file(file)
        
        return Response({
            "status": "Processing complete.",
            "log": log_output.splitlines()
        }, status=status.HTTP_200_OK)

    def _process_file(self, file_path, user):
        output_buffer = io.StringIO()
        command_to_run = ''
        filename = os.path.basename(file_path)

        if filename.endswith('.csv'): command_to_run = 'import_grants_from_csv'
        elif filename.endswith('.xml'): command_to_run = 'import_grants_from_xml'
        
        if command_to_run:
            with contextlib.redirect_stdout(output_buffer), contextlib.redirect_stderr(output_buffer):
                try:
                    call_command(command_to_run, file_path, stdout=output_buffer, stderr=output_buffer)
                except Exception as e:
                    output_buffer.write(f"\nCRITICAL ERROR: Command failed with exception: {e}")
            return output_buffer.getvalue()
        return f"Skipping unsupported file: {filename}"

    def _process_uploaded_file(self, file):
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
        else:
            from django.core.files.storage import FileSystemStorage
            fs = FileSystemStorage()
            filename = fs.save(file.name, file)
            uploaded_file_path = fs.path(filename)
            try:
                return self._process_file(uploaded_file_path, self.request.user)
            finally:
                fs.delete(filename)
