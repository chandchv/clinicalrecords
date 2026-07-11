"""
Webhook notification service for clinical records management.

This service handles sending webhook notifications to external systems
when clinical records are created, updated, or processed.
"""

import json
import logging
import hashlib
import hmac
import time
from typing import Dict, Any, Optional, List
from urllib.parse import urlparse

import requests
from django.conf import settings
from django.core.cache import cache
from django.utils import timezone
from django_q.tasks import async_task

from ..models import ClinicalRecord, ClinicalDocument, WebhookConfiguration, WebhookDelivery

logger = logging.getLogger(__name__)


class WebhookService:
    """Service for managing webhook notifications."""
    
    def __init__(self):
        self.default_timeout = 30
        self.default_max_retries = 3
        self.default_retry_delays = [60, 300, 900]  # 1min, 5min, 15min
        
    def send_webhook(self, webhook_config: WebhookConfiguration, event_type: str, 
                    payload: Dict[str, Any]) -> WebhookDelivery:
        """
        Send a webhook notification to an external endpoint.
        
        Args:
            webhook_config: WebhookConfiguration instance
            event_type: Type of event (e.g., 'record.created', 'document.processed')
            payload: Event data to send
            
        Returns:
            WebhookDelivery: The delivery record
        """
        # Create delivery record
        delivery = WebhookDelivery.objects.create(
            webhook_config=webhook_config,
            event_type=event_type,
            request_payload=payload,
            clinic=webhook_config.clinic
        )
        
        try:
            # Check if event is enabled for this webhook
            if not webhook_config.is_event_enabled(event_type):
                delivery.mark_as_failed("Event type not enabled for this webhook")
                return delivery
                
            # Validate webhook URL
            if not self._is_valid_url(webhook_config.url):
                delivery.mark_as_failed(f"Invalid webhook URL: {webhook_config.url}")
                return delivery
                
            # Prepare webhook payload
            webhook_payload = {
                'event_type': event_type,
                'timestamp': timezone.now().isoformat(),
                'clinic_id': webhook_config.clinic.id,
                'data': payload
            }
            
            # Generate signature if secret is provided
            headers = {'Content-Type': 'application/json'}
            if webhook_config.secret:
                signature = self._generate_signature(webhook_payload, webhook_config.secret)
                headers['X-Webhook-Signature'] = signature
                
            delivery.request_headers = headers
            delivery.save(update_fields=['request_headers'])
                
            # Send webhook
            self._send_webhook_request(delivery, webhook_config.url, webhook_payload, headers)
            return delivery
            
        except Exception as e:
            logger.error(f"Error sending webhook: {str(e)}")
            delivery.mark_as_failed(str(e))
            return delivery
            
    def _send_webhook_request(self, delivery: WebhookDelivery, url: str, 
                             payload: Dict[str, Any], headers: Dict[str, str]):
        """Send webhook request and handle response."""
        delivery.increment_attempt()
        
        try:
            response = requests.post(
                url,
                json=payload,
                headers=headers,
                timeout=delivery.webhook_config.timeout_seconds
            )
            
            if response.status_code in [200, 201, 202]:
                delivery.mark_as_sent(
                    status_code=response.status_code,
                    response_body=response.text,
                    response_headers=dict(response.headers)
                )
                logger.info(f"Webhook sent successfully to {url}")
            else:
                error_msg = f"HTTP {response.status_code}: {response.text}"
                self._handle_webhook_failure(delivery, error_msg, response.status_code, response.text)
                
        except requests.exceptions.RequestException as e:
            error_msg = f"Request failed: {str(e)}"
            self._handle_webhook_failure(delivery, error_msg)
            
    def _handle_webhook_failure(self, delivery: WebhookDelivery, error_message: str,
                               status_code: int = None, response_body: str = ""):
        """Handle webhook delivery failure and schedule retries if needed."""
        max_retries = delivery.webhook_config.max_retries
        
        if delivery.attempt_count <= max_retries:
            # Schedule retry
            retry_delays = delivery.webhook_config.retry_delays or self.default_retry_delays
            delay_index = min(delivery.attempt_count - 1, len(retry_delays) - 1)
            delay = retry_delays[delay_index]
            
            delivery.schedule_retry(delay)
            
            # Schedule async retry task
            async_task(
                'clinical_records.services.webhook_service.retry_webhook_delivery',
                delivery.id,
                schedule=timezone.now() + timezone.timedelta(seconds=delay)
            )
            
            logger.warning(f"Webhook failed, scheduled retry in {delay}s: {error_message}")
        else:
            # Max retries exceeded, mark as permanently failed
            delivery.mark_as_failed(error_message, status_code, response_body)
            logger.error(f"Webhook failed after {max_retries} retries: {error_message}")
        
    def _generate_signature(self, payload: Dict[str, Any], secret: str) -> str:
        """Generate HMAC signature for webhook verification."""
        payload_str = json.dumps(payload, sort_keys=True)
        signature = hmac.new(
            secret.encode('utf-8'),
            payload_str.encode('utf-8'),
            hashlib.sha256
        ).hexdigest()
        return f"sha256={signature}"
        
    def _is_valid_url(self, url: str) -> bool:
        """Validate webhook URL."""
        try:
            parsed = urlparse(url)
            return parsed.scheme in ['http', 'https'] and parsed.netloc
        except Exception:
            return False
            
    def notify_record_created(self, record: ClinicalRecord) -> None:
        """Send webhook notification when a clinical record is created."""
        payload = {
            'record_id': record.id,
            'patient_id': record.patient.id,
            'record_type': record.record_type,
            'title': record.title,
            'created_at': record.created_at.isoformat()
        }
        
        self._send_clinic_webhooks(
            record.clinic.id,
            'record.created',
            payload
        )
        
    def notify_document_processed(self, document: ClinicalDocument) -> None:
        """Send webhook notification when a document is processed."""
        payload = {
            'document_id': document.id,
            'record_id': document.clinical_record.id,
            'patient_id': document.clinical_record.patient.id,
            'file_name': document.file_name,
            'processing_status': document.processing_status,
            'processed_at': document.processed_at.isoformat() if document.processed_at else None,
            'ocr_confidence': document.ocr_confidence,
            'extracted_data_summary': document.extracted_data.get('summary', {}) if document.extracted_data else {}
        }
        
        self._send_clinic_webhooks(
            document.clinical_record.clinic.id,
            'document.processed',
            payload
        )
        
    def notify_record_shared(self, record: ClinicalRecord, share_token: str, 
                           shared_with: str) -> None:
        """Send webhook notification when a record is shared."""
        payload = {
            'record_id': record.id,
            'patient_id': record.patient.id,
            'share_token': share_token,
            'shared_with': shared_with,
            'shared_at': timezone.now().isoformat()
        }
        
        self._send_clinic_webhooks(
            record.clinic.id,
            'record.shared',
            payload
        )
        
    def _send_clinic_webhooks(self, clinic_id: int, event_type: str, 
                             payload: Dict[str, Any]) -> None:
        """Send webhooks to all configured endpoints for a clinic."""
        try:
            webhook_configs = WebhookConfiguration.objects.filter(
                clinic_id=clinic_id,
                is_active=True,
                status='active'
            )
            
            for config in webhook_configs:
                if config.is_event_enabled(event_type):
                    async_task(
                        'clinical_records.services.webhook_service.send_webhook_async',
                        config.id,
                        event_type,
                        payload
                    )
        except Exception as e:
            logger.error(f"Error sending clinic webhooks: {str(e)}")
                



# Async task functions for Django-Q
def send_webhook_async(webhook_config_id: int, event_type: str, payload: Dict[str, Any]):
    """Async task wrapper for sending webhooks."""
    try:
        webhook_config = WebhookConfiguration.objects.get(id=webhook_config_id)
        service = WebhookService()
        return service.send_webhook(webhook_config, event_type, payload)
    except WebhookConfiguration.DoesNotExist:
        logger.error(f"Webhook configuration {webhook_config_id} not found")
        return None
    except Exception as e:
        logger.error(f"Error in async webhook task: {str(e)}")
        return None


def retry_webhook_delivery(delivery_id: int):
    """Retry webhook delivery."""
    try:
        delivery = WebhookDelivery.objects.get(id=delivery_id)
        service = WebhookService()
        
        # Prepare payload and headers
        webhook_payload = {
            'event_type': delivery.event_type,
            'timestamp': timezone.now().isoformat(),
            'clinic_id': delivery.clinic.id,
            'data': delivery.request_payload
        }
        
        headers = delivery.request_headers.copy()
        
        # Update signature if secret is provided
        if delivery.webhook_config.secret:
            signature = service._generate_signature(webhook_payload, delivery.webhook_config.secret)
            headers['X-Webhook-Signature'] = signature
        
        # Send the webhook
        service._send_webhook_request(
            delivery, 
            delivery.webhook_config.url, 
            webhook_payload, 
            headers
        )
        
        return True
        
    except WebhookDelivery.DoesNotExist:
        logger.error(f"Webhook delivery {delivery_id} not found")
        return False
    except Exception as e:
        logger.error(f"Error in webhook retry task: {str(e)}")
        return False