"""
Background tasks for clinical document processing using Django-Q
"""
import logging
import time
from typing import Dict, Any, Optional
from django.conf import settings
from django.utils import timezone
from django_q.tasks import async_task, result
from django_q.models import Task

from .models import ClinicalDocument, ClinicalRecord
from .services.ocr_processor import ClinicalOCRProcessor, OCRProcessingError
from .services.dicom_service import DICOMStudyService
from .services.enhanced_ocr_service import enhanced_ocr_service
from .services.textract_service import textract_service
from users.models import AuditLog

logger = logging.getLogger(__name__)


class DocumentProcessingTask:
    """
    Main class for handling document processing tasks with Django-Q
    """
    
    def __init__(self):
        self.ocr_processor = ClinicalOCRProcessor()
        self.dicom_service = DICOMStudyService()
        self.enhanced_ocr_service = enhanced_ocr_service
        self.processing_config = getattr(settings, 'CLINICAL_RECORDS_PROCESSING', {})
    
    def process_document(self, document_id: str, attempt: int = 1) -> Dict[str, Any]:
        """
        Main document processing task that routes to appropriate processor
        
        Args:
            document_id: UUID of the ClinicalDocument to process
            attempt: Current attempt number (for retry logic)
            
        Returns:
            Dict containing processing results and status
        """
        start_time = time.time()
        result = {
            'document_id': document_id,
            'attempt': attempt,
            'status': 'started',
            'start_time': start_time,
            'processing_method': 'unknown',
            'error': None
        }
        
        try:
            # Get the document
            document = ClinicalDocument.objects.get(id=document_id)
            
            # Update document status to processing
            document.processing_status = 'processing'
            document.processing_started_at = timezone.now()
            document.save(update_fields=['processing_status', 'processing_started_at'])
            
            # Log processing start
            self._log_processing_event(
                document, 
                'PROCESSING_STARTED', 
                f"Document processing started (attempt {attempt})"
            )
            
            # Route to appropriate processor based on document type
            processing_result = self._route_document_processing(document)
            
            # Update result with processing outcome
            result.update(processing_result)
            result['status'] = 'completed'
            result['processing_time'] = time.time() - start_time
            
            # Update document with results
            self._update_document_with_results(document, processing_result)
            
            # Log successful completion
            self._log_processing_event(
                document,
                'PROCESSING_COMPLETED',
                f"Document processed successfully in {result['processing_time']:.2f}s"
            )
            
            # Check if manual review is needed
            if processing_result.get('overall_confidence', 0) < self.processing_config.get('MANUAL_REVIEW_THRESHOLD', 0.5):
                self._flag_for_manual_review(document, processing_result)
            
            return result
            
        except ClinicalDocument.DoesNotExist:
            error_msg = f"Document {document_id} not found"
            logger.error(error_msg)
            result.update({
                'status': 'failed',
                'error': error_msg,
                'processing_time': time.time() - start_time
            })
            return result
            
        except Exception as e:
            error_msg = f"Document processing failed: {str(e)}"
            logger.error(f"Processing error for document {document_id}: {e}", exc_info=True)
            
            result.update({
                'status': 'failed',
                'error': error_msg,
                'processing_time': time.time() - start_time
            })
            
            # Handle retry logic
            if attempt < self.processing_config.get('max_attempts', 3):
                self._schedule_retry(document_id, attempt + 1, str(e))
            else:
                # Mark document as failed after max attempts
                try:
                    document = ClinicalDocument.objects.get(id=document_id)
                    document.processing_status = 'failed'
                    document.processing_error = error_msg
                    document.processing_completed_at = timezone.now()
                    document.save(update_fields=[
                        'processing_status', 
                        'processing_error', 
                        'processing_completed_at'
                    ])
                    
                    self._log_processing_event(
                        document,
                        'PROCESSING_FAILED',
                        f"Document processing failed after {attempt} attempts: {error_msg}"
                    )
                except Exception as update_error:
                    logger.error(f"Failed to update document status: {update_error}")
            
            return result
    
    def _route_document_processing(self, document: ClinicalDocument) -> Dict[str, Any]:
        """
        Route document to appropriate processor based on type and content
        """
        try:
            # Determine document type for processing
            if document.content_type.startswith('application/dicom'):
                return self._process_dicom_document(document)
            elif document.content_type == 'application/pdf':
                return self._process_pdf_document(document)
            elif document.content_type.startswith('image/'):
                return self._process_image_document(document)
            elif document.content_type.startswith('text/'):
                return self._process_text_document(document)
            else:
                return self._process_generic_document(document)
                
        except Exception as e:
            logger.error(f"Error routing document processing: {e}")
            raise
    
    def _process_dicom_document(self, document: ClinicalDocument) -> Dict[str, Any]:
        """Process DICOM documents"""
        logger.info(f"Processing DICOM document: {document.id}")
        
        # Use the OCR processor's DICOM processing method
        result = self.ocr_processor._process_dicom_document(document)
        
        # Also create/update ImagingStudy if applicable
        try:
            imaging_study = self.dicom_service.process_dicom_document(document)
            if imaging_study:
                result['imaging_study_created'] = True
                result['imaging_study_id'] = str(imaging_study.id)
        except Exception as e:
            logger.warning(f"Failed to create ImagingStudy: {e}")
            result['imaging_study_created'] = False
        
        return result
    
    def _process_pdf_document(self, document: ClinicalDocument) -> Dict[str, Any]:
        """Process PDF documents with enhanced OCR"""
        logger.info(f"Processing PDF document: {document.id}")
        
        try:
            # Read document file
            document.file.seek(0)
            file_data = document.file.read()
            
            # Use enhanced OCR service
            result = self.enhanced_ocr_service.process_document(
                file_data, 
                document_type=document.clinical_record.record_type
            )
            
            # Add processing metadata
            result['processing_method'] = 'enhanced_ocr_pdf'
            result['file_size'] = len(file_data)
            
            return self._format_processing_result(result)
            
        except Exception as e:
            logger.error(f"Enhanced OCR PDF processing failed for {document.id}: {e}")
            # Fallback to original processor
            return self.ocr_processor._process_pdf_document(document)
    
    def _process_image_document(self, document: ClinicalDocument) -> Dict[str, Any]:
        """Process image documents with enhanced OCR"""
        logger.info(f"Processing image document: {document.id}")
        
        try:
            # Read document file
            document.file.seek(0)
            file_data = document.file.read()
            
            # Determine if this is a prescription for specialized processing
            if document.clinical_record.record_type == 'prescription':
                result = self.enhanced_ocr_service.process_prescription(file_data)
            elif document.clinical_record.record_type == 'lab_report':
                result = self.enhanced_ocr_service.process_lab_report(file_data)
            else:
                result = self.enhanced_ocr_service.process_document(
                    file_data,
                    document_type=document.clinical_record.record_type
                )
            
            # Add processing metadata
            result['processing_method'] = f"enhanced_ocr_{document.clinical_record.record_type}"
            result['file_size'] = len(file_data)
            
            return self._format_processing_result(result)
            
        except Exception as e:
            logger.error(f"Enhanced OCR image processing failed for {document.id}: {e}")
            # Fallback to original processor
            return self.ocr_processor._process_image_document(document)
    
    def _process_text_document(self, document: ClinicalDocument) -> Dict[str, Any]:
        """Process text documents"""
        logger.info(f"Processing text document: {document.id}")
        return self.ocr_processor._process_generic_document(document)
    
    def _process_generic_document(self, document: ClinicalDocument) -> Dict[str, Any]:
        """Process other document types"""
        logger.info(f"Processing generic document: {document.id}")
        
        try:
            # Try enhanced OCR for supported formats
            if document.content_type in ['application/pdf', 'image/jpeg', 'image/png', 'image/tiff']:
                document.file.seek(0)
                file_data = document.file.read()
                
                result = self.enhanced_ocr_service.process_document(
                    file_data,
                    document_type=document.clinical_record.record_type
                )
                
                result['processing_method'] = 'enhanced_ocr_generic'
                result['file_size'] = len(file_data)
                
                return self._format_processing_result(result)
            else:
                # Use original processor for unsupported formats
                return self.ocr_processor._process_generic_document(document)
                
        except Exception as e:
            logger.error(f"Enhanced OCR generic processing failed for {document.id}: {e}")
            # Fallback to original processor
            return self.ocr_processor._process_generic_document(document)
    
    def _format_processing_result(self, enhanced_result: Dict[str, Any]) -> Dict[str, Any]:
        """
        Format enhanced OCR result to match expected format
        
        Args:
            enhanced_result: Result from enhanced OCR service
            
        Returns:
            Dict in expected format for document processing
        """
        formatted = {
            'raw_text': enhanced_result.get('text', ''),
            'overall_confidence': enhanced_result.get('confidence', 0.0),
            'structured_data': enhanced_result.get('structured_data', {}),
            'processing_method': enhanced_result.get('processing_method', 'enhanced_ocr'),
            'textract_used': enhanced_result.get('textract_used', False),
            'local_ocr_used': enhanced_result.get('local_ocr_used', False),
            'processing_time': enhanced_result.get('processing_time', 0.0),
            'cost_estimate': enhanced_result.get('cost_estimate', 0.0)
        }
        
        # Add error information if present
        if 'error' in enhanced_result:
            formatted['processing_error'] = enhanced_result['error']
        
        # Add Textract-specific data if available
        if enhanced_result.get('textract_used'):
            formatted['textract_confidence'] = enhanced_result.get('structured_data', {}).get('textract_confidence')
            formatted['textract_forms'] = enhanced_result.get('structured_data', {}).get('forms', [])
            formatted['textract_tables'] = enhanced_result.get('structured_data', {}).get('tables', [])
        
        return formatted
    
    def _update_document_with_results(self, document: ClinicalDocument, result: Dict[str, Any]):
        """Update document with processing results"""
        try:
            # Update basic processing fields
            document.processing_status = 'completed'
            document.processing_completed_at = timezone.now()
            document.processing_error = result.get('processing_error', None)
            
            # Update OCR and structured data
            if 'raw_text' in result:
                document.ocr_text = result['raw_text']
            
            if 'structured_data' in result:
                document.structured_data = result['structured_data']
            
            if 'overall_confidence' in result:
                document.ocr_confidence = result['overall_confidence']
            
            # Update DICOM metadata if present
            if 'dicom_metadata' in result:
                document.dicom_metadata = result['dicom_metadata']
            
            # Add enhanced OCR metadata
            processing_metadata = {
                'processing_method': result.get('processing_method', 'unknown'),
                'textract_used': result.get('textract_used', False),
                'local_ocr_used': result.get('local_ocr_used', False),
                'processing_time': result.get('processing_time', 0.0),
                'cost_estimate': result.get('cost_estimate', 0.0),
                'processed_at': timezone.now().isoformat()
            }
            
            # Merge with existing metadata
            if hasattr(document, 'processing_metadata') and document.processing_metadata:
                document.processing_metadata.update(processing_metadata)
            else:
                document.processing_metadata = processing_metadata
            
            # Save all updates
            save_fields = [
                'processing_status',
                'processing_completed_at', 
                'processing_error',
                'ocr_text',
                'structured_data',
                'ocr_confidence',
                'dicom_metadata'
            ]
            
            # Add processing_metadata field if it exists
            if hasattr(document, 'processing_metadata'):
                save_fields.append('processing_metadata')
            
            document.save(update_fields=save_fields)
            
            # Log enhanced OCR usage for monitoring
            if result.get('textract_used'):
                logger.info(f"Document {document.id} processed with Textract - Cost: ${result.get('cost_estimate', 0):.4f}")
            
        except Exception as e:
            logger.error(f"Failed to update document {document.id} with results: {e}")
            raise
    
    def _flag_for_manual_review(self, document: ClinicalDocument, result: Dict[str, Any]):
        """Flag document for manual review if confidence is low"""
        try:
            document.requires_manual_review = True
            document.manual_review_reason = f"Low confidence score: {result.get('overall_confidence', 0):.2f}"
            document.save(update_fields=['requires_manual_review', 'manual_review_reason'])
            
            self._log_processing_event(
                document,
                'MANUAL_REVIEW_REQUIRED',
                f"Document flagged for manual review: {document.manual_review_reason}"
            )
            
        except Exception as e:
            logger.error(f"Failed to flag document for manual review: {e}")
    
    def _schedule_retry(self, document_id: str, attempt: int, error: str):
        """Schedule a retry for failed document processing"""
        try:
            retry_delays = self.processing_config.get('RETRY_DELAYS', [60, 300, 900])
            delay_index = min(attempt - 2, len(retry_delays) - 1)  # attempt-2 because we start from attempt 1
            delay = retry_delays[delay_index] if delay_index >= 0 else retry_delays[-1]
            
            # Schedule retry task
            task_id = async_task(
                'clinical_records.tasks.process_clinical_document',
                document_id,
                attempt,
                task_name=f'retry_document_processing_{document_id}_{attempt}',
                timeout=self.processing_config.get('PROCESSING_TIMEOUT', 300),
                schedule=timezone.now() + timezone.timedelta(seconds=delay)
            )
            
            logger.info(f"Scheduled retry {attempt} for document {document_id} in {delay}s (task: {task_id})")
            
            # Update document with retry info
            try:
                document = ClinicalDocument.objects.get(id=document_id)
                document.processing_status = 'retry_scheduled'
                document.processing_error = f"Retry {attempt} scheduled: {error}"
                document.save(update_fields=['processing_status', 'processing_error'])
                
                self._log_processing_event(
                    document,
                    'RETRY_SCHEDULED',
                    f"Retry {attempt} scheduled in {delay}s due to: {error}"
                )
            except Exception as update_error:
                logger.error(f"Failed to update document with retry info: {update_error}")
                
        except Exception as e:
            logger.error(f"Failed to schedule retry for document {document_id}: {e}")
    
    def _log_processing_event(self, document: ClinicalDocument, action: str, details: str):
        """Log processing events for audit trail"""
        try:
            AuditLog.log_action(
                user=None,  # System action
                action=action,
                resource_type='CLINICAL_DOCUMENT',
                resource_id=str(document.id),
                details=details,
                tenant=document.clinical_record.clinic
            )
        except Exception as e:
            logger.error(f"Failed to log processing event: {e}")


