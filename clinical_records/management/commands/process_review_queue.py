"""
Management command to process the manual review queue.

This command handles automatic processing of the review queue including:
- Creating reviews for low-confidence documents
- Escalating overdue reviews
- Rebalancing workload among reviewers
- Sending notifications
"""
import logging
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone
from datetime import timedelta

from users.models import Clinic
from clinical_records.services.review_queue_service import get_review_queue_service
from clinical_records.models import ManualReview, ReviewerProfile

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Process the manual review queue for clinical documents'
    
    def add_arguments(self, parser):
        parser.add_argument(
            '--clinic-id',
            type=str,
            help='Process only specific clinic (UUID)',
        )
        
        parser.add_argument(
            '--confidence-threshold',
            type=float,
            default=0.7,
            help='OCR confidence threshold for creating reviews (default: 0.7)',
        )
        
        parser.add_argument(
            '--escalation-hours',
            type=int,
            default=24,
            help='Hours before escalating overdue reviews (default: 24)',
        )
        
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be done without making changes',
        )
        
        parser.add_argument(
            '--skip-low-confidence',
            action='store_true',
            help='Skip processing low confidence documents',
        )
        
        parser.add_argument(
            '--skip-escalation',
            action='store_true',
            help='Skip escalating overdue reviews',
        )
        
        parser.add_argument(
            '--skip-rebalancing',
            action='store_true',
            help='Skip workload rebalancing',
        )
        
        parser.add_argument(
            '--skip-notifications',
            action='store_true',
            help='Skip sending notifications',
        )
    
    def handle(self, *args, **options):
        """Main command handler"""
        self.verbosity = options['verbosity']
        self.dry_run = options['dry_run']
        
        if self.dry_run:
            self.stdout.write(
                self.style.WARNING('DRY RUN MODE - No changes will be made')
            )
        
        # Get service instance
        service = get_review_queue_service()
        
        # Get clinics to process
        clinics = self._get_clinics_to_process(options['clinic_id'])
        
        if not clinics:
            raise CommandError('No clinics found to process')
        
        self.stdout.write(f'Processing {len(clinics)} clinic(s)...')
        
        total_stats = {
            'clinics_processed': 0,
            'total_reviews_created': 0,
            'total_reviews_escalated': 0,
            'total_reviews_reassigned': 0,
            'total_notifications_sent': 0,
            'total_errors': 0,
        }
        
        for clinic in clinics:
            try:
                self.stdout.write(f'\\nProcessing clinic: {clinic.name} ({clinic.id})')
                
                clinic_stats = self._process_clinic(
                    clinic, 
                    service, 
                    options
                )
                
                # Aggregate statistics
                total_stats['clinics_processed'] += 1
                total_stats['total_reviews_created'] += clinic_stats.get('reviews_created', 0)
                total_stats['total_reviews_escalated'] += clinic_stats.get('reviews_escalated', 0)
                total_stats['total_reviews_reassigned'] += clinic_stats.get('reviews_reassigned', 0)
                total_stats['total_notifications_sent'] += clinic_stats.get('notifications_sent', 0)
                total_stats['total_errors'] += clinic_stats.get('errors', 0)
                
                if self.verbosity >= 2:
                    self._print_clinic_stats(clinic, clinic_stats)
                
            except Exception as e:
                self.stderr.write(
                    self.style.ERROR(f'Error processing clinic {clinic.name}: {e}')
                )
                total_stats['total_errors'] += 1
                logger.error(f'Error processing clinic {clinic.id}: {e}', exc_info=True)
        
        # Print summary
        self._print_summary(total_stats)
    
    def _get_clinics_to_process(self, clinic_id=None):
        """Get list of clinics to process"""
        if clinic_id:
            try:
                return [Clinic.objects.get(id=clinic_id)]
            except Clinic.DoesNotExist:
                raise CommandError(f'Clinic with ID {clinic_id} not found')
        else:
            return Clinic.objects.filter(is_active=True)
    
    def _process_clinic(self, clinic, service, options):
        """Process review queue for a single clinic"""
        clinic_stats = {
            'reviews_created': 0,
            'reviews_escalated': 0,
            'reviews_reassigned': 0,
            'notifications_sent': 0,
            'errors': 0,
        }
        
        # 1. Process low confidence documents
        if not options['skip_low_confidence']:
            if self.verbosity >= 1:
                self.stdout.write('  Processing low confidence documents...')
            
            if not self.dry_run:
                try:
                    low_conf_stats = service.process_low_confidence_documents(
                        confidence_threshold=options['confidence_threshold']
                    )
                    clinic_stats['reviews_created'] = low_conf_stats['reviews_created']
                    clinic_stats['errors'] += low_conf_stats['errors']
                    
                    if self.verbosity >= 1:
                        self.stdout.write(
                            f'    Created {low_conf_stats[\"reviews_created\"]} reviews'
                        )
                except Exception as e:
                    self.stderr.write(f'    Error processing low confidence documents: {e}')
                    clinic_stats['errors'] += 1
            else:
                # Dry run - just count what would be processed
                from clinical_records.models import ClinicalDocument
                count = ClinicalDocument.objects.filter(
                    clinical_record__clinic=clinic,
                    processing_status='completed',
                    requires_manual_review=False,
                    ocr_confidence__lt=options['confidence_threshold']
                ).exclude(
                    manual_reviews__status__in=['pending', 'in_progress']
                ).count()
                
                self.stdout.write(f'    Would create {count} reviews')
        
        # 2. Escalate overdue reviews
        if not options['skip_escalation']:
            if self.verbosity >= 1:
                self.stdout.write('  Escalating overdue reviews...')
            
            if not self.dry_run:
                try:
                    escalation_stats = service.escalate_overdue_reviews(
                        max_age_hours=options['escalation_hours']
                    )
                    clinic_stats['reviews_escalated'] = escalation_stats['reviews_escalated']
                    clinic_stats['errors'] += escalation_stats['errors']
                    
                    if self.verbosity >= 1:
                        self.stdout.write(
                            f'    Escalated {escalation_stats[\"reviews_escalated\"]} reviews'
                        )
                except Exception as e:
                    self.stderr.write(f'    Error escalating reviews: {e}')
                    clinic_stats['errors'] += 1
            else:
                # Dry run - count overdue reviews
                cutoff_time = timezone.now() - timedelta(hours=options['escalation_hours'])
                count = ManualReview.objects.filter(
                    document__clinical_record__clinic=clinic,
                    status__in=['pending', 'in_progress'],
                    created_at__lt=cutoff_time,
                    requires_escalation=False
                ).count()
                
                self.stdout.write(f'    Would escalate {count} reviews')
        
        # 3. Rebalance workload
        if not options['skip_rebalancing']:
            if self.verbosity >= 1:
                self.stdout.write('  Rebalancing workload...')
            
            if not self.dry_run:
                try:
                    rebalance_stats = service.rebalance_workload(clinic)
                    clinic_stats['reviews_reassigned'] = rebalance_stats['reviews_reassigned']
                    clinic_stats['errors'] += rebalance_stats['errors']
                    
                    if self.verbosity >= 1:
                        self.stdout.write(
                            f'    Reassigned {rebalance_stats[\"reviews_reassigned\"]} reviews'
                        )
                except Exception as e:
                    self.stderr.write(f'    Error rebalancing workload: {e}')
                    clinic_stats['errors'] += 1
            else:
                self.stdout.write('    Would rebalance workload (dry run)')
        
        # 4. Send notifications
        if not options['skip_notifications']:
            if self.verbosity >= 1:
                self.stdout.write('  Sending notifications...')
            
            if not self.dry_run:
                try:
                    notification_stats = service.send_review_notifications(clinic)
                    clinic_stats['notifications_sent'] = sum(notification_stats.values())
                    
                    if self.verbosity >= 1:
                        self.stdout.write(
                            f'    Sent {clinic_stats[\"notifications_sent\"]} notifications'
                        )
                except Exception as e:
                    self.stderr.write(f'    Error sending notifications: {e}')
                    clinic_stats['errors'] += 1
            else:
                self.stdout.write('    Would send notifications (dry run)')
        
        return clinic_stats
    
    def _print_clinic_stats(self, clinic, stats):
        """Print detailed statistics for a clinic"""
        self.stdout.write(f'  Clinic {clinic.name} statistics:')
        self.stdout.write(f'    Reviews created: {stats[\"reviews_created\"]}')
        self.stdout.write(f'    Reviews escalated: {stats[\"reviews_escalated\"]}')
        self.stdout.write(f'    Reviews reassigned: {stats[\"reviews_reassigned\"]}')
        self.stdout.write(f'    Notifications sent: {stats[\"notifications_sent\"]}')
        if stats['errors'] > 0:
            self.stdout.write(
                self.style.ERROR(f'    Errors: {stats[\"errors\"]}')
            )
    
    def _print_summary(self, stats):
        """Print overall summary statistics"""
        self.stdout.write('\\n' + '='*50)
        self.stdout.write(self.style.SUCCESS('PROCESSING SUMMARY'))
        self.stdout.write('='*50)
        
        self.stdout.write(f'Clinics processed: {stats[\"clinics_processed\"]}')
        self.stdout.write(f'Total reviews created: {stats[\"total_reviews_created\"]}')
        self.stdout.write(f'Total reviews escalated: {stats[\"total_reviews_escalated\"]}')
        self.stdout.write(f'Total reviews reassigned: {stats[\"total_reviews_reassigned\"]}')
        self.stdout.write(f'Total notifications sent: {stats[\"total_notifications_sent\"]}')
        
        if stats['total_errors'] > 0:
            self.stdout.write(
                self.style.ERROR(f'Total errors: {stats[\"total_errors\"]}')
            )
        else:
            self.stdout.write(self.style.SUCCESS('No errors encountered'))
        
        if self.dry_run:
            self.stdout.write(
                self.style.WARNING('\\nThis was a dry run - no changes were made')
            )"