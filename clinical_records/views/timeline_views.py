"""
Views for patient timeline functionality.

This module provides both API and template views for displaying
patient clinical record timelines with filtering and search capabilities.
"""

import json
import logging
from typing import Dict, Any, Optional

from django.shortcuts import render, get_object_or_404
from django.http import JsonResponse, HttpRequest, HttpResponse
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_http_methods
from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator
from django.views import View
from django.core.exceptions import PermissionDenied
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from users.models import Patient
from ..services.timeline_service import timeline_service
from ..permissions.rest_permissions import ClinicalRecordPermission
from ..decorators.audit_decorators import audit_clinical_action

logger = logging.getLogger(__name__)


class PatientTimelineView(View):
    """Main view for patient timeline display."""
    
    @method_decorator(login_required)
    @method_decorator(audit_clinical_action('TIMELINE_PAGE_ACCESSED'))
    def get(self, request: HttpRequest, patient_id: str) -> HttpResponse:
        """
        Display patient timeline page.
        
        Args:
            request: HTTP request
            patient_id: ID of the patient
            
        Returns:
            Rendered timeline template
        """
        try:
            # Get patient
            patient = get_object_or_404(Patient, id=patient_id)
            
            # Check if user has access to this patient
            if not timeline_service._check_patient_access(request.user, patient):
                raise PermissionDenied("You do not have access to this patient's records")
            
            # Get timeline summary for initial page load
            try:
                summary = timeline_service.get_timeline_summary(
                    patient=patient,
                    user=request.user,
                    date_range_days=30
                )
            except Exception as e:
                logger.error(f"Error getting timeline summary: {e}")
                summary = {
                    'patient_id': str(patient.id),
                    'patient_name': patient.get_full_name(),
                    'total_records': 0,
                    'error': 'Unable to load timeline summary'
                }
            
            # Prepare context
            context = {
                'patient': patient,
                'timeline_summary': summary,
                'patient_id': str(patient.id),
                'patient_name': patient.get_full_name(),
                'clinic_name': patient.clinic.name,
                'available_record_types': self._get_available_record_types(patient),
                'page_title': f"Timeline - {patient.get_full_name()}"
            }
            
            return render(request, 'clinical_records/timeline.html', context)
            
        except PermissionDenied:
            raise
        except Exception as e:
            logger.error(f"Error displaying timeline page: {e}")
            return render(request, 'clinical_records/error.html', {
                'error_message': 'Unable to load patient timeline',
                'error_details': str(e)
            }, status=500)
    
    def _get_available_record_types(self, patient: Patient) -> list:
        """Get list of available record types for this patient."""
        try:
            from ..models import ClinicalRecord
            
            record_types = ClinicalRecord.objects.filter(
                patient=patient
            ).values_list('record_type', flat=True).distinct()
            
            return list(record_types)
            
        except Exception as e:
            logger.error(f"Error getting record types: {e}")
            return []


@api_view(['GET'])
@permission_classes([IsAuthenticated, ClinicalRecordPermission])
def get_timeline_data(request: HttpRequest, patient_id: str) -> Response:
    """
    API endpoint to get timeline data for a patient.
    
    Args:
        request: HTTP request
        patient_id: ID of the patient
        
    Returns:
        JSON response with timeline data
    """
    try:
        # Get patient
        patient = get_object_or_404(Patient, id=patient_id)
        
        # Parse query parameters
        page = int(request.GET.get('page', 1))
        page_size = int(request.GET.get('page_size', 20))
        
        # Parse filters
        filters = {}
        if request.GET.get('start_date'):
            filters['start_date'] = request.GET.get('start_date')
        if request.GET.get('end_date'):
            filters['end_date'] = request.GET.get('end_date')
        if request.GET.get('record_types'):
            record_types = request.GET.get('record_types').split(',')
            filters['record_types'] = [rt.strip() for rt in record_types if rt.strip()]
        if request.GET.get('has_documents'):
            filters['has_documents'] = request.GET.get('has_documents').lower() == 'true'
        if request.GET.get('processing_status'):
            filters['processing_status'] = request.GET.get('processing_status')
        
        # Get timeline data
        timeline_data = timeline_service.get_patient_timeline(
            patient=patient,
            user=request.user,
            filters=filters if filters else None,
            page=page,
            page_size=page_size
        )
        
        return Response(timeline_data, status=status.HTTP_200_OK)
        
    except PermissionError as e:
        return Response(
            {'error': str(e)},
            status=status.HTTP_403_FORBIDDEN
        )
    except ValueError as e:
        return Response(
            {'error': str(e)},
            status=status.HTTP_400_BAD_REQUEST
        )
    except Exception as e:
        logger.error(f"Error getting timeline data: {e}")
        return Response(
            {'error': 'Unable to load timeline data'},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['GET'])
