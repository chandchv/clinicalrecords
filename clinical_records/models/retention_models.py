"""
Data retention and deletion policy models.

This module defines models for managing data retention policies,
archival processes, and secure deletion workflows for clinical records.
"""

import uuid
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, List

from django.db import models
from django.utils import timezone
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError

from users.models import Clinic, Patient, TenantAwareModel

User = get_user_model()


class RetentionPolicy(TenantAwareModel):
    """
    Model for defining data retention policies per clinic.
    
    This model allows clinics to configure how long different types
    of clinical data should be retained before archival or deletion.
    """
    
    POLICY_TYPES = [
        ('clinical_records', 'Clinical Records'),
        ('documents', 'Clinical Documents'),
        ('audit_logs', 'Audit Logs'),
        ('patient_data', 'Patient Data'),
        ('imaging_studies', 'Imaging Studies'),
        ('lab_results', 'Lab Results'),
        ('prescriptions', 'Prescriptions'),
        ('appointments', 'Appointments'),
    ]
    
    ACTION_TYPES = [
        ('archive', 'Archive Data'),
        ('delete', 'Delete Data'),
        ('anonymize', 'Anonymize Data'),
        ('review', 'Manual Review Required'),
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=200, help_text="Policy name")
    description = models.TextField(blank=True, help_text="Policy description")
    
    # Policy configuration
    data_type = models.CharField(
        max_length=50, 
        choices=POLICY_TYPES,
        help_text="Type of data this policy applies to"
    )
    retention_period_days = models.PositiveIntegerField(
        help_text="Number of days to retain data before action"
    )
    action_after_retention = models.CharField(
        max_length=20,
        choices=ACTION_TYPES,
        default='archive',
        help_text="Action to take after retention period"
    )
    
    # Advanced settings
    grace_period_days = models.PositiveIntegerField(
        default=30,
        help_text="Grace period before final action (for review/appeals)"
    )
    require_approval = models.BooleanField(
        default=False,
        help_text="Require manual approval before action"
    )
    notify_before_days = models.PositiveIntegerField(
        default=30,
        help_text="Days before action to send notifications"
    )
    
    # Legal and compliance
    legal_basis = models.TextField(
        blank=True,
        help_text="Legal basis for retention policy"
    )
    regulatory_requirement = models.CharField(
        max_length=200,
        blank=True,
        help_text="Regulatory requirement (e.g., HIPAA, GDPR)"
    )
    
    # Status and metadata
    is_active = models.BooleanField(default=True)
    created_by = models.ForeignKey(
        User,
        on_delete=models.PROTECT,
        related_name='created_retention_policies'
    )
    approved_by = models.ForeignKey(
        User,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='approved_retention_policies'
    )
    approved_at = models.DateTimeField(null=True, blank=True)
    
    class Meta:
        db_table = 'clinical_retention_policies'
        unique_together = ['clinic', 'data_type']
        indexes = [
            models.Index(fields=['clinic', 'data_type']),
            models.Index(fields=['is_active']),
        ]
    
    def __str__(self):
        return f"{self.name} ({self.clinic.name})"
    
    def clean(self):
        """Validate retention policy configuration."""
        if self.retention_period_days <= 0:
            raise ValidationError("Retention period must be positive")
        
        if self.grace_period_days < 0:
            raise ValidationError("Grace period cannot be negative")
        
        if self.notify_before_days > self.retention_period_days:
            raise ValidationError("Notification period cannot exceed retention period")
    
    def get_action_date(self, created_date: datetime) -> datetime:
        """Calculate when action should be taken for given creation date."""
        return created_date + timedelta(days=self.retention_period_days)
    
    def get_notification_date(self, created_date: datetime) -> datetime:
        """Calculate when notification should be sent for given creation date."""
        action_date = self.get_action_date(created_date)
        return action_date - timedelta(days=self.notify_before_days)
    
    def is_due_for_action(self, created_date: datetime) -> bool:
        """Check if data created on given date is due for action."""
        return timezone.now() >= self.get_action_date(created_date)
    
    def is_due_for_notification(self, created_date: datetime) -> bool:
        """Check if notification should be sent for data created on given date."""
        return timezone.now() >= self.get_notification_date(created_date)


