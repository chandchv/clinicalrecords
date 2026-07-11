"""
Views for secure sharing interface.

This module provides both web interface views and API endpoints
for secure sharing of clinical records with external parties.
"""

import json
import logging
from typing import Dict, Any

from django.shortcuts import render, get_object_or_404, redirect
from django.http import JsonResponse, HttpResponse, Http404
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from django.contrib.auth.decorators import login_required
from django.utils.decorators import method_decorator
from django.views import View
from django.contrib import messages
from django.urls import reverse
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from users.models import Clinic, Patient
from ..models import ClinicalRecord, ClinicalDocument, ShareToken
from ..services.secure_sharing_service import secure_sharing_service
from ..permissions.rest_permissions import CanViewRecords, CanShareRecords
from ..decorators.audit_decorators import audit_api_call

logger = logging.getLogger(__name__)


@method_decorator(login_required, name='dispatch')
class SecureSharingView(View):
    """Web interface view for secure sharing management."""
    
    def get(self, request, record_id=None):
        """Render the secure sharing interface."""
        try:
            context = {
                'record_id': record_id,
                'sharing_config': {
                    'max_expiry_days': 365,
                    'default_expiry_days': 30,
                    'max_access_count': 100,
                    'enable_ip_restrictions': True,
                    'require_consent': True
                }
            }
            
            # If record_id is provided, get record details
            if record_id:
                record = get_object_or_404(ClinicalRecord, id=record_id)
                
                # Check permissions
                if not request.user.clinic or record.clinic != request.user.clinic:
                    messages.error(request, "You don't have permission to share this record.")
                    return redirect('clinical_records:patient_timeline', patient_id=record.patient.id)
                
                context['record'] = {
                    'id': str(record.id),
                    'title': record.title,
                    'record_type': record.record_type,
                    'patient_name': record.patient.get_full_name(),
                    'created_at': record.created_at.isoformat(),
                    'document_count': record.documents.count()
                }
                
                # Get existing shares
                existing_shares = secure_sharing_service.get_share_tokens(
                    record_id=str(record.id),
                    user=request.user,
                    active_only=False
                )
                context['existing_shares'] = existing_shares
            
            return render(request, 'clinical_records/secure_sharing.html', context)
            
        except Exception as e:
            logger.error(f"Error in secure sharing view: {e}", exc_info=True)
            messages.error(request, "An error occurred while loading the sharing interface.")
            return redirect('clinical_records:patient_timeline', patient_id=record.patient.id if record_id else None)


@method_decorator(login_required, name='dispatch')
class ShareManagementView(View):
    """Web interface view for managing all shares."""
    
    def get(self, request):
        """Render the share management dashboard."""
        try:
            # Get all shares for the user's clinic
            all_shares = secure_sharing_service.get_share_tokens(
                user=request.user,
                clinic=request.user.clinic,
                active_only=False
            )
            
            # Separate active and inactive shares
            active_shares = [share for share in all_shares if share['is_active']]
            inactive_shares = [share for share in all_shares if not share['is_active']]
            
            context = {
                'active_shares': active_shares,
                'inactive_shares': inactive_shares,
                'total_shares': len(all_shares),
                'active_count': len(active_shares),
                'inactive_count': len(inactive_shares)
            }
            
            return render(request, 'clinical_records/share_management.html', context)
            
        except Exception as e:
            logger.error(f"Error in share management view: {e}", exc_info=True)
            messages.error(request, "An error occurred while loading the share management dashboard.")
            return render(request, 'clinical_records/share_management.html', {'error': True})


class SharedRecordAccessView(View):
    """Public view for accessing shared records via token."""
    
    def get(self, request, token):
        """Display shared record access page."""
        try:
            # Access the shared record
            access_result = secure_sharing_service.access_shared_record(
                token=token,
                request=request
            )
            
            if not access_result['success']:
                context = {
                    'error': 'Invalid or expired share link',
                    'error_type': 'invalid_token'
                }
                return render(request, 'clinical_records/shared_access_error.html', context, status=403)
            
            context = {
                'record_data': access_result['record_data'],
                'share_info': access_result['share_info'],
                'token': token
            }
            
            return render(request, 'clinical_records/shared_record_view.html', context)
            
        except PermissionError as e:
            context = {
                'error': str(e),
                'error_type': 'permission_denied'
            }
            return render(request, 'clinical_records/shared_access_error.html', context, status=403)
            
        except ValueError as e:
            context = {
                'error': str(e),
                'error_type': 'invalid_token'
            }
            return render(request, 'clinical_records/shared_access_error.html', context, status=404)
            
        except Exception as e:
            logger.error(f"Error accessing shared record: {e}", exc_info=True)
            context = {
                'error': 'An error occurred while accessing the shared record',
                'error_type': 'server_error'
            }
            return render(request, 'clinical_records/shared_access_error.html', context, status=500)


@api_view(['POST'])
@permission_classes([IsAuthenticated, CanShareRecords])
@audit_api_call
def create_share_token_api(request, record_id):
    """
    API endpoint to create a share token for a clinical record.
    
    Args:
        record_id: ID of the clinical record to share
    """
    try:
        share_options = request.data
        
        # Validate required fields
        required_fields = ['expiry_days', 'access_level']
        for field in required_fields:
            if field not in share_options:
                return Response(
                    {'error': f'Missing required field: {field}'},
                    status=status.HTTP_400_BAD_REQUEST
                )
        
        # Create share token
        result = secure_sharing_service.create_share_token(
            record_id=record_id,
            user=request.user,
            share_options=share_options,
            request=request
        )
        
        return Response(result, status=status.HTTP_201_CREATED)
        
    except PermissionError as e:
        return Response(
            {'error': str(e)},
            status=status.HTTP_403_FORBIDDEN
        )
    except ValueError as e:
        return Response(
            {'error': str(e)},
            status=status.HTTP_400_BAD_REQUEST
        )
    except Exception as e:
        logger.error(f"Error creating share token: {e}")
        return Response(
            {'error': 'Failed to create share token'},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['POST'])
@permission_classes([IsAuthenticated, CanShareRecords])
@audit_api_call
def revoke_share_token_api(request, token_id):
    """
    API endpoint to revoke a share token.
    
    Args:
        token_id: ID of the share token to revoke
    """
    try:
        reason = request.data.get('reason', 'Manually revoked')
        
        result = secure_sharing_service.revoke_share_token(
            token_id=token_id,
            user=request.user,
            reason=reason,
            request=request
        )
        
        return Response(result, status=status.HTTP_200_OK)
        
    except PermissionError as e:
        return Response(
            {'error': str(e)},
            status=status.HTTP_403_FORBIDDEN
        )
    except ValueError as e:
        return Response(
            {'error': str(e)},
            status=status.HTTP_404_NOT_FOUND
        )
    except Exception as e:
        logger.error(f"Error revoking share token: {e}")
        return Response(
            {'error': 'Failed to revoke share token'},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['GET'])
@permission_classes([IsAuthenticated, CanViewRecords])
def get_share_tokens_api(request, record_id=None):
    """
    API endpoint to get share tokens.
    
    Args:
        record_id: Optional specific record ID
    """
    try:
        active_only = request.query_params.get('active_only', 'true').lower() == 'true'
        
        tokens = secure_sharing_service.get_share_tokens(
            record_id=record_id,
            user=request.user,
            clinic=request.user.clinic,
            active_only=active_only
        )
        
        return Response({
            'tokens': tokens,
            'count': len(tokens)
        }, status=status.HTTP_200_OK)
        
    except Exception as e:
        logger.error(f"Error getting share tokens: {e}")
        return Response(
            {'error': 'Failed to get share tokens'},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['GET'])
@permission_classes([IsAuthenticated, CanViewRecords])
def get_share_audit_trail_api(request, token_id):
    """
    API endpoint to get audit trail for a share token.
    
    Args:
        token_id: ID of the share token
    """
    try:
        audit_trail = secure_sharing_service.get_share_audit_trail(
            token_id=token_id,
            user=request.user
        )
        
        return Response({
            'audit_trail': audit_trail,
            'count': len(audit_trail)
        }, status=status.HTTP_200_OK)
        
    except PermissionError as e:
        return Response(
            {'error': str(e)},
            status=status.HTTP_403_FORBIDDEN
        )
    except ValueError as e:
        return Response(
            {'error': str(e)},
            status=status.HTTP_404_NOT_FOUND
        )
    except Exception as e:
        logger.error(f"Error getting share audit trail: {e}")
        return Response(
            {'error': 'Failed to get audit trail'},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['GET'])
def access_shared_record_api(request, token):
    """
    API endpoint to access a shared record via token.
    
    Args:
        token: Share token
    """
    try:
        result = secure_sharing_service.access_shared_record(
            token=token,
            request=request
        )
        
        return Response(result, status=status.HTTP_200_OK)
        
    except PermissionError as e:
        return Response(
            {'error': str(e)},
            status=status.HTTP_403_FORBIDDEN
        )
    except ValueError as e:
        return Response(
            {'error': str(e)},
            status=status.HTTP_404_NOT_FOUND
        )
    except Exception as e:
        logger.error(f"Error accessing shared record: {e}")
        return Response(
            {'error': 'Failed to access shared record'},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['GET'])
