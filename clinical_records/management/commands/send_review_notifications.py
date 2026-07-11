"""
Management command to send review queue notifications.

This command can be run periodically (e.g., via cron) to send notifications
for overdue reviews, new assignments, and escalations.
"""
from django.core.management.base import BaseCommand
from django.utils import timezone
from users.models import Clinic
from clinical_records.services.review_queue_service import ReviewQueueService


class Command(BaseCommand):
    help = 'Send notifications for review queue events'
    
    def add_arguments(self, parser):
        parser.add_argument(
            '--clinic-id',
            type=str,
            help='Send notifications for specific clinic only'
        )
        
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be done without actually sending notifications'
        )
    
    def handle(self, *args, **options):
        service = ReviewQueueService()
        clinic_id = options.get('clinic_id')
        dry_run = options.get('dry_run', False)
        
        if dry_run:
            self.stdout.write(
                self.style.WARNING('DRY RUN MODE - No notifications will be sent')
            )
        
        # Get clinics to process
        if clinic_id:
            try:
                clinics = [Clinic.objects.get(id=clinic_id)]
            except Clinic.DoesNotExist:
                self.stdout.write(
                    self.style.ERROR(f'Clinic with ID {clinic_id} not found')
                )
                return
        else:
            clinics = Clinic.objects.filter(is_active=True)
        
        total_stats = {
            'overdue_notifications': 0,
            'assignment_notifications': 0,
            'escalation_notifications': 0,
        }
        
        for clinic in clinics:
            self.stdout.write(f'Processing notifications for clinic: {clinic.name}')
            
            if not dry_run:
                stats = service.send_review_notifications(clinic)
                
                # Update totals
                for key in total_stats:
                    total_stats[key] += stats[key]
                
                self.stdout.write(
                    f'  - Overdue notifications: {stats["overdue_notifications"]}'
                )
                self.stdout.write(
                    f'  - Assignment notifications: {stats["assignment_notifications"]}'
                )
                self.stdout.write(
                    f'  - Escalation notifications: {stats["escalation_notifications"]}'
                )
            else:
                # In dry run, just count what would be processed
                from clinical_records.models import ManualReview
                from datetime import timedelta
                
                overdue_count = ManualReview.objects.filter(
                    document__clinical_record__clinic=clinic,
                    due_date__lt=timezone.now(),
                    status__in=['pending', 'in_progress']
                ).count()
                
                recent_assignments = ManualReview.objects.filter(
                    document__clinical_record__clinic=clinic,
                    assigned_at__gte=timezone.now() - timedelta(hours=1),
                    assigned_to__isnull=False
                ).count()
                
                recent_escalations = ManualReview.objects.filter(
                    document__clinical_record__clinic=clinic,
                    status='escalated',
                    escalated_at__gte=timezone.now() - timedelta(hours=1)
                ).count()
                
                self.stdout.write(
                    f'  - Would send {overdue_count} overdue notifications'
                )
                self.stdout.write(
                    f'  - Would send {recent_assignments} assignment notifications'
                )
                self.stdout.write(
                    f'  - Would send {recent_escalations} escalation notifications'
                )
        
        if not dry_run:
            self.stdout.write(
                self.style.SUCCESS(
                    f'Successfully sent {sum(total_stats.values())} notifications'
                )
            )
        else:
            self.stdout.write(
                self.style.SUCCESS('Dry run completed')
            )