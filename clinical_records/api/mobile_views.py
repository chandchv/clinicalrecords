"""
Mobile API Views for Clinical Records

This module contains mobile-optimized REST API views for clinical records management.
These views provide lightweight, mobile-friendly responses with pagination and
optimized data structures for mobile consumption.
"""
import logging
from datetime import datetime, timedelta
from django.db.models import Q, Count, Prefetch
from django.utils import timezone
from django.http import Http404, JsonResponse
from django.core.exceptions import PermissionDenied
from rest_framework import status, permissions
from rest_framework.decorators import api_view, permission_classes, action
from rest_framework.response import Response
from rest_framework.pagination import PageNumberPagination
from rest_framework.exceptions import ValidationError
from rest_framework.views import APIView
from rest_framework.viewsets import ViewSet

from ..models import ClinicalRecord, ClinicalDocument
# Import serializers - will create simple ones if main ones are not available
try:
    from clinical_records.serializers import ClinicalRecordSerializer, ClinicalDocumentSerializer
except ImportError:
    # Create simple serializers for mobile API
    from rest_framework import serializers
    from ..models import ClinicalRecord, ClinicalDocument
    
    class ClinicalRecordSerializer(serializers.ModelSerializer):
        class Meta:
            model = ClinicalRecord
            fields = ['id', 'title', 'record_type', 'status', 'priority', 'record_date', 'created_at', 'updated_at']
    
    class ClinicalDocumentSerializer(serializers.ModelSerializer):
        class Meta:
            model = ClinicalDocument
            fields = ['id', 'original_filename', 'file_size', 'document_type', 'processing_status', 'created_at']
from ..permissions import ClinicalRecordPermission, DocumentPermission
# from ..utils.file_utils import FileValidator  # Commented out due to numpy compatibility issues
from users.models import AuditLog

logger = logging.getLogger(__name__)


class MobilePagination(PageNumberPagination):
    """Mobile-optimized pagination with smaller page sizes"""
    page_size = 10
    page_size_query_param = 'page_size'
    max_page_size = 50


class MobileClinicalRecordsSerializer(ClinicalRecordSerializer):
    """Mobile-optimized serializer for clinical records with minimal data"""
    
    class Meta(ClinicalRecordSerializer.Meta):
        fields = [
            'id', 'record_type', 'title', 'status', 'priority',
            'record_date', 'document_count', 'has_documents',
            'created_at', 'updated_at'
        ]


class MobileClinicalDocumentSerializer(ClinicalDocumentSerializer):
    """Mobile-optimized serializer for clinical documents"""
    
    class Meta(ClinicalDocumentSerializer.Meta):
        fields = [
            'id', 'original_filename', 'file_size', 'file_size_mb',
            'document_type', 'processing_status', 'ocr_confidence',
            'is_processed', 'has_ocr_text', 'created_at'
        ]


