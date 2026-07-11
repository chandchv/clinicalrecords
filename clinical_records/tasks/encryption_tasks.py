"""
Django-Q tasks for encryption operations.

This module contains background tasks for encrypting documents,
key rotation, and encryption maintenance operations.
"""

import logging
from typing import Dict, Any

from django.utils import timezone
from django_q.tasks import async_task

logger = logging.getLogger(__name__)


def encrypt_document_task(document_id: str) -> Dict[str, Any]:
    """
    Background task to encrypt a clinical document.
    
    Args:
        document_id: UUID of the ClinicalDocument to encrypt
        
    Returns:
        Dict with encryption result
    """
    try:
        from ..models import ClinicalDocument
        
        document = ClinicalDocument.objects.get(id=document_id)
        
        # Encrypt the document
        result = document.encrypt_file()
        
        logger.info(f"Document {document_id} encryption result: {result['status']}")
        return result
        
    except ClinicalDocument.DoesNotExist:
        error_msg = f"Document {document_id} not found"
        logger.error(error_msg)
        return {
            'status': 'error',
            'message': error_msg
        }
    except Exception as e:
        error_msg = f"Error encrypting document {document_id}: {str(e)}"
        logger.error(error_msg)
        return {
            'status': 'error',
            'message': error_msg
        }


def encrypt_clinic_documents_task(clinic_id: int, force: bool = False) -> Dict[str, Any]:
    """
    Background task to encrypt all documents for a clinic.
    
    Args:
        clinic_id: ID of the clinic
        force: Force encryption even if already encrypted
        
    Returns:
        Dict with encryption results
    """
    try:
        from ..models import ClinicalDocument
        from ..services.encryption_service import EncryptionService
        
        encryption_service = EncryptionService()
        
        # Get documents to encrypt
        if force:
            documents = ClinicalDocument.objects.filter(
                clinical_record__clinic_id=clinic_id
            )
        else:
            documents = ClinicalDocument.objects.filter(
                clinical_record__clinic_id=clinic_id,
                is_encrypted=False
            )
        
        results = {
            'clinic_id': clinic_id,
            'total_documents': documents.count(),
            'processed': 0,
            'errors': 0,
            'error_details': [],
            'started_at': timezone.now().isoformat()
        }
        
        for document in documents:
            try:
                if document.file and document.file.path:
                    # Encrypt the file
                    metadata = encryption_service.encrypt_file(
                        document.file.path,
                        clinic_id
                    )
                    
                    # Update document record
                    document.is_encrypted = True
                    document.metadata.update({
                        'encryption': metadata
                    })
                    document.save(update_fields=['is_encrypted', 'metadata'])
                    
                    results['processed'] += 1
                    
            except Exception as e:
                results['errors'] += 1
                results['error_details'].append({
                    'document_id': str(document.id),
                    'filename': document.original_filename,
                    'error': str(e)
                })
                logger.error(f"Error encrypting document {document.id}: {str(e)}")
        
        results['completed_at'] = timezone.now().isoformat()
        logger.info(f"Clinic {clinic_id} encryption completed: {results['processed']} processed, {results['errors']} errors")
        
        return results
        
    except Exception as e:
        error_msg = f"Error encrypting clinic {clinic_id} documents: {str(e)}"
        logger.error(error_msg)
        return {
            'clinic_id': clinic_id,
            'status': 'error',
            'message': error_msg
        }


def rotate_clinic_keys_task(clinic_id: int) -> Dict[str, Any]:
    """
    Background task to rotate encryption keys for a clinic.
    
    Args:
        clinic_id: ID of the clinic
        
    Returns:
        Dict with rotation results
    """
    try:
        from ..services.encryption_service import rotate_tenant_keys
        
        logger.info(f"Starting key rotation for clinic {clinic_id}")
        
        results = rotate_tenant_keys(clinic_id)
        results['completed_at'] = timezone.now().isoformat()
        
        logger.info(f"Key rotation completed for clinic {clinic_id}: {results['processed']} processed, {results['errors']} errors")
        
        return results
        
    except Exception as e:
        error_msg = f"Error rotating keys for clinic {clinic_id}: {str(e)}"
        logger.error(error_msg)
        return {
            'clinic_id': clinic_id,
            'status': 'error',
            'message': error_msg
        }


def verify_encryption_integrity_task(clinic_id: int) -> Dict[str, Any]:
    """
    Background task to verify encryption integrity for all clinic documents.
    
    Args:
        clinic_id: ID of the clinic
        
    Returns:
        Dict with verification results
    """
    try:
        from ..models import ClinicalDocument
        from ..services.encryption_service import EncryptionService
        
        encryption_service = EncryptionService()
        
        # Get encrypted documents with file hashes
        documents = ClinicalDocument.objects.filter(
            clinical_record__clinic_id=clinic_id,
            is_encrypted=True
        ).exclude(file_hash='')
        
        results = {
            'clinic_id': clinic_id,
            'total_documents': documents.count(),
            'verified': 0,
            'failed': 0,
            'error_details': [],
            'started_at': timezone.now().isoformat()
        }
        
        for document in documents:
            try:
                if document.file and document.file.path and document.file_hash:
                    # Verify file integrity
                    is_valid = encryption_service.verify_file_integrity(
                        document.file.path,
                        clinic_id,
                        document.file_hash
                    )
                    
                    if is_valid:
                        results['verified'] += 1
                    else:
                        results['failed'] += 1
                        results['error_details'].append({
                            'document_id': str(document.id),
                            'filename': document.original_filename,
                            'error': 'File integrity check failed'
                        })
                        
            except Exception as e:
                results['failed'] += 1
                results['error_details'].append({
                    'document_id': str(document.id),
                    'filename': document.original_filename,
                    'error': str(e)
                })
                logger.error(f"Error verifying document {document.id}: {str(e)}")
        
        results['completed_at'] = timezone.now().isoformat()
        logger.info(f"Integrity verification completed for clinic {clinic_id}: {results['verified']} verified, {results['failed']} failed")
        
        return results
        
    except Exception as e:
        error_msg = f"Error verifying encryption integrity for clinic {clinic_id}: {str(e)}"
        logger.error(error_msg)
        return {
            'clinic_id': clinic_id,
            'status': 'error',
            'message': error_msg
        }


def cleanup_temp_decrypted_files_task() -> Dict[str, Any]:
    """
    Background task to clean up temporary decrypted files.
    
    Returns:
        Dict with cleanup results
    """
    try:
        import os
        import tempfile
        import time
        
        temp_dir = tempfile.gettempdir()
        cleanup_count = 0
        error_count = 0
        
        # Look for temporary files older than 1 hour
        cutoff_time = time.time() - 3600  # 1 hour ago
        
        for filename in os.listdir(temp_dir):
            if filename.startswith('tmp') and 'clinical_records' in filename:
                file_path = os.path.join(temp_dir, filename)
                try:
                    if os.path.getmtime(file_path) < cutoff_time:
                        os.unlink(file_path)
                        cleanup_count += 1
                except Exception as e:
                    error_count += 1
                    logger.warning(f"Error cleaning up temp file {file_path}: {str(e)}")
        
        results = {
            'cleaned_up': cleanup_count,
            'errors': error_count,
            'completed_at': timezone.now().isoformat()
        }
        
        if cleanup_count > 0:
            logger.info(f"Cleaned up {cleanup_count} temporary decrypted files")
        
        return results
        
    except Exception as e:
        error_msg = f"Error cleaning up temporary files: {str(e)}"
        logger.error(error_msg)
        return {
            'status': 'error',
            'message': error_msg
        }


def schedule_encryption_maintenance():
    """
    Schedule regular encryption maintenance tasks.
    """
    try:
        # Schedule temp file cleanup every hour
        async_task(
            'clinical_records.tasks.encryption_tasks.cleanup_temp_decrypted_files_task',
            schedule=timezone.now() + timezone.timedelta(hours=1)
        )
        
        logger.info("Scheduled encryption maintenance tasks")
        
    except Exception as e:
        logger.error(f"Error scheduling encryption maintenance: {str(e)}")


# Task registration for Django-Q
def register_encryption_tasks():
    """
    Register encryption tasks with Django-Q.
    This function can be called during app initialization.
    """
    try:
        # Schedule initial maintenance
        schedule_encryption_maintenance()
        
        logger.info("Encryption tasks registered successfully")
        
    except Exception as e:
        logger.error(f"Error registering encryption tasks: {str(e)}")