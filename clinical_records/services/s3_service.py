"""
S3 service for clinical records management.
Provides high-level operations for clinical document storage and retrieval.
"""

import logging
import hashlib
import mimetypes
from datetime import datetime, timedelta
from django.conf import settings
from django.core.files.base import ContentFile
from django.utils import timezone
from clinical_records.storage.s3_storage import clinical_records_storage, S3StorageManager
from clinical_records.models import ClinicalDocument, ClinicalRecord
from users.models import Clinic

logger = logging.getLogger(__name__)


class ClinicalRecordsS3Service:
    """
    High-level service for S3 operations with clinical records.
    """
    
    def __init__(self, storage=None):
        self.storage = storage or clinical_records_storage
        self.storage_manager = S3StorageManager(self.storage)

    def upload_clinical_document(self, clinical_record, file_obj, file_name=None, metadata=None):
        """
        Upload clinical document to S3 with proper organization and metadata.
        
        Args:
            clinical_record: ClinicalRecord instance
            file_obj: File object to upload
            file_name: Optional file name override
            metadata: Additional metadata dictionary
            
        Returns:
            dict: Upload result with S3 key, size, hash, etc.
        """
        try:
            # Generate file name if not provided
            if not file_name:
                file_name = getattr(file_obj, 'name', f'document_{timezone.now().strftime("%Y%m%d_%H%M%S")}')
            
            # Generate tenant-aware S3 key
            tenant_id = str(clinical_record.clinic.id)
            record_type = clinical_record.record_type
            patient_id = str(clinical_record.patient.id)
            
            s3_key = f"tenants/{tenant_id}/{record_type}/{patient_id}/{file_name}"
            
            # Prepare file content
            file_obj.seek(0)
            content = ContentFile(file_obj.read())
            content.name = file_name
            content.tenant_id = tenant_id
            
            # Calculate file hash
            file_obj.seek(0)
            file_hash = hashlib.sha256(file_obj.read()).hexdigest()
            file_obj.seek(0)
            
            # Get file metadata
            file_size = file_obj.size if hasattr(file_obj, 'size') else len(file_obj.read())
            file_obj.seek(0)
            
            content_type = mimetypes.guess_type(file_name)[0] or 'application/octet-stream'
            
            # Upload to S3
            saved_key = self.storage._save(s3_key, content)
            
            # Prepare result
            result = {
                's3_key': saved_key,
                's3_bucket': self.storage.bucket_name,
                'file_name': file_name,
                'file_size': file_size,
                'file_hash': file_hash,
                'content_type': content_type,
                'upload_timestamp': timezone.now(),
                'tenant_id': tenant_id
            }
            
            # Add custom metadata if provided
            if metadata:
                result['custom_metadata'] = metadata
            
            logger.info(f"Successfully uploaded clinical document to S3: {saved_key}")
            return result
            
        except Exception as e:
            logger.error(f"Failed to upload clinical document to S3: {e}")
            raise

    def download_clinical_document(self, s3_key, expire_in=3600):
        """
        Generate secure download URL for clinical document.
        
        Args:
            s3_key: S3 object key
            expire_in: URL expiration time in seconds
            
        Returns:
            str: Presigned download URL
        """
        try:
            url = self.storage.url(s3_key, expire=expire_in)
            
            logger.info(f"Generated download URL for clinical document: {s3_key}")
            return url
            
        except Exception as e:
            logger.error(f"Failed to generate download URL for {s3_key}: {e}")
            raise

    def get_document_content(self, s3_key):
        """
        Retrieve document content from S3.
        
        Args:
            s3_key: S3 object key
            
        Returns:
            ContentFile: File content
        """
        try:
            content = self.storage._open(s3_key)
            
            logger.info(f"Retrieved document content from S3: {s3_key}")
            return content
            
        except Exception as e:
            logger.error(f"Failed to retrieve document content from {s3_key}: {e}")
            raise

    def delete_clinical_document(self, s3_key):
        """
        Delete clinical document from S3.
        
        Args:
            s3_key: S3 object key
            
        Returns:
            bool: Success status
        """
        try:
            self.storage.delete(s3_key)
            
            logger.info(f"Successfully deleted clinical document from S3: {s3_key}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to delete clinical document from S3: {e}")
            raise

    def copy_clinical_document(self, source_s3_key, dest_clinical_record, new_file_name=None):
        """
        Copy clinical document to new location in S3.
        
        Args:
            source_s3_key: Source S3 object key
            dest_clinical_record: Destination ClinicalRecord instance
            new_file_name: Optional new file name
            
        Returns:
            str: New S3 key
        """
        try:
            # Generate destination key
            tenant_id = str(dest_clinical_record.clinic.id)
            record_type = dest_clinical_record.record_type
            patient_id = str(dest_clinical_record.patient.id)
            
            if not new_file_name:
                # Extract original file name
                new_file_name = source_s3_key.split('/')[-1]
            
            dest_s3_key = f"tenants/{tenant_id}/{record_type}/{patient_id}/{new_file_name}"
            
            # Copy file in S3
            copied_key = self.storage.copy_file(source_s3_key, dest_s3_key, tenant_id)
            
            logger.info(f"Successfully copied clinical document in S3: {source_s3_key} -> {copied_key}")
            return copied_key
            
        except Exception as e:
            logger.error(f"Failed to copy clinical document in S3: {e}")
            raise

    def move_clinical_document(self, source_s3_key, dest_clinical_record, new_file_name=None):
        """
        Move clinical document to new location in S3.
        
        Args:
            source_s3_key: Source S3 object key
            dest_clinical_record: Destination ClinicalRecord instance
            new_file_name: Optional new file name
            
        Returns:
            str: New S3 key
        """
        try:
            # Generate destination key
            tenant_id = str(dest_clinical_record.clinic.id)
            record_type = dest_clinical_record.record_type
            patient_id = str(dest_clinical_record.patient.id)
            
            if not new_file_name:
                # Extract original file name
                new_file_name = source_s3_key.split('/')[-1]
            
            dest_s3_key = f"tenants/{tenant_id}/{record_type}/{patient_id}/{new_file_name}"
            
            # Move file in S3
            moved_key = self.storage.move_file(source_s3_key, dest_s3_key, tenant_id)
            
            logger.info(f"Successfully moved clinical document in S3: {source_s3_key} -> {moved_key}")
            return moved_key
            
        except Exception as e:
            logger.error(f"Failed to move clinical document in S3: {e}")
            raise

    def get_document_metadata(self, s3_key):
        """
        Get comprehensive metadata for clinical document.
        
        Args:
            s3_key: S3 object key
            
        Returns:
            dict: Document metadata
        """
        try:
            metadata = self.storage.get_file_metadata(s3_key)
            
            logger.info(f"Retrieved document metadata from S3: {s3_key}")
            return metadata
            
        except Exception as e:
            logger.error(f"Failed to retrieve document metadata from {s3_key}: {e}")
            raise

    def list_tenant_documents(self, tenant_id, prefix=None, limit=1000):
        """
        List documents for a specific tenant.
        
        Args:
            tenant_id: Tenant/clinic ID
            prefix: Optional prefix filter
            limit: Maximum number of documents to return
            
        Returns:
            list: List of document keys
        """
        try:
            tenant_prefix = f"tenants/{tenant_id}/"
            if prefix:
                tenant_prefix += prefix
            
            # Use S3 list_objects_v2 to get documents
            response = self.storage.s3_client.list_objects_v2(
                Bucket=self.storage.bucket_name,
                Prefix=tenant_prefix,
                MaxKeys=limit
            )
            
            documents = []
            for obj in response.get('Contents', []):
                documents.append({
                    'key': obj['Key'],
                    'size': obj['Size'],
                    'last_modified': obj['LastModified'],
                    'etag': obj['ETag'].strip('"')
                })
            
            logger.info(f"Listed {len(documents)} documents for tenant {tenant_id}")
            return documents
            
        except Exception as e:
            logger.error(f"Failed to list documents for tenant {tenant_id}: {e}")
            raise

    def get_tenant_storage_usage(self, tenant_id):
        """
        Get storage usage statistics for a tenant.
        
        Args:
            tenant_id: Tenant/clinic ID
            
        Returns:
            dict: Storage usage statistics
        """
        try:
            documents = self.list_tenant_documents(tenant_id)
            
            total_size = sum(doc['size'] for doc in documents)
            document_count = len(documents)
            
            # Group by record type
            record_types = {}
            for doc in documents:
                # Extract record type from key path
                key_parts = doc['key'].split('/')
                if len(key_parts) >= 3:
                    record_type = key_parts[2]
                    if record_type not in record_types:
                        record_types[record_type] = {'count': 0, 'size': 0}
                    record_types[record_type]['count'] += 1
                    record_types[record_type]['size'] += doc['size']
            
            usage_stats = {
                'tenant_id': tenant_id,
                'total_documents': document_count,
                'total_size_bytes': total_size,
                'total_size_mb': total_size / (1024 * 1024),
                'total_size_gb': total_size / (1024 * 1024 * 1024),
                'record_types': record_types,
                'calculated_at': timezone.now()
            }
            
            logger.info(f"Calculated storage usage for tenant {tenant_id}: {total_size} bytes")
            return usage_stats
            
        except Exception as e:
            logger.error(f"Failed to calculate storage usage for tenant {tenant_id}: {e}")
            raise

    def create_multipart_upload(self, clinical_record, file_name, file_size):
        """
        Create multipart upload for large clinical documents.
        
        Args:
            clinical_record: ClinicalRecord instance
            file_name: File name
            file_size: Total file size
            
        Returns:
            dict: Multipart upload information
        """
        try:
            # Generate S3 key
            tenant_id = str(clinical_record.clinic.id)
            record_type = clinical_record.record_type
            patient_id = str(clinical_record.patient.id)
            
            s3_key = f"tenants/{tenant_id}/{record_type}/{patient_id}/{file_name}"
            
            # Create multipart upload
            upload_id = self.storage.create_multipart_upload(s3_key, tenant_id)
            
            # Calculate part size and count
            part_size = self.storage.MULTIPART_CHUNKSIZE
            part_count = (file_size + part_size - 1) // part_size
            
            upload_info = {
                'upload_id': upload_id,
                's3_key': s3_key,
                'part_size': part_size,
                'part_count': part_count,
                'file_size': file_size,
                'created_at': timezone.now()
            }
            
            logger.info(f"Created multipart upload for clinical document: {s3_key}")
            return upload_info
            
        except Exception as e:
            logger.error(f"Failed to create multipart upload: {e}")
            raise

    def upload_part(self, upload_info, part_number, part_data):
        """
        Upload part for multipart upload.
        
        Args:
            upload_info: Multipart upload information
            part_number: Part number (1-based)
            part_data: Part data
            
        Returns:
            dict: Part upload result
        """
        try:
            part_result = self.storage.upload_part(
                upload_info['upload_id'],
                part_number,
                upload_info['s3_key'],
                part_data
            )
            
            logger.info(f"Uploaded part {part_number} for {upload_info['s3_key']}")
            return part_result
            
        except Exception as e:
            logger.error(f"Failed to upload part {part_number}: {e}")
            raise

    def complete_multipart_upload(self, upload_info, parts):
        """
        Complete multipart upload.
        
        Args:
            upload_info: Multipart upload information
            parts: List of uploaded parts
            
        Returns:
            dict: Upload completion result
        """
        try:
            result = self.storage.complete_multipart_upload(
                upload_info['upload_id'],
                upload_info['s3_key'],
                parts
            )
            
            logger.info(f"Completed multipart upload for {upload_info['s3_key']}")
            return result
            
        except Exception as e:
            logger.error(f"Failed to complete multipart upload: {e}")
            raise

    def abort_multipart_upload(self, upload_info):
        """
        Abort multipart upload.
        
        Args:
            upload_info: Multipart upload information
        """
        try:
            self.storage.abort_multipart_upload(
                upload_info['upload_id'],
                upload_info['s3_key']
            )
            
            logger.info(f"Aborted multipart upload for {upload_info['s3_key']}")
            
        except Exception as e:
            logger.error(f"Failed to abort multipart upload: {e}")
            raise

    def sync_database_with_s3(self, tenant_id=None, dry_run=False):
        """
        Synchronize database records with S3 objects.
        
        Args:
            tenant_id: Optional tenant ID to sync specific tenant
            dry_run: If True, only report what would be done
            
        Returns:
            dict: Synchronization results
        """
        try:
            sync_results = {
                'database_records': 0,
                's3_objects': 0,
                'missing_in_s3': [],
                'missing_in_database': [],
                'mismatched_metadata': [],
                'actions_taken': []
            }
            
            # Get database records
            documents_query = ClinicalDocument.objects.all()
            if tenant_id:
                documents_query = documents_query.filter(clinical_record__clinic_id=tenant_id)
            
            db_documents = {}
            for doc in documents_query:
                if hasattr(doc, 's3_key') and doc.s3_key:
                    db_documents[doc.s3_key] = doc
            
            sync_results['database_records'] = len(db_documents)
            
            # Get S3 objects
            if tenant_id:
                s3_objects = self.list_tenant_documents(tenant_id)
            else:
                # List all objects (this could be expensive for large buckets)
                response = self.storage.s3_client.list_objects_v2(
                    Bucket=self.storage.bucket_name,
                    Prefix='tenants/'
                )
                s3_objects = []
                for obj in response.get('Contents', []):
                    s3_objects.append({
                        'key': obj['Key'],
                        'size': obj['Size'],
                        'last_modified': obj['LastModified'],
                        'etag': obj['ETag'].strip('"')
                    })
            
            sync_results['s3_objects'] = len(s3_objects)
            
            s3_keys = {obj['key'] for obj in s3_objects}
            
            # Find missing objects
            for s3_key in db_documents:
                if s3_key not in s3_keys:
                    sync_results['missing_in_s3'].append(s3_key)
            
            for s3_obj in s3_objects:
                if s3_obj['key'] not in db_documents:
                    sync_results['missing_in_database'].append(s3_obj['key'])
            
            # Check metadata mismatches
            for s3_obj in s3_objects:
                if s3_obj['key'] in db_documents:
                    db_doc = db_documents[s3_obj['key']]
                    if db_doc.file_size != s3_obj['size']:
                        sync_results['mismatched_metadata'].append({
                            'key': s3_obj['key'],
                            'issue': 'size_mismatch',
                            'db_size': db_doc.file_size,
                            's3_size': s3_obj['size']
                        })
            
            # Take corrective actions if not dry run
            if not dry_run:
                # Update database records with correct S3 metadata
                for mismatch in sync_results['mismatched_metadata']:
                    if mismatch['issue'] == 'size_mismatch':
                        db_doc = db_documents[mismatch['key']]
                        db_doc.file_size = mismatch['s3_size']
                        db_doc.save()
                        sync_results['actions_taken'].append(f"Updated size for {mismatch['key']}")
            
            logger.info(f"S3 synchronization completed for tenant {tenant_id or 'all'}")
            return sync_results
            
        except Exception as e:
            logger.error(f"Failed to synchronize database with S3: {e}")
            raise

    def generate_batch_download_urls(self, s3_keys, expire_in=3600):
        """
        Generate batch download URLs for multiple documents.
        
        Args:
            s3_keys: List of S3 object keys
            expire_in: URL expiration time in seconds
            
        Returns:
            dict: Mapping of S3 keys to download URLs
        """
        try:
            download_urls = {}
            
            for s3_key in s3_keys:
                try:
                    url = self.storage.url(s3_key, expire=expire_in)
                    download_urls[s3_key] = url
                except Exception as e:
                    logger.warning(f"Failed to generate URL for {s3_key}: {e}")
                    download_urls[s3_key] = None
            
            logger.info(f"Generated {len(download_urls)} batch download URLs")
            return download_urls
            
        except Exception as e:
            logger.error(f"Failed to generate batch download URLs: {e}")
            raise


# Global service instance
clinical_s3_service = ClinicalRecordsS3Service()