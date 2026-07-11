#!/usr/bin/env python3
"""
Management command for setting up and managing S3 storage backend.
Handles bucket creation, policy setup, and migration from local storage.
"""

import json
import logging
from django.core.management.base import BaseCommand, CommandError
from django.conf import settings
from clinical_records.storage.s3_storage import S3StorageManager, clinical_records_storage
from clinical_records.config.s3_config import get_s3_config
from botocore.exceptions import ClientError, NoCredentialsError

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Set up and manage S3 storage backend for clinical records'

    def add_arguments(self, parser):
        parser.add_argument(
            'action',
            type=str,
            choices=[
                'setup',
                'validate',
                'migrate',
                'test',
                'policy',
                'lifecycle',
                'metrics',
                'cleanup'
            ],
            help='Action to perform'
        )
        parser.add_argument(
            '--bucket-name',
            type=str,
            help='S3 bucket name (overrides configuration)'
        )
        parser.add_argument(
            '--source-path',
            type=str,
            help='Source path for migration (local media root)'
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Perform dry run without making changes'
        )
        parser.add_argument(
            '--force',
            action='store_true',
            help='Force operation even if bucket exists'
        )
        parser.add_argument(
            '--batch-size',
            type=int,
            default=100,
            help='Batch size for migration operations'
        )

    def handle(self, *args, **options):
        """Main command execution"""
        try:
            self.action = options['action']
            self.bucket_name = options.get('bucket_name')
            self.source_path = options.get('source_path')
            self.dry_run = options['dry_run']
            self.force = options['force']
            self.batch_size = options['batch_size']
            
            # Get S3 configuration
            self.s3_config = get_s3_config()
            
            # Override bucket name if provided
            if self.bucket_name:
                self.s3_config.BUCKET_NAME = self.bucket_name
            
            # Initialize storage manager
            self.storage_manager = S3StorageManager()
            
            self.stdout.write(f"Starting S3 storage action: {self.action}")
            
            # Execute action
            if self.action == 'setup':
                self.setup_s3_bucket()
            elif self.action == 'validate':
                self.validate_s3_setup()
            elif self.action == 'migrate':
                self.migrate_to_s3()
            elif self.action == 'test':
                self.test_s3_operations()
            elif self.action == 'policy':
                self.setup_bucket_policy()
            elif self.action == 'lifecycle':
                self.setup_lifecycle_rules()
            elif self.action == 'metrics':
                self.show_bucket_metrics()
            elif self.action == 'cleanup':
                self.cleanup_s3_bucket()
            
            self.stdout.write(
                self.style.SUCCESS(f'S3 storage action completed: {self.action}')
            )
            
        except Exception as e:
            logger.error(f"S3 storage command failed: {e}")
            raise CommandError(f'S3 storage command failed: {e}')

    def setup_s3_bucket(self):
        """Set up S3 bucket with all configurations"""
        self.stdout.write("Setting up S3 bucket...")
        
        try:
            # Check if bucket exists
            try:
                self.storage_manager.storage.s3_client.head_bucket(
                    Bucket=self.s3_config.BUCKET_NAME
                )
                
                if not self.force:
                    self.stdout.write(f"Bucket {self.s3_config.BUCKET_NAME} already exists")
                    return
                else:
                    self.stdout.write(f"Bucket exists, but continuing due to --force flag")
                    
            except ClientError as e:
                if e.response['Error']['Code'] == '404':
                    # Bucket doesn't exist, create it
                    self.create_bucket()
                else:
                    raise
            
            # Set up bucket configurations
            if not self.dry_run:
                self.setup_bucket_policy()
                self.setup_bucket_versioning()
                self.setup_lifecycle_rules()
                self.setup_cors_configuration()
                self.setup_encryption()
                
                self.stdout.write("✅ S3 bucket setup completed successfully")
            else:
                self.stdout.write("✅ S3 bucket setup validated (dry run)")
                
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"❌ S3 bucket setup failed: {e}"))
            raise

    def create_bucket(self):
        """Create S3 bucket"""
        self.stdout.write(f"Creating S3 bucket: {self.s3_config.BUCKET_NAME}")
        
        if self.dry_run:
            self.stdout.write("Would create bucket (dry run)")
            return
        
        try:
            if self.s3_config.REGION_NAME == 'us-east-1':
                # us-east-1 doesn't need LocationConstraint
                self.storage_manager.storage.s3_client.create_bucket(
                    Bucket=self.s3_config.BUCKET_NAME
                )
            else:
                self.storage_manager.storage.s3_client.create_bucket(
                    Bucket=self.s3_config.BUCKET_NAME,
                    CreateBucketConfiguration={
                        'LocationConstraint': self.s3_config.REGION_NAME
                    }
                )
            
            self.stdout.write(f"✅ Created bucket: {self.s3_config.BUCKET_NAME}")
            
        except ClientError as e:
            if e.response['Error']['Code'] == 'BucketAlreadyExists':
                self.stdout.write(f"Bucket {self.s3_config.BUCKET_NAME} already exists")
            else:
                raise

    def setup_bucket_policy(self):
        """Set up S3 bucket policy"""
        self.stdout.write("Setting up bucket policy...")
        
        if self.dry_run:
            policy = self.s3_config.get_bucket_policy()
            self.stdout.write("Would apply bucket policy:")
            self.stdout.write(json.dumps(policy, indent=2))
            return
        
        try:
            self.storage_manager.setup_bucket_policy()
            self.stdout.write("✅ Bucket policy configured")
            
        except Exception as e:
            self.stdout.write(self.style.WARNING(f"⚠️  Bucket policy setup failed: {e}"))

    def setup_bucket_versioning(self):
        """Set up S3 bucket versioning"""
        self.stdout.write("Setting up bucket versioning...")
        
        if self.dry_run:
            self.stdout.write(f"Would enable versioning: {self.s3_config.ENABLE_VERSIONING}")
            return
        
        try:
            self.storage_manager.setup_bucket_versioning(self.s3_config.ENABLE_VERSIONING)
            self.stdout.write("✅ Bucket versioning configured")
            
        except Exception as e:
            self.stdout.write(self.style.WARNING(f"⚠️  Bucket versioning setup failed: {e}"))

    def setup_lifecycle_rules(self):
        """Set up S3 lifecycle rules"""
        self.stdout.write("Setting up lifecycle rules...")
        
        if self.dry_run:
            lifecycle = self.s3_config.get_lifecycle_configuration()
            self.stdout.write("Would apply lifecycle configuration:")
            self.stdout.write(json.dumps(lifecycle, indent=2, default=str))
            return
        
        try:
            self.storage_manager.setup_bucket_lifecycle()
            self.stdout.write("✅ Lifecycle rules configured")
            
        except Exception as e:
            self.stdout.write(self.style.WARNING(f"⚠️  Lifecycle rules setup failed: {e}"))

    def setup_cors_configuration(self):
        """Set up CORS configuration"""
        self.stdout.write("Setting up CORS configuration...")
        
        cors_config = self.s3_config.get_cors_configuration()
        
        if self.dry_run:
            self.stdout.write("Would apply CORS configuration:")
            self.stdout.write(json.dumps(cors_config, indent=2))
            return
        
        try:
            self.storage_manager.storage.s3_client.put_bucket_cors(
                Bucket=self.s3_config.BUCKET_NAME,
                CORSConfiguration=cors_config
            )
            self.stdout.write("✅ CORS configuration applied")
            
        except Exception as e:
            self.stdout.write(self.style.WARNING(f"⚠️  CORS configuration failed: {e}"))

    def setup_encryption(self):
        """Set up bucket encryption"""
        self.stdout.write("Setting up bucket encryption...")
        
        encryption_config = {
            'Rules': [
                {
                    'ApplyServerSideEncryptionByDefault': {
                        'SSEAlgorithm': self.s3_config.SERVER_SIDE_ENCRYPTION
                    }
                }
            ]
        }
        
        if self.s3_config.SERVER_SIDE_ENCRYPTION == 'aws:kms' and self.s3_config.KMS_KEY_ID:
            encryption_config['Rules'][0]['ApplyServerSideEncryptionByDefault']['KMSMasterKeyID'] = self.s3_config.KMS_KEY_ID
        
        if self.dry_run:
            self.stdout.write("Would apply encryption configuration:")
            self.stdout.write(json.dumps(encryption_config, indent=2))
            return
        
        try:
            self.storage_manager.storage.s3_client.put_bucket_encryption(
                Bucket=self.s3_config.BUCKET_NAME,
                ServerSideEncryptionConfiguration=encryption_config
            )
            self.stdout.write("✅ Bucket encryption configured")
            
        except Exception as e:
            self.stdout.write(self.style.WARNING(f"⚠️  Bucket encryption setup failed: {e}"))

    def validate_s3_setup(self):
        """Validate S3 setup and configuration"""
        self.stdout.write("Validating S3 setup...")
        
        validation_results = {
            'bucket_exists': False,
            'bucket_accessible': False,
            'policy_configured': False,
            'versioning_enabled': False,
            'lifecycle_configured': False,
            'encryption_enabled': False,
            'cors_configured': False
        }
        
        try:
            # Check bucket existence and accessibility
            self.storage_manager.storage.s3_client.head_bucket(
                Bucket=self.s3_config.BUCKET_NAME
            )
            validation_results['bucket_exists'] = True
            validation_results['bucket_accessible'] = True
            self.stdout.write("✅ Bucket exists and is accessible")
            
            # Check bucket policy
            try:
                self.storage_manager.storage.s3_client.get_bucket_policy(
                    Bucket=self.s3_config.BUCKET_NAME
                )
                validation_results['policy_configured'] = True
                self.stdout.write("✅ Bucket policy is configured")
            except ClientError as e:
                if e.response['Error']['Code'] != 'NoSuchBucketPolicy':
                    raise
                self.stdout.write("⚠️  No bucket policy configured")
            
            # Check versioning
            try:
                response = self.storage_manager.storage.s3_client.get_bucket_versioning(
                    Bucket=self.s3_config.BUCKET_NAME
                )
                if response.get('Status') == 'Enabled':
                    validation_results['versioning_enabled'] = True
                    self.stdout.write("✅ Bucket versioning is enabled")
                else:
                    self.stdout.write("⚠️  Bucket versioning is not enabled")
            except ClientError:
                self.stdout.write("⚠️  Could not check bucket versioning")
            
            # Check lifecycle configuration
            try:
                self.storage_manager.storage.s3_client.get_bucket_lifecycle_configuration(
                    Bucket=self.s3_config.BUCKET_NAME
                )
                validation_results['lifecycle_configured'] = True
                self.stdout.write("✅ Lifecycle rules are configured")
            except ClientError as e:
                if e.response['Error']['Code'] != 'NoSuchLifecycleConfiguration':
                    raise
                self.stdout.write("⚠️  No lifecycle rules configured")
            
            # Check encryption
            try:
                self.storage_manager.storage.s3_client.get_bucket_encryption(
                    Bucket=self.s3_config.BUCKET_NAME
                )
                validation_results['encryption_enabled'] = True
                self.stdout.write("✅ Bucket encryption is enabled")
            except ClientError as e:
                if e.response['Error']['Code'] != 'ServerSideEncryptionConfigurationNotFoundError':
                    raise
                self.stdout.write("⚠️  Bucket encryption is not configured")
            
            # Check CORS
            try:
                self.storage_manager.storage.s3_client.get_bucket_cors(
                    Bucket=self.s3_config.BUCKET_NAME
                )
                validation_results['cors_configured'] = True
                self.stdout.write("✅ CORS configuration is present")
            except ClientError as e:
                if e.response['Error']['Code'] != 'NoSuchCORSConfiguration':
                    raise
                self.stdout.write("⚠️  No CORS configuration")
            
        except ClientError as e:
            if e.response['Error']['Code'] == '404':
                self.stdout.write("❌ Bucket does not exist")
            else:
                self.stdout.write(f"❌ Bucket validation failed: {e}")
        
        # Summary
        configured_count = sum(validation_results.values())
        total_checks = len(validation_results)
        
        self.stdout.write(f"\nValidation Summary: {configured_count}/{total_checks} checks passed")
        
        if configured_count == total_checks:
            self.stdout.write("✅ S3 setup is fully configured")
        elif configured_count >= total_checks * 0.7:
            self.stdout.write("⚠️  S3 setup is mostly configured")
        else:
            self.stdout.write("❌ S3 setup needs attention")

    def migrate_to_s3(self):
        """Migrate files from local storage to S3"""
        if not self.source_path:
            self.source_path = getattr(settings, 'MEDIA_ROOT', 'media')
        
        self.stdout.write(f"Migrating files from {self.source_path} to S3...")
        
        if self.dry_run:
            self.stdout.write("Would migrate files (dry run)")
            # Count files that would be migrated
            from pathlib import Path
            source_path = Path(self.source_path)
            if source_path.exists():
                file_count = len(list(source_path.rglob('*')))
                self.stdout.write(f"Would migrate approximately {file_count} files")
            return
        
        try:
            result = self.storage_manager.migrate_from_local_storage(
                self.source_path,
                batch_size=self.batch_size
            )
            
            self.stdout.write(f"✅ Migration completed:")
            self.stdout.write(f"  - Migrated: {result['migrated_count']} files")
            self.stdout.write(f"  - Failed: {len(result['failed_files'])} files")
            
            if result['failed_files']:
                self.stdout.write("Failed files:")
                for failed_file in result['failed_files'][:10]:  # Show first 10
                    self.stdout.write(f"  - {failed_file}")
                if len(result['failed_files']) > 10:
                    self.stdout.write(f"  ... and {len(result['failed_files']) - 10} more")
            
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"❌ Migration failed: {e}"))
            raise

    def test_s3_operations(self):
        """Test basic S3 operations"""
        self.stdout.write("Testing S3 operations...")
        
        test_file_name = "test_clinical_record.txt"
        test_content = "This is a test clinical record file for S3 operations."
        
        try:
            # Test file upload
            from django.core.files.base import ContentFile
            content_file = ContentFile(test_content.encode())
            content_file.name = test_file_name
            
            if not self.dry_run:
                saved_name = self.storage_manager.storage._save(test_file_name, content_file)
                self.stdout.write(f"✅ File upload successful: {saved_name}")
                
                # Test file existence
                if self.storage_manager.storage.exists(saved_name):
                    self.stdout.write("✅ File existence check successful")
                else:
                    self.stdout.write("❌ File existence check failed")
                
                # Test file size
                size = self.storage_manager.storage.size(saved_name)
                self.stdout.write(f"✅ File size check successful: {size} bytes")
                
                # Test presigned URL generation
                url = self.storage_manager.storage.url(saved_name)
                self.stdout.write(f"✅ Presigned URL generation successful")
                
                # Test file metadata
                metadata = self.storage_manager.storage.get_file_metadata(saved_name)
                self.stdout.write(f"✅ File metadata retrieval successful")
                
                # Test file deletion
                self.storage_manager.storage.delete(saved_name)
                self.stdout.write("✅ File deletion successful")
                
            else:
                self.stdout.write("✅ S3 operations test (dry run)")
            
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"❌ S3 operations test failed: {e}"))
            raise

    def show_bucket_metrics(self):
        """Show S3 bucket metrics"""
        self.stdout.write("Retrieving S3 bucket metrics...")
        
        try:
            metrics = self.storage_manager.get_bucket_metrics()
            
            self.stdout.write(f"\nS3 Bucket Metrics:")
            self.stdout.write(f"  Bucket Name: {metrics['bucket_name']}")
            self.stdout.write(f"  Total Objects: {metrics['object_count']:,}")
            self.stdout.write(f"  Total Size: {metrics['total_size_gb']:.2f} GB")
            self.stdout.write(f"  Total Size: {metrics['total_size_mb']:.2f} MB")
            self.stdout.write(f"  Total Size: {metrics['total_size_bytes']:,} bytes")
            
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"❌ Failed to retrieve metrics: {e}"))
            raise

    def cleanup_s3_bucket(self):
        """Clean up S3 bucket (delete all objects)"""
        self.stdout.write("Cleaning up S3 bucket...")
        
        if not self.force:
            self.stdout.write("Use --force to confirm bucket cleanup")
            return
        
        if self.dry_run:
            self.stdout.write("Would delete all objects in bucket (dry run)")
            return
        
        try:
            # List and delete all objects
            response = self.storage_manager.storage.s3_client.list_objects_v2(
                Bucket=self.s3_config.BUCKET_NAME
            )
            
            deleted_count = 0
            
            while True:
                objects = response.get('Contents', [])
                
                if not objects:
                    break
                
                # Delete objects in batches
                delete_keys = [{'Key': obj['Key']} for obj in objects]
                
                self.storage_manager.storage.s3_client.delete_objects(
                    Bucket=self.s3_config.BUCKET_NAME,
                    Delete={'Objects': delete_keys}
                )
                
                deleted_count += len(delete_keys)
                self.stdout.write(f"Deleted {deleted_count} objects...")
                
                # Check for more objects
                if not response.get('IsTruncated'):
                    break
                
                response = self.storage_manager.storage.s3_client.list_objects_v2(
                    Bucket=self.s3_config.BUCKET_NAME,
                    ContinuationToken=response['NextContinuationToken']
                )
            
            self.stdout.write(f"✅ Cleanup completed: {deleted_count} objects deleted")
            
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"❌ Cleanup failed: {e}"))
            raise