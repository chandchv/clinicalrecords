"""
Django management command for Django-Q autoscaling service.
"""

import json
import signal
import sys
from django.core.management.base import BaseCommand, CommandError
from clinical_records.services.django_q_autoscaler import DjangoQAutoScaler

class Command(BaseCommand):
    help = 'Django-Q autoscaling service'
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.autoscaler = None
        self.running = False
    
    def add_arguments(self, parser):
        parser.add_argument(
            'action',
            choices=['start', 'check', 'status', 'history', 'config'],
            help='Action to perform'
        )
        parser.add_argument(
            '--daemon',
            action='store_true',
            help='Run as daemon (for start action)'
        )
        parser.add_argument(
            '--json',
            action='store_true',
            help='Output in JSON format'
        )
        parser.add_argument(
            '--limit',
            type=int,
            default=50,
            help='Limit for history results (default: 50)'
        )
    
    def handle(self, *args, **options):
        self.autoscaler = DjangoQAutoScaler()
        
        # Set up signal handlers for graceful shutdown
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)
        
        try:
            if options['action'] == 'start':
                self._handle_start(options)
            elif options['action'] == 'check':
                self._handle_check(options)
            elif options['action'] == 'status':
                self._handle_status(options)
            elif options['action'] == 'history':
                self._handle_history(options)
            elif options['action'] == 'config':
                self._handle_config(options)
                
        except KeyboardInterrupt:
            self.stdout.write("Autoscaling service stopped by user")
        except Exception as e:
            raise CommandError(f"Error in autoscaling service: {str(e)}")
    
    def _signal_handler(self, signum, frame):
        """Handle shutdown signals gracefully."""
        self.stdout.write(f"Received signal {signum}, shutting down...")
        self.running = False
        sys.exit(0)
    
    def _handle_start(self, options):
        """Handle start action."""
        if not self.autoscaler.config['enabled']:
            self.stdout.write(
                self.style.WARNING("Autoscaling is disabled in configuration")
            )
            return
        
        self.stdout.write("Starting Django-Q autoscaling service...")
        self.stdout.write(f"Check interval: {self.autoscaler.config['check_interval']} seconds")
        self.stdout.write(f"Min workers: {self.autoscaler.config['min_workers']}")
        self.stdout.write(f"Max workers: {self.autoscaler.config['max_workers']}")
        self.stdout.write("Press Ctrl+C to stop")
        self.stdout.write("-" * 50)
        
        self.running = True
        
        if options['daemon']:
            # Run as daemon (simplified implementation)
            self.autoscaler.run_continuous_autoscaling()
        else:
            # Run with console output
            self._run_with_output()
    
    def _run_with_output(self):
        """Run autoscaling with console output."""
        import time
        
        while self.running:
            try:
                result = self.autoscaler.run_autoscaling_check()
                
                timestamp = result.get('metrics', {}).get('timestamp', 'unknown')
                if hasattr(timestamp, 'strftime'):
                    timestamp = timestamp.strftime('%H:%M:%S')
                
                if result['success']:
                    if result.get('action') == 'none':
                        metrics = result.get('metrics', {})
                        self.stdout.write(
                            f"[{timestamp}] ✓ No action needed - "
                            f"Workers: {metrics.get('worker_count', 0)}, "
                            f"Queue: {metrics.get('queue_length', 0)}, "
                            f"CPU: {metrics.get('avg_cpu_usage', 0):.1f}%"
                        )
                    else:
                        self.stdout.write(
                            f"[{timestamp}] 🔄 {result['message']} - {result.get('reason', '')}"
                        )
                else:
                    self.stdout.write(
                        f"[{timestamp}] ❌ {result['message']}"
                    )
                
                time.sleep(self.autoscaler.config['check_interval'])
                
            except KeyboardInterrupt:
                break
            except Exception as e:
                self.stdout.write(f"Error: {str(e)}")
                time.sleep(self.autoscaler.config['check_interval'])
    
    def _handle_check(self, options):
        """Handle single check action."""
        result = self.autoscaler.run_autoscaling_check()
        
        if options['json']:
            self.stdout.write(json.dumps(result, indent=2, default=str))
        else:
            if result['success']:
                self.stdout.write(
                    self.style.SUCCESS(f"✓ {result['message']}")
                )
                
                if result.get('metrics'):
                    metrics = result['metrics']
                    self.stdout.write(f"Workers: {metrics.get('worker_count', 0)}")
                    self.stdout.write(f"Queue Length: {metrics.get('queue_length', 0)}")
                    self.stdout.write(f"Processing: {metrics.get('processing_length', 0)}")
                    self.stdout.write(f"Failed: {metrics.get('failed_length', 0)}")
                    self.stdout.write(f"Avg CPU: {metrics.get('avg_cpu_usage', 0):.1f}%")
                    self.stdout.write(f"Avg Memory: {metrics.get('avg_memory_usage', 0):.1f}MB")
                    self.stdout.write(f"Failure Rate: {metrics.get('failure_rate', 0):.1f}%")
                
                if result.get('reason'):
                    self.stdout.write(f"Reason: {result['reason']}")
            else:
                self.stdout.write(
                    self.style.ERROR(f"❌ {result['message']}")
                )
    
    def _handle_status(self, options):
        """Handle status action."""
        status = self.autoscaler.get_autoscaling_status()
        
        if options['json']:
            self.stdout.write(json.dumps(status, indent=2, default=str))
        else:
            self.stdout.write("=== Django-Q Autoscaling Status ===")
            self.stdout.write(f"Enabled: {status['enabled']}")
            self.stdout.write(f"Last Check: {status['last_check']}")
            self.stdout.write("")
            
            config = status['config']
            self.stdout.write("Configuration:")
            self.stdout.write(f"  Min Workers: {config['min_workers']}")
            self.stdout.write(f"  Max Workers: {config['max_workers']}")
            self.stdout.write(f"  Scale Up Threshold: {config['scale_up_threshold']}")
            self.stdout.write(f"  Scale Down Threshold: {config['scale_down_threshold']}")
            self.stdout.write(f"  CPU Threshold: {config['cpu_threshold']}%")
            self.stdout.write(f"  Memory Threshold: {config['memory_threshold']}%")
            self.stdout.write(f"  Check Interval: {config['check_interval']}s")
            self.stdout.write("")
            
            history = status['recent_history']
            if history:
                self.stdout.write("Recent Scaling Actions:")
                for entry in history:
                    timestamp = entry['timestamp']
                    if hasattr(timestamp, 'strftime'):
                        timestamp = timestamp.strftime('%Y-%m-%d %H:%M:%S')
                    
                    self.stdout.write(
                        f"  {timestamp}: {entry['action']} "
                        f"({entry['from_workers']} → {entry['to_workers']}) - {entry['reason']}"
                    )
            else:
                self.stdout.write("No recent scaling actions")
    
    def _handle_history(self, options):
        """Handle history action."""
        history = self.autoscaler.get_scaling_history(options['limit'])
        
        if options['json']:
            self.stdout.write(json.dumps(history, indent=2, default=str))
        else:
            if history:
                self.stdout.write(f"=== Scaling History (Last {len(history)} actions) ===")
                for entry in history:
                    timestamp = entry['timestamp']
                    if hasattr(timestamp, 'strftime'):
                        timestamp = timestamp.strftime('%Y-%m-%d %H:%M:%S')
                    
                    action_color = self.style.SUCCESS if entry['action'] == 'scale_up' else self.style.WARNING
                    
                    self.stdout.write(
                        f"{timestamp}: {action_color(entry['action'])} "
                        f"({entry['from_workers']} → {entry['to_workers']}) - {entry['reason']}"
                    )
            else:
                self.stdout.write("No scaling history available")
    
    def _handle_config(self, options):
        """Handle config action."""
        config = self.autoscaler.config
        
        if options['json']:
            self.stdout.write(json.dumps(config, indent=2))
        else:
            self.stdout.write("=== Django-Q Autoscaling Configuration ===")
            for key, value in config.items():
                self.stdout.write(f"{key}: {value}")