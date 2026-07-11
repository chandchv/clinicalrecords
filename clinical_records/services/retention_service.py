"""
Data retention and deletion service.

This service handles the execution of retention policies,
data archival, secure deletion, and compliance reporting.
"""

import os
import json
import hashlib
import logging
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, List, Tuple
from pathlib import Path

from django.conf import settings
from django.utils import timezone
from django.db import transaction
from django.contrib.auth import get_user_model
from django.core.files.storage import default_storage

from users.models import Clinic, Patient
from ..models import ClinicalRecord, ClinicalDocument
from ..models.retention_models import (
    RetentionPolicy, RetentionJob, DataArchive, 
    DeletionRequest, RetentionNotification
)
from .audit_service import audit_service
from .encryption_service import encryption_service

User = get_user_model()
logger = logging.getLogger(__name__)


class RetentionService:
    """Service for managing data retention and deletion policies."""
    
    def __init__(self):
        self.logger = logging.getLogger(f"{__name__}.{self.__class__.__name__}")
        self.config = getattr(settings, 'CLINICAL_RECORDS_RETENTION', {})
        self.archive_root = self.config.get('ARCHIVE_ROOT', 'archives/')
    
    def create_retention_policy(self, clinic: Clinic, policy_data: Dict[str, Any], 
                              created_by: User) -> RetentionPolicy:
        """
        Create a new retention policy for a clinic.
        
        Args:
            clinic: Clinic to create policy for
            policy_data: Policy configuration data
            created_by: User creating the policy
            
        Returns:
            Created RetentionPolicy instance
        """
        try:
            policy = RetentionPolicy.objects.create(
                clinic=clinic,
                name=policy_data['name'],
                description=policy_data.get('description', ''),
                data_type=policy_data['data_type'],
                retention_period_days=policy_data['retention_period_days'],
                action_after_retention=policy_data.get('action_after_retention', 'archive'),
                grace_period_days=policy_data.get('grace_period_days', 30),
                require_approval=policy_data.get('require_approval', False),
                notify_before_days=policy_data.get('notify_before_days', 30),
                legal_basis=policy_data.get('legal_basis', ''),
                regulatory_requirement=policy_data.get('regulatory_requirement', ''),
                created_by=created_by
            )
            
            # Log policy creation
            audit_service.log_clinical_action(
                action='RETENTION_POLICY_CREATED',
                user=created_by,
                resource_type='RETENTION_POLICY',
                resource_id=str(policy.id),
                clinic=clinic,
                details={
                    'policy_name': policy.name,
                    'data_type': policy.data_type,
                    'retention_days': policy.retention_period_days,
                    'action': policy.action_after_retention
                }
            )
            
            self.logger.info(f"Created retention policy: {policy.name} for {clinic.name}")
            return policy
            
        except Exception as e:
            self.logger.error(f"Error creating retention policy: {e}")
            raise
    
    def execute_retention_policy(self, policy: RetentionPolicy, 
                                user: Optional[User] = None) -> RetentionJob:
        """
        Execute a retention policy to process eligible data.
        
        Args:
            policy: Retention policy to execute
            user: User executing the policy (optional for automated execution)
            
        Returns:
            Created RetentionJob instance
        """
        try:
            # Create retention job
            job = RetentionJob.objects.create(
                clinic=policy.clinic,
                policy=policy,
                job_type=policy.action_after_retention,
                requires_approval=policy.require_approval
            )
            
            # Find eligible data based on policy
            eligible_data = self._find_eligible_data(policy)
            job.total_items = len(eligible_data)
            job.save(update_fields=['total_items'])
            
            # Start job execution
            job.start_job(user)
            
            # Log job start
            audit_service.log_clinical_action(
                action='RETENTION_JOB_STARTED',
                user=user,
                resource_type='RETENTION_JOB',
                resource_id=str(job.id),
                clinic=policy.clinic,
                details={
                    'policy_name': policy.name,
                    'job_type': job.job_type,
                    'total_items': job.total_items
                }
            )
            
            # Execute based on action type
            if policy.action_after_retention == 'archive':
                self._execute_archive_action(job, eligible_data)
            elif policy.action_after_retention == 'delete':
                self._execute_delete_action(job, eligible_data)
            elif policy.action_after_retention == 'anonymize':
                self._execute_anonymize_action(job, eligible_data)
            elif policy.action_after_retention == 'review':
                self._execute_review_action(job, eligible_data)
            
            job.complete_job()
            
            # Log job completion
            audit_service.log_clinical_action(
                action='RETENTION_JOB_COMPLETED',
                user=user,
                resource_type='RETENTION_JOB',
                resource_id=str(job.id),
                clinic=policy.clinic,
                details={
                    'successful_items': job.successful_items,
                    'failed_items': job.failed_items,
                    'success_rate': job.success_rate
                }
            )
            
            self.logger.info(f"Completed retention job {job.id}: {job.successful_items}/{job.total_items} successful")
            return job
            
        except Exception as e:
            error_msg = f"Retention policy execution failed: {str(e)}"
            self.logger.error(error_msg)
            
            if 'job' in locals():
                job.fail_job(error_msg)
            
            raise
    
    def archive_data_item(self, data_item: Any, policy: RetentionPolicy, 
                         job: RetentionJob) -> DataArchive:
        """
        Archive a single data item.
        
        Args:
            data_item: Data item to archive
            policy: Retention policy being executed
            job: Retention job
            
        Returns:
            Created DataArchive instance
        """
        try:
            # Determine data type and extract metadata
            if isinstance(data_item, ClinicalRecord):
                data_type = 'clinical_record'
                original_id = data_item.id
                patient = data_item.patient
                data_content = self._serialize_clinical_record(data_item)
            elif isinstance(data_item, ClinicalDocument):
                data_type = 'clinical_document'
                original_id = data_item.id
                patient = data_item.clinical_record.patient
                data_content = self._serialize_clinical_document(data_item)
            else:
                raise ValueError(f"Unsupported data type for archival: {type(data_item)}")
            
            # Create archive directory structure
            archive_dir = Path(self.archive_root) / str(policy.clinic.id) / data_type
            archive_dir.mkdir(parents=True, exist_ok=True)
            
            # Generate archive filename
            timestamp = timezone.now().strftime('%Y%m%d_%H%M%S')
            archive_filename = f"{original_id}_{timestamp}.json"
            archive_path = archive_dir / archive_filename
            
            # Encrypt data if encryption is enabled
            if self.config.get('ENCRYPT_ARCHIVES', True):
                encrypted_content, key_id = encryption_service.encrypt_data(
                    json.dumps(data_content).encode('utf-8'),
                    policy.clinic
                )
                content_to_store = encrypted_content
                encryption_key_id = key_id
            else:
                content_to_store = json.dumps(data_content, indent=2).encode('utf-8')
                encryption_key_id = ''
            
            # Calculate checksum
            checksum = hashlib.sha256(content_to_store).hexdigest()
            
            # Store archived data
            with open(archive_path, 'wb') as f:
                f.write(content_to_store)
            
            # Create archive record
            archive = DataArchive.objects.create(
                clinic=policy.clinic,
                original_id=original_id,
                data_type=data_type,
                archive_path=str(archive_path),
                storage_type='local_archive',
                archive_size_bytes=len(content_to_store),
                original_created_at=data_item.created_at,
                archived_by_policy=policy,
                archived_by_job=job,
                patient=patient,
                checksum=checksum,
                encryption_key_id=encryption_key_id
            )
            
            # Remove original data if configured
            if self.config.get('DELETE_AFTER_ARCHIVE', False):
                data_item.delete()
            
            self.logger.info(f"Archived {data_type} {original_id} to {archive_path}")
            return archive
            
        except Exception as e:
            self.logger.error(f"Error archiving data item {original_id}: {e}")
            raise
    
    def restore_archived_data(self, archive: DataArchive, 
                             user: User) -> Dict[str, Any]:
        """
        Restore archived data.
        
        Args:
            archive: DataArchive to restore
            user: User requesting restoration
            
        Returns:
            Dictionary containing restored data
        """
        try:
            # Check if archive file exists
            if not os.path.exists(archive.archive_path):
                raise FileNotFoundError(f"Archive file not found: {archive.archive_path}")
            
            # Read archived data
            with open(archive.archive_path, 'rb') as f:
                archived_content = f.read()
            
            # Verify checksum
            current_checksum = hashlib.sha256(archived_content).hexdigest()
            if current_checksum != archive.checksum:
                raise ValueError("Archive integrity check failed - checksum mismatch")
            
            # Decrypt if encrypted
            if archive.encryption_key_id:
                decrypted_content = encryption_service.decrypt_data(
                    archived_content,
                    archive.encryption_key_id,
                    archive.clinic
                )
                data_content = json.loads(decrypted_content.decode('utf-8'))
            else:
                data_content = json.loads(archived_content.decode('utf-8'))
            
            # Update restoration tracking
            archive.restoration_count += 1
            archive.last_restored_at = timezone.now()
            archive.save(update_fields=['restoration_count', 'last_restored_at'])
            
            # Log restoration
            audit_service.log_clinical_action(
                action='DATA_RESTORED',
                user=user,
                resource_type='DATA_ARCHIVE',
                resource_id=str(archive.id),
                clinic=archive.clinic,
                patient_id=str(archive.patient.id) if archive.patient else None,
                details={
                    'data_type': archive.data_type,
                    'original_id': str(archive.original_id),
                    'restoration_count': archive.restoration_count
                }
            )
            
            self.logger.info(f"Restored archived data {archive.id} for user {user.username}")
            return data_content
            
        except Exception as e:
            self.logger.error(f"Error restoring archived data {archive.id}: {e}")
            raise
    
    def create_deletion_request(self, request_data: Dict[str, Any], 
                               requested_by: User) -> DeletionRequest:
        """
        Create a data deletion request.
        
        Args:
            request_data: Deletion request data
            requested_by: User making the request
            
        Returns:
            Created DeletionRequest instance
        """
        try:
            # Get patient if specified
            patient = None
            if 'patient_id' in request_data:
                patient = Patient.objects.get(id=request_data['patient_id'])
            
            deletion_request = DeletionRequest.objects.create(
                clinic=requested_by.clinic,
                request_type=request_data['request_type'],
                requested_by=requested_by,
                patient=patient,
                deletion_scope=request_data.get('deletion_scope', {}),
                reason=request_data['reason'],
                legal_basis=request_data.get('legal_basis', '')
            )
            
            # Log deletion request
            audit_service.log_clinical_action(
                action='DELETION_REQUEST_CREATED',
                user=requested_by,
                resource_type='DELETION_REQUEST',
                resource_id=str(deletion_request.id),
                clinic=requested_by.clinic,
                patient_id=str(patient.id) if patient else None,
                details={
                    'request_type': deletion_request.request_type,
                    'reason': deletion_request.reason[:100]  # Truncate for logging
                }
            )
            
            # Send notification to administrators
            self._send_deletion_request_notification(deletion_request)
            
            self.logger.info(f"Created deletion request {deletion_request.id} by {requested_by.username}")
            return deletion_request
            
        except Exception as e:
            self.logger.error(f"Error creating deletion request: {e}")
            raise
    
    def execute_deletion_request(self, deletion_request: DeletionRequest, 
                                user: User) -> Dict[str, Any]:
        """
        Execute an approved deletion request.
        
        Args:
            deletion_request: Approved deletion request
            user: User executing the deletion
            
        Returns:
            Dictionary containing execution results
        """
        try:
            if deletion_request.status != 'approved':
                raise ValueError("Deletion request must be approved before execution")
            
            deletion_request.start_execution(user)
            
            results = {
                'deleted_records': 0,
                'deleted_documents': 0,
                'deleted_archives': 0,
                'errors': []
            }
            
            # Execute deletion based on scope
            scope = deletion_request.deletion_scope
            
            if deletion_request.patient:
                # Patient-specific deletion
                results.update(self._delete_patient_data(deletion_request.patient, scope))
            else:
                # Administrative deletion
                results.update(self._execute_administrative_deletion(scope))
            
            # Complete the request
            deletion_request.complete_execution(results)
            
            # Log completion
            audit_service.log_clinical_action(
                action='DELETION_REQUEST_EXECUTED',
                user=user,
                resource_type='DELETION_REQUEST',
                resource_id=str(deletion_request.id),
                clinic=deletion_request.clinic,
                patient_id=str(deletion_request.patient.id) if deletion_request.patient else None,
                sensitive_data=True,
                details={
                    'deleted_records': results['deleted_records'],
                    'deleted_documents': results['deleted_documents'],
                    'deleted_archives': results['deleted_archives'],
                    'error_count': len(results['errors'])
                }
            )
            
            self.logger.info(f"Executed deletion request {deletion_request.id}: {results}")
            return results
            
        except Exception as e:
            error_msg = f"Deletion request execution failed: {str(e)}"
            self.logger.error(error_msg)
            
            deletion_request.status = 'failed'
            deletion_request.completion_report = {'error': error_msg}
            deletion_request.save(update_fields=['status', 'completion_report'])
            
            raise
    
    def generate_retention_report(self, clinic: Clinic, 
                                 report_type: str = 'summary') -> Dict[str, Any]:
        """
        Generate retention compliance report.
        
        Args:
            clinic: Clinic to generate report for
            report_type: Type of report ('summary', 'detailed', 'compliance')
            
        Returns:
            Dictionary containing report data
        """
        try:
            report_data = {
                'clinic_name': clinic.name,
                'generated_at': timezone.now().isoformat(),
                'report_type': report_type
            }
            
            if report_type == 'summary':
                # Summary statistics
                report_data.update({
                    'active_policies': RetentionPolicy.objects.filter(
                        clinic=clinic, is_active=True
                    ).count(),
                    'total_jobs': RetentionJob.objects.filter(clinic=clinic).count(),
                    'completed_jobs': RetentionJob.objects.filter(
                        clinic=clinic, status='completed'
                    ).count(),
                    'archived_items': DataArchive.objects.filter(clinic=clinic).count(),
                    'pending_deletions': DeletionRequest.objects.filter(
                        clinic=clinic, status='pending'
                    ).count()
                })
                
            elif report_type == 'detailed':
                # Detailed policy and job information
                policies = RetentionPolicy.objects.filter(clinic=clinic, is_active=True)
                policy_data = []
                
                for policy in policies:
                    jobs = RetentionJob.objects.filter(policy=policy)
                    policy_data.append({
                        'policy_name': policy.name,
                        'data_type': policy.data_type,
                        'retention_days': policy.retention_period_days,
                        'action': policy.action_after_retention,
                        'total_jobs': jobs.count(),
                        'successful_jobs': jobs.filter(status='completed').count(),
                        'archived_items': DataArchive.objects.filter(
                            archived_by_policy=policy
                        ).count()
                    })
                
                report_data['policies'] = policy_data
                
            elif report_type == 'compliance':
                # Compliance-focused report
                now = timezone.now()
                
                # Find data that should be processed but hasn't been
                overdue_data = []
                for policy in RetentionPolicy.objects.filter(clinic=clinic, is_active=True):
                    eligible_data = self._find_eligible_data(policy)
                    if eligible_data:
                        overdue_data.append({
                            'policy_name': policy.name,
                            'data_type': policy.data_type,
                            'overdue_items': len(eligible_data)
                        })
                
                report_data.update({
                    'overdue_data': overdue_data,
                    'legal_holds': DataArchive.objects.filter(
                        clinic=clinic, legal_hold=True
                    ).count(),
                    'pending_approvals': RetentionJob.objects.filter(
                        clinic=clinic, status='requires_approval'
                    ).count()
                })
            
            self.logger.info(f"Generated {report_type} retention report for {clinic.name}")
            return report_data
            
        except Exception as e:
            self.logger.error(f"Error generating retention report: {e}")
            raise  
  def _find_eligible_data(self, policy: RetentionPolicy) -> List[Any]:
        """Find data eligible for retention action based on policy."""
        try:
            cutoff_date = timezone.now() - timedelta(days=policy.retention_period_days)
            eligible_data = []
            
            if policy.data_type == 'clinical_records':
                eligible_data = list(ClinicalRecord.objects.filter(
                    clinic=policy.clinic,
                    created_at__lt=cutoff_date
                ))
            elif policy.data_type == 'documents':
                eligible_data = list(ClinicalDocument.objects.filter(
                    clinical_record__clinic=policy.clinic,
                    created_at__lt=cutoff_date
                ))
            # Add more data types as needed
            
            return eligible_data
            
        except Exception as e:
            self.logger.error(f"Error finding eligible data for policy {policy.id}: {e}")
            return []
    
    def _execute_archive_action(self, job: RetentionJob, eligible_data: List[Any]):
        """Execute archive action for eligible data."""
        for data_item in eligible_data:
            try:
                self.archive_data_item(data_item, job.policy, job)
                job.successful_items += 1
            except Exception as e:
                self.logger.error(f"Failed to archive item {data_item.id}: {e}")
                job.failed_items += 1
                
                # Add to execution log
                if 'errors' not in job.execution_log:
                    job.execution_log['errors'] = []
                job.execution_log['errors'].append({
                    'item_id': str(data_item.id),
                    'error': str(e)
                })
            
            job.processed_items += 1
            job.save(update_fields=['processed_items', 'successful_items', 'failed_items', 'execution_log'])
    
    def _execute_delete_action(self, job: RetentionJob, eligible_data: List[Any]):
        """Execute delete action for eligible data."""
        for data_item in eligible_data:
            try:
                # Check for legal holds or other restrictions
                if hasattr(data_item, 'patient'):
                    # Check if patient data is under legal hold
                    legal_hold_archives = DataArchive.objects.filter(
                        patient=data_item.patient,
                        legal_hold=True
                    )
                    if legal_hold_archives.exists():
                        self.logger.warning(f"Skipping deletion of {data_item.id} - under legal hold")
                        continue
                
                # Perform secure deletion
                self._secure_delete_item(data_item)
                job.successful_items += 1
                
            except Exception as e:
                self.logger.error(f"Failed to delete item {data_item.id}: {e}")
                job.failed_items += 1
                
                if 'errors' not in job.execution_log:
                    job.execution_log['errors'] = []
                job.execution_log['errors'].append({
                    'item_id': str(data_item.id),
                    'error': str(e)
                })
            
            job.processed_items += 1
            job.save(update_fields=['processed_items', 'successful_items', 'failed_items', 'execution_log'])
    
    def _execute_anonymize_action(self, job: RetentionJob, eligible_data: List[Any]):
        """Execute anonymize action for eligible data."""
        for data_item in eligible_data:
            try:
                self._anonymize_data_item(data_item)
                job.successful_items += 1
            except Exception as e:
                self.logger.error(f"Failed to anonymize item {data_item.id}: {e}")
                job.failed_items += 1
                
                if 'errors' not in job.execution_log:
                    job.execution_log['errors'] = []
                job.execution_log['errors'].append({
                    'item_id': str(data_item.id),
                    'error': str(e)
                })
            
            job.processed_items += 1
            job.save(update_fields=['processed_items', 'successful_items', 'failed_items', 'execution_log'])
    
    def _execute_review_action(self, job: RetentionJob, eligible_data: List[Any]):
        """Execute review action - flag items for manual review."""
        for data_item in eligible_data:
            try:
                # Create notification for manual review
                self._create_review_notification(data_item, job)
                job.successful_items += 1
            except Exception as e:
                self.logger.error(f"Failed to flag item {data_item.id} for review: {e}")
                job.failed_items += 1
            
            job.processed_items += 1
            job.save(update_fields=['processed_items', 'successful_items', 'failed_items'])
    
    def _serialize_clinical_record(self, record: ClinicalRecord) -> Dict[str, Any]:
        """Serialize clinical record for archival."""
        return {
            'id': str(record.id),
            'patient_id': str(record.patient.id),
            'clinic_id': str(record.clinic.id),
            'record_type': record.record_type,
            'title': record.title,
            'description': record.description,
            'created_at': record.created_at.isoformat(),
            'updated_at': record.updated_at.isoformat(),
            'metadata': record.metadata if hasattr(record, 'metadata') else {}
        }
    
    def _serialize_clinical_document(self, document: ClinicalDocument) -> Dict[str, Any]:
        """Serialize clinical document for archival."""
        # Read file content if it exists
        file_content = None
        if document.file and default_storage.exists(document.file.name):
            try:
                with document.file.open('rb') as f:
                    file_content = f.read().hex()  # Store as hex string
            except Exception as e:
                self.logger.warning(f"Could not read file content for document {document.id}: {e}")
        
        return {
            'id': str(document.id),
            'clinical_record_id': str(document.clinical_record.id),
            'original_filename': document.original_filename,
            'content_type': document.content_type,
            'file_size': document.file_size,
            'file_content': file_content,
            'ocr_text': document.ocr_text,
            'structured_data': document.structured_data,
            'dicom_metadata': document.dicom_metadata,
            'created_at': document.created_at.isoformat(),
            'updated_at': document.updated_at.isoformat()
        }
    
    def _secure_delete_item(self, data_item: Any):
        """Securely delete a data item."""
        # If it's a document with a file, securely delete the file
        if isinstance(data_item, ClinicalDocument) and data_item.file:
            try:
                # Overwrite file with random data before deletion
                if default_storage.exists(data_item.file.name):
                    file_path = data_item.file.path
                    file_size = os.path.getsize(file_path)
                    
                    # Overwrite with random data multiple times
                    with open(file_path, 'r+b') as f:
                        for _ in range(3):  # 3-pass overwrite
                            f.seek(0)
                            f.write(os.urandom(file_size))
                            f.flush()
                            os.fsync(f.fileno())
                    
                    # Delete the file
                    default_storage.delete(data_item.file.name)
            except Exception as e:
                self.logger.error(f"Error securely deleting file for document {data_item.id}: {e}")
        
        # Delete the database record
        data_item.delete()
    
    def _anonymize_data_item(self, data_item: Any):
        """Anonymize a data item by removing/masking PII."""
        if isinstance(data_item, ClinicalRecord):
            # Anonymize clinical record
            data_item.title = f"Anonymized Record {data_item.id}"
            data_item.description = "[ANONYMIZED]"
            data_item.save(update_fields=['title', 'description'])
            
        elif isinstance(data_item, ClinicalDocument):
            # Anonymize document
            data_item.original_filename = f"anonymized_{data_item.id}.dat"
            data_item.ocr_text = "[ANONYMIZED]"
            data_item.structured_data = {}
            data_item.save(update_fields=['original_filename', 'ocr_text', 'structured_data'])
    
    def _delete_patient_data(self, patient: Patient, scope: Dict[str, Any]) -> Dict[str, Any]:
        """Delete all data for a specific patient."""
        results = {
            'deleted_records': 0,
            'deleted_documents': 0,
            'deleted_archives': 0,
            'errors': []
        }
        
        try:
            # Delete clinical records
            records = ClinicalRecord.objects.filter(patient=patient)
            for record in records:
                try:
                    # Delete associated documents first
                    documents = ClinicalDocument.objects.filter(clinical_record=record)
                    for document in documents:
                        self._secure_delete_item(document)
                        results['deleted_documents'] += 1
                    
                    # Delete the record
                    record.delete()
                    results['deleted_records'] += 1
                    
                except Exception as e:
                    results['errors'].append(f"Error deleting record {record.id}: {str(e)}")
            
            # Delete archived data
            archives = DataArchive.objects.filter(patient=patient)
            for archive in archives:
                try:
                    if not archive.is_under_legal_hold():
                        # Delete archive file
                        if os.path.exists(archive.archive_path):
                            os.remove(archive.archive_path)
                        
                        # Delete archive record
                        archive.delete()
                        results['deleted_archives'] += 1
                    else:
                        results['errors'].append(f"Archive {archive.id} under legal hold - not deleted")
                        
                except Exception as e:
                    results['errors'].append(f"Error deleting archive {archive.id}: {str(e)}")
            
        except Exception as e:
            results['errors'].append(f"Error in patient data deletion: {str(e)}")
        
        return results
    
    def _execute_administrative_deletion(self, scope: Dict[str, Any]) -> Dict[str, Any]:
        """Execute administrative deletion based on scope."""
        results = {
            'deleted_records': 0,
            'deleted_documents': 0,
            'deleted_archives': 0,
            'errors': []
        }
        
        # Implementation depends on scope definition
        # This is a placeholder for administrative deletion logic
        
        return results
    
    def _send_deletion_request_notification(self, deletion_request: DeletionRequest):
        """Send notification about new deletion request to administrators."""
        try:
            # Find administrators in the clinic
            from ..models.access_models import ClinicalRole, UserClinicalRole
            
            admin_roles = ClinicalRole.objects.filter(
                clinic=deletion_request.clinic,
                role_type='admin',
                is_active=True
            )
            
            admin_assignments = UserClinicalRole.objects.filter(
                role__in=admin_roles,
                is_active=True
            ).select_related('user')
            
            for assignment in admin_assignments:
                RetentionNotification.objects.create(
                    clinic=deletion_request.clinic,
                    notification_type='approval_required',
                    recipient=assignment.user,
                    deletion_request=deletion_request,
                    subject=f"Deletion Request Requires Approval - {deletion_request.request_type}",
                    message=f"A new deletion request has been submitted and requires your approval.\n\n"
                           f"Request Type: {deletion_request.request_type}\n"
                           f"Requested by: {deletion_request.requested_by.username}\n"
                           f"Reason: {deletion_request.reason}\n\n"
                           f"Please review and approve or reject this request.",
                    response_required=True,
                    response_deadline=timezone.now() + timedelta(days=7)
                )
            
        except Exception as e:
            self.logger.error(f"Error sending deletion request notification: {e}")
    
    def _create_review_notification(self, data_item: Any, job: RetentionJob):
        """Create notification for manual review of data item."""
        try:
            # Find users who can perform manual reviews
            from ..models.access_models import ClinicalRole, UserClinicalRole
            
            review_roles = ClinicalRole.objects.filter(
                clinic=job.clinic,
                can_perform_manual_review=True,
                is_active=True
            )
            
            review_assignments = UserClinicalRole.objects.filter(
                role__in=review_roles,
                is_active=True
            ).select_related('user')
            
            for assignment in review_assignments:
                RetentionNotification.objects.create(
                    clinic=job.clinic,
                    notification_type='upcoming_action',
                    recipient=assignment.user,
                    job=job,
                    subject=f"Manual Review Required - {job.policy.name}",
                    message=f"A data item requires manual review before retention action.\n\n"
                           f"Policy: {job.policy.name}\n"
                           f"Data Type: {job.policy.data_type}\n"
                           f"Action: {job.policy.action_after_retention}\n"
                           f"Item ID: {data_item.id}\n\n"
                           f"Please review and determine appropriate action.",
                    data_summary={
                        'item_id': str(data_item.id),
                        'item_type': type(data_item).__name__,
                        'created_at': data_item.created_at.isoformat()
                    },
                    response_required=True,
                    response_deadline=timezone.now() + timedelta(days=30)
                )
            
        except Exception as e:
            self.logger.error(f"Error creating review notification: {e}")


# Global retention service instance
retention_service = RetentionService()