"""
Django-Q monitoring views for web interface.
"""

import json
from django.shortcuts import render
from django.http import JsonResponse
from django.views import View
from django.contrib.auth.decorators import login_required
from django.contrib.admin.views.decorators import staff_member_required
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_exempt
from clinical_records.services.django_q_manager import DjangoQManager

@method_decorator([login_required, staff_member_required], name='dispatch')
class DjangoQDashboardView(View):
    """
    Django-Q monitoring dashboard view.
    """
    
    def get(self, request):
        """Render Django-Q dashboard."""
        return render(request, 'clinical_records/django_q_dashboard.html')

@method_decorator([login_required, staff_member_required], name='dispatch')
class DjangoQStatusAPIView(View):
    """
    API view for Django-Q status information.
    """
    
    def get(self, request):
        """Get Django-Q status."""
        manager = DjangoQManager()
        status = manager.get_worker_status()
        return JsonResponse(status)

@method_decorator([login_required, staff_member_required], name='dispatch')
class DjangoQHealthAPIView(View):
    """
    API view for Django-Q health check.
    """
    
    def get(self, request):
        """Get Django-Q health status."""
        manager = DjangoQManager()
        health = manager.check_worker_health()
        
        # Send alerts if requested
        if request.GET.get('send_alerts') == 'true':
            manager.send_health_alert(health)
        
        return JsonResponse(health)

@method_decorator([login_required, staff_member_required, csrf_exempt], name='dispatch')
class DjangoQControlAPIView(View):
    """
    API view for Django-Q worker control operations.
    """
    
    def post(self, request):
        """Handle Django-Q control operations."""
        try:
            data = json.loads(request.body)
            action = data.get('action')
            
            manager = DjangoQManager()
            
            if action == 'restart':
                result = manager.restart_workers()
            elif action == 'scale':
                workers = data.get('workers')
                if not workers:
                    return JsonResponse({'error': 'workers parameter required'}, status=400)
                result = manager.scale_workers(workers)
            elif action == 'clear_failed':
                result = manager.clear_failed_tasks()
            elif action == 'retry_failed':
                max_retries = data.get('max_retries', 3)
                result = manager.retry_failed_tasks(max_retries)
            else:
                return JsonResponse({'error': 'Invalid action'}, status=400)
            
            return JsonResponse(result)
            
        except json.JSONDecodeError:
            return JsonResponse({'error': 'Invalid JSON'}, status=400)
        except Exception as e:
            return JsonResponse({'error': str(e)}, status=500)

@method_decorator([login_required, staff_member_required], name='dispatch')
class DjangoQTaskDetailsAPIView(View):
    """
    API view for Django-Q task details.
    """
    
    def get(self, request, task_id):
        """Get task details."""
        manager = DjangoQManager()
        details = manager.get_task_details(task_id)
        return JsonResponse(details)

@login_required
@staff_member_required
def django_q_dashboard(request):
    """
    Django-Q monitoring dashboard.
    """
    return render(request, 'clinical_records/django_q_dashboard.html', {
        'title': 'Django-Q Monitoring Dashboard'
    })

@login_required
@staff_member_required
def django_q_status_api(request):
    """
    API endpoint for Django-Q status.
    """
    manager = DjangoQManager()
    status = manager.get_worker_status()
    return JsonResponse(status)

@login_required
@staff_member_required
def django_q_health_api(request):
    """
    API endpoint for Django-Q health check.
    """
    manager = DjangoQManager()
    health = manager.check_worker_health()
    
    # Send alerts if requested
    if request.GET.get('send_alerts') == 'true':
        manager.send_health_alert(health)
    
    return JsonResponse(health)

@login_required
@staff_member_required
@csrf_exempt
def django_q_control_api(request):
    """
    API endpoint for Django-Q control operations.
    """
    if request.method != 'POST':
        return JsonResponse({'error': 'POST method required'}, status=405)
    
    try:
        data = json.loads(request.body)
        action = data.get('action')
        
        manager = DjangoQManager()
        
        if action == 'restart':
            result = manager.restart_workers()
        elif action == 'scale':
            workers = data.get('workers')
            if not workers:
                return JsonResponse({'error': 'workers parameter required'}, status=400)
            result = manager.scale_workers(workers)
        elif action == 'clear_failed':
            result = manager.clear_failed_tasks()
        elif action == 'retry_failed':
            max_retries = data.get('max_retries', 3)
            result = manager.retry_failed_tasks(max_retries)
        else:
            return JsonResponse({'error': 'Invalid action'}, status=400)
        
        return JsonResponse(result)
        
    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON'}, status=400)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)

@login_required
@staff_member_required
def django_q_metrics_api(request):
    """
    API endpoint for Django-Q metrics (for monitoring systems).
    """
    manager = DjangoQManager()
    status = manager.get_worker_status()
    health = manager.check_worker_health()
    
    # Format metrics for Prometheus/monitoring systems
    metrics = {
        'django_q_workers_total': len(status.get('worker_processes', [])),
        'django_q_queue_length': status.get('queue_info', {}).get('queue_length', 0),
        'django_q_processing_length': status.get('queue_info', {}).get('processing_length', 0),
        'django_q_failed_length': status.get('queue_info', {}).get('failed_length', 0),
        'django_q_tasks_total': status.get('task_statistics', {}).get('total_tasks', 0),
        'django_q_tasks_pending': status.get('task_statistics', {}).get('pending_tasks', 0),
        'django_q_tasks_running': status.get('task_statistics', {}).get('running_tasks', 0),
        'django_q_failure_rate_1h': status.get('task_statistics', {}).get('last_hour', {}).get('failure_rate', 0),
        'django_q_failure_rate_24h': status.get('task_statistics', {}).get('last_24_hours', {}).get('failure_rate', 0),
        'django_q_avg_duration_seconds': status.get('task_statistics', {}).get('average_duration_seconds', 0),
        'django_q_healthy': 1 if health.get('healthy') else 0,
        'django_q_issues_count': len(health.get('issues', [])),
        'django_q_warnings_count': len(health.get('warnings', []))
    }
    
    return JsonResponse(metrics)