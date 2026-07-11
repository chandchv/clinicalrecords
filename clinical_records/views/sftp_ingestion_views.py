"""
SFTP Ingestion API Views

This module provides REST API endpoints for SFTP ingestion functionality,
including monitor management, file processing, and statistics.
"""
import logging
import os
from django.http import Http404
from rest_framework import viewsets, status, permissions
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.exceptions import ValidationError

from ..services.sftp_ingestion_service import sftp_ingestion_service, SFTPIngestionError
from ..permissions import ClinicalRecordPermission
from users.models import AuditLog

logger = logging.getLogger(__name__)


class SFTPIngestionViewSet(viewsets.ViewSet):
    """
    ViewSet for SFTP ingestion operations
    
    Provides endpoints for managing SFTP monitors, processing files,
    and getting statistics.
    """
    permission_classes = [permissions.IsAuthenticated, ClinicalRecordPermission]
    
    @action(detail=False, methods=['post'])
    def start_monitor(self, request):
        """
        Start SFTP monitoring for the current clinic
        
        Expects configuration in request body:
        {
            "monitor_directory": "/path/to/monitor",
            "connection_type": "local" or "remote",
            "host": "sftp.example.com" (for remote),
            "username": "user" (for remote),
            "password": "pass" (for remote, optional),
            "key_file": "/path/to/key" (for remote, optional),
            "port": 22 (for remote, optional),
            "check_interval": 60 (optional, seconds),
            "move_processed_files": true (optional),
            "move_failed_files": true (optional),
            "processed_directory": "processed" (optional),
            "failed_directory": "failed" (optional)
        }
        """
        user = request.user
        if not hasattr(user, 'current_tenant') or not user.current_tenant:
            return Response(
                {'error': 'No clinic context available'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Validate required fields
        config = request.data
        required_fields = ['monitor_directory', 'connection_type']
        
        for field in required_fields:
            if field not in config:
                return Response(
                    {'error': f'Missing required field: {field}'},
                    status=status.HTTP_400_BAD_REQUEST
                )
        
        # Validate connection type
        if config['connection_type'] not in ['local', 'remote']:
            return Response(
                {'error': 'connection_type must be "local" or "remote"'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Validate remote connection fields
        if config['connection_type'] == 'remote':
            remote_required = ['host', 'username']
            for field in remote_required:
                if field not in config:
                    return Response(
                        {'error': f'Missing required field for remote connection: {field}'},
                        status=status.HTTP_400_BAD_REQUEST
                    )
        
        try:
            monitor_id = sftp_ingestion_service.start_monitoring(
                clinic=user.current_tenant,
                config=config
            )
            
            return Response({
                'message': 'SFTP monitoring started successfully',
                'monitor_id': monitor_id,
                'config': {
                    'monitor_directory': config['monitor_directory'],
                    'connection_type': config['connection_type'],
                    'check_interval': config.get('check_interval', 60)
                }
            }, status=status.HTTP_201_CREATED)
            
        except SFTPIngestionError as e:
            return Response(
                {'error': str(e)},
                status=status.HTTP_400_BAD_REQUEST
            )
        except Exception as e:
            logger.error(f"Unexpected error starting SFTP monitor: {e}")
            return Response(
                {'error': 'Internal server error'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    @action(detail=False, methods=['post'])
    def stop_monitor(self, request):
        """
        Stop SFTP monitoring
        
        Expects monitor_id in request body:
        {
            "monitor_id": "clinic_id_directory"
        }
        """
        monitor_id = request.data.get('monitor_id')
        if not monitor_id:
            return Response(
                {'error': 'monitor_id is required'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            sftp_ingestion_service.stop_monitoring(monitor_id)
            
            return Response({
                'message': 'SFTP monitoring stopped successfully',
                'monitor_id': monitor_id
            }, status=status.HTTP_200_OK)
            
        except SFTPIngestionError as e:
            return Response(
                {'error': str(e)},
                status=status.HTTP_400_BAD_REQUEST
            )
        except Exception as e:
            logger.error(f"Unexpected error stopping SFTP monitor: {e}")
            return Response(
                {'error': 'Internal server error'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    @action(detail=False, methods=['get'])
    def monitor_status(self, request):
        """
        Get status of SFTP monitor
        
        Query parameter: monitor_id
        """
        monitor_id = request.query_params.get('monitor_id')
        if not monitor_id:
            return Response(
                {'error': 'monitor_id parameter is required'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            status_info = sftp_ingestion_service.get_monitor_status(monitor_id)
            
            return Response(status_info, status=status.HTTP_200_OK)
            
        except Exception as e:
            logger.error(f"Error getting monitor status: {e}")
            return Response(
                {'error': 'Failed to get monitor status'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    @action(detail=False, methods=['get'])
    def list_monitors(self, request):
        """
        List all active SFTP monitors
        """
        try:
            monitors = sftp_ingestion_service.list_active_monitors()
            
            # Filter by current clinic if user has tenant context
            user = request.user
            if hasattr(user, 'current_tenant') and user.current_tenant:
                clinic_id = str(user.current_tenant.id)
                monitors = [m for m in monitors if m['clinic_id'] == clinic_id]
            
            return Response({
                'monitors': monitors,
                'total_count': len(monitors)
            }, status=status.HTTP_200_OK)
            
        except Exception as e:
            logger.error(f"Error listing monitors: {e}")
            return Response(
                {'error': 'Failed to list monitors'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    @action(detail=False, methods=['post'])
    def process_file(self, request):
        """
        Process a single file manually
        
        Expects file_path in request body:
        {
            "file_path": "/path/to/file.pdf"
        }
        """
        user = request.user
        if not hasattr(user, 'current_tenant') or not user.current_tenant:
            return Response(
                {'error': 'No clinic context available'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        file_path = request.data.get('file_path')
        if not file_path:
            return Response(
                {'error': 'file_path is required'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            result = sftp_ingestion_service.process_single_file(
                file_path=file_path,
                clinic=user.current_tenant,
                processing_user=user
            )
            
            return Response({
                'message': 'File processed successfully' if result['success'] else 'File processing failed',
                'result': result
            }, status=status.HTTP_200_OK if result['success'] else status.HTTP_400_BAD_REQUEST)
            
        except SFTPIngestionError as e:
            return Response(
                {'error': str(e)},
                status=status.HTTP_400_BAD_REQUEST
            )
        except Exception as e:
            logger.error(f"Unexpected error processing file: {e}")
            return Response(
                {'error': 'Internal server error'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    @action(detail=False, methods=['get'])
    def statistics(self, request):
        """
        Get SFTP processing statistics for the current clinic
        """
        user = request.user
        if not hasattr(user, 'current_tenant') or not user.current_tenant:
            return Response(
                {'error': 'No clinic context available'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Get days parameter (default 30)
        try:
            days = int(request.query_params.get('days', 30))
            if days <= 0 or days > 365:
                days = 30
        except ValueError:
            days = 30
        
        try:
            stats = sftp_ingestion_service.get_processing_statistics(
                clinic=user.current_tenant,
                days=days
            )
            
            return Response(stats, status=status.HTTP_200_OK)
            
        except Exception as e:
            logger.error(f"Error getting SFTP statistics: {e}")
            return Response(
                {'error': 'Failed to get statistics'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    @action(detail=False, methods=['get'])
    def unmatched_files(self, request):
        """
        Get list of files that couldn't be matched to patients
        """
        user = request.user
        if not hasattr(user, 'current_tenant') or not user.current_tenant:
            return Response(
                {'error': 'No clinic context available'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Get pagination parameters
        try:
            page = int(request.query_params.get('page', 1))
            page_size = int(request.query_params.get('page_size', 20))
            if page_size > 100:
                page_size = 100
        except ValueError:
            page = 1
            page_size = 20
        
        # Get days parameter
        try:
            days = int(request.query_params.get('days', 30))
            if days <= 0 or days > 365:
                days = 30
        except ValueError:
            days = 30
        
        try:
            from datetime import timedelta
            from django.utils import timezone
            
            since_date = timezone.now() - timedelta(days=days)
            
            # Get unmatched file logs
            unmatched_logs = AuditLog.objects.filter(
                tenant=user.current_tenant,
                action__in=['SFTP_FILE_UNMATCHED', 'SFTP_FILE_UNPARSEABLE'],
                created_at__gte=since_date
            ).order_by('-created_at')
            
            # Paginate
            start = (page - 1) * page_size
            end = start + page_size
            paginated_logs = unmatched_logs[start:end]
            
            # Format results
            results = []
            for log in paginated_logs:
                results.append({
                    'id': str(log.id),
                    'timestamp': log.created_at,
                    'filename': log.details.get('filename', ''),
                    'action': log.action,
                    'reason': log.details.get('reason', ''),
                    'parsed_metadata': log.details.get('parsed_metadata', {}),
                })
            
            return Response({
                'results': results,
                'total_count': unmatched_logs.count(),
                'page': page,
                'page_size': page_size,
                'has_next': end < unmatched_logs.count()
            }, status=status.HTTP_200_OK)
            
        except Exception as e:
            logger.error(f"Error getting unmatched files: {e}")
            return Response(
                {'error': 'Failed to get unmatched files'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    @action(detail=False, methods=['post'])
    def test_filename_parsing(self, request):
        """
        Test filename parsing logic
        
        This endpoint is useful for testing and debugging filename parsing rules.
        """
        filename = request.data.get('filename')
        if not filename:
            return Response(
                {'error': 'filename is required'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            from ..services.sftp_ingestion_service import FileNamingConventionParser
            
            parser = FileNamingConventionParser()
            metadata = parser.parse_filename(filename)
            
            return Response({
                'filename': filename,
                'parsing_result': metadata,
                'available_patterns': list(parser.naming_patterns.keys()),
                'record_type_mappings': parser.record_type_mappings
            }, status=status.HTTP_200_OK)
            
        except Exception as e:
            logger.error(f"Error testing filename parsing: {e}")
            return Response(
                {'error': 'Failed to test filename parsing'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    @action(detail=False, methods=['post'])
    def test_patient_matching(self, request):
        """
        Test patient matching from parsed metadata
        
        This endpoint is useful for testing and debugging patient matching rules.
        """
        user = request.user
        if not hasattr(user, 'current_tenant') or not user.current_tenant:
            return Response(
                {'error': 'No clinic context available'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        metadata = request.data.get('metadata', {})
        if not metadata:
            return Response(
                {'error': 'metadata is required'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            from ..services.sftp_ingestion_service import SFTPPatientMatcher
            
            matcher = SFTPPatientMatcher(user.current_tenant)
            patient = matcher.match_patient_from_metadata(metadata)
            
            if patient:
                return Response({
                    'match_found': True,
                    'patient': {
                        'id': str(patient.id),
                        'name': patient.get_full_name(),
                        'phone': patient.phone,
                        'email': getattr(patient, 'email', '')
                    },
                    'metadata_used': metadata
                }, status=status.HTTP_200_OK)
            else:
                return Response({
                    'match_found': False,
                    'message': 'No patient match found',
                    'metadata_used': metadata
                }, status=status.HTTP_200_OK)
                
        except Exception as e:
            logger.error(f"Error testing patient matching: {e}")
            return Response(
                {'error': 'Failed to test patient matching'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    @action(detail=False, methods=['get'])
    def configuration(self, request):
        """
        Get SFTP ingestion configuration information
        """
        user = request.user
        if not hasattr(user, 'current_tenant') or not user.current_tenant:
            return Response(
                {'error': 'No clinic context available'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Return configuration information
        return Response({
            'clinic_id': str(user.current_tenant.id),
            'clinic_name': user.current_tenant.name,
            'supported_file_types': [
                'application/pdf',
                'image/jpeg',
                'image/png',
                'image/tiff',
                'application/dicom',
                'text/csv',
                'text/plain'
            ],
            'connection_types': ['local', 'remote'],
            'naming_conventions': [
                'standard: clinic_patient_type_date.ext',
                'dash_separated: CLINIC-PATIENT-TYPE-YYYYMMDD.ext',
                'detailed: PatientID_RecordType_YYYYMMDD_HHMMSS.ext',
                'date_first: YYYYMMDD_PatientID_Type.ext',
                'type_first: Type_PatientID_YYYYMMDD.ext',
                'name_based: LastName_FirstName_DOB_Type.ext',
                'mrn_based: MRN12345_LabReport_20240101.pdf'
            ],
            'record_types': [
                'lab_report',
                'prescription',
                'imaging',
                'discharge_summary',
                'consultation',
                'vaccination',
                'other'
            ],
            'default_check_interval': 60,
            'max_file_size_mb': 100
        }, status=status.HTTP_200_OK)
    
    @action(detail=False, methods=['get'])
    def monitoring_failures(self, request):
        """
        Get list of SFTP monitoring failures for alerting
        """
        user = request.user
        if not hasattr(user, 'current_tenant') or not user.current_tenant:
            return Response(
                {'error': 'No clinic context available'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Get days parameter
        try:
            days = int(request.query_params.get('days', 7))
            if days <= 0 or days > 30:
                days = 7
        except ValueError:
            days = 7
        
        try:
            from datetime import timedelta
            from django.utils import timezone
            
            since_date = timezone.now() - timedelta(days=days)
            
            # Get monitoring failure logs
            failure_logs = AuditLog.objects.filter(
                tenant=user.current_tenant,
                action='SFTP_MONITORING_FAILURE',
                created_at__gte=since_date
            ).order_by('-created_at')
            
            # Format results
            results = []
            for log in failure_logs:
                results.append({
                    'id': str(log.id),
                    'timestamp': log.created_at,
                    'monitor_directory': log.details.get('monitor_directory', ''),
                    'connection_type': log.details.get('connection_type', ''),
                    'error_message': log.details.get('error_message', ''),
                    'last_successful_check': log.details.get('last_successful_check')
                })
            
            return Response({
                'failures': results,
                'total_count': failure_logs.count(),
                'period_days': days
            }, status=status.HTTP_200_OK)
            
        except Exception as e:
            logger.error(f"Error getting monitoring failures: {e}")
            return Response(
                {'error': 'Failed to get monitoring failures'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )