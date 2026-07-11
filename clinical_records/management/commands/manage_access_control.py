"""
Management command for access control operations.

This command provides utilities for managing access control tasks,
role assignments, emergency access, and cleanup operations.
"""

import json
from datetime import datetime, timedelta
from typing import Optional

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone
from django.contrib.auth import get_user_model
from django_q.tasks import async_task

from users.models import Clinic, Patient
from clinical_records.models.access_models import (
    ClinicalRole, UserClinicalRole, PatientConsent, EmergencyAccess
)
from clinical_records.tasks.access_control_tasks import (
    cleanup_expired_access, generate_access_report, schedule_access_cleanup
)

User = get_user_model()


class Command(BaseCommand):
    help = 'Manage access control operations and tasks'

    def add_arguments(self, parser):
        subparsers = parser.add_subparsers(dest='action', help='Available actions')
        
        # Cleanup command
        cleanup_parser = subparsers.add_parser('cleanup', help='Clean up expired access')
        cleanup_parser.add_argument(
            '--clinic-id',
            type=str,
            help='Clinic ID to limit cleanup scope'
        )
        cleanup_parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be cleaned up without making changes'
        )
        
        # Report command
        report_parser = subparsers.add_parser('report', help='Generate access control reports')
        report_parser.add_argument(
            'clinic_id',
            type=str,
            help='Clinic ID for the report'
        )
        report_parser.add_argument(
            '--type',
            choices=['summary', 'detailed', 'emergency'],
            default='summary',
            help='Type of report to generate'
        )
        report_parser.add_argument(
            '--output',
            type=str,
            help='Output file path (optional)'
        )
        
        # Role assignment command
        role_parser = subparsers.add_parser('assign-role', help='Assign role to user')
        role_parser.add_argument('username', type=str, help='Username to assign role to')
        role_parser.add_argument('role_name', type=str, help='Role name to assign')
        role_parser.add_argument('clinic_id', type=str, help='Clinic ID')
        role_parser.add_argument(
            '--reason',
            type=str,
            default='',
            help='Reason for role assignment'
        )
        role_parser.add_argument(
            '--valid-until',
            type=str,
            help='Role expiry date (YYYY-MM-DD format)'
        )
        
        # Emergency access command
        emergency_parser = subparsers.add_parser('emergency-access', help='Grant emergency access')
        emergency_parser.add_argument('username', type=str, help='Username requesting access')
        emergency_parser.add_argument('patient_id', type=str, help='Patient ID')
        emergency_parser.add_argument('reason', type=str, help='Emergency reason')
        emergency_parser.add_argument('justification', type=str, help='Medical justification')
        emergency_parser.add_argument(
            '--access-type',
            choices=['read_only', 'full_access'],
            default='read_only',
            help='Type of emergency access'
        )
        emergency_parser.add_argument(
            '--duration-hours',
            type=int,
            default=24,
            help='Duration of access in hours'
        )
        
        # Schedule cleanup command
        schedule_parser = subparsers.add_parser('schedule-cleanup', help='Schedule periodic cleanup')
        schedule_parser.add_argument(
            '--clinic-id',
            type=str,
            help='Clinic ID to limit cleanup scope'
        )
        schedule_parser.add_argument(
            '--delay-hours',
            type=int,
            default=24,
            help='Hours to delay before running cleanup'
        )
        
        # Status command
        status_parser = subparsers.add_parser('status', help='Show access control status')
        status_parser.add_argument(
            'clinic_id',
            type=str,
            help='Clinic ID to check status for'
        )

    def handle(self, *args, **options):
        action = options['action']
        
        if not action:
            self.print_help('manage.py', 'manage_access_control')
            return
        
        try:
            if action == 'cleanup':
                self.handle_cleanup(options)
            elif action == 'report':
                self.handle_report(options)
            elif action == 'assign-role':
                self.handle_assign_role(options)
            elif action == 'emergency-access':
                self.handle_emergency_access(options)
            elif action == 'schedule-cleanup':
                self.handle_schedule_cleanup(options)
            elif action == 'status':
                self.handle_status(options)
            else:
                raise CommandError(f"Unknown action: {action}")
                
        except Exception as e:
            raise CommandError(f"Command failed: {str(e)}")

    def handle_cleanup(self, options):
        """Handle cleanup command."""
        clinic_id = options.get('clinic_id')
        dry_run = options.get('dry_run', False)
        
        if dry_run:
            self.stdout.write("DRY RUN - No changes will be made")
            
            # Count items that would be cleaned up
            now = timezone.now()
            
            emergency_count = EmergencyAccess.objects.filter(
                expires_at__lt=now,
                status='active'
            )
            
            consent_count = PatientConsent.objects.filter(
                valid_until__lt=now,
                status='granted'
            )
            
            role_count = UserClinicalRole.objects.filter(
                valid_until__lt=now,
                is_active=True
            )
            
            if clinic_id:
                clinic = Clinic.objects.get(id=clinic_id)
                emergency_count = emergency_count.filter(clinic=clinic)
                consent_count = consent_count.filter(clinic=clinic)
                role_count = role_count.filter(clinic=clinic)
            
            self.stdout.write(f"Would clean up:")
            self.stdout.write(f"  - {emergency_count.count()} expired emergency access records")
            self.stdout.write(f"  - {consent_count.count()} expired patient consents")
            self.stdout.write(f"  - {role_count.count()} expired role assignments")
            
        else:
            # Run actual cleanup
            task_id = async_task(
                'clinical_records.tasks.cleanup_expired_access',
                clinic_id,
                task_name=f'manual_cleanup_{clinic_id or "all"}'
            )
            
            self.stdout.write(
                self.style.SUCCESS(f"Cleanup task queued with ID: {task_id}")
            )

    def handle_report(self, options):
        """Handle report generation command."""
        clinic_id = options['clinic_id']
        report_type = options['type']
        output_file = options.get('output')
        
        # Verify clinic exists
        try:
            clinic = Clinic.objects.get(id=clinic_id)
        except Clinic.DoesNotExist:
            raise CommandError(f"Clinic {clinic_id} not found")
        
        # Queue report generation task
        task_id = async_task(
            'clinical_records.tasks.generate_access_report',
            clinic_id,
            report_type,
            task_name=f'manual_report_{clinic_id}_{report_type}'
        )
        
        self.stdout.write(
            self.style.SUCCESS(f"Report generation task queued with ID: {task_id}")
        )
        
        if output_file:
            self.stdout.write(f"Report will be saved to: {output_file}")

    def handle_assign_role(self, options):
        """Handle role assignment command."""
        username = options['username']
        role_name = options['role_name']
        clinic_id = options['clinic_id']
        reason = options.get('reason', '')
        valid_until_str = options.get('valid_until')
        
        try:
            # Get user and clinic
            user = User.objects.get(username=username)
            clinic = Clinic.objects.get(id=clinic_id)
            role = ClinicalRole.objects.get(name=role_name, clinic=clinic)
            
            # Parse valid_until date if provided
            valid_until = None
            if valid_until_str:
                valid_until = datetime.strptime(valid_until_str, '%Y-%m-%d').date()
            
            # Create role assignment
            assignment = UserClinicalRole.objects.create(
                user=user,
                role=role,
                assigned_by=user,  # Self-assignment for command
                assignment_reason=reason or f"Assigned via management command",
                valid_until=valid_until,
                clinic=clinic
            )
            
            # Queue processing task
            task_id = async_task(
                'clinical_records.tasks.process_role_assignment',
                str(assignment.id),
                'assign',
                task_name=f'manual_role_assignment_{assignment.id}'
            )
            
            self.stdout.write(
                self.style.SUCCESS(
                    f"Role '{role_name}' assigned to '{username}' (Task ID: {task_id})"
                )
            )
            
        except User.DoesNotExist:
            raise CommandError(f"User '{username}' not found")
        except Clinic.DoesNotExist:
            raise CommandError(f"Clinic '{clinic_id}' not found")
        except ClinicalRole.DoesNotExist:
            raise CommandError(f"Role '{role_name}' not found in clinic '{clinic_id}'")

    def handle_emergency_access(self, options):
        """Handle emergency access command."""
        username = options['username']
        patient_id = options['patient_id']
        reason = options['reason']
        justification = options['justification']
        access_type = options['access_type']
        duration_hours = options['duration_hours']
        
        try:
            # Get user and patient
            user = User.objects.get(username=username)
            patient = Patient.objects.get(id=patient_id)
            
            # Create emergency access
            expires_at = timezone.now() + timedelta(hours=duration_hours)
            
            emergency_access = EmergencyAccess.objects.create(
                user=user,
                patient=patient,
                access_type=access_type,
                emergency_reason=reason,
                medical_justification=justification,
                clinic=patient.clinic,
                expires_at=expires_at
            )
            
            # Queue processing task
            task_id = async_task(
                'clinical_records.tasks.process_emergency_access_request',
                str(emergency_access.id),
                task_name=f'manual_emergency_access_{emergency_access.id}'
            )
            
            self.stdout.write(
                self.style.SUCCESS(
                    f"Emergency access granted to '{username}' for patient '{patient.get_full_name()}' "
                    f"(Task ID: {task_id}, Expires: {expires_at})"
                )
            )
            
        except User.DoesNotExist:
            raise CommandError(f"User '{username}' not found")
        except Patient.DoesNotExist:
            raise CommandError(f"Patient '{patient_id}' not found")

    def handle_schedule_cleanup(self, options):
        """Handle schedule cleanup command."""
        clinic_id = options.get('clinic_id')
        delay_hours = options['delay_hours']
        
        task_id = schedule_access_cleanup(clinic_id, delay_hours)
        
        schedule_time = timezone.now() + timedelta(hours=delay_hours)
        self.stdout.write(
            self.style.SUCCESS(
                f"Cleanup task scheduled with ID: {task_id} "
                f"(Will run at: {schedule_time})"
            )
        )

    def handle_status(self, options):
        """Handle status command."""
        clinic_id = options['clinic_id']
        
        try:
            clinic = Clinic.objects.get(id=clinic_id)
        except Clinic.DoesNotExist:
            raise CommandError(f"Clinic {clinic_id} not found")
        
        now = timezone.now()
        
        # Get current statistics
        active_roles = ClinicalRole.objects.filter(clinic=clinic, is_active=True).count()
        active_assignments = UserClinicalRole.objects.filter(
            clinic=clinic, is_active=True
        ).count()
        active_emergency = EmergencyAccess.objects.filter(
            clinic=clinic, status='active', expires_at__gt=now
        ).count()
        granted_consents = PatientConsent.objects.filter(
            clinic=clinic, status='granted'
        ).count()
        
        # Get expired items
        expired_emergency = EmergencyAccess.objects.filter(
            clinic=clinic, expires_at__lt=now, status='active'
        ).count()
        expired_consents = PatientConsent.objects.filter(
            clinic=clinic, valid_until__lt=now, status='granted'
        ).count()
        expired_roles = UserClinicalRole.objects.filter(
            clinic=clinic, valid_until__lt=now, is_active=True
        ).count()
        
        self.stdout.write(f"\nAccess Control Status for {clinic.name}")
        self.stdout.write("=" * 50)
        self.stdout.write(f"Active Roles: {active_roles}")
        self.stdout.write(f"Active Role Assignments: {active_assignments}")
        self.stdout.write(f"Active Emergency Access: {active_emergency}")
        self.stdout.write(f"Granted Consents: {granted_consents}")
        self.stdout.write("\nExpired Items (need cleanup):")
        self.stdout.write(f"  - Emergency Access: {expired_emergency}")
        self.stdout.write(f"  - Patient Consents: {expired_consents}")
        self.stdout.write(f"  - Role Assignments: {expired_roles}")
        
        if expired_emergency + expired_consents + expired_roles > 0:
            self.stdout.write(
                self.style.WARNING(
                    f"\nTotal expired items: {expired_emergency + expired_consents + expired_roles}"
                )
            )
            self.stdout.write("Run 'manage.py manage_access_control cleanup' to clean up expired items")
        else:
            self.stdout.write(self.style.SUCCESS("\nNo expired items found"))