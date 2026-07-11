"""
API views for Elasticsearch-powered search functionality.
"""

import logging
from typing import Dict, Any
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator
from django.views import View

from ..services.elasticsearch_service import elasticsearch_service
from ..permissions.rest_permissions import TenantPermission
from users.models import AuditLog

logger = logging.getLogger(__name__)


@api_view(['GET'])
@permission_classes([IsAuthenticated, TenantPermission])
def search_clinical_records(request):
    """
    Search clinical records using Elasticsearch.
    
    Query Parameters:
        q: Search query string
        record_type: Filter by record type
        patient_id: Filter by patient ID
        date_from: Filter by date range (from)
        date_to: Filter by date range (to)
        has_structured_data: Filter by presence of structured data
        page: Page number (default: 1)
        page_size: Results per page (default: 20, max: 100)
        sort_by: Sort field (_score, created_at, updated_at, title)
    """
    try:
        # Get search parameters
        query = request.GET.get('q', '').strip()
        clinic_id = str(request.user.current_tenant.id)
        
        # Build filters
        filters = {}
        
        if request.GET.get('record_type'):
            filters['record_type'] = request.GET.get('record_type')
        
        if request.GET.get('patient_id'):
            filters['patient_id'] = request.GET.get('patient_id')
        
        if request.GET.get('date_from') or request.GET.get('date_to'):
            date_range = {}
            if request.GET.get('date_from'):
                date_range['from'] = request.GET.get('date_from')
            if request.GET.get('date_to'):
                date_range['to'] = request.GET.get('date_to')
            filters['date_range'] = date_range
        
        if request.GET.get('has_structured_data') is not None:
            filters['has_structured_data'] = request.GET.get('has_structured_data').lower() == 'true'
        
        # Pagination parameters
        try:
            page = int(request.GET.get('page', 1))
            page_size = min(int(request.GET.get('page_size', 20)), 100)
        except (ValueError, TypeError):
            page = 1
            page_size = 20
        
        # Sort parameter
        sort_by = request.GET.get('sort_by', '_score')
        if sort_by not in ['_score', 'created_at', 'updated_at', 'title']:
            sort_by = '_score'
        
        # Perform search
        search_result = elasticsearch_service.search_clinical_records(
            query=query,
            clinic_id=clinic_id,
            filters=filters,
            page=page,
            page_size=page_size,
            sort_by=sort_by
        )
        
        # Log search activity
        AuditLog.log_action(
            user=request.user,
            action='CLINICAL_RECORDS_SEARCH',
            resource_type='SEARCH',
            resource_id=None,
            details=f"Search query: '{query}', Results: {search_result.get('total', 0)}",
            tenant=request.user.current_tenant
        )
        
        return Response(search_result, status=status.HTTP_200_OK)
        
    except Exception as e:
        logger.error(f"Clinical records search failed: {e}")
        return Response(
            {'error': 'Search failed', 'detail': str(e)},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['GET'])
