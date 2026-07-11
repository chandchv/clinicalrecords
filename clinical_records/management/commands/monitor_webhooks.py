"""
Management command for monitoring webhook health and performance.

This command provides utilities for monitoring webhook configurations,
checking delivery statistics, and managing webhook health.
"""

import json
from datetime import timedelta
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone
from django.db.models import Count, Q

from clinical_records.models import WebhookConfiguration, WebhookDelivery


class Command(BaseCommand):
    help = 'Monitor webhook configurations and deliveries'

    def add_arguments(self, parser):
        parser.add_argument(
            '--action',
            type=str,
            choices=['status', 'stats', 'health-check', 'retry-failed', 'cleanup'],
            default='status',
            help='Action to perform'
        )
        
        parser.add_argument(
            '--clinic-id',
            type=int,
            help='Filter by specific clinic ID'
        )
        
        parser.add_argument(
            '--webhook-id',
            type=int,
            help='Filter by specific webhook configuration ID'
        )
        
        parser.add_argument(
            '--days',
            type=int,
            default=7,
            help='Number of days to look back for statistics (default: 7)'
        )
        
        parser.add_argument(
            '--cleanup-days',
            type=int,
            default=30,
            help='Delete delivery records older than this many days (default: 30)'
        )

    def handle(self, *args, **options):
        action = options['action']
        
        if action == 'status':
            self.show_webhook_status(options)
        elif action == 'stats':
            self.show_webhook_statistics(options)
        elif action == 'health-check':
            self.perform_health_check(options)
        elif action == 'retry-failed':
            self.retry_failed_deliveries(options)
        elif action == 'cleanup':
            self.cleanup_old_deliveries(options)

    def show_webhook_status(self, options):
        """Show current status of webhook configurations."""
        self.stdout.write(self.style.SUCCESS('Webhook Configuration Status'))
        self.stdout.write('=' * 50)
        
        queryset = WebhookConfiguration.objects.all()
        
        if options['clinic_id']:
            queryset = queryset.filter(clinic_id=options['clinic_id'])
        
        if options['webhook_id']:
            queryset = queryset.filter(id=options['webhook_id'])
        
        for webhook in queryset.select_related('clinic'):
            status_color = self.style.SUCCESS if webhook.is_active else self.style.ERROR
            
            self.stdout.write(f"\nWebhook: {webhook.name}")
            self.stdout.write(f"  Clinic: {webhook.clinic.name}")
            self.stdout.write(f"  URL: {webhook.url}")
            self.stdout.write(f"  Status: {status_color(webhook.status)}")
            self.stdout.write(f"  Active: {status_color(str(webhook.is_active))}")
            self.stdout.write(f"  Events: {', '.join(webhook.enabled_events) if webhook.enabled_events else 'All events'}")
            self.stdout.write(f"  Total Sent: {webhook.total_sent}")
            self.stdout.write(f"  Total Failed: {webhook.total_failed}")
            
            if webhook.total_sent + webhook.total_failed > 0:
                success_rate = (webhook.total_sent / (webhook.total_sent + webhook.total_failed)) * 100
                rate_color = self.style.SUCCESS if success_rate >= 90 else self.style.WARNING if success_rate >= 70 else self.style.ERROR
                self.stdout.write(f"  Success Rate: {rate_color(f'{success_rate:.1f}%')}")
            
            if webhook.last_sent_at:
                self.stdout.write(f"  Last Sent: {webhook.last_sent_at}")
            
            if webhook.last_failed_at:
                self.stdout.write(f"  Last Failed: {webhook.last_failed_at}")
            
            if webhook.last_error:
                self.stdout.write(f"  Last Error: {webhook.last_error[:100]}...")

    def show_webhook_statistics(self, options):
        """Show detailed webhook delivery statistics."""
        days = options['days']
        since_date = timezone.now() - timedelta(days=days)
        
        self.stdout.write(self.style.SUCCESS(f'Webhook Statistics (Last {days} days)'))
        self.stdout.write('=' * 50)
        
        queryset = WebhookDelivery.objects.filter(created_at__gte=since_date)
        
        if options['clinic_id']:
            queryset = queryset.filter(clinic_id=options['clinic_id'])
        
        if options['webhook_id']:
            queryset = queryset.filter(webhook_config_id=options['webhook_id'])
        
        # Overall statistics
        total_deliveries = queryset.count()
        sent_deliveries = queryset.filter(status='sent').count()
        failed_deliveries = queryset.filter(status='failed').count()
        pending_deliveries = queryset.filter(status='pending').count()
        retrying_deliveries = queryset.filter(status='retrying').count()
        
        self.stdout.write(f"\nOverall Statistics:")
        self.stdout.write(f"  Total Deliveries: {total_deliveries}")
        self.stdout.write(f"  Sent: {self.style.SUCCESS(str(sent_deliveries))}")
        self.stdout.write(f"  Failed: {self.style.ERROR(str(failed_deliveries))}")
        self.stdout.write(f"  Pending: {self.style.WARNING(str(pending_deliveries))}")
        self.stdout.write(f"  Retrying: {self.style.WARNING(str(retrying_deliveries))}")
        
        if total_deliveries > 0:
            success_rate = (sent_deliveries / total_deliveries) * 100
            self.stdout.write(f"  Success Rate: {success_rate:.1f}%")
        
        # Statistics by event type
        event_stats = queryset.values('event_type').annotate(
            total=Count('id'),
            sent=Count('id', filter=Q(status='sent')),
            failed=Count('id', filter=Q(status='failed'))
        ).order_by('-total')
        
        if event_stats:
            self.stdout.write(f"\nStatistics by Event Type:")
            for stat in event_stats:
                success_rate = (stat['sent'] / stat['total']) * 100 if stat['total'] > 0 else 0
                self.stdout.write(f"  {stat['event_type']}: {stat['total']} total, {stat['sent']} sent, {stat['failed']} failed ({success_rate:.1f}% success)")
        
        # Statistics by webhook configuration
        webhook_stats = queryset.values('webhook_config__name', 'webhook_config__id').annotate(
            total=Count('id'),
            sent=Count('id', filter=Q(status='sent')),
            failed=Count('id', filter=Q(status='failed'))
        ).order_by('-total')
        
        if webhook_stats:
            self.stdout.write(f"\nStatistics by Webhook Configuration:")
            for stat in webhook_stats:
                success_rate = (stat['sent'] / stat['total']) * 100 if stat['total'] > 0 else 0
                self.stdout.write(f"  {stat['webhook_config__name']}: {stat['total']} total, {stat['sent']} sent, {stat['failed']} failed ({success_rate:.1f}% success)")

    def perform_health_check(self, options):
        """Perform health check on webhook configurations."""
        self.stdout.write(self.style.SUCCESS('Webhook Health Check'))
        self.stdout.write('=' * 50)
        
        queryset = WebhookConfiguration.objects.all()
        
        if options['clinic_id']:
            queryset = queryset.filter(clinic_id=options['clinic_id'])
        
        issues_found = 0
        
        for webhook in queryset.select_related('clinic'):
            issues = []
            
            # Check if webhook is inactive
            if not webhook.is_active:
                issues.append("Webhook is inactive")
            
            # Check if webhook status is failed
            if webhook.status == 'failed':
                issues.append("Webhook status is 'failed'")
            
            # Check high failure rate
            total_attempts = webhook.total_sent + webhook.total_failed
            if total_attempts > 10:  # Only check if there have been enough attempts
                failure_rate = (webhook.total_failed / total_attempts) * 100
                if failure_rate > 50:
                    issues.append(f"High failure rate: {failure_rate:.1f}%")
            
            # Check if webhook hasn't been used recently
            if webhook.last_sent_at:
                days_since_last_sent = (timezone.now() - webhook.last_sent_at).days
                if days_since_last_sent > 7:
                    issues.append(f"No successful deliveries in {days_since_last_sent} days")
            elif webhook.total_sent == 0 and webhook.created_at < timezone.now() - timedelta(days=1):
                issues.append("Webhook has never sent successfully")
            
            # Check for recent errors
            if webhook.last_failed_at and webhook.last_failed_at > timezone.now() - timedelta(hours=24):
                issues.append(f"Recent failure: {webhook.last_error[:50]}...")
            
            if issues:
                issues_found += len(issues)
                self.stdout.write(f"\n{self.style.ERROR('ISSUES FOUND')} - {webhook.name} ({webhook.clinic.name}):")
                for issue in issues:
                    self.stdout.write(f"  - {issue}")
            else:
                self.stdout.write(f"{self.style.SUCCESS('OK')} - {webhook.name} ({webhook.clinic.name})")
        
        if issues_found == 0:
            self.stdout.write(f"\n{self.style.SUCCESS('All webhook configurations are healthy!')}")
        else:
            self.stdout.write(f"\n{self.style.WARNING(f'Found {issues_found} issues across webhook configurations.')}")

    def retry_failed_deliveries(self, options):
        """Retry failed webhook deliveries."""
        from django_q.tasks import async_task
        
        self.stdout.write(self.style.SUCCESS('Retrying Failed Webhook Deliveries'))
        self.stdout.write('=' * 50)
        
        queryset = WebhookDelivery.objects.filter(status='failed')
        
        if options['clinic_id']:
            queryset = queryset.filter(clinic_id=options['clinic_id'])
        
        if options['webhook_id']:
            queryset = queryset.filter(webhook_config_id=options['webhook_id'])
        
        # Only retry deliveries that are not too old
        recent_failures = queryset.filter(
            failed_at__gte=timezone.now() - timedelta(hours=24)
        )
        
        retry_count = 0
        for delivery in recent_failures:
            try:
                async_task(
                    'clinical_records.services.webhook_service.retry_webhook_delivery',
                    delivery.id
                )
                retry_count += 1
                self.stdout.write(f"Scheduled retry for delivery {delivery.id} ({delivery.event_type})")
            except Exception as e:
                self.stdout.write(
                    self.style.ERROR(f"Failed to schedule retry for delivery {delivery.id}: {str(e)}")
                )
        
        self.stdout.write(f"\n{self.style.SUCCESS(f'Scheduled retry for {retry_count} failed deliveries.')}")

    def cleanup_old_deliveries(self, options):
        """Clean up old webhook delivery records."""
        cleanup_days = options['cleanup_days']
        cutoff_date = timezone.now() - timedelta(days=cleanup_days)
        
        self.stdout.write(self.style.SUCCESS(f'Cleaning up webhook deliveries older than {cleanup_days} days'))
        self.stdout.write('=' * 50)
        
        queryset = WebhookDelivery.objects.filter(created_at__lt=cutoff_date)
        
        if options['clinic_id']:
            queryset = queryset.filter(clinic_id=options['clinic_id'])
        
        if options['webhook_id']:
            queryset = queryset.filter(webhook_config_id=options['webhook_id'])
        
        count = queryset.count()
        
        if count == 0:
            self.stdout.write("No old delivery records found to clean up.")
            return
        
        # Show what will be deleted
        self.stdout.write(f"Found {count} delivery records to delete:")
        
        status_counts = queryset.values('status').annotate(count=Count('id'))
        for status_count in status_counts:
            self.stdout.write(f"  {status_count['status']}: {status_count['count']} records")
        
        # Confirm deletion
        confirm = input(f"\nAre you sure you want to delete {count} delivery records? (yes/no): ")
        
        if confirm.lower() == 'yes':
            deleted_count, _ = queryset.delete()
            self.stdout.write(self.style.SUCCESS(f"Successfully deleted {deleted_count} old delivery records."))
        else:
            self.stdout.write("Cleanup cancelled.")