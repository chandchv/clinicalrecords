"""
Management command for data retention and deletion operations.

This command provides utilities for managing retention policies,
executing retention actions, and handling deletion requests.
"""

import json
from datetime import datetime, timedelta
from typing import Optional

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone
from django.contrib.auth import get_user_model
from django_q.tasks import async_task

from users.models import Clinic, Patient
from clinical_records.models.retention_models import (
    RetentionPolicy, RetentionJob, DataArchive, DeletionRequest
)
from clinical_records.tasks.retention_tasks import (
    execute_retention_policy, check_retention_compliance, 
    cleanup_old_archives, schedule_retention_compliance_check
)
from clinical_records.services.retention_service import retention_service

User = get_user_model()


class Command(BaseCommand):
    help = 'Manage data retention and deletion operations'

    def add_arguments(self, parser):
        subparsers = parser.add_subparsers(dest='action', help='Available actions')
        
        # Create policy command
        create_parser = subparsers.add_parser('create-policy', help='Create retention policy')
        create_parser.add_argument('clinic_id', type=str, help='Clinic ID')
        create_parser.add_argument('--name', type=str, required=True, help='Policy name')
        create_parser.add_argument('--data-type', type=str, required=True, 
                                 choices=['clinical_records', 'documents', 'audit_logs', 
                                        'patient_data', 'imaging_studies', 'lab_results'],
                                 help='Type of data')
        create_parser.add_argument('--retention-days', type=int, required=True,
                                 help='Retention period in days')
        create_parser.add_argument('--action', type=str, 
                                 choices=['archive', 'delete', 'anonymize', 'review'],
                                 default='archive', help='Action after retention period')
        create_parser.add_argument('--grace-days', type=int, default=30,
                                 help='Grace period in days')
        create_parser.add_argument('--notify-days', type=int, default=30,
                                 help='Days before action to notify')
        create_parser.add_argument('--require-approval', action='store_true',
                                 help='Require manual approval')
        create_parser.add_argument('--legal-basis', type=str, default='',
                                 help='Legal basis for policy')
        
        # Execute policy command
        execute_parser = subparsers.add_parser('execute-policy', help='Execute retention policy')
        execute_parser.add_argument('policy_id', type=str, help='Policy ID to execute')
        execute_parser.add_argument('--user-id', type=str, help='User ID executing policy')
        execute_parser.add_argument('--async', action='store_true',
                                  help='Execute asynchronously')
        
        # List policies command
        list_parser = subparsers.add_parser('list-policies', help='List retention policies')
        list_parser.add_argument('--clinic-id', type=str, help='Filter by clinic ID')
        list_parser.add_argument('--active-only', action='store_true',
                               help='Show only active policies')
        
        # Compliance check command
        compliance_parser = subparsers.add_parser('check-compliance', help='Check retention compliance')
        compliance_parser.add_argument('--clinic-id', type=str, help='Clinic ID to check')
        compliance_parser.add_argument('--async', action='store_true',
                                     help='Run asynchronously')
        
        # Cleanup command
        cleanup_parser = subparsers.add_parser('cleanup-archives', help='Clean up old archives')
        cleanup_parser.add_argument('--days-old', type=int, default=365,
                                  help='Age threshold for cleanup (days)')
        cleanup_parser.add_argument('--clinic-id', type=str, help='Clinic ID to limit scope')
        cleanup_parser.add_argument('--dry-run', action='store_true',
                                  help='Show what would be cleaned without making changes')
        
        # Deletion request command
        deletion_parser = subparsers.add_parser('create-deletion-request', 
                                              help='Create deletion request')
        deletion_parser.add_argument('--type', type=str, required=True,
                                   choices=['patient_erasure', 'administrative', 
                                          'legal_requirement', 'data_breach'],
                                   help='Type of deletion request')
        deletion_parser.add_argument('--patient-id', type=str, help='Patient ID (for patient erasure)')
        deletion_parser.add_argument('--reason', type=str, required=True,
                                   help='Reason for deletion')
        deletion_parser.add_argument('--legal-basis', type=str, default='',
                                   help='Legal basis for deletion')
        deletion_parser.add_argument('--scope', type=str, default='{}',
                                   help='Deletion scope as JSON string')
        deletion_parser.add_argument('--requestor-username', type=str, required=True,
                                   help='Username of person making request')
        
        # Report command
        report_parser = subparsers.add_parser('generate-report', help='Generate retention report')
        report_parser.add_argument('clinic_id', type=str, help='Clinic ID for report')
        report_parser.add_argument('--type', type=str, 
                                 choices=['summary', 'detailed', 'compliance'],
                                 default='summary', help='Type of report')
        report_parser.add_argument('--output', type=str, help='Output file path')
        
        # Status command
        status_parser = subparsers.add_parser('status', help='Show retention status')
        status_parser.add_argument('clinic_id', type=str, help='Clinic ID to check')
        
        # Schedule command
        schedule_parser = subparsers.add_parser('schedule-compliance', 
                                              help='Schedule compliance check')
        schedule_parser.add_argument('--clinic-id', type=str, help='Clinic ID to check')
        schedule_parser.add_argument('--delay-hours', type=int, default=24,
                                   help='Hours to delay before running')

    def handle(self, *args, **options):
        action = options['action']
        
        if not action:
            self.print_help('manage.py', 'manage_retention')
            return
        
        try:
            if action == 'create-policy':
                self.handle_create_policy(options)
            elif action == 'execute-policy':
                self.handle_execute_policy(options)
            elif action == 'list-policies':
                self.handle_list_policies(options)
            elif action == 'check-compliance':
                self.handle_check_compliance(options)
            elif action == 'cleanup-archives':
                self.handle_cleanup_archives(options)
            elif action == 'create-deletion-request':
                self.handle_create_deletion_request(options)
            elif action == 'generate-report':
                self.handle_generate_report(options)
            elif action == 'status':
                self.handle_status(options)
            elif action == 'schedule-compliance':
                self.handle_schedule_compliance(options)
            else:
                raise CommandError(f"Unknown action: {action}")
                
        except Exception as e:
            raise CommandError(f"Command failed: {str(e)}")

    def handle_create_policy(self, options):
        """Handle create policy command."""
        clinic_id = options['clinic_id']
        
        try:
            clinic = Clinic.objects.get(id=clinic_id)
        except Clinic.DoesNotExist:
            raise CommandError(f"Clinic {clinic_id} not found")
        
        # Create a system user for policy creation
        admin_user = User.objects.filter(
            clinic=clinic, 
            is_staff=True
        ).first()
        
        if not admin_user:
            raise CommandError(f"No admin user found for clinic {clinic_id}")
        
        policy_data = {
            'name': options['name'],
            'data_type': options['data_type'],
            'retention_period_days': options['retention_days'],
            'action_after_retention': options['action'],
            'grace_period_days': options['grace_days'],
            'notify_before_days': options['notify_days'],
            'require_approval': options['require_approval'],
            'legal_basis': options['legal_basis']
        }
        
        policy = retention_service.create_retention_policy(
            clinic=clinic,
            policy_data=policy_data,
            created_by=admin_user
        )
        
        self.stdout.write(
            self.style.SUCCESS(
                f"Created retention policy '{policy.name}' with ID: {policy.id}"
            )
        )

    def handle_execute_policy(self, options):
        """Handle execute policy command."""
        policy_id = options['policy_id']
        user_id = options.get('user_id')
        async_execution = options.get('async', False)
        
        try:
            policy = RetentionPolicy.objects.get(id=policy_id)
        except RetentionPolicy.DoesNotExist:
            raise CommandError(f"Retention policy {policy_id} not found")
        
        if async_execution:
            # Execute asynchronously
            task_id = async_task(
                'clinical_records.tasks.execute_retention_policy',
                policy_id,
                user_id,
                task_name=f'manual_retention_policy_{policy_id}'
            )
            
            self.stdout.write(
                self.style.SUCCESS(f"Retention policy execution queued with task ID: {task_id}")
            )
        else:
            # Execute synchronously
            user = User.objects.get(id=user_id) if user_id else None
            job = retention_service.execute_retention_policy(policy, user)
            
            self.stdout.write(
                self.style.SUCCESS(
                    f"Retention policy executed. Job ID: {job.id}, "
                    f"Status: {job.status}, "
                    f"Processed: {job.processed_items}/{job.total_items}"
                )
            )

    def handle_list_policies(self, options):
        """Handle list policies command."""
        clinic_id = options.get('clinic_id')
        active_only = options.get('active_only', False)
        
        policies_query = RetentionPolicy.objects.all()
        
        if clinic_id:
            policies_query = policies_query.filter(clinic_id=clinic_id)
        
        if active_only:
            policies_query = policies_query.filter(is_active=True)
        
        policies = policies_query.select_related('clinic', 'created_by').order_by('clinic__name', 'name')
        
        if not policies:
            self.stdout.write("No retention policies found.")
            return
        
        self.stdout.write(f"\nFound {policies.count()} retention policies:")
        self.stdout.write("=" * 80)
        
        for policy in policies:
            status = "Active" if policy.is_active else "Inactive"
            self.stdout.write(f"ID: {policy.id}")
            self.stdout.write(f"Name: {policy.name}")
            self.stdout.write(f"Clinic: {policy.clinic.name}")
            self.stdout.write(f"Data Type: {policy.data_type}")
            self.stdout.write(f"Retention: {policy.retention_period_days} days")
            self.stdout.write(f"Action: {policy.action_after_retention}")
            self.stdout.write(f"Status: {status}")
            self.stdout.write(f"Created: {policy.created_at.strftime('%Y-%m-%d %H:%M')}")
            self.stdout.write("-" * 40)

    def handle_check_compliance(self, options):
        """Handle compliance check command."""
        clinic_id = options.get('clinic_id')
        async_execution = options.get('async', False)
        
        if async_execution:
            # Run asynchronously
            task_id = async_task(
                'clinical_records.tasks.check_retention_compliance',
                clinic_id,
                task_name=f'manual_compliance_check_{clinic_id or "all"}'
            )
            
            self.stdout.write(
                self.style.SUCCESS(f"Compliance check queued with task ID: {task_id}")
            )
        else:
            # Run synchronously
            from clinical_records.tasks.retention_tasks import RetentionTaskProcessor
            processor = RetentionTaskProcessor()
            result = processor.check_retention_compliance(clinic_id)
            
            self.stdout.write(f"\nCompliance Check Results:")
            self.stdout.write("=" * 50)
            self.stdout.write(f"Status: {result['status']}")
            self.stdout.write(f"Total Issues: {result.get('total_issues', 0)}")
            self.stdout.write(f"Clinics Checked: {result.get('clinics_checked', 0)}")
            
            if result.get('compliance_issues'):
                self.stdout.write("\nCompliance Issues:")
                for clinic_issues in result['compliance_issues']:
                    self.stdout.write(f"\nClinic: {clinic_issues['clinic_name']}")
                    for issue in clinic_issues['issues']:
                        self.stdout.write(f"  - Policy: {issue['policy_name']}")
                        self.stdout.write(f"    Data Type: {issue['data_type']}")
                        self.stdout.write(f"    Overdue Items: {issue['overdue_items']}")
                        self.stdout.write(f"    Action Required: {issue['action_required']}")
            else:
                self.stdout.write(self.style.SUCCESS("\nNo compliance issues found."))

    def handle_cleanup_archives(self, options):
        """Handle cleanup archives command."""
        days_old = options['days_old']
        clinic_id = options.get('clinic_id')
        dry_run = options.get('dry_run', False)
        
        if dry_run:
            self.stdout.write("DRY RUN - No changes will be made")
            
            # Count archives that would be cleaned
            cutoff_date = timezone.now() - timedelta(days=days_old)
            
            archives_query = DataArchive.objects.filter(
                created_at__lt=cutoff_date,
                legal_hold=False
            )
            
            if clinic_id:
                archives_query = archives_query.filter(clinic_id=clinic_id)
            
            count = archives_query.count()
            total_size = sum(archive.archive_size_bytes for archive in archives_query.all())
            
            self.stdout.write(f"Would clean up {count} archives")
            self.stdout.write(f"Total size: {total_size / (1024*1024):.2f} MB")
            
        else:
            # Run actual cleanup
            task_id = async_task(
                'clinical_records.tasks.cleanup_old_archives',
                days_old,
                clinic_id,
                task_name=f'manual_archive_cleanup_{clinic_id or "all"}'
            )
            
            self.stdout.write(
                self.style.SUCCESS(f"Archive cleanup queued with task ID: {task_id}")
            )

    def handle_create_deletion_request(self, options):
        """Handle create deletion request command."""
        request_type = options['type']
        patient_id = options.get('patient_id')
        reason = options['reason']
        legal_basis = options.get('legal_basis', '')
        scope_json = options.get('scope', '{}')
        requestor_username = options['requestor_username']
        
        try:
            requestor = User.objects.get(username=requestor_username)
        except User.DoesNotExist:
            raise CommandError(f"User '{requestor_username}' not found")
        
        try:
            scope = json.loads(scope_json)
        except json.JSONDecodeError:
            raise CommandError("Invalid JSON format for scope")
        
        request_data = {
            'request_type': request_type,
            'reason': reason,
            'legal_basis': legal_basis,
            'deletion_scope': scope
        }
        
        if patient_id:
            try:
                patient = Patient.objects.get(id=patient_id)
                request_data['patient_id'] = patient_id
            except Patient.DoesNotExist:
                raise CommandError(f"Patient {patient_id} not found")
        
        deletion_request = retention_service.create_deletion_request(
            request_data=request_data,
            requested_by=requestor
        )
        
        self.stdout.write(
            self.style.SUCCESS(
                f"Created deletion request with ID: {deletion_request.id}"
            )
        )

    def handle_generate_report(self, options):
        """Handle generate report command."""
        clinic_id = options['clinic_id']
        report_type = options['type']
        output_file = options.get('output')
        
        try:
            clinic = Clinic.objects.get(id=clinic_id)
        except Clinic.DoesNotExist:
            raise CommandError(f"Clinic {clinic_id} not found")
        
        # Generate report
        report_data = retention_service.generate_retention_report(clinic, report_type)
        
        # Output report
        if output_file:
            with open(output_file, 'w') as f:
                json.dump(report_data, f, indent=2, default=str)
            self.stdout.write(
                self.style.SUCCESS(f"Report saved to: {output_file}")
            )
        else:
            self.stdout.write(f"\nRetention Report - {clinic.name}")
            self.stdout.write("=" * 50)
            self.stdout.write(json.dumps(report_data, indent=2, default=str))

    def handle_status(self, options):
        """Handle status command."""
        clinic_id = options['clinic_id']
        
        try:
            clinic = Clinic.objects.get(id=clinic_id)
        except Clinic.DoesNotExist:
            raise CommandError(f"Clinic {clinic_id} not found")
        
        # Get status information
        active_policies = RetentionPolicy.objects.filter(clinic=clinic, is_active=True).count()
        total_jobs = RetentionJob.objects.filter(clinic=clinic).count()
        completed_jobs = RetentionJob.objects.filter(clinic=clinic, status='completed').count()
        failed_jobs = RetentionJob.objects.filter(clinic=clinic, status='failed').count()
        pending_jobs = RetentionJob.objects.filter(clinic=clinic, status='pending').count()
        
        archived_items = DataArchive.objects.filter(clinic=clinic).count()
        legal_holds = DataArchive.objects.filter(clinic=clinic, legal_hold=True).count()
        
        pending_deletions = DeletionRequest.objects.filter(clinic=clinic, status='pending').count()
        approved_deletions = DeletionRequest.objects.filter(clinic=clinic, status='approved').count()
        
        self.stdout.write(f"\nRetention Status for {clinic.name}")
        self.stdout.write("=" * 50)
        self.stdout.write(f"Active Policies: {active_policies}")
        self.stdout.write(f"Total Jobs: {total_jobs}")
        self.stdout.write(f"  - Completed: {completed_jobs}")
        self.stdout.write(f"  - Failed: {failed_jobs}")
        self.stdout.write(f"  - Pending: {pending_jobs}")
        self.stdout.write(f"Archived Items: {archived_items}")
        self.stdout.write(f"Legal Holds: {legal_holds}")
        self.stdout.write(f"Pending Deletions: {pending_deletions}")
        self.stdout.write(f"Approved Deletions: {approved_deletions}")
        
        if failed_jobs > 0:
            self.stdout.write(
                self.style.WARNING(f"\nWarning: {failed_jobs} retention jobs have failed")
            )
        
        if pending_deletions > 0:
            self.stdout.write(
                self.style.WARNING(f"\nNote: {pending_deletions} deletion requests need review")
            )

    def handle_schedule_compliance(self, options):
        """Handle schedule compliance command."""
        clinic_id = options.get('clinic_id')
        delay_hours = options['delay_hours']
        
        task_id = schedule_retention_compliance_check(clinic_id, delay_hours)
        
        schedule_time = timezone.now() + timedelta(hours=delay_hours)
        self.stdout.write(
            self.style.SUCCESS(
                f"Compliance check scheduled with task ID: {task_id} "
                f"(Will run at: {schedule_time})"
            )
        )