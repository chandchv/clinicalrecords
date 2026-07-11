"""
Django signals for automatic Elasticsearch synchronization.
"""

import logging
from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver
from django.conf import settings

from ..models import ClinicalRecord, ClinicalDocument
from ..services.elasticsearch_service import elasticsearch_service

logger = logging.getLogger(__name__)


@receiver(post_save, sender=ClinicalRecord)
def sync_clinical_record_to_elasticsearch(sender, instance, created, **kwargs):
    """
    Sync clinical record to Elasticsearch when saved.
    
    Args:
        sender: The model class
        instance: The actual instance being saved
        created: Boolean indicating if this is a new record
        **kwargs: Additional keyword arguments
    """
    # Only sync if Elasticsearch is enabled and auto-sync is on
    if not getattr(settings, 'ELASTICSEARCH_AUTO_SYNC', True):
        return
    
    if not elasticsearch_service.is_enabled():
        return
    
    try:
        # Index the clinical record
        result = elasticsearch_service.index_clinical_record(instance)
        
        if result['status'] == 'success':
            action = 'created' if created else 'updated'
            logger.debug(f"Clinical record {instance.id} {action} in Elasticsearch")
        else:
            logger.warning(f"Failed to sync clinical record {instance.id}: {result.get('message', 'Unknown error')}")
            
    except Exception as e:
        logger.error(f"Error syncing clinical record {instance.id} to Elasticsearch: {e}")


@receiver(post_delete, sender=ClinicalRecord)
def remove_clinical_record_from_elasticsearch(sender, instance, **kwargs):
    """
    Remove clinical record from Elasticsearch when deleted.
    
    Args:
        sender: The model class
        instance: The actual instance being deleted
        **kwargs: Additional keyword arguments
    """
    if not getattr(settings, 'ELASTICSEARCH_AUTO_SYNC', True):
        return
    
    if not elasticsearch_service.is_enabled():
        return
    
    try:
        # Remove from Elasticsearch
        result = elasticsearch_service.delete_clinical_record(str(instance.id))
        
        if result['status'] == 'success':
            logger.debug(f"Clinical record {instance.id} removed from Elasticsearch")
        else:
            logger.warning(f"Failed to remove clinical record {instance.id}: {result.get('message', 'Unknown error')}")
            
    except Exception as e:
        logger.error(f"Error removing clinical record {instance.id} from Elasticsearch: {e}")


@receiver(post_save, sender=ClinicalDocument)
def sync_clinical_document_to_elasticsearch(sender, instance, created, **kwargs):
    """
    Sync clinical document to Elasticsearch when saved.
    
    Args:
        sender: The model class
        instance: The actual instance being saved
        created: Boolean indicating if this is a new document
        **kwargs: Additional keyword arguments
    """
    if not getattr(settings, 'ELASTICSEARCH_AUTO_SYNC', True):
        return
    
    if not elasticsearch_service.is_enabled():
        return
    
    try:
        # Only index if document has been processed (has OCR text or structured data)
        if instance.processing_status == 'completed' or instance.ocr_text or instance.structured_data:
            result = elasticsearch_service.index_clinical_document(instance)
            
            if result['status'] == 'success':
                action = 'created' if created else 'updated'
                logger.debug(f"Clinical document {instance.id} {action} in Elasticsearch")
            else:
                logger.warning(f"Failed to sync clinical document {instance.id}: {result.get('message', 'Unknown error')}")
        else:
            logger.debug(f"Skipping Elasticsearch sync for unprocessed document {instance.id}")
            
    except Exception as e:
        logger.error(f"Error syncing clinical document {instance.id} to Elasticsearch: {e}")


@receiver(post_delete, sender=ClinicalDocument)
def remove_clinical_document_from_elasticsearch(sender, instance, **kwargs):
    """
    Remove clinical document from Elasticsearch when deleted.
    
    Args:
        sender: The model class
        instance: The actual instance being deleted
        **kwargs: Additional keyword arguments
    """
    if not getattr(settings, 'ELASTICSEARCH_AUTO_SYNC', True):
        return
    
    if not elasticsearch_service.is_enabled():
        return
    
    try:
        # Remove from Elasticsearch
        result = elasticsearch_service.delete_clinical_document(str(instance.id))
        
        if result['status'] == 'success':
            logger.debug(f"Clinical document {instance.id} removed from Elasticsearch")
        else:
            logger.warning(f"Failed to remove clinical document {instance.id}: {result.get('message', 'Unknown error')}")
            
    except Exception as e:
        logger.error(f"Error removing clinical document {instance.id} from Elasticsearch: {e}")


