"""
Background tasks for access control operations using Django-Q.

This module provides background tasks for managing access control operations
such as role assignments, permission updates, emergency access processing,
and access control auditing.
"""

import logging
import time
from typing import Dict, Any, Optional, List
from datetime import datetime, timedelta

from django.conf import settings
from django.utils import timezone
from django.contrib.auth import get_user_model
from django_q.tasks import async_task, result
from django_q.models import Task

from users.models import Clinic, Patient
from ..models import ClinicalRecord, ClinicalDocument
from ..models.access_models import (
    ClinicalRole, UserClinicalRole, PatientConsent, 
    EmergencyAccess, DocumentAccessPermission
)
from ..services.access_control_service import access_control_service
from ..services.audit_service import audit_service

User = get_user_model()
logger = logging.getLogger(__name__)


class AccessControlTaskProcessor:
    """Main class for handling access control background tasks."""
    
    def __init__(self):
        self.logger = logging.getLogger(f"{__name__}.{self.__class__.__name__}")
        self.config = getattr(settings, 'CLINICAL_RECORDS_ACCESS_CONTROL', {})
    
    def process_role_assignment(self, assignment_id: str, action: str = 'assign') -> Dict[str, Any]:
        """
        Process role assignment or revocation.
        
        Args:
            assignment_id: ID of UserClinicalRole
            action: 'assign' or 'revoke'
            
        Returns:
            Dict containing processing results
        """
        start_time = time.time()
        result = {
            'assignment_id': assignment_id,
            'action': action,
            'status': 'started',
            'start_time': start_time
        }
        
        try:
            assignment = UserClinicalRole.objects.get(id=assignment_id)
            
            if action == 'assign':
                assignment.is_active = True
                assignment.activated_at = timezone.now()
                status_message = f"Role {assignment.role.name} assigned to {assignment.user.username}"
            elif action == 'revoke':
                assignment.is_active = False
                assignment.deactivated_at = timezone.now()
                status_message = f"Role {assignment.role.name} revoked from {assignment.user.username}"
            else:
                raise ValueError(f"Invalid action: {action}")
            
            assignment.save()
            
            # Log the role change
            audit_service.log_clinical_action(
                action=f'ROLE_{action.upper()}',
                user=assignment.assigned_by,
                resource_type='USER_CLINICAL_ROLE',
                resource_id=str(assignment.id),
                clinic=assignment.clinic,
                details={
                    'target_user': assignment.user.username,
                    'role_name': assignment.role.name,
                    'role_type': assignment.role.role_type,
                    'reason': assignment.assignment_reason
                }
            )
            
            result.update({
                'status': 'completed',
                'message': status_message,
                'processing_time': time.time() - start_time
            })
            
            self.logger.info(status_message)
            return result
            
        except UserClinicalRole.DoesNotExist:
            error_msg = f"Role assignment {assignment_id} not found"
            self.logger.error(error_msg)
            result.update({
                'status': 'failed',
                'error': error_msg,
                'processing_time': time.time() - start_time
            })
            return result
            
        except Exception as e:
            error_msg = f"Role {action} failed: {str(e)}"
            self.logger.error(f"Error processing role assignment {assignment_id}: {e}", exc_info=True)
            result.update({
                'status': 'failed',
                'error': error_msg,
                'processing_time': time.time() - start_time
            })
            return result    de
