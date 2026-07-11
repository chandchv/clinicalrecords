"""
Email Ingestion API Views

This module provides REST API endpoints for email ingestion functionality,
including email processing, patient matching, and ingestion statistics.
"""
import logging
from django.http import Http404
from django.core.files.storage import default_storage
from rest_framework import viewsets, status, permissions
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.parsers import MultiPartParser, FormParser
from rest_framework.exceptions import ValidationError

from ..services.email_ingestion_service import email_ingestion_service, EmailIngestionError
from ..permissions import ClinicalRecordPermission
from users.models import AuditLog

logger = logging.getLogger(__name__)


class EmailIngestionViewSet(viewsets.ViewSet):
    """
    ViewSet for email ingestion operations
    
    Provides endpoints for processing emails, checking statistics,
    and managing email ingestion configuration.
    """
    permission_classes = [permissions.IsAuthenticated, ClinicalRecordPermission]
    parser_classes = [MultiPartParser, FormParser]
    
    @action(detail=False, methods=['post'])
    def process_email_content(self, request):
        """
        Process email content directly
        
        Expects email content as raw text in request body.
        """
        user = request.user
        if not hasattr(user, 'current_tenant') or not user.current_tenant:
            return Response(
                {'error': 'No clinic context available'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        email_content = request.data.get('email_content')
        if not email_content:
            return Response(
                {'error': 'email_content is required'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            result = email_ingestion_service.process_email_message(
                email_content=email_content,
                clinic=user.current_tenant,
                processing_user=user
            )
            
            return Response({
                'message': 'Email processed successfully',
                'result': result
            }, status=status.HTTP_200_OK)
            
        except EmailIngestionError as e:
            return Response(
                {'error': str(e)},
                status=status.HTTP_400_BAD_REQUEST
            )
        except Exception as e:
            logger.error(f"Unexpected error processing email: {e}")
            return Response(
                {'error': 'Internal server error'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    @action(detail=False, methods=['post'])
    def process_email_file(self, request):
        """
        Process email from uploaded file
        
        Expects email file upload in 'email_file' field.
        """
        user = request.user
        if not hasattr(user, 'current_tenant') or not user.current_tenant:
            return Response(
                {'error': 'No clinic context available'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        email_file = request.FILES.get('email_file')
        if not email_file:
            return Response(
                {'error': 'email_file is required'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Validate file type
        if not email_file.name.lower().endswith(('.eml', '.msg', '.txt')):
            return Response(
                {'error': 'Invalid file type. Expected .eml, .msg, or .txt'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Save file temporarily
        try:
            import tempfile
            import os
            
            with tempfile.NamedTemporaryFile(delete=False, suffix='.eml') as temp_file:
                for chunk in email_file.chunks():
                    temp_file.write(chunk)
                temp_file.flush()
                
                try:
                    result = email_ingestion_service.process_email_file(
                        email_file_path=temp_file.name,
                        clinic=user.current_tenant,
                        processing_user=user
                    )
                    
                    return Response({
                        'message': 'Email file processed successfully',
                        'result': result
                    }, status=status.HTTP_200_OK)
                    
                finally:
                    # Clean up temp file
                    try:
                        os.unlink(temp_file.name)
                    except Exception:
                        pass
                        
        except EmailIngestionError as e:
            return Response(
                {'error': str(e)},
                status=status.HTTP_400_BAD_REQUEST
            )
        except Exception as e:
            logger.error(f"Unexpected error processing email file: {e}")
            return Response(
                {'error': 'Internal server error'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    @action(detail=False, methods=['get'])
    def statistics(self, request):
        """
        Get email ingestion statistics for the current clinic
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
            stats = email_ingestion_service.get_processing_statistics(
                clinic=user.current_tenant,
                days=days
            )
            
            return Response(stats, status=status.HTTP_200_OK)
            
        except Exception as e:
            logger.error(f"Error getting email statistics: {e}")
            return Response(
                {'error': 'Failed to get statistics'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    @action(detail=False, methods=['get'])
    def unmatched_emails(self, request):
        """
        Get list of emails that couldn't be matched to patients
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
            
            # Get unmatched email logs
            unmatched_logs = AuditLog.objects.filter(
                tenant=user.current_tenant,
                action='EMAIL_UNMATCHED',
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
                    'sender': log.details.get('sender', ''),
                    'subject': log.details.get('subject', ''),
                    'date': log.details.get('date', ''),
                    'content_preview': log.details.get('content_preview', ''),
                    'reason': log.details.get('reason', '')
                })
            
            return Response({
                'results': results,
                'total_count': unmatched_logs.count(),
                'page': page,
                'page_size': page_size,
                'has_next': end < unmatched_logs.count()
            }, status=status.HTTP_200_OK)
            
        except Exception as e:
            logger.error(f"Error getting unmatched emails: {e}")
            return Response(
                {'error': 'Failed to get unmatched emails'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    @action(detail=False, methods=['post'])
    def test_patient_matching(self, request):
        """
        Test patient matching logic with sample email content
        
        This endpoint is useful for testing and debugging patient matching rules.
        """
        user = request.user
        if not hasattr(user, 'current_tenant') or not user.current_tenant:
            return Response(
                {'error': 'No clinic context available'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        email_content = request.data.get('email_content', '')
        sender_email = request.data.get('sender_email', '')
        subject = request.data.get('subject', '')
        
        if not email_content:
            return Response(
                {'error': 'email_content is required'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            from ..services.email_ingestion_service import PatientMatcher
            
            matcher = PatientMatcher(user.current_tenant)
            patient = matcher.match_patient_from_email(
                email_content=email_content,
                sender_email=sender_email,
                subject=subject
            )
            
            if patient:
                return Response({
                    'match_found': True,
                    'patient': {
                        'id': str(patient.id),
                        'name': patient.get_full_name(),
                        'phone': patient.phone,
                        'email': getattr(patient, 'email', '')
                    }
                }, status=status.HTTP_200_OK)
            else:
                return Response({
                    'match_found': False,
                    'message': 'No patient match found'
                }, status=status.HTTP_200_OK)
                
        except Exception as e:
            logger.error(f"Error testing patient matching: {e}")
            return Response(
                {'error': 'Failed to test patient matching'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    @action(detail=False, methods=['post'])
    def test_document_categorization(self, request):
        """
        Test document categorization logic
        
        This endpoint is useful for testing and debugging document categorization rules.
        """
        filename = request.data.get('filename', '')
        content = request.data.get('content', '')
        subject = request.data.get('subject', '')
        
        if not filename:
            return Response(
                {'error': 'filename is required'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            from ..services.email_ingestion_service import DocumentCategorizer
            
            categorizer = DocumentCategorizer()
            category = categorizer.categorize_document(
                filename=filename,
                content=content,
                subject=subject
            )
            
            return Response({
                'filename': filename,
                'predicted_category': category,
                'available_categories': list(categorizer.category_patterns.keys())
            }, status=status.HTTP_200_OK)
            
        except Exception as e:
            logger.error(f"Error testing document categorization: {e}")
            return Response(
                {'error': 'Failed to test document categorization'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    @action(detail=False, methods=['get'])
    def configuration(self, request):
        """
        Get email ingestion configuration for the current clinic
        """
        user = request.user
        if not hasattr(user, 'current_tenant') or not user.current_tenant:
            return Response(
                {'error': 'No clinic context available'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Return configuration information
        # This could be extended to include clinic-specific settings
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
                'application/vnd.ms-excel'
            ],
            'max_file_size_mb': 100,
            'patient_matching_strategies': [
                'patient_id_patterns',
                'phone_number_patterns',
                'name_patterns',
                'sender_email_matching'
            ],
            'document_categories': [
                'lab_report',
                'prescription',
                'imaging',
                'discharge_summary',
                'consultation',
                'vaccination',
                'other'
            ]
        }, status=status.HTTP_200_OK)