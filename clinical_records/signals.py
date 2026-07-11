"""
Django signals for webhook notifications.

This module contains signal handlers that trigger webhook notifications
when clinical records are created, updated, or processed.
"""

import logging
from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver
from django_q.tasks import async_task

from .models import ClinicalRecord, ClinicalDocument, ShareToken, ManualReview
from .services.webhook_service import WebhookService

logger = logging.getLogger(__name__)


@receiver(post_save, sender=ClinicalRecord)
def clinical_record_saved(sender, instance, created, **kwargs):
    """
    Send webhook notification when a clinical record is created or updated.
    """
    try:
        if created:
            # Record was created
            service = WebhookService()
            service.notify_record_created(instance)
        else:
            # Record was updated
            payload = {
                'record_id': instance.id,
                'patient_id': instance.patient.id,
                'record_type': instance.record_type,
                'title': instance.title,
                'status': instance.status,
                'updated_at': instance.updated_at.isoformat()
            }
            
            service = WebhookService()
            service._send_clinic_webhooks(
                instance.clinic.id,
                'record.updated',
                payload
            )
            
    except Exception as e:
        logger.error(f"Error sending webhook for clinical record {instance.id}: {str(e)}")


@receiver(post_save, sender=ClinicalDocument)
def clinical_document_saved(sender, instance, created, **kwargs):
    """
    Send webhook notification when a clinical document is uploaded or processed.
    """
    try:
        if created:
            # Document was uploaded
            payload = {
                'document_id': instance.id,
                'record_id': instance.clinical_record.id,
                'patient_id': instance.clinical_record.patient.id,
                'file_name': instance.file_name,
                'document_type': instance.document_type,
                'file_size': instance.file_size,
                'uploaded_at': instance.created_at.isoformat()
            }
            
            service = WebhookService()
            service._send_clinic_webhooks(
                instance.clinical_record.clinic.id,
                'document.uploaded',
                payload
            )
            
        elif instance.processing_status == 'completed' and instance.processed_at:
            # Document processing completed
            service = WebhookService()
            service.notify_document_processed(instance)
            
        elif instance.processing_status == 'failed':
            # Document processing failed
            payload = {
                'document_id': instance.id,
                'record_id': instance.clinical_record.id,
                'patient_id': instance.clinical_record.patient.id,
                'file_name': instance.file_name,
                'error_message': instance.processing_error or 'Processing failed',
                'failed_at': instance.updated_at.isoformat()
            }
            
            service = WebhookService()
            service._send_clinic_webhooks(
                instance.clinical_record.clinic.id,
                'document.failed',
                payload
            )
            
    except Exception as e:
        logger.error(f"Error sending webhook for clinical document {instance.id}: {str(e)}")


@receiver(post_save, sender=ShareToken)
def share_token_created(sender, instance, created, **kwargs):
    """
    Send webhook notification when a record is shared.
    """
    if not created:
        return
        
    try:
        service = WebhookService()
        service.notify_record_shared(
            instance.clinical_record,
            instance.token,
            instance.shared_with_email or 'External user'
        )
        
    except Exception as e:
        logger.error(f"Error sending webhook for share token {instance.id}: {str(e)}")


@receiver(post_save, sender=ManualReview)
def manual_review_saved(sender, instance, created, **kwargs):
    """
    Send webhook notification when manual review is required or completed.
    """
    try:
        if created:
            # Manual review required
            payload = {
                'review_id': instance.id,
                'document_id': instance.clinical_document.id,
                'record_id': instance.clinical_document.clinical_record.id,
                'patient_id': instance.clinical_document.clinical_record.patient.id,
                'confidence_score': instance.confidence_score,
                'review_reason': instance.review_reason,
                'created_at': instance.created_at.isoformat()
            }
            
            service = WebhookService()
            service._send_clinic_webhooks(
                instance.clinic.id,
                'manual_review.required',
                payload
            )
            
        elif instance.status == 'completed' and instance.completed_at:
            # Manual review completed
            payload = {
                'review_id': instance.id,
                'document_id': instance.clinical_document.id,
                'record_id': instance.clinical_document.clinical_record.id,
                'patient_id': instance.clinical_document.clinical_record.patient.id,
                'reviewer_id': instance.reviewer.id if instance.reviewer else None,
                'reviewer_name': instance.reviewer.get_full_name() if instance.reviewer else None,
                'final_confidence': instance.final_confidence_score,
                'completed_at': instance.completed_at.isoformat()
            }
            
            service = WebhookService()
            service._send_clinic_webhooks(
                instance.clinic.id,
                'manual_review.completed',
                payload
            )
            
    except Exception as e:
        logger.error(f"Error sending webhook for manual review {instance.id}: {str(e)}")


# Signal handler for share token access (when someone accesses a shared record)
def notify_record_accessed(share_token, access_info):
    """
    Send webhook notification when a shared record is accessed.
    This is called manually from the sharing views.
    """
    try:
        payload = {
            'record_id': share_token.clinical_record.id,
            'patient_id': share_token.clinical_record.patient.id,
            'share_token': share_token.token,
            'accessed_by_ip': access_info.get('ip_address'),
            'accessed_by_user_agent': access_info.get('user_agent'),
            'accessed_at': access_info.get('accessed_at')
        }
        
        service = WebhookService()
        service._send_clinic_webhooks(
            share_token.clinical_record.clinic.id,
            'record.accessed',
            payload
        )
        
    except Exception as e:
        logger.error(f"Error sending webhook for record access: {str(e)}")