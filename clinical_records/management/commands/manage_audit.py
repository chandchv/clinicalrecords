"""
Management command for audit logging operations.

This command provides utilities for managing audit logs,
generating reports, and maintaining audit data.
"""

import json
from datetime import datetime, timedelta
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone
from django.db.models import Count, Q

from users.models import AuditLog
from clinical_records.services.audit_service import audit_service
from users.models import Clinic


class Command(BaseCommand):
    help = 'Manage audit logging for clinical records'

    def add_arguments(self, parser):
        parser.add_argument(
            '--action',
            type=str,
            choices=[
                'status', 'compliance-report', 'cleanup', 'export',
                'user-activity', 'resource-audit', 'statistics'
            ],
            default='status',
            help='Action to perform'
        )
        
        parser.add_argument(
            '--clinic-id',
            type=int,
            help='Specific clinic ID to operate on'
        )
        
        parser.add_argument(
            '--user-id',
            type=int,
            help='Specific user ID for user activity reports'
        )
        
        parser.add_argument(
            '--resource-type',
            type=str,
            help='Resource type for resource audit'
        )
        
        parser.add_argument(
            '--resource-id',
            type=str,
            help='Resource ID for resource audit'
        )
        
        parser.add_argument(
            '--start-date',
            type=str,
            help='Start date for reports (YYYY-MM-DD)'
        )
        
        parser.add_argument(
            '--end-date',
            type=str,
            help='End date for reports (YYYY-MM-DD)'
        )
        
        parser.add_argument(
            '--days',
            type=int,
            default=30,
            help='Number of days to look back (default: 30)'
        )
        
        parser.add_argument(
            '--cleanup-days',
            type=int,
            default=365,
            help='Delete audit logs older than this many days (default: 365)'
        )
        
        parser.add_argument(
            '--output-file',
            type=str,
            help='Output file for export (JSON format)'
        )
        
        parser.add_argument(
            '--format',
            type=str,
            choices=['table', 'json', 'csv'],
            default='table',
            help='Output format'
        )

    def handle(self, *args, **options):
        action = options['action']
        
        try:
            if action == 'status':
                self.show_audit_status(options)
            elif action == 'compliance-report':
                self.generate_compliance_report(options)
            elif action == 'cleanup':
                self.cleanup_old_logs(options)
            elif action == 'export':
                self.export_audit_logs(options)
            elif action == 'user-activity':
                self.show_user_activity(options)
            elif action == 'resource-audit':
                self.show_resource_audit(options)
            elif action == 'statistics':
                self.show_audit_statistics(options)
                
        except Exception as e:
            raise CommandError(f"Error executing {action}: {str(e)}")

    def show_audit_status(self, options):
        """Show audit logging status."""
        self.stdout.write(self.style.SUCCESS('Audit Logging Status'))
        self.stdout.write('=' * 50)
        
        # Overall statistics
        total_logs = AuditLog.objects.count()
        clinical_logs = AuditLog.objects.filter(
            action__in=list(audit_service.CLINICAL_ACTIONS.keys())
        ).count()
        
        # Recent activity (last 24 hours)
        last_24h = timezone.now() - timedelta(hours=24)
        recent_logs = AuditLog.objects.filter(
            timestamp__gte=last_24h,
            action__in=list(audit_service.CLINICAL_ACTIONS.keys())
        )
        
        self.stdout.write(f"Total Audit Logs: {total_logs}")
        self.stdout.write(f"Clinical Records Logs: {clinical_logs}")
        self.stdout.write(f"Recent Activity (24h): {recent_logs.count()}")
        
        # Clinic breakdown
        if options['clinic_id']:
            clinics = Clinic.objects.filter(id=options['clinic_id'])
        else:
            clinics = Clinic.objects.all()
        
        self.stdout.write(f"\nClinic Breakdown:")
        for clinic in clinics:
            clinic_logs = AuditLog.objects.filter(
                clinic=clinic,
                action__in=list(audit_service.CLINICAL_ACTIONS.keys())
            ).count()
            
            recent_clinic_logs = recent_logs.filter(clinic=clinic).count()
            
            self.stdout.write(f"  {clinic.name}: {clinic_logs} total, {recent_clinic_logs} recent")
        
        # Top actions
        top_actions = AuditLog.objects.filter(
            action__in=list(audit_service.CLINICAL_ACTIONS.keys()),
            timestamp__gte=timezone.now() - timedelta(days=7)
        ).values('action').annotate(
            count=Count('id')
        ).order_by('-count')[:5]
        
        self.stdout.write(f"\nTop Actions (Last 7 Days):")
        for action in top_actions:
            action_name = audit_service.CLINICAL_ACTIONS.get(action['action'], action['action'])
            self.stdout.write(f"  {action_name}: {action['count']}")

    def generate_compliance_report(self, options):
        """Generate compliance report for a clinic."""
        clinic_id = options.get('clinic_id')
        if not clinic_id:
            raise CommandError("--clinic-id is required for compliance report")
        
        try:
            clinic = Clinic.objects.get(id=clinic_id)
        except Clinic.DoesNotExist:
            raise CommandError(f"Clinic with ID {clinic_id} not found")
        
        # Parse dates
        end_date = timezone.now()
        if options['end_date']:
            end_date = datetime.strptime(options['end_date'], '%Y-%m-%d')
            end_date = timezone.make_aware(end_date)
        
        start_date = end_date - timedelta(days=options['days'])
        if options['start_date']:
            start_date = datetime.strptime(options['start_date'], '%Y-%m-%d')
            start_date = timezone.make_aware(start_date)
        
        self.stdout.write(f"Generating compliance report for {clinic.name}")
        self.stdout.write(f"Period: {start_date.date()} to {end_date.date()}")
        
        # Generate report
        report = audit_service.generate_compliance_report(clinic, start_date, end_date)
        
        if options['format'] == 'json':
            self.stdout.write(json.dumps(report, indent=2))
        else:
            # Display formatted report
            self.stdout.write(f"\nCompliance Report for {report['clinic_name']}")
            self.stdout.write('=' * 50)
            
            summary = report['summary']
            self.stdout.write(f"Total Actions: {summary['total_actions']}")
            self.stdout.write(f"Unique Users: {summary['unique_users']}")
            self.stdout.write(f"Sensitive Data Access: {summary['sensitive_data_access_count']}")
            self.stdout.write(f"External Access: {summary['external_access_count']}")
            self.stdout.write(f"Unauthorized Attempts: {summary['unauthorized_attempts']}")
            self.stdout.write(f"Document Operations: {summary['document_operations']}")
            
            # Compliance indicators
            indicators = report['compliance_indicators']
            self.stdout.write(f"\nCompliance Indicators:")
            for key, value in indicators.items():
                status_color = self.style.SUCCESS if value else self.style.WARNING
                self.stdout.write(f"  {key.replace('_', ' ').title()}: {status_color(str(value))}")

    def cleanup_old_logs(self, options):
        """Clean up old audit logs."""
        cleanup_days = options['cleanup_days']
        cutoff_date = timezone.now() - timedelta(days=cleanup_days)
        
        self.stdout.write(f"Cleaning up audit logs older than {cleanup_days} days")
        self.stdout.write(f"Cutoff date: {cutoff_date.date()}")
        
        # Get logs to delete
        old_logs = AuditLog.objects.filter(timestamp__lt=cutoff_date)
        
        if options['clinic_id']:
            old_logs = old_logs.filter(clinic_id=options['clinic_id'])
        
        count = old_logs.count()
        
        if count == 0:
            self.stdout.write("No old audit logs found to clean up.")
            return
        
        # Show what will be deleted
        self.stdout.write(f"Found {count} audit logs to delete:")
        
        action_counts = old_logs.values('action').annotate(count=Count('id'))
        for action_count in action_counts:
            self.stdout.write(f"  {action_count['action']}: {action_count['count']} logs")
        
        # Confirm deletion
        confirm = input(f"\nAre you sure you want to delete {count} audit logs? (yes/no): ")
        
        if confirm.lower() == 'yes':
            deleted_count, _ = old_logs.delete()
            self.stdout.write(
                self.style.SUCCESS(f"Successfully deleted {deleted_count} old audit logs.")
            )
        else:
            self.stdout.write("Cleanup cancelled.")

    def export_audit_logs(self, options):
        """Export audit logs to file."""
        output_file = options.get('output_file')
        if not output_file:
            raise CommandError("--output-file is required for export")
        
        # Build query
        queryset = AuditLog.objects.filter(
            action__in=list(audit_service.CLINICAL_ACTIONS.keys())
        )
        
        if options['clinic_id']:
            queryset = queryset.filter(clinic_id=options['clinic_id'])
        
        if options['start_date']:
            start_date = datetime.strptime(options['start_date'], '%Y-%m-%d')
            start_date = timezone.make_aware(start_date)
            queryset = queryset.filter(timestamp__gte=start_date)
        
        if options['end_date']:
            end_date = datetime.strptime(options['end_date'], '%Y-%m-%d')
            end_date = timezone.make_aware(end_date)
            queryset = queryset.filter(timestamp__lte=end_date)
        
        queryset = queryset.order_by('-timestamp')
        
        self.stdout.write(f"Exporting {queryset.count()} audit logs to {output_file}")
        
        # Export to JSON
        export_data = []
        for log in queryset:
            export_data.append({
                'id': log.id,
                'timestamp': log.timestamp.isoformat(),
                'user': log.user.username if log.user else None,
                'action': log.action,
                'resource_type': log.resource_type,
                'resource_id': log.resource_id,
                'ip_address': log.ip_address,
                'user_agent': log.user_agent,
                'details': log.details,
                'clinic_id': log.clinic.id if log.clinic else None,
                'clinic_name': log.clinic.name if log.clinic else None
            })
        
        with open(output_file, 'w') as f:
            json.dump(export_data, f, indent=2)
        
        self.stdout.write(self.style.SUCCESS(f"Successfully exported {len(export_data)} audit logs."))

    def show_user_activity(self, options):
        """Show user activity report."""
        user_id = options.get('user_id')
        if not user_id:
            raise CommandError("--user-id is required for user activity report")
        
        from django.contrib.auth import get_user_model
        User = get_user_model()
        
        try:
            user = User.objects.get(id=user_id)
        except User.DoesNotExist:
            raise CommandError(f"User with ID {user_id} not found")
        
        # Parse dates
        end_date = timezone.now()
        if options['end_date']:
            end_date = datetime.strptime(options['end_date'], '%Y-%m-%d')
            end_date = timezone.make_aware(end_date)
        
        start_date = end_date - timedelta(days=options['days'])
        if options['start_date']:
            start_date = datetime.strptime(options['start_date'], '%Y-%m-%d')
            start_date = timezone.make_aware(start_date)
        
        # Get user activity
        user_logs = AuditLog.objects.filter(
            user=user,
            timestamp__gte=start_date,
            timestamp__lte=end_date,
            action__in=list(audit_service.CLINICAL_ACTIONS.keys())
        ).order_by('-timestamp')
        
        self.stdout.write(f"User Activity Report for {user.get_full_name()}")
        self.stdout.write(f"Period: {start_date.date()} to {end_date.date()}")
        self.stdout.write('=' * 50)
        
        self.stdout.write(f"Total Actions: {user_logs.count()}")
        
        # Action breakdown
        action_counts = user_logs.values('action').annotate(
            count=Count('id')
        ).order_by('-count')
        
        self.stdout.write(f"\nAction Breakdown:")
        for action in action_counts:
            action_name = audit_service.CLINICAL_ACTIONS.get(action['action'], action['action'])
            self.stdout.write(f"  {action_name}: {action['count']}")
        
        # Recent activity
        self.stdout.write(f"\nRecent Activity (Last 10):")
        for log in user_logs[:10]:
            action_name = audit_service.CLINICAL_ACTIONS.get(log.action, log.action)
            self.stdout.write(f"  {log.timestamp.strftime('%Y-%m-%d %H:%M')} - {action_name}")

    def show_resource_audit(self, options):
        """Show audit trail for a specific resource."""
        resource_type = options.get('resource_type')
        resource_id = options.get('resource_id')
        
        if not resource_type or not resource_id:
            raise CommandError("--resource-type and --resource-id are required for resource audit")
        
        # Get audit logs for the resource
        resource_logs = AuditLog.objects.filter(
            resource_type=resource_type,
            resource_id=resource_id,
            action__in=list(audit_service.CLINICAL_ACTIONS.keys())
        ).order_by('-timestamp')
        
        if options['clinic_id']:
            resource_logs = resource_logs.filter(clinic_id=options['clinic_id'])
        
        self.stdout.write(f"Resource Audit Trail")
        self.stdout.write(f"Resource: {resource_type}:{resource_id}")
        self.stdout.write('=' * 50)
        
        self.stdout.write(f"Total Audit Entries: {resource_logs.count()}")
        
        if resource_logs.exists():
            self.stdout.write(f"\nAudit Trail:")
            for log in resource_logs[:20]:  # Show last 20 entries
                user_name = log.user.get_full_name() if log.user else 'System'
                action_name = audit_service.CLINICAL_ACTIONS.get(log.action, log.action)
                self.stdout.write(
                    f"  {log.timestamp.strftime('%Y-%m-%d %H:%M')} - "
                    f"{user_name} - {action_name} - {log.ip_address or 'N/A'}"
                )

    def show_audit_statistics(self, options):
        """Show detailed audit statistics."""
        self.stdout.write(self.style.SUCCESS('Detailed Audit Statistics'))
        self.stdout.write('=' * 50)
        
        # Time period
        end_date = timezone.now()
        start_date = end_date - timedelta(days=options['days'])
        
        if options['start_date']:
            start_date = datetime.strptime(options['start_date'], '%Y-%m-%d')
            start_date = timezone.make_aware(start_date)
        
        if options['end_date']:
            end_date = datetime.strptime(options['end_date'], '%Y-%m-%d')
            end_date = timezone.make_aware(end_date)
        
        self.stdout.write(f"Period: {start_date.date()} to {end_date.date()}")
        
        # Base queryset
        logs = AuditLog.objects.filter(
            timestamp__gte=start_date,
            timestamp__lte=end_date,
            action__in=list(audit_service.CLINICAL_ACTIONS.keys())
        )
        
        if options['clinic_id']:
            logs = logs.filter(clinic_id=options['clinic_id'])
        
        # Overall statistics
        total_logs = logs.count()
        unique_users = logs.values('user').distinct().count()
        unique_ips = logs.values('ip_address').distinct().count()
        
        self.stdout.write(f"\nOverall Statistics:")
        self.stdout.write(f"  Total Actions: {total_logs}")
        self.stdout.write(f"  Unique Users: {unique_users}")
        self.stdout.write(f"  Unique IP Addresses: {unique_ips}")
        
        # Action statistics
        action_stats = logs.values('action').annotate(
            count=Count('id')
        ).order_by('-count')
        
        self.stdout.write(f"\nTop Actions:")
        for action in action_stats[:10]:
            action_name = audit_service.CLINICAL_ACTIONS.get(action['action'], action['action'])
            self.stdout.write(f"  {action_name}: {action['count']}")
        
        # Resource statistics
        resource_stats = logs.values('resource_type').annotate(
            count=Count('id')
        ).order_by('-count')
        
        self.stdout.write(f"\nResource Type Statistics:")
        for resource in resource_stats:
            resource_name = audit_service.CLINICAL_RESOURCE_TYPES.get(
                resource['resource_type'], 
                resource['resource_type']
            )
            self.stdout.write(f"  {resource_name}: {resource['count']}")
        
        # User statistics
        user_stats = logs.values(
            'user__username', 'user__first_name', 'user__last_name'
        ).annotate(
            count=Count('id')
        ).order_by('-count')
        
        self.stdout.write(f"\nTop Users:")
        for user in user_stats[:10]:
            username = user['user__username'] or 'System'
            full_name = f"{user['user__first_name'] or ''} {user['user__last_name'] or ''}".strip()
            display_name = full_name if full_name else username
            self.stdout.write(f"  {display_name}: {user['count']}")
        
        # Daily activity
        self.stdout.write(f"\nDaily Activity (Last 7 Days):")
        for i in range(7):
            day = end_date - timedelta(days=i)
            day_start = day.replace(hour=0, minute=0, second=0, microsecond=0)
            day_end = day.replace(hour=23, minute=59, second=59, microsecond=999999)
            
            day_count = logs.filter(
                timestamp__gte=day_start,
                timestamp__lte=day_end
            ).count()
            
            self.stdout.write(f"  {day.strftime('%Y-%m-%d')}: {day_count} actions")