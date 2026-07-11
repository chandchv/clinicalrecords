"""
Audit reporting views for clinical records.

This module provides views for generating audit reports,
compliance reports, and audit trail access.
"""

import csv
import json
import logging
from datetime import datetime, timedelta
from typing import Dict, Any, List

from django.http import HttpResponse, JsonResponse, Http404
from django.shortcuts import get_object_or_404
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_http_methods
from django.utils.decorators import method_decorator
from django.utils import timezone
from django.db.models import Count, Q
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated

from users.models import AuditLog
from ..models import ClinicalRecord, ClinicalDocument
from ..services.audit_service import audit_service
from ..permissions import ClinicalRecordsPermission
from ..decorators.audit_decorators import audit_clinical_action

logger = logging.getLogger(__name__)


class AuditReportViewSet(viewsets.ViewSet):
    """
    ViewSet for generating and accessing audit reports.
    """
    
    permission_classes = [IsAuthenticated, ClinicalRecordsPermission]
    
    @action(detail=False, methods=['get'])
    def compliance_report(self, request):
        """
        Generate compliance report for the current clinic.
        
        Query Parameters:
            start_date: Start date for report (YYYY-MM-DD)
            end_date: End date for report (YYYY-MM-DD)
            format: Response format (json, csv)
        """
        try:
            if not hasattr(request.user, 'clinic'):
                return Response({
                    'error': 'No clinic context'
                }, status=status.HTTP_400_BAD_REQUEST)
            
            # Parse date parameters
            start_date_str = request.query_params.get('start_date')
            end_date_str = request.query_params.get('end_date')
            report_format = request.query_params.get('format', 'json')
            
            # Default to last 30 days if no dates provided
            if not end_date_str:
                end_date = timezone.now()
            else:
                end_date = datetime.strptime(end_date_str, '%Y-%m-%d')
                end_date = timezone.make_aware(end_date)
            
            if not start_date_str:
                start_date = end_date - timedelta(days=30)
            else:
                start_date = datetime.strptime(start_date_str, '%Y-%m-%d')
                start_date = timezone.make_aware(start_date)
            
            # Generate compliance report
            report = audit_service.generate_compliance_report(
                clinic=request.user.clinic,
                start_date=start_date,
                end_date=end_date
            )
            
            # Log report generation
            audit_service.log_clinical_action(
                action='COMPLIANCE_REPORT_GENERATE',
                user=request.user,
                resource_type='AUDIT_REPORT',
                clinic=request.user.clinic,
                request=request,
                details={
                    'report_period': {
                        'start_date': start_date.isoformat(),
                        'end_date': end_date.isoformat()
                    },
                    'format': report_format
                }
            )
            
            # Return in requested format
            if report_format == 'csv':
                return self._generate_csv_response(report, 'compliance_report')
            else:
                return Response(report)
                
        except Exception as e:
            logger.error(f"Error generating compliance report: {str(e)}")
            return Response({
                'error': str(e)
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    
    @action(detail=False, methods=['get'])
    def audit_trail(self, request):
        """
        Get audit trail for specific resource or general audit log.
        
        Query Parameters:
            resource_type: Filter by resource type
            resource_id: Filter by specific resource ID
            user_id: Filter by user
            start_date: Start date for filtering
            end_date: End date for filtering
            limit: Maximum number of records (default: 100)
            format: Response format (json, csv)
        """
        try:
            if not hasattr(request.user, 'clinic'):
                return Response({
                    'error': 'No clinic context'
                }, status=status.HTTP_400_BAD_REQUEST)
            
            # Parse query parameters
            resource_type = request.query_params.get('resource_type')
            resource_id = request.query_params.get('resource_id')
            user_id = request.query_params.get('user_id')
            start_date_str = request.query_params.get('start_date')
            end_date_str = request.query_params.get('end_date')
            limit = int(request.query_params.get('limit', 100))
            report_format = request.query_params.get('format', 'json')
            
            # Parse dates
            start_date = None
            end_date = None
            
            if start_date_str:
                start_date = datetime.strptime(start_date_str, '%Y-%m-%d')
                start_date = timezone.make_aware(start_date)
            
            if end_date_str:
                end_date = datetime.strptime(end_date_str, '%Y-%m-%d')
                end_date = timezone.make_aware(end_date)
            
            # Get user filter
            user_filter = None
            if user_id:
                from django.contrib.auth import get_user_model
                User = get_user_model()
                try:
                    user_filter = User.objects.get(id=user_id)
                except User.DoesNotExist:
                    return Response({
                        'error': f'User {user_id} not found'
                    }, status=status.HTTP_404_NOT_FOUND)
            
            # Get audit trail
            audit_logs = audit_service.get_audit_trail(
                resource_type=resource_type,
                resource_id=resource_id,
                clinic=request.user.clinic,
                user=user_filter,
                start_date=start_date,
                end_date=end_date,
                limit=limit
            )
            
            # Log audit trail access
            audit_service.log_clinical_action(
                action='AUDIT_REPORT_GENERATE',
                user=request.user,
                resource_type='AUDIT_REPORT',
                clinic=request.user.clinic,
                request=request,
                details={
                    'filters': {
                        'resource_type': resource_type,
                        'resource_id': resource_id,
                        'user_id': user_id,
                        'start_date': start_date.isoformat() if start_date else None,
                        'end_date': end_date.isoformat() if end_date else None,
                        'limit': limit
                    },
                    'result_count': len(audit_logs),
                    'format': report_format
                }
            )
            
            # Serialize audit logs
            audit_data = []
            for log in audit_logs:
                audit_data.append({
                    'id': log.id,
                    'timestamp': log.timestamp.isoformat(),
                    'user': log.user.username if log.user else 'System',
                    'user_full_name': log.user.get_full_name() if log.user else 'System',
                    'action': log.action,
                    'resource_type': log.resource_type,
                    'resource_id': log.resource_id,
                    'ip_address': log.ip_address,
                    'user_agent': log.user_agent[:100] + '...' if log.user_agent and len(log.user_agent) > 100 else log.user_agent,
                    'details': log.details,
                    'success': log.success if hasattr(log, 'success') else True
                })
            
            # Return in requested format
            if report_format == 'csv':
                return self._generate_audit_csv_response(audit_data, 'audit_trail')
            else:
                return Response({
                    'audit_logs': audit_data,
                    'total_count': len(audit_data),
                    'filters_applied': {
                        'resource_type': resource_type,
                        'resource_id': resource_id,
                        'user_id': user_id,
                        'start_date': start_date.isoformat() if start_date else None,
                        'end_date': end_date.isoformat() if end_date else None,
                        'limit': limit
                    }
                })
                
        except Exception as e:
            logger.error(f"Error getting audit trail: {str(e)}")
            return Response({
                'error': str(e)
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    
    @action(detail=False, methods=['get'])
    def resource_audit(self, request):
        """
        Get audit trail for a specific resource.
        
        Query Parameters:
            resource_type: Type of resource (required)
            resource_id: ID of resource (required)
            format: Response format (json, csv)
        """
        try:
            resource_type = request.query_params.get('resource_type')
            resource_id = request.query_params.get('resource_id')
            report_format = request.query_params.get('format', 'json')
            
            if not resource_type or not resource_id:
                return Response({
                    'error': 'resource_type and resource_id are required'
                }, status=status.HTTP_400_BAD_REQUEST)
            
            # Verify user has access to this resource
            if not self._verify_resource_access(request.user, resource_type, resource_id):
                return Response({
                    'error': 'Access denied to this resource'
                }, status=status.HTTP_403_FORBIDDEN)
            
            # Get audit logs for the resource
            audit_logs = AuditLog.objects.filter(
                resource_type=resource_type,
                resource_id=resource_id,
                clinic=request.user.clinic,
                action__in=list(audit_service.CLINICAL_ACTIONS.keys())
            ).order_by('-timestamp')[:100]
            
            # Serialize audit logs
            audit_data = []
            for log in audit_logs:
                audit_data.append({
                    'id': log.id,
                    'timestamp': log.timestamp.isoformat(),
                    'user': log.user.username if log.user else 'System',
                    'user_full_name': log.user.get_full_name() if log.user else 'System',
                    'action': log.action,
                    'ip_address': log.ip_address,
                    'details': log.details
                })
            
            # Log resource audit access
            audit_service.log_clinical_action(
                action='AUDIT_REPORT_GENERATE',
                user=request.user,
                resource_type='AUDIT_REPORT',
                clinic=request.user.clinic,
                request=request,
                details={
                    'target_resource_type': resource_type,
                    'target_resource_id': resource_id,
                    'audit_entries_found': len(audit_data),
                    'format': report_format
                }
            )
            
            # Return in requested format
            if report_format == 'csv':
                return self._generate_audit_csv_response(audit_data, f'resource_audit_{resource_type}_{resource_id}')
            else:
                return Response({
                    'resource_type': resource_type,
                    'resource_id': resource_id,
                    'audit_logs': audit_data,
                    'total_count': len(audit_data)
                })
                
        except Exception as e:
            logger.error(f"Error getting resource audit: {str(e)}")
            return Response({
                'error': str(e)
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    
    @action(detail=False, methods=['get'])
    def user_activity(self, request):
        """
        Get user activity report.
        
        Query Parameters:
            user_id: Specific user ID (optional, defaults to current user)
            start_date: Start date for report
            end_date: End date for report
            format: Response format (json, csv)
        """
        try:
            user_id = request.query_params.get('user_id')
            start_date_str = request.query_params.get('start_date')
            end_date_str = request.query_params.get('end_date')
            report_format = request.query_params.get('format', 'json')
            
            # Determine target user
            if user_id:
                from django.contrib.auth import get_user_model
                User = get_user_model()
                try:
                    target_user = User.objects.get(id=user_id)
                    # Verify user has permission to view other users' activity
                    if target_user != request.user and not request.user.is_staff:
                        return Response({
                            'error': 'Permission denied to view other users activity'
                        }, status=status.HTTP_403_FORBIDDEN)
                except User.DoesNotExist:
                    return Response({
                        'error': f'User {user_id} not found'
                    }, status=status.HTTP_404_NOT_FOUND)
            else:
                target_user = request.user
            
            # Parse dates (default to last 7 days)
            if not end_date_str:
                end_date = timezone.now()
            else:
                end_date = datetime.strptime(end_date_str, '%Y-%m-%d')
                end_date = timezone.make_aware(end_date)
            
            if not start_date_str:
                start_date = end_date - timedelta(days=7)
            else:
                start_date = datetime.strptime(start_date_str, '%Y-%m-%d')
                start_date = timezone.make_aware(start_date)
            
            # Get user activity
            user_logs = AuditLog.objects.filter(
                user=target_user,
                clinic=request.user.clinic,
                timestamp__gte=start_date,
                timestamp__lte=end_date,
                action__in=list(audit_service.CLINICAL_ACTIONS.keys())
            ).order_by('-timestamp')
            
            # Generate activity summary
            activity_summary = {
                'user_id': target_user.id,
                'username': target_user.username,
                'full_name': target_user.get_full_name(),
                'period': {
                    'start_date': start_date.isoformat(),
                    'end_date': end_date.isoformat()
                },
                'total_actions': user_logs.count(),
                'action_breakdown': list(user_logs.values('action').annotate(
                    count=Count('id')
                ).order_by('-count')),
                'resource_breakdown': list(user_logs.values('resource_type').annotate(
                    count=Count('id')
                ).order_by('-count')),
                'daily_activity': []
            }
            
            # Calculate daily activity
            current_date = start_date.date()
            end_date_only = end_date.date()
            
            while current_date <= end_date_only:
                day_start = timezone.make_aware(datetime.combine(current_date, datetime.min.time()))
                day_end = timezone.make_aware(datetime.combine(current_date, datetime.max.time()))
                
                day_count = user_logs.filter(
                    timestamp__gte=day_start,
                    timestamp__lte=day_end
                ).count()
                
                activity_summary['daily_activity'].append({
                    'date': current_date.isoformat(),
                    'action_count': day_count
                })
                
                current_date += timedelta(days=1)
            
            # Log user activity report access
            audit_service.log_clinical_action(
                action='AUDIT_REPORT_GENERATE',
                user=request.user,
                resource_type='AUDIT_REPORT',
                clinic=request.user.clinic,
                request=request,
                details={
                    'report_type': 'user_activity',
                    'target_user_id': target_user.id,
                    'period': activity_summary['period'],
                    'format': report_format
                }
            )
            
            # Return in requested format
            if report_format == 'csv':
                return self._generate_user_activity_csv_response(activity_summary, user_logs)
            else:
                return Response(activity_summary)
                
        except Exception as e:
            logger.error(f"Error generating user activity report: {str(e)}")
            return Response({
                'error': str(e)
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    
    def _verify_resource_access(self, user, resource_type: str, resource_id: str) -> bool:
        """Verify user has access to the specified resource."""
        try:
            if resource_type == 'CLINICAL_RECORD':
                record = ClinicalRecord.objects.get(id=resource_id, clinic=user.clinic)
                return True
            elif resource_type == 'CLINICAL_DOCUMENT':
                document = ClinicalDocument.objects.get(
                    id=resource_id, 
                    clinical_record__clinic=user.clinic
                )
                return True
            # Add other resource type checks as needed
            return True
        except:
            return False
    
    def _generate_csv_response(self, report_data: Dict[str, Any], filename: str) -> HttpResponse:
        """Generate CSV response for compliance report."""
        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = f'attachment; filename="{filename}_{timezone.now().strftime("%Y%m%d")}.csv"'
        
        writer = csv.writer(response)
        
        # Write header
        writer.writerow(['Metric', 'Value'])
        
        # Write summary data
        summary = report_data.get('summary', {})
        for key, value in summary.items():
            writer.writerow([key.replace('_', ' ').title(), value])
        
        # Write action breakdown
        writer.writerow([])
        writer.writerow(['Action Breakdown'])
        writer.writerow(['Action', 'Count'])
        
        for action in report_data.get('action_breakdown', []):
            writer.writerow([action['action'], action['count']])
        
        return response
    
    def _generate_audit_csv_response(self, audit_data: List[Dict], filename: str) -> HttpResponse:
        """Generate CSV response for audit trail."""
        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = f'attachment; filename="{filename}_{timezone.now().strftime("%Y%m%d")}.csv"'
        
        writer = csv.writer(response)
        
        # Write header
        writer.writerow([
            'Timestamp', 'User', 'Action', 'Resource Type', 
            'Resource ID', 'IP Address', 'Details'
        ])
        
        # Write audit data
        for log in audit_data:
            writer.writerow([
                log['timestamp'],
                log['user'],
                log['action'],
                log['resource_type'],
                log['resource_id'],
                log['ip_address'],
                json.dumps(log['details']) if log['details'] else ''
            ])
        
        return response
    
    def _generate_user_activity_csv_response(self, activity_summary: Dict, user_logs) -> HttpResponse:
        """Generate CSV response for user activity report."""
        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = f'attachment; filename="user_activity_{activity_summary["user_id"]}_{timezone.now().strftime("%Y%m%d")}.csv"'
        
        writer = csv.writer(response)
        
        # Write summary
        writer.writerow(['User Activity Summary'])
        writer.writerow(['User', activity_summary['full_name']])
        writer.writerow(['Period', f"{activity_summary['period']['start_date']} to {activity_summary['period']['end_date']}"])
        writer.writerow(['Total Actions', activity_summary['total_actions']])
        writer.writerow([])
        
        # Write detailed logs
        writer.writerow(['Detailed Activity Log'])
        writer.writerow(['Timestamp', 'Action', 'Resource Type', 'Resource ID', 'IP Address'])
        
        for log in user_logs:
            writer.writerow([
                log.timestamp.isoformat(),
                log.action,
                log.resource_type,
                log.resource_id,
                log.ip_address
            ])
        
        return response


@require_http_methods(["GET"])
@login_required
@audit_clinical_action('AUDIT_REPORT_GENERATE', 'AUDIT_REPORT')
def audit_dashboard(request):
    """
    Audit dashboard with summary statistics.
    """
    try:
        if not hasattr(request.user, 'clinic'):
            return JsonResponse({'error': 'No clinic context'}, status=400)
        
        clinic = request.user.clinic
        
        # Get recent activity (last 24 hours)
        last_24h = timezone.now() - timedelta(hours=24)
        recent_logs = AuditLog.objects.filter(
            clinic=clinic,
            timestamp__gte=last_24h,
            action__in=list(audit_service.CLINICAL_ACTIONS.keys())
        )
        
        # Calculate dashboard metrics
        dashboard_data = {
            'clinic_name': clinic.name,
            'last_24_hours': {
                'total_actions': recent_logs.count(),
                'unique_users': recent_logs.values('user').distinct().count(),
                'document_accesses': recent_logs.filter(
                    resource_type='CLINICAL_DOCUMENT'
                ).count(),
                'external_accesses': recent_logs.filter(
                    action='EXTERNAL_ACCESS'
                ).count(),
                'unauthorized_attempts': recent_logs.filter(
                    action='UNAUTHORIZED_ACCESS_ATTEMPT'
                ).count()
            },
            'top_actions': list(recent_logs.values('action').annotate(
                count=Count('id')
            ).order_by('-count')[:5]),
            'top_users': list(recent_logs.values(
                'user__username', 'user__first_name', 'user__last_name'
            ).annotate(
                count=Count('id')
            ).order_by('-count')[:5]),
            'generated_at': timezone.now().isoformat()
        }
        
        return JsonResponse(dashboard_data)
        
    except Exception as e:
        logger.error(f"Error generating audit dashboard: {str(e)}")
        return JsonResponse({'error': str(e)}, status=500)