"""
API Views for Clinical Records

This module contains REST API ViewSets for managing clinical records and documents.
All views implement proper tenant filtering and permissions.
"""
import logging
import os
import zipfile
import tempfile
from datetime import datetime, timedelta
from django.db.models import Q, Count, Prefetch
from django.utils import timezone
from django.http import Http404, HttpResponse, FileResponse
from django.core.exceptions import PermissionDenied
from django.conf import settings
from rest_framework import viewsets, status, permissions, filters
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.pagination import PageNumberPagination
from rest_framework.exceptions import ValidationError
from django_filters.rest_framework import DjangoFilterBackend

from ..models import ClinicalRecord, ClinicalDocument, ImagingStudy, RecordRelationship, ShareToken
from ..serializers import (
    ClinicalRecordSerializer, ClinicalDocumentSerializer, 
    ImagingStudySerializer, RecordRelationshipSerializer, ShareTokenSerializer
)
from ..permissions import ClinicalRecordPermission, DocumentPermission
from ..utils.file_utils import FileTypeDetector, FileValidator
from ..services.file_access_service import FileAccessService, BatchDownloadService
from ..services.simple_audit_service import audit_service
from ..decorators.audit_decorators import (
    audit_record_access, audit_document_access, audit_search, audit_export_action
)
# from users.models import AuditLog  # External dependency removed

logger = logging.getLogger(__name__)


class ClinicalRecordPagination(PageNumberPagination):
    """Custom pagination for clinical records"""
    page_size = 20
    page_size_query_param = 'page_size'
    max_page_size = 100


class ClinicalRecordViewSet(viewsets.ModelViewSet):
    """
    ViewSet for managing clinical records with tenant filtering.
    
    Provides CRUD operations for clinical records with proper tenant isolation,
    search capabilities, filtering, and nested document management.
    """
    serializer_class = ClinicalRecordSerializer
    permission_classes = [permissions.IsAuthenticated, ClinicalRecordPermission]
    pagination_class = ClinicalRecordPagination
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    
    # Filtering options
    filterset_fields = {
        'record_type': ['exact', 'in'],
        'status': ['exact', 'in'],
        'priority': ['exact', 'in'],
        'is_active': ['exact'],
        'is_confidential': ['exact'],
        'record_date': ['gte', 'lte', 'exact', 'year', 'month'],
        'created_at': ['gte', 'lte'],
        'patient': ['exact'],
        'created_by': ['exact'],
    }
    
    # Search fields
    search_fields = ['title', 'description', 'tags', 'patient__first_name', 'patient__last_name']
    
    # Ordering options
    ordering_fields = ['record_date', 'created_at', 'updated_at', 'title', 'priority']
    ordering = ['-record_date', '-created_at']
    
    def get_queryset(self):
        """Filter records by current user's clinic with optimized queries"""
        user = self.request.user
        if not hasattr(user, 'current_tenant') or not user.current_tenant:
            return ClinicalRecord.objects.none()
        
        # Base queryset with tenant filtering
        queryset = ClinicalRecord.objects.filter(
            clinic=user.current_tenant
        ).select_related(
            'patient',
            'clinic', 
            'created_by'
        ).prefetch_related(
            'tags'
        )
        
        # Add document count annotation
        queryset = queryset.annotate(
            document_count=Count('documents', distinct=True)
        )
        
        return queryset


