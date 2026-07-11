"""
Serializers for timeline functionality.

This module provides serializers for timeline data, including
patient timelines, record details, and search results.
"""

from rest_framework import serializers
from django.contrib.auth import get_user_model

from users.models import Patient
from ..models import ClinicalRecord, ClinicalDocument

User = get_user_model()


class TimelineDocumentSerializer(serializers.ModelSerializer):
    """Serializer for documents in timeline view."""
    
    id = serializers.UUIDField(read_only=True)
    filename = serializers.CharField(source='original_filename', read_only=True)
    file_size_mb = serializers.SerializerMethodField()
    processing_status_display = serializers.SerializerMethodField()
    has_preview = serializers.SerializerMethodField()
    
    class Meta:
        model = ClinicalDocument
        fields = [
            'id', 'filename', 'content_type', 'file_size', 'file_size_mb',
            'processing_status', 'processing_status_display', 'created_at',
            'ocr_confidence', 'has_preview'
        ]
        read_only_fields = fields
    
    def get_file_size_mb(self, obj):
        """Get file size in MB."""
        if obj.file_size:
            return round(obj.file_size / (1024 * 1024), 2)
        return 0
    
    def get_processing_status_display(self, obj):
        """Get human-readable processing status."""
        status_map = {
            'pending': 'Pending Processing',
            'processing': 'Processing...',
            'completed': 'Completed',
            'failed': 'Processing Failed',
            'retry_scheduled': 'Retry Scheduled'
        }
        return status_map.get(obj.processing_status, obj.processing_status)
    
    def get_has_preview(self, obj):
        """Check if document has preview capability."""
        preview_types = ['application/pdf', 'image/jpeg', 'image/png', 'image/gif']
        return obj.content_type in preview_types


class TimelineRecordSerializer(serializers.ModelSerializer):
    """Serializer for clinical records in timeline view."""
    
    id = serializers.UUIDField(read_only=True)
    documents = TimelineDocumentSerializer(many=True, read_only=True)
    documents_count = serializers.SerializerMethodField()
    has_unprocessed_documents = serializers.SerializerMethodField()
    record_type_display = serializers.SerializerMethodField()
    age_days = serializers.SerializerMethodField()
    
    class Meta:
        model = ClinicalRecord
        fields = [
            'id', 'title', 'description', 'record_type', 'record_type_display',
            'created_at', 'updated_at', 'age_days', 'documents', 'documents_count',
            'has_unprocessed_documents'
        ]
        read_only_fields = fields
    
    def get_documents_count(self, obj):
        """Get count of documents."""
        return obj.documents.count()
    
    def get_has_unprocessed_documents(self, obj):
        """Check if record has unprocessed documents."""
        return obj.documents.filter(
            processing_status__in=['pending', 'processing', 'failed']
        ).exists()
    
    def get_record_type_display(self, obj):
        """Get human-readable record type."""
        type_map = {
            'consultation': 'Consultation',
            'lab_result': 'Lab Result',
            'prescription': 'Prescription',
            'imaging': 'Medical Imaging',
            'procedure': 'Medical Procedure',
            'discharge_summary': 'Discharge Summary',
            'referral': 'Referral',
            'progress_note': 'Progress Note'
        }
        return type_map.get(obj.record_type, obj.record_type.replace('_', ' ').title())
    
    def get_age_days(self, obj):
        """Get age of record in days."""
        from django.utils import timezone
        return (timezone.now() - obj.created_at).days


class TimelineItemSerializer(serializers.Serializer):
    """Serializer for timeline items with additional metadata."""
    
    id = serializers.UUIDField()
    title = serializers.CharField()
    description = serializers.CharField()
    record_type = serializers.CharField()
    record_type_display = serializers.CharField()
    created_at = serializers.DateTimeField()
    updated_at = serializers.DateTimeField()
    age_days = serializers.IntegerField()
    documents_count = serializers.IntegerField()
    documents = TimelineDocumentSerializer(many=True)
    has_unprocessed_documents = serializers.BooleanField()
    search_relevance = serializers.FloatField(required=False)
    metadata = serializers.JSONField(required=False)


class TimelinePaginationSerializer(serializers.Serializer):
    """Serializer for timeline pagination information."""
    
    current_page = serializers.IntegerField()
    total_pages = serializers.IntegerField()
    total_records = serializers.IntegerField()
    page_size = serializers.IntegerField()
    has_next = serializers.BooleanField()
    has_previous = serializers.BooleanField()


class TimelineDataSerializer(serializers.Serializer):
    """Serializer for complete timeline data response."""
    
    patient_id = serializers.UUIDField()
    patient_name = serializers.CharField()
    timeline_items = TimelineItemSerializer(many=True)
    pagination = TimelinePaginationSerializer()
    filters_applied = serializers.JSONField()
    generated_at = serializers.DateTimeField()


class TimelineSummarySerializer(serializers.Serializer):
    """Serializer for timeline summary data."""
    
    patient_id = serializers.UUIDField()
    patient_name = serializers.CharField()
    total_records = serializers.IntegerField()
    recent_records = serializers.IntegerField()
    total_documents = serializers.IntegerField()
    recent_documents = serializers.IntegerField()
    record_types = serializers.JSONField()
    date_range_days = serializers.IntegerField()
    first_record_date = serializers.DateTimeField(allow_null=True)
    last_record_date = serializers.DateTimeField(allow_null=True)
    generated_at = serializers.DateTimeField()