f process_emergency_access_request(self, emergency_access_id: str) -> Dict[str, Any]:
        """
        Process emergency access request and notifications.
        
        Args:
            emergency_access_id: ID of EmergencyAccess record
            
        Returns:
            Dict containing processing results
        """
        start_time = time.time()
        result = {
            'emergency_access_id': emergency_access_id,
            'status': 'started',
            'start_time': start_time
        }
        
        try:
            emergency_access = EmergencyAccess.objects.get(id=emergency_access_id)
            
            # Validate emergency access request
            if emergency_access.status != 'active':
                raise ValueError(f"Emergency access is not active: {emergency_access.status}")
            
            # Check if access has expired
            if emergency_access.expires_at <= timezone.now():
                emergency_access.status = 'expired'
                emergency_access.save()
                raise ValueError("Emergency access has expired")
            
            # Log emergency access usage
            audit_service.log_clinical_action(
                action='EMERGENCY_ACCESS_USED',
                user=emergency_access.user,
                resource_type='EMERGENCY_ACCESS',
                resource_id=str(emergency_access.id),
                clinic=emergency_access.clinic,
                patient_id=str(emergency_access.patient.id),
                sensitive_data=True,
                details={
                    'access_type': emergency_access.access_type,
                    'emergency_reason': emergency_access.emergency_reason[:100],
                    'medical_justification': emergency_access.medical_justification[:100],
                    'expires_at': emergency_access.expires_at.isoformat()
                }
            )
            
            # Send notifications to administrators
            self._send_emergency_access_notifications(emergency_access)
            
            result.update({
                'status': 'completed',
                'message': f"Emergency access processed for {emergency_access.user.username}",
                'processing_time': time.time() - start_time,
                'access_type': emergency_access.access_type,
                'expires_at': emergency_access.expires_at.isoformat()
            })
            
            return result
            
        except EmergencyAccess.DoesNotExist:
            error_msg = f"Emergency access {emergency_access_id} not found"
            self.logger.error(error_msg)
            result.update({
                'status': 'failed',
                'error': error_msg,
                'processing_time': time.time() - start_time
            })
            return result
            
        except Exception as e:
            error_msg = f"Emergency access processing failed: {str(e)}"
            self.logger.error(f"Error processing emergency access {emergency_access_id}: {e}", exc_info=True)
            result.update({
                'status': 'failed',
                'error': error_msg,
                'processing_time': time.time() - start_time
            })
            return result
    
    def process_consent_update(self, consent_id: str, action: str = 'grant') -> Dict[str, Any]:
        """
        Process patient consent updates.
        
        Args:
            consent_id: ID of PatientConsent record
            action: 'grant' or 'revoke'
            
        Returns:
            Dict containing processing results
        """
        start_time = time.time()
        result = {
            'consent_id': consent_id,
            'action': action,
            'status': 'started',
            'start_time': start_time
        }
        
        try:
            consent = PatientConsent.objects.get(id=consent_id)
            
            if action == 'grant':
                consent.status = 'granted'
                consent.granted_at = timezone.now()
                status_message = f"Consent granted for {consent.patient.get_full_name()}: {consent.consent_type}"
            elif action == 'revoke':
                consent.status = 'revoked'
                consent.revoked_at = timezone.now()
                status_message = f"Consent revoked for {consent.patient.get_full_name()}: {consent.consent_type}"
            else:
                raise ValueError(f"Invalid action: {action}")
            
            consent.save()
            
            # Log consent change
            audit_service.log_clinical_action(
                action=f'CONSENT_{action.upper()}',
                user=consent.granted_by,
                resource_type='PATIENT_CONSENT',
                resource_id=str(consent.id),
                clinic=consent.clinic,
                patient_id=str(consent.patient.id),
                details={
                    'consent_type': consent.consent_type,
                    'purpose': consent.purpose,
                    'valid_until': consent.valid_until.isoformat() if consent.valid_until else None
                }
            )
            
            result.update({
                'status': 'completed',
                'message': status_message,
                'processing_time': time.time() - start_time
            })
            
            return result
            
        except PatientConsent.DoesNotExist:
            error_msg = f"Patient consent {consent_id} not found"
            self.logger.error(error_msg)
            result.update({
                'status': 'failed',
                'error': error_msg,
                'processing_time': time.time() - start_time
            })
            return result
            
        except Exception as e:
            error_msg = f"Consent {action} failed: {str(e)}"
            self.logger.error(f"Error processing consent {consent_id}: {e}", exc_info=True)
            result.update({
                'status': 'failed',
                'error': error_msg,
                'processing_time': time.time() - start_time
            })
            return result 
   def cleanup_expired_access(self, clinic_id: Optional[str] = None) -> Dict[str, Any]:
        """
        Clean up expired access tokens, emergency access, and permissions.
        
        Args:
            clinic_id: Optional clinic ID to limit cleanup scope
            
        Returns:
            Dict containing cleanup results
        """
        start_time = time.time()
        result = {
            'status': 'started',
            'start_time': start_time,
            'clinic_id': clinic_id,
            'cleanup_counts': {}
        }
        
        try:
            now = timezone.now()
            
            # Build base queries
            emergency_query = EmergencyAccess.objects.filter(
                expires_at__lt=now,
                status='active'
            )
            
            consent_query = PatientConsent.objects.filter(
                valid_until__lt=now,
                status='granted'
            )
            
            role_query = UserClinicalRole.objects.filter(
                valid_until__lt=now,
                is_active=True
            )
            
            doc_permission_query = DocumentAccessPermission.objects.filter(
                valid_until__lt=now,
                is_active=True
            )
            
            # Filter by clinic if specified
            if clinic_id:
                clinic = Clinic.objects.get(id=clinic_id)
                emergency_query = emergency_query.filter(clinic=clinic)
                consent_query = consent_query.filter(clinic=clinic)
                role_query = role_query.filter(clinic=clinic)
                doc_permission_query = doc_permission_query.filter(
                    document__clinical_record__clinic=clinic
                )
            
            # Count items to be cleaned up
            emergency_count = emergency_query.count()
            consent_count = consent_query.count()
            role_count = role_query.count()
            doc_permission_count = doc_permission_query.count()
            
            # Update expired emergency access
            emergency_query.update(status='expired')
            
            # Update expired consents
            consent_query.update(status='expired')
            
            # Deactivate expired role assignments
            role_query.update(is_active=False, deactivated_at=now)
            
            # Deactivate expired document permissions
            doc_permission_query.update(is_active=False)
            
            result['cleanup_counts'] = {
                'emergency_access': emergency_count,
                'patient_consents': consent_count,
                'role_assignments': role_count,
                'document_permissions': doc_permission_count
            }
            
            # Log cleanup activity
            total_cleaned = sum(result['cleanup_counts'].values())
            if total_cleaned > 0:
                audit_service.log_clinical_action(
                    action='ACCESS_CLEANUP',
                    user=None,  # System action
                    resource_type='ACCESS_CONTROL',
                    resource_id='cleanup_task',
                    clinic=clinic if clinic_id else None,
                    details={
                        'cleanup_counts': result['cleanup_counts'],
                        'total_items_cleaned': total_cleaned
                    }
                )
            
            result.update({
                'status': 'completed',
                'message': f"Cleaned up {total_cleaned} expired access items",
                'processing_time': time.time() - start_time
            })
            
            self.logger.info(f"Access cleanup completed: {result['cleanup_counts']}")
            return result
            
        except Exception as e:
            error_msg = f"Access cleanup failed: {str(e)}"
            self.logger.error(f"Error during access cleanup: {e}", exc_info=True)
            result.update({
                'status': 'failed',
                'error': error_msg,
                'processing_time': time.time() - start_time
            })
            return result
    
    def generate_access_report(self, clinic_id: str, report_type: str = 'summary') -> Dict[str, Any]:
        """
        Generate access control reports for compliance and auditing.
        
        Args:
            clinic_id: Clinic ID for the report
            report_type: Type of report ('summary', 'detailed', 'emergency')
            
        Returns:
            Dict containing report data
        """
        start_time = time.time()
        result = {
            'clinic_id': clinic_id,
            'report_type': report_type,
            'status': 'started',
            'start_time': start_time
        }
        
        try:
            clinic = Clinic.objects.get(id=clinic_id)
            now = timezone.now()
            
            # Base report data
            report_data = {
                'clinic_name': clinic.name,
                'generated_at': now.isoformat(),
                'report_type': report_type
            }
            
            if report_type == 'summary':
                # Summary statistics
                report_data.update({
                    'active_roles': ClinicalRole.objects.filter(clinic=clinic, is_active=True).count(),
                    'active_role_assignments': UserClinicalRole.objects.filter(
                        clinic=clinic, is_active=True
                    ).count(),
                    'active_emergency_access': EmergencyAccess.objects.filter(
                        clinic=clinic, status='active', expires_at__gt=now
                    ).count(),
                    'granted_consents': PatientConsent.objects.filter(
                        clinic=clinic, status='granted'
                    ).count(),
                    'active_document_permissions': DocumentAccessPermission.objects.filter(
                        document__clinical_record__clinic=clinic, is_active=True
                    ).count()
                })
                
            elif report_type == 'detailed':
                # Detailed role and permission information
                roles = ClinicalRole.objects.filter(clinic=clinic, is_active=True)
                role_data = []
                
                for role in roles:
                    assignments = UserClinicalRole.objects.filter(
                        role=role, is_active=True
                    ).select_related('user')
                    
                    role_data.append({
                        'role_name': role.name,
                        'role_type': role.role_type,
                        'active_assignments': assignments.count(),
                        'users': [assignment.user.username for assignment in assignments],
                        'permissions': {
                            'can_view_all_patients': role.can_view_all_patients,
                            'can_edit_all_records': role.can_edit_all_records,
                            'can_delete_records': role.can_delete_records,
                            'can_share_records': role.can_share_records,
                            'can_export_data': role.can_export_data
                        }
                    })
                
                report_data['roles'] = role_data
                
            elif report_type == 'emergency':
                # Emergency access report
                emergency_accesses = EmergencyAccess.objects.filter(
                    clinic=clinic
                ).select_related('user', 'patient').order_by('-created_at')[:50]
                
                emergency_data = []
                for access in emergency_accesses:
                    emergency_data.append({
                        'user': access.user.username,
                        'patient': access.patient.get_full_name(),
                        'access_type': access.access_type,
                        'status': access.status,
                        'created_at': access.created_at.isoformat(),
                        'expires_at': access.expires_at.isoformat(),
                        'emergency_reason': access.emergency_reason[:100],
                        'ip_address': access.ip_address
                    })
                
                report_data['emergency_accesses'] = emergency_data
            
            result.update({
                'status': 'completed',
                'report_data': report_data,
                'processing_time': time.time() - start_time
            })
            
            # Log report generation
            audit_service.log_clinical_action(
                action='ACCESS_REPORT_GENERATED',
                user=None,  # System action
                resource_type='ACCESS_REPORT',
                resource_id=f"{report_type}_{clinic_id}",
                clinic=clinic,
                details={
                    'report_type': report_type,
                    'data_points': len(report_data)
                }
            )
            
            return result
            
        except Clinic.DoesNotExist:
            error_msg = f"Clinic {clinic_id} not found"
            self.logger.error(error_msg)
            result.update({
                'status': 'failed',
                'error': error_msg,
                'processing_time': time.time() - start_time
            })
            return result
            
        except Exception as e:
            error_msg = f"Report generation failed: {str(e)}"
            self.logger.error(f"Error generating access report: {e}", exc_info=True)
            result.update({
                'status': 'failed',
                'error': error_msg,
                'processing_time': time.time() - start_time
            })
            return result    def _
