"""
Background tasks for data retention and deletion operations using Django-Q.

This module provides background tasks for executing retention policies,
processing deletion requests, and managing data archival operations.
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
from ..models.retention_models import (
    RetentionPolicy, RetentionJob, DataArchive, 
    DeletionRequest, RetentionNotification
)
from ..services.retention_service import retention_service
from ..services.audit_service import audit_service

User = get_user_model()
logger = logging.getLogger(__name__)


class RetentionTaskProcessor:
    """Main class for handling retention background tasks."""
    
    def __init__(self):
        self.logger = logging.getLogger(f"{__name__}.{self.__class__.__name__}")
        self.config = getattr(settings, 'CLINICAL_RECORDS_RETENTION', {})
    
    def execute_retention_policy(self, policy_id: str, user_id: Optional[str] = None) -> Dict[str, Any]:
        """
        Execute a retention policy in the background.
        
        Args:
            policy_id: ID of the retention policy to execute
            user_id: ID of user executing the policy (optional)
            
        Returns:
            Dict containing execution results
        """
        start_time = time.time()
        result = {
            'policy_id': policy_id,
            'user_id': user_id,
            'status': 'started',
            'start_time': start_time
        }
        
        try:
            # Get policy and user
            policy = RetentionPolicy.objects.get(id=policy_id)
            user = User.objects.get(id=user_id) if user_id else None
            
            # Execute the policy
            job = retention_service.execute_retention_policy(policy, user)
            
            result.update({
                'status': 'completed',
                'job_id': str(job.id),
                'total_items': job.total_items,
                'successful_items': job.successful_items,
                'failed_items': job.failed_items,
                'processing_time': time.time() - start_time
            })
            
            # Send completion notification
            self._send_policy_completion_notification(job)
            
            return result
            
        except RetentionPolicy.DoesNotExist:
            error_msg = f"Retention policy {policy_id} not found"
            self.logger.error(error_msg)
            result.update({
                'status': 'failed',
                'error': error_msg,
                'processing_time': time.time() - start_time
            })
            return result
            
        except Exception as e:
            error_msg = f"Retention policy execution failed: {str(e)}"
            self.logger.error(f"Error executing retention policy {policy_id}: {e}", exc_info=True)
            result.update({
                'status': 'failed',
                'error': error_msg,
                'processing_time': time.time() - start_time
            })
            return result
    
    def process_deletion_request(self, request_id: str, user_id: str) -> Dict[str, Any]:
        """
        Process an approved deletion request.
        
        Args:
            request_id: ID of the deletion request
            user_id: ID of user executing the deletion
            
        Returns:
            Dict containing processing results
        """
        start_time = time.time()
        result = {
            'request_id': request_id,
            'user_id': user_id,
            'status': 'started',
            'start_time': start_time
        }
        
        try:
            # Get deletion request and user
            deletion_request = DeletionRequest.objects.get(id=request_id)
            user = User.objects.get(id=user_id)
            
            # Execute the deletion
            execution_results = retention_service.execute_deletion_request(deletion_request, user)
            
            result.update({
                'status': 'completed',
                'execution_results': execution_results,
                'processing_time': time.time() - start_time
            })
            
            # Send completion notification
            self._send_deletion_completion_notification(deletion_request, execution_results)
            
            return result
            
        except DeletionRequest.DoesNotExist:
            error_msg = f"Deletion request {request_id} not found"
            self.logger.error(error_msg)
            result.update({
                'status': 'failed',
                'error': error_msg,
                'processing_time': time.time() - start_time
            })
            return result
            
        except Exception as e:
            error_msg = f"Deletion request processing failed: {str(e)}"
            self.logger.error(f"Error processing deletion request {request_id}: {e}", exc_info=True)
            result.update({
                'status': 'failed',
                'error': error_msg,
                'processing_time': time.time() - start_time
            })
            return result
    
    def check_retention_compliance(self, clinic_id: Optional[str] = None) -> Dict[str, Any]:
        """
        Check retention compliance and identify overdue items.
        
        Args:
            clinic_id: Optional clinic ID to limit scope
            
        Returns:
            Dict containing compliance check results
        """
        start_time = time.time()
        result = {
            'clinic_id': clinic_id,
            'status': 'started',
            'start_time': start_time,
            'compliance_issues': []
        }
        
        try:
            # Get clinics to check
            if clinic_id:
                clinics = [Clinic.objects.get(id=clinic_id)]
            else:
                clinics = Clinic.objects.all()
            
            total_issues = 0
            
            for clinic in clinics:
                clinic_issues = self._check_clinic_compliance(clinic)
                total_issues += len(clinic_issues)
                
                if clinic_issues:
                    result['compliance_issues'].append({
                        'clinic_id': str(clinic.id),
                        'clinic_name': clinic.name,
                        'issues': clinic_issues
                    })
            
            result.update({
                'status': 'completed',
                'total_issues': total_issues,
                'clinics_checked': len(clinics),
                'processing_time': time.time() - start_time
            })
            
            # Send notifications for compliance issues
            if total_issues > 0:
                self._send_compliance_notifications(result['compliance_issues'])
            
            return result
            
        except Exception as e:
            error_msg = f"Compliance check failed: {str(e)}"
            self.logger.error(f"Error checking retention compliance: {e}", exc_info=True)
            result.update({
                'status': 'failed',
                'error': error_msg,
                'processing_time': time.time() - start_time
            })
            return result
    
    def send_retention_notifications(self, clinic_id: Optional[str] = None) -> Dict[str, Any]:
        """
        Send retention policy notifications for upcoming actions.
        
        Args:
            clinic_id: Optional clinic ID to limit scope
            
        Returns:
            Dict containing notification results
        """
        start_time = time.time()
        result = {
            'clinic_id': clinic_id,
            'status': 'started',
            'start_time': start_time,
            'notifications_sent': 0
        }
        
        try:
            # Get active policies
            policies_query = RetentionPolicy.objects.filter(is_active=True)
            if clinic_id:
                policies_query = policies_query.filter(clinic_id=clinic_id)
            
            policies = policies_query.all()
            
            for policy in policies:
                notifications_sent = self._send_policy_notifications(policy)
                result['notifications_sent'] += notifications_sent
            
            result.update({
                'status': 'completed',
                'policies_processed': len(policies),
                'processing_time': time.time() - start_time
            })
            
            return result
            
        except Exception as e:
            error_msg = f"Notification sending failed: {str(e)}"
            self.logger.error(f"Error sending retention notifications: {e}", exc_info=True)
            result.update({
                'status': 'failed',
                'error': error_msg,
                'processing_time': time.time() - start_time
            })
            return result
    
    def cleanup_old_archives(self, days_old: int = 365, clinic_id: Optional[str] = None) -> Dict[str, Any]:
        """
        Clean up old archived data that's no longer needed.
        
        Args:
            days_old: Age threshold for cleanup (days)
            clinic_id: Optional clinic ID to limit scope
            
        Returns:
            Dict containing cleanup results
        """
        start_time = time.time()
        result = {
            'days_old': days_old,
            'clinic_id': clinic_id,
            'status': 'started',
            'start_time': start_time,
            'cleaned_archives': 0
        }
        
        try:
            cutoff_date = timezone.now() - timedelta(days=days_old)
            
            # Find old archives not under legal hold
            archives_query = DataArchive.objects.filter(
                created_at__lt=cutoff_date,
                legal_hold=False
            )
            
            if clinic_id:
                archives_query = archives_query.filter(clinic_id=clinic_id)
            
            old_archives = archives_query.all()
            
            for archive in old_archives:
                try:
                    # Remove archive file
                    import os
                    if os.path.exists(archive.archive_path):
                        os.remove(archive.archive_path)
                    
                    # Remove archive record
                    archive.delete()
                    result['cleaned_archives'] += 1
                    
                except Exception as e:
                    self.logger.error(f"Error cleaning archive {archive.id}: {e}")
            
            result.update({
                'status': 'completed',
                'processing_time': time.time() - start_time
            })
            
            # Log cleanup activity
            if result['cleaned_archives'] > 0:
                audit_service.log_clinical_action(
                    action='ARCHIVE_CLEANUP',
                    user=None,  # System action
                    resource_type='DATA_ARCHIVE',
                    resource_id='cleanup_task',
                    clinic=Clinic.objects.get(id=clinic_id) if clinic_id else None,
                    details={
                        'cleaned_archives': result['cleaned_archives'],
                        'days_old_threshold': days_old
                    }
                )
            
            return result
            
        except Exception as e:
            error_msg = f"Archive cleanup failed: {str(e)}"
            self.logger.error(f"Error cleaning old archives: {e}", exc_info=True)
            result.update({
                'status': 'failed',
                'error': error_msg,
                'processing_time': time.time() - start_time
            })
            return result
    
    def generate_retention_report(self, clinic_id: str, report_type: str = 'summary') -> Dict[str, Any]:
        """
        Generate retention compliance report.
        
        Args:
            clinic_id: Clinic ID for the report
            report_type: Type of report to generate
            
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
            report_data = retention_service.generate_retention_report(clinic, report_type)
            
            result.update({
                'status': 'completed',
                'report_data': report_data,
                'processing_time': time.time() - start_time
            })
            
            # Log report generation
            audit_service.log_clinical_action(
                action='RETENTION_REPORT_GENERATED',
                user=None,  # System action
                resource_type='RETENTION_REPORT',
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
            self.logger.error(f"Error generating retention report: {e}", exc_info=True)
            result.update({
                'status': 'failed',
                'error': error_msg,
                'processing_time': time.time() - start_time
            })
            return result
    
    def _check_clinic_compliance(self, clinic: Clinic) -> List[Dict[str, Any]]:
        """Check compliance issues for a specific clinic."""
        issues = []
        
        try:
            # Check each active policy
            policies = RetentionPolicy.objects.filter(clinic=clinic, is_active=True)
            
            for policy in policies:
                # Find data that should have been processed
                eligible_data = retention_service._find_eligible_data(policy)
                
                if eligible_data:
                    issues.append({
                        'policy_id': str(policy.id),
                        'policy_name': policy.name,
                        'data_type': policy.data_type,
                        'overdue_items': len(eligible_data),
                        'action_required': policy.action_after_retention,
                        'days_overdue': (timezone.now() - (timezone.now() - timedelta(days=policy.retention_period_days))).days
                    })
            
        except Exception as e:
            self.logger.error(f"Error checking compliance for clinic {clinic.id}: {e}")
        
        return issues
    
    def _send_policy_notifications(self, policy: RetentionPolicy) -> int:
        """Send notifications for a specific policy."""
        notifications_sent = 0
        
        try:
            # Find data that needs notification
            eligible_data = retention_service._find_eligible_data(policy)
            
            if not eligible_data:
                return 0
            
            # Find users to notify (administrators and data managers)
            from ..models.access_models import ClinicalRole, UserClinicalRole
            
            notify_roles = ClinicalRole.objects.filter(
                clinic=policy.clinic,
                role_type__in=['admin', 'data_manager'],
                is_active=True
            )
            
            notify_assignments = UserClinicalRole.objects.filter(
                role__in=notify_roles,
                is_active=True
            ).select_related('user')
            
            for assignment in notify_assignments:
                # Check if notification already sent recently
                recent_notification = RetentionNotification.objects.filter(
                    recipient=assignment.user,
                    policy=policy,
                    notification_type='upcoming_action',
                    created_at__gte=timezone.now() - timedelta(days=7)
                ).exists()
                
                if not recent_notification:
                    RetentionNotification.objects.create(
                        clinic=policy.clinic,
                        notification_type='upcoming_action',
                        recipient=assignment.user,
                        policy=policy,
                        subject=f"Retention Action Required - {policy.name}",
                        message=f"Data retention action is required for policy '{policy.name}'.\n\n"
                               f"Data Type: {policy.data_type}\n"
                               f"Action: {policy.action_after_retention}\n"
                               f"Items Affected: {len(eligible_data)}\n\n"
                               f"Please review and execute the retention policy.",
                        data_summary={
                            'policy_name': policy.name,
                            'data_type': policy.data_type,
                            'action': policy.action_after_retention,
                            'affected_items': len(eligible_data)
                        }
                    )
                    notifications_sent += 1
            
        except Exception as e:
            self.logger.error(f"Error sending notifications for policy {policy.id}: {e}")
        
        return notifications_sent
    
    def _send_policy_completion_notification(self, job: RetentionJob):
        """Send notification when retention policy execution completes."""
        try:
            # Find administrators to notify
            from ..models.access_models import ClinicalRole, UserClinicalRole
            
            admin_roles = ClinicalRole.objects.filter(
                clinic=job.clinic,
                role_type='admin',
                is_active=True
            )
            
            admin_assignments = UserClinicalRole.objects.filter(
                role__in=admin_roles,
                is_active=True
            ).select_related('user')
            
            for assignment in admin_assignments:
                RetentionNotification.objects.create(
                    clinic=job.clinic,
                    notification_type='action_completed',
                    recipient=assignment.user,
                    job=job,
                    subject=f"Retention Policy Executed - {job.policy.name}",
                    message=f"Retention policy '{job.policy.name}' has been executed.\n\n"
                           f"Job Status: {job.status}\n"
                           f"Items Processed: {job.processed_items}\n"
                           f"Successful: {job.successful_items}\n"
                           f"Failed: {job.failed_items}\n"
                           f"Success Rate: {job.success_rate:.1f}%\n\n"
                           f"Please review the results and take any necessary follow-up actions.",
                    data_summary={
                        'job_id': str(job.id),
                        'policy_name': job.policy.name,
                        'status': job.status,
                        'processed_items': job.processed_items,
                        'success_rate': job.success_rate
                    }
                )
            
        except Exception as e:
            self.logger.error(f"Error sending policy completion notification: {e}")
    
    def _send_deletion_completion_notification(self, deletion_request: DeletionRequest, 
                                             execution_results: Dict[str, Any]):
        """Send notification when deletion request execution completes."""
        try:
            # Notify the requestor
            RetentionNotification.objects.create(
                clinic=deletion_request.clinic,
                notification_type='action_completed',
                recipient=deletion_request.requested_by,
                deletion_request=deletion_request,
                subject=f"Deletion Request Completed - {deletion_request.request_type}",
                message=f"Your deletion request has been completed.\n\n"
                       f"Request Type: {deletion_request.request_type}\n"
                       f"Status: {deletion_request.status}\n"
                       f"Records Deleted: {execution_results.get('deleted_records', 0)}\n"
                       f"Documents Deleted: {execution_results.get('deleted_documents', 0)}\n"
                       f"Archives Deleted: {execution_results.get('deleted_archives', 0)}\n"
                       f"Errors: {len(execution_results.get('errors', []))}\n\n"
                       f"The deletion has been completed as requested.",
                data_summary=execution_results
            )
            
        except Exception as e:
            self.logger.error(f"Error sending deletion completion notification: {e}")
    
    def _send_compliance_notifications(self, compliance_issues: List[Dict[str, Any]]):
        """Send notifications about compliance issues."""
        try:
            for clinic_issues in compliance_issues:
                clinic = Clinic.objects.get(id=clinic_issues['clinic_id'])
                
                # Find administrators to notify
                from ..models.access_models import ClinicalRole, UserClinicalRole
                
                admin_roles = ClinicalRole.objects.filter(
                    clinic=clinic,
                    role_type='admin',
                    is_active=True
                )
                
                admin_assignments = UserClinicalRole.objects.filter(
                    role__in=admin_roles,
                    is_active=True
                ).select_related('user')
                
                for assignment in admin_assignments:
                    RetentionNotification.objects.create(
                        clinic=clinic,
                        notification_type='approval_required',
                        recipient=assignment.user,
                        subject=f"Retention Compliance Issues - {clinic.name}",
                        message=f"Retention compliance issues have been identified for {clinic.name}.\n\n"
                               f"Number of Issues: {len(clinic_issues['issues'])}\n\n"
                               f"Please review and address these compliance issues promptly.",
                        data_summary=clinic_issues,
                        response_required=True,
                        response_deadline=timezone.now() + timedelta(days=3)
                    )
            
        except Exception as e:
            self.logger.error(f"Error sending compliance notifications: {e}")


# Task functions for Django-Q
def execute_retention_policy(policy_id: str, user_id: Optional[str] = None) -> Dict[str, Any]:
    """
    Django-Q task function for executing retention policies.
    
    Args:
        policy_id: ID of the retention policy to execute
        user_id: ID of user executing the policy (optional)
        
    Returns:
        Dict containing execution results
    """
    processor = RetentionTaskProcessor()
    return processor.execute_retention_policy(policy_id, user_id)


def process_deletion_request(request_id: str, user_id: str) -> Dict[str, Any]:
    """
    Django-Q task function for processing deletion requests.
    
    Args:
        request_id: ID of the deletion request
        user_id: ID of user executing the deletion
        
    Returns:
        Dict containing processing results
    """
    processor = RetentionTaskProcessor()
    return processor.process_deletion_request(request_id, user_id)


def check_retention_compliance(clinic_id: Optional[str] = None) -> Dict[str, Any]:
    """
    Django-Q task function for checking retention compliance.
    
    Args:
        clinic_id: Optional clinic ID to limit scope
        
    Returns:
        Dict containing compliance check results
    """
    processor = RetentionTaskProcessor()
    return processor.check_retention_compliance(clinic_id)


def send_retention_notifications(clinic_id: Optional[str] = None) -> Dict[str, Any]:
    """
    Django-Q task function for sending retention notifications.
    
    Args:
        clinic_id: Optional clinic ID to limit scope
        
    Returns:
        Dict containing notification results
    """
    processor = RetentionTaskProcessor()
    return processor.send_retention_notifications(clinic_id)


def cleanup_old_archives(days_old: int = 365, clinic_id: Optional[str] = None) -> Dict[str, Any]:
    """
    Django-Q task function for cleaning up old archives.
    
    Args:
        days_old: Age threshold for cleanup (days)
        clinic_id: Optional clinic ID to limit scope
        
    Returns:
        Dict containing cleanup results
    """
    processor = RetentionTaskProcessor()
    return processor.cleanup_old_archives(days_old, clinic_id)


def generate_retention_report(clinic_id: str, report_type: str = 'summary') -> Dict[str, Any]:
    """
    Django-Q task function for generating retention reports.
    
    Args:
        clinic_id: Clinic ID for the report
        report_type: Type of report to generate
        
    Returns:
        Dict containing report data
    """
    processor = RetentionTaskProcessor()
    return processor.generate_retention_report(clinic_id, report_type)


def schedule_retention_compliance_check(clinic_id: Optional[str] = None, 
                                       delay_hours: int = 24) -> str:
    """
    Schedule periodic retention compliance check.
    
    Args:
        clinic_id: Optional clinic ID to limit scope
        delay_hours: Hours to delay before running check
        
    Returns:
        Task ID of scheduled check
    """
    schedule_time = timezone.now() + timedelta(hours=delay_hours)
    
    task_id = async_task(
        'clinical_records.tasks.check_retention_compliance',
        clinic_id,
        task_name=f'scheduled_compliance_check_{clinic_id or "all"}',
        schedule=schedule_time
    )
    
    logger.info(f"Scheduled retention compliance check task {task_id} for {schedule_time}")
    return task_id


def get_retention_task_status(task_id: str) -> Dict[str, Any]:
    """
    Get the status of a retention task.
    
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