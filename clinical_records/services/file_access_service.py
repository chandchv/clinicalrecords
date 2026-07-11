"""
File Access Service for Clinical Records

This service provides secure file access with abstraction for local storage
and future S3 integration. It handles permissions, audit logging, and
secure URL generation.
"""
import os
import logging
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, Union
from django.conf import settings
from django.core.exceptions import PermissionDenied
from django.http import HttpResponse, FileResponse
from django.utils import timezone
# from users.models import AuditLog  # External dependency removed

logger = logging.getLogger(__name__)


class FileAccessService:
    """
    Service for secure file access with abstraction for different storage backends.
    
    This service provides a unified interface for accessing clinical document files
    whether they are stored locally or in cloud storage (S3). It handles:
    - Access control and permissions
    - Audit logging
    - Secure URL generation
    - File serving with proper headers
    """
    
    def __init__(self):
        self.storage_backend = getattr(settings, 'CLINICAL_DOCUMENTS_STORAGE', 'local')
        self.use_s3 = self.storage_backend == 's3'
        
    def get_secure_file_response(self, document, user, action='download'):
        """
        Get a secure file response for the given document.
        
        Args:
            document: ClinicalDocument instance
            user: User requesting access
            action: Type of access ('download', 'preview', 'thumbnail')
            
        Returns:
            HttpResponse or FileResponse for the file
            
        Raises:
            PermissionDenied: If user doesn't have access
            FileNotFoundError: If file doesn't exist
        """
        # Check permissions
        if not self._check_access_permission(user, document, action):
            raise PermissionDenied(f"Access denied for {action} on document {document.id}")
        
        # Log the access
        self._log_file_access(user, document, action)
        
        if self.use_s3:
            return self._get_s3_file_response(document, action)
        else:
            return self._get_local_file_response(document, action)
    
    def get_secure_url(self, document, user, action='download', expires_in=3600):
        """
        Generate a secure URL for accessing a document.
        
        Args:
            document: ClinicalDocument instance
            user: User requesting access
            action: Type of access ('download', 'preview', 'thumbnail')
            expires_in: URL expiration time in seconds
            
        Returns:
            Secure URL string
            
        Raises:
            PermissionDenied: If user doesn't have access
        """
        # Check permissions
        if not self._check_access_permission(user, document, action):
            raise PermissionDenied(f"Access denied for {action} on document {document.id}")
        
        if self.use_s3:
            return self._generate_s3_presigned_url(document, action, expires_in)
        else:
            return self._generate_local_secure_url(document, action, expires_in)
    
    def check_file_availability(self, document):
        """
        Check if the document file is available and accessible.
        
        Args:
            document: ClinicalDocument instance
            
        Returns:
            Dictionary with availability information
        """
        availability = {
            'original_file': False,
            'preview': False,
            'thumbnail': False,
            'file_size': 0,
            'last_modified': None
        }
        
        if self.use_s3:
            availability.update(self._check_s3_file_availability(document))
        else:
            availability.update(self._check_local_file_availability(document))
        
        return availability
    
    def _get_local_file_response(self, document, action):
        """Get file response for local storage."""
        file_path = self._get_local_file_path(document, action)
        
        if not file_path or not os.path.exists(file_path):
            raise FileNotFoundError(f"File not found for document {document.id}")
        
        # Determine content type and disposition
        if action == 'download':
            content_type = document.content_type or 'application/octet-stream'
            disposition = f'attachment; filename="{document.original_filename}"'
        elif action in ['preview', 'thumbnail']:
            content_type = 'image/jpeg'
            disposition = f'inline; filename="{action}_{document.original_filename}.jpg"'
        else:
            content_type = 'application/octet-stream'
            disposition = f'attachment; filename="{document.original_filename}"'
        
        # Create file response
        response = FileResponse(
            open(file_path, 'rb'),
            content_type=content_type
        )
        
        response['Content-Disposition'] = disposition
        response['Content-Length'] = os.path.getsize(file_path)
        response['X-Document-ID'] = str(document.id)
        response['X-Access-Method'] = 'local'
        
        # Add cache headers for previews and thumbnails
        if action in ['preview', 'thumbnail']:
            response['Cache-Control'] = 'private, max-age=3600'
            response['ETag'] = f'"{document.file_hash}"'
        
        return response
    
    def _get_s3_file_response(self, document, action):
        """Get file response for S3 storage (redirect to presigned URL)."""
        try:
            import boto3
            from botocore.exceptions import ClientError
            
            s3_client = boto3.client('s3')
            
            # Get S3 key for the requested action
            s3_key = self._get_s3_key(document, action)
            bucket = getattr(settings, 'AWS_STORAGE_BUCKET_NAME', 'clinical-documents')
            
            # Generate presigned URL
            presigned_url = s3_client.generate_presigned_url(
                'get_object',
                Params={'Bucket': bucket, 'Key': s3_key},
                ExpiresIn=3600  # 1 hour
            )
            
            # Return redirect response
            response = HttpResponse(status=302)
            response['Location'] = presigned_url
            response['X-Document-ID'] = str(document.id)
            response['X-Access-Method'] = 's3'
            
            return response
            
        except Exception as e:
            logger.error(f"S3 file access failed for document {document.id}: {e}")
            raise FileNotFoundError(f"File access failed for document {document.id}")
    
    def _get_local_file_path(self, document, action):
        """Get local file path for the requested action."""
        if action == 'download':
            return document.file.path if document.file else None
        elif action == 'preview':
            return self._get_preview_path(document)
        elif action == 'thumbnail':
            return self._get_thumbnail_path(document)
        else:
            return document.file.path if document.file else None
    
    def _get_s3_key(self, document, action):
        """Get S3 key for the requested action."""
        if action == 'download':
            return document.s3_key if hasattr(document, 's3_key') else None
        elif action == 'preview':
            return document.preview_s3_key if hasattr(document, 'preview_s3_key') else None
        elif action == 'thumbnail':
            return document.thumbnail_s3_key if hasattr(document, 'thumbnail_s3_key') else None
        else:
            return document.s3_key if hasattr(document, 's3_key') else None
    
    def _check_local_file_availability(self, document):
        """Check availability of local files."""
        availability = {}
        
        # Check original file
        if document.file and os.path.exists(document.file.path):
            availability['original_file'] = True
            availability['file_size'] = os.path.getsize(document.file.path)
            availability['last_modified'] = datetime.fromtimestamp(
                os.path.getmtime(document.file.path)
            )
        
        # Check preview
        preview_path = self._get_preview_path(document)
        availability['preview'] = bool(preview_path and os.path.exists(preview_path))
        
        # Check thumbnail
        thumbnail_path = self._get_thumbnail_path(document)
        availability['thumbnail'] = bool(thumbnail_path and os.path.exists(thumbnail_path))
        
        return availability
    
    def _check_s3_file_availability(self, document):
        """Check availability of S3 files."""
        try:
            import boto3
            from botocore.exceptions import ClientError
            
            s3_client = boto3.client('s3')
            bucket = getattr(settings, 'AWS_STORAGE_BUCKET_NAME', 'clinical-documents')
            availability = {}
            
            # Check original file
            if hasattr(document, 's3_key') and document.s3_key:
                try:
                    response = s3_client.head_object(Bucket=bucket, Key=document.s3_key)
                    availability['original_file'] = True
                    availability['file_size'] = response['ContentLength']
                    availability['last_modified'] = response['LastModified']
                except ClientError:
                    availability['original_file'] = False
            
            # Check preview
            if hasattr(document, 'preview_s3_key') and document.preview_s3_key:
                try:
                    s3_client.head_object(Bucket=bucket, Key=document.preview_s3_key)
                    availability['preview'] = True
                except ClientError:
                    availability['preview'] = False
            
            # Check thumbnail
            if hasattr(document, 'thumbnail_s3_key') and document.thumbnail_s3_key:
                try:
                    s3_client.head_object(Bucket=bucket, Key=document.thumbnail_s3_key)
                    availability['thumbnail'] = True
                except ClientError:
                    availability['thumbnail'] = False
            
            return availability
            
        except Exception as e:
            logger.error(f"S3 availability check failed: {e}")
            return {'original_file': False, 'preview': False, 'thumbnail': False}
    
    def _generate_s3_presigned_url(self, document, action, expires_in):
        """Generate S3 presigned URL."""
        try:
            import boto3
            
            s3_client = boto3.client('s3')
            bucket = getattr(settings, 'AWS_STORAGE_BUCKET_NAME', 'clinical-documents')
            s3_key = self._get_s3_key(document, action)
            
            if not s3_key:
                raise ValueError(f"No S3 key available for {action}")
            
            return s3_client.generate_presigned_url(
                'get_object',
                Params={'Bucket': bucket, 'Key': s3_key},
                ExpiresIn=expires_in
            )
            
        except Exception as e:
            logger.error(f"S3 presigned URL generation failed: {e}")
            raise
    
    def _generate_local_secure_url(self, document, action, expires_in):
        """Generate secure URL for local files (using signed tokens)."""
        # This would implement a token-based system for secure local file access
        # For now, return a basic URL - this should be enhanced with signed tokens
        from django.urls import reverse
        
        if action == 'download':
            return reverse('clinical_records:clinicaldocument-download', kwargs={'pk': document.id})
        elif action == 'preview':
            return reverse('clinical_records:clinicaldocument-preview', kwargs={'pk': document.id})
        elif action == 'thumbnail':
            return reverse('clinical_records:clinicaldocument-thumbnail', kwargs={'pk': document.id})
        else:
            return reverse('clinical_records:clinicaldocument-download', kwargs={'pk': document.id})
    
    def _check_access_permission(self, user, document, action):
        """Check if user has permission to access the document."""
        # Basic tenant check
        if not hasattr(user, 'current_tenant') or user.current_tenant != document.clinical_record.clinic:
            return False
        
        # Check if document is in deleted status
        if document.processing_status == 'deleted':
            return False
        
        # Check confidentiality level
        if document.clinical_record.is_confidential:
            if not user.has_perm('clinical_records.view_confidential_documents'):
                return False
        
        # Action-specific permissions
        if action == 'download':
            if not user.has_perm('clinical_records.download_documents'):
                return False
        
        return True
    
    def _log_file_access(self, user, document, action):
        """Log file access for audit purposes."""
        AuditLog.log_action(
            user=user,
            action=f'CLINICAL_DOCUMENT_{action.upper()}',
            resource_type='CLINICAL_DOCUMENT',
            resource_id=str(document.id),
            details={
                'filename': document.original_filename,
                'file_size': document.file_size,
                'clinical_record_id': str(document.clinical_record.id),
                'access_method': action,
                'storage_backend': self.storage_backend
            },
            tenant=user.current_tenant
        )
    
    def _get_preview_path(self, document):
        """Get the file path for document preview image."""
        if not document.file:
            return None
        
        # Generate preview path based on original file path
        base_path = os.path.splitext(document.file.path)[0]
        preview_path = f"{base_path}_preview.jpg"
        
        if os.path.exists(preview_path):
            return preview_path
        
        # Alternative preview paths for different processing systems
        alt_paths = [
            f"{base_path}_preview.png",
            f"{base_path}.preview.jpg",
            os.path.join(os.path.dirname(document.file.path), 'previews', f"{document.id}_preview.jpg")
        ]
        
        for path in alt_paths:
            if os.path.exists(path):
                return path
        
        return None
    
    def _get_thumbnail_path(self, document):
        """Get the file path for document thumbnail image."""
        if not document.file:
            return None
        
        # Generate thumbnail path based on original file path
        base_path = os.path.splitext(document.file.path)[0]
        thumbnail_path = f"{base_path}_thumb.jpg"
        
        if os.path.exists(thumbnail_path):
            return thumbnail_path
        
        # Alternative thumbnail paths
        alt_paths = [
            f"{base_path}_thumb.png",
            f"{base_path}.thumb.jpg",
            os.path.join(os.path.dirname(document.file.path), 'thumbnails', f"{document.id}_thumb.jpg")
        ]
        
        for path in alt_paths:
            if os.path.exists(path):
                return path
        
        return None