class RetentionJob(TenantAwareModel):
    """
    Model for tracking retention policy execution jobs.
    
    This model tracks the execution of retention policies,
    including status, progress, and results.
    """
    
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('running', 'Running'),
        ('completed', 'Completed'),
        ('failed', 'Failed'),
        ('cancelled', 'Cancelled'),
        ('requires_approval', 'Requires Approval'),
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    policy = models.ForeignKey(
        RetentionPolicy,
        on_delete=models.CASCADE,
        related_name='jobs'
    )
    
    # Job details
    job_type = models.CharField(
        max_length=20,
        choices=RetentionPolicy.ACTION_TYPES,
        help_text="Type of retention action"
    )
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default='pending'
    )
    
    # Execution details
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    started_by = models.ForeignKey(
        User,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='started_retention_jobs'
    )
    
    # Progress tracking
    total_items = models.PositiveIntegerField(default=0)
    processed_items = models.PositiveIntegerField(default=0)
    successful_items = models.PositiveIntegerField(default=0)
    failed_items = models.PositiveIntegerField(default=0)
    
    # Results and errors
    error_message = models.TextField(blank=True)
    execution_log = models.JSONField(default=dict, blank=True)
    
    # Approval workflow
    requires_approval = models.BooleanField(default=False)
    approved_by = models.ForeignKey(
        User,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='approved_retention_jobs'
    )
    approved_at = models.DateTimeField(null=True, blank=True)
    approval_notes = models.TextField(blank=True)
    
    class Meta:
        db_table = 'clinical_retention_jobs'
        indexes = [
            models.Index(fields=['clinic', 'status']),
            models.Index(fields=['policy', 'created_at']),
            models.Index(fields=['started_at']),
        ]
    
    def __str__(self):
        return f"Retention Job {self.id} - {self.policy.name}"
    
    @property
    def progress_percentage(self) -> float:
        """Calculate job progress percentage."""
        if self.total_items == 0:
            return 0.0
        return (self.processed_items / self.total_items) * 100
    
    @property
    def success_rate(self) -> float:
        """Calculate job success rate."""
        if self.processed_items == 0:
            return 0.0
        return (self.successful_items / self.processed_items) * 100
    
    def start_job(self, user: User = None):
        """Mark job as started."""
        self.status = 'running'
        self.started_at = timezone.now()
        self.started_by = user
        self.save(update_fields=['status', 'started_at', 'started_by'])
    
    def complete_job(self):
        """Mark job as completed."""
        self.status = 'completed'
        self.completed_at = timezone.now()
        self.save(update_fields=['status', 'completed_at'])
    
    def fail_job(self, error_message: str):
        """Mark job as failed with error message."""
        self.status = 'failed'
        self.completed_at = timezone.now()
        self.error_message = error_message
        self.save(update_fields=['status', 'completed_at', 'error_message'])


