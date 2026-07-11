"""
Django management command for managing AWS Lambda processing

This command provides various operations for managing Lambda functions,
SQS queues, and auto-scaling for clinical document processing.
"""

import json
import time
from datetime import datetime, timezone
from django.core.management.base import BaseCommand, CommandError
from django.conf import settings

from ...services.lambda_sqs_service import LambdaSQSService
from ...services.lambda_autoscaler import LambdaAutoScaler
from ...models import ClinicalDocument


class Command(BaseCommand):
    help = 'Manage AWS Lambda processing for clinical documents'
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.lambda_service = LambdaSQSService()
        self.autoscaler = LambdaAutoScaler()
    
    def add_arguments(self, parser):
        parser.add_argument(
            'action',
            choices=[
                'queue_document',
                'queue_batch',
                'process_results',
                'get_metrics',
                'auto_scale',
                'scale_to',
                'monitor',
                'reprocess_failed',
                'purge_dlq',
                'test_lambda',
                'scaling_history',
                'scaling_stats'
            ],
            help='Action to perform'
        )
        
        parser.add_argument(
            '--document-id',
            type=str,
            help='Document ID for single document operations'
        )
        
        parser.add_argument(
            '--document-ids',
            type=str,
            nargs='+',
            help='Multiple document IDs for batch operations'
        )
        
        parser.add_argument(
            '--priority',
            choices=['high', 'normal', 'low'],
            default='normal',
            help='Processing priority'
        )
        
        parser.add_argument(
            '--concurrency',
            type=int,
            help='Target concurrency for scaling operations'
        )
        
        parser.add_argument(
            '--max-age-hours',
            type=int,
            default=24,
            help='Maximum age in hours for reprocessing failed documents'
        )
        
        parser.add_argument(
            '--monitor-duration',
            type=int,
            default=300,
            help='Duration in seconds for monitoring mode'
        )
        
        parser.add_argument(
            '--interval',
            type=int,
            default=30,
            help='Interval in seconds between monitoring checks'
        )
        
        parser.add_argument(
            '--auto-scale-cycles',
            type=int,
            default=1,
            help='Number of auto-scaling cycles to run'
        )
        
        parser.add_argument(
            '--limit',
            type=int,
            default=50,
            help='Limit for history and statistics queries'
        )
    
    def handle(self, *args, **options):
        action = options['action']
        
        try:
            if action == 'queue_document':
                self.queue_document(options)
            elif action == 'queue_batch':
                self.queue_batch(options)
            elif action == 'process_results':
                self.process_results(options)
            elif action == 'get_metrics':
                self.get_metrics(options)
            elif action == 'auto_scale':
                self.auto_scale(options)
            elif action == 'scale_to':
                self.scale_to(options)
            elif action == 'monitor':
                self.monitor(options)
            elif action == 'reprocess_failed':
                self.reprocess_failed(options)
            elif action == 'purge_dlq':
                self.purge_dlq(options)
            elif action == 'test_lambda':
                self.test_lambda(options)
            elif action == 'scaling_history':
                self.scaling_history(options)
            elif action == 'scaling_stats':
                self.scaling_stats(options)
                
        except Exception as e:
            raise CommandError(f'Error executing {action}: {str(e)}')
    
    def queue_document(self, options):
        """Queue a single document for processing"""
        document_id = options.get('document_id')
        priority = options.get('priority', 'normal')
        
        if not document_id:
            raise CommandError('--document-id is required for queue_document action')
        
        success = self.lambda_service.queue_document_processing(document_id, priority)
        
        if success:
            self.stdout.write(
                self.style.SUCCESS(f'Document {document_id} queued successfully with priority {priority}')
            )
        else:
            self.stdout.write(
                self.style.ERROR(f'Failed to queue document {document_id}')
            )
    
    def queue_batch(self, options):
        """Queue multiple documents for batch processing"""
        document_ids = options.get('document_ids')
        priority = options.get('priority', 'normal')
        
        if not document_ids:
            raise CommandError('--document-ids is required for queue_batch action')
        
        success = self.lambda_service.queue_batch_processing(document_ids, priority)
        
        if success:
            self.stdout.write(
                self.style.SUCCESS(f'Batch of {len(document_ids)} documents queued successfully')
            )
        else:
            self.stdout.write(
                self.style.ERROR('Failed to queue batch processing')
            )
    
    def process_results(self, options):
        """Process messages from the results queue"""
        self.stdout.write('Processing results queue...')
        
        result = self.lambda_service.process_results_queue()
        
        self.stdout.write(
            self.style.SUCCESS(
                f"Processed {result['processed_count']} messages, "
                f"{result['error_count']} errors, "
                f"{result['total_messages']} total messages"
            )
        )
        
        if 'error' in result:
            self.stdout.write(
                self.style.ERROR(f"Error: {result['error']}")
            )
    
    def get_metrics(self, options):
        """Get current metrics for queues and Lambda functions"""
        self.stdout.write('Getting metrics...')
        
        # Get queue metrics
        queue_metrics = self.lambda_service.get_queue_metrics()
        lambda_metrics = self.lambda_service.get_lambda_metrics()
        
        self.stdout.write('\n=== Queue Metrics ===')
        if 'error' in queue_metrics:
            self.stdout.write(self.style.ERROR(f"Queue metrics error: {queue_metrics['error']}"))
        else:
            for queue_name, metrics in queue_metrics.items():
                self.stdout.write(f'{queue_name}:')
                for metric, value in metrics.items():
                    self.stdout.write(f'  {metric}: {value}')
        
        self.stdout.write('\n=== Lambda Metrics ===')
        if 'error' in lambda_metrics:
            self.stdout.write(self.style.ERROR(f"Lambda metrics error: {lambda_metrics['error']}"))
        else:
            for metric, value in lambda_metrics.items():
                self.stdout.write(f'{metric}: {value}')
    
    def auto_scale(self, options):
        """Run auto-scaling cycles"""
        cycles = options.get('auto_scale_cycles', 1)
        
        self.stdout.write(f'Running {cycles} auto-scaling cycle(s)...')
        
        for i in range(cycles):
            self.stdout.write(f'\n--- Cycle {i + 1} ---')
            
            result = self.autoscaler.run_auto_scaling_cycle()
            
            if result.get('execution_success', False):
                decision = result.get('decision', {})
                metrics = result.get('metrics', {})
                
                self.stdout.write(
                    self.style.SUCCESS(
                        f"Action: {decision.get('action', 'unknown')}, "
                        f"Target: {decision.get('target_concurrency', 0)}, "
                        f"Queue: {metrics.get('queue_depth', 0)}, "
                        f"Cost Impact: ${decision.get('estimated_cost_impact', 0):.4f}/hour"
                    )
                )
                
                self.stdout.write(f"Reason: {decision.get('reason', 'N/A')}")
                
            else:
                self.stdout.write(
                    self.style.ERROR(f"Cycle {i + 1} failed: {result.get('error', 'Unknown error')}")
                )
            
            # Wait between cycles
            if i < cycles - 1:
                time.sleep(30)
    
    def scale_to(self, options):
        """Scale to specific concurrency level"""
        concurrency = options.get('concurrency')
        
        if concurrency is None:
            raise CommandError('--concurrency is required for scale_to action')
        
        self.stdout.write(f'Scaling to {concurrency} concurrent executions...')
        
        success = self.lambda_service.scale_lambda_concurrency(concurrency)
        
        if success:
            self.stdout.write(
                self.style.SUCCESS(f'Successfully scaled to {concurrency} concurrent executions')
            )
        else:
            self.stdout.write(
                self.style.ERROR('Failed to scale Lambda concurrency')
            )
    
    def monitor(self, options):
        """Monitor Lambda processing in real-time"""
        duration = options.get('monitor_duration', 300)
        interval = options.get('interval', 30)
        
        self.stdout.write(f'Monitoring Lambda processing for {duration} seconds (interval: {interval}s)...')
        self.stdout.write('Press Ctrl+C to stop monitoring\n')
        
        start_time = time.time()
        
        try:
            while time.time() - start_time < duration:
                # Get current metrics
                queue_metrics = self.lambda_service.get_queue_metrics()
                lambda_metrics = self.lambda_service.get_lambda_metrics()
                
                # Get scaling metrics
                scaling_metrics = self.autoscaler.analyze_scaling_metrics()
                
                # Display current status
                timestamp = datetime.now().strftime('%H:%M:%S')
                queue_depth = queue_metrics.get('processing_queue', {}).get('approximate_number_of_messages', 0)
                concurrency = lambda_metrics.get('provisioned_concurrency', 0)
                processing_rate = scaling_metrics.processing_rate
                cost_per_hour = scaling_metrics.cost_per_hour
                
                self.stdout.write(
                    f'[{timestamp}] Queue: {queue_depth:3d} | '
                    f'Concurrency: {concurrency:2d} | '
                    f'Rate: {processing_rate:5.1f}/min | '
                    f'Cost: ${cost_per_hour:6.4f}/hr'
                )
                
                time.sleep(interval)
                
        except KeyboardInterrupt:
            self.stdout.write('\nMonitoring stopped by user')
    
    def reprocess_failed(self, options):
        """Reprocess failed documents"""
        max_age_hours = options.get('max_age_hours', 24)
        
        self.stdout.write(f'Reprocessing failed documents (max age: {max_age_hours} hours)...')
        
        requeued_count = self.lambda_service.reprocess_failed_documents(max_age_hours)
        
        self.stdout.write(
            self.style.SUCCESS(f'Requeued {requeued_count} failed documents for processing')
        )
    
    def purge_dlq(self, options):
        """Purge dead letter queue"""
        self.stdout.write('Purging dead letter queue...')
        
        success = self.lambda_service.purge_dead_letter_queue()
        
        if success:
            self.stdout.write(
                self.style.SUCCESS('Dead letter queue purged successfully')
            )
        else:
            self.stdout.write(
                self.style.ERROR('Failed to purge dead letter queue')
            )
    
    def test_lambda(self, options):
        """Test Lambda function with a sample payload"""
        self.stdout.write('Testing Lambda function...')
        
        test_payload = {
            'task_type': 'process_document',
            'document_id': 'test-document-id',
            's3_key': 'test/sample.pdf',
            's3_bucket': 'test-bucket',
            'content_type': 'application/pdf',
            'test_mode': True
        }
        
        result = self.lambda_service.invoke_lambda_directly(test_payload)
        
        if result.get('success', False):
            self.stdout.write(
                self.style.SUCCESS(f"Lambda test successful (status: {result['status_code']})")
            )
            
            payload = result.get('payload', {})
            if payload:
                self.stdout.write(f"Response: {json.dumps(payload, indent=2)}")
        else:
            self.stdout.write(
                self.style.ERROR(f"Lambda test failed: {result.get('error', 'Unknown error')}")
            )
    
    def scaling_history(self, options):
        """Show scaling history"""
        limit = options.get('limit', 50)
        
        self.stdout.write(f'Showing last {limit} scaling actions...')
        
        history = self.autoscaler.get_scaling_history(limit)
        
        if not history:
            self.stdout.write('No scaling history available')
            return
        
        self.stdout.write('\n=== Scaling History ===')
        for entry in history[-20:]:  # Show last 20 entries
            timestamp = entry.get('timestamp', 'N/A')
            action = entry.get('action', 'N/A')
            target = entry.get('target_concurrency', 0)
            reason = entry.get('reason', 'N/A')
            confidence = entry.get('confidence', 0.0)
            cost_impact = entry.get('cost_impact', 0.0)
            
            self.stdout.write(
                f'{timestamp[:19]} | {action:10} | Target: {target:2d} | '
                f'Confidence: {confidence:.2f} | Cost: ${cost_impact:+.4f}/hr'
            )
            self.stdout.write(f'  Reason: {reason}')
    
    def scaling_stats(self, options):
        """Show scaling statistics"""
        self.stdout.write('Getting scaling statistics...')
        
        stats = self.autoscaler.get_scaling_statistics()
        
        if 'error' in stats:
            self.stdout.write(self.style.ERROR(f"Error: {stats['error']}"))
            return
        
        if 'message' in stats:
            self.stdout.write(stats['message'])
            return
        
        self.stdout.write('\n=== Scaling Statistics ===')
        self.stdout.write(f"Total cycles: {stats.get('total_cycles', 0)}")
        self.stdout.write(f"Successful cycles: {stats.get('successful_cycles', 0)}")
        self.stdout.write(f"Success rate: {stats.get('success_rate', 0):.2%}")
        
        action_counts = stats.get('action_counts', {})
        self.stdout.write(f"Scale up actions: {action_counts.get('scale_up', 0)}")
        self.stdout.write(f"Scale down actions: {action_counts.get('scale_down', 0)}")
        self.stdout.write(f"Maintain actions: {action_counts.get('maintain', 0)}")
        
        self.stdout.write(f"Average queue depth: {stats.get('average_queue_depth', 0):.1f}")
        self.stdout.write(f"Average cost per hour: ${stats.get('average_cost_per_hour', 0):.4f}")
        
        last_cycle = stats.get('last_cycle')
        if last_cycle:
            self.stdout.write('\n=== Last Cycle ===')
            self.stdout.write(f"Timestamp: {last_cycle.get('timestamp', 'N/A')}")
            self.stdout.write(f"Success: {last_cycle.get('execution_success', False)}")
            
            decision = last_cycle.get('decision', {})
            if decision:
                self.stdout.write(f"Action: {decision.get('action', 'N/A')}")
                self.stdout.write(f"Target concurrency: {decision.get('target_concurrency', 0)}")
                self.stdout.write(f"Reason: {decision.get('reason', 'N/A')}")