@permission_classes([IsAuthenticated, ClinicalRecordPermission])
def get_timeline_summary(request: HttpRequest, patient_id: str) -> Response:
    """
    API endpoint to get timeline summary for a patient.
    
    Args:
        request: HTTP request
        patient_id: ID of the patient
        
    Returns:
        JSON response with timeline summary
    """
    try:
        # Get patient
        patient = get_object_or_404(Patient, id=patient_id)
        
        # Parse date range parameter
        date_range_days = int(request.GET.get('date_range_days', 30))
        
        # Get timeline summary
        summary = timeline_service.get_timeline_summary(
            patient=patient,
            user=request.user,
            date_range_days=date_range_days
        )
        
        return Response(summary, status=status.HTTP_200_OK)
        
    except PermissionError as e:
        return Response(
            {'error': str(e)},
            status=status.HTTP_403_FORBIDDEN
        )
    except ValueError as e:
        return Response(
            {'error': str(e)},
            status=status.HTTP_400_BAD_REQUEST
        )
    except Exception as e:
        logger.error(f"Error getting timeline summary: {e}")
        return Response(
            {'error': 'Unable to load timeline summary'},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['GET'])
@permission_classes([IsAuthenticated, ClinicalRecordPermission])
def search_timeline(request: HttpRequest, patient_id: str) -> Response:
    """
    API endpoint to search patient timeline.
    
    Args:
        request: HTTP request
        patient_id: ID of the patient
        
    Returns:
        JSON response with search results
    """
    try:
        # Get patient
        patient = get_object_or_404(Patient, id=patient_id)
        
        # Get search parameters
        search_query = request.GET.get('q', '').strip()
        search_type = request.GET.get('type', 'all')
        
        if not search_query:
            return Response(
                {'error': 'Search query is required'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Perform search
        results = timeline_service.search_timeline(
            patient=patient,
            user=request.user,
            search_query=search_query,
            search_type=search_type
        )
        
        return Response({
            'patient_id': str(patient.id),
            'search_query': search_query,
            'search_type': search_type,
            'results_count': len(results),
            'results': results
        }, status=status.HTTP_200_OK)
        
    except PermissionError as e:
        return Response(
            {'error': str(e)},
            status=status.HTTP_403_FORBIDDEN
        )
    except ValueError as e:
        return Response(
            {'error': str(e)},
            status=status.HTTP_400_BAD_REQUEST
        )
    except Exception as e:
        logger.error(f"Error searching timeline: {e}")
        return Response(
            {'error': 'Unable to search timeline'},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['GET'])
@permission_classes([IsAuthenticated, ClinicalRecordPermission])
def get_record_details(request: HttpRequest, record_id: str) -> Response:
    """
    API endpoint to get detailed information for a specific record.
    
    Args:
        request: HTTP request
        record_id: ID of the clinical record
        
    Returns:
        JSON response with record details
    """
    try:
        # Get record details
        record_details = timeline_service.get_record_details(
            record_id=record_id,
            user=request.user
        )
        
        return Response(record_details, status=status.HTTP_200_OK)
        
    except PermissionError as e:
        return Response(
            {'error': str(e)},
            status=status.HTTP_403_FORBIDDEN
        )
    except ValueError as e:
        return Response(
            {'error': str(e)},
            status=status.HTTP_404_NOT_FOUND
        )
    except Exception as e:
        logger.error(f"Error getting record details: {e}")
        return Response(
            {'error': 'Unable to load record details'},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@require_http_methods(["GET"])
@login_required
def timeline_export(request: HttpRequest, patient_id: str) -> HttpResponse:
    """
    Export patient timeline data.
    
    Args:
        request: HTTP request
        patient_id: ID of the patient
        
    Returns:
        JSON or CSV export of timeline data
    """
    try:
        # Get patient
        patient = get_object_or_404(Patient, id=patient_id)
        
        # Check export permissions
        from ..services.access_control_service import access_control_service
        permissions = access_control_service.get_user_permissions_summary(
            user=request.user,
            clinic=patient.clinic
        )
        
        if not permissions.get('permissions', {}).get('can_export_data', False):
            raise PermissionDenied("You do not have permission to export data")
        
        # Get export format
        export_format = request.GET.get('format', 'json').lower()
        
        # Get all timeline data (no pagination for export)
        timeline_data = timeline_service.get_patient_timeline(
            patient=patient,
            user=request.user,
            page_size=1000  # Large page size for export
        )
        
        if export_format == 'csv':
            return _export_timeline_csv(timeline_data, patient)
        else:
            # JSON export
            response = JsonResponse(timeline_data, json_dumps_params={'indent': 2})
            response['Content-Disposition'] = f'attachment; filename="timeline_{patient_id}.json"'
            return response
            
    except PermissionDenied:
        raise
    except Exception as e:
        logger.error(f"Error exporting timeline: {e}")
        return JsonResponse(
            {'error': 'Unable to export timeline data'},
            status=500
        )


def _export_timeline_csv(timeline_data: Dict[str, Any], patient: Patient) -> HttpResponse:
    """Export timeline data as CSV."""
    import csv
    from django.http import HttpResponse
    
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = f'attachment; filename="timeline_{patient.id}.csv"'
    
    writer = csv.writer(response)
    
    # Write header
    writer.writerow([
        'Record ID',
        'Title',
        'Description',
        'Record Type',
        'Created Date',
        'Updated Date',
        'Documents Count',
        'Has Unprocessed Documents'
    ])
    
    # Write data rows
    for item in timeline_data.get('timeline_items', []):
        writer.writerow([
            item.get('id', ''),
            item.get('title', ''),
            item.get('description', ''),
            item.get('record_type', ''),
            item.get('created_at', ''),
            item.get('updated_at', ''),
            item.get('documents_count', 0),
            'Yes' if item.get('has_unprocessed_documents', False) else 'No'
        ])
    
    return response


# Legacy function-based views for backward compatibility
@login_required
@audit_clinical_action('TIMELINE_ACCESSED')
def patient_timeline_legacy(request: HttpRequest, patient_id: str) -> HttpResponse:
    """Legacy function-based view for patient timeline."""
    view = PatientTimelineView()
    return view.get(request, patient_id)


@csrf_exempt
@require_http_methods(["POST"])
@login_required
def update_timeline_preferences(request: HttpRequest) -> JsonResponse:
    """
    Update user's timeline display preferences.
    
    Args:
        request: HTTP request with preference data
        
    Returns:
        JSON response confirming update
    """
    try:
        # Parse request data
        data = json.loads(request.body)
        
        # Get or create user preferences
        # This would typically be stored in a UserPreferences model
        # For now, we'll store in session
        preferences = request.session.get('timeline_preferences', {})
        
        # Update preferences
        if 'default_page_size' in data:
            preferences['default_page_size'] = int(data['default_page_size'])
        if 'default_date_range' in data:
            preferences['default_date_range'] = int(data['default_date_range'])
        if 'show_document_previews' in data:
            preferences['show_document_previews'] = bool(data['show_document_previews'])
        if 'auto_refresh_interval' in data:
            preferences['auto_refresh_interval'] = int(data['auto_refresh_interval'])
        
        # Save to session
        request.session['timeline_preferences'] = preferences
        
        return JsonResponse({
            'success': True,
            'message': 'Preferences updated successfully',
            'preferences': preferences
        })
        
    except Exception as e:
        logger.error(f"Error updating timeline preferences: {e}")
        return JsonResponse({
            'success': False,
            'error': 'Unable to update preferences'
        }, status=500)


@login_required
def get_timeline_preferences(request: HttpRequest) -> JsonResponse:
    """
    Get user's timeline display preferences.
    
    Args:
        request: HTTP request
        
    Returns:
        JSON response with user preferences
    """
    try:
        # Get preferences from session
        preferences = request.session.get('timeline_preferences', {
            'default_page_size': 20,
            'default_date_range': 30,
            'show_document_previews': True,
            'auto_refresh_interval': 0  # 0 = disabled
        })
        
        return JsonResponse({
            'success': True,
            'preferences': preferences
        })
        
    except Exception as e:
        logger.error(f"Error getting timeline preferences: {e}")
        return JsonResponse({
            'success': False,
            'error': 'Unable to load preferences'
        }, status=500)


# API Functions for timeline views
@api_view(['GET'])
@permission_classes([IsAuthenticated, ClinicalRecordPermission])
@audit_clinical_action('TIMELINE_API_ACCESSED')
def patient_timeline_api(request: HttpRequest, patient_id: str) -> Response:
    """
    API endpoint for patient timeline data.
    
    Args:
        request: HTTP request
        patient_id: ID of the patient
        
    Returns:
        JSON response with timeline data
    """
    try:
        # Get patient
        patient = get_object_or_404(Patient, id=patient_id)
        
        # Get query parameters
        page = int(request.GET.get('page', 1))
        page_size = int(request.GET.get('page_size', 20))
        filters = request.GET.dict()
        
        # Remove pagination parameters from filters
        filters.pop('page', None)
        filters.pop('page_size', None)
        
        # Get timeline data
        timeline_data = timeline_service.get_patient_timeline(
            patient=patient,
            user=request.user,
            filters=filters,
            page=page,
            page_size=page_size
        )
        
        return Response(timeline_data)
        
    except Exception as e:
        logger.error(f"Error in patient_timeline_api: {e}")
        return Response({
            'error': 'Unable to load timeline data'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['GET'])
@permission_classes([IsAuthenticated, ClinicalRecordPermission])
@audit_clinical_action('TIMELINE_ENTRY_DETAILS_ACCESSED')
def timeline_entry_details_api(request: HttpRequest, patient_id: str, record_id: str) -> Response:
    """
    API endpoint for timeline entry details.
    
    Args:
        request: HTTP request
        patient_id: ID of the patient
        record_id: ID of the clinical record
        
    Returns:
        JSON response with entry details
    """
    try:
        # Get patient and record
        patient = get_object_or_404(Patient, id=patient_id)
        from ..models import ClinicalRecord
        record = get_object_or_404(ClinicalRecord, id=record_id, patient=patient)
        
        # Get entry details
        entry_details = timeline_service.get_timeline_entry_details(
            record=record,
            user=request.user
        )
        
        return Response(entry_details)
        
    except Exception as e:
        logger.error(f"Error in timeline_entry_details_api: {e}")
        return Response({
            'error': 'Unable to load entry details'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['GET'])
@permission_classes([IsAuthenticated, ClinicalRecordPermission])
def timeline_filters_api(request: HttpRequest, patient_id: str) -> Response:
    """
    API endpoint for timeline filters.
    
    Args:
        request: HTTP request
        patient_id: ID of the patient
        
    Returns:
        JSON response with available filters
    """
    try:
        # Get patient
        patient = get_object_or_404(Patient, id=patient_id)
        
        # Get available filters
        filters = timeline_service.get_available_filters(
            patient=patient,
            user=request.user
        )
        
        return Response(filters)
        
    except Exception as e:
        logger.error(f"Error in timeline_filters_api: {e}")
        return Response({
            'error': 'Unable to load filters'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['GET'])
@permission_classes([IsAuthenticated, ClinicalRecordPermission])
def timeline_search_api(request: HttpRequest, patient_id: str) -> Response:
    """
    API endpoint for timeline search.
    
    Args:
        request: HTTP request
        patient_id: ID of the patient
        
    Returns:
        JSON response with search results
    """
    try:
        # Get patient
        patient = get_object_or_404(Patient, id=patient_id)
        
        # Get search parameters
        query = request.GET.get('q', '')
        page = int(request.GET.get('page', 1))
        page_size = int(request.GET.get('page_size', 20))
        
        # Perform search
        search_results = timeline_service.search_timeline(
            patient=patient,
            user=request.user,
            query=query,
            page=page,
            page_size=page_size
        )
        
        return Response(search_results)
        
    except Exception as e:
        logger.error(f"Error in timeline_search_api: {e}")
        return Response({
            'error': 'Unable to perform search'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['GET'])
@permission_classes([IsAuthenticated, ClinicalRecordPermission])
def timeline_load_more(request: HttpRequest, patient_id: str) -> Response:
    """
    API endpoint for loading more timeline entries.
    
    Args:
        request: HTTP request
        patient_id: ID of the patient
        
    Returns:
        JSON response with additional entries
    """
    try:
        # Get patient
        patient = get_object_or_404(Patient, id=patient_id)
        
        # Get parameters
        page = int(request.GET.get('page', 1))
        page_size = int(request.GET.get('page_size', 20))
        filters = request.GET.dict()
        
        # Remove pagination parameters from filters
        filters.pop('page', None)
        filters.pop('page_size', None)
        
        # Get additional entries
        additional_entries = timeline_service.get_patient_timeline(
            patient=patient,
            user=request.user,
            filters=filters,
            page=page,
            page_size=page_size
        )
        
        return Response(additional_entries)
        
    except Exception as e:
        logger.error(f"Error in timeline_load_more: {e}")
        return Response({
            'error': 'Unable to load more entries'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['GET'])
@permission_classes([IsAuthenticated, ClinicalRecordPermission])
def timeline_quick_search(request: HttpRequest, patient_id: str) -> Response:
    """
    API endpoint for quick timeline search.
    
    Args:
        request: HTTP request
        patient_id: ID of the patient
        
    Returns:
        JSON response with quick search results
    """
    try:
        # Get patient
        patient = get_object_or_404(Patient, id=patient_id)
        
        # Get search query
        query = request.GET.get('q', '')
        
        # Perform quick search
        quick_results = timeline_service.quick_search_timeline(
            patient=patient,
            user=request.user,
            query=query
        )
        
        return Response(quick_results)
        
    except Exception as e:
        logger.error(f"Error in timeline_quick_search: {e}")
        return Response({
            'error': 'Unable to perform quick search'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['GET'])
@permission_classes([IsAuthenticated, ClinicalRecordPermission])
def document_preview(request: HttpRequest, patient_id: str, document_id: str) -> Response:
    """
    API endpoint for document preview in timeline.
    
    Args:
        request: HTTP request
        patient_id: ID of the patient
        document_id: ID of the document
        
    Returns:
        JSON response with document preview data
    """
    try:
        # Get patient and document
        patient = get_object_or_404(Patient, id=patient_id)
        from ..models import ClinicalDocument
        document = get_object_or_404(ClinicalDocument, id=document_id)
        
        # Get document preview
        preview_data = timeline_service.get_document_preview(
            document=document,
            user=request.user
        )
        
        return Response(preview_data)
        
    except Exception as e:
        logger.error(f"Error in document_preview: {e}")
        return Response({
            'error': 'Unable to load document preview'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class TimelineEntryDetailView(View):
    """
    View for displaying timeline entry details.
    """
    
    @method_decorator(login_required)
    @method_decorator(audit_clinical_action('TIMELINE_ENTRY_DETAILS_PAGE_ACCESSED'))
    def get(self, request: HttpRequest, patient_id: str, record_id: str) -> HttpResponse:
        """
        Display timeline entry details page.
        
        Args:
            request: HTTP request
            patient_id: ID of the patient
            record_id: ID of the clinical record
            
        Returns:
            Rendered details template
        """
        try:
            # Get patient and record
            patient = get_object_or_404(Patient, id=patient_id)
            from ..models import ClinicalRecord
            record = get_object_or_404(ClinicalRecord, id=record_id, patient=patient)
            
            # Check access
            if not timeline_service._check_patient_access(request.user, patient):
                raise PermissionDenied("You do not have access to this patient's records")
            
            # Get entry details
            entry_details = timeline_service.get_timeline_entry_details(
                record=record,
                user=request.user
            )
            
            # Prepare context
            context = {
                'patient': patient,
                'record': record,
                'entry_details': entry_details,
                'page_title': f"Record Details - {patient.get_full_name()}"
            }
            
            return render(request, 'clinical_records/timeline_entry_detail.html', context)
            
        except PermissionDenied:
            raise
        except Exception as e:
            logger.error(f"Error displaying timeline entry details: {e}")
            return render(request, 'clinical_records/error.html', {
                'error_message': 'Unable to load record details',
                'error_details': str(e)
            }, status=500)