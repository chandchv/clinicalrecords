"""
Admin configuration for Clinical Records
"""
from django.contrib import admin
from .models import (
    Patient, ClinicalRecord, ClinicalDocument, ImagingStudy, 
    RecordRelationship, ShareToken, ManualReview, ReviewerProfile
)


@admin.register(Patient)
class PatientAdmin(admin.ModelAdmin):
    list_display = ['get_full_name', 'patient_id', 'rxbackend_patient_id', 'clinic_name', 'is_active', 'last_synced']
    list_filter = ['is_active', 'clinic_id', 'gender', 'last_synced']
    search_fields = ['first_name', 'last_name', 'patient_id', 'rxbackend_patient_id', 'phone_number', 'email']
    readonly_fields = ['id', 'created_at', 'last_synced']
    date_hierarchy = 'created_at'
    
    fieldsets = (
        ('Patient Information', {
            'fields': ('rxbackend_patient_id', 'patient_id', 'first_name', 'last_name', 'date_of_birth', 'gender', 'blood_group')
        }),
        ('Contact Information', {
            'fields': ('phone_number', 'email', 'address')
        }),
        ('Clinic Information', {
            'fields': ('clinic_id', 'clinic_name', 'tenant_id')
        }),
        ('Status', {
            'fields': ('is_active', 'last_synced', 'created_at')
        }),
    )


@admin.register(ClinicalRecord)
class ClinicalRecordAdmin(admin.ModelAdmin):
    list_display = ['title', 'patient', 'record_type', 'status', 'priority', 'record_date', 'created_by']
    list_filter = ['record_type', 'status', 'priority', 'is_active', 'is_confidential', 'patient__clinic_id']
    search_fields = ['title', 'description', 'patient__first_name', 'patient__last_name', 'patient__patient_id']
    date_hierarchy = 'record_date'
    readonly_fields = ['id', 'created_at', 'updated_at']
    
    fieldsets = (
        ('Record Information', {
            'fields': ('patient', 'title', 'description', 'record_type', 'record_date')
        }),
        ('Status & Priority', {
            'fields': ('status', 'priority', 'is_active', 'is_confidential')
        }),
        ('Metadata', {
            'fields': ('id', 'created_by', 'created_at', 'updated_at', 'tenant_id')
        }),
    )


@admin.register(ClinicalDocument)
class ClinicalDocumentAdmin(admin.ModelAdmin):
    list_display = ['title', 'clinical_record', 'file_type', 'file_size', 'processing_status', 'created_by']
    list_filter = ['file_type', 'is_encrypted', 'is_processed', 'processing_status', 'clinical_record__patient__clinic_id']
    search_fields = ['title', 'clinical_record__title', 'clinical_record__patient__first_name', 'clinical_record__patient__last_name']
    readonly_fields = ['id', 'created_at', 'updated_at', 'file_type', 'file_size', 'mime_type']
    
    fieldsets = (
        ('Document Information', {
            'fields': ('clinical_record', 'title', 'file')
        }),
        ('File Properties', {
            'fields': ('file_type', 'file_size', 'mime_type', 'processing_status')
        }),
        ('Security', {
            'fields': ('is_encrypted', 'is_processed')
        }),
        ('Metadata', {
            'fields': ('id', 'created_by', 'created_at', 'updated_at', 'tenant_id')
        }),
    )


@admin.register(ImagingStudy)
class ImagingStudyAdmin(admin.ModelAdmin):
    list_display = ['study_type', 'modality', 'study_date', 'clinical_record']
    list_filter = ['study_type', 'modality']
    search_fields = ['study_type', 'study_description']
    date_hierarchy = 'study_date'


@admin.register(RecordRelationship)
class RecordRelationshipAdmin(admin.ModelAdmin):
    list_display = ['source_record', 'target_record', 'relationship_type', 'created_by']
    list_filter = ['relationship_type']
    search_fields = ['source_record__title', 'target_record__title']


@admin.register(ShareToken)
class ShareTokenAdmin(admin.ModelAdmin):
    list_display = ['clinical_record', 'token', 'expires_at', 'is_active', 'access_count']
    list_filter = ['is_active', 'expires_at']
    search_fields = ['clinical_record__title', 'token']
    readonly_fields = ['id', 'created_at']


@admin.register(ManualReview)
class ManualReviewAdmin(admin.ModelAdmin):
    list_display = ['clinical_record', 'reviewer', 'status', 'priority', 'assigned_at']
    list_filter = ['status', 'priority']
    search_fields = ['clinical_record__title', 'reviewer__username']
    readonly_fields = ['id', 'assigned_at']


@admin.register(ReviewerProfile)
class ReviewerProfileAdmin(admin.ModelAdmin):
    list_display = ['user', 'specialization', 'max_daily_reviews', 'is_active']
    list_filter = ['specialization', 'is_active']
    search_fields = ['user__username', 'specialization']