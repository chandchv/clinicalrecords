"""
Secure sharing service for clinical records.

This service handles secure sharing of clinical records and documents
with external parties, including share token management, access control,
and audit logging.
"""

import secrets
import hashlib
import logging
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, List, Tuple
from urllib.parse import urljoin

from django.conf import settings
from django.utils import timezone
from django.contrib.auth import get_user_model
from django.urls import reverse
from django.core.mail import send_mail
from django.template.loader import render_to_string

from users.models import Clinic, Patient
from ..models import ClinicalRecord, ClinicalDocument, ShareToken
from .audit_service import audit_service
from .access_control_service import access_control_service

User = get_user_model()
logger = logging.getLogger(__name__)


class SecureSharingService:
    """Service for secure sharing of clinical records and documents."""
    
    def __init__(self):
        self.logger = logging.getLogger(f"{__name__}.{self.__class__.__name__}")
        self.config = getattr(settings, 'CLINICAL_RECORDS_SHARING', {})
        
        # Default sharing settings
        self.default_expiry_days = self.config.get('DEFAULT_EXPIRY_DAYS', 30)
        self.max_expiry_days = self.config.get('MAX_EXPIRY_DAYS', 365)
        self.max_access_count = self.config.get('MAX_ACCESS_COUNT', 100)
        self.require_consent = self.config.get('REQUIRE_CONSENT', True)
        self.enable_ip_restrictions = self.config.get('ENABLE_IP_RESTRICTIONS', True)
    
    def create_share_token(self, record_id: str, user: User, share_options: Dict[str, Any],
                          request=None) -> Dict[str, Any]:
        """
        Create a secure share token for a clinical record.
        
        Args:
            record_id: ID of the clinical record to share
            user: User creating the share
            share_options: Sharing configuration options
            request: HTTP request object for audit logging
            
        Returns:
            Dict containing share token information
        """
        try:
            # Get clinical record
            record = ClinicalRecord.objects.select_related(
                'patient', 'clinic', 'created_by'
            ).get(id=record_id)
            
            # Check permissions
            has_access, access_reason = access_control_service.check_record_access(
                user=user,
                record=record,
                action='share',
                request=request
            )
            
            if not has_access:
                raise PermissionError(f"Cannot share record: {access_reason}")
            
            # Validate share options
            validated_options = self._validate_share_options(share_options, record)
            
            # Check patient consent if required
            if self.require_consent and not validated_options.get('patient_consent_confirmed'):
                raise ValueError("Patient consent is required for sharing")
            
            # Generate secure token
            token = self._generate_secure_token()
            
            # Calculate expiry date
            expiry_date = self._calculate_expiry_date(validated_options.get('expiry_days'))
            
            # Create share token record
            share_token = ShareToken.objects.create(
                token=token,
                clinical_record=record,
                created_by=user,
                clinic=record.clinic,
                expires_at=expiry_date,
                max_access_count=validated_options.get('max_access_count', self.max_access_count),
                allowed_ip_addresses=validated_options.get('allowed_ips', []),
                access_level=validated_options.get('access_level', 'VIEW'),
                require_authentication=validated_options.get('require_authentication', False),
                patient_consent_confirmed=validated_options.get('patient_consent_confirmed', False),
                share_metadata={
                    'purpose': validated_options.get('purpose', ''),
                    'recipient_info': validated_options.get('recipient_info', {}),
                    'restrictions': validated_options.get('restrictions', {}),
                    'created_from_ip': request.META.get('REMOTE_ADDR') if request else None
                }
            )
            
            # Generate share URL
            share_url = self._generate_share_url(token)
            
            # Send notification if requested
            if validated_options.get('send_notification'):
                self._send_share_notification(share_token, validated_options, share_url)
            
            # Log share creation
            audit_service.log_clinical_action(
                action='RECORD_SHARE_CREATED',
                user=user,
                resource_type='CLINICAL_RECORD',
                resource_id=str(record.id),
                clinic=record.clinic,
                patient_id=str(record.patient.id),
                details={
                    'share_token_id': str(share_token.id),
                    'expires_at': expiry_date.isoformat(),
                    'access_level': share_token.access_level,
                    'purpose': validated_options.get('purpose', ''),
                    'recipient_email': validated_options.get('recipient_info', {}).get('email')
                },
                request=request
            )
            
            return {
                'success': True,
                'share_token_id': str(share_token.id),
                'token': token,
                'share_url': share_url,
                'expires_at': expiry_date.isoformat(),
                'access_level': share_token.access_level,
                'max_access_count': share_token.max_access_count,
                'created_at': share_token.created_at.isoformat()
            }
            
        except ClinicalRecord.DoesNotExist:
            raise ValueError("Clinical record not found")
        except Exception as e:
            self.logger.error(f"Error creating share token: {e}")
            raise
    
    def access_shared_record(self, token: str, request=None) -> Dict[str, Any]:
        """
        Access a shared clinical record using a share token.
        
        Args:
            token: Share token
            request: HTTP request object for validation and logging
            
        Returns:
            Dict containing record data and access information
        """
        try:
            # Get share token
            share_token = ShareToken.objects.select_related(
                'clinical_record', 'clinical_record__patient', 'clinical_record__clinic'
            ).get(token=token, is_active=True)
            
            # Validate token access
            validation_result = self._validate_token_access(share_token, request)
            if not validation_result['valid']:
                raise PermissionError(validation_result['reason'])
            
            # Increment access count
            share_token.access_count += 1
            share_token.last_accessed_at = timezone.now()
            share_token.last_accessed_ip = request.META.get('REMOTE_ADDR') if request else None
            share_token.save(update_fields=['access_count', 'last_accessed_at', 'last_accessed_ip'])
            
            # Get record data based on access level
            record_data = self._get_shared_record_data(share_token)
            
            # Log access
            audit_service.log_clinical_action(
                action='SHARED_RECORD_ACCESSED',
                user=None,  # External access
                resource_type='CLINICAL_RECORD',
                resource_id=str(share_token.clinical_record.id),
                clinic=share_token.clinic,
                patient_id=str(share_token.clinical_record.patient.id),
                details={
                    'share_token_id': str(share_token.id),
                    'access_count': share_token.access_count,
                    'access_ip': request.META.get('REMOTE_ADDR') if request else None,
                    'user_agent': request.META.get('HTTP_USER_AGENT') if request else None
                },
                request=request
            )
            
            return {
                'success': True,
                'record_data': record_data,
                'share_info': {
                    'access_level': share_token.access_level,
                    'expires_at': share_token.expires_at.isoformat(),
                    'access_count': share_token.access_count,
                    'max_access_count': share_token.max_access_count,
                    'purpose': share_token.share_metadata.get('purpose', ''),
                    'restrictions': share_token.share_metadata.get('restrictions', {})
                }
            }
            
        except ShareToken.DoesNotExist:
            raise ValueError("Invalid or expired share token")
        except Exception as e:
            self.logger.error(f"Error accessing shared record: {e}")
            raise
    
    def revoke_share_token(self, token_id: str, user: User, reason: str = None,
                          request=None) -> Dict[str, Any]:
        """
        Revoke a share token.
        
        Args:
            token_id: ID of the share token to revoke
            user: User revoking the share
            reason: Reason for revocation
            request: HTTP request object for audit logging
            
        Returns:
            Dict containing revocation result
        """
        try:
            # Get share token
            share_token = ShareToken.objects.select_related(
                'clinical_record', 'clinical_record__clinic'
            ).get(id=token_id)
            
            # Check permissions
            has_access, access_reason = access_control_service.check_record_access(
                user=user,
                record=share_token.clinical_record,
                action='share',
                request=request
            )
            
            if not has_access:
                raise PermissionError(f"Cannot revoke share: {access_reason}")
            
            # Revoke token
            share_token.is_active = False
            share_token.revoked_at = timezone.now()
            share_token.revoked_by = user
            share_token.revocation_reason = reason or "Manually revoked"
            share_token.save(update_fields=[
                'is_active', 'revoked_at', 'revoked_by', 'revocation_reason'
            ])
            
            # Log revocation
            audit_service.log_clinical_action(
                action='SHARE_TOKEN_REVOKED',
                user=user,
                resource_type='CLINICAL_RECORD',
                resource_id=str(share_token.clinical_record.id),
                clinic=share_token.clinic,
                patient_id=str(share_token.clinical_record.patient.id),
                details={
                    'share_token_id': str(share_token.id),
                    'revocation_reason': reason,
                    'access_count_at_revocation': share_token.access_count
                },
                request=request
            )
            
            return {
                'success': True,
                'message': 'Share token revoked successfully',
                'revoked_at': share_token.revoked_at.isoformat()
            }
            
        except ShareToken.DoesNotExist:
            raise ValueError("Share token not found")
        except Exception as e:
            self.logger.error(f"Error revoking share token: {e}")
            raise
    
    def get_share_tokens(self, record_id: str = None, user: User = None,
                        clinic: Clinic = None, active_only: bool = True) -> List[Dict[str, Any]]:
        """
        Get share tokens for records.
        
        Args:
            record_id: Optional specific record ID
            user: User requesting the tokens
            clinic: Optional clinic filter
            active_only: Whether to return only active tokens
            
        Returns:
            List of share token information
        """
        try:
            # Build query
            query = ShareToken.objects.select_related(
                'clinical_record', 'clinical_record__patient', 'created_by', 'revoked_by'
            )
            
            if record_id:
                query = query.filter(clinical_record_id=record_id)
            
            if clinic:
                query = query.filter(clinic=clinic)
            
            if active_only:
                query = query.filter(is_active=True, expires_at__gt=timezone.now())
            
            # Apply user-based filtering if needed
            if user and not user.is_superuser:
                query = query.filter(clinic=user.clinic)
            
            tokens = []
            for token in query.order_by('-created_at'):
                # Check if user has access to this token's record
                if user:
                    has_access, _ = access_control_service.check_record_access(
                        user=user,
                        record=token.clinical_record,
                        action='view'
                    )
                    if not has_access:
                        continue
                
                tokens.append({
                    'id': str(token.id),
                    'token': token.token[:8] + '...',  # Partial token for security
                    'record_id': str(token.clinical_record.id),
                    'record_title': token.clinical_record.title,
                    'patient_name': token.clinical_record.patient.get_full_name(),
                    'created_by': token.created_by.get_full_name(),
                    'created_at': token.created_at.isoformat(),
                    'expires_at': token.expires_at.isoformat(),
                    'access_level': token.access_level,
                    'access_count': token.access_count,
                    'max_access_count': token.max_access_count,
                    'is_active': token.is_active,
                    'last_accessed_at': token.last_accessed_at.isoformat() if token.last_accessed_at else None,
                    'purpose': token.share_metadata.get('purpose', ''),
                    'recipient_info': token.share_metadata.get('recipient_info', {}),
                    'revoked_at': token.revoked_at.isoformat() if token.revoked_at else None,
                    'revoked_by': token.revoked_by.get_full_name() if token.revoked_by else None,
                    'revocation_reason': token.revocation_reason
                })
            
            return tokens
            
        except Exception as e:
            self.logger.error(f"Error getting share tokens: {e}")
            raise
    
    def get_share_audit_trail(self, token_id: str, user: User) -> List[Dict[str, Any]]:
        """
        Get audit trail for a share token.
        
        Args:
            token_id: ID of the share token
            user: User requesting the audit trail
            
        Returns:
            List of audit events
        """
        try:
            # Get share token
            share_token = ShareToken.objects.select_related(
                'clinical_record', 'clinical_record__clinic'
            ).get(id=token_id)
            
            # Check permissions
            has_access, access_reason = access_control_service.check_record_access(
                user=user,
                record=share_token.clinical_record,
                action='view'
            )
            
            if not has_access:
                raise PermissionError(f"Cannot view audit trail: {access_reason}")
            
            # Get audit events related to this share token
            audit_events = audit_service.get_audit_events(
                resource_type='CLINICAL_RECORD',
                resource_id=str(share_token.clinical_record.id),
                clinic=share_token.clinic,
                filters={
                    'share_token_id': str(share_token.id)
                }
            )
            
            return audit_events
            
        except ShareToken.DoesNotExist:
            raise ValueError("Share token not found")
        except Exception as e:
            self.logger.error(f"Error getting share audit trail: {e}")
            raise
    
    def _validate_share_options(self, options: Dict[str, Any], 
                              record: ClinicalRecord) -> Dict[str, Any]:
        """Validate and normalize share options."""
        validated = {}
        
        # Validate expiry days
        expiry_days = options.get('expiry_days', self.default_expiry_days)
        if expiry_days > self.max_expiry_days:
            raise ValueError(f"Expiry days cannot exceed {self.max_expiry_days}")
        validated['expiry_days'] = expiry_days
        
        # Validate access count
        max_access = options.get('max_access_count', self.max_access_count)
        if max_access > self.max_access_count:
            raise ValueError(f"Max access count cannot exceed {self.max_access_count}")
        validated['max_access_count'] = max_access
        
        # Validate access level
        access_level = options.get('access_level', 'VIEW')
        if access_level not in ['VIEW', 'DOWNLOAD', 'FULL']:
            raise ValueError("Invalid access level")
        validated['access_level'] = access_level
        
        # Validate IP restrictions
        allowed_ips = options.get('allowed_ips', [])
        if allowed_ips and not self.enable_ip_restrictions:
            raise ValueError("IP restrictions are not enabled")
        validated['allowed_ips'] = allowed_ips
        
        # Validate recipient info
        recipient_info = options.get('recipient_info', {})
        if recipient_info.get('email'):
            # Basic email validation could be added here
            pass
        validated['recipient_info'] = recipient_info
        
        # Other validations
        validated['purpose'] = options.get('purpose', '')
        validated['require_authentication'] = options.get('require_authentication', False)
        validated['patient_consent_confirmed'] = options.get('patient_consent_confirmed', False)
        validated['send_notification'] = options.get('send_notification', False)
        validated['restrictions'] = options.get('restrictions', {})
        
        return validated
    
    def _generate_secure_token(self) -> str:
        """Generate a cryptographically secure token."""
        # Generate 32 bytes of random data
        random_bytes = secrets.token_bytes(32)
        
        # Create a hash with additional entropy
        hasher = hashlib.sha256()
        hasher.update(random_bytes)
        hasher.update(str(timezone.now().timestamp()).encode())
        hasher.update(secrets.token_bytes(16))
        
        return hasher.hexdigest()
    
    def _calculate_expiry_date(self, expiry_days: int) -> datetime:
        """Calculate expiry date from days."""
        return timezone.now() + timedelta(days=expiry_days)
    
    def _generate_share_url(self, token: str) -> str:
        """Generate the full share URL."""
        base_url = getattr(settings, 'BASE_URL', 'http://localhost:8000')
        share_path = reverse('clinical_records:shared_record_access', kwargs={'token': token})
        return urljoin(base_url, share_path)
    
    def _validate_token_access(self, share_token: ShareToken, request=None) -> Dict[str, Any]:
        """Validate if a token can be accessed."""
        # Check if token is active
        if not share_token.is_active:
            return {'valid': False, 'reason': 'Share token has been revoked'}
        
        # Check expiry
        if share_token.expires_at <= timezone.now():
            return {'valid': False, 'reason': 'Share token has expired'}
        
        # Check access count
        if share_token.access_count >= share_token.max_access_count:
            return {'valid': False, 'reason': 'Maximum access count reached'}
        
        # Check IP restrictions
        if request and share_token.allowed_ip_addresses:
            client_ip = request.META.get('REMOTE_ADDR')
            if client_ip not in share_token.allowed_ip_addresses:
                return {'valid': False, 'reason': 'Access denied from this IP address'}
        
        return {'valid': True, 'reason': 'Access granted'}
    
    def _get_shared_record_data(self, share_token: ShareToken) -> Dict[str, Any]:
        """Get record data based on share token access level."""
        record = share_token.clinical_record
        
        # Base record data
        record_data = {
            'id': str(record.id),
            'title': record.title,
            'record_type': record.record_type,
            'created_at': record.created_at.isoformat(),
            'patient': {
                'name': record.patient.get_full_name(),
                'date_of_birth': record.patient.date_of_birth.isoformat() if record.patient.date_of_birth else None
            },
            'clinic': {
                'name': record.clinic.name,
                'address': record.clinic.address
            }
        }
        
        # Add documents based on access level
        if share_token.access_level in ['VIEW', 'DOWNLOAD', 'FULL']:
            documents = []
            for doc in record.documents.filter(processing_status='COMPLETED'):
                doc_data = {
                    'id': str(doc.id),
                    'filename': doc.original_filename,
                    'content_type': doc.content_type,
                    'file_size': doc.file_size,
                    'created_at': doc.created_at.isoformat()
                }
                
                # Add view URL
                if share_token.access_level in ['VIEW', 'DOWNLOAD', 'FULL']:
                    doc_data['view_url'] = reverse(
                        'clinical_records:shared_document_view',
                        kwargs={'token': share_token.token, 'document_id': doc.id}
                    )
                
                # Add download URL
                if share_token.access_level in ['DOWNLOAD', 'FULL']:
                    doc_data['download_url'] = reverse(
                        'clinical_records:shared_document_download',
                        kwargs={'token': share_token.token, 'document_id': doc.id}
                    )
                
                documents.append(doc_data)
            
            record_data['documents'] = documents
        
        # Add additional data for FULL access
        if share_token.access_level == 'FULL':
            record_data['description'] = record.description
            record_data['created_by'] = record.created_by.get_full_name()
            
            # Add structured data if available
            structured_data = {}
            for doc in record.documents.filter(processing_status='COMPLETED'):
                if doc.structured_data:
                    structured_data[str(doc.id)] = doc.structured_data
            
            if structured_data:
                record_data['structured_data'] = structured_data
        
        return record_data
    
    def _send_share_notification(self, share_token: ShareToken, options: Dict[str, Any],
                               share_url: str) -> None:
        """Send notification email about the shared record."""
        try:
            recipient_info = options.get('recipient_info', {})
            recipient_email = recipient_info.get('email')
            
            if not recipient_email:
                return
            
            # Prepare email context
            context = {
                'share_token': share_token,
                'share_url': share_url,
                'record': share_token.clinical_record,
                'patient': share_token.clinical_record.patient,
                'clinic': share_token.clinic,
                'sender': share_token.created_by,
                'purpose': options.get('purpose', ''),
                'expires_at': share_token.expires_at,
                'recipient_name': recipient_info.get('name', 'Recipient')
            }
            
            # Render email content
            subject = f"Shared Medical Record: {share_token.clinical_record.title}"
            html_content = render_to_string('clinical_records/emails/share_notification.html', context)
            text_content = render_to_string('clinical_records/emails/share_notification.txt', context)
            
            # Send email
            send_mail(
                subject=subject,
                message=text_content,
                html_message=html_content,
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[recipient_email],
                fail_silently=False
            )
            
            self.logger.info(f"Share notification sent to {recipient_email}")
            
        except Exception as e:
            self.logger.error(f"Error sending share notification: {e}")
            # Don't raise exception as this is not critical


# Global secure sharing service instance
secure_sharing_service = SecureSharingService()