def bulk_sync_to_elasticsearch(clinic_id=None, force_reindex=False):
    """
    Bulk synchronize all clinical records and documents to Elasticsearch.
    
    Args:
        clinic_id: Optional clinic ID to sync specific clinic data
        force_reindex: Force reindexing even if already indexed
        
    Returns:
        Dict containing sync results
    """
    if not elasticsearch_service.is_enabled():
        return {'status': 'disabled', 'message': 'Elasticsearch is not enabled'}
    
    try:
        logger.info(f"Starting bulk sync to Elasticsearch (clinic_id: {clinic_id})")
        
        # Create indices if they don't exist
        indices_result = elasticsearch_service.create_indices()
        if indices_result['status'] != 'success':
            return {'status': 'error', 'message': f"Failed to create indices: {indices_result.get('message')}"}
        
        # Reindex all data
        reindex_result = elasticsearch_service.reindex_all_data(clinic_id)
        
        if reindex_result['status'] == 'success':
            results = reindex_result['results']
            logger.info(f"Bulk sync completed: {results['records']} records, {results['documents']} documents")
            
            return {
                'status': 'success',
                'records_synced': results['records'],
                'documents_synced': results['documents'],
                'errors': results['errors']
            }
        else:
            return {'status': 'error', 'message': reindex_result.get('message', 'Unknown error')}
            
    except Exception as e:
        logger.error(f"Bulk sync to Elasticsearch failed: {e}")
        return {'status': 'error', 'message': str(e)}


def setup_elasticsearch_indices():
    """
    Set up Elasticsearch indices with proper mappings.
    
    Returns:
        Dict containing setup results
    """
    if not elasticsearch_service.is_enabled():
        return {'status': 'disabled', 'message': 'Elasticsearch is not enabled'}
    
    try:
        logger.info("Setting up Elasticsearch indices")
        
        # Create indices
        result = elasticsearch_service.create_indices()
        
        if result['status'] == 'success':
            logger.info(f"Elasticsearch indices setup completed: {result['indices']}")
            return result
        else:
            logger.error(f"Failed to setup Elasticsearch indices: {result.get('message')}")
            return result
            
    except Exception as e:
        logger.error(f"Elasticsearch indices setup failed: {e}")
        return {'status': 'error', 'message': str(e)}


def check_elasticsearch_health():
    """
    Check Elasticsearch cluster health and connectivity.
    
    Returns:
        Dict containing health status
    """
    if not elasticsearch_service.is_enabled():
        return {'status': 'disabled', 'message': 'Elasticsearch is not enabled'}
    
    try:
        # Check if client is available
        if not elasticsearch_service.client:
            return {'status': 'error', 'message': 'Elasticsearch client not initialized'}
        
        # Ping Elasticsearch
        if not elasticsearch_service.client.ping():
            return {'status': 'error', 'message': 'Cannot connect to Elasticsearch'}
        
        # Get cluster health
        health = elasticsearch_service.client.cluster.health()
        
        # Get indices info
        indices_info = {}
        try:
            records_index = f"{elasticsearch_service.index_prefix}_records"
            documents_index = f"{elasticsearch_service.index_prefix}_documents"
            
            if elasticsearch_service.client.indices.exists(index=records_index):
                records_stats = elasticsearch_service.client.indices.stats(index=records_index)
                indices_info['records'] = {
                    'exists': True,
                    'doc_count': records_stats['indices'][records_index]['total']['docs']['count'],
                    'size': records_stats['indices'][records_index]['total']['store']['size_in_bytes']
                }
            else:
                indices_info['records'] = {'exists': False}
            
            if elasticsearch_service.client.indices.exists(index=documents_index):
                documents_stats = elasticsearch_service.client.indices.stats(index=documents_index)
                indices_info['documents'] = {
                    'exists': True,
                    'doc_count': documents_stats['indices'][documents_index]['total']['docs']['count'],
                    'size': documents_stats['indices'][documents_index]['total']['store']['size_in_bytes']
                }
            else:
                indices_info['documents'] = {'exists': False}
                
        except Exception as e:
            logger.warning(f"Failed to get indices info: {e}")
            indices_info = {'error': str(e)}
        
        return {
            'status': 'healthy',
            'cluster_name': health['cluster_name'],
            'cluster_status': health['status'],
            'number_of_nodes': health['number_of_nodes'],
            'active_primary_shards': health['active_primary_shards'],
            'active_shards': health['active_shards'],
            'indices': indices_info
        }
        
    except Exception as e:
        logger.error(f"Elasticsearch health check failed: {e}")
        return {'status': 'error', 'message': str(e)}


# Signal handler for share token access (when someone accesses a shared record)
def notify_record_accessed(share_token, access_info):
    """
    Send webhook notification when a shared record is accessed.
    This is called manually from the sharing views.
    """
    try:
        from ..services.webhook_service import WebhookService
        
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