class DataArchive(TenantAwareModel):
    """
    Model for tracking archived clinical data.
    
    This model maintains metadata about archived data for
    compliance and potential restoration purposes.
    """
    
    ARCHIVE_TYPES = [
        ('clinical_record', 'Clinical Record'),
        ('clinical_document', 'Clinical Document'),
        ('patient_data', 'Patient Data'),
        ('audit_log', 'Audit Log'),
    ]
    
    STORAGE_TYPES = [
        ('local_archive', 'Local Archive Storage'),
        ('s3_glacier', 'AWS S3 Glacier'),
        ('azure_archive', 'Azure Archive Storage'),
        ('tape_backup', 'Tape Backup'),
        ('cold_storage', 'Cold Storage'),
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    
    # Original data reference
    original_id = models.UUIDField(help_text="ID of original data item")
    data_type = models.CharField(
        max_length=50,
        choices=ARCHIVE_TYPES,
        help_text="Type of archived data"
    )
    
    # Archive details
    archive_path = models.TextField(help_text="Path to archived data")
    storage_type = models.CharField(
        max_length=50,
        choices=STORAGE_TYPES,
        default='local_archive'
    )
    archive_size_bytes = models.BigIntegerField(default=0)
    
    # Metadata
    original_created_at = models.DateTimeField(
        help_text="Original creation date of the data"
    )
    archived_by_policy = models.ForeignKey(
        RetentionPolicy,
        on_delete=models.PROTECT,
        related_name='archived_items'
    )
    archived_by_job = models.ForeignKey(
        RetentionJob,
        on_delete=models.PROTECT,
        related_name='archived_items'
    )
    
    # Patient reference (for patient data requests)
    patient = models.ForeignKey(
        Patient,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='archived_data'
    )
    
    # Archive integrity
    checksum = models.CharField(
        max_length=128,
        blank=True,
        help_text="Checksum for data integrity verification"
    )
    encryption_key_id = models.CharField(
        max_length=100,
        blank=True,
        help_text="ID of encryption key used for archive"
    )
    
    # Compliance and legal
    legal_hold = models.BooleanField(
        default=False,
        help_text="Data is under legal hold and cannot be deleted"
    )
    legal_hold_reason = models.TextField(
        blank=True,
        help_text="Reason for legal hold"
    )
    legal_hold_expires = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When legal hold expires"
    )
    
    # Restoration tracking
    restoration_count = models.PositiveIntegerField(
        default=0,
        help_text="Number of times data has been restored"
    )
    last_restored_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Last restoration timestamp"
    )
    
    class Meta:
        db_table = 'clinical_data_archives'
        indexes = [
            models.Index(fields=['clinic', 'data_type']),
            models.Index(fields=['original_id', 'data_type']),
            models.Index(fields=['patient']),
            models.Index(fields=['legal_hold']),
            models.Index(fields=['archived_by_policy']),
        ]
    
    def __str__(self):
        return f"Archive {self.id} - {self.data_type}"
    
    def is_under_legal_hold(self) -> bool:
        """Check if data is currently under legal hold."""
        if not self.legal_hold:
            return False
        
        if self.legal_hold_expires and timezone.now() > self.legal_hold_expires:
            return False
        
        return True
    
    def can_be_deleted(self) -> bool:
        """Check if archived data can be permanently deleted."""
        return not self.is_under_legal_hold()


