"""
Django management command for Django-Q worker management and monitoring.
"""

import json
import time
from django.core.management.base import BaseCommand, CommandError
from clinical_records.services.django_q_manager import DjangoQManager

class Command(BaseCommand):
    help = 'Manage and monitor Django-Q workers'
    
    def add_arguments(self, parser):
        parser.add_argument(
            'action',
            choices=['status', 'health', 'restart', 'scale', 'clear-failed', 'retry-failed', 'monitor', 'task-details'],
            help='Action to perform'
        )
        parser.add_argument(
            '--workers',
            type=int,
            help='Number of workers for scaling'
        )
        parser.add_argument(
            '--task-id',
            type=str,
            help='Task ID for task-details action'
        )
        parser.add_argument(
            '--json',
            action='store_true',
            help='Output in JSON format'
        )
        parser.add_argument(
            '--continuous',
            action='store_true',
            help='Continuous monitoring (for monitor action)'
        )
        parser.add_argument(
            '--interval',
            type=int,
            default=30,
            help='Monitoring interval in seconds (default: 30)'
        )
        parser.add_argument(
            '--send-alerts',
            action='store_true',
            help='Send email alerts for health issues'
        )
        parser.add_argument(
            '--max-retries',
            type=int,
            default=3,
            help='Maximum retries for failed tasks (default: 3)'
        )
    
    def handle(self, *args, **options):
        manager = DjangoQManager()
        
        try:
            if options['action'] == 'status':
                self._handle_status(manager, options)
            elif options['action'] == 'health':
                self._handle_health(manager, options)
            elif options['action'] == 'restart':
                self._handle_restart(manager, options)
            elif options['action'] == 'scale':
                self._handle_scale(manager, options)
            elif options['action'] == 'clear-failed':
                self._handle_clear_failed(manager, options)
            elif options['action'] == 'retry-failed':
                self._handle_retry_failed(manager, options)
            elif options['action'] == 'monitor':
                self._handle_monitor(manager, options)
            elif options['action'] == 'task-details':
                self._handle_task_details(manager, options)
                
        except KeyboardInterrupt:
            self.stdout.write("Monitoring stopped by user")
        except Exception as e:
            raise CommandError(f"Error executing action: {str(e)}")
    
    def _handle_status(self, manager, options):
        """Handle status action."""
        status = manager.get_worker_status()
        
        if options['json']:
            self.stdout.write(json.dumps(status, indent=2))
        else:
            self._print_status(status)
    
    def _handle_health(self, manager, options):
        """Handle health check action."""
        health = manager.check_worker_health()
        
        if options['send_alerts']:
            manager.send_health_alert(health)
        
        if options['json']:
            self.stdout.write(json.dumps(health, indent=2))
        else:
            self._print_health(health)
    
    def _handle_restart(self, manager, options):
        """Handle restart action."""
        result = manager.restart_workers()
        
        if options['json']:
            self.stdout.write(json.dumps(result, indent=2))
        else:
            if result['success']:
                self.stdout.write(
                    self.style.SUCCESS(result['message'])
                )
            else:
                self.stdout.write(
                    self.style.ERROR(result['message'])
                )
    
    def _handle_scale(self, manager, options):
        """Handle scale action."""
        if not options['workers']:
            raise CommandError("--workers argument is required for scale action")
        
        result = manager.scale_workers(options['workers'])
        
        if options['json']:
            self.stdout.write(json.dumps(result, indent=2))
        else:
            if result['success']:
                self.stdout.write(
                    self.style.SUCCESS(result['message'])
                )
            else:
                self.stdout.write(
                    self.style.ERROR(result['message'])
                )
    
    def _handle_clear_failed(self, manager, options):
        """Handle clear failed tasks action."""
        result = manager.clear_failed_tasks()
        
        if options['json']:
            self.stdout.write(json.dumps(result, indent=2))
        else:
            if result['success']:
                self.stdout.write(
                    self.style.SUCCESS(result['message'])
                )
            else:
                self.stdout.write(
                    self.style.ERROR(result['message'])
                )
    
    def _handle_retry_failed(self, manager, options):
        """Handle retry failed tasks action."""
        result = manager.retry_failed_tasks(options['max_retries'])
        
        if options['json']:
            self.stdout.write(json.dumps(result, indent=2))
        else:
            if result['success']:
                self.stdout.write(
                    self.style.SUCCESS(result['message'])
                )
            else:
                self.stdout.write(
                    self.style.ERROR(result['message'])
                )
    
    def _handle_monitor(self, manager, options):
        """Handle continuous monitoring action."""
        self.stdout.write("Starting Django-Q monitoring...")
        self.stdout.write(f"Interval: {options['interval']} seconds")
        self.stdout.write("Press Ctrl+C to stop")
        self.stdout.write("-" * 50)
        
        try:
            while True:
                # Get status and health
                status = manager.get_worker_status()
                health = manager.check_worker_health()
                
                # Print summary
                self._print_monitoring_summary(status, health)
                
                # Send alerts if enabled
                if options['send_alerts']:
                    manager.send_health_alert(health)
                
                if not options['continuous']:
                    break
                
                time.sleep(options['interval'])
                
        except KeyboardInterrupt:
            self.stdout.write("\nMonitoring stopped")
    
    def _handle_task_details(self, manager, options):
        """Handle task details action."""
        if not options['task_id']:
            raise CommandError("--task-id argument is required for task-details action")
        
        details = manager.get_task_details(options['task_id'])
        
        if options['json']:
            self.stdout.write(json.dumps(details, indent=2))
        else:
            self._print_task_details(details)
    
    def _print_status(self, status):
        """Print worker status in human-readable format."""
        if 'error' in status:
            self.stdout.write(
                self.style.ERROR(f"Error getting status: {status['error']}")
            )
            return
        
        self.stdout.write(f"=== Django-Q Worker Status ===")
        self.stdout.write(f"Timestamp: {status['timestamp']}")
        self.stdout.write("")
        
        # Cluster configuration
        config = status.get('cluster_config', {})
        self.stdout.write("Cluster Configuration:")
        self.stdout.write(f"  Workers: {config.get('workers', 'unknown')}")
        self.stdout.write(f"  Timeout: {config.get('timeout', 'unknown')}s")
        self.stdout.write(f"  Recycle: {config.get('recycle', 'unknown')} tasks")
        self.stdout.write(f"  Queue Limit: {config.get('queue_limit', 'unknown')}")
        self.stdout.write("")
        
        # Queue information
        queue_info = status.get('queue_info', {})
        if 'error' not in queue_info:
            self.stdout.write("Queue Information:")
            self.stdout.write(f"  Pending: {queue_info.get('queue_length', 'unknown')}")
            self.stdout.write(f"  Processing: {queue_info.get('processing_length', 'unknown')}")
            self.stdout.write(f"  Failed: {queue_info.get('failed_length', 'unknown')}")
            self.stdout.write(f"  Redis Memory: {queue_info.get('redis_memory_used', 'unknown')}")
            self.stdout.write(f"  Redis Clients: {queue_info.get('redis_connected_clients', 'unknown')}")
            self.stdout.write("")
        
        # Worker processes
        workers = status.get('worker_processes', [])
        self.stdout.write(f"Worker Processes ({len(workers)}):")
        if workers:
            for worker in workers:
                self.stdout.write(f"  PID {worker['pid']}: {worker['memory_mb']:.1f}MB, {worker['cpu_percent']:.1f}% CPU")
        else:
            self.stdout.write("  No worker processes found")
        self.stdout.write("")
        
        # Task statistics
        task_stats = status.get('task_statistics', {})
        if 'error' not in task_stats:
            self.stdout.write("Task Statistics:")
            self.stdout.write(f"  Total Tasks: {task_stats.get('total_tasks', 'unknown')}")
            self.stdout.write(f"  Pending: {task_stats.get('pending_tasks', 'unknown')}")
            self.stdout.write(f"  Running: {task_stats.get('running_tasks', 'unknown')}")
            
            last_hour = task_stats.get('last_hour', {})
            self.stdout.write(f"  Last Hour: {last_hour.get('total', 0)} total, {last_hour.get('failed', 0)} failed ({last_hour.get('failure_rate', 0):.1f}% failure rate)")
            
            last_24h = task_stats.get('last_24_hours', {})
            self.stdout.write(f"  Last 24h: {last_24h.get('total', 0)} total, {last_24h.get('failed', 0)} failed ({last_24h.get('failure_rate', 0):.1f}% failure rate)")
            
            avg_duration = task_stats.get('average_duration_seconds', 0)
            self.stdout.write(f"  Avg Duration: {avg_duration:.2f}s")
    
    def _print_health(self, health):
        """Print health status in human-readable format."""
        status_color = self.style.SUCCESS if health['healthy'] else self.style.ERROR
        status_text = "HEALTHY" if health['healthy'] else "UNHEALTHY"
        
        self.stdout.write(f"=== Django-Q Health Check ===")
        self.stdout.write(f"Status: {status_color(status_text)}")
        self.stdout.write(f"Timestamp: {health['timestamp']}")
        self.stdout.write("")
        
        if health['issues']:
            self.stdout.write(self.style.ERROR("Issues:"))
            for issue in health['issues']:
                self.stdout.write(f"  ❌ {issue}")
            self.stdout.write("")
        
        if health['warnings']:
            self.stdout.write(self.style.WARNING("Warnings:"))
            for warning in health['warnings']:
                self.stdout.write(f"  ⚠️  {warning}")
            self.stdout.write("")
        
        if not health['issues'] and not health['warnings']:
            self.stdout.write(self.style.SUCCESS("✅ All checks passed"))
    
    def _print_monitoring_summary(self, status, health):
        """Print monitoring summary."""
        timestamp = status.get('timestamp', 'unknown')
        
        # Health status
        health_symbol = "✅" if health['healthy'] else "❌"
        health_text = "HEALTHY" if health['healthy'] else "UNHEALTHY"
        
        # Queue info
        queue_info = status.get('queue_info', {})
        pending = queue_info.get('queue_length', 0)
        processing = queue_info.get('processing_length', 0)
        failed = queue_info.get('failed_length', 0)
        
        # Worker count
        worker_count = len(status.get('worker_processes', []))
        
        # Task stats
        task_stats = status.get('task_statistics', {})
        last_hour = task_stats.get('last_hour', {})
        failure_rate = last_hour.get('failure_rate', 0)
        
        self.stdout.write(f"[{timestamp}] {health_symbol} {health_text} | Workers: {worker_count} | Queue: {pending}P/{processing}R/{failed}F | Failure Rate: {failure_rate:.1f}%")
        
        # Print issues/warnings if any
        if health['issues']:
            for issue in health['issues']:
                self.stdout.write(f"  ❌ {issue}")
        
        if health['warnings']:
            for warning in health['warnings']:
                self.stdout.write(f"  ⚠️  {warning}")
    
    def _print_task_details(self, details):
        """Print task details in human-readable format."""
        if 'error' in details:
            self.stdout.write(
                self.style.ERROR(f"Error: {details['error']}")
            )
            return
        
        self.stdout.write(f"=== Task Details ===")
        self.stdout.write(f"ID: {details['id']}")
        self.stdout.write(f"Name: {details['name']}")
        self.stdout.write(f"Function: {details['func']}")
        self.stdout.write(f"Started: {details['started'] or 'Not started'}")
        self.stdout.write(f"Stopped: {details['stopped'] or 'Not stopped'}")
        self.stdout.write(f"Success: {details['success']}")
        self.stdout.write(f"Duration: {details['duration_seconds'] or 'N/A'}s")
        self.stdout.write(f"Attempts: {details['attempt_count']}")
        self.stdout.write(f"Group: {details['group'] or 'None'}")
        
        if details['args']:
            self.stdout.write(f"Args: {details['args']}")
        
        if details['kwargs']:
            self.stdout.write(f"Kwargs: {details['kwargs']}")
        
        if details['result']:
            self.stdout.write(f"Result: {details['result']}")