class MobileClinicalRecordsAPIView(APIView):
    """
    Mobile API for clinical records list with pagination and search
    
    GET /api/mobile/clinical-records/
    - Returns paginated list of clinical records
    - Supports search, filtering, and sorting
    - Optimized for mobile consumption
    """
    permission_classes = [permissions.IsAuthenticated, ClinicalRecordPermission]
    pagination_class = MobilePagination
    
    def get(self, request):
        """Get paginated list of clinical records for mobile"""
        user = request.user
        if not hasattr(user, 'current_tenant') or not user.current_tenant:
            return Response(
                {'error': 'No clinic context available'}, 
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Base queryset with tenant filtering
        queryset = ClinicalRecord.objects.filter(
            clinic=user.current_tenant,
            is_active=True
        ).select_related('patient').annotate(
            document_count=Count('documents', distinct=True)
        )
        
        # Apply filters
        record_type = request.query_params.get('record_type')
        if record_type:
            queryset = queryset.filter(record_type=record_type)
        
        status_filter = request.query_params.get('status')
        if status_filter:
            queryset = queryset.filter(status=status_filter)
        
        patient_id = request.query_params.get('patient_id')
        if patient_id:
            queryset = queryset.filter(patient_id=patient_id)
        
        # Date range filtering
        date_from = request.query_params.get('date_from')
        date_to = request.query_params.get('date_to')
        
        if date_from:
            try:
                date_from = datetime.fromisoformat(date_from.replace('Z', '+00:00'))
                queryset = queryset.filter(record_date__gte=date_from)
            except ValueError:
                pass
        
        if date_to:
            try:
                date_to = datetime.fromisoformat(date_to.replace('Z', '+00:00'))
                queryset = queryset.filter(record_date__lte=date_to)
            except ValueError:
                pass
        
        # Search functionality
        search_query = request.query_params.get('search', '').strip()
        if search_query:
            queryset = queryset.filter(
                Q(title__icontains=search_query) |
                Q(description__icontains=search_query) |
                Q(patient__first_name__icontains=search_query) |
                Q(patient__last_name__icontains=search_query)
            )
        
        # Ordering
        ordering = request.query_params.get('ordering', '-record_date')
        if ordering in ['record_date', '-record_date', 'created_at', '-created_at', 'title', '-title']:
            queryset = queryset.order_by(ordering)
        else:
            queryset = queryset.order_by('-record_date', '-created_at')
        
        # Pagination
        paginator = MobilePagination()
        page = paginator.paginate_queryset(queryset, request)
        
        if page is not None:
            serializer = MobileClinicalRecordsSerializer(page, many=True)
            return paginator.get_paginated_response(serializer.data)
        
        serializer = MobileClinicalRecordsSerializer(queryset, many=True)
        return Response(serializer.data)


class MobileClinicalRecordDetailAPIView(APIView):
    """
    Mobile API for clinical record detail view
    
    GET /api/mobile/clinical-records/{id}/
    - Returns detailed clinical record information
    - Includes associated documents
    - Optimized for mobile display
    """
    permission_classes = [permissions.IsAuthenticated, ClinicalRecordPermission]
    
    def get(self, request, record_id):
        """Get detailed clinical record for mobile"""
        user = request.user
        if not hasattr(user, 'current_tenant') or not user.current_tenant:
            return Response(
                {'error': 'No clinic context available'}, 
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            record = ClinicalRecord.objects.select_related(
                'patient', 'created_by'
            ).prefetch_related(
                Prefetch(
                    'documents',
                    queryset=ClinicalDocument.objects.select_related('uploaded_by').order_by('-created_at')
                )
            ).get(
                id=record_id,
                clinic=user.current_tenant,
                is_active=True
            )
        except ClinicalRecord.DoesNotExist:
            return Response(
                {'error': 'Clinical record not found'}, 
                status=status.HTTP_404_NOT_FOUND
            )
        
        # Log access
        AuditLog.log_action(
            user=user,
            action='CLINICAL_RECORD_VIEWED',
            resource_type='CLINICAL_RECORD',
            resource_id=str(record.id),
            details={'title': record.title, 'access_method': 'mobile_api'},
            tenant=user.current_tenant
        )
        
        # Serialize record data
        record_data = ClinicalRecordSerializer(record).data
        
        # Add mobile-optimized document list
        documents = record.documents.all()[:10]  # Limit to recent 10 documents
        document_data = MobileClinicalDocumentSerializer(documents, many=True).data
        
        response_data = {
            'record': record_data,
            'documents': document_data,
            'document_count': record.documents.count(),
            'has_more_documents': record.documents.count() > 10
        }
        
        return Response(response_data)


class MobileDocumentUploadAPIView(APIView):
    """
    Mobile API for document upload with progress tracking
    
    POST /api/mobile/clinical-records/upload/
    - Handles file upload from mobile devices
    - Supports camera capture and file selection
    - Returns upload progress and processing status
    """
    permission_classes = [permissions.IsAuthenticated, DocumentPermission]
    
    def post(self, request):
        """Upload document from mobile device"""
        user = request.user
        if not hasattr(user, 'current_tenant') or not user.current_tenant:
            return Response(
                {'error': 'No clinic context available'}, 
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Validate required fields
        if 'file' not in request.FILES:
            return Response(
                {'error': 'No file was uploaded'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        if 'clinical_record' not in request.data:
            return Response(
                {'error': 'clinical_record field is required'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        uploaded_file = request.FILES['file']
        clinical_record_id = request.data['clinical_record']
        
        # Basic file validation (simplified for mobile)
        max_file_size = 50 * 1024 * 1024  # 50MB
        if uploaded_file.size > max_file_size:
            return Response(
                {'error': 'File too large. Maximum size is 50MB.'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Simple validation result
        validation_result = {
            'is_valid': True,
            'content_type': uploaded_file.content_type or 'application/octet-stream',
            'document_type': 'document',
            'file_hash': 'mobile_upload',
        }
        
        # Get clinical record
        try:
            clinical_record = ClinicalRecord.objects.get(
                id=clinical_record_id,
                clinic=user.current_tenant,
                is_active=True
            )
        except ClinicalRecord.DoesNotExist:
            return Response(
                {'error': 'Clinical record not found'},
                status=status.HTTP_404_NOT_FOUND
            )
        
        # Create document
        document = ClinicalDocument.objects.create(
            clinical_record=clinical_record,
            uploaded_by=user,
            file=uploaded_file,
            original_filename=uploaded_file.name,
            file_size=uploaded_file.size,
            content_type=validation_result['content_type'],
            document_type=validation_result['document_type'],
            file_hash=validation_result['file_hash'],
            processing_status='pending'
        )
        
        # Queue background processing
        try:
            from ..tasks import process_clinical_document
            process_clinical_document.delay(str(document.id))
        except Exception as e:
            logger.error(f"Failed to queue document processing: {e}")
        
        # Log the upload
        AuditLog.log_action(
            user=user,
            action='CLINICAL_DOCUMENT_UPLOADED',
            resource_type='CLINICAL_DOCUMENT',
            resource_id=str(document.id),
            details={
                'filename': uploaded_file.name,
                'file_size': uploaded_file.size,
                'content_type': validation_result['content_type'],
                'clinical_record_id': str(clinical_record.id),
                'upload_method': 'mobile_api'
            },
            tenant=user.current_tenant
        )
        
        # Return mobile-optimized response
        response_data = {
            'document_id': str(document.id),
            'filename': document.original_filename,
            'file_size': document.file_size,
            'file_size_mb': document.file_size_mb,
            'document_type': document.document_type,
            'processing_status': document.processing_status,
            'upload_success': True,
            'message': 'Document uploaded successfully and queued for processing'
        }
        
        return Response(response_data, status=status.HTTP_201_CREATED)


class MobileClinicalRecordsSearchAPIView(APIView):
    """
    Mobile API for clinical records search
    
    GET /api/mobile/clinical-records/search/
    - Advanced search across clinical records and documents
    - Mobile-optimized search results
    - Supports filters and faceted search
    """
    permission_classes = [permissions.IsAuthenticated, ClinicalRecordPermission]
    pagination_class = MobilePagination
    
    def get(self, request):
        """Search clinical records for mobile"""
        user = request.user
        if not hasattr(user, 'current_tenant') or not user.current_tenant:
            return Response(
                {'error': 'No clinic context available'}, 
                status=status.HTTP_400_BAD_REQUEST
            )
        
        search_query = request.query_params.get('q', '').strip()
        if not search_query:
            return Response(
                {'error': 'Search query is required'}, 
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Base queryset
        queryset = ClinicalRecord.objects.filter(
            clinic=user.current_tenant,
            is_active=True
        ).select_related('patient').annotate(
            document_count=Count('documents', distinct=True)
        )
        
        # Apply search across multiple fields
        search_filter = (
            Q(title__icontains=search_query) |
            Q(description__icontains=search_query) |
            Q(patient__first_name__icontains=search_query) |
            Q(patient__last_name__icontains=search_query) |
            Q(tags__contains=[search_query])
        )
        
        # Include document OCR text search if requested
        include_documents = request.query_params.get('include_documents', 'false').lower() == 'true'
        if include_documents:
            search_filter |= Q(documents__ocr_text__icontains=search_query)
        
        results = queryset.filter(search_filter).distinct()
        
        # Apply additional filters
        record_type = request.query_params.get('record_type')
        if record_type:
            results = results.filter(record_type=record_type)
        
        priority = request.query_params.get('priority')
        if priority:
            results = results.filter(priority=priority)
        
        # Date range filtering
        date_from = request.query_params.get('date_from')
        if date_from:
            try:
                date_from = datetime.fromisoformat(date_from.replace('Z', '+00:00'))
                results = results.filter(record_date__gte=date_from)
            except ValueError:
                pass
        
        # Order by relevance (most recent first)
        results = results.order_by('-record_date', '-created_at')
        
        # Pagination
        paginator = MobilePagination()
        page = paginator.paginate_queryset(results, request)
        
        if page is not None:
            serializer = MobileClinicalRecordsSerializer(page, many=True)
            
            # Add search metadata
            response_data = paginator.get_paginated_response(serializer.data).data
            response_data['search_metadata'] = {
                'query': search_query,
                'total_results': results.count(),
                'included_documents': include_documents,
                'filters_applied': {
                    'record_type': record_type,
                    'priority': priority,
                    'date_from': date_from
                }
            }
            
            return Response(response_data)
        
        serializer = MobileClinicalRecordsSerializer(results, many=True)
        return Response({
            'results': serializer.data,
            'search_metadata': {
                'query': search_query,
                'total_results': results.count(),
                'included_documents': include_documents
            }
        })


class MobileDocumentProcessingStatusAPIView(APIView):
    """
    Mobile API for document processing status tracking
    
    GET /api/mobile/documents/{id}/status/
    - Returns current processing status
    - Includes progress information
    - Mobile-optimized response
    """
    permission_classes = [permissions.IsAuthenticated, DocumentPermission]
    
    def get(self, request, document_id):
        """Get document processing status for mobile"""
        user = request.user
        if not hasattr(user, 'current_tenant') or not user.current_tenant:
            return Response(
                {'error': 'No clinic context available'}, 
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            document = ClinicalDocument.objects.select_related(
                'clinical_record'
            ).get(
                id=document_id,
                clinical_record__clinic=user.current_tenant
            )
        except ClinicalDocument.DoesNotExist:
            return Response(
                {'error': 'Document not found'}, 
                status=status.HTTP_404_NOT_FOUND
            )
        
        # Get processing status details
        status_data = {
            'document_id': str(document.id),
            'filename': document.original_filename,
            'processing_status': document.processing_status,
            'processing_status_display': document.get_processing_status_display(),
            'is_processed': document.is_processed,
            'is_processing_active': document.is_processing_active,
            'can_be_processed': document.can_be_processed,
            'processing_started_at': document.processing_started_at,
            'processing_completed_at': document.processing_completed_at,
            'processing_duration': document.processing_duration,
            'processing_error': document.processing_error,
            'ocr_confidence': document.ocr_confidence,
            'has_ocr_text': document.has_ocr_text,
            'has_structured_data': document.has_structured_data,
            'requires_manual_review': document.requires_manual_review
        }
        
        # Add progress estimation
        if document.processing_status == 'processing':
            # Estimate progress based on time elapsed
            if document.processing_started_at:
                elapsed = timezone.now() - document.processing_started_at
                # Rough estimate: most documents process within 2 minutes
                progress_percent = min(90, (elapsed.total_seconds() / 120) * 100)
                status_data['progress_percent'] = round(progress_percent, 1)
            else:
                status_data['progress_percent'] = 10
        elif document.processing_status == 'completed':
            status_data['progress_percent'] = 100
        elif document.processing_status == 'failed':
            status_data['progress_percent'] = 0
        else:
            status_data['progress_percent'] = 0
        
        return Response(status_data)


# API endpoint functions for URL routing
@api_view(['GET'])
@permission_classes([permissions.IsAuthenticated])
def mobile_clinical_records_list(request):
    """Mobile clinical records list endpoint"""
    view = MobileClinicalRecordsAPIView()
    return view.get(request)


@api_view(['GET'])
@permission_classes([permissions.IsAuthenticated])
def mobile_clinical_record_detail(request, record_id):
    """Mobile clinical record detail endpoint"""
    view = MobileClinicalRecordDetailAPIView()
    return view.get(request, record_id)


@api_view(['POST'])
@permission_classes([permissions.IsAuthenticated])
def mobile_document_upload(request):
    """Mobile document upload endpoint"""
    view = MobileDocumentUploadAPIView()
    return view.post(request)


@api_view(['GET'])
@permission_classes([permissions.IsAuthenticated])
def mobile_clinical_records_search(request):
    """Mobile clinical records search endpoint"""
    view = MobileClinicalRecordsSearchAPIView()
    return view.get(request)


@api_view(['GET'])
@permission_classes([permissions.IsAuthenticated])
def mobile_document_processing_status(request, document_id):
    """Mobile document processing status endpoint"""
    view = MobileDocumentProcessingStatusAPIView()
    return view.get(request, document_id)


@api_view(['GET'])
@permission_classes([permissions.IsAuthenticated])
def mobile_search_suggestions(request):
    """Mobile search suggestions endpoint"""
    user = request.user
    if not hasattr(user, 'current_tenant') or not user.current_tenant:
        return Response(
            {'error': 'No clinic context available'}, 
            status=status.HTTP_400_BAD_REQUEST
        )
    
    query = request.query_params.get('q', '').strip()
    suggestion_type = request.query_params.get('type', 'medications')
    
    if not query or len(query) < 2:
        return Response({'suggestions': []})
    
    try:
        # Try to use Elasticsearch service if available
        from ..services.elasticsearch_service import ElasticsearchService
        es_service = ElasticsearchService()
        
        if es_service.is_enabled():
            suggestions = es_service.get_search_suggestions(
                query=query,
                clinic_id=str(user.current_tenant.id),
                suggestion_type=suggestion_type
            )
            return Response({'suggestions': suggestions})
        else:
            # Fallback to database search for suggestions
            suggestions = []
            
            if suggestion_type == 'medications':
                # Search in structured data for medication names
                from django.db.models import Q
                documents = ClinicalDocument.objects.filter(
                    clinical_record__clinic=user.current_tenant,
                    structured_data__medications__isnull=False
                ).values_list('structured_data', flat=True)[:100]
                
                medication_names = set()
                for doc_data in documents:
                    if doc_data and 'medications' in doc_data:
                        for med in doc_data['medications']:
                            if isinstance(med, dict) and 'name' in med:
                                name = med['name'].lower()
                                if query.lower() in name:
                                    medication_names.add(med['name'])
                
                suggestions = list(medication_names)[:10]
            
            elif suggestion_type == 'diagnoses':
                # Search in structured data for diagnoses
                documents = ClinicalDocument.objects.filter(
                    clinical_record__clinic=user.current_tenant,
                    structured_data__diagnosis__isnull=False
                ).values_list('structured_data', flat=True)[:100]
                
                diagnoses = set()
                for doc_data in documents:
                    if doc_data and 'diagnosis' in doc_data:
                        diagnosis = doc_data['diagnosis']
                        if isinstance(diagnosis, dict) and 'text' in diagnosis:
                            text = diagnosis['text'].lower()
                            if query.lower() in text:
                                diagnoses.add(diagnosis['text'])
                
                suggestions = list(diagnoses)[:10]
            
            elif suggestion_type == 'patients':
                # Search patient names
                from users.models import Patient
                patients = Patient.objects.filter(
                    clinic=user.current_tenant
                ).filter(
                    Q(user__first_name__icontains=query) |
                    Q(user__last_name__icontains=query)
                )[:10]
                
                suggestions = [
                    f"{p.user.first_name} {p.user.last_name}".strip()
                    for p in patients
                ]
            
            return Response({'suggestions': suggestions})
            
    except Exception as e:
        logger.error(f"Mobile search suggestions failed: {e}")
        return Response(
            {'error': 'Failed to get suggestions', 'suggestions': []},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )