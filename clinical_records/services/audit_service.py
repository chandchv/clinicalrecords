"""
Comprehensive audit logging service for clinical records.

This service extends the existing AuditLog model to provide detailed
audit trails for clinical record operations, document access, and
compliance reporting.
"""

import json
import logging
from typing import Dict, Any, Optional, List
from datetime import datetime, timedelta
from django.contrib.auth import get_user_model
from django.utils import timezone
from django.db.models import Q, Count
from django.http import HttpRequest

# from users.models import AuditLog, Clinic  # External dependency removed
from ..models import ClinicalRecord, ClinicalDocument, ShareToken, ManualReview

User = get_user_model()
logger = logging.getLogger(__name__)


class ClinicalAuditService:
    """Service for comprehensive clinical records audit logging."""
    
    # Clinical records specific action types
    CLINICAL_ACTIONS = {
        # Record operations
        'CLINICAL_RECORD_CREATE': 'Clinical Record Created',
        'CLINICAL_RECORD_VIEW': 'Clinical Record Viewed',
        'CLINICAL_RECORD_UPDATE': 'Clinical Record Updated',
        'CLINICAL_RECORD_DELETE': 'Clinical Record Deleted',
        'CLINICAL_RECORD_ARCHIVE': 'Clinical Record Archived',
        'CLINICAL_RECORD_RESTORE': 'Clinical Record Restored',
        
        # Document operations
        'DOCUMENT_UPLOAD': 'Document Uploaded',
        'DOCUMENT_VIEW': 'Document Viewed',
        'DOCUMENT_DOWNLOAD': 'Document Downloaded',
        'DOCUMENT_UPDATE': 'Document Updated',
        'DOCUMENT_DELETE': 'Document Deleted',
        'DOCUMENT_PROCESS': 'Document Processed',
        'DOCUMENT_ENCRYPT': 'Document Encrypted',
        'DOCUMENT_DECRYPT': 'Document Decrypted',
        
        # Sharing operations
        'RECORD_SHARE_CREATE': 'Record Share Created',
        'RECORD_SHARE_ACCESS': 'Record Share Accessed',
        'RECORD_SHARE_REVOKE': 'Record Share Revoked',
        'RECORD_SHARE_EXPIRE': 'Record Share Expired',
        'EXTERNAL_ACCESS': 'External Access via Share',
        
        # Manual review operations
        'MANUAL_REVIEW_CREATE': 'Manual Review Created',
        'MANUAL_REVIEW_ASSIGN': 'Manual Review Assigned',
        'MANUAL_REVIEW_START': 'Manual Review Started',
        'MANUAL_REVIEW_COMPLETE': 'Manual Review Completed',
        'MANUAL_REVIEW_ESCALATE': 'Manual Review Escalated',
        
        # Relationship operations
        'RECORD_RELATIONSHIP_CREATE': 'Record Relationship Created',
        'RECORD_RELATIONSHIP_DELETE': 'Record Relationship Deleted',
        'RECORD_RELATIONSHIP_UPDATE': 'Record Relationship Updated',
        
        # Search and export operations
        'CLINICAL_SEARCH': 'Clinical Records Search',
        'CLINICAL_EXPORT': 'Clinical Records Export',
        'FHIR_EXPORT': 'FHIR Data Export',
        'BULK_OPERATION': 'Bulk Clinical Operation',
        
        # Security and compliance
        'UNAUTHORIZED_ACCESS_ATTEMPT': 'Unauthorized Access Attempt',
        'ENCRYPTION_KEY_ROTATION': 'Encryption Key Rotation',
        'INTEGRITY_VERIFICATION': 'File Integrity Verification',
        'COMPLIANCE_REPORT_GENERATE': 'Compliance Report Generated',
        'AUDIT_REPORT_GENERATE': 'Audit Report Generated',
        
        # System operations
        'WEBHOOK_DELIVERY': 'Webhook Delivered',
        'EMAIL_INGESTION': 'Email Ingestion',
        'SFTP_INGESTION': 'SFTP Ingestion',
        'BACKGROUND_TASK': 'Background Task Executed',
    }
    
    # Resource types for clinical records
    CLINICAL_RESOURCE_TYPES = {
        'CLINICAL_RECORD': 'Clinical Record',
        'CLINICAL_DOCUMENT': 'Clinical Document',
        'SHARE_TOKEN': 'Share Token',
        'MANUAL_REVIEW': 'Manual Review',
        'RECORD_RELATIONSHIP': 'Record Relationship',
        'WEBHOOK_CONFIG': 'Webhook Configuration',
        'ENCRYPTION_KEY': 'Encryption Key',
        'AUDIT_REPORT': 'Audit Report',
        'COMPLIANCE_REPORT': 'Compliance Report',
    }
    
    def __init__(self):
        self.logger = logging.getLogger(f"{__name__}.{self.__class__.__name__}")
    
    def log_clinical_action(self, action: str, user: Optional[User] = None,
                          resource_type: str = None, resource_id: str = None,
                          clinic: Optional[Clinic] = None, request: Optional[HttpRequest] = None,
                          details: Optional[Dict[str, Any]] = None,
                          patient_id: Optional[str] = None,
                          sensitive_data: bool = False) -> AuditLog:
        """
        Log a clinical records action.
        
        Args:
            action: Action type from CLINICAL_ACTIONS
            user: User performing the action
            resource_type: Type of resource from CLINICAL_RESOURCE_TYPES
            resource_id: ID of the affected resource
            clinic: Clinic context
            request: HTTP request object
            details: Additional details about the action
            patient_id: Patient ID if applicable
            sensitive_data: Whether sensitive data was accessed
            
        Returns:
            Created AuditLog instance
        """
        try:
            # Extract request information
            ip_address = None
            user_agent = None
            session_id = None
            
            if request:
                ip_address = self._get_client_ip(request)
                user_agent = request.META.get('HTTP_USER_AGENT', '')[:500]
                session_id = request.session.session_key
            
            # Prepare audit details
            audit_details = {
                'timestamp': timezone.now().isoformat(),
                'action_description': self.CLINICAL_ACTIONS.get(action, action),
                'resource_type_description': self.CLINICAL_RESOURCE_TYPES.get(resource_type, resource_type),
            }
            
            if patient_id:
                audit_details['patient_id'] = patient_id
            
            if sensitive_data:
                audit_details['sensitive_data_accessed'] = True
            
            if details:
                audit_details.update(details)
            
            # Create audit log entry
            audit_log = AuditLog.objects.create(
                user=user,
                action=action,
                resource_type=resource_type or 'CLINICAL_RECORD',
                resource_id=str(resource_id) if resource_id else None,
                ip_address=ip_address,
                user_agent=user_agent,
                details=audit_details,
                clinic=clinic,
                timestamp=timezone.now(),
                session_id=session_id
            )
            
            # Log to application logger for real-time monitoring
            self.logger.info(
                f"Clinical audit: {action} by {user.username if user else 'System'} "
                f"on {resource_type}:{resource_id} from {ip_address}"
            )
            
            return audit_log
            
        except Exception as e:
            # Ensure audit logging failures don't break the application
            self.logger.error(f"Failed to create audit log: {str(e)}")
            # Create a minimal audit log entry
            try:
                return AuditLog.objects.create(
                    user=user,
                    action='AUDIT_LOG_ERROR',
                    resource_type='SYSTEM',
                    details={'error': str(e), 'original_action': action},
                    clinic=clinic,
                    timestamp=timezone.now()
                )
            except:
                # If even this fails, just log the error
                self.logger.critical(f"Critical audit logging failure: {str(e)}")
                return None
    
    def log_record_access(self, record: ClinicalRecord, user: User,
                         request: HttpRequest, access_type: str = 'VIEW') -> AuditLog:
        """Log access to a clinical record."""
        return self.log_clinical_action(
            action=f'CLINICAL_RECORD_{access_type}',
            user=user,
            resource_type='CLINICAL_RECORD',
            resource_id=str(record.id),
            clinic=record.clinic,
            request=request,
            patient_id=str(record.patient.id),
            sensitive_data=True,
            details={
                'record_title': record.title,
                'record_type': record.record_type,
                'patient_name': record.patient.get_full_name(),
                'access_type': access_type
            }
        )
    
    def log_document_access(self, document: ClinicalDocument, user: User,
                          request: HttpRequest, access_type: str = 'VIEW') -> AuditLog:
        """Log access to a clinical document."""
        return self.log_clinical_action(
            action=f'DOCUMENT_{access_type}',
            user=user,
            resource_type='CLINICAL_DOCUMENT',
            resource_id=str(document.id),
            clinic=document.clinical_record.clinic,
            request=request,
            patient_id=str(document.clinical_record.patient.id),
            sensitive_data=True,
            details={
                'document_filename': document.original_filename,
                'document_type': document.document_type,
                'record_title': document.clinical_record.title,
                'patient_name': document.clinical_record.patient.get_full_name(),
                'file_size': document.file_size,
                'is_encrypted': document.is_encrypted,
                'access_type': access_type
            }
        )
    
    def log_share_access(self, share_token: ShareToken, request: HttpRequest,
                        access_details: Dict[str, Any] = None) -> AuditLog:
        """Log external access via share token."""
        details = {
            'share_token': share_token.token[:8] + '...',  # Partial token for audit
            'shared_with': share_token.shared_with_email,
            'expires_at': share_token.expires_at.isoformat() if share_token.expires_at else None,
            'access_count': share_token.access_count,
            'record_title': share_token.clinical_record.title,
            'patient_name': share_token.clinical_record.patient.get_full_name(),
        }
        
        if access_details:
            details.update(access_details)
        
        return self.log_clinical_action(
            action='EXTERNAL_ACCESS',
            user=None,  # External access
            resource_type='SHARE_TOKEN',
            resource_id=str(share_token.id),
            clinic=share_token.clinical_record.clinic,
            request=request,
            patient_id=str(share_token.clinical_record.patient.id),
            sensitive_data=True,
            details=details
        )
    
    def log_manual_review_action(self, review: ManualReview, user: User,
                               action: str, request: HttpRequest = None,
                               details: Dict[str, Any] = None) -> AuditLog:
        """Log manual review actions."""
        audit_details = {
            'review_type': review.review_type,
            'status': review.status,
            'priority': review.priority,
            'confidence_score': review.confidence_score,
            'document_filename': review.clinical_document.original_filename,
            'record_title': review.clinical_document.clinical_record.title,
            'patient_name': review.clinical_document.clinical_record.patient.get_full_name(),
        }
        
        if details:
            audit_details.update(details)
        
        return self.log_clinical_action(
            action=f'MANUAL_REVIEW_{action}',
            user=user,
            resource_type='MANUAL_REVIEW',
            resource_id=str(review.id),
            clinic=review.clinic,
            request=request,
            patient_id=str(review.clinical_document.clinical_record.patient.id),
            sensitive_data=True,
            details=audit_details
        )
    
    def log_search_action(self, user: User, search_params: Dict[str, Any],
                         result_count: int, clinic: Clinic,
                         request: HttpRequest = None) -> AuditLog:
        """Log clinical records search actions."""
        return self.log_clinical_action(
            action='CLINICAL_SEARCH',
            user=user,
            resource_type='CLINICAL_RECORD',
            clinic=clinic,
            request=request,
            details={
                'search_parameters': search_params,
                'result_count': result_count,
                'search_timestamp': timezone.now().isoformat()
            }
        )
    
    def log_export_action(self, user: User, export_type: str, export_params: Dict[str, Any],
                         record_count: int, clinic: Clinic,
                         request: HttpRequest = None) -> AuditLog:
        """Log data export actions."""
        action = 'FHIR_EXPORT' if export_type == 'fhir' else 'CLINICAL_EXPORT'
        
        return self.log_clinical_action(
            action=action,
            user=user,
            resource_type='CLINICAL_RECORD',
            clinic=clinic,
            request=request,
            sensitive_data=True,
            details={
                'export_type': export_type,
                'export_parameters': export_params,
                'record_count': record_count,
                'export_timestamp': timezone.now().isoformat()
            }
        )
    
    def log_encryption_action(self, user: User, action: str, resource_id: str,
                            clinic: Clinic, details: Dict[str, Any] = None) -> AuditLog:
        """Log encryption-related actions."""
        return self.log_clinical_action(
            action=f'DOCUMENT_{action}',
            user=user,
            resource_type='CLINICAL_DOCUMENT',
            resource_id=resource_id,
            clinic=clinic,
            details=details or {}
        )
    
    def log_webhook_delivery(self, webhook_config_id: str, event_type: str,
                           delivery_status: str, clinic: Clinic,
                           details: Dict[str, Any] = None) -> AuditLog:
        """Log webhook delivery attempts."""
        return self.log_clinical_action(
            action='WEBHOOK_DELIVERY',
            user=None,  # System action
            resource_type='WEBHOOK_CONFIG',
            resource_id=webhook_config_id,
            clinic=clinic,
            details={
                'event_type': event_type,
                'delivery_status': delivery_status,
                'delivery_timestamp': timezone.now().isoformat(),
                **(details or {})
            }
        )
    
    def log_unauthorized_access(self, user: Optional[User], resource_type: str,
                              resource_id: str, clinic: Clinic,
                              request: HttpRequest, reason: str) -> AuditLog:
        """Log unauthorized access attempts."""
        return self.log_clinical_action(
            action='UNAUTHORIZED_ACCESS_ATTEMPT',
            user=user,
            resource_type=resource_type,
            resource_id=resource_id,
            clinic=clinic,
            request=request,
            details={
                'reason': reason,
                'attempted_resource': f"{resource_type}:{resource_id}",
                'timestamp': timezone.now().isoformat()
            }
        )
    
    def get_audit_trail(self, resource_type: str = None, resource_id: str = None,
                       clinic: Clinic = None, user: User = None,
                       start_date: datetime = None, end_date: datetime = None,
                       limit: int = 100) -> List[AuditLog]:
        """
        Retrieve audit trail with filtering options.
        
        Args:
            resource_type: Filter by resource type
            resource_id: Filter by specific resource ID
            clinic: Filter by clinic
            user: Filter by user
            start_date: Filter by start date
            end_date: Filter by end date
            limit: Maximum number of records to return
            
        Returns:
            List of AuditLog entries
        """
        queryset = AuditLog.objects.all()
        
        # Apply filters
        if resource_type:
            queryset = queryset.filter(resource_type=resource_type)
        
        if resource_id:
            queryset = queryset.filter(resource_id=resource_id)
        
        if clinic:
            queryset = queryset.filter(clinic=clinic)
        
        if user:
            queryset = queryset.filter(user=user)
        
        if start_date:
            queryset = queryset.filter(timestamp__gte=start_date)
        
        if end_date:
            queryset = queryset.filter(timestamp__lte=end_date)
        
        # Filter for clinical actions only
        clinical_actions = list(self.CLINICAL_ACTIONS.keys())
        queryset = queryset.filter(action__in=clinical_actions)
        
        return queryset.order_by('-timestamp')[:limit]
    
    def generate_compliance_report(self, clinic: Clinic, start_date: datetime,
                                 end_date: datetime) -> Dict[str, Any]:
        """
        Generate compliance report for a clinic.
        
        Args:
            clinic: Clinic to generate report for
            start_date: Report start date
            end_date: Report end date
            
        Returns:
            Dictionary containing compliance metrics
        """
        # Get audit logs for the period
        audit_logs = AuditLog.objects.filter(
            clinic=clinic,
            timestamp__gte=start_date,
            timestamp__lte=end_date,
            action__in=list(self.CLINICAL_ACTIONS.keys())
        )
        
        # Calculate metrics
        total_actions = audit_logs.count()
        unique_users = audit_logs.values('user').distinct().count()
        
        # Action breakdown
        action_counts = audit_logs.values('action').annotate(
            count=Count('id')
        ).order_by('-count')
        
        # Resource access breakdown
        resource_counts = audit_logs.values('resource_type').annotate(
            count=Count('id')
        ).order_by('-count')
        
        # Sensitive data access
        sensitive_access = audit_logs.filter(
            details__contains='sensitive_data_accessed'
        ).count()
        
        # External access via shares
        external_access = audit_logs.filter(
            action='EXTERNAL_ACCESS'
        ).count()
        
        # Unauthorized access attempts
        unauthorized_attempts = audit_logs.filter(
            action='UNAUTHORIZED_ACCESS_ATTEMPT'
        ).count()
        
        # Document operations
        document_operations = audit_logs.filter(
            resource_type='CLINICAL_DOCUMENT'
        ).count()
        
        return {
            'clinic_id': clinic.id,
            'clinic_name': clinic.name,
            'report_period': {
                'start_date': start_date.isoformat(),
                'end_date': end_date.isoformat()
            },
            'summary': {
                'total_actions': total_actions,
                'unique_users': unique_users,
                'sensitive_data_access_count': sensitive_access,
                'external_access_count': external_access,
                'unauthorized_attempts': unauthorized_attempts,
                'document_operations': document_operations
            },
            'action_breakdown': list(action_counts),
            'resource_breakdown': list(resource_counts),
            'compliance_indicators': {
                'audit_coverage': 'Complete' if total_actions > 0 else 'No Activity',
                'external_access_monitored': external_access > 0,
                'unauthorized_attempts_detected': unauthorized_attempts > 0,
                'document_access_tracked': document_operations > 0
            },
            'generated_at': timezone.now().isoformat()
        }
    
    def _get_client_ip(self, request: HttpRequest) -> str:
        """Extract client IP address from request."""
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            ip = x_forwarded_for.split(',')[0]
        else:
            ip = request.META.get('REMOTE_ADDR')
        return ip


# Global audit service instance
audit_service = ClinicalAuditService()