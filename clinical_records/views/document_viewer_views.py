"""
Views for document viewer interface.

This module provides both web interface views and API endpoints
for document viewing with metadata panel and annotation support.
"""

import json
import logging
from typing import Dict, Any

from django.shortcuts import render, get_object_or_404
from django.http import JsonResponse, HttpResponse, Http404
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from django.contrib.auth.decorators import login_required
from django.utils.decorators import method_decorator
from django.views import View
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from users.models import Clinic, Patient
from ..models import ClinicalRecord, ClinicalDocument
from ..services.document_viewer_service import document_viewer_service
from ..permissions.rest_permissions import CanViewRecords
from ..decorators.audit_decorators import audit_api_call

logger = logging.getLogger(__name__)


@method_decorator(login_required, name='dispatch')
class DocumentViewerView(View):
    """Web interface view for document viewer."""
    
    def get(self, request, document_id):
        """Render the document viewer interface."""
        try:
            document = get_object_or_404(ClinicalDocument, id=document_id)
            
            # Get viewer data
            viewer_data = document_viewer_service.get_document_viewer_data(
                document=document,
                user=request.user,
                request=request
            )
            
            if not viewer_data.get('has_access'):
                context = {
                    'error': viewer_data.get('error', 'Access denied'),
                    'document_id': document_id
                }
                return render(request, 'clinical_records/viewer_error.html', context)
            
            context = {
                'document': document,
                'viewer_data': json.dumps(viewer_data),
                'viewer_config': viewer_data['viewer_config'],
                'metadata': viewer_data['metadata'],
                'has_ocr': bool(viewer_data.get('ocr_data')),
                'supports_annotations': viewer_data['viewer_config'].get('supports_annotations', False),
                'supports_search': viewer_data['viewer_config'].get('search_enabled', False)
            }
            
            return render(request, 'clinical_records/document_viewer.html', context)
            
        except Exception as e:
            logger.error(f"Error in document viewer: {e}", exc_info=True)
            context = {
                'error': 'Failed to load document viewer',
                'document_id': document_id
            }
            return render(request, 'clinical_records/viewer_error.html', context)


@api_view(['GET'])
@permission_classes([IsAuthenticated, CanViewRecords])
@audit_api_call
def document_viewer_data_api(request, document_id):
    """
    API endpoint to get document viewer data.
    
    Args:
        document_id: ID of the document to view
    """
    try:
        document = get_object_or_404(ClinicalDocument, id=document_id)
        
        viewer_data = document_viewer_service.get_document_viewer_data(
            document=document,
            user=request.user,
            request=request
        )
        
        if not viewer_data.get('has_access'):
            return Response(
                {'error': viewer_data.get('error', 'Access denied')},
                status=status.HTTP_403_FORBIDDEN
            )
        
        return Response(viewer_data, status=status.HTTP_200_OK)
        
    except ClinicalDocument.DoesNotExist:
        return Response(
            {'error': 'Document not found'},
            status=status.HTTP_404_NOT_FOUND
        )
    except Exception as e:
        logger.error(f"Error getting viewer data: {e}")
        return Response(
            {'error': 'Failed to load document data'},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['GET'])
@permission_classes([IsAuthenticated, CanViewRecords])
def document_metadata_api(request, document_id):
    """
    API endpoint to get document metadata only.
    
    Args:
        document_id: ID of the document
    """
    try:
        document = get_object_or_404(ClinicalDocument, id=document_id)
        
        viewer_data = document_viewer_service.get_document_viewer_data(
            document=document,
            user=request.user,
            request=request
        )
        
        if not viewer_data.get('has_access'):
            return Response(
                {'error': viewer_data.get('error', 'Access denied')},
                status=status.HTTP_403_FORBIDDEN
            )
        
        # Return only metadata
        metadata_response = {
            'document_id': document_id,
            'metadata': viewer_data['metadata'],
            'processing_info': viewer_data['metadata']['processing_info'],
            'has_ocr': bool(viewer_data.get('ocr_data')),
            'has_structured_data': bool(viewer_data['metadata'].get('structured_data')),
            'has_dicom_data': bool(viewer_data['metadata'].get('dicom_info'))
        }
        
        return Response(metadata_response, status=status.HTTP_200_OK)
        
    except ClinicalDocument.DoesNotExist:
        return Response(
            {'error': 'Document not found'},
            status=status.HTTP_404_NOT_FOUND
        )
    except Exception as e:
        logger.error(f"Error getting metadata: {e}")
        return Response(
            {'error': 'Failed to load metadata'},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['GET'])
