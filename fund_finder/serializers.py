# fund_finder/serializers.py
from rest_framework import serializers
from .models import FunderType, FunderProfile, GrantOpportunity
from core.models import Organization

# --- Generic Error Serializer ---
class ErrorResponseSerializer(serializers.Serializer):
    """A generic serializer for representing error messages."""
    detail = serializers.CharField()


# --- Serializers for Read Operations ---

class FunderTypeSerializer(serializers.ModelSerializer):
    """
    Serializer for the FunderType model.
    Used for listing and retrieving funder categories.
    """
    organization_name = serializers.CharField(source='organization.name', read_only=True, default="System-Level")
    
    class Meta:
        model = FunderType
        fields = ('id', 'name', 'organization', 'organization_name', 'is_active')
        read_only_fields = ('id', 'organization_name')


class FunderProfileSerializer(serializers.ModelSerializer):
    """
    Serializer for the FunderProfile model.
    Displays detailed information about a funding organization.
    """
    funder_type = FunderTypeSerializer(read_only=True)
    organization_name = serializers.CharField(source='organization.name', read_only=True, default="Global")

    class Meta:
        model = FunderProfile
        fields = (
            'id', 'name', 'agency_code', 'description', 'website', 'funder_type', 
            'contact_info', 'geographic_focus', 'program_areas', 'is_active', 
            'organization', 'organization_name'
        )
        read_only_fields = ('id', 'funder_type', 'organization_name')


class GrantOpportunitySerializer(serializers.ModelSerializer):
    """
    Serializer for the GrantOpportunity model.
    Provides a comprehensive view of a grant.
    """
    funder = FunderProfileSerializer(read_only=True)

    class Meta:
        model = GrantOpportunity
        fields = '__all__' # Show all fields for detail view
        read_only_fields = ('id', 'funder', 'created_at', 'updated_at', 'created_by', 'updated_by')


# --- Serializers for Write Operations (Create/Update) ---

class FunderTypeWriteSerializer(serializers.ModelSerializer):
    """Serializer for creating/updating FunderType instances."""
    organization = serializers.PrimaryKeyRelatedField(
        queryset=Organization.objects.all(),
        required=False, allow_null=True,
        help_text="The organization this type belongs to. Leave null for a system-level type (Superuser only)."
    )

    class Meta:
        model = FunderType
        fields = ('name', 'organization', 'is_active')


class FunderProfileWriteSerializer(serializers.ModelSerializer):
    """Serializer for creating/updating FunderProfile instances."""
    organization = serializers.PrimaryKeyRelatedField(
        queryset=Organization.objects.all(),
        required=False, allow_null=True,
        help_text="The organization creating this profile. Leave null for a global funder (Superuser only)."
    )
    funder_type = serializers.PrimaryKeyRelatedField(
        queryset=FunderType.objects.all(),
        help_text="The ID of the FunderType for this profile."
    )
    class Meta:
        model = FunderProfile
        fields = ('name', 'agency_code', 'description', 'website', 'funder_type', 'contact_info', 'geographic_focus', 'program_areas', 'is_active', 'organization')


class GrantOpportunityWriteSerializer(serializers.ModelSerializer):
    """Serializer for creating/updating GrantOpportunity instances manually."""
    funder = serializers.PrimaryKeyRelatedField(
        queryset=FunderProfile.objects.all(),
        help_text="The ID of the FunderProfile offering this grant."
    )
    class Meta:
        model = GrantOpportunity
        # Exclude source fields that are for automated ingestion
        exclude = ('source_name', 'source_id')


# --- Serializer for File Upload Endpoint ---
class GrantFileUploadSerializer(serializers.Serializer):
    """
    Validates the file uploaded for grant data ingestion.
    """
    file = serializers.FileField(help_text="A CSV, XML, or ZIP file containing grant data.")

    def validate_file(self, value):
        """Check if the uploaded file has a supported extension."""
        if not value.name.endswith(('.csv', '.xml', '.zip')):
            raise serializers.ValidationError("Unsupported file type. Please upload a .csv, .xml, or .zip file.")
        return value