# Task functions for Django-Q
def process_clinical_document(document_id: str, attempt: int = 1) -> Dict[str, Any]:
    """
    Django-Q task function for processing clinical documents
    
    Args:
        document_id: UUID of the ClinicalDocument to process
        attempt: Current attempt number
        
    Returns:
        Dict containing processing results
    """
    processor = DocumentProcessingTask()
    return processor.process_document(document_id, attempt)


def batch_process_documents(document_ids: list, priority: str = 'normal') -> Dict[str, Any]:
    """
    Process multiple documents in batch
    
    Args:
        document_ids: List of document IDs to process
        priority: Task priority ('high', 'normal', 'low')
        
    Returns:
        Dict containing batch processing results
    """
    results = {
        'total_documents': len(document_ids),
        'queued_tasks': [],
        'failed_to_queue': [],
        'batch_id': f"batch_{int(time.time())}"
    }
    
    for document_id in document_ids:
        try:
            # Queue individual processing task
            task_id = async_task(
                'clinical_records.tasks.process_clinical_document',
                document_id,
                1,  # First attempt
                task_name=f'process_document_{document_id}',
                timeout=settings.CLINICAL_RECORDS_PROCESSING.get('PROCESSING_TIMEOUT', 300),
                group=results['batch_id']
            )
            
            results['queued_tasks'].append({
                'document_id': document_id,
                'task_id': task_id
            })
            
        except Exception as e:
            logger.error(f"Failed to queue document {document_id}: {e}")
            results['failed_to_queue'].append({
                'document_id': document_id,
                'error': str(e)
            })
    
    logger.info(f"Batch processing queued: {len(results['queued_tasks'])} tasks, {len(results['failed_to_queue'])} failed")
    return results