class BatchDownloadService:
    """
    Service for handling batch downloads of clinical documents.
    
    This service creates ZIP archives containing multiple documents
    with proper access control and audit logging.
    """
    
    def __init__(self):
        self.file_access_service = FileAccessService()
        self.max_batch_size = getattr(settings, 'MAX_BATCH_DOWNLOAD_SIZE', 50)
        self.max_zip_size = getattr(settings, 'MAX_ZIP_SIZE_BYTES', 500 * 1024 * 1024)  # 500MB
    
    def create_batch_download(self, document_ids, user, include_metadata=False):
        """
        Create a ZIP archive containing multiple documents.
        
        Args:
            document_ids: List of document IDs to include
            user: User requesting the download
            include_metadata: Whether to include metadata files
            
        Returns:
            Tuple of (zip_file_path, download_info)
        """
        import tempfile
        import zipfile
        from ..models import ClinicalDocument
        
        if len(document_ids) > self.max_batch_size:
            raise ValueError(f"Too many documents requested (maximum {self.max_batch_size})")
        
        # Get accessible documents
        accessible_documents = []
        access_errors = []
        total_size = 0
        
        for doc_id in document_ids:
            try:
                document = ClinicalDocument.objects.get(
                    id=doc_id,
                    clinical_record__clinic=user.current_tenant
                )
                
                if self.file_access_service._check_access_permission(user, document, 'download'):
                    if document.file and os.path.exists(document.file.path):
                        file_size = os.path.getsize(document.file.path)
                        if total_size + file_size > self.max_zip_size:
                            access_errors.append({
                                'document_id': doc_id,
                                'error': 'ZIP size limit would be exceeded'
                            })
                        else:
                            accessible_documents.append(document)
                            total_size += file_size
                    else:
                        access_errors.append({
                            'document_id': doc_id,
                            'error': 'File not found'
                        })
                else:
                    access_errors.append({
                        'document_id': doc_id,
                        'error': 'Access denied'
                    })
                    
            except ClinicalDocument.DoesNotExist:
                access_errors.append({
                    'document_id': doc_id,
                    'error': 'Document not found'
                })
        
        if not accessible_documents:
            raise ValueError("No accessible documents found")
        
        # Create ZIP file
        temp_zip = tempfile.NamedTemporaryFile(delete=False, suffix='.zip')
        
        with zipfile.ZipFile(temp_zip.name, 'w', zipfile.ZIP_DEFLATED) as zip_file:
            for document in accessible_documents:
                try:
                    # Add document file
                    safe_filename = self._get_safe_filename(document.original_filename)
                    zip_file.write(document.file.path, safe_filename)
                    
                    # Add metadata file if requested
                    if include_metadata:
                        metadata_content = self._generate_metadata_content(document)
                        metadata_filename = f"{os.path.splitext(safe_filename)[0]}_metadata.json"
                        zip_file.writestr(metadata_filename, metadata_content)
                    
                    # Log individual document access
                    self.file_access_service._log_file_access(user, document, 'batch_download')
                    
                except Exception as e:
                    logger.error(f"Failed to add document {document.id} to ZIP: {e}")
                    access_errors.append({
                        'document_id': str(document.id),
                        'error': f'Failed to add to archive: {str(e)}'
                    })
        
        # Log batch download
        AuditLog.log_action(
            user=user,
            action='CLINICAL_DOCUMENTS_BATCH_DOWNLOADED',
            resource_type='CLINICAL_DOCUMENT',
            resource_id='batch',
            details={
                'document_count': len(accessible_documents),
                'document_ids': [str(doc.id) for doc in accessible_documents],
                'total_size_bytes': total_size,
                'include_metadata': include_metadata,
                'errors': access_errors
            },
            tenant=user.current_tenant
        )
        
        download_info = {
            'document_count': len(accessible_documents),
            'total_size': total_size,
            'errors': access_errors,
            'zip_filename': f"clinical_documents_{timezone.now().strftime('%Y%m%d_%H%M%S')}.zip"
        }
        
        return temp_zip.name, download_info
    
    def _get_safe_filename(self, filename):
        """Generate a safe filename for ZIP archives."""
        import re
        
        # Remove or replace unsafe characters
        safe_name = re.sub(r'[<>:"/\\|?*]', '_', filename)
        
        # Limit length
        if len(safe_name) > 200:
            name, ext = os.path.splitext(safe_name)
            safe_name = name[:200-len(ext)] + ext
        
        return safe_name
    
    def _generate_metadata_content(self, document):
        """Generate metadata content for a document."""
        import json
        
        metadata = {
            'document_info': {
                'id': str(document.id),
                'filename': document.original_filename,
                'file_size': document.file_size,
                'content_type': document.content_type,
                'document_type': document.get_document_type_display(),
                'file_hash': document.file_hash,
                'created_at': document.created_at.isoformat(),
                'updated_at': document.updated_at.isoformat(),
            },
            'clinical_record': {
                'id': str(document.clinical_record.id),
                'title': document.clinical_record.title,
                'record_type': document.clinical_record.get_record_type_display(),
                'patient_name': document.clinical_record.patient.get_full_name() if document.clinical_record.patient else None,
            },
            'processing_info': {
                'status': document.get_processing_status_display(),
                'ocr_confidence': document.ocr_confidence,
                'has_ocr_text': bool(document.ocr_text),
                'has_structured_data': bool(document.structured_data),
                'has_dicom_metadata': bool(document.dicom_metadata),
            }
        }
        
        return json.dumps(metadata, indent=2)