"""
Document upload service for clinical records.

This service handles file uploads, validation, processing queue management,
and integration with the document processing pipeline.
"""

import os
import uuid
import mimetypes
import logging
from typing import Dict, Any, List, Optional, Tuple
from pathlib import Path

from django.conf import settings
from django.core.files.uploadedfile import UploadedFile
from django.core.files.storage import default_storage
from django.utils import timezone
from django.contrib.auth import get_user_model
from django_q.tasks import async_task

from users.models import Clinic, Patient
from ..models import ClinicalRecord, ClinicalDocument
from .audit_service import audit_service
from .access_control_service import access_control_service

User = get_user_model()
logger = logging.getLogger(__name__)


class UploadService:
    """Service for handling document uploads and processing."""
    
    def __init__(self):
        self.logger = logging.getLogger(f"{__name__}.{self.__class__.__name__}")
        self.config = getattr(settings, 'CLINICAL_RECORDS_UPLOAD', {})
        
        # File validation settings
        self.max_file_size = self.config.get('MAX_FILE_SIZE', 50 * 1024 * 1024)  # 50MB
        self.allowed_extensions = self.config.get('ALLOWED_EXTENSIONS', [
            '.pdf', '.jpg', '.jpeg', '.png', '.tiff', '.tif', '.dcm', '.txt', '.doc', '.docx'
        ])
        self.allowed_mime_types = self.config.get('ALLOWED_MIME_TYPES', [
            'application/pdf',
            'image/jpeg', 'image/png', 'image/tiff',
            'application/dicom',
            'text/plain',
            'application/msword',
            'application/vnd.openxmlformats-officedocument.wordprocessingml.document'
        ])
    
    def validate_upload(self, uploaded_file: UploadedFile, user: User) -> Tuple[bool, str]:
        """
        Validate uploaded file for security and compliance.
        
        Args:
            uploaded_file: The uploaded file to validate
            user: User uploading the file
            
        Returns:
            Tuple of (is_valid: bool, error_message: str)
        """
        try:
            # Check file size
            if uploaded_file.size > self.max_file_size:
                return False, f"File size ({uploaded_file.size} bytes) exceeds maximum allowed size ({self.max_file_size} bytes)"
            
            # Check file extension
            file_ext = Path(uploaded_file.name).suffix.lower()
            if file_ext not in self.allowed_extensions:
                return False, f"File extension '{file_ext}' is not allowed. Allowed extensions: {', '.join(self.allowed_extensions)}"
            
            # Check MIME type
            mime_type, _ = mimetypes.guess_type(uploaded_file.name)
            if mime_type and mime_type not in self.allowed_mime_types:
                return False, f"MIME type '{mime_type}' is not allowed"
            
            # Additional content-based validation
            content_type = uploaded_file.content_type
            if content_type and content_type not in self.allowed_mime_types:
                return False, f"Content type '{content_type}' is not allowed"
            
            # Check for empty files
            if uploaded_file.size == 0:
                return False, "Empty files are not allowed"
            
            # Basic malware check (check for suspicious patterns)
            if self._contains_suspicious_content(uploaded_file):
                return False, "File contains suspicious content and cannot be uploaded"
            
            return True, "File validation passed"
            
        except Exception as e:
            self.logger.error(f"Error validating upload: {e}")
            return False, f"Validation error: {str(e)}"
    
    def process_upload(self, uploaded_file: UploadedFile, clinical_record: ClinicalRecord,
                      user: User, metadata: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Process a single file upload.
        
        Args:
            uploaded_file: The uploaded file
            clinical_record: Clinical record to associate with
            user: User uploading the file
            metadata: Optional metadata for the upload
            
        Returns:
            Dict containing upload results
        """
        upload_id = str(uuid.uuid4())
        result = {
            'upload_id': upload_id,
            'filename': uploaded_file.name,
            'size': uploaded_file.size,
            'status': 'started',
            'document_id': None,
            'processing_queued': False
        }
        
        try:
            # Validate upload
            is_valid, validation_message = self.validate_upload(uploaded_file, user)
            if not is_valid:
                result.update({
                    'status': 'failed',
                    'error': validation_message
                })
                return result
            
            # Check user permissions
            has_access, access_reason = access_control_service.check_record_access(
                user=user,
                record=clinical_record,
                action='edit'
            )
            
            if not has_access:
                result.update({
                    'status': 'failed',
                    'error': f"Access denied: {access_reason}"
                })
                return result
            
            # Create document record
            document = ClinicalDocument.objects.create(
                clinical_record=clinical_record,
                original_filename=uploaded_file.name,
                content_type=uploaded_file.content_type or 'application/octet-stream',
                file_size=uploaded_file.size,
                file=uploaded_file,
                uploaded_by=user,
                upload_metadata=metadata or {}
            )
            
            result.update({
                'status': 'uploaded',
                'document_id': str(document.id)
            })
            
            # Queue for background processing
            if self.config.get('AUTO_PROCESS', True):
                task_id = async_task(
                    'clinical_records.tasks.process_clinical_document',
                    str(document.id),
                    task_name=f'process_upload_{document.id}',
                    timeout=self.config.get('PROCESSING_TIMEOUT', 300)
                )
                
                result.update({
                    'processing_queued': True,
                    'task_id': task_id
                })
            
            # Log successful upload
            audit_service.log_clinical_action(
                action='DOCUMENT_UPLOADED',
                user=user,
                resource_type='CLINICAL_DOCUMENT',
                resource_id=str(document.id),
                clinic=clinical_record.clinic,
                patient_id=str(clinical_record.patient.id),
                details={
                    'filename': uploaded_file.name,
                    'file_size': uploaded_file.size,
                    'content_type': uploaded_file.content_type,
                    'clinical_record_id': str(clinical_record.id)
                }
            )
            
            self.logger.info(f"Document uploaded successfully: {document.id} by {user.username}")
            return result
            
        except Exception as e:
            error_msg = f"Upload processing failed: {str(e)}"
            self.logger.error(f"Error processing upload {upload_id}: {e}", exc_info=True)
            
            result.update({
                'status': 'failed',
                'error': error_msg
            })
            
            # Log failed upload
            audit_service.log_clinical_action(
                action='DOCUMENT_UPLOAD_FAILED',
                user=user,
                resource_type='CLINICAL_DOCUMENT',
                resource_id=upload_id,
                clinic=clinical_record.clinic,
                patient_id=str(clinical_record.patient.id),
                details={
                    'filename': uploaded_file.name,
                    'error': error_msg
                }
            )
            
            return result
    
    def process_batch_upload(self, uploaded_files: List[UploadedFile], 
                           clinical_record: ClinicalRecord, user: User,
                           metadata: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Process multiple file uploads in batch.
        
        Args:
            uploaded_files: List of uploaded files
            clinical_record: Clinical record to associate with
            user: User uploading the files
            metadata: Optional metadata for the uploads
            
        Returns:
            Dict containing batch upload results
        """
        batch_id = str(uuid.uuid4())
        results = {
            'batch_id': batch_id,
            'total_files': len(uploaded_files),
            'successful_uploads': [],
            'failed_uploads': [],
            'processing_queued': 0
        }
        
        try:
            for uploaded_file in uploaded_files:
                upload_result = self.process_upload(
                    uploaded_file=uploaded_file,
                    clinical_record=clinical_record,
                    user=user,
                    metadata=metadata
                )
                
                if upload_result['status'] == 'uploaded':
                    results['successful_uploads'].append(upload_result)
                    if upload_result.get('processing_queued'):
                        results['processing_queued'] += 1
                else:
                    results['failed_uploads'].append(upload_result)
            
            # Log batch upload completion
            audit_service.log_clinical_action(
                action='BATCH_UPLOAD_COMPLETED',
                user=user,
                resource_type='CLINICAL_DOCUMENT',
                resource_id=batch_id,
                clinic=clinical_record.clinic,
                patient_id=str(clinical_record.patient.id),
                details={
                    'total_files': results['total_files'],
                    'successful_uploads': len(results['successful_uploads']),
                    'failed_uploads': len(results['failed_uploads']),
                    'processing_queued': results['processing_queued']
                }
            )
            
            self.logger.info(
                f"Batch upload completed: {batch_id}, "
                f"Success: {len(results['successful_uploads'])}, "
                f"Failed: {len(results['failed_uploads'])}"
            )
            
            return results
            
        except Exception as e:
            error_msg = f"Batch upload processing failed: {str(e)}"
            self.logger.error(f"Error processing batch upload {batch_id}: {e}", exc_info=True)
            
            results.update({
                'error': error_msg
            })
            
            return results
    
    def get_upload_progress(self, document_id: str) -> Dict[str, Any]:
        """
        Get upload and processing progress for a document.
        
        Args:
            document_id: ID of the document to check
            
        Returns:
            Dict containing progress information
        """
        try:
            document = ClinicalDocument.objects.get(id=document_id)
            
            progress = {
                'document_id': document_id,
                'filename': document.original_filename,
                'upload_status': 'completed',
                'processing_status': document.processing_status,
                'processing_progress': 0,
                'created_at': document.created_at.isoformat(),
                'file_size': document.file_size,
                'content_type': document.content_type
            }
            
            # Calculate processing progress
            if document.processing_status == 'completed':
                progress['processing_progress'] = 100
            elif document.processing_status == 'processing':
                progress['processing_progress'] = 50  # Estimate
            elif document.processing_status == 'failed':
                progress['processing_progress'] = 0
                progress['error'] = document.processing_error
            
            # Add OCR results if available
            if document.ocr_text:
                progress['ocr_available'] = True
                progress['ocr_confidence'] = document.ocr_confidence
            
            # Add structured data if available
            if document.structured_data:
                progress['structured_data_available'] = True
            
            return progress
            
        except ClinicalDocument.DoesNotExist:
            return {
                'document_id': document_id,
                'error': 'Document not found'
            }
        except Exception as e:
            return {
                'document_id': document_id,
                'error': str(e)
            }
    
    def get_upload_queue_status(self, user: User, clinic: Optional[Clinic] = None) -> Dict[str, Any]:
        """
        Get status of upload queue for user or clinic.
        
        Args:
            user: User to get queue status for
            clinic: Optional clinic to filter by
            
        Returns:
            Dict containing queue status
        """
        try:
            # Build query
            documents_query = ClinicalDocument.objects.filter(uploaded_by=user)
            
            if clinic:
                documents_query = documents_query.filter(clinical_record__clinic=clinic)
            
            # Get recent uploads (last 24 hours)
            recent_cutoff = timezone.now() - timezone.timedelta(hours=24)
            recent_documents = documents_query.filter(created_at__gte=recent_cutoff)
            
            # Count by status
            status_counts = {
                'pending': recent_documents.filter(processing_status='pending').count(),
                'processing': recent_documents.filter(processing_status='processing').count(),
                'completed': recent_documents.filter(processing_status='completed').count(),
                'failed': recent_documents.filter(processing_status='failed').count(),
                'retry_scheduled': recent_documents.filter(processing_status='retry_scheduled').count()
            }
            
            # Get documents requiring manual review
            manual_review_count = recent_documents.filter(requires_manual_review=True).count()
            
            return {
                'user_id': str(user.id),
                'clinic_id': str(clinic.id) if clinic else None,
                'recent_uploads': recent_documents.count(),
                'status_counts': status_counts,
                'manual_review_required': manual_review_count,
                'queue_health': self._calculate_queue_health(status_counts)
            }
            
        except Exception as e:
            self.logger.error(f"Error getting upload queue status: {e}")
            return {
                'error': str(e)
            }
    
    def cancel_upload(self, document_id: str, user: User) -> Dict[str, Any]:
        """
        Cancel an upload and remove associated files.
        
        Args:
            document_id: ID of document to cancel
            user: User requesting cancellation
            
        Returns:
            Dict containing cancellation results
        """
        try:
            document = ClinicalDocument.objects.get(id=document_id)
            
            # Check permissions
            has_access, access_reason = access_control_service.check_document_access(
                user=user,
                document=document,
                action='delete'
            )
            
            if not has_access:
                return {
                    'status': 'failed',
                    'error': f"Access denied: {access_reason}"
                }
            
            # Remove file if it exists
            if document.file and default_storage.exists(document.file.name):
                default_storage.delete(document.file.name)
            
            # Log cancellation
            audit_service.log_clinical_action(
                action='DOCUMENT_UPLOAD_CANCELLED',
                user=user,
                resource_type='CLINICAL_DOCUMENT',
                resource_id=str(document.id),
                clinic=document.clinical_record.clinic,
                patient_id=str(document.clinical_record.patient.id),
                details={
                    'filename': document.original_filename,
                    'processing_status': document.processing_status
                }
            )
            
            # Delete document record
            document.delete()
            
            return {
                'status': 'cancelled',
                'document_id': document_id
            }
            
        except ClinicalDocument.DoesNotExist:
            return {
                'status': 'failed',
                'error': 'Document not found'
            }
        except Exception as e:
            self.logger.error(f"Error cancelling upload {document_id}: {e}")
            return {
                'status': 'failed',
                'error': str(e)
            }
    
    def _contains_suspicious_content(self, uploaded_file: UploadedFile) -> bool:
        """
        Basic check for suspicious file content.
        
        Args:
            uploaded_file: File to check
            
        Returns:
            True if suspicious content detected
        """
        try:
            # Read first few bytes to check for suspicious patterns
            uploaded_file.seek(0)
            header = uploaded_file.read(1024)
            uploaded_file.seek(0)  # Reset file pointer
            
            # Check for executable signatures
            suspicious_signatures = [
                b'MZ',  # Windows executable
                b'\x7fELF',  # Linux executable
                b'\xfe\xed\xfa',  # Mach-O executable
                b'PK\x03\x04',  # ZIP file (could contain executables)
            ]
            
            for signature in suspicious_signatures:
                if header.startswith(signature):
                    # Allow ZIP files for Office documents
                    if signature == b'PK\x03\x04' and uploaded_file.content_type in [
                        'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
                        'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
                    ]:
                        continue
                    return True
            
            return False
            
        except Exception as e:
            self.logger.warning(f"Error checking file content: {e}")
            return False  # Don't block upload on check failure
    
    def _calculate_queue_health(self, status_counts: Dict[str, int]) -> str:
        """
        Calculate overall health of upload queue.
        
        Args:
            status_counts: Dictionary of status counts
            
        Returns:
            Health status string
        """
        total = sum(status_counts.values())
        if total == 0:
            return 'healthy'
        
        failed_ratio = status_counts['failed'] / total
        processing_ratio = (status_counts['pending'] + status_counts['processing']) / total
        
        if failed_ratio > 0.2:  # More than 20% failed
            return 'unhealthy'
        elif failed_ratio > 0.1 or processing_ratio > 0.5:  # More than 10% failed or 50% processing
            return 'degraded'
        else:
            return 'healthy'


# Global upload service instance
upload_service = UploadService()