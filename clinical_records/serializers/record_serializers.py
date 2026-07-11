"""
Clinical Records Serializers
"""
from rest_framework import serializers
from ..models import Patient, ClinicalRecord, ClinicalDocument, ImagingStudy


class PatientSerializer(serializers.ModelSerializer):
    """
    Serializer for Patient model
    """
    full_name = serializers.CharField(source='get_full_name', read_only=True)
    age = serializers.IntegerField(source='get_age', read_only=True)
    
    class Meta:
        model = Patient
        fields = [
            'id', 'rxbackend_patient_id', 'patient_id', 'first_name', 'last_name',
            'full_name', 'date_of_birth', 'age', 'phone_number', 'email',
            'clinic_id', 'clinic_name', 'address', 'gender', 'blood_group',
            'is_active', 'last_synced', 'created_at', 'tenant_id'
        ]
        read_only_fields = ['id', 'last_synced', 'created_at']


class ClinicalRecordSerializer(serializers.ModelSerializer):
    """
    Serializer for Clinical Record model
    """
    patient = PatientSerializer(read_only=True)
    patient_id = serializers.IntegerField(write_only=True, required=False)
    documents_count = serializers.SerializerMethodField()
    
    class Meta:
        model = ClinicalRecord
        fields = [
            'id', 'patient', 'patient_id', 'title', 'description', 'record_type', 
            'status', 'priority', 'is_active', 'is_confidential', 'record_date',
            'created_at', 'updated_at', 'tenant_id', 'documents_count'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at', 'created_by']
    
    def get_documents_count(self, obj):
        """Get count of documents for this record"""
        return obj.documents.count()
    
    def create(self, validated_data):
        """Create record with patient linking"""
        patient_id = validated_data.pop('patient_id', None)
        if patient_id:
            try:
                from ..services.patient_sync_service import get_patient_sync_service
                patient_sync_service = get_patient_sync_service()
                patient = patient_sync_service.get_patient_by_rxbackend_id(patient_id)
                if patient:
                    validated_data['patient'] = patient
            except Exception:
                pass  # Continue without patient if sync fails
        
        return super().create(validated_data)


class ClinicalDocumentSerializer(serializers.ModelSerializer):
    """
    Serializer for Clinical Document model
    """
    file_url = serializers.SerializerMethodField()
    file_name = serializers.SerializerMethodField()
    
    class Meta:
        model = ClinicalDocument
        fields = [
            'id', 'clinical_record', 'title', 'file', 'file_url', 'file_name',
            'file_type', 'file_size', 'mime_type', 'is_encrypted', 'is_processed',
            'processing_status', 'created_at', 'updated_at', 'tenant_id'
        ]
        read_only_fields = ['id', 'file_type', 'file_size', 'mime_type', 'created_at', 'updated_at', 'created_by']
    
    def get_file_url(self, obj):
        """Get file URL"""
        if obj.file:
            request = self.context.get('request')
            if request:
                return request.build_absolute_uri(obj.file.url)
            return obj.file.url
        return None
    
    def get_file_name(self, obj):
        """Get file name"""
        if obj.file:
            return obj.file.name.split('/')[-1]  # Get just the filename
        return None
    
    def create(self, validated_data):
        """Create document with auto-detection of file properties"""
        document = super().create(validated_data)
        
        # File properties are auto-detected in the model's save method
        return document


class PatientRecordSummarySerializer(serializers.ModelSerializer):
    """
    Summary serializer for patient records
    """
    patient_name = serializers.CharField(source='patient.get_full_name', read_only=True)
    documents_count = serializers.SerializerMethodField()
    
    class Meta:
        model = ClinicalRecord
        fields = [
            'id', 'title', 'record_type', 'status', 'record_date',
            'created_at', 'patient_name', 'documents_count'
        ]
    
    def get_documents_count(self, obj):
        """Get count of documents for this record"""
        return obj.documents.count()


class ImagingStudySerializer(serializers.ModelSerializer):
    """
    Serializer for ImagingStudy model
    """
    class Meta:
        # model = ImagingStudy
        # fields = '__all__'
        pass


class RecordRelationshipSerializer(serializers.ModelSerializer):
    """
    Serializer for RecordRelationship model
    """
    class Meta:
        # model = RecordRelationship
        # fields = '__all__'
        pass


class RecordRelationshipCreateSerializer(serializers.ModelSerializer):
    """
    Serializer for creating RecordRelationship instances
    """
    class Meta:
        # model = RecordRelationship
        # fields = '__all__'
        pass


class ShareTokenSerializer(serializers.ModelSerializer):
    """
    Serializer for ShareToken model
    """
    class Meta:
        # model = ShareToken
        # fields = '__all__'
        pass


class WebhookConfigurationSerializer(serializers.ModelSerializer):
    """
    Serializer for webhook configuration management
    """
    class Meta:
        # model = WebhookConfiguration
        # fields = '__all__'
        pass


class WebhookDeliverySerializer(serializers.ModelSerializer):
    """
    Serializer for webhook delivery logs
    """
    class Meta:
        # model = WebhookDelivery
        # fields = '__all__'
        pass