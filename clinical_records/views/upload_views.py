"""
Views for document upload interface.

This module provides both API endpoints and web interface views
for document upload functionality with drag-and-drop support.
"""

import json
import logging
from typing import Dict, Any

from django.shortcuts import render, get_object_or_404
from django.http import JsonResponse, HttpResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from django.contrib.auth.decorators import login_required
from django.utils.decorators import method_decorator
from django.views import View
from django.core.files.uploadedfile import UploadedFile
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from users.models import Clinic, Patient
from ..models import ClinicalRecord, ClinicalDocument
from ..services.upload_service import upload_service
from ..permissions.rest_permissions import CanUploadDocuments
from ..decorators.audit_decorators import audit_api_call

logger = logging.getLogger(__name__)


@method_decorator(login_required, name='dispatch')
class DocumentUploadView(View):
    """Web interface view for document upload."""
    
    def get(self, request, record_id=None):
        """Render the document upload interface."""
        context = {
            'record_id': record_id,
            'max_file_size': upload_service.max_file_size,
            'allowed_extensions': upload_service.allowed_extensions,
            'config': {
                'chunk_size': 1024 * 1024,  # 1MB chunks
                'max_concurrent_uploads': 3,
                'auto_process': upload_service.config.get('AUTO_PROCESS', True)
            }
        }
        
        # If record_id is provided, get record details
        if record_id:
            try:
                record = get_object_or_404(ClinicalRecord, id=record_id)
                
                # Check if user has access to this record
                from ..services.access_control_service import access_control_service
                has_access, _ = access_control_service.check_record_access(
                    user=request.user,
                    record=record,
                    action='edit',
                    request=request
                )
                
                if not has_access:
                    context['error'] = 'You do not have permission to upload documents to this record.'
                else:
                    context['record'] = {
                        'id': str(record.id),
                        'title': record.title,
                        'patient_name': record.patient.get_full_name(),
                        'record_type': record.record_type,
                        'created_at': record.created_at.isoformat()
                    }
                    
            except Exception as e:
                logger.error(f"Error loading record {record_id}: {e}")
                context['error'] = 'Record not found or access denied.'
        
        return render(request, 'clinical_records/upload.html', context)