@permission_classes([IsAuthenticated, TenantPermission])
def search_document_content(request):
    """
    Search within document content (OCR text and structured data).
    
    Query Parameters:
        q: Search query string
        record_type: Filter by record type
        processing_status: Filter by processing status
        content_type: Filter by content type
        page: Page number (default: 1)
        page_size: Results per page (default: 20, max: 100)
    """
    try:
        # Get search parameters
        query = request.GET.get('q', '').strip()
        clinic_id = str(request.user.current_tenant.id)
        
        if not query:
            return Response(
                {'error': 'Search query is required'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Build filters
        filters = {}
        
        if request.GET.get('record_type'):
            filters['record_type'] = request.GET.get('record_type')
        
        if request.GET.get('processing_status'):
            filters['processing_status'] = request.GET.get('processing_status')
        
        if request.GET.get('content_type'):
            filters['content_type'] = request.GET.get('content_type')
        
        # Pagination parameters
        try:
            page = int(request.GET.get('page', 1))
            page_size = min(int(request.GET.get('page_size', 20)), 100)
        except (ValueError, TypeError):
            page = 1
            page_size = 20
        
        # Perform search
        search_result = elasticsearch_service.search_documents_content(
            query=query,
            clinic_id=clinic_id,
            filters=filters,
            page=page,
            page_size=page_size
        )
        
        # Log search activity
        AuditLog.log_action(
            user=request.user,
            action='DOCUMENT_CONTENT_SEARCH',
            resource_type='SEARCH',
            resource_id=None,
            details=f"Content search query: '{query}', Results: {search_result.get('total', 0)}",
            tenant=request.user.current_tenant
        )
        
        return Response(search_result, status=status.HTTP_200_OK)
        
    except Exception as e:
        logger.error(f"Document content search failed: {e}")
        return Response(
            {'error': 'Content search failed', 'detail': str(e)},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['GET'])
@permission_classes([IsAuthenticated, TenantPermission])
def search_suggestions(request):
    """
    Get search suggestions based on indexed content.
    
    Query Parameters:
        q: Partial query string
        type: Suggestion type (medications, diagnoses, patients)
    """
    try:
        query = request.GET.get('q', '').strip()
        suggestion_type = request.GET.get('type', 'medications')
        clinic_id = str(request.user.current_tenant.id)
        
        if not query or len(query) < 2:
            return Response(
                {'suggestions': []},
                status=status.HTTP_200_OK
            )
        
        # Get suggestions
        suggestions = elasticsearch_service.get_search_suggestions(
            query=query,
            clinic_id=clinic_id,
            suggestion_type=suggestion_type
        )
        
        return Response(
            {'suggestions': suggestions},
            status=status.HTTP_200_OK
        )
        
    except Exception as e:
        logger.error(f"Search suggestions failed: {e}")
        return Response(
            {'error': 'Failed to get suggestions', 'detail': str(e)},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['GET'])
@permission_classes([IsAuthenticated, TenantPermission])
def search_analytics(request):
    """
    Get search analytics and statistics.
    
    Query Parameters:
        date_from: Analytics date range (from)
        date_to: Analytics date range (to)
    """
    try:
        clinic_id = str(request.user.current_tenant.id)
        
        # Build date range filter
        date_range = None
        if request.GET.get('date_from') or request.GET.get('date_to'):
            date_range = {}
            if request.GET.get('date_from'):
                date_range['from'] = request.GET.get('date_from')
            if request.GET.get('date_to'):
                date_range['to'] = request.GET.get('date_to')
        
        # Get analytics
        analytics = elasticsearch_service.get_search_analytics(
            clinic_id=clinic_id,
            date_range=date_range
        )
        
        # Log analytics access
        AuditLog.log_action(
            user=request.user,
            action='SEARCH_ANALYTICS_ACCESSED',
            resource_type='ANALYTICS',
            resource_id=None,
            details=f"Analytics accessed for date range: {date_range}",
            tenant=request.user.current_tenant
        )
        
        return Response(analytics, status=status.HTTP_200_OK)
        
    except Exception as e:
        logger.error(f"Search analytics failed: {e}")
        return Response(
            {'error': 'Analytics failed', 'detail': str(e)},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@method_decorator(csrf_exempt, name='dispatch')
class ElasticsearchHealthView(View):
    """
    Health check endpoint for Elasticsearch service.
    """
    
    def get(self, request):
        """Get Elasticsearch health status."""
        try:
            from ..signals.elasticsearch_signals import check_elasticsearch_health
            
            health_status = check_elasticsearch_health()
            
            if health_status['status'] == 'healthy':
                return JsonResponse(health_status, status=200)
            elif health_status['status'] == 'disabled':
                return JsonResponse(health_status, status=503)
            else:
                return JsonResponse(health_status, status=503)
                
        except Exception as e:
            logger.error(f"Elasticsearch health check failed: {e}")
            return JsonResponse(
                {'status': 'error', 'message': str(e)},
                status=500
            )


@api_view(['POST'])
@permission_classes([IsAuthenticated, TenantPermission])
def reindex_clinic_data(request):
    """
    Reindex all clinical data for the current clinic.
    Requires admin permissions.
    """
    try:
        # Check if user has admin permissions
        if not request.user.is_staff and not hasattr(request.user, 'is_clinic_admin'):
            return Response(
                {'error': 'Admin permissions required'},
                status=status.HTTP_403_FORBIDDEN
            )
        
        clinic_id = str(request.user.current_tenant.id)
        
        # Trigger reindexing
        from ..signals.elasticsearch_signals import bulk_sync_to_elasticsearch
        
        result = bulk_sync_to_elasticsearch(clinic_id=clinic_id, force_reindex=True)
        
        # Log reindexing activity
        AuditLog.log_action(
            user=request.user,
            action='ELASTICSEARCH_REINDEX',
            resource_type='SYSTEM',
            resource_id=None,
            details=f"Reindexing triggered for clinic {clinic_id}",
            tenant=request.user.current_tenant
        )
        
        if result['status'] == 'success':
            return Response(result, status=status.HTTP_200_OK)
        else:
            return Response(result, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
            
    except Exception as e:
        logger.error(f"Reindexing failed: {e}")
        return Response(
            {'error': 'Reindexing failed', 'detail': str(e)},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['GET'])
@permission_classes([IsAuthenticated, TenantPermission])
def advanced_search(request):
    """
    Advanced search with multiple criteria and faceted search.
    
    Query Parameters:
        q: Main search query
        medications: Medication names (comma-separated)
        diagnoses: Diagnoses (comma-separated)
        patient_name: Patient name
        date_from: Date range from
        date_to: Date range to
        record_types: Record types (comma-separated)
        confidence_min: Minimum OCR confidence
        has_attachments: Has document attachments
        page: Page number
        page_size: Results per page
        facets: Include faceted search results
    """
    try:
        clinic_id = str(request.user.current_tenant.id)
        
        # Build complex search query
        search_params = {
            'query': request.GET.get('q', '').strip(),
            'clinic_id': clinic_id,
            'filters': {},
            'page': int(request.GET.get('page', 1)),
            'page_size': min(int(request.GET.get('page_size', 20)), 100),
            'sort_by': request.GET.get('sort_by', '_score')
        }
        
        # Add advanced filters
        filters = search_params['filters']
        
        if request.GET.get('medications'):
            filters['medications'] = [m.strip() for m in request.GET.get('medications').split(',')]
        
        if request.GET.get('diagnoses'):
            filters['diagnoses'] = [d.strip() for d in request.GET.get('diagnoses').split(',')]
        
        if request.GET.get('patient_name'):
            filters['patient_name'] = request.GET.get('patient_name').strip()
        
        if request.GET.get('date_from') or request.GET.get('date_to'):
            date_range = {}
            if request.GET.get('date_from'):
                date_range['from'] = request.GET.get('date_from')
            if request.GET.get('date_to'):
                date_range['to'] = request.GET.get('date_to')
            filters['date_range'] = date_range
        
        if request.GET.get('record_types'):
            filters['record_types'] = [rt.strip() for rt in request.GET.get('record_types').split(',')]
        
        if request.GET.get('confidence_min'):
            try:
                filters['confidence_min'] = float(request.GET.get('confidence_min'))
            except ValueError:
                pass
        
        if request.GET.get('has_attachments') is not None:
            filters['has_attachments'] = request.GET.get('has_attachments').lower() == 'true'
        
        # Perform advanced search
        # Note: This would require extending the elasticsearch_service with advanced search capabilities
        search_result = elasticsearch_service.search_clinical_records(
            query=search_params['query'],
            clinic_id=clinic_id,
            filters=filters,
            page=search_params['page'],
            page_size=search_params['page_size'],
            sort_by=search_params['sort_by']
        )
        
        # Add faceted search results if requested
        if request.GET.get('facets', '').lower() == 'true':
            # Add facet information to the response
            search_result['facets'] = {
                'record_types': search_result.get('aggregations', {}).get('record_types', {}),
                'patient_genders': search_result.get('aggregations', {}).get('patient_genders', {}),
                'created_by_month': search_result.get('aggregations', {}).get('created_by_month', {})
            }
        
        # Log advanced search activity
        AuditLog.log_action(
            user=request.user,
            action='ADVANCED_SEARCH',
            resource_type='SEARCH',
            resource_id=None,
            details=f"Advanced search with {len(filters)} filters, Results: {search_result.get('total', 0)}",
            tenant=request.user.current_tenant
        )
        
        return Response(search_result, status=status.HTTP_200_OK)
        
    except Exception as e:
        logger.error(f"Advanced search failed: {e}")
        return Response(
            {'error': 'Advanced search failed', 'detail': str(e)},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )