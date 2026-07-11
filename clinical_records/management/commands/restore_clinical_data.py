#!/usr/bin/env python3
"""
Comprehensive restore management command for clinical records system.
Handles database restoration, file restoration, and data validation.
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
from django.db import connection, transaction
from django.core.management import call_command
from clinical_records.models import ClinicalRecord, ClinicalDocument
from users.models import Clinic, CustomUser, Patient

logger = logging.getLogger(__name__)

class Command(BaseCommand):
    help = 'Restore clinical records data and files from backup'

    def add_arguments(self, parser):
        parser.add_argument(
            'backup_path',
            type=str,
            help='Path to backup directory or archive'
        )
        parser.add_argument(
            '--restore-type',
            type=str,
            choices=['full', 'database-only', 'files-only', 'metadata-only'],
            default='full',
            help='Type of restore to perform'
        )
        parser.add_argument(
            '--clinic-id',
            type=str,
            help='Restore specific clinic only'
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Perform validation without actual restore'
        )
        parser.add_argument(
            '--force',
            action='store_true',
            help='Force restore even if validation fails'
        )
        parser.add_argument(
            '--backup-existing',
            action='store_true',
            help='Create backup of existing data before restore'
        )

    def handle(self, *args, **options):
        """Main restore execution"""
        try:
            self.backup_path = Path(options['backup_path'])
            self.restore_type = options['restore_type']
            self.clinic_id = options['clinic_id']
            self.dry_run = options['dry_run']
            self.force = options['force']
            self.backup_existing = options['backup_existing']
            
            if not self.backup_path.exists():
                raise CommandError(f"Backup path does not exist: {self.backup_path}")
            
            # Extract backup if it's an archive
            self.working_dir = self.extract_backup_if_needed()
            
            # Load and validate backup metadata
            self.backup_metadata = self.load_backup_metadata()
            self.validate_backup()
            
            if self.dry_run:
                self.stdout.write("Dry run completed successfully. No changes made.")
                return
            
            # Backup existing data if requested
            if self.backup_existing:
                self.create_pre_restore_backup()
            
            self.stdout.write(f"Starting {self.restore_type} restore...")
            
            # Initialize restore metadata
            self.restore_metadata = {
                'restore_type': self.restore_type,
                'backup_source': str(self.backup_path),
                'start_time': datetime.datetime.now().isoformat(),
                'clinic_id': self.clinic_id,
                'components_restored': [],
                'status': 'in_progress'
            }
            
            # Perform restore based on type
            if self.restore_type in ['full', 'database-only']:
                self.restore_database()
            
            if self.restore_type in ['full', 'files-only']:
                self.restore_clinical_files()
            
            if self.restore_type in ['full', 'metadata-only']:
                self.restore_metadata()
            
            # Finalize restore
            self.finalize_restore()
            
            self.stdout.write(
                self.style.SUCCESS('Restore completed successfully!')
            )
            
        except Exception as e:
            logger.error(f"Restore failed: {e}")
            self.restore_metadata['status'] = 'failed'
            self.restore_metadata['error'] = str(e)
            self.save_restore_metadata()
            raise CommandError(f'Restore failed: {e}')

    def extract_backup_if_needed(self):
        """Extract backup archive if needed"""
        if self.backup_path.is_file() and self.backup_path.suffix in ['.tar', '.gz']:
            # Extract archive to temporary directory
            extract_dir = self.backup_path.parent / f"temp_restore_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}"
            extract_dir.mkdir(exist_ok=True)
            
            self.stdout.write(f"Extracting backup archive: {self.backup_path}")
            shutil.unpack_archive(str(self.backup_path), str(extract_dir))
            
            # Find the actual backup directory
            backup_dirs = list(extract_dir.glob("clinical_backup_*"))
            if backup_dirs:
                return backup_dirs[0]
            else:
                return extract_dir
        
        return self.backup_path

    def load_backup_metadata(self):
        """Load backup metadata"""
        metadata_file = self.working_dir / "backup_metadata.json"
        if not metadata_file.exists():
            raise CommandError("Backup metadata file not found")
        
        with open(metadata_file, 'r') as f:
            return json.load(f)

    def validate_backup(self):
        """Validate backup integrity and compatibility"""
        self.stdout.write("Validating backup...")
        
        # Check backup status
        if self.backup_metadata.get('status') != 'completed':
            if not self.force:
                raise CommandError("Backup is incomplete or failed. Use --force to proceed anyway.")
            self.stdout.write(self.style.WARNING("Warning: Backup is incomplete but proceeding due to --force"))
        
        # Validate backup components
        components = self.backup_metadata.get('components', [])
        for component in components:
            if component['type'] == 'database':
                db_file = Path(component['file'])
                if not db_file.exists():
                    raise CommandError(f"Database backup file not found: {db_file}")
            
            elif component['type'] == 'clinical_files':
                files_dir = self.working_dir / "clinical_files"
                if not files_dir.exists():
                    if not self.force:
                        raise CommandError("Clinical files directory not found in backup")
        
        # Check clinic compatibility
        if self.clinic_id:
            metadata_dir = self.working_dir / "metadata"
            if metadata_dir.exists():
                records_file = metadata_dir / "clinical_records_metadata.json"
                if records_file.exists():
                    with open(records_file, 'r') as f:
                        records_metadata = json.load(f)
                    
                    clinic_records = [r for r in records_metadata if r['clinic_id'] == self.clinic_id]
                    if not clinic_records:
                        self.stdout.write(f"Warning: No records found for clinic {self.clinic_id} in backup")
        
        self.stdout.write("✅ Backup validation completed")

    def create_pre_restore_backup(self):
        """Create backup of existing data before restore"""
        self.stdout.write("Creating pre-restore backup...")
        
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        pre_restore_dir = Path(f"pre_restore_backup_{timestamp}")
        
        # Use the backup command to create pre-restore backup
        call_command(
            'backup_clinical_data',
            '--backup-type', 'full',
            '--output-dir', str(pre_restore_dir.parent),
            '--clinic-id', self.clinic_id if self.clinic_id else None
        )

    def restore_database(self):
        """Restore database from backup"""
        self.stdout.write("Restoring database...")
        
        # Find database backup file
        db_component = next(
            (c for c in self.backup_metadata['components'] if c['type'] == 'database'),
            None
        )
        
        if not db_component:
            raise CommandError("No database backup found in backup metadata")
        
        db_file = Path(db_component['file'])
        if not db_file.exists():
            # Try relative path from working directory
            db_file = self.working_dir / db_file.name
        
        if not db_file.exists():
            raise CommandError(f"Database backup file not found: {db_file}")
        
        db_config = settings.DATABASES['default']
        
        if db_file.suffix == '.sql' and 'postgresql' in db_config['ENGINE']:
            self.restore_postgresql_backup(db_file, db_config)
        elif db_file.suffix == '.json':
            self.restore_django_backup(db_file)
        else:
            raise CommandError(f"Unsupported database backup format: {db_file}")
        
        self.restore_metadata['components_restored'].append('database')

    def restore_postgresql_backup(self, backup_file, db_config):
        """Restore PostgreSQL backup using psql"""
        env = os.environ.copy()
        if db_config.get('PASSWORD'):
            env['PGPASSWORD'] = db_config['PASSWORD']
        
        # Drop and recreate database (if not in production)
        if not settings.DEBUG:
            self.stdout.write(self.style.WARNING(
                "Warning: Restoring to production database. Ensure you have proper backups!"
            ))
        
        cmd = [
            'psql',
            '--host', db_config.get('HOST', 'localhost'),
            '--port', str(db_config.get('PORT', 5432)),
            '--username', db_config.get('USER', 'postgres'),
            '--dbname', db_config['NAME'],
            '--file', str(backup_file)
        ]
        
        try:
            result = subprocess.run(cmd, env=env, capture_output=True, text=True, check=True)
            self.stdout.write("✅ PostgreSQL database restored successfully!")
        except subprocess.CalledProcessError as e:
            self.stdout.write(f"❌ PostgreSQL restore failed: {e}")
            self.stdout.write(f"STDERR: {e.stderr}")
            raise CommandError(f"Database restore failed: {e}")

    def restore_django_backup(self, backup_file):
        """Restore Django data backup using loaddata"""
        try:
            # Clear existing data if full restore
            if self.restore_type == 'full':
                self.stdout.write("Clearing existing clinical records data...")
                with transaction.atomic():
                    ClinicalDocument.objects.all().delete()
                    ClinicalRecord.objects.all().delete()
            
            # Load data
            call_command('loaddata', str(backup_file))
            self.stdout.write("✅ Django data restored successfully!")
            
        except Exception as e:
            self.stdout.write(f"❌ Django data restore failed: {e}")
            raise CommandError(f"Django data restore failed: {e}")

    def restore_clinical_files(self):
        """Restore clinical document files"""
        self.stdout.write("Restoring clinical files...")
        
        files_dir = self.working_dir / "clinical_files"
        if not files_dir.exists():
            self.stdout.write("No clinical files directory found in backup")
            return
        
        # Get target media directory
        media_root = Path(settings.MEDIA_ROOT)
        clinical_files_dir = media_root / "clinical_documents"
        clinical_files_dir.mkdir(parents=True, exist_ok=True)
        
        file_count = 0
        failed_files = []
        
        # Restore files by clinic
        for clinic_dir in files_dir.iterdir():
            if not clinic_dir.is_dir():
                continue
            
            # Skip if restoring specific clinic and this isn't it
            if self.clinic_id and clinic_dir.name != self.clinic_id:
                continue
            
            target_clinic_dir = clinical_files_dir / clinic_dir.name
            target_clinic_dir.mkdir(exist_ok=True)
            
            for file_path in clinic_dir.rglob('*'):
                if file_path.is_file():
                    try:
                        # Restore file with original structure
                        relative_path = file_path.relative_to(clinic_dir)
                        target_path = target_clinic_dir / relative_path
                        target_path.parent.mkdir(parents=True, exist_ok=True)
                        
                        shutil.copy2(file_path, target_path)
                        file_count += 1
                        
                    except Exception as e:
                        failed_files.append({
                            'file': str(file_path),
                            'error': str(e)
                        })
                        logger.error(f"Failed to restore file {file_path}: {e}")
        
        self.restore_metadata['components_restored'].append({
            'type': 'clinical_files',
            'file_count': file_count,
            'failed_files': failed_files
        })
        
        self.stdout.write(f"✅ Restored {file_count} clinical files")
        if failed_files:
            self.stdout.write(f"⚠️  {len(failed_files)} files failed to restore")

    def restore_metadata(self):
        """Restore metadata and configuration"""
        self.stdout.write("Restoring metadata...")
        
        metadata_dir = self.working_dir / "metadata"
        if not metadata_dir.exists():
            self.stdout.write("No metadata directory found in backup")
            return
        
        # Restore clinical records metadata if needed
        records_file = metadata_dir / "clinical_records_metadata.json"
        if records_file.exists():
            with open(records_file, 'r') as f:
                records_metadata = json.load(f)
            
            # Update records with restored metadata
            for record_meta in records_metadata:
                if self.clinic_id and record_meta['clinic_id'] != self.clinic_id:
                    continue
                
                try:
                    record = ClinicalRecord.objects.get(id=record_meta['id'])
                    record.metadata = record_meta['metadata']
                    record.tags = record_meta['tags']
                    record.save()
                except ClinicalRecord.DoesNotExist:
                    self.stdout.write(f"Warning: Record {record_meta['id']} not found")
        
        self.restore_metadata['components_restored'].append('metadata')

    def finalize_restore(self):
        """Finalize restore process"""
        self.restore_metadata['end_time'] = datetime.datetime.now().isoformat()
        self.restore_metadata['status'] = 'completed'
        
        # Save restore metadata
        self.save_restore_metadata()
        
        # Run post-restore validation
        self.validate_restored_data()
        
        # Clean up temporary files
        if self.working_dir != self.backup_path:
            shutil.rmtree(self.working_dir)

    def save_restore_metadata(self):
        """Save restore metadata"""
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        metadata_file = Path(f"restore_metadata_{timestamp}.json")
        
        with open(metadata_file, 'w') as f:
            json.dump(self.restore_metadata, f, indent=2, default=str)
        
        self.stdout.write(f"Restore metadata saved: {metadata_file}")

    def validate_restored_data(self):
        """Validate restored data integrity"""
        self.stdout.write("Validating restored data...")
        
        # Count restored records
        total_records = ClinicalRecord.objects.count()
        total_documents = ClinicalDocument.objects.count()
        
        if self.clinic_id:
            clinic_records = ClinicalRecord.objects.filter(clinic_id=self.clinic_id).count()
            clinic_documents = ClinicalDocument.objects.filter(
                clinical_record__clinic_id=self.clinic_id
            ).count()
            
            self.stdout.write(f"Clinic {self.clinic_id}: {clinic_records} records, {clinic_documents} documents")
        
        self.stdout.write(f"Total: {total_records} records, {total_documents} documents")
        
        # Validate file references
        missing_files = []
        for document in ClinicalDocument.objects.all()[:100]:  # Sample check
            if hasattr(document, 'file') and document.file:
                if not Path(document.file.path).exists():
                    missing_files.append(str(document.id))
        
        if missing_files:
            self.stdout.write(f"⚠️  {len(missing_files)} documents have missing files")
        else:
            self.stdout.write("✅ File references validated")
        
        self.stdout.write("✅ Data validation completed")