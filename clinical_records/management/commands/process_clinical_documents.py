"""
Management command for processing clinical documents
"""
import logging
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone
from django_q.tasks import async_task, result
from django_q.models import Task

from clinical_records.models import ClinicalDocument
from clinical_records.tasks import (
    process_clinical_document,
    batch_process_documents,
    cleanup_old_tasks,
    get_processing_status
)

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Process clinical documents using background tasks'
    
    def add_arguments(self, parser):
        parser.add_argument(
            '--document-id',
            type=str,
            help='Process a specific document by ID'
        )
        
        parser.add_argument(
            '--batch',
            action='store_true',
            help='Process all pending documents in batch'
        )
        
        parser.add_argument(
            '--status',
            type=str,
            help='Check processing status of a document by ID'
        )
        
        parser.add_argument(
            '--cleanup',
            action='store_true',
            help='Clean up old completed tasks'
        )
        
        parser.add_argument(
            '--cleanup-days',
            type=int,
            default=7,
            help='Days old for task cleanup (default: 7)'
        )
        
        parser.add_argument(
            '--list-pending',
            action='store_true',
            help='List all pending documents'
        )
        
        parser.add_argument(
            '--retry-failed',
            action='store_true',
            help='Retry all failed documents'
        )
        
        parser.add_argument(
            '--force',
            action='store_true',
            help='Force processing even if already processed'
        )
    
    def handle(self, *args, **options):
        """Handle the management command"""
        
        if options['document_id']:
            self.process_single_document(options['document_id'], options['force'])
            
        elif options['batch']:
            self.process_batch()
            
        elif options['status']:
            self.check_status(options['status'])
            
        elif options['cleanup']:
            self.cleanup_tasks(options['cleanup_days'])
            
        elif options['list_pending']:
            self.list_pending_documents()
            
        elif options['retry_failed']:
            self.retry_failed_documents()
            
        else:
            self.stdout.write(
                self.style.ERROR('Please specify an action. Use --help for options.')
            )
    
    def process_single_document(self, document_id: str, force: bool = False):
        """Process a single document"""
        try:
            document = ClinicalDocument.objects.get(id=document_id)
            
            # Check if already processed
            if document.processing_status == 'completed' and not force:
                self.stdout.write(
                    self.style.WARNING(
                        f'Document {document_id} already processed. Use --force to reprocess.'
                    )
                )
                return
            
            # Queue processing task
            task_id = async_task(
                'clinical_records.tasks.process_clinical_document',
                document_id,
                1,  # First attempt
                task_name=f'manual_process_{document_id}',
                timeout=300
            )
            
            self.stdout.write(
                self.style.SUCCESS(
                    f'Queued document {document_id} for processing (task: {task_id})'
                )
            )
            
            # Wait for result if requested
            self.stdout.write('Waiting for processing to complete...')
            
            # Poll for result
            import time
            max_wait = 60  # Wait up to 60 seconds
            waited = 0
            
            while waited < max_wait:
                task_result = result(task_id, wait=1000)  # Wait 1 second
                if task_result is not None:
                    self.stdout.write(
                        self.style.SUCCESS(
                            f'Processing completed: {task_result.get("status", "unknown")}'
                        )
                    )
                    if task_result.get('error'):
                        self.stdout.write(
                            self.style.ERROR(f'Error: {task_result["error"]}')
                        )
                    break
                
                waited += 1
                time.sleep(1)
            
            if waited >= max_wait:
                self.stdout.write(
                    self.style.WARNING(
                        f'Processing is taking longer than expected. Task ID: {task_id}'
                    )
                )
            
        except ClinicalDocument.DoesNotExist:
            raise CommandError(f'Document {document_id} not found')
        except Exception as e:
            raise CommandError(f'Failed to process document: {e}')
    
    def process_batch(self):
        """Process all pending documents in batch"""
        try:
            # Get all pending documents
            pending_docs = ClinicalDocument.objects.filter(
                processing_status__in=['uploaded', 'failed', 'retry_scheduled']
            ).values_list('id', flat=True)
            
            if not pending_docs:
                self.stdout.write(
                    self.style.SUCCESS('No pending documents to process')
                )
                return
            
            # Convert to list of strings
            document_ids = [str(doc_id) for doc_id in pending_docs]
            
            self.stdout.write(
                f'Found {len(document_ids)} pending documents'
            )
            
            # Queue batch processing
            batch_result = batch_process_documents(document_ids)
            
            self.stdout.write(
                self.style.SUCCESS(
                    f'Batch processing queued: {len(batch_result["queued_tasks"])} tasks'
                )
            )
            
            if batch_result['failed_to_queue']:
                self.stdout.write(
                    self.style.WARNING(
                        f'Failed to queue {len(batch_result["failed_to_queue"])} documents'
                    )
                )
                for failed in batch_result['failed_to_queue']:
                    self.stdout.write(f'  - {failed["document_id"]}: {failed["error"]}')
            
        except Exception as e:
            raise CommandError(f'Batch processing failed: {e}')
    
    def check_status(self, document_id: str):
        """Check processing status of a document"""
        try:
            status_info = get_processing_status(document_id)
            
            if 'error' in status_info:
                self.stdout.write(
                    self.style.ERROR(f'Error: {status_info["error"]}')
                )
                return
            
            self.stdout.write(f'Document ID: {document_id}')
            self.stdout.write(f'Status: {status_info["processing_status"]}')
            
            if status_info['processing_started_at']:
                self.stdout.write(f'Started: {status_info["processing_started_at"]}')
            
            if status_info['processing_completed_at']:
                self.stdout.write(f'Completed: {status_info["processing_completed_at"]}')
            
            if status_info['processing_error']:
                self.stdout.write(
                    self.style.ERROR(f'Error: {status_info["processing_error"]}')
                )
            
            if status_info['requires_manual_review']:
                self.stdout.write(
                    self.style.WARNING(
                        f'Manual review required: {status_info["manual_review_reason"]}'
                    )
                )
            
            if status_info['ocr_confidence'] is not None:
                self.stdout.write(f'OCR Confidence: {status_info["ocr_confidence"]:.2f}')
            
            self.stdout.write(f'Has structured data: {status_info["has_structured_data"]}')
            
            # Show related tasks
            if status_info['related_tasks']:
                self.stdout.write('\nRelated tasks:')
                for task in status_info['related_tasks']:
                    status = 'SUCCESS' if task['success'] else 'FAILED'
                    self.stdout.write(f'  - Task {task["task_id"]}: {status}')
                    if task['started']:
                        self.stdout.write(f'    Started: {task["started"]}')
                    if task['stopped']:
                        self.stdout.write(f'    Stopped: {task["stopped"]}')
                    if task['error']:
                        self.stdout.write(f'    Error: {task["error"]}')
            
        except Exception as e:
            raise CommandError(f'Failed to check status: {e}')
    
    def cleanup_tasks(self, days_old: int):
        """Clean up old completed tasks"""
        try:
            self.stdout.write(f'Cleaning up tasks older than {days_old} days...')
            
            cleanup_result = cleanup_old_tasks(days_old)
            
            if cleanup_result['status'] == 'completed':
                self.stdout.write(
                    self.style.SUCCESS(
                        f'Cleaned up {cleanup_result["tasks_deleted"]} old tasks'
                    )
                )
            else:
                self.stdout.write(
                    self.style.ERROR(f'Cleanup failed: {cleanup_result["error"]}')
                )
            
        except Exception as e:
            raise CommandError(f'Cleanup failed: {e}')
    
    def list_pending_documents(self):
        """List all pending documents"""
        try:
            pending_docs = ClinicalDocument.objects.filter(
                processing_status__in=['uploaded', 'failed', 'retry_scheduled']
            ).select_related('clinical_record', 'clinical_record__patient')
            
            if not pending_docs:
                self.stdout.write(
                    self.style.SUCCESS('No pending documents found')
                )
                return
            
            self.stdout.write(f'Found {pending_docs.count()} pending documents:')
            self.stdout.write('')
            
            for doc in pending_docs:
                patient_name = f"{doc.clinical_record.patient.first_name} {doc.clinical_record.patient.last_name}"
                self.stdout.write(
                    f'ID: {doc.id}'
                )
                self.stdout.write(f'  Patient: {patient_name}')
                self.stdout.write(f'  File: {doc.original_filename}')
                self.stdout.write(f'  Type: {doc.content_type}')
                self.stdout.write(f'  Status: {doc.processing_status}')
                self.stdout.write(f'  Uploaded: {doc.created_at}')
                if doc.processing_error:
                    self.stdout.write(
                        self.style.ERROR(f'  Error: {doc.processing_error}')
                    )
                self.stdout.write('')
            
        except Exception as e:
            raise CommandError(f'Failed to list pending documents: {e}')
    
    def retry_failed_documents(self):
        """Retry all failed documents"""
        try:
            failed_docs = ClinicalDocument.objects.filter(
                processing_status='failed'
            ).values_list('id', flat=True)
            
            if not failed_docs:
                self.stdout.write(
                    self.style.SUCCESS('No failed documents to retry')
                )
                return
            
            # Convert to list of strings
            document_ids = [str(doc_id) for doc_id in failed_docs]
            
            self.stdout.write(f'Retrying {len(document_ids)} failed documents...')
            
            # Queue retry processing
            batch_result = batch_process_documents(document_ids)
            
            self.stdout.write(
                self.style.SUCCESS(
                    f'Retry processing queued: {len(batch_result["queued_tasks"])} tasks'
                )
            )
            
            if batch_result['failed_to_queue']:
                self.stdout.write(
                    self.style.WARNING(
                        f'Failed to queue {len(batch_result["failed_to_queue"])} documents for retry'
                    )
                )
            
        except Exception as e:
            raise CommandError(f'Retry processing failed: {e}')