send_emergency_access_notifications(self, emergency_access: EmergencyAccess):
        """Send notifications for emergency access usage."""
        try:
            # Get administrators for the clinic
            admin_roles = ClinicalRole.objects.filter(
                clinic=emergency_access.clinic,
                role_type='admin',
                is_active=True
            )
            
            admin_assignments = UserClinicalRole.objects.filter(
                role__in=admin_roles,
                is_active=True
            ).select_related('user')
            
            notification_data = {
                'type': 'emergency_access_used',
                'user': emergency_access.user.username,
                'patient': emergency_access.patient.get_full_name(),
                'access_type': emergency_access.access_type,
                'emergency_reason': emergency_access.emergency_reason,
                'timestamp': emergency_access.created_at.isoformat(),
                'expires_at': emergency_access.expires_at.isoformat()
            }
            
            # Queue notification tasks for each admin
            for assignment in admin_assignments:
                async_task(
                    'clinical_records.tasks.send_access_notification',
                    assignment.user.id,
                    notification_data,
                    task_name=f'emergency_notification_{assignment.user.id}_{emergency_access.id}'
                )
            
            self.logger.info(f"Queued emergency access notifications for {admin_assignments.count()} administrators")
            
        except Exception as e:
            self.logger.error(f"Failed to send emergency access notifications: {e}")


# Task functions for Django-Q
def process_role_assignment(assignment_id: str, action: str = 'assign') -> Dict[str, Any]:
    """
    Django-Q task function for processing role assignments.
    
    Args:
        assignment_id: ID of UserClinicalRole
        action: 'assign' or 'revoke'
        
    Returns:
        Dict containing processing results
    """
    processor = AccessControlTaskProcessor()
    return processor.process_role_assignment(assignment_id, action)


def process_emergency_access_request(emergency_access_id: str) -> Dict[str, Any]:
    """
    Django-Q task function for processing emergency access requests.
    
    Args:
        emergency_access_id: ID of EmergencyAccess record
        
    Returns:
        Dict containing processing results
    """
    processor = AccessControlTaskProcessor()
    return processor.process_emergency_access_request(emergency_access_id)


def process_consent_update(consent_id: str, action: str = 'grant') -> Dict[str, Any]:
    """
    Django-Q task function for processing consent updates.
    
    Args:
        consent_id: ID of PatientConsent record
        action: 'grant' or 'revoke'
        
    Returns:
        Dict containing processing results
    """
    processor = AccessControlTaskProcessor()
    return processor.process_consent_update(consent_id, action)


def cleanup_expired_access(clinic_id: Optional[str] = None) -> Dict[str, Any]:
    """
    Django-Q task function for cleaning up expired access.
    
    Args:
        clinic_id: Optional clinic ID to limit cleanup scope
        
    Returns:
        Dict containing cleanup results
    """
    processor = AccessControlTaskProcessor()
    return processor.cleanup_expired_access(clinic_id)