def shared_document_view_api(request, token, document_id):
    """
    API endpoint to view a shared document.
    
    Args:
        token: Share token
        document_id: ID of the document to view
    """
    try:
        # First validate the share token
        access_result = secure_sharing_service.access_shared_record(
            token=token,
            request=request
        )
        
        if not access_result['success']:
            return Response(
                {'error': 'Invalid or expired share token'},
                status=status.HTTP_403_FORBIDDEN
            )
        
        # Check if document is in the shared record
        record_data = access_result['record_data']
        document_found = False
        for doc in record_data.get('documents', []):
            if doc['id'] == document_id:
                document_found = True
                break
        
        if not document_found:
            return Response(
                {'error': 'Document not found in shared record'},
                status=status.HTTP_404_NOT_FOUND
            )
        
        # Get document
        document = get_object_or_404(ClinicalDocument, id=document_id)
        
        # Return document content
        with document.file.open('rb') as f:
            content = f.read()
        
        response = HttpResponse(content, content_type=document.content_type)
        response['Content-Disposition'] = f'inline; filename="{document.original_filename}"'
        response['Content-Length'] = len(content)
        
        return response
        
    except Exception as e:
        logger.error(f"Error viewing shared document: {e}")
        return Response(
            {'error': 'Failed to view document'},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['GET'])
def shared_document_download_api(request, token, document_id):
    """
    API endpoint to download a shared document.
    
    Args:
        token: Share token
        document_id: ID of the document to download
    """
    try:
        # First validate the share token and check download permission
        access_result = secure_sharing_service.access_shared_record(
            token=token,
            request=request
        )
        
        if not access_result['success']:
            return Response(
                {'error': 'Invalid or expired share token'},
                status=status.HTTP_403_FORBIDDEN
            )
        
        # Check if download is allowed
        share_info = access_result['share_info']
        if share_info['access_level'] not in ['DOWNLOAD', 'FULL']:
            return Response(
                {'error': 'Download not permitted for this share'},
                status=status.HTTP_403_FORBIDDEN
            )
        
        # Check if document is in the shared record
        record_data = access_result['record_data']
        document_found = False
        for doc in record_data.get('documents', []):
            if doc['id'] == document_id:
                document_found = True
                break
        
        if not document_found:
            return Response(
                {'error': 'Document not found in shared record'},
                status=status.HTTP_404_NOT_FOUND
            )
        
        # Get document
        document = get_object_or_404(ClinicalDocument, id=document_id)
        
        # Return document content for download
        with document.file.open('rb') as f:
            content = f.read()
        
        response = HttpResponse(content, content_type=document.content_type)
        response['Content-Disposition'] = f'attachment; filename="{document.original_filename}"'
        response['Content-Length'] = len(content)
        
        return response
        
    except Exception as e:
        logger.error(f"Error downloading shared document: {e}")
        return Response(
            {'error': 'Failed to download document'},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@login_required
@require_http_methods(["GET"])
def sharing_config_api(request):
    """
    API endpoint to get sharing configuration.
    """
    try:
        config = {
            'max_expiry_days': 365,
            'default_expiry_days': 30,
            'max_access_count': 100,
            'access_levels': [
                {'value': 'VIEW', 'label': 'View Only', 'description': 'Can view record and documents'},
                {'value': 'DOWNLOAD', 'label': 'View & Download', 'description': 'Can view and download documents'},
                {'value': 'FULL', 'label': 'Full Access', 'description': 'Full access to all record data'}
            ],
            'features': {
                'ip_restrictions': True,
                'patient_consent_required': True,
                'email_notifications': True,
                'audit_logging': True
            }
        }
        
        return JsonResponse(config)
        
    except Exception as e:
        logger.error(f"Error getting sharing config: {e}")
        return JsonResponse(
            {'error': 'Failed to get configuration'},
            status=500
        )


@method_decorator(login_required, name='dispatch')
class ShareAuditView(View):
    """Web interface view for share audit trail."""
    
    def get(self, request, token_id):
        """Render the share audit trail page."""
        try:
            # Get share token
            share_token = get_object_or_404(ShareToken, id=token_id)
            
            # Check permissions
            if not request.user.clinic or share_token.clinic != request.user.clinic:
                messages.error(request, "You don't have permission to view this audit trail.")
                return redirect('clinical_records:share_management')
            
            # Get audit trail
            audit_trail = secure_sharing_service.get_share_audit_trail(
                token_id=token_id,
                user=request.user
            )
            
            context = {
                'share_token': {
                    'id': str(share_token.id),
                    'token': share_token.token[:8] + '...',
                    'record_title': share_token.clinical_record.title,
                    'patient_name': share_token.clinical_record.patient.get_full_name(),
                    'created_by': share_token.created_by.get_full_name(),
                    'created_at': share_token.created_at.isoformat(),
                    'expires_at': share_token.expires_at.isoformat(),
                    'access_count': share_token.access_count,
                    'is_active': share_token.is_active
                },
                'audit_trail': audit_trail
            }
            
            return render(request, 'clinical_records/share_audit.html', context)
            
        except Exception as e:
            logger.error(f"Error in share audit view: {e}", exc_info=True)
            messages.error(request, "An error occurred while loading the audit trail.")
            return redirect('clinical_records:share_management')