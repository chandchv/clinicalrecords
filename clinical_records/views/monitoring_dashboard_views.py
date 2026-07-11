"""
Comprehensive monitoring dashboard views.
"""

import json
from django.shortcuts import render
from django.http import JsonResponse
from django.views import View
from django.contrib.auth.decorators import login_required
from django.contrib.admin.views.decorators import staff_member_required
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_exempt
from clinical_records.services.comprehensive_monitoring import ComprehensiveMonitor

@method_decorator([login_required, staff_member_required], name='dispatch')
class MonitoringDashboardView(View):
    """
    Main monitoring dashboard view.
    """
    
    def get(self, request):
        """Render monitoring dashboard."""
        return render(request, 'clinical_records/monitoring_dashboard.html', {
            'title': 'System Monitoring Dashboard'
        })

@method_decorator([login_required, staff_member_required], name='dispatch')
class SystemMetricsAPIView(View):
    """
    API view for system metrics.
    """
    
    def get(self, request):
        """Get system metrics."""
        monitor = ComprehensiveMonitor()
        metrics = monitor.get_system_metrics()
        return JsonResponse(metrics)

@method_decorator([login_required, staff_member_required], name='dispatch')
class ApplicationMetricsAPIView(View):
    """
    API view for application metrics.
    """
    
    def get(self, request):
        """Get application metrics."""
        monitor = ComprehensiveMonitor()
        metrics = monitor.get_application_metrics()
        return JsonResponse(metrics)

@method_decorator([login_required, staff_member_required], name='dispatch')
class SecurityMetricsAPIView(View):
    """
    API view for security metrics.
    """
    
    def get(self, request):
        """Get security metrics."""
        monitor = ComprehensiveMonitor()
        metrics = monitor.get_security_metrics()
        return JsonResponse(metrics)

@method_decorator([login_required, staff_member_required], name='dispatch')
class HealthCheckAPIView(View):
    """
    API view for comprehensive health check.
    """
    
    def get(self, request):
        """Get health status."""
        monitor = ComprehensiveMonitor()
        health_status = monitor.check_health_status()
        
        # Send alerts if requested
        if request.GET.get('send_alerts') == 'true' and not health_status['overall_healthy']:
            alert_messages = []
            for alert in health_status.get('alerts', []):
                alert_messages.append(alert)
            
            if alert_messages:
                monitor.send_alert(
                    'health_check',
                    'System health check failed',
                    '\n'.join(alert_messages)
                )
        
        # Return appropriate HTTP status
        status_code = 200 if health_status['overall_healthy'] else 503
        return JsonResponse(health_status, status=status_code)

@method_decorator([login_required, staff_member_required], name='dispatch')
class AlertHistoryAPIView(View):
    """
    API view for alert history.
    """
    
    def get(self, request):
        """Get alert history."""
        monitor = ComprehensiveMonitor()
        
        # Get recent alerts (last 50)
        alert_history = monitor.alert_history[-50:] if monitor.alert_history else []
        
        # Convert to serializable format
        serializable_history = []
        for alert in alert_history:
            serializable_history.append({
                'timestamp': alert['timestamp'].isoformat(),
                'type': alert['type'],
                'message': alert['message']
            })
        
        return JsonResponse({
            'alerts': serializable_history,
            'count': len(serializable_history)
        })

@method_decorator([login_required, staff_member_required, csrf_exempt], name='dispatch')
class TestAlertAPIView(View):
    """
    API view for sending test alerts.
    """
    
    def post(self, request):
        """Send test alert."""
        try:
            data = json.loads(request.body)
            alert_type = data.get('type', 'test')
            message = data.get('message', 'Test alert from monitoring dashboard')
            
            monitor = ComprehensiveMonitor()
            success = monitor.send_alert(alert_type, message, 'Test alert details')
            
            return JsonResponse({
                'success': success,
                'message': 'Test alert sent' if success else 'Test alert not sent (cooldown active)'
            })
            
        except json.JSONDecodeError:
            return JsonResponse({'error': 'Invalid JSON'}, status=400)
        except Exception as e:
            return JsonResponse({'error': str(e)}, status=500)

@method_decorator([login_required, staff_member_required], name='dispatch')
class PrometheusMetricsView(View):
    """
    Prometheus-compatible metrics endpoint.
    """
    
    def get(self, request):
        """Export metrics in Prometheus format."""
        monitor = ComprehensiveMonitor()
        
        try:
            # Get all metrics
            system_metrics = monitor.get_system_metrics()
            app_metrics = monitor.get_application_metrics()
            security_metrics = monitor.get_security_metrics()
            health_status = monitor.check_health_status()
            
            metrics_lines = []
            
            # System metrics
            if 'error' not in system_metrics:
                cpu = system_metrics.get('cpu', {})
                memory = system_metrics.get('memory', {})
                disk = system_metrics.get('disk', {})
                network = system_metrics.get('network', {})
                
                metrics_lines.extend([
                    f'# HELP rxdoctor_cpu_percent CPU usage percentage',
                    f'# TYPE rxdoctor_cpu_percent gauge',
                    f'rxdoctor_cpu_percent {cpu.get("percent", 0)}',
                    f'# HELP rxdoctor_memory_percent Memory usage percentage',
                    f'# TYPE rxdoctor_memory_percent gauge',
                    f'rxdoctor_memory_percent {memory.get("percent", 0)}',
                    f'# HELP rxdoctor_disk_percent Disk usage percentage',
                    f'# TYPE rxdoctor_disk_percent gauge',
                    f'rxdoctor_disk_percent {disk.get("percent", 0)}',
                    f'# HELP rxdoctor_network_bytes_sent Network bytes sent',
                    f'# TYPE rxdoctor_network_bytes_sent counter',
                    f'rxdoctor_network_bytes_sent {network.get("bytes_sent", 0)}',
                    f'# HELP rxdoctor_network_bytes_recv Network bytes received',
                    f'# TYPE rxdoctor_network_bytes_recv counter',
                    f'rxdoctor_network_bytes_recv {network.get("bytes_recv", 0)}'
                ])
            
            # Application metrics
            if 'error' not in app_metrics:
                records = app_metrics.get('clinical_records', {})
                processing = app_metrics.get('processing', {})
                django_q = app_metrics.get('django_q', {})
                
                metrics_lines.extend([
                    f'# HELP rxdoctor_clinical_records_total Total clinical records',
                    f'# TYPE rxdoctor_clinical_records_total gauge',
                    f'rxdoctor_clinical_records_total {records.get("records", {}).get("total", 0)}',
                    f'# HELP rxdoctor_documents_total Total clinical documents',
                    f'# TYPE rxdoctor_documents_total gauge',
                    f'rxdoctor_documents_total {records.get("documents", {}).get("total", 0)}',
                    f'# HELP rxdoctor_documents_failed Failed documents',
                    f'# TYPE rxdoctor_documents_failed gauge',
                    f'rxdoctor_documents_failed {records.get("documents", {}).get("failed", 0)}',
                    f'# HELP rxdoctor_processing_success_rate Processing success rate',
                    f'# TYPE rxdoctor_processing_success_rate gauge',
                    f'rxdoctor_processing_success_rate {processing.get("last_hour", {}).get("success_rate", 100)}',
                    f'# HELP rxdoctor_django_q_workers Django-Q workers',
                    f'# TYPE rxdoctor_django_q_workers gauge',
                    f'rxdoctor_django_q_workers {django_q.get("workers", 0)}',
                    f'# HELP rxdoctor_django_q_queue_length Django-Q queue length',
                    f'# TYPE rxdoctor_django_q_queue_length gauge',
                    f'rxdoctor_django_q_queue_length {django_q.get("queue_length", 0)}'
                ])
            
            # Security metrics
            if 'error' not in security_metrics:
                events = security_metrics.get('security_events', {})
                logins = security_metrics.get('failed_logins', {})
                
                metrics_lines.extend([
                    f'# HELP rxdoctor_security_events_hour Security events in last hour',
                    f'# TYPE rxdoctor_security_events_hour gauge',
                    f'rxdoctor_security_events_hour {events.get("last_hour", 0)}',
                    f'# HELP rxdoctor_failed_logins_hour Failed logins in last hour',
                    f'# TYPE rxdoctor_failed_logins_hour gauge',
                    f'rxdoctor_failed_logins_hour {logins.get("last_hour", 0)}',
                    f'# HELP rxdoctor_suspicious_ips Suspicious IP addresses',
                    f'# TYPE rxdoctor_suspicious_ips gauge',
                    f'rxdoctor_suspicious_ips {len(security_metrics.get("suspicious_ips", []))}'
                ])
            
            # Health metrics
            metrics_lines.extend([
                f'# HELP rxdoctor_system_healthy System health status',
                f'# TYPE rxdoctor_system_healthy gauge',
                f'rxdoctor_system_healthy {1 if health_status.get("overall_healthy") else 0}',
                f'# HELP rxdoctor_alerts_count Number of active alerts',
                f'# TYPE rxdoctor_alerts_count gauge',
                f'rxdoctor_alerts_count {len(health_status.get("alerts", []))}'
            ])
            
            response_content = '\n'.join(metrics_lines)
            
            from django.http import HttpResponse
            return HttpResponse(response_content, content_type='text/plain; version=0.0.4; charset=utf-8')
            
        except Exception as e:
            from django.http import HttpResponse
            return HttpResponse(f'# Error generating metrics: {str(e)}', 
                              content_type='text/plain', status=500)

# Function-based views for backward compatibility
@login_required
@staff_member_required
def monitoring_dashboard(request):
    """Main monitoring dashboard."""
    return render(request, 'clinical_records/monitoring_dashboard.html', {
        'title': 'System Monitoring Dashboard'
    })

@login_required
@staff_member_required
def system_metrics_api(request):
    """System metrics API endpoint."""
    monitor = ComprehensiveMonitor()
    metrics = monitor.get_system_metrics()
    return JsonResponse(metrics)

@login_required
@staff_member_required
def application_metrics_api(request):
    """Application metrics API endpoint."""
    monitor = ComprehensiveMonitor()
    metrics = monitor.get_application_metrics()
    return JsonResponse(metrics)

@login_required
@staff_member_required
def security_metrics_api(request):
    """Security metrics API endpoint."""
    monitor = ComprehensiveMonitor()
    metrics = monitor.get_security_metrics()
    return JsonResponse(metrics)

@login_required
@staff_member_required
def health_check_api(request):
    """Health check API endpoint."""
    monitor = ComprehensiveMonitor()
    health_status = monitor.check_health_status()
    
    # Send alerts if requested
    if request.GET.get('send_alerts') == 'true' and not health_status['overall_healthy']:
        alert_messages = []
        for alert in health_status.get('alerts', []):
            alert_messages.append(alert)
        
        if alert_messages:
            monitor.send_alert(
                'health_check',
                'System health check failed',
                '\n'.join(alert_messages)
            )
    
    # Return appropriate HTTP status
    status_code = 200 if health_status['overall_healthy'] else 503
    return JsonResponse(health_status, status=status_code)

@login_required
@staff_member_required
def prometheus_metrics(request):
    """Prometheus metrics endpoint."""
    view = PrometheusMetricsView()
    return view.get(request)