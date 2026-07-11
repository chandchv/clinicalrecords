"""
Django management command for comprehensive monitoring and alerting.
"""

import json
import time
import signal
import sys
from django.core.management.base import BaseCommand, CommandError
from clinical_records.services.comprehensive_monitoring import ComprehensiveMonitor

class Command(BaseCommand):
    help = 'Comprehensive monitoring and alerting service'
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.monitor = None
        self.running = False
    
    def add_arguments(self, parser):
        parser.add_argument(
            'action',
            choices=['status', 'health', 'metrics', 'security', 'monitor', 'test-alert'],
            help='Action to perform'
        )
        parser.add_argument(
            '--continuous',
            action='store_true',
            help='Run continuous monitoring'
        )
        parser.add_argument(
            '--interval',
            type=int,
            default=300,
            help='Monitoring interval in seconds (default: 300)'
        )
        parser.add_argument(
            '--json',
            action='store_true',
            help='Output in JSON format'
        )
        parser.add_argument(
            '--send-alerts',
            action='store_true',
            help='Send email alerts for issues'
        )
        parser.add_argument(
            '--alert-type',
            type=str,
            default='test',
            help='Alert type for test-alert action'
        )
        parser.add_argument(
            '--alert-message',
            type=str,
            default='Test alert message',
            help='Alert message for test-alert action'
        )
    
    def handle(self, *args, **options):
        self.monitor = ComprehensiveMonitor()
        
        # Set up signal handlers for graceful shutdown
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)
        
        try:
            if options['action'] == 'status':
                self._handle_status(options)
            elif options['action'] == 'health':
                self._handle_health(options)
            elif options['action'] == 'metrics':
                self._handle_metrics(options)
            elif options['action'] == 'security':
                self._handle_security(options)
            elif options['action'] == 'monitor':
                self._handle_monitor(options)
            elif options['action'] == 'test-alert':
                self._handle_test_alert(options)
                
        except KeyboardInterrupt:
            self.stdout.write("Monitoring stopped by user")
        except Exception as e:
            raise CommandError(f"Error in monitoring service: {str(e)}")
    
    def _signal_handler(self, signum, frame):
        """Handle shutdown signals gracefully."""
        self.stdout.write(f"Received signal {signum}, shutting down...")
        self.running = False
        sys.exit(0)
    
    def _handle_status(self, options):
        """Handle status action."""
        try:
            system_metrics = self.monitor.get_system_metrics()
            app_metrics = self.monitor.get_application_metrics()
            
            status = {
                'timestamp': system_metrics.get('timestamp'),
                'system': system_metrics,
                'application': app_metrics
            }
            
            if options['json']:
                self.stdout.write(json.dumps(status, indent=2, default=str))
            else:
                self._print_status(status)
                
        except Exception as e:
            if options['json']:
                self.stdout.write(json.dumps({'error': str(e)}))
            else:
                self.stdout.write(self.style.ERROR(f"Error getting status: {str(e)}"))
    
    def _handle_health(self, options):
        """Handle health check action."""
        try:
            health_status = self.monitor.check_health_status()
            
            if options['send_alerts'] and not health_status['overall_healthy']:
                alert_messages = []
                for alert in health_status.get('alerts', []):
                    alert_messages.append(alert)
                
                if alert_messages:
                    self.monitor.send_alert(
                        'health_check',
                        'System health check failed',
                        '\n'.join(alert_messages)
                    )
            
            if options['json']:
                self.stdout.write(json.dumps(health_status, indent=2, default=str))
            else:
                self._print_health_status(health_status)
                
        except Exception as e:
            if options['json']:
                self.stdout.write(json.dumps({'error': str(e)}))
            else:
                self.stdout.write(self.style.ERROR(f"Error in health check: {str(e)}"))
    
    def _handle_metrics(self, options):
        """Handle metrics action."""
        try:
            system_metrics = self.monitor.get_system_metrics()
            app_metrics = self.monitor.get_application_metrics()
            security_metrics = self.monitor.get_security_metrics()
            
            all_metrics = {
                'system': system_metrics,
                'application': app_metrics,
                'security': security_metrics
            }
            
            if options['json']:
                self.stdout.write(json.dumps(all_metrics, indent=2, default=str))
            else:
                self._print_metrics(all_metrics)
                
        except Exception as e:
            if options['json']:
                self.stdout.write(json.dumps({'error': str(e)}))
            else:
                self.stdout.write(self.style.ERROR(f"Error getting metrics: {str(e)}"))
    
    def _handle_security(self, options):
        """Handle security metrics action."""
        try:
            security_metrics = self.monitor.get_security_metrics()
            
            if options['json']:
                self.stdout.write(json.dumps(security_metrics, indent=2, default=str))
            else:
                self._print_security_metrics(security_metrics)
                
        except Exception as e:
            if options['json']:
                self.stdout.write(json.dumps({'error': str(e)}))
            else:
                self.stdout.write(self.style.ERROR(f"Error getting security metrics: {str(e)}"))
    
    def _handle_monitor(self, options):
        """Handle continuous monitoring action."""
        self.stdout.write("Starting comprehensive monitoring...")
        self.stdout.write(f"Interval: {options['interval']} seconds")
        self.stdout.write("Press Ctrl+C to stop")
        self.stdout.write("-" * 50)
        
        self.running = True
        
        try:
            while self.running:
                health_status = self.monitor.run_monitoring_cycle()
                
                if not options['json']:
                    timestamp = health_status.get('timestamp', 'unknown')
                    healthy = health_status.get('overall_healthy', False)
                    status_symbol = "✅" if healthy else "❌"
                    status_text = "HEALTHY" if healthy else "UNHEALTHY"
                    
                    self.stdout.write(f"[{timestamp}] {status_symbol} {status_text}")
                    
                    # Print alerts
                    for alert in health_status.get('alerts', []):
                        if 'CRITICAL' in alert:
                            self.stdout.write(f"  🚨 {alert}")
                        elif 'WARNING' in alert:
                            self.stdout.write(f"  ⚠️  {alert}")
                        else:
                            self.stdout.write(f"  ℹ️  {alert}")
                else:
                    self.stdout.write(json.dumps(health_status, default=str))
                
                if not options['continuous']:
                    break
                
                time.sleep(options['interval'])
                
        except KeyboardInterrupt:
            self.stdout.write("\nMonitoring stopped")
    
    def _handle_test_alert(self, options):
        """Handle test alert action."""
        try:
            success = self.monitor.send_alert(
                options['alert_type'],
                options['alert_message'],
                'This is a test alert generated by the monitoring system.'
            )
            
            if success:
                self.stdout.write(
                    self.style.SUCCESS(f"Test alert sent successfully")
                )
            else:
                self.stdout.write(
                    self.style.WARNING(f"Test alert not sent (possibly due to cooldown)")
                )
                
        except Exception as e:
            self.stdout.write(
                self.style.ERROR(f"Error sending test alert: {str(e)}")
            )
    
    def _print_status(self, status):
        """Print status in human-readable format."""
        self.stdout.write("=== System Status ===")
        
        system = status.get('system', {})
        if 'error' not in system:
            cpu = system.get('cpu', {})
            memory = system.get('memory', {})
            disk = system.get('disk', {})
            
            self.stdout.write(f"CPU: {cpu.get('percent', 0):.1f}% ({cpu.get('count', 0)} cores)")
            self.stdout.write(f"Memory: {memory.get('percent', 0):.1f}% ({memory.get('used_gb', 0):.1f}GB / {memory.get('total_gb', 0):.1f}GB)")
            self.stdout.write(f"Disk: {disk.get('percent', 0):.1f}% ({disk.get('used_gb', 0):.1f}GB / {disk.get('total_gb', 0):.1f}GB)")
        else:
            self.stdout.write(f"System metrics error: {system['error']}")
        
        self.stdout.write("\n=== Application Status ===")
        
        app = status.get('application', {})
        if 'error' not in app:
            db = app.get('database', {})
            cache = app.get('cache', {})
            records = app.get('clinical_records', {})
            django_q = app.get('django_q', {})
            
            self.stdout.write(f"Database: {'OK' if 'error' not in db else 'ERROR'} (Query time: {db.get('query_performance', 0):.3f}s)")
            self.stdout.write(f"Cache: {'OK' if cache.get('working') else 'ERROR'}")
            self.stdout.write(f"Clinical Records: {records.get('records', {}).get('total', 0)} total")
            self.stdout.write(f"Django-Q: {django_q.get('workers', 0)} workers, {django_q.get('queue_length', 0)} queued")
        else:
            self.stdout.write(f"Application metrics error: {app['error']}")
    
    def _print_health_status(self, health_status):
        """Print health status in human-readable format."""
        overall_healthy = health_status.get('overall_healthy', False)
        status_color = self.style.SUCCESS if overall_healthy else self.style.ERROR
        status_text = "HEALTHY" if overall_healthy else "UNHEALTHY"
        
        self.stdout.write(f"=== Health Status ===")
        self.stdout.write(f"Overall Status: {status_color(status_text)}")
        self.stdout.write(f"Timestamp: {health_status.get('timestamp', 'unknown')}")
        self.stdout.write("")
        
        # Print check results
        checks = health_status.get('checks', {})
        for check_name, check_result in checks.items():
            check_healthy = check_result.get('healthy', True)
            check_symbol = "✅" if check_healthy else "❌"
            self.stdout.write(f"{check_symbol} {check_name.title()}: {'HEALTHY' if check_healthy else 'UNHEALTHY'}")
            
            # Print alerts for this check
            for alert in check_result.get('alerts', []):
                if 'CRITICAL' in alert:
                    self.stdout.write(f"  🚨 {alert}")
                elif 'WARNING' in alert:
                    self.stdout.write(f"  ⚠️  {alert}")
                else:
                    self.stdout.write(f"  ℹ️  {alert}")
        
        # Print overall alerts
        overall_alerts = health_status.get('alerts', [])
        if overall_alerts:
            self.stdout.write("\n=== Alerts ===")
            for alert in overall_alerts:
                if 'CRITICAL' in alert:
                    self.stdout.write(self.style.ERROR(f"🚨 {alert}"))
                elif 'WARNING' in alert:
                    self.stdout.write(self.style.WARNING(f"⚠️  {alert}"))
                else:
                    self.stdout.write(f"ℹ️  {alert}")
    
    def _print_metrics(self, metrics):
        """Print metrics in human-readable format."""
        self.stdout.write("=== System Metrics ===")
        system = metrics.get('system', {})
        if 'error' not in system:
            cpu = system.get('cpu', {})
            memory = system.get('memory', {})
            disk = system.get('disk', {})
            network = system.get('network', {})
            
            self.stdout.write(f"CPU: {cpu.get('percent', 0):.1f}% (Load: {cpu.get('load_avg_1m', 0):.2f})")
            self.stdout.write(f"Memory: {memory.get('percent', 0):.1f}% ({memory.get('used_gb', 0):.1f}GB used)")
            self.stdout.write(f"Disk: {disk.get('percent', 0):.1f}% ({disk.get('free_gb', 0):.1f}GB free)")
            self.stdout.write(f"Network: {network.get('bytes_sent', 0) / (1024**2):.1f}MB sent, {network.get('bytes_recv', 0) / (1024**2):.1f}MB received")
        
        self.stdout.write("\n=== Application Metrics ===")
        app = metrics.get('application', {})
        if 'error' not in app:
            records = app.get('clinical_records', {})
            processing = app.get('processing', {})
            django_q = app.get('django_q', {})
            
            self.stdout.write(f"Records: {records.get('records', {}).get('total', 0)} total, {records.get('records', {}).get('last_hour', 0)} last hour")
            self.stdout.write(f"Documents: {records.get('documents', {}).get('total', 0)} total, {records.get('documents', {}).get('failed', 0)} failed")
            
            proc_hour = processing.get('last_hour', {})
            self.stdout.write(f"Processing: {proc_hour.get('success_rate', 0):.1f}% success rate, {proc_hour.get('avg_processing_time', 0):.1f}s avg time")
            
            self.stdout.write(f"Django-Q: {django_q.get('workers', 0)} workers, {django_q.get('queue_length', 0)} queued, {django_q.get('failed_tasks', 0)} failed")
        
        self.stdout.write("\n=== Security Metrics ===")
        security = metrics.get('security', {})
        if 'error' not in security:
            events = security.get('security_events', {})
            logins = security.get('failed_logins', {})
            
            self.stdout.write(f"Security Events: {events.get('last_hour', 0)} last hour, {events.get('last_day', 0)} last day")
            self.stdout.write(f"Failed Logins: {logins.get('last_hour', 0)} last hour")
            self.stdout.write(f"Suspicious IPs: {len(security.get('suspicious_ips', []))}")
    
    def _print_security_metrics(self, metrics):
        """Print security metrics in human-readable format."""
        if 'error' in metrics:
            self.stdout.write(self.style.ERROR(f"Error: {metrics['error']}"))
            return
        
        self.stdout.write("=== Security Metrics ===")
        self.stdout.write(f"Timestamp: {metrics.get('timestamp', 'unknown')}")
        self.stdout.write("")
        
        events = metrics.get('security_events', {})
        self.stdout.write(f"Security Events:")
        self.stdout.write(f"  Last Hour: {events.get('last_hour', 0)}")
        self.stdout.write(f"  Last Day: {events.get('last_day', 0)}")
        
        logins = metrics.get('failed_logins', {})
        self.stdout.write(f"Failed Logins:")
        self.stdout.write(f"  Last Hour: {logins.get('last_hour', 0)}")
        
        self.stdout.write(f"File Access Violations: {metrics.get('file_access_violations', 0)}")
        
        suspicious_ips = metrics.get('suspicious_ips', [])
        if suspicious_ips:
            self.stdout.write("Suspicious IP Addresses:")
            for ip_info in suspicious_ips:
                self.stdout.write(f"  {ip_info.get('ip_address', 'unknown')}: {ip_info.get('attempt_count', 0)} attempts")
        else:
            self.stdout.write("No suspicious IP addresses detected")