def generate_access_report(clinic_id: str, report_type: str = 'summary') -> Dict[str, Any]:
    """
    Django-Q task function for generating access control reports.
    
    Args:
        clinic_id: Clinic ID for the report
        report_type: Type of report ('summary', 'detailed', 'emergency')
        
    Returns:
        Dict containing report data
    """
    processor = AccessControlTaskProcessor()
    return processor.generate_access_report(clinic_id, report_type)


def send_access_notification(user_id: str, notification_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Django-Q task function for sending access control notifications.
    
    Args:
        user_id: ID of user to notify
        notification_data: Notification content
        
    Returns:
        Dict containing notification results
    """
    try:
        user = User.objects.get(id=user_id)
        
        # Here you would integrate with your notification system
        # For now, we'll just log the notification
        logger.info(f"Access notification for {user.username}: {notification_data['type']}")
        
        # You could integrate with:
        # - Email service
        # - Push notifications
        # - In-app notifications
        # - SMS service
        
        return {
            'status': 'completed',
            'user_id': user_id,
            'notification_type': notification_data['type'],
            'message': f"Notification sent to {user.username}"
        }
        
    except User.DoesNotExist:
        error_msg = f"User {user_id} not found"
        logger.error(error_msg)
        return {
            'status': 'failed',
            'error': error_msg
        }
    except Exception as e:
        error_msg = f"Notification failed: {str(e)}"
        logger.error(f"Error sending notification to user {user_id}: {e}")
        return {
            'status': 'failed',
            'error': error_msg
        }


def batch_role_assignment(assignments_data: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Process multiple role assignments in batch.
    
    Args:
        assignments_data: List of assignment data dicts
        
    Returns:
        Dict containing batch processing results
    """
    results = {
        'total_assignments': len(assignments_data),
        'queued_tasks': [],
        'failed_to_queue': [],
        'batch_id': f"batch_role_{int(time.time())}"
    }
    
    for assignment_data in assignments_data:
        try:
            task_id = async_task(
                'clinical_records.tasks.process_role_assignment',
                assignment_data['assignment_id'],
                assignment_data.get('action', 'assign'),
                task_name=f"role_assignment_{assignment_data['assignment_id']}",
                group=results['batch_id']
            )
            
            results['queued_tasks'].append({
                'assignment_id': assignment_data['assignment_id'],
                'action': assignment_data.get('action', 'assign'),
                'task_id': task_id
            })
            
        except Exception as e:
            logger.error(f"Failed to queue role assignment {assignment_data.get('assignment_id')}: {e}")
            results['failed_to_queue'].append({
                'assignment_data': assignment_data,
                'error': str(e)
            })
    
    logger.info(f"Batch role assignment queued: {len(results['queued_tasks'])} tasks, {len(results['failed_to_queue'])} failed")
    return results


def schedule_access_cleanup(clinic_id: Optional[str] = None, delay_hours: int = 24) -> str:
    """
    Schedule periodic access cleanup task.
    
    Args:
        clinic_id: Optional clinic ID to limit cleanup scope
        delay_hours: Hours to delay before running cleanup
        
    Returns:
        Task ID of scheduled cleanup
    """
    schedule_time = timezone.now() + timedelta(hours=delay_hours)
    
    task_id = async_task(
        'clinical_records.tasks.cleanup_expired_access',
        clinic_id,
        task_name=f'scheduled_access_cleanup_{clinic_id or "all"}',
        schedule=schedule_time
    )
    
    logger.info(f"Scheduled access cleanup task {task_id} for {schedule_time}")
    return task_id


def get_access_task_status(task_id: str) -> Dict[str, Any]:
    """
    Get the status of an access control task.
    
    Args:
        task_id: ID of the task to check
        
    Returns:
        Dict containing task status information
    """
    try:
        task = Task.objects.get(id=task_id)
        
        return {
            'task_id': task_id,
            'name': task.name,
            'started': task.started.isoformat() if task.started else None,
            'stopped': task.stopped.isoformat() if task.stopped else None,
            'success': task.success,
            'result': task.result if task.success else None,
            'error': task.result if not task.success else None,
            'group': task.group
        }
        
    except Task.DoesNotExist:
        return {
            'task_id': task_id,
            'error': 'Task not found'
        }
    except Exception as e:
        return {
            'task_id': task_id,
            'error': str(e)
        }