"""
Comprehensive monitoring and alerting service for RxDoctor clinical records system.
"""

import os
import time
import psutil
import logging
import smtplib
from datetime import datetime, timedelta
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from pathlib import Path
from django.conf import settings
from django.db import connection
from django.core.cache import cache
from django.core.mail import send_mail
from django.utils import timezone
from users.models import AuditLog
from clinical_records.models import ClinicalDocument, ClinicalRecord
from clinical_records.storage.secure_file_handler import FileStorageMonitor
from clinical_records.services.django_q_manager import DjangoQManager

logger = logging.getLogger(__name__)

class ComprehensiveMonitor:
    """
    Comprehensive monitoring system for application performance, security, and health.
    """
    
    def __init__(self):
        self.config = self._load_config()
        self.file_monitor = FileStorageMonitor()
        self.django_q_manager = DjangoQManager()
        self.alert_history = []
        
    def _load_config(self):
        """Load monitoring configuration."""
        return {
            'enabled': getattr(settings, 'COMPREHENSIVE_MONITORING_ENABLED', True),
            'check_interval': getattr(settings, 'MONITORING_CHECK_INTERVAL', 300),  # 5 minutes
            'alert_cooldown': getattr(settings, 'MONITORING_ALERT_COOLDOWN', 1800),  # 30 minutes
            'admin_email': getattr(settings, 'ADMIN_EMAIL', 'admin@rxdoctor.com'),
            'thresholds': {
                'cpu_warning': 70,
                'cpu_critical': 85,
                'memory_warning': 75,
                'memory_critical': 90,
                'disk_warning': 80,
                'disk_critical': 90,
                'response_time_warning': 2.0,  # seconds
                'response_time_critical': 5.0,  # seconds
                'error_rate_warning': 5.0,  # percentage
                'error_rate_critical': 10.0,  # percentage
                'failed_tasks_warning': 10,
                'failed_tasks_critical': 25,
                'security_events_warning': 5,
                'security_events_critical': 15
            }
        }
    
    def get_system_metrics(self):
        """Get comprehensive system metrics."""
        try:
            # CPU metrics
            cpu_percent = psutil.cpu_percent(interval=1)
            cpu_count = psutil.cpu_count()
            load_avg = os.getloadavg() if hasattr(os, 'getloadavg') else (0, 0, 0)
            
            # Memory metrics
            memory = psutil.virtual_memory()
            swap = psutil.swap_memory()
            
            # Disk metrics
            disk_usage = psutil.disk_usage('/')
            disk_io = psutil.disk_io_counters()
            
            # Network metrics
            network_io = psutil.net_io_counters()
            
            # Process metrics
            process_count = len(psutil.pids())
            
            return {
                'timestamp': datetime.now().isoformat(),
                'cpu': {
                    'percent': cpu_percent,
                    'count': cpu_count,
                    'load_avg_1m': load_avg[0],
                    'load_avg_5m': load_avg[1],
                    'load_avg_15m': load_avg[2]
                },
                'memory': {
                    'total_gb': memory.total / (1024**3),
                    'available_gb': memory.available / (1024**3),
                    'used_gb': memory.used / (1024**3),
                    'percent': memory.percent,
                    'swap_total_gb': swap.total / (1024**3),
                    'swap_used_gb': swap.used / (1024**3),
                    'swap_percent': swap.percent
                },
                'disk': {
                    'total_gb': disk_usage.total / (1024**3),
                    'used_gb': disk_usage.used / (1024**3),
                    'free_gb': disk_usage.free / (1024**3),
                    'percent': (disk_usage.used / disk_usage.total) * 100,
                    'read_bytes': disk_io.read_bytes if disk_io else 0,
                    'write_bytes': disk_io.write_bytes if disk_io else 0
                },
                'network': {
                    'bytes_sent': network_io.bytes_sent,
                    'bytes_recv': network_io.bytes_recv,
                    'packets_sent': network_io.packets_sent,
                    'packets_recv': network_io.packets_recv
                },
                'processes': {
                    'count': process_count
                }
            }
            
        except Exception as e:
            logger.error(f"Error getting system metrics: {str(e)}")
            return {'error': str(e)}
    
    def get_application_metrics(self):
        """Get application-specific metrics."""
        try:
            # Database metrics
            db_metrics = self._get_database_metrics()
            
            # Cache metrics
            cache_metrics = self._get_cache_metrics()
            
            # Clinical records metrics
            records_metrics = self._get_clinical_records_metrics()
            
            # Processing metrics
            processing_metrics = self._get_processing_metrics()
            
            # Django-Q metrics
            django_q_metrics = self._get_django_q_metrics()
            
            return {
                'timestamp': datetime.now().isoformat(),
                'database': db_metrics,
                'cache': cache_metrics,
                'clinical_records': records_metrics,
                'processing': processing_metrics,
                'django_q': django_q_metrics
            }
            
        except Exception as e:
            logger.error(f"Error getting application metrics: {str(e)}")
            return {'error': str(e)}
    
    def _get_database_metrics(self):
        """Get database performance metrics."""
        try:
            start_time = time.time()
            
            with connection.cursor() as cursor:
                # Test query performance
                cursor.execute("SELECT COUNT(*) FROM django_migrations")
                migration_count = cursor.fetchone()[0]
                
                # Get table sizes (PostgreSQL specific)
                if 'postgresql' in settings.DATABASES['default']['ENGINE']:
                    cursor.execute("""
                        SELECT schemaname, tablename, pg_size_pretty(pg_total_relation_size(schemaname||'.'||tablename)) as size
                        FROM pg_tables 
                        WHERE schemaname = 'public' 
                        ORDER BY pg_total_relation_size(schemaname||'.'||tablename) DESC 
                        LIMIT 10
                    """)
                    table_sizes = cursor.fetchall()
                else:
                    table_sizes = []
            
            query_time = time.time() - start_time
            
            # Get connection info
            connection_info = {
                'vendor': connection.vendor,
                'queries_count': len(connection.queries),
                'query_time': query_time
            }
            
            return {
                'connection': connection_info,
                'migration_count': migration_count,
                'table_sizes': table_sizes,
                'query_performance': query_time
            }
            
        except Exception as e:
            logger.error(f"Error getting database metrics: {str(e)}")
            return {'error': str(e)}
    
    def _get_cache_metrics(self):
        """Get cache performance metrics."""
        try:
            # Test cache performance
            test_key = 'monitoring_test_key'
            test_value = 'test_value'
            
            start_time = time.time()
            cache.set(test_key, test_value, 60)
            cached_value = cache.get(test_key)
            cache_time = time.time() - start_time
            
            cache.delete(test_key)
            
            cache_working = cached_value == test_value
            
            return {
                'working': cache_working,
                'response_time': cache_time,
                'backend': str(cache.__class__.__name__)
            }
            
        except Exception as e:
            logger.error(f"Error getting cache metrics: {str(e)}")
            return {'error': str(e)}
    
    def _get_clinical_records_metrics(self):
        """Get clinical records specific metrics."""
        try:
            now = timezone.now()
            one_hour_ago = now - timedelta(hours=1)
            one_day_ago = now - timedelta(days=1)
            
            # Record counts
            total_records = ClinicalRecord.objects.count()
            records_last_hour = ClinicalRecord.objects.filter(created_at__gte=one_hour_ago).count()
            records_last_day = ClinicalRecord.objects.filter(created_at__gte=one_day_ago).count()
            
            # Document counts
            total_documents = ClinicalDocument.objects.count()
            documents_last_hour = ClinicalDocument.objects.filter(created_at__gte=one_hour_ago).count()
            documents_last_day = ClinicalDocument.objects.filter(created_at__gte=one_day_ago).count()
            
            # Processing status
            processing_documents = ClinicalDocument.objects.filter(processing_status='processing').count()
            failed_documents = ClinicalDocument.objects.filter(processing_status='failed').count()
            pending_review = ClinicalDocument.objects.filter(processing_status='manual_review').count()
            
            return {
                'records': {
                    'total': total_records,
                    'last_hour': records_last_hour,
                    'last_day': records_last_day
                },
                'documents': {
                    'total': total_documents,
                    'last_hour': documents_last_hour,
                    'last_day': documents_last_day,
                    'processing': processing_documents,
                    'failed': failed_documents,
                    'pending_review': pending_review
                }
            }
            
        except Exception as e:
            logger.error(f"Error getting clinical records metrics: {str(e)}")
            return {'error': str(e)}
    
    def _get_processing_metrics(self):
        """Get document processing metrics."""
        try:
            now = timezone.now()
            one_hour_ago = now - timedelta(hours=1)
            
            # Get recent processing statistics
            recent_docs = ClinicalDocument.objects.filter(created_at__gte=one_hour_ago)
            
            total_processed = recent_docs.filter(processing_status__in=['completed', 'failed']).count()
            successful = recent_docs.filter(processing_status='completed').count()
            failed = recent_docs.filter(processing_status='failed').count()
            
            success_rate = (successful / total_processed * 100) if total_processed > 0 else 100
            failure_rate = (failed / total_processed * 100) if total_processed > 0 else 0
            
            # Average processing time
            completed_docs = recent_docs.filter(
                processing_status='completed',
                created_at__isnull=False,
                updated_at__isnull=False
            )
            
            processing_times = []
            for doc in completed_docs:
                if doc.created_at and doc.updated_at:
                    processing_time = (doc.updated_at - doc.created_at).total_seconds()
                    processing_times.append(processing_time)
            
            avg_processing_time = sum(processing_times) / len(processing_times) if processing_times else 0
            
            return {
                'last_hour': {
                    'total_processed': total_processed,
                    'successful': successful,
                    'failed': failed,
                    'success_rate': success_rate,
                    'failure_rate': failure_rate,
                    'avg_processing_time': avg_processing_time
                }
            }
            
        except Exception as e:
            logger.error(f"Error getting processing metrics: {str(e)}")
            return {'error': str(e)}
    
    def _get_django_q_metrics(self):
        """Get Django-Q metrics."""
        try:
            status = self.django_q_manager.get_worker_status()
            health = self.django_q_manager.check_worker_health()
            
            return {
                'workers': len(status.get('worker_processes', [])),
                'queue_length': status.get('queue_info', {}).get('queue_length', 0),
                'failed_tasks': status.get('queue_info', {}).get('failed_length', 0),
                'processing_tasks': status.get('queue_info', {}).get('processing_length', 0),
                'healthy': health.get('healthy', False),
                'issues': len(health.get('issues', [])),
                'warnings': len(health.get('warnings', []))
            }
            
        except Exception as e:
            logger.error(f"Error getting Django-Q metrics: {str(e)}")
            return {'error': str(e)}
    
    def get_security_metrics(self):
        """Get security-related metrics."""
        try:
            now = timezone.now()
            one_hour_ago = now - timedelta(hours=1)
            one_day_ago = now - timedelta(days=1)
            
            # Get security events from audit logs
            security_events_hour = AuditLog.objects.filter(
                timestamp__gte=one_hour_ago,
                action__in=['LOGIN_FAILED', 'UNAUTHORIZED_ACCESS', 'PERMISSION_DENIED', 'SUSPICIOUS_ACTIVITY']
            ).count()
            
            security_events_day = AuditLog.objects.filter(
                timestamp__gte=one_day_ago,
                action__in=['LOGIN_FAILED', 'UNAUTHORIZED_ACCESS', 'PERMISSION_DENIED', 'SUSPICIOUS_ACTIVITY']
            ).count()
            
            # Failed login attempts
            failed_logins_hour = AuditLog.objects.filter(
                timestamp__gte=one_hour_ago,
                action='LOGIN_FAILED'
            ).count()
            
            # File access violations
            file_access_violations = AuditLog.objects.filter(
                timestamp__gte=one_hour_ago,
                action__in=['FILE_ACCESS_DENIED', 'UNAUTHORIZED_FILE_ACCESS']
            ).count()
            
            # Suspicious IP addresses (multiple failed attempts)
            suspicious_ips = AuditLog.objects.filter(
                timestamp__gte=one_hour_ago,
                action='LOGIN_FAILED'
            ).values('ip_address').annotate(
                attempt_count=models.Count('id')
            ).filter(attempt_count__gte=5)
            
            return {
                'timestamp': datetime.now().isoformat(),
                'security_events': {
                    'last_hour': security_events_hour,
                    'last_day': security_events_day
                },
                'failed_logins': {
                    'last_hour': failed_logins_hour
                },
                'file_access_violations': file_access_violations,
                'suspicious_ips': list(suspicious_ips)
            }
            
        except Exception as e:
            logger.error(f"Error getting security metrics: {str(e)}")
            return {'error': str(e)}
    
    def check_health_status(self):
        """Perform comprehensive health check."""
        health_status = {
            'timestamp': datetime.now().isoformat(),
            'overall_healthy': True,
            'checks': {},
            'alerts': []
        }
        
        try:
            # System health checks
            system_metrics = self.get_system_metrics()
            health_status['checks']['system'] = self._check_system_health(system_metrics)
            
            # Application health checks
            app_metrics = self.get_application_metrics()
            health_status['checks']['application'] = self._check_application_health(app_metrics)
            
            # Security health checks
            security_metrics = self.get_security_metrics()
            health_status['checks']['security'] = self._check_security_health(security_metrics)
            
            # Storage health checks
            storage_info = self.file_monitor.check_disk_space()
            health_status['checks']['storage'] = self._check_storage_health(storage_info)
            
            # Determine overall health
            for check_name, check_result in health_status['checks'].items():
                if not check_result.get('healthy', True):
                    health_status['overall_healthy'] = False
                
                # Collect alerts
                if check_result.get('alerts'):
                    health_status['alerts'].extend(check_result['alerts'])
            
            return health_status
            
        except Exception as e:
            logger.error(f"Error in health check: {str(e)}")
            health_status['overall_healthy'] = False
            health_status['error'] = str(e)
            return health_status
    
    def _check_system_health(self, metrics):
        """Check system health against thresholds."""
        if 'error' in metrics:
            return {'healthy': False, 'error': metrics['error']}
        
        alerts = []
        healthy = True
        
        # CPU check
        cpu_percent = metrics.get('cpu', {}).get('percent', 0)
        if cpu_percent >= self.config['thresholds']['cpu_critical']:
            alerts.append(f"CRITICAL: CPU usage at {cpu_percent:.1f}%")
            healthy = False
        elif cpu_percent >= self.config['thresholds']['cpu_warning']:
            alerts.append(f"WARNING: CPU usage at {cpu_percent:.1f}%")
        
        # Memory check
        memory_percent = metrics.get('memory', {}).get('percent', 0)
        if memory_percent >= self.config['thresholds']['memory_critical']:
            alerts.append(f"CRITICAL: Memory usage at {memory_percent:.1f}%")
            healthy = False
        elif memory_percent >= self.config['thresholds']['memory_warning']:
            alerts.append(f"WARNING: Memory usage at {memory_percent:.1f}%")
        
        # Disk check
        disk_percent = metrics.get('disk', {}).get('percent', 0)
        if disk_percent >= self.config['thresholds']['disk_critical']:
            alerts.append(f"CRITICAL: Disk usage at {disk_percent:.1f}%")
            healthy = False
        elif disk_percent >= self.config['thresholds']['disk_warning']:
            alerts.append(f"WARNING: Disk usage at {disk_percent:.1f}%")
        
        return {
            'healthy': healthy,
            'alerts': alerts,
            'metrics': metrics
        }
    
    def _check_application_health(self, metrics):
        """Check application health against thresholds."""
        if 'error' in metrics:
            return {'healthy': False, 'error': metrics['error']}
        
        alerts = []
        healthy = True
        
        # Database check
        db_metrics = metrics.get('database', {})
        if 'error' in db_metrics:
            alerts.append("CRITICAL: Database connection error")
            healthy = False
        elif db_metrics.get('query_performance', 0) > self.config['thresholds']['response_time_critical']:
            alerts.append(f"CRITICAL: Database response time {db_metrics['query_performance']:.2f}s")
            healthy = False
        elif db_metrics.get('query_performance', 0) > self.config['thresholds']['response_time_warning']:
            alerts.append(f"WARNING: Database response time {db_metrics['query_performance']:.2f}s")
        
        # Cache check
        cache_metrics = metrics.get('cache', {})
        if 'error' in cache_metrics or not cache_metrics.get('working', False):
            alerts.append("WARNING: Cache not working properly")
        
        # Processing check
        processing_metrics = metrics.get('processing', {}).get('last_hour', {})
        failure_rate = processing_metrics.get('failure_rate', 0)
        
        if failure_rate >= self.config['thresholds']['error_rate_critical']:
            alerts.append(f"CRITICAL: Processing failure rate at {failure_rate:.1f}%")
            healthy = False
        elif failure_rate >= self.config['thresholds']['error_rate_warning']:
            alerts.append(f"WARNING: Processing failure rate at {failure_rate:.1f}%")
        
        # Django-Q check
        django_q_metrics = metrics.get('django_q', {})
        failed_tasks = django_q_metrics.get('failed_tasks', 0)
        
        if failed_tasks >= self.config['thresholds']['failed_tasks_critical']:
            alerts.append(f"CRITICAL: {failed_tasks} failed Django-Q tasks")
            healthy = False
        elif failed_tasks >= self.config['thresholds']['failed_tasks_warning']:
            alerts.append(f"WARNING: {failed_tasks} failed Django-Q tasks")
        
        if not django_q_metrics.get('healthy', True):
            alerts.append("WARNING: Django-Q workers unhealthy")
        
        return {
            'healthy': healthy,
            'alerts': alerts,
            'metrics': metrics
        }
    
    def _check_security_health(self, metrics):
        """Check security health against thresholds."""
        if 'error' in metrics:
            return {'healthy': False, 'error': metrics['error']}
        
        alerts = []
        healthy = True
        
        # Security events check
        security_events = metrics.get('security_events', {}).get('last_hour', 0)
        
        if security_events >= self.config['thresholds']['security_events_critical']:
            alerts.append(f"CRITICAL: {security_events} security events in last hour")
            healthy = False
        elif security_events >= self.config['thresholds']['security_events_warning']:
            alerts.append(f"WARNING: {security_events} security events in last hour")
        
        # Failed logins check
        failed_logins = metrics.get('failed_logins', {}).get('last_hour', 0)
        if failed_logins >= 20:
            alerts.append(f"WARNING: {failed_logins} failed login attempts in last hour")
        
        # Suspicious IPs check
        suspicious_ips = metrics.get('suspicious_ips', [])
        if len(suspicious_ips) > 0:
            alerts.append(f"WARNING: {len(suspicious_ips)} suspicious IP addresses detected")
        
        return {
            'healthy': healthy,
            'alerts': alerts,
            'metrics': metrics
        }
    
    def _check_storage_health(self, storage_info):
        """Check storage health."""
        if not storage_info:
            return {'healthy': False, 'error': 'Could not get storage information'}
        
        alerts = []
        healthy = True
        
        usage_percent = storage_info.get('usage_percent', 0)
        
        if usage_percent >= self.config['thresholds']['disk_critical']:
            alerts.append(f"CRITICAL: Storage usage at {usage_percent:.1f}%")
            healthy = False
        elif usage_percent >= self.config['thresholds']['disk_warning']:
            alerts.append(f"WARNING: Storage usage at {usage_percent:.1f}%")
        
        return {
            'healthy': healthy,
            'alerts': alerts,
            'metrics': storage_info
        }
    
    def send_alert(self, alert_type, message, details=None):
        """Send alert notification."""
        try:
            # Check alert cooldown
            if not self._should_send_alert(alert_type):
                return False
            
            subject = f"RxDoctor {alert_type.upper()} Alert"
            
            email_body = f"""
RxDoctor Monitoring Alert

Alert Type: {alert_type.upper()}
Message: {message}
Timestamp: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
Server: {os.uname().nodename if hasattr(os, 'uname') else 'Unknown'}

"""
            
            if details:
                email_body += f"Details:\n{details}\n\n"
            
            email_body += """
Please investigate and take appropriate action.

This is an automated alert from the RxDoctor monitoring system.
            """
            
            send_mail(
                subject,
                email_body,
                settings.DEFAULT_FROM_EMAIL,
                [self.config['admin_email']],
                fail_silently=False
            )
            
            # Record alert
            self.alert_history.append({
                'timestamp': datetime.now(),
                'type': alert_type,
                'message': message
            })
            
            # Keep only last 100 alerts
            if len(self.alert_history) > 100:
                self.alert_history = self.alert_history[-100:]
            
            logger.info(f"Alert sent: {alert_type} - {message}")
            return True
            
        except Exception as e:
            logger.error(f"Error sending alert: {str(e)}")
            return False
    
    def _should_send_alert(self, alert_type):
        """Check if alert should be sent based on cooldown."""
        cooldown_seconds = self.config['alert_cooldown']
        
        # Find last alert of this type
        for alert in reversed(self.alert_history):
            if alert['type'] == alert_type:
                time_since = (datetime.now() - alert['timestamp']).total_seconds()
                return time_since >= cooldown_seconds
        
        # No previous alert found, can send
        return True
    
    def run_monitoring_cycle(self):
        """Run a complete monitoring cycle."""
        try:
            logger.info("Starting monitoring cycle")
            
            # Get comprehensive health status
            health_status = self.check_health_status()
            
            # Send alerts for any issues
            if not health_status['overall_healthy']:
                alert_messages = []
                for alert in health_status['alerts']:
                    alert_messages.append(alert)
                
                if alert_messages:
                    self.send_alert(
                        'health_check',
                        'System health check failed',
                        '\n'.join(alert_messages)
                    )
            
            # Log monitoring results
            logger.info(f"Monitoring cycle completed. Healthy: {health_status['overall_healthy']}")
            
            return health_status
            
        except Exception as e:
            logger.error(f"Error in monitoring cycle: {str(e)}")
            self.send_alert('monitoring_error', f'Monitoring cycle failed: {str(e)}')
            return {
                'timestamp': datetime.now().isoformat(),
                'overall_healthy': False,
                'error': str(e)
            }