@api_view(['POST'])
@permission_classes([IsAuthenticated, CanUploadDocuments])
@audit_api_call
def upload_document_api(request):
    """
    API endpoint for single document upload.
    
    Expected form data:
    - file: The uploaded file
    - record_id: ID of the clinical record
    - metadata: Optional JSON metadata
    """
    try:
        # Get uploaded file
        if 'file' not in request.FILES:
            return Response(
                {'error': 'No file provided'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        uploaded_file = request.FILES['file']
        
        # Get clinical record
        record_id = request.data.get('record_id')
        if not record_id:
            return Response(
                {'error': 'record_id is required'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            clinical_record = ClinicalRecord.objects.get(id=record_id)
        except ClinicalRecord.DoesNotExist:
            return Response(
                {'error': 'Clinical record not found'},
                status=status.HTTP_404_NOT_FOUND
            )
        
        # Parse metadata if provided
        metadata = {}
        if 'metadata' in request.data:
            try:
                metadata = json.loads(request.data['metadata'])
            except json.JSONDecodeError:
                return Response(
                    {'error': 'Invalid metadata JSON'},
                    status=status.HTTP_400_BAD_REQUEST
                )
        
        # Process upload
        result = upload_service.process_upload(
            uploaded_file=uploaded_file,
            clinical_record=clinical_record,
            user=request.user,
            metadata=metadata
        )
        
        if result['status'] == 'uploaded':
            return Response(result, status=status.HTTP_201_CREATED)
        else:
            return Response(result, status=status.HTTP_400_BAD_REQUEST)
            
    except Exception as e:
        logger.error(f"Error in upload API: {e}", exc_info=True)
        return Response(
            {'error': 'Upload processing failed'},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['POST'])
@permission_classes([IsAuthenticated, CanUploadDocuments])
@audit_api_call
def batch_upload_api(request):
    """
    API endpoint for batch document upload.
    
    Expected form data:
    - files: Multiple uploaded files
    - record_id: ID of the clinical record
    - metadata: Optional JSON metadata
    """
    try:
        # Get uploaded files
        uploaded_files = request.FILES.getlist('files')
        if not uploaded_files:
            return Response(
                {'error': 'No files provided'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Get clinical record
        record_id = request.data.get('record_id')
        if not record_id:
            return Response(
                {'error': 'record_id is required'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            clinical_record = ClinicalRecord.objects.get(id=record_id)
        except ClinicalRecord.DoesNotExist:
            return Response(
                {'error': 'Clinical record not found'},
                status=status.HTTP_404_NOT_FOUND
            )
        
        # Parse metadata if provided
        metadata = {}
        if 'metadata' in request.data:
            try:
                metadata = json.loads(request.data['metadata'])
            except json.JSONDecodeError:
                return Response(
                    {'error': 'Invalid metadata JSON'},
                    status=status.HTTP_400_BAD_REQUEST
                )
        
        # Process batch upload
        result = upload_service.process_batch_upload(
            uploaded_files=uploaded_files,
            clinical_record=clinical_record,
            user=request.user,
            metadata=metadata
        )
        
        return Response(result, status=status.HTTP_201_CREATED)
        
    except Exception as e:
        logger.error(f"Error in batch upload API: {e}", exc_info=True)
        return Response(
            {'error': 'Batch upload processing failed'},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def upload_progress_api(request, document_id):
    """
    API endpoint to get upload and processing progress.
    
    Args:
        document_id: ID of the document to check
    """
    try:
        progress = upload_service.get_upload_progress(document_id)
        
        if 'error' in progress:
            return Response(progress, status=status.HTTP_404_NOT_FOUND)
        
        return Response(progress, status=status.HTTP_200_OK)
        
    except Exception as e:
        logger.error(f"Error getting upload progress: {e}")
        return Response(
            {'error': 'Failed to get progress'},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def upload_queue_status_api(request):
    """
    API endpoint to get upload queue status for the user.
    """
    try:
        clinic_id = request.query_params.get('clinic_id')
        clinic = None
        
        if clinic_id:
            try:
                clinic = Clinic.objects.get(id=clinic_id)
            except Clinic.DoesNotExist:
                return Response(
                    {'error': 'Clinic not found'},
                    status=status.HTTP_404_NOT_FOUND
                )
        
        queue_status = upload_service.get_upload_queue_status(
            user=request.user,
            clinic=clinic
        )
        
        if 'error' in queue_status:
            return Response(queue_status, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        
        return Response(queue_status, status=status.HTTP_200_OK)
        
    except Exception as e:
        logger.error(f"Error getting queue status: {e}")
        return Response(
            {'error': 'Failed to get queue status'},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['DELETE'])
@permission_classes([IsAuthenticated])
@audit_api_call
def cancel_upload_api(request, document_id):
    """
    API endpoint to cancel an upload.
    
    Args:
        document_id: ID of the document to cancel
    """
    try:
        result = upload_service.cancel_upload(document_id, request.user)
        
        if result['status'] == 'cancelled':
            return Response(result, status=status.HTTP_200_OK)
        else:
            return Response(result, status=status.HTTP_400_BAD_REQUEST)
            
    except Exception as e:
        logger.error(f"Error cancelling upload: {e}")
        return Response(
            {'error': 'Failed to cancel upload'},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def validate_file_api(request):
    """
    API endpoint to validate a file before upload.
    
    Expected form data:
    - file: The file to validate (or file info)
    - filename: Filename if file not provided
    - size: File size if file not provided
    """
    try:
        if 'file' in request.FILES:
            # Validate actual file
            uploaded_file = request.FILES['file']
            is_valid, message = upload_service.validate_upload(uploaded_file, request.user)
        else:
            # Validate file info only
            filename = request.data.get('filename')
            file_size = request.data.get('size')
            
            if not filename or not file_size:
                return Response(
                    {'error': 'filename and size are required'},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            # Create mock uploaded file for validation
            class MockUploadedFile:
                def __init__(self, name, size):
                    self.name = name
                    self.size = int(size)
                    self.content_type = None
            
            mock_file = MockUploadedFile(filename, file_size)
            is_valid, message = upload_service.validate_upload(mock_file, request.user)
        
        return Response({
            'valid': is_valid,
            'message': message,
            'max_file_size': upload_service.max_file_size,
            'allowed_extensions': upload_service.allowed_extensions
        }, status=status.HTTP_200_OK)
        
    except Exception as e:
        logger.error(f"Error validating file: {e}")
        return Response(
            {'error': 'File validation failed'},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@login_required
@require_http_methods(["GET"])
def upload_config_api(request):
    """
    API endpoint to get upload configuration.
    """
    try:
        config = {
            'max_file_size': upload_service.max_file_size,
            'allowed_extensions': upload_service.allowed_extensions,
            'allowed_mime_types': upload_service.allowed_mime_types,
            'auto_process': upload_service.config.get('AUTO_PROCESS', True),
            'chunk_size': 1024 * 1024,  # 1MB chunks for large file uploads
            'max_concurrent_uploads': 3,
            'processing_timeout': upload_service.config.get('PROCESSING_TIMEOUT', 300)
        }
        
        return JsonResponse(config)
        
    except Exception as e:
        logger.error(f"Error getting upload config: {e}")
        return JsonResponse(
            {'error': 'Failed to get configuration'},
            status=500
        )


@method_decorator(login_required, name='dispatch')
class MobileUploadView(View):
    """Mobile-optimized upload interface with camera integration."""
    
    def get(self, request, record_id=None):
        """Render mobile upload interface."""
        context = {
            'record_id': record_id,
            'mobile_optimized': True,
            'camera_enabled': True,
            'max_file_size': upload_service.max_file_size,
            'allowed_extensions': upload_service.allowed_extensions
        }
        
        # Add record details if provided
        if record_id:
            try:
                record = get_object_or_404(ClinicalRecord, id=record_id)
                
                # Check access
                from ..services.access_control_service import access_control_service
                has_access, _ = access_control_service.check_record_access(
                    user=request.user,
                    record=record,
                    action='edit',
                    request=request
                )
                
                if has_access:
                    context['record'] = {
                        'id': str(record.id),
                        'title': record.title,
                        'patient_name': record.patient.get_full_name(),
                        'record_type': record.record_type
                    }
                else:
                    context['error'] = 'Access denied to this record.'
                    
            except Exception as e:
                logger.error(f"Error loading record for mobile upload: {e}")
                context['error'] = 'Record not found.'
        
        return render(request, 'clinical_records/mobile_upload.html', context)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
@audit_api_call
def camera_capture_api(request):
    """
    API endpoint for camera capture uploads.
    
    Expected form data:
    - image: Base64 encoded image data or file
    - record_id: ID of the clinical record
    - capture_metadata: JSON metadata about the capture
    """
    try:
        record_id = request.data.get('record_id')
        if not record_id:
            return Response(
                {'error': 'record_id is required'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            clinical_record = ClinicalRecord.objects.get(id=record_id)
        except ClinicalRecord.DoesNotExist:
            return Response(
                {'error': 'Clinical record not found'},
                status=status.HTTP_404_NOT_FOUND
            )
        
        # Handle image data
        if 'image' in request.FILES:
            # File upload
            uploaded_file = request.FILES['image']
        elif 'image_data' in request.data:
            # Base64 encoded image
            import base64
            from django.core.files.base import ContentFile
            
            image_data = request.data['image_data']
            if image_data.startswith('data:image'):
                # Remove data URL prefix
                format_part, imgstr = image_data.split(';base64,')
                ext = format_part.split('/')[-1]
                
                # Decode base64
                img_data = base64.b64decode(imgstr)
                
                # Create uploaded file
                filename = f"camera_capture_{timezone.now().strftime('%Y%m%d_%H%M%S')}.{ext}"
                uploaded_file = ContentFile(img_data, name=filename)
                uploaded_file.content_type = f"image/{ext}"
            else:
                return Response(
                    {'error': 'Invalid image data format'},
                    status=status.HTTP_400_BAD_REQUEST
                )
        else:
            return Response(
                {'error': 'No image provided'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Parse capture metadata
        capture_metadata = {}
        if 'capture_metadata' in request.data:
            try:
                capture_metadata = json.loads(request.data['capture_metadata'])
            except json.JSONDecodeError:
                pass
        
        # Add camera capture flag to metadata
        metadata = {
            'source': 'camera_capture',
            'capture_timestamp': timezone.now().isoformat(),
            **capture_metadata
        }
        
        # Process upload
        result = upload_service.process_upload(
            uploaded_file=uploaded_file,
            clinical_record=clinical_record,
            user=request.user,
            metadata=metadata
        )
        
        if result['status'] == 'uploaded':
            return Response(result, status=status.HTTP_201_CREATED)
        else:
            return Response(result, status=status.HTTP_400_BAD_REQUEST)
            
    except Exception as e:
        logger.error(f"Error in camera capture API: {e}", exc_info=True)
        return Response(
            {'error': 'Camera capture processing failed'},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )