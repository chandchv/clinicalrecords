"""
Document viewer service for clinical records.

This service handles document viewing, metadata extraction, OCR text overlay,
annotations, and viewer configuration for various document types.
"""

import os
import json
import logging
from typing import Dict, Any, List, Optional, Tuple
from pathlib import Path

from django.conf import settings
from django.core.files.storage import default_storage
from django.utils import timezone
from django.contrib.auth import get_user_model

from users.models import Clinic, Patient
from ..models import ClinicalRecord, ClinicalDocument
from .access_control_service import access_control_service
from .audit_service import audit_service

User = get_user_model()
logger = logging.getLogger(__name__)


class DocumentViewerService:
    """Service for handling document viewing and metadata display."""
    
    def __init__(self):
        self.logger = logging.getLogger(f"{__name__}.{self.__class__.__name__}")
        self.config = getattr(settings, 'CLINICAL_RECORDS_VIEWER', {})
        
        # Viewer configuration
        self.supported_formats = self.config.get('SUPPORTED_FORMATS', {
            'pdf': {'viewer': 'pdf_js', 'annotations': True, 'ocr_overlay': True},
            'image': {'viewer': 'image', 'annotations': True, 'ocr_overlay': True},
            'dicom': {'viewer': 'dicom', 'annotations': True, 'ocr_overlay': False},
            'text': {'viewer': 'text', 'annotations': False, 'ocr_overlay': False}
        })
    
    def get_document_viewer_data(self, document: ClinicalDocument, 
                               user: User, request=None) -> Dict[str, Any]:
        """
        Get comprehensive document viewer data including metadata and viewer config.
        
        Args:
            document: Clinical document to view
            user: User requesting the view
            request: HTTP request object for audit logging
            
        Returns:
            Dict containing viewer data and configuration
        """
        try:
            # Check access permissions
            has_access, access_reason = access_control_service.check_document_access(
                user=user,
                document=document,
                action='view',
                request=request
            )
            
            if not has_access:
                return {
                    'error': f'Access denied: {access_reason}',
                    'has_access': False
                }
            
            # Get document metadata
            metadata = self._extract_document_metadata(document)
            
            # Get viewer configuration
            viewer_config = self._get_viewer_configuration(document)
            
            # Get OCR data if available
            ocr_data = self._get_ocr_data(document) if viewer_config.get('ocr_overlay') else None
            
            # Get annotations if supported
            annotations = self._get_annotations(document) if viewer_config.get('annotations') else []
            
            # Get document content info
            content_info = self._get_content_info(document)
            
            # Log document view
            if request:
                audit_service.log_document_access(
                    document=document,
                    user=user,
                    request=request,
                    access_type='VIEW'
                )
            
            viewer_data = {
                'document_id': str(document.id),
                'filename': document.original_filename,
                'content_type': document.content_type,
                'file_size': document.file_size,
                'has_access': True,
                'metadata': metadata,
                'viewer_config': viewer_config,
                'ocr_data': ocr_data,
                'annotations': annotations,
                'content_info': content_info,
                'download_url': self._get_secure_download_url(document, user),
                'thumbnail_url': self._get_thumbnail_url(document),
                'created_at': document.created_at.isoformat(),
                'updated_at': document.updated_at.isoformat()
            }
            
            return viewer_data
            
        except Exception as e:
            self.logger.error(f"Error getting document viewer data: {e}", exc_info=True)
            return {
                'error': f'Failed to load document: {str(e)}',
                'has_access': False
            }
    
    def _extract_document_metadata(self, document: ClinicalDocument) -> Dict[str, Any]:
        """Extract comprehensive metadata from document."""
        metadata = {
            'basic_info': {
                'filename': document.original_filename,
                'content_type': document.content_type,
                'file_size': document.file_size,
                'file_size_formatted': self._format_file_size(document.file_size),
                'created_at': document.created_at.isoformat(),
                'updated_at': document.updated_at.isoformat(),
                'uploaded_by': document.uploaded_by.get_full_name() if document.uploaded_by else 'System'
            },
            'clinical_info': {
                'record_title': document.clinical_record.title,
                'record_type': document.clinical_record.record_type,
                'patient_name': document.clinical_record.patient.get_full_name(),
                'clinic_name': document.clinical_record.clinic.name,
                'record_date': document.clinical_record.created_at.isoformat()
            },
            'processing_info': {
                'processing_status': document.processing_status,
                'processing_completed_at': document.processing_completed_at.isoformat() if document.processing_completed_at else None,
                'ocr_confidence': document.ocr_confidence,
                'requires_manual_review': document.requires_manual_review,
                'manual_review_reason': document.manual_review_reason
            }
        }
        
        # Add DICOM metadata if available
        if document.dicom_metadata:
            metadata['dicom_info'] = self._format_dicom_metadata(document.dicom_metadata)
        
        # Add structured data if available
        if document.structured_data:
            metadata['structured_data'] = self._format_structured_data(document.structured_data)
        
        # Add upload metadata if available
        if document.upload_metadata:
            metadata['upload_info'] = document.upload_metadata
        
        return metadata
    
    def _get_viewer_configuration(self, document: ClinicalDocument) -> Dict[str, Any]:
        """Get viewer configuration based on document type."""
        file_ext = Path(document.original_filename).suffix.lower()
        content_type = document.content_type.lower()
        
        # Determine document format
        if content_type == 'application/pdf' or file_ext == '.pdf':
            format_key = 'pdf'
        elif content_type.startswith('image/') or file_ext in ['.jpg', '.jpeg', '.png', '.tiff', '.tif']:
            format_key = 'image'
        elif content_type == 'application/dicom' or file_ext in ['.dcm', '.dicom']:
            format_key = 'dicom'
        elif content_type.startswith('text/') or file_ext in ['.txt', '.rtf']:
            format_key = 'text'
        else:
            format_key = 'pdf'  # Default fallback
        
        base_config = self.supported_formats.get(format_key, self.supported_formats['pdf'])
        
        # Enhance configuration with document-specific settings
        config = {
            'format': format_key,
            'viewer_type': base_config['viewer'],
            'supports_annotations': base_config.get('annotations', False),
            'supports_ocr_overlay': base_config.get('ocr_overlay', False),
            'supports_zoom': True,
            'supports_rotation': format_key in ['pdf', 'image'],
            'supports_fullscreen': True,
            'default_zoom': 'fit_width',
            'toolbar_enabled': True,
            'sidebar_enabled': True,
            'search_enabled': bool(document.ocr_text),
            'download_enabled': True,
            'print_enabled': True
        }
        
        # Add format-specific configuration
        if format_key == 'pdf':
            config.update({
                'pdf_js_config': {
                    'worker_src': '/static/clinical_records/js/pdf.worker.min.js',
                    'cmap_url': '/static/clinical_records/cmaps/',
                    'cmap_packed': True,
                    'enable_xfa': True
                }
            })
        elif format_key == 'dicom':
            config.update({
                'dicom_config': {
                    'window_width': 400,
                    'window_center': 40,
                    'invert': False,
                    'interpolate': True
                }
            })
        
        return config
    
    def _get_ocr_data(self, document: ClinicalDocument) -> Optional[Dict[str, Any]]:
        """Get OCR data for text overlay."""
        if not document.ocr_text:
            return None
        
        ocr_data = {
            'text': document.ocr_text,
            'confidence': document.ocr_confidence,
            'has_structured_data': bool(document.structured_data),
            'word_level_data': None,  # Could be enhanced with word-level OCR data
            'text_regions': None      # Could be enhanced with text region coordinates
        }
        
        # Add structured data highlights if available
        if document.structured_data:
            ocr_data['highlights'] = self._generate_text_highlights(
                document.ocr_text, 
                document.structured_data
            )
        
        return ocr_data
    
    def _get_annotations(self, document: ClinicalDocument) -> List[Dict[str, Any]]:
        """Get document annotations (placeholder for future implementation)."""
        # This would integrate with an annotation system
        # For now, return empty list
        return []
    
    def _get_content_info(self, document: ClinicalDocument) -> Dict[str, Any]:
        """Get document content information."""
        content_info = {
            'has_file': bool(document.file),
            'file_exists': False,
            'file_path': None,
            'page_count': None,
            'dimensions': None
        }
        
        if document.file:
            try:
                content_info['file_exists'] = default_storage.exists(document.file.name)
                content_info['file_path'] = document.file.name
                
                # Add format-specific content info
                if document.content_type == 'application/pdf':
                    content_info.update(self._get_pdf_info(document))
                elif document.content_type.startswith('image/'):
                    content_info.update(self._get_image_info(document))
                elif document.dicom_metadata:
                    content_info.update(self._get_dicom_info(document))
                    
            except Exception as e:
                self.logger.warning(f"Error getting content info for document {document.id}: {e}")
        
        return content_info
    
    def _get_secure_download_url(self, document: ClinicalDocument, user: User) -> str:
        """Generate secure download URL for document."""
        # This would integrate with the file access service
        return f"/api/clinical-records/documents/{document.id}/download/"
    
    def _get_thumbnail_url(self, document: ClinicalDocument) -> Optional[str]:
        """Get thumbnail URL if available."""
        # This would integrate with thumbnail generation service
        if document.content_type.startswith('image/'):
            return f"/api/clinical-records/documents/{document.id}/thumbnail/"
        elif document.content_type == 'application/pdf':
            return f"/api/clinical-records/documents/{document.id}/thumbnail/"
        return None
    
    def _format_dicom_metadata(self, dicom_metadata: Dict[str, Any]) -> Dict[str, Any]:
        """Format DICOM metadata for display."""
        formatted = {}
        
        # Patient information
        if 'patient_info' in dicom_metadata:
            patient_info = dicom_metadata['patient_info']
            formatted['patient'] = {
                'name': patient_info.get('patient_name', 'Unknown'),
                'id': patient_info.get('patient_id', 'Unknown'),
                'birth_date': patient_info.get('patient_birth_date', 'Unknown'),
                'sex': patient_info.get('patient_sex', 'Unknown'),
                'age': patient_info.get('patient_age', 'Unknown')
            }
        
        # Study information
        if 'study_info' in dicom_metadata:
            study_info = dicom_metadata['study_info']
            formatted['study'] = {
                'date': study_info.get('study_date', 'Unknown'),
                'time': study_info.get('study_time', 'Unknown'),
                'description': study_info.get('study_description', 'Unknown'),
                'instance_uid': study_info.get('study_instance_uid', 'Unknown')
            }
        
        # Series information
        if 'series_info' in dicom_metadata:
            series_info = dicom_metadata['series_info']
            formatted['series'] = {
                'number': series_info.get('series_number', 'Unknown'),
                'description': series_info.get('series_description', 'Unknown'),
                'modality': series_info.get('modality', 'Unknown'),
                'body_part': series_info.get('body_part_examined', 'Unknown')
            }
        
        # Image information
        if 'image_info' in dicom_metadata:
            image_info = dicom_metadata['image_info']
            formatted['image'] = {
                'rows': image_info.get('rows', 'Unknown'),
                'columns': image_info.get('columns', 'Unknown'),
                'pixel_spacing': image_info.get('pixel_spacing', 'Unknown'),
                'slice_thickness': image_info.get('slice_thickness', 'Unknown')
            }
        
        return formatted
    
    def _format_structured_data(self, structured_data: Dict[str, Any]) -> Dict[str, Any]:
        """Format structured data for display."""
        formatted = {}
        
        # Lab results
        if 'lab_results' in structured_data:
            lab_results = structured_data['lab_results']
            formatted['lab_results'] = {
                'tests': lab_results.get('tests', []),
                'lab_name': lab_results.get('lab_info', {}).get('name', 'Unknown'),
                'report_date': lab_results.get('report_date', 'Unknown'),
                'patient_info': lab_results.get('patient_info', {})
            }
        
        # Prescription data
        if 'prescription' in structured_data:
            prescription = structured_data['prescription']
            formatted['prescription'] = {
                'medications': prescription.get('medications', []),
                'doctor_info': prescription.get('doctor_info', {}),
                'patient_info': prescription.get('patient_info', {}),
                'prescription_date': prescription.get('date', 'Unknown')
            }
        
        # General extracted data
        if 'extracted_text' in structured_data:
            formatted['extracted_text'] = structured_data['extracted_text']
        
        return formatted
    
    def _generate_text_highlights(self, ocr_text: str, 
                                structured_data: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Generate text highlights based on structured data."""
        highlights = []
        
        # Highlight lab test names and values
        if 'lab_results' in structured_data:
            tests = structured_data['lab_results'].get('tests', [])
            for test in tests:
                test_name = test.get('name', '')
                test_value = test.get('value', '')
                
                if test_name and test_name in ocr_text:
                    highlights.append({
                        'text': test_name,
                        'type': 'test_name',
                        'color': '#007bff',
                        'tooltip': f"Test: {test_name}"
                    })
                
                if test_value and str(test_value) in ocr_text:
                    highlights.append({
                        'text': str(test_value),
                        'type': 'test_value',
                        'color': '#28a745',
                        'tooltip': f"Value: {test_value}"
                    })
        
        # Highlight medication names
        if 'prescription' in structured_data:
            medications = structured_data['prescription'].get('medications', [])
            for medication in medications:
                med_name = medication.get('name', '')
                if med_name and med_name in ocr_text:
                    highlights.append({
                        'text': med_name,
                        'type': 'medication',
                        'color': '#dc3545',
                        'tooltip': f"Medication: {med_name}"
                    })
        
        return highlights
    
    def _get_pdf_info(self, document: ClinicalDocument) -> Dict[str, Any]:
        """Get PDF-specific information."""
        # This would use a PDF library to extract info
        return {
            'page_count': 1,  # Placeholder
            'pdf_version': 'Unknown',
            'encrypted': False,
            'has_forms': False
        }
    
    def _get_image_info(self, document: ClinicalDocument) -> Dict[str, Any]:
        """Get image-specific information."""
        # This would use PIL or similar to extract info
        return {
            'dimensions': {'width': 'Unknown', 'height': 'Unknown'},
            'color_mode': 'Unknown',
            'dpi': 'Unknown',
            'has_exif': False
        }
    
    def _get_dicom_info(self, document: ClinicalDocument) -> Dict[str, Any]:
        """Get DICOM-specific information."""
        if not document.dicom_metadata:
            return {}
        
        image_info = document.dicom_metadata.get('image_info', {})
        return {
            'dimensions': {
                'width': image_info.get('columns', 'Unknown'),
                'height': image_info.get('rows', 'Unknown')
            },
            'pixel_spacing': image_info.get('pixel_spacing', 'Unknown'),
            'slice_thickness': image_info.get('slice_thickness', 'Unknown'),
            'modality': document.dicom_metadata.get('series_info', {}).get('modality', 'Unknown')
        }
    
    def _format_file_size(self, size_bytes: int) -> str:
        """Format file size in human-readable format."""
        if size_bytes == 0:
            return "0 B"
        
        size_names = ["B", "KB", "MB", "GB", "TB"]
        import math
        i = int(math.floor(math.log(size_bytes, 1024)))
        p = math.pow(1024, i)
        s = round(size_bytes / p, 2)
        return f"{s} {size_names[i]}"
    
    def save_annotation(self, document: ClinicalDocument, user: User,
                       annotation_data: Dict[str, Any]) -> Dict[str, Any]:
        """Save document annotation (placeholder for future implementation)."""
        # This would integrate with an annotation storage system
        return {
            'success': False,
            'message': 'Annotations not yet implemented'
        }
    
    def get_document_search_results(self, document: ClinicalDocument, 
                                  search_query: str) -> List[Dict[str, Any]]:
        """Search within document OCR text."""
        if not document.ocr_text or not search_query:
            return []
        
        results = []
        text = document.ocr_text.lower()
        query = search_query.lower()
        
        # Simple text search (could be enhanced with fuzzy matching)
        start = 0
        while True:
            pos = text.find(query, start)
            if pos == -1:
                break
            
            # Get context around the match
            context_start = max(0, pos - 50)
            context_end = min(len(text), pos + len(query) + 50)
            context = document.ocr_text[context_start:context_end]
            
            results.append({
                'position': pos,
                'context': context,
                'highlight_start': pos - context_start,
                'highlight_end': pos - context_start + len(query)
            })
            
            start = pos + 1
        
        return results


# Global document viewer service instance
document_viewer_service = DocumentViewerService()