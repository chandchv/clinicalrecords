"""
JWT-Aware Upload Views for Clinical Records Service

This module handles patient uploads with proper JWT authentication
from RxBackend, ensuring secure access to patient records.
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
def jwt_patient_upload_page(request):
    """
    Serve the patient upload page with JWT authentication.
    Patient ID is extracted from JWT claims.
    
    Args:
        request: HTTP request with JWT token
        
    Returns:
        Rendered HTML page for patient uploads
    """
    try:
        # Extract patient ID from JWT claims or Session
        jwt_claims = {}
        if hasattr(request, 'jwt_claims'):
            jwt_claims = request.jwt_claims
        elif request.session.get('jwt_claims'):
            jwt_claims = request.session.get('jwt_claims')
            # Inject into request for consistency if needed elsewhere
            request.jwt_claims = jwt_claims
            
        patient_id = jwt_claims.get('patient_id')
        
        if not patient_id:
            # Fallback to direct session patient_id
            patient_id = request.session.get('patient_id')
            
        if not patient_id:
             return Response({
                'error': 'JWT token or Session context required'
            }, status=status.HTTP_401_UNAUTHORIZED)
        
        # Get token from request or session
        jwt_token = getattr(request, 'jwt_token', None) or request.session.get('jwt_token')

        # Get or sync patient
        patient_sync_service = get_patient_sync_service()
        patient = patient_sync_service.ensure_patient_exists(
            patient_id, 
            token=jwt_token
        )
        
        if not patient:
            return Response({
                'error': 'Patient not found or could not be synced'
            }, status=status.HTTP_404_NOT_FOUND)
        
        context = {
            'patient': patient,
            'patient_data': PatientSerializer(patient).data,
            'jwt_claims': jwt_claims,
            'user': request.user
        }
        
        return render(request, 'clinical_records/patient_upload.html', context)
        
    except Exception as e:
        logger.error(f"Error loading JWT patient upload page: {e}")
        return Response({
            'error': 'Failed to load upload page'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['POST'])
@permission_classes([permissions.IsAuthenticated, ClinicalRecordPermission])
def jwt_patient_upload_prescription(request):
    """
    Upload external prescription with JWT authentication.
    Patient ID is extracted from JWT claims.
    
    Args:
        request: HTTP request with JWT token and file data
        
    Returns:
        JSON response with upload status
    """
    try:
        # Extract patient ID from JWT claims
        if not hasattr(request, 'jwt_claims'):
            return Response({
                'error': 'JWT token required'
            }, status=status.HTTP_401_UNAUTHORIZED)
        
        jwt_claims = request.jwt_claims
        patient_id = jwt_claims.get('patient_id')
        
        if not patient_id:
            return Response({
                'error': 'Patient ID not found in JWT claims'
            }, status=status.HTTP_400_BAD_REQUEST)
        
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
        
        # Create clinical record
        record_data = {
            'patient': patient,
            'title': title,
            'description': f"External prescription uploaded by patient. {description}",
            'record_type': 'prescription',
            'record_date': prescription_date_obj,
            'created_by': request.user,
            'tenant_id': patient.tenant_id,
        }
        
        # Add doctor and pharmacy info to description
        if doctor_name:
            record_data['description'] += f" Doctor: {doctor_name}"
        if pharmacy_name:
            record_data['description'] += f" Pharmacy: {pharmacy_name}"
        
        clinical_record = ClinicalRecord.objects.create(**record_data)
        
        # Create clinical document
        document_data = {
            'clinical_record': clinical_record,
            'title': title,
            'file': file,
            'created_by': request.user,
            'tenant_id': patient.tenant_id,
        }
        
        clinical_document = ClinicalDocument.objects.create(**document_data)
        
        # Serialize response
        record_serializer = ClinicalRecordSerializer(clinical_record)
        document_serializer = ClinicalDocumentSerializer(clinical_document, context={'request': request})
        
        logger.info(f"Patient {patient_id} uploaded prescription: {title}")
        
        return Response({
            'success': True,
            'message': 'Prescription uploaded successfully',
            'record': record_serializer.data,
            'document': document_serializer.data
        }, status=status.HTTP_201_CREATED)
        
    except Exception as e:
        logger.error(f"Error uploading prescription: {e}")
        return Response({
            'error': 'Failed to upload prescription'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['POST'])
@permission_classes([permissions.IsAuthenticated, ClinicalRecordPermission])
def jwt_patient_upload_lab_report(request):
    """
    Upload external lab report with JWT authentication.
    Patient ID is extracted from JWT claims.
    
    Args:
        request: HTTP request with JWT token and file data
        
    Returns:
        JSON response with upload status
    """
    try:
        # Extract patient ID from JWT claims
        if not hasattr(request, 'jwt_claims'):
            return Response({
                'error': 'JWT token required'
            }, status=status.HTTP_401_UNAUTHORIZED)
        
        jwt_claims = request.jwt_claims
        patient_id = jwt_claims.get('patient_id')
        
        if not patient_id:
            return Response({
                'error': 'Patient ID not found in JWT claims'
            }, status=status.HTTP_400_BAD_REQUEST)
        
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
        
        # Create clinical record
        record_data = {
            'patient': patient,
            'title': title,
            'description': f"External lab report uploaded by patient. {description}",
            'record_type': 'lab_report',
            'record_date': test_date_obj,
            'created_by': request.user,
            'tenant_id': patient.tenant_id,
        }
        
        # Add lab and test info to description
        if lab_name:
            record_data['description'] += f" Lab: {lab_name}"
        if test_type:
            record_data['description'] += f" Test: {test_type}"
        
        clinical_record = ClinicalRecord.objects.create(**record_data)
        
        # Create clinical document
        document_data = {
            'clinical_record': clinical_record,
            'title': title,
            'file': file,
            'created_by': request.user,
            'tenant_id': patient.tenant_id,
        }
        
        clinical_document = ClinicalDocument.objects.create(**document_data)
        
        # Serialize response
        record_serializer = ClinicalRecordSerializer(clinical_record)
        document_serializer = ClinicalDocumentSerializer(clinical_document, context={'request': request})
        
        logger.info(f"Patient {patient_id} uploaded lab report: {title}")
        
        return Response({
            'success': True,
            'message': 'Lab report uploaded successfully',
            'record': record_serializer.data,
            'document': document_serializer.data
        }, status=status.HTTP_201_CREATED)
        
    except Exception as e:
        logger.error(f"Error uploading lab report: {e}")
        return Response({
            'error': 'Failed to upload lab report'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['POST'])
@permission_classes([permissions.IsAuthenticated, ClinicalRecordPermission])
def jwt_patient_upload_record(request):
    """
    Upload external medical record with JWT authentication.
    Patient ID is extracted from JWT claims.
    
    Args:
        request: HTTP request with JWT token and file data
        
    Returns:
        JSON response with upload status
    """
    try:
        # Extract patient ID from JWT claims
        if not hasattr(request, 'jwt_claims'):
            return Response({
                'error': 'JWT token required'
            }, status=status.HTTP_401_UNAUTHORIZED)
        
        jwt_claims = request.jwt_claims
        patient_id = jwt_claims.get('patient_id')
        
        if not patient_id:
            return Response({
                'error': 'Patient ID not found in JWT claims'
            }, status=status.HTTP_400_BAD_REQUEST)
        
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
        record_date = request.data.get('record_date')
        record_type = request.data.get('record_type', 'external_record')
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
            'patient': patient,
            'title': title,
            'description': f"External medical record uploaded by patient. {description}",
            'record_type': record_type,
            'record_date': record_date_obj,
            'created_by': request.user,
            'tenant_id': patient.tenant_id,
        }
        
        # Add source info to description
        if source_name:
            record_data['description'] += f" Source: {source_name}"
        
        clinical_record = ClinicalRecord.objects.create(**record_data)
        
        # Create clinical document
        document_data = {
            'clinical_record': clinical_record,
            'title': title,
            'file': file,
            'created_by': request.user,
            'tenant_id': patient.tenant_id,
        }
        
        clinical_document = ClinicalDocument.objects.create(**document_data)
        
        # Serialize response
        record_serializer = ClinicalRecordSerializer(clinical_record)
        document_serializer = ClinicalDocumentSerializer(clinical_document, context={'request': request})
        
        logger.info(f"Patient {patient_id} uploaded medical record: {title}")
        
        return Response({
            'success': True,
            'message': 'Medical record uploaded successfully',
            'record': record_serializer.data,
            'document': document_serializer.data
        }, status=status.HTTP_201_CREATED)
        
    except Exception as e:
        logger.error(f"Error uploading medical record: {e}")
        return Response({
            'error': 'Failed to upload medical record'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['GET'])
@permission_classes([permissions.IsAuthenticated, ClinicalRecordPermission])
def jwt_patient_external_records(request):
    """
    List patient's external records with JWT authentication.
    Patient ID is extracted from JWT claims.
    
    Args:
        request: HTTP request with JWT token
        
    Returns:
        JSON response with patient's external records
    """
    try:
        # Extract patient ID from GET parameters, JWT claims, or Session
        patient_id = request.GET.get('patient_id')
        
        if not patient_id:
            jwt_claims = {}
            if hasattr(request, 'jwt_claims'):
                jwt_claims = request.jwt_claims
            elif request.session.get('jwt_claims'):
                jwt_claims = request.session.get('jwt_claims')
                
            patient_id = jwt_claims.get('patient_id')
            
        if not patient_id:
            # Fallback to direct session patient_id
            patient_id = request.session.get('patient_id')
            
        if not patient_id:
             return Response({
                'error': 'patient_id or JWT/Session context required'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # Get token
        jwt_token = getattr(request, 'jwt_token', None) or request.session.get('jwt_token')
        
        # Get or sync patient
        patient_sync_service = get_patient_sync_service()
        patient = patient_sync_service.ensure_patient_exists(
            patient_id, 
            token=jwt_token
        )
        
        if not patient:
            return Response({
                'error': 'Patient not found or could not be synced'
            }, status=status.HTTP_404_NOT_FOUND)
        
        # Get external records (records uploaded by patients)
        external_records = ClinicalRecord.objects.filter(
            patient=patient,
            record_type__in=['prescription', 'lab_report', 'external_record', 'discharge_summary', 'consultation_report']
        ).order_by('-created_at')
        
        # Apply pagination
        page_size = int(request.GET.get('page_size', 20))
        page = int(request.GET.get('page', 1))
        
        start_idx = (page - 1) * page_size
        end_idx = start_idx + page_size
        
        records_page = external_records[start_idx:end_idx]
        
        # Serialize records
        serializer = ClinicalRecordSerializer(records_page, many=True, context={'request': request})
        
        return Response({
            'success': True,
            'results': serializer.data,
            'pagination': {
                'page': page,
                'page_size': page_size,
                'total_count': external_records.count(),
                'has_next': end_idx < external_records.count(),
                'has_previous': page > 1
            }
        }, status=status.HTTP_200_OK)
        
    except Exception as e:
        logger.error(f"Error fetching external records: {e}")
        return Response({
            'error': 'Failed to fetch external records'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['GET'])
@permission_classes([permissions.IsAuthenticated, ClinicalRecordPermission])
def jwt_patient_upload_history(request):
    """
    Get patient upload statistics with JWT authentication.
    Patient ID is extracted from JWT claims.
    
    Args:
        request: HTTP request with JWT token
        
    Returns:
        JSON response with upload statistics
    """
    try:
        # Extract patient ID from JWT claims or Session
        jwt_claims = {}
        if hasattr(request, 'jwt_claims'):
            jwt_claims = request.jwt_claims
        elif request.session.get('jwt_claims'):
            jwt_claims = request.session.get('jwt_claims')
            
        patient_id = jwt_claims.get('patient_id')
        
        if not patient_id:
            # Fallback to direct session patient_id
            patient_id = request.session.get('patient_id')
            
        if not patient_id:
             return Response({
                'error': 'JWT token or Session context required'
            }, status=status.HTTP_401_UNAUTHORIZED)
        
        # Get token
        jwt_token = getattr(request, 'jwt_token', None) or request.session.get('jwt_token')
        
        # Get or sync patient
        patient_sync_service = get_patient_sync_service()
        patient = patient_sync_service.ensure_patient_exists(
            patient_id, 
            token=jwt_token
        )
        
        if not patient:
            return Response({
                'error': 'Patient not found or could not be synced'
            }, status=status.HTTP_404_NOT_FOUND)
        
        # Get upload statistics
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
        
        return Response({
            'success': True,
            'statistics': {
                'total_records': total_records,
                'recent_uploads': recent_uploads,
                'records_by_type': records_by_type,
                'processing_queue': 0  # Could be implemented later
            }
        }, status=status.HTTP_200_OK)
        
    except Exception as e:
        logger.error(f"Error fetching upload history: {e}")
        return Response({
            'error': 'Failed to fetch upload history'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
