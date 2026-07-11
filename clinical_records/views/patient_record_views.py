"""
Patient Record Views for Clinical Records Service

This module contains views for managing patient clinical records with proper
authentication, tenant filtering, and patient verification.
"""

import logging
from django.shortcuts import get_object_or_404
from django.http import JsonResponse
from django.core.exceptions import PermissionDenied
from rest_framework import status, permissions
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
from rest_framework.pagination import PageNumberPagination
from django.core.paginator import Paginator
from django.db.models import Q

from ..models import Patient, ClinicalRecord, ClinicalDocument
from ..serializers import (
    PatientSerializer, ClinicalRecordSerializer, ClinicalDocumentSerializer
)
from ..services.patient_sync_service import get_patient_sync_service
from ..permissions import ClinicalRecordPermission

logger = logging.getLogger(__name__)


class PatientRecordPagination(PageNumberPagination):
    """Custom pagination for patient records"""
    page_size = 20
    page_size_query_param = 'page_size'
    max_page_size = 100


@api_view(['GET'])
@permission_classes([permissions.IsAuthenticated, ClinicalRecordPermission])
def patient_records_list(request, patient_id):
    """
    List clinical records for a specific patient
    
    Args:
        request: HTTP request
        patient_id: Patient ID from RxBackend
        
    Returns:
        JSON response with patient records
    """
    try:
        # Get or sync patient
        patient_sync_service = get_patient_sync_service()
        patient = patient_sync_service.ensure_patient_exists(
            patient_id, 
            token=getattr(request, 'jwt_token', None)
        )
        
        if not patient:
            return Response({
                'error': 'Patient not found or could not be synced'
            }, status=status.HTTP_404_NOT_FOUND)
        
        # Get records for this patient
        records = ClinicalRecord.objects.filter(
            patient=patient,
            is_active=True
        ).order_by('-record_date', '-created_at')
        
        # Apply search filter
        search_query = request.GET.get('search', '')
        if search_query:
            records = records.filter(
                Q(title__icontains=search_query) |
                Q(description__icontains=search_query) |
                Q(record_type__icontains=search_query)
            )
        
        # Apply filters
        record_type = request.GET.get('record_type', '')
        if record_type:
            records = records.filter(record_type=record_type)
        
        status_filter = request.GET.get('status', '')
        if status_filter:
            records = records.filter(status=status_filter)
        
        # Pagination
        paginator = PatientRecordPagination()
        page = paginator.paginate_queryset(records, request)
        
        if page is not None:
            serializer = ClinicalRecordSerializer(page, many=True)
            return paginator.get_paginated_response(serializer.data)
        
        # If no pagination
        serializer = ClinicalRecordSerializer(records, many=True)
        return Response({
            'results': serializer.data,
            'count': records.count(),
            'patient': PatientSerializer(patient).data
        })
        
    except Exception as e:
        logger.error(f"Error listing patient records: {e}")
        return Response({
            'error': 'Failed to retrieve patient records'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['GET'])
@permission_classes([permissions.IsAuthenticated, ClinicalRecordPermission])
def patient_record_detail(request, patient_id, record_id):
    """
    Get detailed information about a specific patient record
    
    Args:
        request: HTTP request
        patient_id: Patient ID from RxBackend
        record_id: Clinical record UUID
        
    Returns:
        JSON response with record details
    """
    try:
        # Get or sync patient
        patient_sync_service = get_patient_sync_service()
        patient = patient_sync_service.ensure_patient_exists(
            patient_id, 
            token=getattr(request, 'jwt_token', None)
        )
        
        if not patient:
            return Response({
                'error': 'Patient not found or could not be synced'
            }, status=status.HTTP_404_NOT_FOUND)
        
        # Get the specific record
        record = get_object_or_404(
            ClinicalRecord,
            id=record_id,
            patient=patient,
            is_active=True
        )
        
        # Get related documents
        documents = ClinicalDocument.objects.filter(
            clinical_record=record
        ).order_by('-created_at')
        
        # Serialize data
        record_serializer = ClinicalRecordSerializer(record)
        documents_serializer = ClinicalDocumentSerializer(documents, many=True)
        
        return Response({
            'record': record_serializer.data,
            'documents': documents_serializer.data,
            'patient': PatientSerializer(patient).data
        })
        
    except Exception as e:
        logger.error(f"Error getting patient record detail: {e}")
        return Response({
            'error': 'Failed to retrieve record details'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['POST'])
@permission_classes([permissions.IsAuthenticated, ClinicalRecordPermission])
def patient_record_create(request, patient_id):
    """
    Create a new clinical record for a patient
    
    Args:
        request: HTTP request
        patient_id: Patient ID from RxBackend
        
    Returns:
        JSON response with created record
    """
    try:
        # Get or sync patient
        patient_sync_service = get_patient_sync_service()
        patient = patient_sync_service.ensure_patient_exists(
            patient_id, 
            token=getattr(request, 'jwt_token', None)
        )
        
        if not patient:
            return Response({
                'error': 'Patient not found or could not be synced'
            }, status=status.HTTP_404_NOT_FOUND)
        
        # Create record
        record_data = request.data.copy()
        record_data['patient'] = patient.id
        record_data['created_by'] = request.user.id
        
        serializer = ClinicalRecordSerializer(data=record_data)
        if serializer.is_valid():
            record = serializer.save()
            logger.info(f"Created clinical record {record.id} for patient {patient.get_full_name()}")
            
            return Response({
                'record': ClinicalRecordSerializer(record).data,
                'patient': PatientSerializer(patient).data
            }, status=status.HTTP_201_CREATED)
        else:
            return Response({
                'error': 'Invalid record data',
                'details': serializer.errors
            }, status=status.HTTP_400_BAD_REQUEST)
        
    except Exception as e:
        logger.error(f"Error creating patient record: {e}")
        return Response({
            'error': 'Failed to create record'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['GET'])
@permission_classes([permissions.IsAuthenticated, ClinicalRecordPermission])
def current_patient_records(request):
    """
    Get clinical records for the current authenticated patient
    
    Args:
        request: HTTP request
        
    Returns:
        JSON response with current patient's records
    """
    try:
        # Extract patient ID from JWT claims
        if not hasattr(request, 'jwt_claims'):
            return Response({
                'error': 'No patient information in token'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # Get patient ID from JWT claims (assuming it's in the token)
        patient_id = request.jwt_claims.get('patient_id')
        if not patient_id:
            return Response({
                'error': 'No patient ID in authentication token'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # Use the same logic as patient_records_list
        return patient_records_list(request, patient_id)
        
    except Exception as e:
        logger.error(f"Error getting current patient records: {e}")
        return Response({
            'error': 'Failed to retrieve current patient records'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['POST'])
@permission_classes([permissions.IsAuthenticated, ClinicalRecordPermission])
def patient_document_upload(request, patient_id):
    """
    Upload a document for a patient's clinical record
    
    Args:
        request: HTTP request
        patient_id: Patient ID from RxBackend
        
    Returns:
        JSON response with upload result
    """
    try:
        # Get or sync patient
        patient_sync_service = get_patient_sync_service()
        patient = patient_sync_service.ensure_patient_exists(
            patient_id, 
            token=getattr(request, 'jwt_token', None)
        )
        
        if not patient:
            return Response({
                'error': 'Patient not found or could not be synced'
            }, status=status.HTTP_404_NOT_FOUND)
        
        # Get the file and record ID
        file = request.FILES.get('file')
        record_id = request.data.get('record_id')
        title = request.data.get('title', '')
        description = request.data.get('description', '')
        
        if not file:
            return Response({
                'error': 'No file provided'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        if not record_id:
            return Response({
                'error': 'Record ID is required'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # Get the clinical record
        try:
            record = ClinicalRecord.objects.get(
                id=record_id,
                patient=patient,
                is_active=True
            )
        except ClinicalRecord.DoesNotExist:
            return Response({
                'error': 'Clinical record not found'
            }, status=status.HTTP_404_NOT_FOUND)
        
        # Create document
        document_data = {
            'clinical_record': record.id,
            'title': title or file.name,
            'file': file,
            'created_by': request.user.id,
        }
        
        if description:
            document_data['description'] = description
        
        serializer = ClinicalDocumentSerializer(data=document_data)
        if serializer.is_valid():
            document = serializer.save()
            logger.info(f"Uploaded document {document.id} for patient {patient.get_full_name()}")
            
            return Response({
                'document': ClinicalDocumentSerializer(document).data,
                'record': ClinicalRecordSerializer(record).data,
                'patient': PatientSerializer(patient).data
            }, status=status.HTTP_201_CREATED)
        else:
            return Response({
                'error': 'Invalid document data',
                'details': serializer.errors
            }, status=status.HTTP_400_BAD_REQUEST)
        
    except Exception as e:
        logger.error(f"Error uploading patient document: {e}")
        return Response({
            'error': 'Failed to upload document'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['GET'])
@permission_classes([permissions.IsAuthenticated, ClinicalRecordPermission])
def patient_search_records(request, patient_id):
    """
    Search clinical records for a specific patient
    
    Args:
        request: HTTP request
        patient_id: Patient ID from RxBackend
        
    Returns:
        JSON response with search results
    """
    try:
        # Get or sync patient
        patient_sync_service = get_patient_sync_service()
        patient = patient_sync_service.ensure_patient_exists(
            patient_id, 
            token=getattr(request, 'jwt_token', None)
        )
        
        if not patient:
            return Response({
                'error': 'Patient not found or could not be synced'
            }, status=status.HTTP_404_NOT_FOUND)
        
        # Get search query
        query = request.GET.get('q', '')
        if not query:
            return Response({
                'error': 'Search query is required'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # Search records
        records = ClinicalRecord.objects.filter(
            patient=patient,
            is_active=True
        ).filter(
            Q(title__icontains=query) |
            Q(description__icontains=query) |
            Q(record_type__icontains=query)
        ).order_by('-record_date', '-created_at')
        
        # Pagination
        paginator = PatientRecordPagination()
        page = paginator.paginate_queryset(records, request)
        
        if page is not None:
            serializer = ClinicalRecordSerializer(page, many=True)
            return paginator.get_paginated_response(serializer.data)
        
        # If no pagination
        serializer = ClinicalRecordSerializer(records, many=True)
        return Response({
            'results': serializer.data,
            'count': records.count(),
            'query': query,
            'patient': PatientSerializer(patient).data
        })
        
    except Exception as e:
        logger.error(f"Error searching patient records: {e}")
        return Response({
            'error': 'Failed to search records'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
