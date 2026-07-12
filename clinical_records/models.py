"""
Simplified Clinical Records Models for standalone service
"""
from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone
import uuid


class TenantAwareModel(models.Model):
    """
    Base model for tenant-aware models
    """
    tenant_id = models.IntegerField(default=1)  # Simplified tenant handling
    
    class Meta:
        abstract = True


class Patient(TenantAwareModel):
    """
    Patient model synced from RxBackend
    """
    rxbackend_patient_id = models.IntegerField(unique=True, db_index=True, help_text="Patient ID from RxBackend")
    patient_id = models.CharField(max_length=50, help_text="Patient identifier")
    first_name = models.CharField(max_length=100)
    last_name = models.CharField(max_length=100)
    date_of_birth = models.DateField(null=True, blank=True)
    phone_number = models.CharField(max_length=17, blank=True)
    email = models.EmailField(blank=True, null=True)
    clinic_id = models.IntegerField(help_text="Reference to RxBackend clinic")
    clinic_name = models.CharField(max_length=255, blank=True, help_text="Clinic name from RxBackend")
    address = models.TextField(blank=True)
    gender = models.CharField(max_length=1, choices=[('M', 'Male'), ('F', 'Female'), ('O', 'Other')], blank=True)
    blood_group = models.CharField(max_length=3, blank=True)
    is_active = models.BooleanField(default=True)
    last_synced = models.DateTimeField(auto_now=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        db_table = 'patients'
        ordering = ['first_name', 'last_name']
        indexes = [
            models.Index(fields=['rxbackend_patient_id']),
            models.Index(fields=['clinic_id']),
            models.Index(fields=['patient_id']),
        ]
    
    def __str__(self):
        return f"{self.first_name} {self.last_name} ({self.patient_id})"
    
    def get_full_name(self):
        return f"{self.first_name} {self.last_name}"
    
    def get_age(self):
        if self.date_of_birth:
            today = timezone.now().date()
            dob = self.date_of_birth
            # Handle case where date_of_birth might be stored as string
            if isinstance(dob, str):
                from datetime import datetime
                try:
                    dob = datetime.strptime(dob, '%Y-%m-%d').date()
                except (ValueError, TypeError):
                    return None
            return today.year - dob.year - (
                (today.month, today.day) < 
                (dob.month, dob.day)
            )
        return None


class ClinicalRecord(TenantAwareModel):
    """
    Clinical Record Model
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    patient = models.ForeignKey(Patient, on_delete=models.CASCADE, related_name='clinical_records', null=True, blank=True)
    title = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    record_type = models.CharField(max_length=100)
    status = models.CharField(max_length=50, default='active')
    priority = models.CharField(max_length=20, default='normal')
    is_active = models.BooleanField(default=True)
    is_confidential = models.BooleanField(default=False)
    is_sealed = models.BooleanField(default=False, help_text="Sealed by patient")
    external_id = models.CharField(max_length=100, blank=True, null=True, db_index=True, help_text="ID from external system (e.g. RxBackend)")
    record_date = models.DateField()
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(User, on_delete=models.CASCADE)
    
    class Meta:
        db_table = 'clinical_records'
        ordering = ['-record_date', '-created_at']
        indexes = [
            models.Index(fields=['patient', '-record_date']),
            models.Index(fields=['record_type']),
            models.Index(fields=['status']),
        ]
    
    def __str__(self):
        return f"{self.title} ({self.record_type})"


class ClinicalDocument(TenantAwareModel):
    """
    Clinical Document Model
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    clinical_record = models.ForeignKey(ClinicalRecord, on_delete=models.CASCADE, related_name='documents')
    title = models.CharField(max_length=255)
    file = models.FileField(upload_to='clinical_documents/%Y/%m/%d/', help_text="Upload clinical document", null=True, blank=True)
    file_type = models.CharField(max_length=50, blank=True, help_text="Auto-detected file type")
    file_size = models.BigIntegerField(null=True, blank=True, help_text="File size in bytes")
    mime_type = models.CharField(max_length=100, blank=True, help_text="MIME type")
    is_encrypted = models.BooleanField(default=False)
    is_processed = models.BooleanField(default=False)
    processing_status = models.CharField(max_length=50, default='pending', choices=[
        ('pending', 'Pending'),
        ('processing', 'Processing'),
        ('completed', 'Completed'),
        ('failed', 'Failed'),
    ])
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(User, on_delete=models.CASCADE)
    
    class Meta:
        db_table = 'clinical_documents'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['clinical_record', '-created_at']),
            models.Index(fields=['processing_status']),
        ]
    
    def __str__(self):
        return f"{self.title} ({self.file_type or 'Unknown'})"
    
    def save(self, *args, **kwargs):
        # Auto-detect file type and size if not provided
        if self.file and not self.file_type:
            import os
            _, ext = os.path.splitext(self.file.name)
            self.file_type = ext.lstrip('.').upper() if ext else 'UNKNOWN'
        
        if self.file and not self.file_size:
            try:
                self.file_size = self.file.size
            except (OSError, AttributeError):
                pass
        
        if self.file and not self.mime_type:
            # Try to detect MIME type
            import mimetypes
            mime_type, _ = mimetypes.guess_type(self.file.name)
            self.mime_type = mime_type or 'application/octet-stream'
        
        super().save(*args, **kwargs)


