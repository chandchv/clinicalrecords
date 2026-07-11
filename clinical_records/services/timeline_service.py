"""
Timeline service for clinical records.

This service provides functionality for creating chronological views
of patient clinical records with filtering, sorting, and metadata.
"""

import logging
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, List, Tuple
from django.utils import timezone
from django.db.models import Q, Prefetch
from django.contrib.auth import get_user_model
from django.core.paginator import Paginator

from users.models import Patient, Clinic
from ..models import ClinicalRecord, ClinicalDocument
from .access_control_service import access_control_service
from .audit_service import audit_service

User = get_user_model()
logger = logging.getLogger(__name__)


class TimelineService:
    """Service for managing patient timeline views."""
    
    def __init__(self):
        self.logger = logging.getLogger(f"{__name__}.{self.__class__.__name__}")
    
    def get_patient_timeline(self, patient: Patient, user: User, 
                           filters: Optional[Dict[str, Any]] = None,
                           page: int = 1, page_size: int = 20) -> Dict[str, Any]:
        """
        Get chronological timeline of patient's clinical records.
        
        Args:
            patient: Patient to get timeline for
            user: User requesting the timeline
            filters: Optional filters for records
            page: Page number for pagination
            page_size: Number of items per page
            
        Returns:
            Dict containing timeline data and metadata
        """
        try:
            # Check if user has access to view patient records
            if not self._check_patient_access(user, patient):
                raise PermissionError("User does not have access to this patient's records")
            
            # Build base query
            records_query = ClinicalRecord.objects.filter(
                patient=patient
            ).select_related(
                'patient', 'clinic'
            ).prefetch_related(
                Prefetch(
                    'documents',
                    queryset=ClinicalDocument.objects.select_related().order_by('-created_at')
                )
            )
            
            # Apply filters
            if filters:
                records_query = self._apply_filters(records_query, filters)
            
            # Order by creation date (most recent first)
            records_query = records_query.order_by('-created_at')
            
            # Get total count before pagination
            total_records = records_query.count()
            
            # Apply pagination
            paginator = Paginator(records_query, page_size)
            page_obj = paginator.get_page(page)
            
            # Build timeline items
            timeline_items = []
            for record in page_obj:
                # Check individual record access
                has_access, _ = access_control_service.check_record_access(
                    user=user,
                    record=record,
                    action='view'
                )
                
                if has_access:
                    timeline_item = self._build_timeline_item(record, user)
                    timeline_items.append(timeline_item)
            
            # Build response
            timeline_data = {
                'patient_id': str(patient.id),
                'patient_name': patient.get_full_name(),
                'timeline_items': timeline_items,
                'pagination': {
                    'current_page': page,
                    'total_pages': paginator.num_pages,
                    'total_records': total_records,
                    'page_size': page_size,
                    'has_next': page_obj.has_next(),
                    'has_previous': page_obj.has_previous()
                },
                'filters_applied': filters or {},
                'generated_at': timezone.now().isoformat()
            }
            
            # Log timeline access
            audit_service.log_clinical_action(
                action='TIMELINE_VIEWED',
                user=user,
                resource_type='PATIENT_TIMELINE',
                resource_id=str(patient.id),
                clinic=patient.clinic,
                patient_id=str(patient.id),
                details={
                    'records_returned': len(timeline_items),
                    'page': page,
                    'filters': filters or {}
                }
            )
            
            return timeline_data
            
        except Exception as e:
            self.logger.error(f"Error getting patient timeline: {e}")
            raise
    
    def get_timeline_summary(self, patient: Patient, user: User,
                           date_range_days: int = 30) -> Dict[str, Any]:
        """
        Get summary statistics for patient timeline.
        
        Args:
            patient: Patient to get summary for
            user: User requesting the summary
            date_range_days: Number of days to include in recent activity
            
        Returns:
            Dict containing timeline summary
        """
        try:
            # Check access
            if not self._check_patient_access(user, patient):
                raise PermissionError("User does not have access to this patient's records")
            
            # Calculate date range
            end_date = timezone.now()
            start_date = end_date - timedelta(days=date_range_days)
            
            # Get all accessible records
            all_records = ClinicalRecord.objects.filter(patient=patient)
            recent_records = all_records.filter(created_at__gte=start_date)
            
            # Filter by access permissions
            accessible_records = []
            accessible_recent = []
            
            for record in all_records:
                has_access, _ = access_control_service.check_record_access(
                    user=user,
                    record=record,
                    action='view'
                )
                if has_access:
                    accessible_records.append(record)
                    if record.created_at >= start_date:
                        accessible_recent.append(record)
            
            # Calculate statistics
            record_types = {}
            for record in accessible_records:
                record_type = record.record_type
                if record_type not in record_types:
                    record_types[record_type] = {'total': 0, 'recent': 0}
                record_types[record_type]['total'] += 1
                
                if record in accessible_recent:
                    record_types[record_type]['recent'] += 1
            
            # Get document statistics
            total_documents = 0
            recent_documents = 0
            
            for record in accessible_records:
                doc_count = record.documents.count()
                total_documents += doc_count
                
                if record in accessible_recent:
                    recent_doc_count = record.documents.filter(
                        created_at__gte=start_date
                    ).count()
                    recent_documents += recent_doc_count
            
            # Find first and last record dates
            first_record_date = None
            last_record_date = None
            
            if accessible_records:
                sorted_records = sorted(accessible_records, key=lambda r: r.created_at)
                first_record_date = sorted_records[0].created_at.isoformat()
                last_record_date = sorted_records[-1].created_at.isoformat()
            
            summary = {
                'patient_id': str(patient.id),
                'patient_name': patient.get_full_name(),
                'total_records': len(accessible_records),
                'recent_records': len(accessible_recent),
                'total_documents': total_documents,
                'recent_documents': recent_documents,
                'record_types': record_types,
                'date_range_days': date_range_days,
                'first_record_date': first_record_date,
                'last_record_date': last_record_date,
                'generated_at': timezone.now().isoformat()
            }
            
            return summary
            
        except Exception as e:
            self.logger.error(f"Error getting timeline summary: {e}")
            raise
    
    def search_timeline(self, patient: Patient, user: User, 
                       search_query: str, search_type: str = 'all') -> List[Dict[str, Any]]:
        """
        Search patient timeline records.
        
        Args:
            patient: Patient to search records for
            user: User performing the search
            search_query: Search query string
            search_type: Type of search ('all', 'title', 'description', 'documents')
            
        Returns:
            List of matching timeline items
        """
        try:
            # Check access
            if not self._check_patient_access(user, patient):
                raise PermissionError("User does not have access to this patient's records")
            
            # Build search query
            base_query = ClinicalRecord.objects.filter(patient=patient)
            
            if search_type == 'title':
                search_filter = Q(title__icontains=search_query)
            elif search_type == 'description':
                search_filter = Q(description__icontains=search_query)
            elif search_type == 'documents':
                search_filter = Q(
                    documents__ocr_text__icontains=search_query
                ) | Q(
                    documents__original_filename__icontains=search_query
                )
            else:  # 'all'
                search_filter = (
                    Q(title__icontains=search_query) |
                    Q(description__icontains=search_query) |
                    Q(documents__ocr_text__icontains=search_query) |
                    Q(documents__original_filename__icontains=search_query)
                )
            
            # Apply search filter
            matching_records = base_query.filter(search_filter).distinct().order_by('-created_at')
            
            # Filter by access permissions and build results
            results = []
            for record in matching_records:
                has_access, _ = access_control_service.check_record_access(
                    user=user,
                    record=record,
                    action='view'
                )
                
                if has_access:
                    timeline_item = self._build_timeline_item(record, user)
                    # Add search relevance information
                    timeline_item['search_relevance'] = self._calculate_search_relevance(
                        record, search_query, search_type
                    )
                    results.append(timeline_item)
            
            # Log search activity
            audit_service.log_clinical_action(
                action='TIMELINE_SEARCHED',
                user=user,
                resource_type='PATIENT_TIMELINE',
                resource_id=str(patient.id),
                clinic=patient.clinic,
                patient_id=str(patient.id),
                details={
                    'search_query': search_query[:100],  # Truncate for logging
                    'search_type': search_type,
                    'results_count': len(results)
                }
            )
            
            return results
            
        except Exception as e:
            self.logger.error(f"Error searching timeline: {e}")
            raise
    
    def get_record_details(self, record_id: str, user: User) -> Dict[str, Any]:
        """
        Get detailed information for a specific record.
        
        Args:
            record_id: ID of the clinical record
            user: User requesting the details
            
        Returns:
            Dict containing detailed record information
        """
        try:
            # Get the record
            record = ClinicalRecord.objects.select_related(
                'patient', 'clinic'
            ).prefetch_related(
                'documents', 'relationships_as_source', 'relationships_as_target'
            ).get(id=record_id)
            
            # Check access
            has_access, reason = access_control_service.check_record_access(
                user=user,
                record=record,
                action='view'
            )
            
            if not has_access:
                raise PermissionError(f"Access denied: {reason}")
            
            # Build detailed record information
            record_details = {
                'id': str(record.id),
                'title': record.title,
                'description': record.description,
                'record_type': record.record_type,
                'created_at': record.created_at.isoformat(),
                'updated_at': record.updated_at.isoformat(),
                'patient': {
                    'id': str(record.patient.id),
                    'name': record.patient.get_full_name(),
                    'date_of_birth': record.patient.date_of_birth.isoformat() if record.patient.date_of_birth else None
                },
                'clinic': {
                    'id': str(record.clinic.id),
                    'name': record.clinic.name
                },
                'documents': [],
                'relationships': [],
                'metadata': getattr(record, 'metadata', {})
            }
            
            # Add document information
            for document in record.documents.all():
                has_doc_access, _ = access_control_service.check_document_access(
                    user=user,
                    document=document,
                    action='view'
                )
                
                if has_doc_access:
                    doc_info = {
                        'id': str(document.id),
                        'filename': document.original_filename,
                        'content_type': document.content_type,
                        'file_size': document.file_size,
                        'created_at': document.created_at.isoformat(),
                        'processing_status': document.processing_status,
                        'has_ocr_text': bool(document.ocr_text),
                        'has_structured_data': bool(document.structured_data),
                        'ocr_confidence': document.ocr_confidence
                    }
                    record_details['documents'].append(doc_info)
            
            # Add relationship information
            for relationship in record.relationships_as_source.all():
                rel_info = {
                    'id': str(relationship.id),
                    'relationship_type': relationship.relationship_type,
                    'target_type': relationship.target_content_type.model,
                    'target_id': str(relationship.target_object_id),
                    'created_at': relationship.created_at.isoformat()
                }
                record_details['relationships'].append(rel_info)
            
            # Log detailed view access
            audit_service.log_clinical_action(
                action='RECORD_DETAILS_VIEWED',
                user=user,
                resource_type='CLINICAL_RECORD',
                resource_id=str(record.id),
                clinic=record.clinic,
                patient_id=str(record.patient.id),
                details={
                    'documents_count': len(record_details['documents']),
                    'relationships_count': len(record_details['relationships'])
                }
            )
            
            return record_details
            
        except ClinicalRecord.DoesNotExist:
            raise ValueError(f"Clinical record {record_id} not found")
        except Exception as e:
            self.logger.error(f"Error getting record details: {e}")
            raise
    
    def _check_patient_access(self, user: User, patient: Patient) -> bool:
        """Check if user has access to patient records."""
        try:
            # Check if user is in the same clinic
            if not hasattr(user, 'clinic') or user.clinic != patient.clinic:
                return False
            
            # Get user permissions
            permissions = access_control_service.get_user_permissions_summary(
                user=user,
                clinic=patient.clinic
            )
            
            # Check if user can view all patients
            return permissions.get('permissions', {}).get('can_view_all_patients', False)
            
        except Exception as e:
            self.logger.error(f"Error checking patient access: {e}")
            return False
    
    def _apply_filters(self, query, filters: Dict[str, Any]):
        """Apply filters to the records query."""
        try:
            # Date range filter
            if 'start_date' in filters and filters['start_date']:
                start_date = datetime.fromisoformat(filters['start_date'].replace('Z', '+00:00'))
                query = query.filter(created_at__gte=start_date)
            
            if 'end_date' in filters and filters['end_date']:
                end_date = datetime.fromisoformat(filters['end_date'].replace('Z', '+00:00'))
                query = query.filter(created_at__lte=end_date)
            
            # Record type filter
            if 'record_types' in filters and filters['record_types']:
                if isinstance(filters['record_types'], list):
                    query = query.filter(record_type__in=filters['record_types'])
                else:
                    query = query.filter(record_type=filters['record_types'])
            
            # Has documents filter
            if 'has_documents' in filters and filters['has_documents']:
                query = query.filter(documents__isnull=False).distinct()
            
            # Processing status filter
            if 'processing_status' in filters and filters['processing_status']:
                query = query.filter(
                    documents__processing_status=filters['processing_status']
                ).distinct()
            
            return query
            
        except Exception as e:
            self.logger.error(f"Error applying filters: {e}")
            return query
    
    def _build_timeline_item(self, record: ClinicalRecord, user: User) -> Dict[str, Any]:
        """Build a timeline item from a clinical record."""
        try:
            # Basic record information
            timeline_item = {
                'id': str(record.id),
                'title': record.title,
                'description': record.description,
                'record_type': record.record_type,
                'created_at': record.created_at.isoformat(),
                'updated_at': record.updated_at.isoformat(),
                'documents_count': 0,
                'documents': [],
                'has_unprocessed_documents': False,
                'metadata': getattr(record, 'metadata', {})
            }
            
            # Add document information
            for document in record.documents.all():
                has_doc_access, _ = access_control_service.check_document_access(
                    user=user,
                    document=document,
                    action='view'
                )
                
                if has_doc_access:
                    doc_info = {
                        'id': str(document.id),
                        'filename': document.original_filename,
                        'content_type': document.content_type,
                        'file_size': document.file_size,
                        'processing_status': document.processing_status,
                        'created_at': document.created_at.isoformat()
                    }
                    timeline_item['documents'].append(doc_info)
                    timeline_item['documents_count'] += 1
                    
                    # Check for unprocessed documents
                    if document.processing_status in ['pending', 'processing', 'failed']:
                        timeline_item['has_unprocessed_documents'] = True
            
            return timeline_item
            
        except Exception as e:
            self.logger.error(f"Error building timeline item: {e}")
            return {
                'id': str(record.id),
                'title': record.title,
                'error': 'Error loading record details'
            }
    
    def _calculate_search_relevance(self, record: ClinicalRecord, 
                                  search_query: str, search_type: str) -> float:
        """Calculate search relevance score for a record."""
        try:
            relevance_score = 0.0
            query_lower = search_query.lower()
            
            # Title relevance (highest weight)
            if query_lower in record.title.lower():
                relevance_score += 1.0
                if record.title.lower().startswith(query_lower):
                    relevance_score += 0.5
            
            # Description relevance (medium weight)
            if query_lower in record.description.lower():
                relevance_score += 0.7
            
            # Document relevance (lower weight)
            for document in record.documents.all():
                if document.ocr_text and query_lower in document.ocr_text.lower():
                    relevance_score += 0.3
                if query_lower in document.original_filename.lower():
                    relevance_score += 0.2
            
            # Boost recent records
            days_old = (timezone.now() - record.created_at).days
            if days_old < 30:
                relevance_score += 0.2
            elif days_old < 90:
                relevance_score += 0.1
            
            return min(relevance_score, 5.0)  # Cap at 5.0
            
        except Exception as e:
            self.logger.error(f"Error calculating search relevance: {e}")
            return 0.0


# Global timeline service instance
timeline_service = TimelineService()