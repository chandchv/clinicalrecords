"""
Load balancer health check endpoints.
"""

import time
from django.http import JsonResponse, HttpResponse
from django.views import View
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.cache import never_cache
from django.utils.decorators import method_decorator
from django.db import connection
from django.core.cache import cache
from clinical_records.services.comprehensive_monitoring import ComprehensiveMonitor

@method_decorator([csrf_exempt, never_cache], name='dispatch')
class LoadBalancerHealthView(View):
    """
    Health check endpoint optimized for load balancers.
    Returns simple HTTP status codes for quick health checks.
    """
    
    def get(self, request):
        """
        Simple health check for load balancers.
        Returns 200 if healthy, 503 if unhealthy.
        """
        try:
            # Quick database check
            start_time = time.time()
            with connection.cursor() as cursor:
                cursor.execute("SELECT 1")
                cursor.fetchone()
            db_time = time.time() - start_time
            
            # Quick cache check
            cache_key = 'lb_health_check'
            cache.set(cache_key, 'ok', 10)
            cache_working = cache.get(cache_key) == 'ok'
            cache.delete(cache_key)
            
            # Determine health status
            healthy = db_time < 1.0 and cache_working
            
            if healthy:
                return HttpResponse('OK', status=200, content_type='text/plain')
            else:
                return HttpResponse('UNHEALTHY', status=503, content_type='text/plain')
                
        except Exception:
            return HttpResponse('ERROR', status=503, content_type='text/plain')

@method_decorator([csrf_exempt, never_cache], name='dispatch')
class LoadBalancerReadinessView(View):
    """
    Readiness check for load balancers.
    Checks if the application is ready to serve requests.
    """
    
    def get(self, request):
        """
        Readiness check for load balancers.
        Returns 200 if ready, 503 if not ready.
        """
        try:
            # Check database connectivity
            with connection.cursor() as cursor:
                cursor.execute("SELECT COUNT(*) FROM django_migrations")
                migration_count = cursor.fetchone()[0]
            
            # Check if we have migrations (app is initialized)
            if migration_count > 0:
                return HttpResponse('READY', status=200, content_type='text/plain')
            else:
                return HttpResponse('NOT_READY', status=503, content_type='text/plain')
                
        except Exception:
            return HttpResponse('NOT_READY', status=503, content_type='text/plain')

@method_decorator([csrf_exempt, never_cache], name='dispatch')
class LoadBalancerLivenessView(View):
    """
    Liveness check for load balancers.
    Checks if the application process is alive.
    """
    
    def get(self, request):
        """
        Liveness check for load balancers.
        Always returns 200 if the process is running.
        """
        return HttpResponse('ALIVE', status=200, content_type='text/plain')

@method_decorator([csrf_exempt, never_cache], name='dispatch')
class DetailedHealthView(View):
    """
    Detailed health check with JSON response.
    """
    
    def get(self, request):
        """
        Detailed health check with component status.
        """
        try:
            monitor = ComprehensiveMonitor()
            health_status = monitor.check_health_status()
            
            # Simplify for load balancer consumption
            simplified_status = {
                'status': 'healthy' if health_status['overall_healthy'] else 'unhealthy',
                'timestamp': health_status['timestamp'],
                'checks': {}
            }
            
            # Add simplified check results
            for check_name, check_result in health_status.get('checks', {}).items():
                simplified_status['checks'][check_name] = {
                    'status': 'healthy' if check_result.get('healthy', True) else 'unhealthy',
                    'alert_count': len(check_result.get('alerts', []))
                }
            
            status_code = 200 if health_status['overall_healthy'] else 503
            return JsonResponse(simplified_status, status=status_code)
            
        except Exception as e:
            return JsonResponse({
                'status': 'error',
                'timestamp': time.time(),
                'error': str(e)
            }, status=503)

# Function-based views for backward compatibility
@csrf_exempt
@never_cache
def lb_health_check(request):
    """Simple health check for load balancers."""
    view = LoadBalancerHealthView()
    return view.get(request)

@csrf_exempt
@never_cache
def lb_readiness_check(request):
    """Readiness check for load balancers."""
    view = LoadBalancerReadinessView()
    return view.get(request)

@csrf_exempt
@never_cache
def lb_liveness_check(request):
    """Liveness check for load balancers."""
    view = LoadBalancerLivenessView()
    return view.get(request)

@csrf_exempt
@never_cache
def detailed_health_check(request):
    """Detailed health check with JSON response."""
    view = DetailedHealthView()
    return view.get(request)