class ImagingStudy(TenantAwareModel):
    """
    Imaging Study Model
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    clinical_record = models.ForeignKey(ClinicalRecord, on_delete=models.CASCADE, related_name='imaging_studies')
    study_type = models.CharField(max_length=100)
    modality = models.CharField(max_length=50)
    study_date = models.DateField()
    study_description = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        db_table = 'imaging_studies'
        verbose_name_plural = 'Imaging Studies'
    
    def __str__(self):
        return f"{self.study_type} - {self.modality}"


class RecordRelationship(TenantAwareModel):
    """
    Record Relationship Model
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    source_record = models.ForeignKey(ClinicalRecord, on_delete=models.CASCADE, related_name='source_relationships')
    target_record = models.ForeignKey(ClinicalRecord, on_delete=models.CASCADE, related_name='target_relationships')
    relationship_type = models.CharField(max_length=100)
    description = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(User, on_delete=models.CASCADE)
    
    class Meta:
        db_table = 'record_relationships'
    
    def __str__(self):
        return f"{self.source_record.title} -> {self.target_record.title}"


class ShareToken(TenantAwareModel):
    """
    Share Token Model
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    clinical_record = models.ForeignKey(ClinicalRecord, on_delete=models.CASCADE, related_name='share_tokens')
    token = models.CharField(max_length=255, unique=True)
    expires_at = models.DateTimeField()
    is_active = models.BooleanField(default=True)
    access_count = models.IntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(User, on_delete=models.CASCADE)
    
    class Meta:
        db_table = 'share_tokens'
    
    def __str__(self):
        return f"Token for {self.clinical_record.title}"


class ManualReview(TenantAwareModel):
    """
    Manual Review Model
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    clinical_record = models.ForeignKey(ClinicalRecord, on_delete=models.CASCADE, related_name='manual_reviews')
    reviewer = models.ForeignKey(User, on_delete=models.CASCADE)
    status = models.CharField(max_length=50, default='pending')
    priority = models.CharField(max_length=20, default='normal')
    assigned_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    notes = models.TextField(blank=True)
    
    class Meta:
        db_table = 'manual_reviews'
    
    def __str__(self):
        return f"Review of {self.clinical_record.title} by {self.reviewer.username}"
    
    @property
    def patient_name(self):
        return "Patient Name"  # Simplified for standalone service
    
    @property
    def clinic_name(self):
        return "Clinic Name"  # Simplified for standalone service
    
    @property
    def document_filename(self):
        return "Document.pdf"  # Simplified for standalone service


class ReviewerProfile(TenantAwareModel):
    """
    Reviewer Profile Model
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    specialization = models.CharField(max_length=100)
    max_daily_reviews = models.IntegerField(default=10)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        db_table = 'reviewer_profiles'
    
    def __str__(self):
        return f"Profile for {self.user.username}"
    
    @property
    def workload_score(self):
        return 0  # Simplified for standalone service