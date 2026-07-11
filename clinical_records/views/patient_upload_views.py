"""
Patient Upload Views for External Records

This module handles patient uploads of external prescriptions and lab records
with proper authentication, file processing, and record creation.
"""

import logging
from django.shortcuts import get_object_or_404, render
from django.http import JsonResponse
from django.core.exceptions import PermissionDenied
from rest_framework import status, permissions
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
from rest_framework.parsers import MultiPartParser, FormParser
from django.utils import timezone
from datetime import date

from ..models import Patient, ClinicalRecord, ClinicalDocument
from ..serializers import (
    PatientSerializer, ClinicalRecordSerializer, ClinicalDocumentSerializer
)
from ..services.patient_sync_service import get_patient_sync_service
from ..permissions import ClinicalRecordPermission

logger = logging.getLogger(__name__)


@api_view(['GET'])
@permission_classes([permissions.IsAuthenticated, ClinicalRecordPermission])
def patient_upload_page(request, patient_id):
    """
    Serve the patient upload page with JWT authentication
    
    Args:
        request: HTTP request with JWT token
        patient_id: Patient ID from RxBackend
        
    Returns:
        Rendered HTML page for patient uploads
    """
    try:
        # Extract patient ID from JWT claims if available
        jwt_patient_id = None
        if hasattr(request, 'jwt_claims'):
            jwt_patient_id = request.jwt_claims.get('patient_id')
            # If JWT has patient_id, use it instead of URL parameter
            if jwt_patient_id:
                patient_id = jwt_patient_id
        
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
        
        # Verify patient access through JWT claims
        if hasattr(request, 'jwt_claims'):
            jwt_user_id = request.jwt_claims.get('user_id')
            jwt_patient_id = request.jwt_claims.get('patient_id')
            
            # Check if user has access to this patient
            if jwt_patient_id and str(jwt_patient_id) != str(patient_id):
                return Response({
                    'error': 'Access denied: Patient ID mismatch'
                }, status=status.HTTP_403_FORBIDDEN)
        
        context = {
            'patient': patient,
            'patient_data': PatientSerializer(patient).data,
            'jwt_claims': getattr(request, 'jwt_claims', {}),
            'jwt_token': getattr(request, 'jwt_token', ''),
            'user': request.user
        }
        
        return render(request, 'clinical_records/patient_upload.html', context)
        
    except Exception as e:
        logger.error(f"Error loading patient upload page: {e}")
        return Response({
            'error': 'Failed to load upload page'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['POST'])
@permission_classes([permissions.IsAuthenticated, ClinicalRecordPermission])
def patient_upload_external_prescription(request, patient_id):
    """
    Upload external prescription for a patient
    
    Args:
        request: HTTP request with file and metadata
        patient_id: Patient ID from RxBackend
        
    Returns:
        JSON response with created record and document
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
        
        # Get upload data
        file = request.FILES.get('file')
        title = request.data.get('title', 'External Prescription')
        description = request.data.get('description', '')
        prescription_date = request.data.get('prescription_date')
        doctor_name = request.data.get('doctor_name', '')
        pharmacy_name = request.data.get('pharmacy_name', '')
        
        if not file:
            return Response({
                'error': 'No file provided'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # Parse prescription date
        prescription_date_obj = None
        if prescription_date:
            try:
                prescription_date_obj = timezone.datetime.strptime(prescription_date, '%Y-%m-%d').date()
            except ValueError:
                return Response({
                    'error': 'Invalid prescription date format. Use YYYY-MM-DD'
                }, status=status.HTTP_400_BAD_REQUEST)
        else:
            prescription_date_obj = date.today()
        
        # Create clinical record for the prescription
        record_data = {
            'patient': patient.id,
            'title': title,
            'description': f"External prescription uploaded by patient. Doctor: {doctor_name}. Pharmacy: {pharmacy_name}. {description}",
            'record_type': 'external_prescription',
            'status': 'active',
            'priority': 'normal',
            'record_date': prescription_date_obj,
            'is_confidential': False,
            'created_by': request.user.id,
        }
        
        record_serializer = ClinicalRecordSerializer(data=record_data)
        if not record_serializer.is_valid():
            return Response({
                'error': 'Invalid record data',
                'details': record_serializer.errors
            }, status=status.HTTP_400_BAD_REQUEST)
        
        record = record_serializer.save()
        
        # Create document for the uploaded file
        document_data = {
            'clinical_record': record.id,
            'title': f"Prescription - {title}",
            'file': file,
            'created_by': request.user.id,
        }
        
        document_serializer = ClinicalDocumentSerializer(data=document_data)
        if not document_serializer.is_valid():
            # Clean up the record if document creation fails
            record.delete()
            return Response({
                'error': 'Invalid document data',
                'details': document_serializer.errors
            }, status=status.HTTP_400_BAD_REQUEST)
        
        document = document_serializer.save()
        
        logger.info(f"Patient {patient.get_full_name()} uploaded external prescription: {record.id}")
        
        return Response({
            'success': True,
            'message': 'External prescription uploaded successfully',
            'record': ClinicalRecordSerializer(record).data,
            'document': ClinicalDocumentSerializer(document).data,
            'patient': PatientSerializer(patient).data
        }, status=status.HTTP_201_CREATED)
        
    except Exception as e:
        logger.error(f"Error uploading external prescription: {e}")
        return Response({
            'error': 'Failed to upload external prescription'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['POST'])
@permission_classes([permissions.IsAuthenticated, ClinicalRecordPermission])
def patient_upload_external_lab_report(request, patient_id):
    """
    Upload external lab report for a patient
    
    Args:
        request: HTTP request with file and metadata
        patient_id: Patient ID from RxBackend
        
    Returns:
        JSON response with created record and document
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
        
        # Get upload data
        file = request.FILES.get('file')
        title = request.data.get('title', 'External Lab Report')
        description = request.data.get('description', '')
        test_date = request.data.get('test_date')
        lab_name = request.data.get('lab_name', '')
        test_type = request.data.get('test_type', '')
        
        if not file:
            return Response({
                'error': 'No file provided'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # Parse test date
        test_date_obj = None
        if test_date:
            try:
                test_date_obj = timezone.datetime.strptime(test_date, '%Y-%m-%d').date()
            except ValueError:
                return Response({
                    'error': 'Invalid test date format. Use YYYY-MM-DD'
                }, status=status.HTTP_400_BAD_REQUEST)
        else:
            test_date_obj = date.today()
        
        # Create clinical record for the lab report
        record_data = {
            'patient': patient.id,
            'title': title,
            'description': f"External lab report uploaded by patient. Lab: {lab_name}. Test Type: {test_type}. {description}",
            'record_type': 'external_lab_report',
            'status': 'active',
            'priority': 'normal',
            'record_date': test_date_obj,
            'is_confidential': False,
            'created_by': request.user.id,
        }
        
        record_serializer = ClinicalRecordSerializer(data=record_data)
        if not record_serializer.is_valid():
            return Response({
                'error': 'Invalid record data',
                'details': record_serializer.errors
            }, status=status.HTTP_400_BAD_REQUEST)
        
        record = record_serializer.save()
        
        # Create document for the uploaded file
        document_data = {
            'clinical_record': record.id,
            'title': f"Lab Report - {title}",
            'file': file,
            'created_by': request.user.id,
        }
        
        document_serializer = ClinicalDocumentSerializer(data=document_data)
        if not document_serializer.is_valid():
            # Clean up the record if document creation fails
            record.delete()
            return Response({
                'error': 'Invalid document data',
                'details': document_serializer.errors
            }, status=status.HTTP_400_BAD_REQUEST)
        
        document = document_serializer.save()
        
        logger.info(f"Patient {patient.get_full_name()} uploaded external lab report: {record.id}")
        
        return Response({
            'success': True,
            'message': 'External lab report uploaded successfully',
            'record': ClinicalRecordSerializer(record).data,
            'document': ClinicalDocumentSerializer(document).data,
            'patient': PatientSerializer(patient).data
        }, status=status.HTTP_201_CREATED)
        
    except Exception as e:
        logger.error(f"Error uploading external lab report: {e}")
        return Response({
            'error': 'Failed to upload external lab report'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['POST'])
@permission_classes([permissions.IsAuthenticated, ClinicalRecordPermission])
def patient_upload_external_record(request, patient_id):
    """
    Upload any external medical record for a patient
    
    Args:
        request: HTTP request with file and metadata
        patient_id: Patient ID from RxBackend
        
    Returns:
        JSON response with created record and document
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
        
        # Get upload data
        file = request.FILES.get('file')
        title = request.data.get('title', 'External Medical Record')
        description = request.data.get('description', '')
        record_type = request.data.get('record_type', 'external_record')
        record_date = request.data.get('record_date')
        source_name = request.data.get('source_name', '')
        
        if not file:
            return Response({
                'error': 'No file provided'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # Parse record date
        record_date_obj = None
        if record_date:
            try:
                record_date_obj = timezone.datetime.strptime(record_date, '%Y-%m-%d').date()
            except ValueError:
                return Response({
                    'error': 'Invalid record date format. Use YYYY-MM-DD'
                }, status=status.HTTP_400_BAD_REQUEST)
        else:
            record_date_obj = date.today()
        
        # Create clinical record
        record_data = {
            'patient': patient.id,
            'title': title,
            'description': f"External medical record uploaded by patient. Source: {source_name}. {description}",
            'record_type': record_type,
            'status': 'active',
            'priority': 'normal',
            'record_date': record_date_obj,
            'is_confidential': False,
            'created_by': request.user.id,
        }
        
        record_serializer = ClinicalRecordSerializer(data=record_data)
        if not record_serializer.is_valid():
            return Response({
                'error': 'Invalid record data',
                'details': record_serializer.errors
            }, status=status.HTTP_400_BAD_REQUEST)
        
        record = record_serializer.save()
        
        # Create document for the uploaded file
        document_data = {
            'clinical_record': record.id,
            'title': f"Medical Record - {title}",
            'file': file,
            'created_by': request.user.id,
        }
        
        document_serializer = ClinicalDocumentSerializer(data=document_data)
        if not document_serializer.is_valid():
            # Clean up the record if document creation fails
            record.delete()
            return Response({
                'error': 'Invalid document data',
                'details': document_serializer.errors
            }, status=status.HTTP_400_BAD_REQUEST)
        
        document = document_serializer.save()
        
        logger.info(f"Patient {patient.get_full_name()} uploaded external record: {record.id}")
        
        return Response({
            'success': True,
            'message': 'External medical record uploaded successfully',
            'record': ClinicalRecordSerializer(record).data,
            'document': ClinicalDocumentSerializer(document).data,
            'patient': PatientSerializer(patient).data
        }, status=status.HTTP_201_CREATED)
        
    except Exception as e:
        logger.error(f"Error uploading external record: {e}")
        return Response({
            'error': 'Failed to upload external record'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['GET'])
@permission_classes([permissions.IsAuthenticated, ClinicalRecordPermission])
def patient_external_records_list(request, patient_id):
    """
    Get list of external records uploaded by patient
    
    Args:
        request: HTTP request
        patient_id: Patient ID from RxBackend
        
    Returns:
        JSON response with external records
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
        
        # Get external records (uploaded by patient)
        external_record_types = ['external_prescription', 'external_lab_report', 'external_record']
        records = ClinicalRecord.objects.filter(
            patient=patient,
            record_type__in=external_record_types,
            is_active=True
        ).order_by('-record_date', '-created_at')
        
        # Apply search filter
        search_query = request.GET.get('search', '')
        if search_query:
            records = records.filter(
                Q(title__icontains=search_query) |
                Q(description__icontains=search_query)
            )
        
        # Apply record type filter
        record_type = request.GET.get('record_type', '')
        if record_type:
            records = records.filter(record_type=record_type)
        
        # Serialize data
        serializer = ClinicalRecordSerializer(records, many=True)
        
        return Response({
            'results': serializer.data,
            'count': records.count(),
            'patient': PatientSerializer(patient).data,
            'record_types': [
                {'value': 'external_prescription', 'label': 'External Prescription'},
                {'value': 'external_lab_report', 'label': 'External Lab Report'},
                {'value': 'external_record', 'label': 'Other Medical Record'},
            ]
        })
        
    except Exception as e:
        logger.error(f"Error listing patient external records: {e}")
        return Response({
            'error': 'Failed to retrieve external records'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['GET'])
@permission_classes([permissions.IsAuthenticated, ClinicalRecordPermission])
def patient_upload_history(request, patient_id):
    """
    Get upload history for a patient
    
    Args:
        request: HTTP request
        patient_id: Patient ID from RxBackend
        
    Returns:
        JSON response with upload history
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
        
        # Get all records for this patient
        records = ClinicalRecord.objects.filter(
            patient=patient,
            is_active=True
        ).order_by('-created_at')
        
        # Get upload statistics
        total_records = records.count()
        external_records = records.filter(record_type__startswith='external_').count()
        prescriptions = records.filter(record_type='external_prescription').count()
        lab_reports = records.filter(record_type='external_lab_report').count()
        other_records = records.filter(record_type='external_record').count()
        
        # Get recent uploads (last 30 days)
        from datetime import timedelta
        thirty_days_ago = timezone.now() - timedelta(days=30)
        recent_uploads = records.filter(created_at__gte=thirty_days_ago).count()
        
        # Serialize recent records
        recent_records = records[:10]  # Last 10 records
        serializer = ClinicalRecordSerializer(recent_records, many=True)
        
        return Response({
            'patient': PatientSerializer(patient).data,
            'statistics': {
                'total_records': total_records,
                'external_records': external_records,
                'prescriptions': prescriptions,
                'lab_reports': lab_reports,
                'other_records': other_records,
                'recent_uploads': recent_uploads,
            },
            'recent_records': serializer.data
        })
        
    except Exception as e:
        logger.error(f"Error getting patient upload history: {e}")
        return Response({
            'error': 'Failed to retrieve upload history'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
