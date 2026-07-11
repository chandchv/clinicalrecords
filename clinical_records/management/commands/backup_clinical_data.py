#!/usr/bin/env python3
"""
Comprehensive backup management command for clinical records system.
Handles database backups, file storage backups, and metadata preservation.
"""

import os
import sys
import subprocess
import datetime
import json
import shutil
import hashlib
import logging
from pathlib import Path
from django.core.management.base import BaseCommand, CommandError
from django.conf import settings
from django.db import connection
from django.core.management import call_command
from clinical_records.models import ClinicalRecord, ClinicalDocument
from users.models import Clinic, CustomUser, Patient

logger = logging.getLogger(__name__)

class Command(BaseCommand):
    help = 'Create comprehensive backup of clinical records data and files'

    def add_arguments(self, parser):
        parser.add_argument(
            '--backup-type',
            type=str,
            choices=['full', 'incremental', 'database-only', 'files-only'],
            default='full',
            help='Type of backup to perform'
        )
        parser.add_argument(
            '--output-dir',
            type=str,
            default='clinical_backups',
            help='Directory to store backup files'
        )
        parser.add_argument(
            '--compress',
            action='store_true',
            help='Compress backup files'
        )
        parser.add_argument(
            '--encrypt',
            action='store_true',
            help='Encrypt backup files'
        )
        parser.add_argument(
            '--clinic-id',
            type=str,
            help='Backup specific clinic only'
        )
        parser.add_argument(
            '--retention-days',
            type=int,
            default=30,
            help='Number of days to retain backups'
        )

    def handle(self, *args, **options):
        """Main backup execution"""
        try:
            self.backup_type = options['backup_type']
            self.output_dir = Path(options['output_dir'])
            self.compress = options['compress']
            self.encrypt = options['encrypt']
            self.clinic_id = options['clinic_id']
            self.retention_days = options['retention_days']
            
            # Create backup directory with timestamp
            timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            self.backup_dir = self.output_dir / f"clinical_backup_{timestamp}"
            self.backup_dir.mkdir(parents=True, exist_ok=True)
            
            self.stdout.write(f"Starting {self.backup_type} backup...")
            self.stdout.write(f"Backup directory: {self.backup_dir}")
            
            # Initialize backup metadata
            self.backup_metadata = {
                'backup_type': self.backup_type,
                'timestamp': timestamp,
                'start_time': datetime.datetime.now().isoformat(),
                'clinic_id': self.clinic_id,
                'components': [],
                'file_count': 0,
                'total_size': 0,
                'status': 'in_progress'
            }
            
            # Perform backup based on type
            if self.backup_type in ['full', 'database-only']:
                self.backup_database()
            
            if self.backup_type in ['full', 'files-only']:
                self.backup_clinical_files()
            
            if self.backup_type in ['full', 'incremental']:
                self.backup_metadata()
            
            # Finalize backup
            self.finalize_backup()
            
            # Cleanup old backups
            self.cleanup_old_backups()
            
            self.stdout.write(
                self.style.SUCCESS(f'Backup completed successfully: {self.backup_dir}')
            )
            
        except Exception as e:
            logger.error(f"Backup failed: {e}")
            self.backup_metadata['status'] = 'failed'
            self.backup_metadata['error'] = str(e)
            self.save_backup_metadata()
            raise CommandError(f'Backup failed: {e}')

    def backup_database(self):
        """Create database backup"""
        self.stdout.write("Creating database backup...")
        
        db_config = settings.DATABASES['default']
        timestamp = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
        
        if 'postgresql' in db_config['ENGINE']:
            backup_file = self.backup_dir / f"database_backup_{timestamp}.sql"
            self.create_postgresql_backup(backup_file, db_config)
        else:
            # Fallback to Django dumpdata
            backup_file = self.backup_dir / f"django_data_backup_{timestamp}.json"
            self.create_django_backup(backup_file)
        
        self.backup_metadata['components'].append({
            'type': 'database',
            'file': str(backup_file),
            'size': backup_file.stat().st_size if backup_file.exists() else 0
        })

    def create_postgresql_backup(self, backup_file, db_config):
        """Create PostgreSQL backup using pg_dump"""
        env = os.environ.copy()
        if db_config.get('PASSWORD'):
            env['PGPASSWORD'] = db_config['PASSWORD']
        
        cmd = [
            'pg_dump',
            '--host', db_config.get('HOST', 'localhost'),
            '--port', str(db_config.get('PORT', 5432)),
            '--username', db_config.get('USER', 'postgres'),
            '--dbname', db_config['NAME'],
            '--verbose',
            '--clean',
            '--create',
            '--format=plain',
            '--file', str(backup_file)
        ]
        
        try:
            result = subprocess.run(cmd, env=env, capture_output=True, text=True, check=True)
            self.stdout.write("✅ PostgreSQL backup created successfully!")
        except subprocess.CalledProcessError as e:
            self.stdout.write(f"❌ PostgreSQL backup failed: {e}")
            # Fallback to Django backup
            self.create_django_backup(backup_file.with_suffix('.json'))

    def create_django_backup(self, backup_file):
        """Create Django data backup using dumpdata"""
        try:
            with open(backup_file, 'w', encoding='utf-8') as f:
                call_command(
                    'dumpdata',
                    'clinical_records',
                    'users.clinic',
                    'users.customuser',
                    'users.patient',
                    'users.doctor',
                    stdout=f,
                    indent=2
                )
            self.stdout.write("✅ Django data backup created successfully!")
        except Exception as e:
            self.stdout.write(f"❌ Django backup failed: {e}")
            raise

    def backup_clinical_files(self):
        """Backup clinical document files"""
        self.stdout.write("Backing up clinical files...")
        
        files_dir = self.backup_dir / "clinical_files"
        files_dir.mkdir(exist_ok=True)
        
        # Query clinical documents
        documents = ClinicalDocument.objects.all()
        if self.clinic_id:
            documents = documents.filter(clinical_record__clinic_id=self.clinic_id)
        
        file_count = 0
        total_size = 0
        failed_files = []
        
        for document in documents:
            try:
                # Determine source file path
                if hasattr(document, 's3_key') and document.s3_key:
                    # Handle S3 files (future implementation)
                    self.backup_s3_file(document, files_dir)
                else:
                    # Handle local files
                    self.backup_local_file(document, files_dir)
                
                file_count += 1
                total_size += document.file_size or 0
                
            except Exception as e:
                failed_files.append({
                    'document_id': str(document.id),
                    'file_name': document.file_name,
                    'error': str(e)
                })
                logger.error(f"Failed to backup file {document.file_name}: {e}")
        
        self.backup_metadata['components'].append({
            'type': 'clinical_files',
            'file_count': file_count,
            'total_size': total_size,
            'failed_files': failed_files
        })
        
        self.backup_metadata['file_count'] = file_count
        self.backup_metadata['total_size'] = total_size

    def backup_local_file(self, document, files_dir):
        """Backup local file"""
        if hasattr(document, 'file') and document.file:
            source_path = Path(document.file.path)
            if source_path.exists():
                # Create tenant-specific subdirectory
                tenant_dir = files_dir / str(document.clinical_record.clinic_id)
                tenant_dir.mkdir(exist_ok=True)
                
                # Copy file with original structure
                dest_path = tenant_dir / document.file_name
                shutil.copy2(source_path, dest_path)
                
                # Verify file integrity
                self.verify_file_integrity(source_path, dest_path)

    def backup_s3_file(self, document, files_dir):
        """Backup S3 file (placeholder for future implementation)"""
        # TODO: Implement S3 file backup when S3 storage is implemented
        pass

    def verify_file_integrity(self, source_path, dest_path):
        """Verify file integrity using checksums"""
        def get_file_hash(file_path):
            hash_sha256 = hashlib.sha256()
            with open(file_path, "rb") as f:
                for chunk in iter(lambda: f.read(4096), b""):
                    hash_sha256.update(chunk)
            return hash_sha256.hexdigest()
        
        source_hash = get_file_hash(source_path)
        dest_hash = get_file_hash(dest_path)
        
        if source_hash != dest_hash:
            raise ValueError(f"File integrity check failed for {source_path}")

    def backup_metadata(self):
        """Backup system metadata and configuration"""
        self.stdout.write("Backing up metadata...")
        
        metadata_dir = self.backup_dir / "metadata"
        metadata_dir.mkdir(exist_ok=True)
        
        # Backup clinical records metadata
        records_metadata = []
        records = ClinicalRecord.objects.all()
        if self.clinic_id:
            records = records.filter(clinic_id=self.clinic_id)
        
        for record in records:
            records_metadata.append({
                'id': str(record.id),
                'patient_id': str(record.patient_id),
                'clinic_id': str(record.clinic_id),
                'record_type': record.record_type,
                'title': record.title,
                'created_at': record.created_at.isoformat(),
                'metadata': record.metadata,
                'tags': record.tags
            })
        
        # Save metadata
        with open(metadata_dir / "clinical_records_metadata.json", 'w') as f:
            json.dump(records_metadata, f, indent=2, default=str)
        
        # Backup system configuration
        config_data = {
            'django_settings': {
                'MEDIA_ROOT': str(settings.MEDIA_ROOT),
                'MEDIA_URL': settings.MEDIA_URL,
                'DATABASE_ENGINE': settings.DATABASES['default']['ENGINE'],
                'INSTALLED_APPS': settings.INSTALLED_APPS
            },
            'backup_timestamp': datetime.datetime.now().isoformat(),
            'python_version': sys.version,
            'django_version': getattr(settings, 'DJANGO_VERSION', 'unknown')
        }
        
        with open(metadata_dir / "system_config.json", 'w') as f:
            json.dump(config_data, f, indent=2)

    def finalize_backup(self):
        """Finalize backup process"""
        self.backup_metadata['end_time'] = datetime.datetime.now().isoformat()
        self.backup_metadata['status'] = 'completed'
        
        # Calculate backup size
        total_size = sum(
            f.stat().st_size 
            for f in self.backup_dir.rglob('*') 
            if f.is_file()
        )
        self.backup_metadata['backup_size'] = total_size
        
        # Save backup metadata
        self.save_backup_metadata()
        
        # Compress if requested
        if self.compress:
            self.compress_backup()
        
        # Encrypt if requested
        if self.encrypt:
            self.encrypt_backup()

    def save_backup_metadata(self):
        """Save backup metadata"""
        metadata_file = self.backup_dir / "backup_metadata.json"
        with open(metadata_file, 'w') as f:
            json.dump(self.backup_metadata, f, indent=2, default=str)

    def compress_backup(self):
        """Compress backup directory"""
        self.stdout.write("Compressing backup...")
        
        archive_path = self.backup_dir.with_suffix('.tar.gz')
        shutil.make_archive(
            str(self.backup_dir),
            'gztar',
            root_dir=self.backup_dir.parent,
            base_dir=self.backup_dir.name
        )
        
        # Remove original directory
        shutil.rmtree(self.backup_dir)
        self.backup_dir = archive_path

    def encrypt_backup(self):
        """Encrypt backup files (placeholder)"""
        # TODO: Implement encryption using cryptography library
        self.stdout.write("Encryption requested but not yet implemented")

    def cleanup_old_backups(self):
        """Remove old backup files based on retention policy"""
        if self.retention_days <= 0:
            return
        
        cutoff_date = datetime.datetime.now() - datetime.timedelta(days=self.retention_days)
        
        for backup_path in self.output_dir.glob("clinical_backup_*"):
            try:
                # Extract timestamp from backup name
                timestamp_str = backup_path.name.split('_')[-1]
                if len(timestamp_str) == 15:  # YYYYMMDD_HHMMSS
                    backup_date = datetime.datetime.strptime(timestamp_str, "%Y%m%d_%H%M%S")
                    if backup_date < cutoff_date:
                        if backup_path.is_dir():
                            shutil.rmtree(backup_path)
                        else:
                            backup_path.unlink()
                        self.stdout.write(f"Removed old backup: {backup_path}")
            except (ValueError, IndexError):
                # Skip files that don't match expected format
                continue