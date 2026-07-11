"""
Secure Sharing API Views

This module contains REST API ViewSets for managing secure sharing of clinical records.
Implements secure token-based sharing with access control and audit logging.
"""
import logging
import os
from django.db.models import Q
from django.utils import timezone
from django.conf import settings
from django.http import FileResponse
from rest_framework import viewsets, status, permissions
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.pagination import PageNumberPagination

from ..models import ClinicalRecord, ClinicalDocument, ShareToken
from ..serializers import ShareTokenSerializer
from ..services.audit_service import audit_service
from ..signals import notify_record_accessed
from users.models import AuditLog, Patient

logger = logging.getLogger(__name__)


class SecureSharingViewSet(viewsets.ViewSet):
    """
    ViewSet for secure sharing functionality.
    
    Provides endpoints for creating, managing, and accessing secure share tokens
    for clinical records, documents, and patient bundles.
    """
    permission_classes = [permissions.IsAuthenticated]
    
    def get_permissions(self):
        """
        Instantiate and return the list of permissions that this view requires.
        """
        if self.action in ['access_shared_content', 'validate_share_token']:
            # Public access for shared content (no authentication required)
            permission_classes = []
        else:
            permission_classes = [permissions.IsAuthenticated]
        
        return [permission() for permission in permission_classes]
    
    @action(detail=False, methods=['post'], url_path='create-document-share')
    def create_document_share(self, request):
        """
        Create a secure share token for a specific document.
        
        Request body:
        {
            "document_id": "uuid",
            "expires_in_hours": 24,
            "max_accesses": 10,
            "allowed_ips": ["192.168.1.1"],
            "patient_consent": true,
            "purpose": "Referral to specialist",
            "recipient_info": {
                "name": "Dr. Smith",
                "organization": "City Hospital"
            }
        }
        """
        try:
            document_id = request.data.get('document_id')
            if not document_id:
                return Response(
                    {'error': 'document_id is required'},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            # Get the document
            try:
                document = ClinicalDocument.objects.get(
                    id=document_id,
                    clinical_record__clinic=request.user.current_tenant
                )
            except ClinicalDocument.DoesNotExist:
                return Response(
                    {'error': 'Document not found'},
                    status=status.HTTP_404_NOT_FOUND
                )
            
            # Extract parameters
            expires_in_hours = request.data.get('expires_in_hours', 24)
            max_accesses = request.data.get('max_accesses')
            allowed_ips = request.data.get('allowed_ips', [])
            patient_consent = request.data.get('patient_consent', True)
            purpose = request.data.get('purpose', '')
            recipient_info = request.data.get('recipient_info', {})
            
            # Validate parameters
            if expires_in_hours > 168:  # Max 7 days
                return Response(
                    {'error': 'Maximum expiry time is 168 hours (7 days)'},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            if max_accesses and max_accesses > 100:  # Max 100 accesses
                return Response(
                    {'error': 'Maximum access count is 100'},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            # Create share token
            share_token = ShareToken.create_document_share(
                clinical_document=document,
                created_by=request.user,
                expires_in_hours=expires_in_hours,
                max_accesses=max_accesses,
                allowed_ips=allowed_ips,
                patient_consent=patient_consent,
                purpose=purpose,
                recipient_info=recipient_info
            )
            
            # Log the creation
            AuditLog.log_action(
                user=request.user,
                action='SHARE_TOKEN_CREATED',
                resource_type='CLINICAL_DOCUMENT',
                resource_id=str(document.id),
                details={
                    'share_token_id': str(share_token.id),
                    'scope': 'document',
                    'expires_in_hours': expires_in_hours,
                    'max_accesses': max_accesses,
                    'purpose': purpose,
                    'patient_consent': patient_consent
                },
                tenant=request.user.current_tenant
            )
            
            # Generate share URL
            share_url = f"{settings.BASE_URL}/clinical-records/share/{share_token.token}/"
            
            serializer = ShareTokenSerializer(share_token)
            response_data = serializer.data
            response_data['share_url'] = share_url
            
            return Response(response_data, status=status.HTTP_201_CREATED)
            
        except Exception as e:
            logger.error(f"Document share creation failed: {e}")
            return Response(
                {'error': 'Share creation failed'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    @action(detail=False, methods=['post'], url_path='create-record-share')
    def create_record_share(self, request):
        """
        Create a secure share token for a clinical record.
        
        Request body:
        {
            "record_id": "uuid",
            "expires_in_hours": 24,
            "max_accesses": 10,
            "allowed_ips": ["192.168.1.1"],
            "patient_consent": true,
            "purpose": "Second opinion consultation",
            "recipient_info": {
                "name": "Dr. Johnson",
                "organization": "Medical Center"
            }
        }
        """
        try:
            record_id = request.data.get('record_id')
            if not record_id:
                return Response(
                    {'error': 'record_id is required'},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            # Get the clinical record
            try:
                clinical_record = ClinicalRecord.objects.get(
                    id=record_id,
                    clinic=request.user.current_tenant
                )
            except ClinicalRecord.DoesNotExist:
                return Response(
                    {'error': 'Clinical record not found'},
                    status=status.HTTP_404_NOT_FOUND
                )
            
            # Extract parameters
            expires_in_hours = request.data.get('expires_in_hours', 24)
            max_accesses = request.data.get('max_accesses')
            allowed_ips = request.data.get('allowed_ips', [])
            patient_consent = request.data.get('patient_consent', True)
            purpose = request.data.get('purpose', '')
            recipient_info = request.data.get('recipient_info', {})
            
            # Validate parameters
            if expires_in_hours > 168:  # Max 7 days
                return Response(
                    {'error': 'Maximum expiry time is 168 hours (7 days)'},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            # Create share token
            share_token = ShareToken.create_record_share(
                clinical_record=clinical_record,
                created_by=request.user,
                expires_in_hours=expires_in_hours,
                max_accesses=max_accesses,
                allowed_ips=allowed_ips,
                patient_consent=patient_consent,
                purpose=purpose,
                recipient_info=recipient_info
            )
            
            # Log the creation
            AuditLog.log_action(
                user=request.user,
                action='SHARE_TOKEN_CREATED',
                resource_type='CLINICAL_RECORD',
                resource_id=str(clinical_record.id),
                details={
                    'share_token_id': str(share_token.id),
                    'scope': 'record',
                    'expires_in_hours': expires_in_hours,
                    'max_accesses': max_accesses,
                    'purpose': purpose,
                    'patient_consent': patient_consent
                },
                tenant=request.user.current_tenant
            )
            
            # Generate share URL
            share_url = f"{settings.BASE_URL}/clinical-records/share/{share_token.token}/"
            
            serializer = ShareTokenSerializer(share_token)
            response_data = serializer.data
            response_data['share_url'] = share_url
            
            return Response(response_data, status=status.HTTP_201_CREATED)
            
        except Exception as e:
            logger.error(f"Record share creation failed: {e}")
            return Response(
                {'error': 'Share creation failed'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    @action(detail=False, methods=['post'], url_path='create-patient-bundle-share')
    def create_patient_bundle_share(self, request):
        """
        Create a secure share token for a patient's complete clinical data bundle.
        
        Request body:
        {
            "patient_id": "uuid",
            "expires_in_hours": 24,
            "max_accesses": 5,
            "allowed_ips": ["192.168.1.1"],
            "patient_consent": true,
            "purpose": "Transfer of care",
            "recipient_info": {
                "name": "Dr. Wilson",
                "organization": "Regional Hospital"
            }
        }
        """
        try:
            patient_id = request.data.get('patient_id')
            if not patient_id:
                return Response(
                    {'error': 'patient_id is required'},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            # Get the patient
            try:
                patient = Patient.objects.get(
                    id=patient_id,
                    clinic=request.user.current_tenant
                )
            except Patient.DoesNotExist:
                return Response(
                    {'error': 'Patient not found'},
                    status=status.HTTP_404_NOT_FOUND
                )
            
            # Extract parameters
            expires_in_hours = request.data.get('expires_in_hours', 24)
            max_accesses = request.data.get('max_accesses')
            allowed_ips = request.data.get('allowed_ips', [])
            patient_consent = request.data.get('patient_consent', True)
            purpose = request.data.get('purpose', '')
            recipient_info = request.data.get('recipient_info', {})
            
            # Validate parameters
            if expires_in_hours > 168:  # Max 7 days
                return Response(
                    {'error': 'Maximum expiry time is 168 hours (7 days)'},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            # Create share token
            share_token = ShareToken.create_patient_bundle_share(
                patient=patient,
                created_by=request.user,
                expires_in_hours=expires_in_hours,
                max_accesses=max_accesses,
                allowed_ips=allowed_ips,
                patient_consent=patient_consent,
                purpose=purpose,
                recipient_info=recipient_info
            )
            
            # Log the creation
            AuditLog.log_action(
                user=request.user,
                action='SHARE_TOKEN_CREATED',
                resource_type='PATIENT',
                resource_id=str(patient.id),
                details={
                    'share_token_id': str(share_token.id),
                    'scope': 'patient_bundle',
                    'expires_in_hours': expires_in_hours,
                    'max_accesses': max_accesses,
                    'purpose': purpose,
                    'patient_consent': patient_consent
                },
                tenant=request.user.current_tenant
            )
            
            # Generate share URL
            share_url = f"{settings.BASE_URL}/clinical-records/share/{share_token.token}/"
            
            serializer = ShareTokenSerializer(share_token)
            response_data = serializer.data
            response_data['share_url'] = share_url
            
            return Response(response_data, status=status.HTTP_201_CREATED)
            
        except Exception as e:
            logger.error(f"Patient bundle share creation failed: {e}")
            return Response(
                {'error': 'Share creation failed'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    @action(detail=False, methods=['get'], url_path='list')
    def list_share_tokens(self, request):
        """
        List all share tokens created by the current user's clinic.
        
        Query parameters:
        - scope: Filter by scope (document, record, patient_bundle)
        - is_active: Filter by active status (true/false)
        - patient_id: Filter by patient
        """
        try:
            # Base queryset
            queryset = ShareToken.objects.filter(
                clinic=request.user.current_tenant
            ).select_related(
                'clinical_document',
                'clinical_record',
                'patient',
                'created_by',
                'revoked_by'
            ).order_by('-created_at')
            
            # Apply filters
            scope = request.query_params.get('scope')
            if scope:
                queryset = queryset.filter(scope=scope)
            
            is_active = request.query_params.get('is_active')
            if is_active is not None:
                is_active_bool = is_active.lower() == 'true'
                queryset = queryset.filter(is_active=is_active_bool)
            
            patient_id = request.query_params.get('patient_id')
            if patient_id:
                queryset = queryset.filter(
                    Q(patient_id=patient_id) |
                    Q(clinical_record__patient_id=patient_id) |
                    Q(clinical_document__clinical_record__patient_id=patient_id)
                )
            
            # Paginate results
            paginator = PageNumberPagination()
            paginator.page_size = 20
            page = paginator.paginate_queryset(queryset, request)
            
            if page is not None:
                serializer = ShareTokenSerializer(page, many=True)
                return paginator.get_paginated_response(serializer.data)
            
            serializer = ShareTokenSerializer(queryset, many=True)
            return Response(serializer.data)
            
        except Exception as e:
            logger.error(f"Share token listing failed: {e}")
            return Response(
                {'error': 'Failed to list share tokens'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    @action(detail=False, methods=['post'], url_path='revoke/(?P<token_id>[^/.]+)')
    def revoke_share_token(self, request, token_id=None):
        """
        Revoke a share token.
        
        Request body:
        {
            "reason": "No longer needed"
        }
        """
        try:
            if not token_id:
                return Response(
                    {'error': 'token_id is required'},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            # Get the share token
            try:
                share_token = ShareToken.objects.get(
                    id=token_id,
                    clinic=request.user.current_tenant
                )
            except ShareToken.DoesNotExist:
                return Response(
                    {'error': 'Share token not found'},
                    status=status.HTTP_404_NOT_FOUND
                )
            
            # Check if already revoked
            if share_token.revoked_at:
                return Response(
                    {'error': 'Share token is already revoked'},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            # Get revocation reason
            reason = request.data.get('reason', 'Revoked by user')
            
            # Revoke the token
            share_token.revoke(revoked_by=request.user, reason=reason)
            
            serializer = ShareTokenSerializer(share_token)
            return Response(serializer.data)
            
        except Exception as e:
            logger.error(f"Share token revocation failed: {e}")
            return Response(
                {'error': 'Revocation failed'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    @action(detail=False, methods=['post'], url_path='extend/(?P<token_id>[^/.]+)')
    def extend_share_token(self, request, token_id=None):
        """
        Extend the expiry time of a share token.
        
        Request body:
        {
            "additional_hours": 24
        }
        """
        try:
            if not token_id:
                return Response(
                    {'error': 'token_id is required'},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            # Get the share token
            try:
                share_token = ShareToken.objects.get(
                    id=token_id,
                    clinic=request.user.current_tenant
                )
            except ShareToken.DoesNotExist:
                return Response(
                    {'error': 'Share token not found'},
                    status=status.HTTP_404_NOT_FOUND
                )
            
            # Check if token is still valid for extension
            if share_token.revoked_at:
                return Response(
                    {'error': 'Cannot extend revoked token'},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            # Get additional hours
            additional_hours = request.data.get('additional_hours')
            if not additional_hours or additional_hours <= 0:
                return Response(
                    {'error': 'additional_hours must be a positive number'},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            if additional_hours > 168:  # Max 7 days extension
                return Response(
                    {'error': 'Maximum extension is 168 hours (7 days)'},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            # Extend the token
            share_token.extend_expiry(additional_hours, request.user)
            
            serializer = ShareTokenSerializer(share_token)
            return Response(serializer.data)
            
        except Exception as e:
            logger.error(f"Share token extension failed: {e}")
            return Response(
                {'error': 'Extension failed'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    @action(detail=False, methods=['get'], url_path='access/(?P<token>[^/.]+)')
    def access_shared_content(self, request, token=None):
        """
        Access shared content using a share token.
        This endpoint is publicly accessible (no authentication required).
        
        Query parameters:
        - format: Response format (json, fhir, file)
        """
        try:
            if not token:
                return Response(
                    {'error': 'Token is required'},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            # Get the share token
            try:
                share_token = ShareToken.objects.select_related(
                    'clinical_document',
                    'clinical_record',
                    'patient',
                    'clinic'
                ).get(token=token)
            except ShareToken.DoesNotExist:
                return Response(
                    {'error': 'Invalid or expired share token'},
                    status=status.HTTP_404_NOT_FOUND
                )
            
            # Get client IP
            client_ip = self._get_client_ip(request)
            user_agent = request.META.get('HTTP_USER_AGENT', '')
            
            # Validate and record access
            if not share_token.record_access(
                request_ip=client_ip,
                user_agent=user_agent,
                additional_info={'format': request.query_params.get('format', 'json')}
            ):
                # Access validation failed, error already logged
                is_valid, error_msg = share_token.validate_access(client_ip)
                return Response(
                    {'error': error_msg},
                    status=status.HTTP_403_FORBIDDEN
                )
            
            # Get requested format
            response_format = request.query_params.get('format', 'json')
            
            # Generate response based on scope and format
            if share_token.scope == 'document':
                return self._serve_document_content(share_token, response_format)
            elif share_token.scope == 'record':
                return self._serve_record_content(share_token, response_format)
            elif share_token.scope == 'patient_bundle':
                return self._serve_patient_bundle_content(share_token, response_format)
            else:
                return Response(
                    {'error': 'Invalid share token scope'},
                    status=status.HTTP_400_BAD_REQUEST
                )
                
        except Exception as e:
            logger.error(f"Shared content access failed: {e}")
            return Response(
                {'error': 'Access failed'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    @action(detail=False, methods=['get'], url_path='validate/(?P<token>[^/.]+)')
    def validate_share_token(self, request, token=None):
        """
        Validate a share token without accessing the content.
        This endpoint is publicly accessible.
        """
        try:
            if not token:
                return Response(
                    {'error': 'Token is required'},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            # Get the share token
            try:
                share_token = ShareToken.objects.get(token=token)
            except ShareToken.DoesNotExist:
                return Response({
                    'valid': False,
                    'error': 'Token not found'
                })
            
            # Get client IP for validation
            client_ip = self._get_client_ip(request)
            
            # Validate access without recording it
            is_valid, error_msg = share_token.validate_access(client_ip)
            
            response_data = {
                'valid': is_valid,
                'expires_at': share_token.expires_at,
                'access_remaining': share_token.access_remaining,
                'scope': share_token.scope,
                'content_summary': share_token.get_shared_content_summary()
            }
            
            if not is_valid:
                response_data['error'] = error_msg
            
            return Response(response_data)
            
        except Exception as e:
            logger.error(f"Share token validation failed: {e}")
            return Response({
                'valid': False,
                'error': 'Validation failed'
            })
    
    def _get_client_ip(self, request):
        """Get the client IP address from the request."""
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            ip = x_forwarded_for.split(',')[0]
        else:
            ip = request.META.get('REMOTE_ADDR')
        return ip
    
    def _serve_document_content(self, share_token, response_format):
        """Serve content for document scope share tokens."""
        document = share_token.clinical_document
        
        if response_format == 'json':
            # Return document metadata and content info
            from ..serializers import ClinicalDocumentSerializer
            serializer = ClinicalDocumentSerializer(document)
            return Response({
                'share_info': {
                    'scope': share_token.scope,
                    'purpose': share_token.purpose,
                    'expires_at': share_token.expires_at,
                    'access_count': share_token.current_access_count
                },
                'document': serializer.data
            })
        
        elif response_format == 'file':
            # Serve the actual file
            if document.file and os.path.exists(document.file.path):
                response = FileResponse(
                    open(document.file.path, 'rb'),
                    content_type=document.content_type or 'application/octet-stream'
                )
                response['Content-Disposition'] = f'attachment; filename="{document.original_filename}"'
                return response
            else:
                return Response(
                    {'error': 'Document file not found'},
                    status=status.HTTP_404_NOT_FOUND
                )
        
        else:
            return Response(
                {'error': f'Unsupported format: {response_format}'},
                status=status.HTTP_400_BAD_REQUEST
            )
    
    def _serve_record_content(self, share_token, response_format):
        """Serve content for record scope share tokens."""
        clinical_record = share_token.clinical_record
        
        if response_format == 'json':
            # Return record with documents
            from ..serializers import ClinicalRecordSerializer
            serializer = ClinicalRecordSerializer(clinical_record)
            return Response({
                'share_info': {
                    'scope': share_token.scope,
                    'purpose': share_token.purpose,
                    'expires_at': share_token.expires_at,
                    'access_count': share_token.current_access_count
                },
                'clinical_record': serializer.data
            })
        
        elif response_format == 'fhir':
            # Return FHIR resources for the record
            try:
                from ..utils.fhir_utils import FHIRExportService
                fhir_service = FHIRExportService()
                resources = fhir_service.create_individual_resource(clinical_record)
                
                return Response(
                    [resource.dict() for resource in resources],
                    content_type='application/fhir+json'
                )
            except ImportError:
                return Response(
                    {'error': 'FHIR export not available'},
                    status=status.HTTP_503_SERVICE_UNAVAILABLE
                )
        
        else:
            return Response(
                {'error': f'Unsupported format: {response_format}'},
                status=status.HTTP_400_BAD_REQUEST
            )
    
    def _serve_patient_bundle_content(self, share_token, response_format):
        """Serve content for patient bundle scope share tokens."""
        patient = share_token.patient
        
        if response_format == 'json':
            # Return patient info with clinical records summary
            clinical_records = patient.clinical_records.filter(is_active=True)
            
            return Response({
                'share_info': {
                    'scope': share_token.scope,
                    'purpose': share_token.purpose,
                    'expires_at': share_token.expires_at,
                    'access_count': share_token.current_access_count
                },
                'patient': {
                    'name': patient.get_full_name(),
                    'date_of_birth': patient.date_of_birth,
                    'gender': patient.gender,
                    'record_count': clinical_records.count()
                },
                'clinical_records': [
                    {
                        'id': str(record.id),
                        'title': record.title,
                        'record_type': record.get_record_type_display(),
                        'record_date': record.record_date,
                        'document_count': record.documents.count()
                    }
                    for record in clinical_records
                ]
            })
        
        elif response_format == 'fhir':
            # Return FHIR bundle for the patient
            try:
                from ..utils.fhir_utils import FHIRExportService
                fhir_service = FHIRExportService()
                
                clinical_records = patient.clinical_records.filter(is_active=True)
                bundle = fhir_service.create_patient_bundle(
                    patient=patient,
                    clinical_records=clinical_records,
                    include_documents=True
                )
                
                if bundle:
                    return Response(
                        fhir_service.export_to_dict(bundle),
                        content_type='application/fhir+json'
                    )
                else:
                    return Response(
                        {'error': 'Failed to create FHIR bundle'},
                        status=status.HTTP_500_INTERNAL_SERVER_ERROR
                    )
            except ImportError:
                return Response(
                    {'error': 'FHIR export not available'},
                    status=status.HTTP_503_SERVICE_UNAVAILABLE
                )
        
        else:
            return Response(
                {'error': f'Unsupported format: {response_format}'},
                status=status.HTTP_400_BAD_REQUEST
            )