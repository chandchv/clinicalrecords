"""
Background Processing Service for Clinical Documents

This service provides a high-level interface for managing background document processing
with Django-Q, including task scheduling, progress tracking, and error handling.
"""
import logging
from typing import Dict, Any, List, Optional
from django.conf import settings
from django.utils import timezone
from django_q.tasks import async_task, result, fetch
from django_q.models import Task

from ..models import ClinicalDocument
from ..tasks import (
    process_clinical_document,
    batch_process_documents,
    get_processing_status
)

logger = logging.getLogger(__name__)


class BackgroundProcessingService:
    """
    Service for managing background processing of clinical documents
    """
    
    def __init__(self):
        self.processing_config = getattr(settings, 'CLINICAL_RECORDS_PROCESSING', {})
    
    def queue_document_processing(
        self, 
        document: ClinicalDocument, 
        priority: str = 'normal',
        force: bool = False
    ) -> Dict[str, Any]:
        """
        Queue a document for background processing
        
        Args:
            document: ClinicalDocument instance to process
            priority: Task priority ('high', 'normal', 'low')
            force: Force processing even if already processed
            
        Returns:
            Dict containing task information
        """
        try:
            # Check if already processed
            if document.processing_status == 'completed' and not force:
                return {
                    'status': 'skipped',
                    'reason': 'already_processed',
                    'document_id': str(document.id)
                }
            
            # Check if already queued
            if document.processing_status == 'processing':
                return {
                    'status': 'skipped',
                    'reason': 'already_processing',
                    'document_id': str(document.id)
                }
            
            # Validate document
            validation_result = self._validate_document_for_processing(document)
            if not validation_result['is_valid']:
                return {
                    'status': 'failed',
                    'reason': 'validation_failed',
                    'document_id': str(document.id),
                    'errors': validation_result['errors']
                }
            
            # Queue the processing task
            task_id = async_task(
                'clinical_records.tasks.process_clinical_document',
                str(document.id),
                1,  # First attempt
                task_name=f'process_document_{document.id}',
                timeout=self.processing_config.get('PROCESSING_TIMEOUT', 300),
                group=f'clinic_{document.clinical_record.clinic.id}'
            )
            
            # Update document status
            document.processing_status = 'queued'
            document.save(update_fields=['processing_status'])
            
            logger.info(f"Queued document {document.id} for processing (task: {task_id})")
            
            return {
                'status': 'queued',
                'task_id': task_id,
                'document_id': str(document.id),
                'estimated_processing_time': self._estimate_processing_time(document)
            }
            
        except Exception as e:
            logger.error(f"Failed to queue document {document.id}: {e}")
            return {
                'status': 'failed',
                'reason': 'queue_error',
                'document_id': str(document.id),
                'error': str(e)
            }
    
    def queue_batch_processing(
        self, 
        documents: List[ClinicalDocument],
        priority: str = 'normal'
    ) -> Dict[str, Any]:
        """
        Queue multiple documents for batch processing
        
        Args:
            documents: List of ClinicalDocument instances
            priority: Task priority
            
        Returns:
            Dict containing batch processing results
        """
        try:
            # Filter documents that need processing
            processable_docs = []
            skipped_docs = []
            
            for doc in documents:
                if doc.processing_status in ['uploaded', 'failed', 'retry_scheduled']:
                    validation_result = self._validate_document_for_processing(doc)
                    if validation_result['is_valid']:
                        processable_docs.append(doc)
                    else:
                        skipped_docs.append({
                            'document_id': str(doc.id),
                            'reason': 'validation_failed',
                            'errors': validation_result['errors']
                        })
                else:
                    skipped_docs.append({
                        'document_id': str(doc.id),
                        'reason': f'status_{doc.processing_status}'
                    })
            
            if not processable_docs:
                return {
                    'status': 'completed',
                    'total_documents': len(documents),
                    'queued_count': 0,
                    'skipped_count': len(skipped_docs),
                    'skipped_documents': skipped_docs
                }
            
            # Extract document IDs
            document_ids = [str(doc.id) for doc in processable_docs]
            
            # Queue batch processing
            batch_result = batch_process_documents(document_ids, priority)
            
            # Update document statuses
            for doc in processable_docs:
                doc.processing_status = 'queued'
                doc.save(update_fields=['processing_status'])
            
            return {
                'status': 'queued',
                'total_documents': len(documents),
                'queued_count': len(batch_result['queued_tasks']),
                'skipped_count': len(skipped_docs) + len(batch_result['failed_to_queue']),
                'batch_id': batch_result['batch_id'],
                'queued_tasks': batch_result['queued_tasks'],
                'skipped_documents': skipped_docs + batch_result['failed_to_queue']
            }
            
        except Exception as e:
            logger.error(f"Batch processing failed: {e}")
            return {
                'status': 'failed',
                'error': str(e),
                'total_documents': len(documents)
            }
    
    def get_document_processing_status(self, document: ClinicalDocument) -> Dict[str, Any]:
        """
        Get detailed processing status for a document
        
        Args:
            document: ClinicalDocument instance
            
        Returns:
            Dict containing detailed status information
        """
        try:
            # Get basic status from database
            status_info = {
                'document_id': str(document.id),
                'processing_status': document.processing_status,
                'processing_started_at': document.processing_started_at.isoformat() if document.processing_started_at else None,
                'processing_completed_at': document.processing_completed_at.isoformat() if document.processing_completed_at else None,
                'processing_error': document.processing_error,
                'requires_manual_review': document.requires_manual_review,
                'manual_review_reason': document.manual_review_reason,
                'ocr_confidence': document.ocr_confidence,
                'has_structured_data': bool(document.structured_data),
                'file_info': {
                    'filename': document.original_filename,
                    'content_type': document.content_type,
                    'file_size': document.file_size,
                    'upload_date': document.created_at.isoformat()
                }
            }
            
            # Get active task information
            active_tasks = Task.objects.filter(
                name__contains=f'process_document_{document.id}',
                stopped__isnull=True
            ).order_by('-started')
            
            if active_tasks.exists():
                task = active_tasks.first()
                status_info['active_task'] = {
                    'task_id': task.id,
                    'started': task.started.isoformat() if task.started else None,
                    'progress': self._calculate_task_progress(task)
                }
            
            # Get recent task history
            recent_tasks = Task.objects.filter(
                name__contains=f'process_document_{document.id}'
            ).order_by('-started')[:5]
            
            status_info['task_history'] = []
            for task in recent_tasks:
                status_info['task_history'].append({
                    'task_id': task.id,
                    'started': task.started.isoformat() if task.started else None,
                    'stopped': task.stopped.isoformat() if task.stopped else None,
                    'success': task.success,
                    'duration': self._calculate_task_duration(task)
                })
            
            return status_info
            
        except Exception as e:
            logger.error(f"Failed to get processing status for document {document.id}: {e}")
            return {
                'document_id': str(document.id),
                'error': str(e)
            }
    
    def cancel_document_processing(self, document: ClinicalDocument) -> Dict[str, Any]:
        """
        Cancel active processing for a document
        
        Args:
            document: ClinicalDocument instance
            
        Returns:
            Dict containing cancellation result
        """
        try:
            # Find active tasks
            active_tasks = Task.objects.filter(
                name__contains=f'process_document_{document.id}',
                stopped__isnull=True
            )
            
            if not active_tasks.exists():
                return {
                    'status': 'no_active_tasks',
                    'document_id': str(document.id)
                }
            
            # Cancel tasks (Django-Q doesn't support direct cancellation,
            # so we mark the document as cancelled)
            document.processing_status = 'cancelled'
            document.processing_error = 'Processing cancelled by user'
            document.save(update_fields=['processing_status', 'processing_error'])
            
            cancelled_tasks = []
            for task in active_tasks:
                cancelled_tasks.append(task.id)
            
            logger.info(f"Cancelled processing for document {document.id}")
            
            return {
                'status': 'cancelled',
                'document_id': str(document.id),
                'cancelled_tasks': cancelled_tasks
            }
            
        except Exception as e:
            logger.error(f"Failed to cancel processing for document {document.id}: {e}")
            return {
                'status': 'failed',
                'document_id': str(document.id),
                'error': str(e)
            }
    
    def get_processing_statistics(self, clinic_id: Optional[str] = None) -> Dict[str, Any]:
        """
        Get processing statistics for documents
        
        Args:
            clinic_id: Optional clinic ID to filter by
            
        Returns:
            Dict containing processing statistics
        """
        try:
            # Base queryset
            queryset = ClinicalDocument.objects.all()
            if clinic_id:
                queryset = queryset.filter(clinical_record__clinic_id=clinic_id)
            
            # Count by status
            stats = {
                'total_documents': queryset.count(),
                'by_status': {},
                'processing_metrics': {},
                'recent_activity': {}
            }
            
            # Status counts
            status_counts = queryset.values('processing_status').annotate(
                count=models.Count('id')
            )
            
            for item in status_counts:
                stats['by_status'][item['processing_status']] = item['count']
            
            # Processing metrics
            completed_docs = queryset.filter(processing_status='completed')
            if completed_docs.exists():
                # Calculate average processing time
                processing_times = []
                for doc in completed_docs.filter(
                    processing_started_at__isnull=False,
                    processing_completed_at__isnull=False
                ):
                    duration = doc.processing_completed_at - doc.processing_started_at
                    processing_times.append(duration.total_seconds())
                
                if processing_times:
                    stats['processing_metrics'] = {
                        'average_processing_time': sum(processing_times) / len(processing_times),
                        'min_processing_time': min(processing_times),
                        'max_processing_time': max(processing_times),
                        'total_processed': len(processing_times)
                    }
            
            # Recent activity (last 24 hours)
            recent_cutoff = timezone.now() - timezone.timedelta(hours=24)
            recent_docs = queryset.filter(created_at__gte=recent_cutoff)
            
            stats['recent_activity'] = {
                'uploaded_last_24h': recent_docs.count(),
                'processed_last_24h': recent_docs.filter(
                    processing_status='completed'
                ).count(),
                'failed_last_24h': recent_docs.filter(
                    processing_status='failed'
                ).count()
            }
            
            return stats
            
        except Exception as e:
            logger.error(f"Failed to get processing statistics: {e}")
            return {
                'error': str(e)
            }
    
    def _validate_document_for_processing(self, document: ClinicalDocument) -> Dict[str, Any]:
        """Validate document before processing"""
        errors = []
        
        # Check file exists
        if not document.file or not document.file.name:
            errors.append("Document file is missing")
        
        # Check file size
        max_size = self.processing_config.get('MAX_FILE_SIZE_MB', 100) * 1024 * 1024
        if document.file_size and document.file_size > max_size:
            errors.append(f"File size ({document.file_size} bytes) exceeds maximum ({max_size} bytes)")
        
        # Check content type
        supported_formats = self.processing_config.get('SUPPORTED_FORMATS', [])
        if supported_formats and document.content_type not in supported_formats:
            errors.append(f"Unsupported content type: {document.content_type}")
        
        return {
            'is_valid': len(errors) == 0,
            'errors': errors
        }
    
    def _estimate_processing_time(self, document: ClinicalDocument) -> int:
        """Estimate processing time in seconds based on document characteristics"""
        base_time = 30  # Base processing time in seconds
        
        # Adjust based on file size
        if document.file_size:
            size_mb = document.file_size / (1024 * 1024)
            base_time += int(size_mb * 2)  # 2 seconds per MB
        
        # Adjust based on content type
        if document.content_type == 'application/pdf':
            base_time += 20  # PDFs take longer
        elif document.content_type.startswith('application/dicom'):
            base_time += 15  # DICOM processing
        elif document.content_type.startswith('image/'):
            base_time += 10  # Image OCR
        
        return min(base_time, 300)  # Cap at 5 minutes
    
    def _calculate_task_progress(self, task: Task) -> float:
        """Calculate task progress percentage"""
        if not task.started:
            return 0.0
        
        if task.stopped:
            return 100.0
        
        # Estimate progress based on elapsed time
        elapsed = (timezone.now() - task.started).total_seconds()
        estimated_total = 60  # Assume 60 seconds average
        
        progress = min((elapsed / estimated_total) * 100, 95)  # Cap at 95% until complete
        return round(progress, 1)
    
    def _calculate_task_duration(self, task: Task) -> Optional[float]:
        """Calculate task duration in seconds"""
        if task.started and task.stopped:
            return (task.stopped - task.started).total_seconds()
        return None