class ClinicalDocumentViewSet(viewsets.ModelViewSet):
    """
    ViewSet for managing clinical documents with tenant filtering.
    
    Provides CRUD operations for clinical documents with proper tenant isolation,
    file handling, and access control.
    """
    serializer_class = ClinicalDocumentSerializer
    permission_classes = [permissions.IsAuthenticated, DocumentPermission]
    pagination_class = ClinicalRecordPagination
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    
    # Filtering options
    filterset_fields = {
        'document_type': ['exact', 'in'],
        'status': ['exact', 'in'],
        'is_active': ['exact'],
        'upload_date': ['gte', 'lte', 'exact'],
        'clinical_record': ['exact'],
        'uploaded_by': ['exact'],
    }
    
    # Search fields
    search_fields = ['title', 'description', 'filename', 'clinical_record__title']
    
    # Ordering options
    ordering_fields = ['upload_date', 'created_at', 'updated_at', 'title']
    ordering = ['-upload_date', '-created_at']
    
    def get_queryset(self):
        """Filter documents by current user's clinic with optimized queries"""
        user = self.request.user
        if not hasattr(user, 'current_tenant') or not user.current_tenant:
            return ClinicalDocument.objects.none()
        
        # Base queryset with tenant filtering
        queryset = ClinicalDocument.objects.filter(
            clinical_record__clinic=user.current_tenant
        ).select_related(
            'clinical_record',
            'uploaded_by'
        )
        
        return queryset


class ImagingStudyViewSet(viewsets.ModelViewSet):
    """
    ViewSet for managing imaging studies with tenant filtering.
    """
    serializer_class = ImagingStudySerializer
    permission_classes = [permissions.IsAuthenticated, ClinicalRecordPermission]
    pagination_class = ClinicalRecordPagination
    
    def get_queryset(self):
        """Filter imaging studies by current user's clinic"""
        user = self.request.user
        if not hasattr(user, 'current_tenant') or not user.current_tenant:
            return ImagingStudy.objects.none()
        
        return ImagingStudy.objects.filter(
            clinical_record__clinic=user.current_tenant
        ).select_related('clinical_record')


class RecordRelationshipViewSet(viewsets.ModelViewSet):
    """
    ViewSet for managing record relationships with tenant filtering.
    """
    serializer_class = RecordRelationshipSerializer
    permission_classes = [permissions.IsAuthenticated, ClinicalRecordPermission]
    pagination_class = ClinicalRecordPagination
    
    def get_queryset(self):
        """Filter relationships by current user's clinic"""
        user = self.request.user
        if not hasattr(user, 'current_tenant') or not user.current_tenant:
            return RecordRelationship.objects.none()
        
        return RecordRelationship.objects.filter(
            source_record__clinic=user.current_tenant
        ).select_related('source_record', 'target_record')


class ShareTokenViewSet(viewsets.ModelViewSet):
    """
    ViewSet for managing share tokens with tenant filtering.
    """
    serializer_class = ShareTokenSerializer
    permission_classes = [permissions.IsAuthenticated, ClinicalRecordPermission]
    pagination_class = ClinicalRecordPagination
    
    def get_queryset(self):
        """Filter share tokens by current user's clinic"""
        user = self.request.user
        if not hasattr(user, 'current_tenant') or not user.current_tenant:
            return ShareToken.objects.none()
        
        return ShareToken.objects.filter(
            clinical_record__clinic=user.current_tenant
        ).select_related('clinical_record', 'created_by')


class FHIRExportViewSet(viewsets.ViewSet):
    """
    ViewSet for FHIR export functionality.
    """
    permission_classes = [permissions.IsAuthenticated, ClinicalRecordPermission]
    
    @action(detail=False, methods=['post'])
    def validate_bundle(self, request):
        """Validate FHIR bundle"""
        try:
            from fhir.resources.bundle import Bundle
            
            # Try to parse as Bundle
            bundle_data = request.data
            bundle = Bundle(**bundle_data)
            
            # Validate bundle
            validation_result = {
                'is_valid': True,
                'errors': [],
                'warnings': [],
                'resource_count': len(bundle.entry) if bundle.entry else 0,
                'resource_types': {}
            }
            
            return Response(validation_result)
            
        except Exception as e:
            return Response({
                'is_valid': False,
                'errors': [f'Validation failed: {str(e)}'],
                'warnings': [],
                'resource_count': 0,
                'resource_types': {}
            })
