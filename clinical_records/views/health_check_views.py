"""
Health check views for production monitoring.
"""

import os
import time
import psutil
from pathlib import Path
from django.http import JsonResponse
from django.views import View
from django.conf import settings
from django.db import connection
from django.core.cache import cache
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.cache import never_cache
from clinical_records.storage.secure_file_handler import FileStorageMonitor

@method_decorator([csrf_exempt, never_cache], name='dispatch')
class HealthCheckView(View):
    """
    Comprehensive health check endpoint for production monitoring.
    """
    
    def get(self, request):
        """
        Return system health status.
        """
        health_data = {
            'status': 'healthy',
            'timestamp': time.time(),
            'checks': {}
        }
        
        # Database health check
        try:
            with connection.cursor() as cursor:
                cursor.execute("SELECT 1")
                health_data['checks']['database'] = {
                    'status': 'healthy',
                    'response_time_ms': self._measure_db_response_time()
                }
        except Exception as e:
            health_data['checks']['database'] = {
                'status': 'unhealthy',
                'error': str(e)
            }
            health_data['status'] = 'unhealthy'
        
        # Cache health check
        try:
            cache_key = 'health_check_test'
            cache.set(cache_key, 'test_value', 30)
            cached_value = cache.get(cache_key)
            
            if cached_value == 'test_value':
                health_data['checks']['cache'] = {'status': 'healthy'}
            else:
                health_data['checks']['cache'] = {
                    'status': 'unhealthy',
                    'error': 'Cache read/write failed'
                }
                health_data['status'] = 'unhealthy'
        except Exception as e:
            health_data['checks']['cache'] = {
                'status': 'unhealthy',
                'error': str(e)
            }
            health_data['status'] = 'unhealthy'
        
        # File storage health check
        try:
            monitor = FileStorageMonitor()
            disk_info = monitor.check_disk_space()
            
            if disk_info:
                health_data['checks']['storage'] = {
                    'status': 'healthy' if disk_info['usage_percent'] < 90 else 'warning',
                    'usage_percent': disk_info['usage_percent'],
                    'free_space_gb': disk_info['free_space_gb']
                }
                
                if disk_info['usage_percent'] >= 95:
                    health_data['checks']['storage']['status'] = 'critical'
                    health_data['status'] = 'unhealthy'
            else:
                health_data['checks']['storage'] = {
                    'status': 'unhealthy',
                    'error': 'Could not check disk space'
                }
                health_data['status'] = 'unhealthy'
        except Exception as e:
            health_data['checks']['storage'] = {
                'status': 'unhealthy',
                'error': str(e)
            }
            health_data['status'] = 'unhealthy'
        
        # Media directory accessibility check
        try:
            media_root = Path(settings.MEDIA_ROOT)
            if media_root.exists() and os.access(media_root, os.R_OK | os.W_OK):
                health_data['checks']['media_access'] = {'status': 'healthy'}
            else:
                health_data['checks']['media_access'] = {
                    'status': 'unhealthy',
                    'error': 'Media directory not accessible'
                }
                health_data['status'] = 'unhealthy'
        except Exception as e:
            health_data['checks']['media_access'] = {
                'status': 'unhealthy',
                'error': str(e)
            }
            health_data['status'] = 'unhealthy'
        
        # System resources check
        try:
            cpu_percent = psutil.cpu_percent(interval=1)
            memory = psutil.virtual_memory()
            
            health_data['checks']['system_resources'] = {
                'status': 'healthy',
                'cpu_percent': cpu_percent,
                'memory_percent': memory.percent,
                'memory_available_gb': memory.available / (1024**3)
            }
            
            # Warning thresholds
            if cpu_percent > 80 or memory.percent > 85:
                health_data['checks']['system_resources']['status'] = 'warning'
            
            # Critical thresholds
            if cpu_percent > 95 or memory.percent > 95:
                health_data['checks']['system_resources']['status'] = 'critical'
                health_data['status'] = 'unhealthy'
                
        except Exception as e:
            health_data['checks']['system_resources'] = {
                'status': 'unhealthy',
                'error': str(e)
            }
        
        # Django-Q health check (if available)
        try:
            from django_q.models import Task
            recent_tasks = Task.objects.filter(
                started__gte=time.time() - 3600  # Last hour
            ).count()
            
            failed_tasks = Task.objects.filter(
                started__gte=time.time() - 3600,
                success=False
            ).count()
            
            failure_rate = (failed_tasks / recent_tasks * 100) if recent_tasks > 0 else 0
            
            health_data['checks']['task_queue'] = {
                'status': 'healthy' if failure_rate < 10 else 'warning',
                'recent_tasks': recent_tasks,
                'failed_tasks': failed_tasks,
                'failure_rate_percent': failure_rate
            }
            
            if failure_rate > 25:
                health_data['checks']['task_queue']['status'] = 'critical'
                health_data['status'] = 'unhealthy'
                
        except Exception as e:
            health_data['checks']['task_queue'] = {
                'status': 'unknown',
                'error': str(e)
            }
        
        # Return appropriate HTTP status code
        status_code = 200 if health_data['status'] == 'healthy' else 503
        
        return JsonResponse(health_data, status=status_code)
    
    def _measure_db_response_time(self):
        """Measure database response time in milliseconds."""
        start_time = time.time()
        try:
            with connection.cursor() as cursor:
                cursor.execute("SELECT COUNT(*) FROM django_migrations")
                cursor.fetchone()
        except Exception:
            pass
        end_time = time.time()
        return round((end_time - start_time) * 1000, 2)


