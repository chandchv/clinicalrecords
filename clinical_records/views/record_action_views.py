"""
Record Action Views
Handles Sync, Seal, and Share actions for Clinical Records
"""

import logging
from django.shortcuts import get_object_or_404
from rest_framework import status, permissions
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
from django.utils import timezone
import uuid

from ..models import ClinicalRecord, ShareToken
from ..services.record_sync_service import get_record_sync_service
from ..services.patient_sync_service import get_patient_sync_service
from ..permissions import ClinicalRecordPermission

logger = logging.getLogger(__name__)

@api_view(['POST'])
@permission_classes([permissions.IsAuthenticated])
def sync_records(request):
    """
    Trigger synchronization of records from RxBackend
    """
    try:
        # Get patient context
        patient_id = None
        if hasattr(request, 'jwt_claims'):
             patient_id = request.jwt_claims.get('patient_id')
        elif request.session.get('jwt_claims'):
             patient_id = request.session.get('jwt_claims', {}).get('patient_id')
        
        if not patient_id:
            # Fallback for session auth
             patient_id = request.session.get('patient_id')

        if not patient_id:
             return Response({'error': 'Patient context required'}, status=400)

        # Get token
        token = getattr(request, 'jwt_token', None) or request.session.get('jwt_token')
        if not token and 'HTTP_AUTHORIZATION' in request.META:
             auth = request.META['HTTP_AUTHORIZATION'].split()
             if len(auth) == 2 and auth[0].lower() == 'bearer':
                 token = auth[1]
        
        # Get patient object
        patient_service = get_patient_sync_service()
        patient = patient_service.ensure_patient_exists(patient_id, token)
        
        if not patient:
             return Response({'error': 'Patient not found'}, status=404)

        # Sync services
        sync_service = get_record_sync_service()
        
        # We need to pass the user to assign 'created_by'
        # But wait, existing service didn't take user. I should update it.
        # For now, I will modify service to use request.user if I can, or update service in next step.
        # I'll rely on service Update in next step.
        
        p_count = sync_service.sync_prescriptions(patient, token, user=request.user)
        l_count = sync_service.sync_labs(patient, token, user=request.user)
        
        return Response({
            'success': True,
            'message': f"Synced {p_count} prescriptions and {l_count} lab reports.",
            'details': {
                'prescriptions': p_count,
                'labs': l_count
            }
        })

    except Exception as e:
        logger.error(f"Sync failed: {e}")
        return Response({'error': str(e)}, status=500)

def get_patient_id(request):
    """Helper to extract patient_id from request or session"""
    if hasattr(request, 'jwt_claims') and request.jwt_claims:
        return request.jwt_claims.get('patient_id')
    if request.session.get('jwt_claims'):
        return request.session.get('jwt_claims', {}).get('patient_id')
    return request.session.get('patient_id')

@api_view(['POST'])
@permission_classes([permissions.IsAuthenticated, ClinicalRecordPermission])
def toggle_seal_record(request, record_id):
    """
    Toggle the sealed status of a record
    """
    record = get_object_or_404(ClinicalRecord, id=record_id)
    
    # Verify ownership
    patient_id = get_patient_id(request)
    if not patient_id:
        return Response({'error': 'Patient context required'}, status=403)
        
    # Check if record belongs to this patient
    # Assuming record.patient has a matching ID or external_id?
    # record.patient is a Patient model instance.
    # We need to compare record.patient.id (local DB ID) vs patient_id (from JWT).
    # JWT patient_id is usually RxBackend's Patient ID or local UUID? 
    # In SyncService, we assumed patient_id passed to it is valid for lookup.
    # In jwt_upload_views, get_patient_sync_service().ensure_patient_exists uses patient_id.
    # If the patient exists locally, we should check record.patient.external_id == patient_id (if patient_id is external) 
    # OR record.patient.id == patient_id (if patient_id is local).
    # Given the SyncService creates Patient with external_id (probably), and we pass patient_id from JWT.
    # Let's check Patient model to see if it has external_id.
    # Or simplified: verify record.patient.id matches the one retrieved via 'ensure_patient_exists' or similar.
    # But for speed, if we trust 'patient_id' session variable corresponds to record.patient.external_id or similar.
    
    # Safest: Use PatientSyncService helper to get local patient, then compare.
    from ..services.patient_sync_service import get_patient_sync_service
    token = getattr(request, 'jwt_token', None) or request.session.get('jwt_token')
    
    # We don't want to sync, just find. But ensure_patient_exists is robust.
    # But it might be expensive.
    # Let's try to match ID directly first.
    if str(record.patient.id) == str(patient_id):
         pass
    elif hasattr(record.patient, 'external_id') and str(record.patient.external_id) == str(patient_id):
         pass
    else:
         # Fallback to sync service to be sure we have the correct local patient
         # (Only if IDs don't match, maybe patient_id is external ID)
         service = get_patient_sync_service()
         local_patient = service.get_local_patient(patient_id)
         if not local_patient or local_patient != record.patient:
              return Response({'error': 'You do not have permission to modify this record'}, status=403)

    # Toggle
    record.is_sealed = not record.is_sealed
    record.save()
    
    return Response({
        'success': True,
        'is_sealed': record.is_sealed,
        'message': 'Record sealed' if record.is_sealed else 'Record unsealed'
    })

@api_view(['POST'])
@permission_classes([permissions.IsAuthenticated, ClinicalRecordPermission])
def share_record(request, record_id):
    """
    Generate a share token for a record
    """
    record = get_object_or_404(ClinicalRecord, id=record_id)
    
    # Verify ownership
    patient_id = get_patient_id(request)
    if not patient_id:
        return Response({'error': 'Patient context required'}, status=403)
        
    if str(record.patient.id) != str(patient_id):
         if hasattr(record.patient, 'external_id') and str(record.patient.external_id) == str(patient_id):
             pass
         else:
             # Check via service
             from ..services.patient_sync_service import get_patient_sync_service
             service = get_patient_sync_service()
             local_patient = service.get_local_patient(patient_id)
             if not local_patient or local_patient != record.patient:
                return Response({'error': 'You do not have permission to share this record'}, status=403)
    
    # Generate token
    expiry = request.data.get('expiry_days', 7)
    
    token = ShareToken.objects.create(
        clinical_record=record,
        token=str(uuid.uuid4()),
        expires_at=timezone.now() + timezone.timedelta(days=expiry),
        created_by=request.user,
        tenant_id=record.tenant_id
    )
    
    share_url = f"/records/shared/{token.token}/" # Frontend URL structure
    
    return Response({
        'success': True,
        'share_token': token.token,
        'share_url': share_url,
        'expires_at': token.expires_at
    })
