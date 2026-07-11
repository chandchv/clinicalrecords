#!/usr/bin/env python3
"""
Management command for migrating clinical documents from local storage to S3.
Handles database updates and file transfers with progress tracking.
"""

import os
import logging
from django.core.management.base import BaseCommand, CommandError
from django.conf import settings
from django.db import transaction
from clinical_records.models import ClinicalDocument
from clinical_records.services.s3_service import ClinicalRecordsS3Service
from clinical_records.storage.s3_storage import clinical_records_storage

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Migrate clinical documents from local storage to S3'

    def add_arguments(self, parser):
        parser.add_argument(
            '--batch-size',
            type=int,
            default=50,
            help='Number of documents to process in each batch'
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Perform dry run without making changes'
        )
        parser.add_argument(
            '--tenant-id',
            type=str,
            help='Migrate documents for specific tenant only'
        )
        parser.add_argument(
            '--document-type',
            type=str,
            help='Migrate specific document type only'
        )
        parser.add_argument(
            '--force',
            action='store_true',
            help='Force migration even if S3 file already exists'
        )
        parser.add_argument(
            '--verify-only',
            action='store_true',
            help='Only verify existing S3 files without migrating'
        )

    def handle(self, *args, **options):
        """Main command execution"""
        try:
            self.batch_size = options['batch_size']
            self.dry_run = options['dry_run']
            self.tenant_id = options.get('tenant_id')
            self.document_type = options.get('document_type')
            self.force = options['force']
            self.verify_only = options['verify_only']
            
            # Initialize S3 service
            self.s3_service = ClinicalRecordsS3Service()
            
            self.stdout.write("Starting clinical documents migration to S3...")
            
            if self.verify_only:
                self.verify_s3_migration()
            else:
                self.migrate_documents()
            
            self.stdout.write(
                self.style.SUCCESS('Migration completed successfully')
            )
            
        except Exception as e:
            logger.error(f"Migration command failed: {e}")
            raise CommandError(f'Migration failed: {e}')

    def get_documents_to_migrate(self):
        """Get documents that need to be migrated"""
        queryset = ClinicalDocument.objects.all()
        
        # Filter by tenant if specified
        if self.tenant_id:
            queryset = queryset.filter(clinical_record__clinic_id=self.tenant_id)
        
        # Filter by document type if specified
        if self.document_type:
            queryset = queryset.filter(clinical_record__record_type=self.document_type)
        
        # Filter documents that don't have S3 keys or need force migration
        if not self.force:
            queryset = queryset.filter(
                models.Q(s3_key__isnull=True) | models.Q(s3_key='')
            )
        
        return queryset.select_related('clinical_record', 'clinical_record__clinic', 'clinical_record__patient')

    def migrate_documents(self):
        """Migrate documents from local storage to S3"""
        documents = self.get_documents_to_migrate()
        total_count = documents.count()
        
        if total_count == 0:
            self.stdout.write("No documents found to migrate")
            return
        
        self.stdout.write(f"Found {total_count} documents to migrate")
        
        migrated_count = 0
        failed_count = 0
        skipped_count = 0
        
        # Process documents in batches
        for i in range(0, total_count, self.batch_size):
            batch = documents[i:i + self.batch_size]
            
            self.stdout.write(f"Processing batch {i//self.batch_size + 1}...")
            
            for document in batch:
                try:
                    result = self.migrate_single_document(document)
                    
                    if result == 'migrated':
                        migrated_count += 1
                    elif result == 'skipped':
                        skipped_count += 1
                    else:
                        failed_count += 1
                        
                except Exception as e:
                    logger.error(f"Failed to migrate document {document.id}: {e}")
                    failed_count += 1
            
            # Progress update
            processed = min(i + self.batch_size, total_count)
            self.stdout.write(f"Progress: {processed}/{total_count} documents processed")
        
        # Final summary
        self.stdout.write(f"\nMigration Summary:")
        self.stdout.write(f"  Total documents: {total_count}")
        self.stdout.write(f"  Migrated: {migrated_count}")
        self.stdout.write(f"  Skipped: {skipped_count}")
        self.stdout.write(f"  Failed: {failed_count}")

    def migrate_single_document(self, document):
        """Migrate a single document to S3"""
        try:
            # Check if document has local file path
            if not hasattr(document, 'file_path') or not document.file_path:
                self.stdout.write(f"Document {document.id} has no local file path, skipping")
                return 'skipped'
            
            # Construct local file path
            local_file_path = os.path.join(settings.MEDIA_ROOT, str(document.file_path))
            
            if not os.path.exists(local_file_path):
                self.stdout.write(f"Local file not found for document {document.id}: {local_file_path}")
                return 'failed'
            
            # Check if S3 file already exists (unless force migration)
            if document.s3_key and not self.force:
                if clinical_records_storage.exists(document.s3_key):
                    self.stdout.write(f"Document {document.id} already exists in S3, skipping")
                    return 'skipped'
            
            if self.dry_run:
                self.stdout.write(f"Would migrate document {document.id}: {local_file_path}")
                return 'migrated'
            
            # Read local file
            with open(local_file_path, 'rb') as local_file:
                # Upload to S3
                result = self.s3_service.upload_clinical_document(
                    document.clinical_record,
                    local_file,
                    document.file_name or os.path.basename(local_file_path)
                )
                
                # Update document record with S3 information
                with transaction.atomic():
                    document.s3_key = result['s3_key']
                    document.s3_bucket = result['s3_bucket']
                    
                    # Update file metadata if different
                    if document.file_size != result['file_size']:
                        document.file_size = result['file_size']
                    
                    if document.file_hash != result['file_hash']:
                        document.file_hash = result['file_hash']
                    
                    document.save()
                
                self.stdout.write(f"✅ Migrated document {document.id} to S3: {result['s3_key']}")
                return 'migrated'
                
        except Exception as e:
            logger.error(f"Failed to migrate document {document.id}: {e}")
            self.stdout.write(f"❌ Failed to migrate document {document.id}: {e}")
            return 'failed'

    def verify_s3_migration(self):
        """Verify existing S3 migration"""
        documents = ClinicalDocument.objects.exclude(
            models.Q(s3_key__isnull=True) | models.Q(s3_key='')
        )
        
        if self.tenant_id:
            documents = documents.filter(clinical_record__clinic_id=self.tenant_id)
        
        if self.document_type:
            documents = documents.filter(clinical_record__record_type=self.document_type)
        
        total_count = documents.count()
        
        if total_count == 0:
            self.stdout.write("No S3 documents found to verify")
            return
        
        self.stdout.write(f"Verifying {total_count} S3 documents...")
        
        verified_count = 0
        missing_count = 0
        metadata_mismatch_count = 0
        
        for document in documents:
            try:
                # Check if S3 file exists
                if not clinical_records_storage.exists(document.s3_key):
                    self.stdout.write(f"❌ S3 file missing for document {document.id}: {document.s3_key}")
                    missing_count += 1
                    continue
                
                # Get S3 metadata
                s3_metadata = clinical_records_storage.get_file_metadata(document.s3_key)
                
                # Verify file size
                if document.file_size != s3_metadata['size']:
                    self.stdout.write(
                        f"⚠️  Size mismatch for document {document.id}: "
                        f"DB={document.file_size}, S3={s3_metadata['size']}"
                    )
                    metadata_mismatch_count += 1
                    
                    if not self.dry_run:
                        # Update database with correct size
                        document.file_size = s3_metadata['size']
                        document.save()
                        self.stdout.write(f"Updated size for document {document.id}")
                
                verified_count += 1
                
            except Exception as e:
                logger.error(f"Failed to verify document {document.id}: {e}")
                self.stdout.write(f"❌ Failed to verify document {document.id}: {e}")
        
        # Verification summary
        self.stdout.write(f"\nVerification Summary:")
        self.stdout.write(f"  Total documents: {total_count}")
        self.stdout.write(f"  Verified: {verified_count}")
        self.stdout.write(f"  Missing in S3: {missing_count}")
        self.stdout.write(f"  Metadata mismatches: {metadata_mismatch_count}")

    def cleanup_local_files(self):
        """Clean up local files after successful migration (optional)"""
        if self.dry_run:
            self.stdout.write("Would clean up local files (dry run)")
            return
        
        # Get documents that have been successfully migrated to S3
        documents = ClinicalDocument.objects.exclude(
            models.Q(s3_key__isnull=True) | models.Q(s3_key='')
        )
        
        if self.tenant_id:
            documents = documents.filter(clinical_record__clinic_id=self.tenant_id)
        
        cleaned_count = 0
        failed_count = 0
        
        for document in documents:
            try:
                # Verify S3 file exists before deleting local file
                if not clinical_records_storage.exists(document.s3_key):
                    self.stdout.write(f"S3 file missing, keeping local file for document {document.id}")
                    continue
                
                # Construct local file path
                if hasattr(document, 'file_path') and document.file_path:
                    local_file_path = os.path.join(settings.MEDIA_ROOT, str(document.file_path))
                    
                    if os.path.exists(local_file_path):
                        os.remove(local_file_path)
                        self.stdout.write(f"Cleaned up local file for document {document.id}")
                        cleaned_count += 1
                
            except Exception as e:
                logger.error(f"Failed to clean up local file for document {document.id}: {e}")
                failed_count += 1
        
        self.stdout.write(f"Cleanup Summary: {cleaned_count} files cleaned, {failed_count} failed")