class TimelineSearchResultSerializer(serializers.Serializer):
    """Serializer for timeline search results."""
    
    patient_id = serializers.UUIDField()
    search_query = serializers.CharField()
    search_type = serializers.CharField()
    results_count = serializers.IntegerField()
    results = TimelineItemSerializer(many=True)


class RecordDetailSerializer(serializers.Serializer):
    """Serializer for detailed record information."""
    
    id = serializers.UUIDField()
    title = serializers.CharField()
    description = serializers.CharField()
    record_type = serializers.CharField()
    created_at = serializers.DateTimeField()
    updated_at = serializers.DateTimeField()
    patient = serializers.JSONField()
    clinic = serializers.JSONField()
    documents = TimelineDocumentSerializer(many=True)
    relationships = serializers.JSONField()
    metadata = serializers.JSONField()


class TimelineFilterSerializer(serializers.Serializer):
    """Serializer for timeline filter parameters."""
    
    start_date = serializers.DateTimeField(required=False)
    end_date = serializers.DateTimeField(required=False)
    record_types = serializers.ListField(
        child=serializers.CharField(),
        required=False
    )
    has_documents = serializers.BooleanField(required=False)
    processing_status = serializers.ChoiceField(
        choices=[
            ('pending', 'Pending'),
            ('processing', 'Processing'),
            ('completed', 'Completed'),
            ('failed', 'Failed'),
            ('retry_scheduled', 'Retry Scheduled')
        ],
        required=False
    )
    
    def validate(self, data):
        """Validate filter parameters."""
        if 'start_date' in data and 'end_date' in data:
            if data['start_date'] > data['end_date']:
                raise serializers.ValidationError(
                    "Start date must be before end date"
                )
        
        return data


class TimelinePreferencesSerializer(serializers.Serializer):
    """Serializer for user timeline preferences."""
    
    default_page_size = serializers.IntegerField(
        min_value=10,
        max_value=100,
        default=20
    )
    default_date_range = serializers.IntegerField(
        min_value=1,
        max_value=365,
        default=30
    )
    show_document_previews = serializers.BooleanField(default=True)
    auto_refresh_interval = serializers.IntegerField(
        min_value=0,
        max_value=300,
        default=0
    )
    
    def validate_auto_refresh_interval(self, value):
        """Validate auto refresh interval."""
        if value > 0 and value < 30:
            raise serializers.ValidationError(
                "Auto refresh interval must be at least 30 seconds or 0 to disable"
            )
        return value


class TimelineExportSerializer(serializers.Serializer):
    """Serializer for timeline export parameters."""
    
    format = serializers.ChoiceField(
        choices=[('json', 'JSON'), ('csv', 'CSV')],
        default='json'
    )
    include_documents = serializers.BooleanField(default=True)
    include_metadata = serializers.BooleanField(default=True)
    date_range_days = serializers.IntegerField(
        min_value=1,
        max_value=3650,  # 10 years
        required=False
    )


class PatientTimelineContextSerializer(serializers.Serializer):
    """Serializer for patient timeline page context."""
    
    patient_id = serializers.UUIDField()
    patient_name = serializers.CharField()
    clinic_name = serializers.CharField()
    timeline_summary = TimelineSummarySerializer()
    available_record_types = serializers.ListField(
        child=serializers.CharField()
    )
    user_permissions = serializers.JSONField()
    preferences = TimelinePreferencesSerializer()


class TimelineStatsSerializer(serializers.Serializer):
    """Serializer for timeline statistics."""
    
    total_records = serializers.IntegerField()
    records_by_type = serializers.JSONField()
    records_by_month = serializers.JSONField()
    documents_by_type = serializers.JSONField()
    processing_status_counts = serializers.JSONField()
    average_documents_per_record = serializers.FloatField()
    most_recent_record_date = serializers.DateTimeField(allow_null=True)
    oldest_record_date = serializers.DateTimeField(allow_null=True)


class TimelineActivitySerializer(serializers.Serializer):
    """Serializer for recent timeline activity."""
    
    recent_records = TimelineItemSerializer(many=True)
    recent_documents = TimelineDocumentSerializer(many=True)
    pending_processing = serializers.IntegerField()
    failed_processing = serializers.IntegerField()
    activity_summary = serializers.CharField()


# Utility serializers for common data structures
class PatientBasicSerializer(serializers.ModelSerializer):
    """Basic patient information for timeline context."""
    
    id = serializers.UUIDField(read_only=True)
    full_name = serializers.SerializerMethodField()
    
    class Meta:
        model = Patient
        fields = ['id', 'full_name', 'date_of_birth', 'phone_number']
        read_only_fields = fields
    
    def get_full_name(self, obj):
        """Get patient's full name."""
        return obj.get_full_name()


class ClinicBasicSerializer(serializers.Serializer):
    """Basic clinic information for timeline context."""
    
    id = serializers.UUIDField()
    name = serializers.CharField()
    address = serializers.CharField(required=False)