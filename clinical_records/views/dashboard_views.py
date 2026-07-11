"""
Dashboard Views for Clinical Records Service

This module provides clean, modern dashboard views for the Clinical Records Service
with proper JWT authentication and user-friendly interfaces.
"""

import logging
from django.shortcuts import render
from django.http import JsonResponse
from rest_framework import status, permissions
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
from django.utils import timezone

from ..models import Patient, ClinicalRecord, ClinicalDocument
from ..serializers import PatientSerializer, ClinicalRecordSerializer
from ..services.patient_sync_service import get_patient_sync_service
from ..permissions import ClinicalRecordPermission

logger = logging.getLogger(__name__)


def landing_page(request):
    """
    Serve the landing page (no authentication required).
    
    Args:
        request: HTTP request
        
    Returns:
        Rendered HTML landing page
    """
    return render(request, 'clinical_records/landing.html')


@api_view(['GET'])
@permission_classes([permissions.IsAuthenticated])
def dashboard_home(request):
    """
    Serve the main dashboard page with flexible authentication.
    Supports both JWT authentication and regular Django authentication.
    
    Args:
        request: HTTP request (with JWT token or regular auth)
        
    Returns:
        Rendered HTML dashboard page
    """
    try:
        patient = None
        jwt_claims = {}
        
        # Check if JWT claims are available (from JWT middleware)
        if hasattr(request, 'jwt_claims'):
            jwt_claims = request.jwt_claims
            patient_id = jwt_claims.get('patient_id')
            
            if patient_id:
                # Get or sync patient from JWT
                patient_sync_service = get_patient_sync_service()
                patient = patient_sync_service.ensure_patient_exists(
                    patient_id, 
                    token=getattr(request, 'jwt_token', None)
                )
        else:
            # Try to get patient from user attributes (for regular Django auth)
            if hasattr(request.user, 'patient_id'):
                patient_id = request.user.patient_id
                patient_sync_service = get_patient_sync_service()
                patient = patient_sync_service.ensure_patient_exists(
                    patient_id, 
                    token=getattr(request, 'jwt_token', None)
                )
            elif hasattr(request.user, 'patient'):
                # User has a patient relationship
                patient = request.user.patient
        
        # If no patient found, create a demo context
        if not patient:
            # Create a demo patient for display purposes
            patient_data = {
                'id': 0,
                'first_name': request.user.first_name or 'User',
                'last_name': request.user.last_name or '',
                'full_name': f"{request.user.first_name or 'User'} {request.user.last_name or ''}".strip(),
                'email': request.user.email or '',
                'phone_number': '',
                'date_of_birth': None,
                'age': None,
                'gender': '',
                'blood_group': '',
                'address': '',
                'clinic_id': None,
                'clinic_name': '',
                'is_active': True,
                'tenant_id': None
            }
            recent_records = []
            total_records = 0
            recent_uploads = 0
        else:
            # Get recent records for dashboard
            recent_records = ClinicalRecord.objects.filter(
                patient=patient
            ).order_by('-created_at')[:5]
            
            # Get statistics
            total_records = ClinicalRecord.objects.filter(patient=patient).count()
            recent_uploads = ClinicalRecord.objects.filter(
                patient=patient,
                created_at__gte=timezone.now() - timezone.timedelta(days=30)
            ).count()
            
            patient_data = PatientSerializer(patient).data
        
        context = {
            'patient': patient,
            'patient_data': patient_data,
            'jwt_claims': jwt_claims,
            'user': request.user,
            'recent_records': ClinicalRecordSerializer(recent_records, many=True, context={'request': request}).data if recent_records else [],
            'statistics': {
                'total_records': total_records,
                'recent_uploads': recent_uploads,
                'processing_queue': 0
            }
        }
        
        return render(request, 'clinical_records/dashboard.html', context)
        
    except Exception as e:
        logger.error(f"Error loading dashboard: {e}")
        return Response({
            'error': 'Failed to load dashboard'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['GET'])
@permission_classes([permissions.IsAuthenticated])
def records_list_page(request):
    """
    Serve the records listing page with flexible authentication.
    Supports both JWT authentication and regular Django authentication.
    
    Args:
        request: HTTP request (with JWT token or regular auth)
        
    Returns:
        Rendered HTML records listing page
    """
    try:
        patient = None
        jwt_claims = {}
        
        # Check if patient_id is in query parameters (for doctors/staff)
        patient_id = request.GET.get('patient_id')
        
        if patient_id:
            patient_sync_service = get_patient_sync_service()
            patient = patient_sync_service.ensure_patient_exists(
                patient_id, 
                token=getattr(request, 'jwt_token', None)
            )
        elif hasattr(request, 'jwt_claims'):
            jwt_claims = request.jwt_claims
            patient_id = jwt_claims.get('patient_id')
            
            if patient_id:
                # Get or sync patient from JWT
                patient_sync_service = get_patient_sync_service()
                patient = patient_sync_service.ensure_patient_exists(
                    patient_id, 
                    token=getattr(request, 'jwt_token', None)
                )
        else:
            # Try to get patient from user attributes (for regular Django auth)
            if hasattr(request.user, 'patient_id'):
                patient_id = request.user.patient_id
                patient_sync_service = get_patient_sync_service()
                patient = patient_sync_service.ensure_patient_exists(
                    patient_id, 
                    token=getattr(request, 'jwt_token', None)
                )
            elif hasattr(request.user, 'patient'):
                # User has a patient relationship
                patient = request.user.patient
        
        # If no patient found, create a demo context
        if not patient:
            patient_data = {
                'id': 0,
                'first_name': request.user.first_name or 'User',
                'last_name': request.user.last_name or '',
                'full_name': f"{request.user.first_name or 'User'} {request.user.last_name or ''}".strip(),
                'email': request.user.email or '',
                'phone_number': '',
                'date_of_birth': None,
                'age': None,
                'gender': '',
                'blood_group': '',
                'address': '',
                'clinic_id': None,
                'clinic_name': '',
                'is_active': True,
                'tenant_id': None
            }
        else:
            patient_data = PatientSerializer(patient).data
        
        context = {
            'patient': patient,
            'patient_data': patient_data,
            'jwt_claims': jwt_claims,
            'user': request.user
        }
        
        return render(request, 'clinical_records/records_list.html', context)
        
    except Exception as e:
        logger.error(f"Error loading records list: {e}")
        return Response({
            'error': 'Failed to load records list'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['GET'])
@permission_classes([permissions.IsAuthenticated])
def dashboard_stats(request):
    """
    Get dashboard statistics with flexible authentication.
    Supports both JWT authentication and regular Django authentication.
    
    Args:
        request: HTTP request (with JWT token or regular auth)
        
    Returns:
        JSON response with dashboard statistics
    """
    try:
        patient = None
        
        # Check if JWT claims are available (from JWT middleware)
        if hasattr(request, 'jwt_claims'):
            jwt_claims = request.jwt_claims
            patient_id = jwt_claims.get('patient_id')
            
            if patient_id:
                # Get or sync patient from JWT
                patient_sync_service = get_patient_sync_service()
                patient = patient_sync_service.ensure_patient_exists(
                    patient_id, 
                    token=getattr(request, 'jwt_token', None)
                )
        else:
            # Try to get patient from user attributes (for regular Django auth)
            if hasattr(request.user, 'patient_id'):
                patient_id = request.user.patient_id
                patient_sync_service = get_patient_sync_service()
                patient = patient_sync_service.ensure_patient_exists(
                    patient_id, 
                    token=getattr(request, 'jwt_token', None)
                )
            elif hasattr(request.user, 'patient'):
                # User has a patient relationship
                patient = request.user.patient
        
        # Get statistics
        if patient:
            total_records = ClinicalRecord.objects.filter(patient=patient).count()
            recent_uploads = ClinicalRecord.objects.filter(
                patient=patient,
                created_at__gte=timezone.now() - timezone.timedelta(days=30)
            ).count()
            
            # Get records by type
            records_by_type = {}
            for record_type in ['prescription', 'lab_report', 'external_record', 'discharge_summary', 'consultation_report']:
                count = ClinicalRecord.objects.filter(
                    patient=patient,
                    record_type=record_type
                ).count()
                records_by_type[record_type] = count
        else:
            # No patient found, return empty statistics
            total_records = 0
            recent_uploads = 0
            records_by_type = {}
        
        return Response({
            'success': True,
            'statistics': {
                'total_records': total_records,
                'recent_uploads': recent_uploads,
                'processing_queue': 0,
                'records_by_type': records_by_type
            }
        }, status=status.HTTP_200_OK)
        
    except Exception as e:
        logger.error(f"Error fetching dashboard stats: {e}")
        return Response({
            'error': 'Failed to fetch dashboard statistics'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)