@method_decorator([csrf_exempt, never_cache], name='dispatch')
class ReadinessCheckView(View):
    """
    Readiness check for Kubernetes/container orchestration.
    """
    
    def get(self, request):
        """
        Check if the application is ready to serve requests.
        """
        readiness_data = {
            'ready': True,
            'timestamp': time.time(),
            'checks': {}
        }
        
        # Check database connectivity
        try:
            with connection.cursor() as cursor:
                cursor.execute("SELECT 1")
            readiness_data['checks']['database'] = {'ready': True}
        except Exception as e:
            readiness_data['checks']['database'] = {
                'ready': False,
                'error': str(e)
            }
            readiness_data['ready'] = False
        
        # Check media directory
        try:
            media_root = Path(settings.MEDIA_ROOT)
            if media_root.exists():
                readiness_data['checks']['media_directory'] = {'ready': True}
            else:
                readiness_data['checks']['media_directory'] = {
                    'ready': False,
                    'error': 'Media directory does not exist'
                }
                readiness_data['ready'] = False
        except Exception as e:
            readiness_data['checks']['media_directory'] = {
                'ready': False,
                'error': str(e)
            }
            readiness_data['ready'] = False
        
        status_code = 200 if readiness_data['ready'] else 503
        return JsonResponse(readiness_data, status=status_code)


@method_decorator([csrf_exempt, never_cache], name='dispatch')
class LivenessCheckView(View):
    """
    Liveness check for Kubernetes/container orchestration.
    """
    
    def get(self, request):
        """
        Check if the application is alive and responding.
        """
        return JsonResponse({
            'alive': True,
            'timestamp': time.time(),
            'version': getattr(settings, 'VERSION', '1.0.0')
        })


def simple_health_check(request):
    """
    Simple health check endpoint for basic monitoring.
    """
    return JsonResponse({
        'status': 'ok',
        'timestamp': time.time()
    })


def storage_health_check(request):
    """
    Dedicated storage health check endpoint.
    """
    try:
        monitor = FileStorageMonitor()
        disk_info = monitor.check_disk_space()
        
        if disk_info:
            status = 'healthy'
            if disk_info['usage_percent'] >= 90:
                status = 'warning'
            if disk_info['usage_percent'] >= 95:
                status = 'critical'
            
            return JsonResponse({
                'status': status,
                'usage_percent': disk_info['usage_percent'],
                'free_space_gb': disk_info['free_space_gb'],
                'total_space_gb': disk_info['total_space_gb'],
                'timestamp': time.time()
            })
        else:
            return JsonResponse({
                'status': 'error',
                'error': 'Could not check disk space',
                'timestamp': time.time()
            }, status=500)
            
    except Exception as e:
        return JsonResponse({
            'status': 'error',
            'error': str(e),
            'timestamp': time.time()
        }, status=500)