class DeletionRequest(TenantAwareModel):
    """
    Model for tracking data deletion requests.
    
    This model handles patient requests for data deletion
    (right to erasure) and administrative deletion requests.
    """
    
    REQUEST_TYPES = [
        ('patient_erasure', 'Patient Right to Erasure'),
        ('administrative', 'Administrative Deletion'),
        ('legal_requirement', 'Legal Requirement'),
        ('data_breach', 'Data Breach Response'),
    ]
    
    STATUS_CHOICES = [
        ('pending', 'Pending Review'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected'),
        ('in_progress', 'In Progress'),
        ('completed', 'Completed'),
        ('failed', 'Failed'),
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    
    # Request details
    request_type = models.CharField(
        max_length=50,
        choices=REQUEST_TYPES,
        help_text="Type of deletion request"
    )
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default='pending'
    )
    
    # Requestor information
    requested_by = models.ForeignKey(
        User,
        on_delete=models.PROTECT,
        related_name='deletion_requests'
    )
    patient = models.ForeignKey(
        Patient,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='deletion_requests',
        help_text="Patient whose data is to be deleted (if applicable)"
    )
    
    # Request scope
    deletion_scope = models.JSONField(
        default=dict,
        help_text="Scope of data to be deleted (data types, date ranges, etc.)"
    )
    reason = models.TextField(help_text="Reason for deletion request")
    legal_basis = models.TextField(
        blank=True,
        help_text="Legal basis for deletion"
    )
    
    # Approval workflow
    reviewed_by = models.ForeignKey(
        User,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='reviewed_deletion_requests'
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)
    review_notes = models.TextField(blank=True)
    
    # Execution tracking
    executed_by = models.ForeignKey(
        User,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='executed_deletion_requests'
    )
    executed_at = models.DateTimeField(null=True, blank=True)
    completion_report = models.JSONField(
        default=dict,
        blank=True,
        help_text="Report of deletion execution results"
    )
    
    # Compliance
    compliance_verified = models.BooleanField(
        default=False,
        help_text="Compliance with deletion requirements verified"
    )
    verification_notes = models.TextField(
        blank=True,
        help_text="Notes on compliance verification"
    )
    
    class Meta:
        db_table = 'clinical_deletion_requests'
        indexes = [
            models.Index(fields=['clinic', 'status']),
            models.Index(fields=['patient']),
            models.Index(fields=['request_type']),
            models.Index(fields=['created_at']),
        ]
    
    def __str__(self):
        return f"Deletion Request {self.id} - {self.request_type}"
    
    def approve_request(self, user: User, notes: str = ""):
        """Approve the deletion request."""
        self.status = 'approved'
        self.reviewed_by = user
        self.reviewed_at = timezone.now()
        self.review_notes = notes
        self.save(update_fields=['status', 'reviewed_by', 'reviewed_at', 'review_notes'])
    
    def reject_request(self, user: User, notes: str):
        """Reject the deletion request."""
        self.status = 'rejected'
        self.reviewed_by = user
        self.reviewed_at = timezone.now()
        self.review_notes = notes
        self.save(update_fields=['status', 'reviewed_by', 'reviewed_at', 'review_notes'])
    
    def start_execution(self, user: User):
        """Start executing the deletion request."""
        self.status = 'in_progress'
        self.executed_by = user
        self.executed_at = timezone.now()
        self.save(update_fields=['status', 'executed_by', 'executed_at'])
    
    def complete_execution(self, completion_report: Dict[str, Any]):
        """Complete the deletion request execution."""
        self.status = 'completed'
        self.completion_report = completion_report
        self.save(update_fields=['status', 'completion_report'])


class RetentionNotification(TenantAwareModel):
    """
    Model for tracking retention policy notifications.
    
    This model tracks notifications sent regarding upcoming
    retention actions and their responses.
    """
    
    NOTIFICATION_TYPES = [
        ('upcoming_action', 'Upcoming Retention Action'),
        ('action_completed', 'Retention Action Completed'),
        ('approval_required', 'Approval Required'),
        ('deletion_warning', 'Deletion Warning'),
    ]
    
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('sent', 'Sent'),
        ('delivered', 'Delivered'),
        ('read', 'Read'),
        ('responded', 'Responded'),
        ('failed', 'Failed'),
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    
    # Notification details
    notification_type = models.CharField(
        max_length=50,
        choices=NOTIFICATION_TYPES
    )
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default='pending'
    )
    
    # Recipients
    recipient = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='retention_notifications'
    )
    
    # Related objects
    policy = models.ForeignKey(
        RetentionPolicy,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='notifications'
    )
    job = models.ForeignKey(
        RetentionJob,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='notifications'
    )
    deletion_request = models.ForeignKey(
        DeletionRequest,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='notifications'
    )
    
    # Notification content
    subject = models.CharField(max_length=200)
    message = models.TextField()
    data_summary = models.JSONField(
        default=dict,
        blank=True,
        help_text="Summary of data affected by retention action"
    )
    
    # Delivery tracking
    sent_at = models.DateTimeField(null=True, blank=True)
    delivered_at = models.DateTimeField(null=True, blank=True)
    read_at = models.DateTimeField(null=True, blank=True)
    responded_at = models.DateTimeField(null=True, blank=True)
    
    # Response tracking
    response_required = models.BooleanField(default=False)
    response_deadline = models.DateTimeField(null=True, blank=True)
    response_data = models.JSONField(default=dict, blank=True)
    
    class Meta:
        db_table = 'clinical_retention_notifications'
        indexes = [
            models.Index(fields=['clinic', 'status']),
            models.Index(fields=['recipient', 'status']),
            models.Index(fields=['notification_type']),
            models.Index(fields=['sent_at']),
        ]
    
    def __str__(self):
        return f"Notification {self.id} - {self.subject}"
    
    def mark_as_sent(self):
        """Mark notification as sent."""
        self.status = 'sent'
        self.sent_at = timezone.now()
        self.save(update_fields=['status', 'sent_at'])
    
    def mark_as_delivered(self):
        """Mark notification as delivered."""
        self.status = 'delivered'
        self.delivered_at = timezone.now()
        self.save(update_fields=['status', 'delivered_at'])
    
    def mark_as_read(self):
        """Mark notification as read."""
        self.status = 'read'
        self.read_at = timezone.now()
        self.save(update_fields=['status', 'read_at'])
    
    def mark_as_responded(self, response_data: Dict[str, Any]):
        """Mark notification as responded with response data."""
        self.status = 'responded'
        self.responded_at = timezone.now()
        self.response_data = response_data
        self.save(update_fields=['status', 'responded_at', 'response_data'])