def cleanup_old_tasks(days_old: int = 7) -> Dict[str, Any]:
    """
    Clean up old completed tasks from Django-Q
    
    Args:
        days_old: Remove tasks older than this many days
        
    Returns:
        Dict containing cleanup results
    """
    try:
        cutoff_date = timezone.now() - timezone.timedelta(days=days_old)
        
        # Count tasks to be deleted
        old_tasks = Task.objects.filter(
            stopped__lt=cutoff_date,
            success=True
        )
        
        count_before = old_tasks.count()
        
        # Delete old successful tasks
        deleted_count, _ = old_tasks.delete()
        
        result = {
            'status': 'completed',
            'tasks_found': count_before,
            'tasks_deleted': deleted_count,
            'cutoff_date': cutoff_date.isoformat()
        }
        
        logger.info(f"Cleaned up {deleted_count} old tasks older than {days_old} days")
        return result
        
    except Exception as e:
        error_msg = f"Task cleanup failed: {str(e)}"
        logger.error(error_msg)
        return {
            'status': 'failed',
            'error': error_msg
        }


def get_processing_status(document_id: str) -> Dict[str, Any]:
    """
    Get the current processing status of a document
    
    Args:
        document_id: UUID of the document to check
        
    Returns:
        Dict containing status information
    """
    try:
        document = ClinicalDocument.objects.get(id=document_id)
        
        # Get related tasks
        related_tasks = Task.objects.filter(
            name__contains=f'process_document_{document_id}'
        ).order_by('-started')
        
        status_info = {
            'document_id': document_id,
            'processing_status': document.processing_status,
            'processing_started_at': document.processing_started_at.isoformat() if document.processing_started_at else None,
            'processing_completed_at': document.processing_completed_at.isoformat() if document.processing_completed_at else None,
            'processing_error': document.processing_error,
            'requires_manual_review': document.requires_manual_review,
            'manual_review_reason': document.manual_review_reason,
            'ocr_confidence': document.ocr_confidence,
            'has_structured_data': bool(document.structured_data),
            'related_tasks': []
        }
        
        # Add task information
        for task in related_tasks[:5]:  # Last 5 tasks
            status_info['related_tasks'].append({
                'task_id': task.id,
                'started': task.started.isoformat() if task.started else None,
                'stopped': task.stopped.isoformat() if task.stopped else None,
                'success': task.success,
                'result': task.result if task.success else None,
                'error': task.result if not task.success else None
            })
        
        return status_info
        
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