@permission_classes([IsAuthenticated, CanViewRecords])
def document_ocr_data_api(request, document_id):
    """
    API endpoint to get document OCR data.
    
    Args:
        document_id: ID of the document
    """
    try:
        document = get_object_or_404(ClinicalDocument, id=document_id)
        
        viewer_data = document_viewer_service.get_document_viewer_data(
            document=document,
            user=request.user,
            request=request
        )
        
        if not viewer_data.get('has_access'):
            return Response(
                {'error': viewer_data.get('error', 'Access denied')},
                status=status.HTTP_403_FORBIDDEN
            )
        
        ocr_data = viewer_data.get('ocr_data')
        if not ocr_data:
            return Response(
                {'error': 'No OCR data available for this document'},
                status=status.HTTP_404_NOT_FOUND
            )
        
        return Response(ocr_data, status=status.HTTP_200_OK)
        
    except ClinicalDocument.DoesNotExist:
        return Response(
            {'error': 'Document not found'},
            status=status.HTTP_404_NOT_FOUND
        )
    except Exception as e:
        logger.error(f"Error getting OCR data: {e}")
        return Response(
            {'error': 'Failed to load OCR data'},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['GET'])
@permission_classes([IsAuthenticated, CanViewRecords])
def document_search_api(request, document_id):
    """
    API endpoint to search within document text.
    
    Args:
        document_id: ID of the document to search
    """
    try:
        document = get_object_or_404(ClinicalDocument, id=document_id)
        search_query = request.query_params.get('q', '').strip()
        
        if not search_query:
            return Response(
                {'error': 'Search query is required'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Check access
        viewer_data = document_viewer_service.get_document_viewer_data(
            document=document,
            user=request.user,
            request=request
        )
        
        if not viewer_data.get('has_access'):
            return Response(
                {'error': viewer_data.get('error', 'Access denied')},
                status=status.HTTP_403_FORBIDDEN
            )
        
        # Perform search
        search_results = document_viewer_service.get_document_search_results(
            document=document,
            search_query=search_query
        )
        
        return Response({
            'query': search_query,
            'results': search_results,
            'total_matches': len(search_results)
        }, status=status.HTTP_200_OK)
        
    except ClinicalDocument.DoesNotExist:
        return Response(
            {'error': 'Document not found'},
            status=status.HTTP_404_NOT_FOUND
        )
    except Exception as e:
        logger.error(f"Error searching document: {e}")
        return Response(
            {'error': 'Search failed'},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['POST'])
@permission_classes([IsAuthenticated])
@audit_api_call
def document_annotation_api(request, document_id):
    """
    API endpoint to save document annotations.
    
    Args:
        document_id: ID of the document to annotate
    """
    try:
        document = get_object_or_404(ClinicalDocument, id=document_id)
        
        # Check access
        viewer_data = document_viewer_service.get_document_viewer_data(
            document=document,
            user=request.user,
            request=request
        )
        
        if not viewer_data.get('has_access'):
            return Response(
                {'error': viewer_data.get('error', 'Access denied')},
                status=status.HTTP_403_FORBIDDEN
            )
        
        if not viewer_data['viewer_config'].get('supports_annotations'):
            return Response(
                {'error': 'Annotations not supported for this document type'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        annotation_data = request.data
        
        # Validate annotation data
        required_fields = ['type', 'content', 'position']
        for field in required_fields:
            if field not in annotation_data:
                return Response(
                    {'error': f'Missing required field: {field}'},
                    status=status.HTTP_400_BAD_REQUEST
                )
        
        # Save annotation
        result = document_viewer_service.save_annotation(
            document=document,
            user=request.user,
            annotation_data=annotation_data
        )
        
        if result.get('success'):
            return Response(result, status=status.HTTP_201_CREATED)
        else:
            return Response(result, status=status.HTTP_400_BAD_REQUEST)
        
    except ClinicalDocument.DoesNotExist:
        return Response(
            {'error': 'Document not found'},
            status=status.HTTP_404_NOT_FOUND
        )
    except Exception as e:
        logger.error(f"Error saving annotation: {e}")
        return Response(
            {'error': 'Failed to save annotation'},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['GET'])
@permission_classes([IsAuthenticated, CanViewRecords])
def document_thumbnail_api(request, document_id):
    """
    API endpoint to get document thumbnail.
    
    Args:
        document_id: ID of the document
    """
    try:
        document = get_object_or_404(ClinicalDocument, id=document_id)
        
        # Check access
        viewer_data = document_viewer_service.get_document_viewer_data(
            document=document,
            user=request.user,
            request=request
        )
        
        if not viewer_data.get('has_access'):
            return Response(
                {'error': viewer_data.get('error', 'Access denied')},
                status=status.HTTP_403_FORBIDDEN
            )
        
        # For now, return placeholder response
        # This would integrate with thumbnail generation service
        return Response({
            'thumbnail_url': viewer_data.get('thumbnail_url'),
            'available': bool(viewer_data.get('thumbnail_url'))
        }, status=status.HTTP_200_OK)
        
    except ClinicalDocument.DoesNotExist:
        return Response(
            {'error': 'Document not found'},
            status=status.HTTP_404_NOT_FOUND
        )
    except Exception as e:
        logger.error(f"Error getting thumbnail: {e}")
        return Response(
            {'error': 'Failed to get thumbnail'},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@login_required
@require_http_methods(["GET"])
def document_viewer_config_api(request):
    """
    API endpoint to get document viewer configuration.
    """
    try:
        config = {
            'supported_formats': document_viewer_service.supported_formats,
            'default_zoom_levels': [25, 50, 75, 100, 125, 150, 200, 300, 400],
            'annotation_types': [
                {'type': 'highlight', 'name': 'Highlight', 'color': '#ffff00'},
                {'type': 'note', 'name': 'Note', 'color': '#ff6b6b'},
                {'type': 'arrow', 'name': 'Arrow', 'color': '#4ecdc4'},
                {'type': 'rectangle', 'name': 'Rectangle', 'color': '#45b7d1'}
            ],
            'keyboard_shortcuts': {
                'zoom_in': 'Ctrl++',
                'zoom_out': 'Ctrl+-',
                'fit_width': 'Ctrl+0',
                'fit_page': 'Ctrl+1',
                'rotate_left': 'Ctrl+L',
                'rotate_right': 'Ctrl+R',
                'toggle_sidebar': 'Ctrl+S',
                'search': 'Ctrl+F',
                'fullscreen': 'F11'
            },
            'max_zoom': 500,
            'min_zoom': 10,
            'zoom_step': 25
        }
        
        return JsonResponse(config)
        
    except Exception as e:
        logger.error(f"Error getting viewer config: {e}")
        return JsonResponse(
            {'error': 'Failed to get configuration'},
            status=500
        )


@method_decorator(login_required, name='dispatch')
class EmbeddedDocumentViewerView(View):
    """Embedded document viewer for use in other interfaces."""
    
    def get(self, request, document_id):
        """Render embedded document viewer."""
        try:
            document = get_object_or_404(ClinicalDocument, id=document_id)
            
            # Get viewer data
            viewer_data = document_viewer_service.get_document_viewer_data(
                document=document,
                user=request.user,
                request=request
            )
            
            if not viewer_data.get('has_access'):
                context = {
                    'error': viewer_data.get('error', 'Access denied'),
                    'document_id': document_id
                }
                return render(request, 'clinical_records/embedded_viewer_error.html', context)
            
            context = {
                'document': document,
                'viewer_data': json.dumps(viewer_data),
                'viewer_config': viewer_data['viewer_config'],
                'embedded': True,
                'show_toolbar': request.GET.get('toolbar', 'true').lower() == 'true',
                'show_sidebar': request.GET.get('sidebar', 'true').lower() == 'true',
                'initial_zoom': request.GET.get('zoom', 'fit_width')
            }
            
            return render(request, 'clinical_records/embedded_document_viewer.html', context)
            
        except Exception as e:
            logger.error(f"Error in embedded viewer: {e}", exc_info=True)
            context = {
                'error': 'Failed to load document',
                'document_id': document_id
            }
            return render(request, 'clinical_records/embedded_viewer_error.html', context)


@method_decorator(login_required, name='dispatch')
class MobileDocumentViewerView(View):
    """Mobile-optimized document viewer."""
    
    def get(self, request, document_id):
        """Render mobile document viewer."""
        try:
            document = get_object_or_404(ClinicalDocument, id=document_id)
            
            # Get viewer data
            viewer_data = document_viewer_service.get_document_viewer_data(
                document=document,
                user=request.user,
                request=request
            )
            
            if not viewer_data.get('has_access'):
                context = {
                    'error': viewer_data.get('error', 'Access denied'),
                    'document_id': document_id
                }
                return render(request, 'clinical_records/mobile_viewer_error.html', context)
            
            context = {
                'document': document,
                'viewer_data': json.dumps(viewer_data),
                'viewer_config': viewer_data['viewer_config'],
                'metadata': viewer_data['metadata'],
                'mobile_optimized': True,
                'has_ocr': bool(viewer_data.get('ocr_data')),
                'supports_search': viewer_data['viewer_config'].get('search_enabled', False)
            }
            
            return render(request, 'clinical_records/mobile_document_viewer.html', context)
            
        except Exception as e:
            logger.error(f"Error in mobile viewer: {e}", exc_info=True)
            context = {
                'error': 'Failed to load document',
                'document_id': document_id
            }
            return render(request, 'clinical_records/mobile_viewer_error.html', context)