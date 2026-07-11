"""
Webhook management views for clinical records.

This module provides API endpoints for managing webhook configurations
and monitoring webhook deliveries.
"""

import logging
from typing import Dict, Any

from django.http import JsonResponse
from django.utils import timezone
from django.db import transaction
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated

from ..models import WebhookConfiguration, WebhookDelivery
from ..serializers import WebhookConfigurationSerializer, WebhookDeliverySerializer
from ..permissions import ClinicalRecordsPermission
from ..services.webhook_service import WebhookService

logger = logging.getLogger(__name__)


class WebhookConfigurationViewSet(viewsets.ModelViewSet):
    """
    ViewSet for managing webhook configurations.
    
    Provides CRUD operations for webhook configurations with tenant isolation.
    """
    
    serializer_class = WebhookConfigurationSerializer
    permission_classes = [IsAuthenticated, ClinicalRecordsPermission]
    
    def get_queryset(self):
        """Filter webhook configurations by current clinic."""
        return WebhookConfiguration.objects.filter(
            clinic=self.request.user.clinic
        ).order_by('name')
    
    def perform_create(self, serializer):
        """Set clinic when creating webhook configuration."""
        serializer.save(clinic=self.request.user.clinic)
    
    @action(detail=True, methods=['post'])
    def test_webhook(self, request, pk=None):
        """
        Test a webhook configuration by sending a test event.
        """
        webhook_config = self.get_object()
        
        try:
            # Create test payload
            test_payload = {
                'test': True,
                'message': 'This is a test webhook from RxDoctor Clinical Records',
                'timestamp': timezone.now().isoformat(),
                'clinic_name': webhook_config.clinic.name
            }
            
            # Send test webhook
            service = WebhookService()
            delivery = service.send_webhook(
                webhook_config=webhook_config,
                event_type='test.webhook',
                payload=test_payload
            )
            
            return Response({
                'success': True,
                'message': 'Test webhook sent',
                'delivery_id': delivery.id,
                'status': delivery.status
            })
            
        except Exception as e:
            logger.error(f"Error testing webhook {pk}: {str(e)}")
            return Response({
                'success': False,
                'error': str(e)
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    
    @action(detail=True, methods=['post'])
    def toggle_status(self, request, pk=None):
        """
        Toggle webhook configuration active status.
        """
        webhook_config = self.get_object()
        
        try:
            webhook_config.is_active = not webhook_config.is_active
            if webhook_config.is_active and webhook_config.status == 'failed':
                webhook_config.status = 'active'
            elif not webhook_config.is_active:
                webhook_config.status = 'inactive'
                
            webhook_config.save(update_fields=['is_active', 'status'])
            
            return Response({
                'success': True,
                'is_active': webhook_config.is_active,
                'status': webhook_config.status
            })
            
        except Exception as e:
            logger.error(f"Error toggling webhook status {pk}: {str(e)}")
            return Response({
                'success': False,
                'error': str(e)
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    
    @action(detail=True, methods=['get'])
    def statistics(self, request, pk=None):
        """
        Get webhook delivery statistics.
        """
        webhook_config = self.get_object()
        
        try:
            # Get recent delivery statistics
            recent_deliveries = WebhookDelivery.objects.filter(
                webhook_config=webhook_config,
                created_at__gte=timezone.now() - timezone.timedelta(days=30)
            )
            
            stats = {
                'total_sent': webhook_config.total_sent,
                'total_failed': webhook_config.total_failed,
                'success_rate': 0,
                'last_sent_at': webhook_config.last_sent_at,
                'last_failed_at': webhook_config.last_failed_at,
                'recent_deliveries': {
                    'total': recent_deliveries.count(),
                    'sent': recent_deliveries.filter(status='sent').count(),
                    'failed': recent_deliveries.filter(status='failed').count(),
                    'pending': recent_deliveries.filter(status='pending').count(),
                    'retrying': recent_deliveries.filter(status='retrying').count(),
                }
            }
            
            # Calculate success rate
            total_attempts = webhook_config.total_sent + webhook_config.total_failed
            if total_attempts > 0:
                stats['success_rate'] = round(
                    (webhook_config.total_sent / total_attempts) * 100, 2
                )
            
            return Response(stats)
            
        except Exception as e:
            logger.error(f"Error getting webhook statistics {pk}: {str(e)}")
            return Response({
                'error': str(e)
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class WebhookDeliveryViewSet(viewsets.ReadOnlyModelViewSet):
    """
    ViewSet for viewing webhook delivery logs.
    
    Provides read-only access to webhook delivery records for monitoring and debugging.
    """
    
    serializer_class = WebhookDeliverySerializer
    permission_classes = [IsAuthenticated, ClinicalRecordsPermission]
    
    def get_queryset(self):
        """Filter webhook deliveries by current clinic."""
        queryset = WebhookDelivery.objects.filter(
            clinic=self.request.user.clinic
        ).select_related('webhook_config').order_by('-created_at')
        
        # Filter by webhook configuration if specified
        webhook_config_id = self.request.query_params.get('webhook_config')
        if webhook_config_id:
            queryset = queryset.filter(webhook_config_id=webhook_config_id)
        
        # Filter by status if specified
        status_filter = self.request.query_params.get('status')
        if status_filter:
            queryset = queryset.filter(status=status_filter)
        
        # Filter by event type if specified
        event_type = self.request.query_params.get('event_type')
        if event_type:
            queryset = queryset.filter(event_type=event_type)
        
        return queryset
    
    @action(detail=True, methods=['post'])
    def retry_delivery(self, request, pk=None):
        """
        Manually retry a failed webhook delivery.
        """
        delivery = self.get_object()
        
        if delivery.status not in ['failed']:
            return Response({
                'success': False,
                'error': 'Only failed deliveries can be retried'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            # Reset delivery status and schedule retry
            delivery.status = 'retrying'
            delivery.next_retry_at = timezone.now()
            delivery.save(update_fields=['status', 'next_retry_at'])
            
            # Send webhook using service
            service = WebhookService()
            webhook_payload = {
                'event_type': delivery.event_type,
                'timestamp': timezone.now().isoformat(),
                'clinic_id': delivery.clinic.id,
                'data': delivery.request_payload
            }
            
            headers = delivery.request_headers.copy()
            if delivery.webhook_config.secret:
                signature = service._generate_signature(
                    webhook_payload, 
                    delivery.webhook_config.secret
                )
                headers['X-Webhook-Signature'] = signature
            
            service._send_webhook_request(
                delivery,
                delivery.webhook_config.url,
                webhook_payload,
                headers
            )
            
            return Response({
                'success': True,
                'message': 'Webhook delivery retried',
                'status': delivery.status
            })
            
        except Exception as e:
            logger.error(f"Error retrying webhook delivery {pk}: {str(e)}")
            return Response({
                'success': False,
                'error': str(e)
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


def webhook_endpoint_test(request):
    """
    Test endpoint for receiving webhooks during development.
    
    This endpoint can be used to test webhook deliveries during development.
    It logs all received webhooks and returns a success response.
    """
    if request.method == 'POST':
        try:
            import json
            
            # Log the received webhook
            headers = dict(request.headers)
            body = request.body.decode('utf-8')
            
            logger.info(f"Received webhook test:")
            logger.info(f"Headers: {headers}")
            logger.info(f"Body: {body}")
            
            # Parse JSON body if possible
            try:
                data = json.loads(body)
                logger.info(f"Parsed data: {data}")
            except json.JSONDecodeError:
                logger.info("Body is not valid JSON")
            
            return JsonResponse({
                'success': True,
                'message': 'Webhook received successfully',
                'timestamp': timezone.now().isoformat()
            })
            
        except Exception as e:
            logger.error(f"Error in webhook test endpoint: {str(e)}")
            return JsonResponse({
                'success': False,
                'error': str(e)
            }, status=500)
    
    return JsonResponse({
        'success': False,
        'error': 'Only POST method allowed'
    }, status=405)