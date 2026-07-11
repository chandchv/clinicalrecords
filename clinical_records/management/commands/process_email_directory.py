"""
Management command to process emails from a directory

This command processes email files (.eml, .msg, .txt) from a specified directory
and ingests them into the clinical records system.
"""
import os
import logging
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from users.models import Clinic, CustomUser
from clinical_records.services.email_ingestion_service import email_ingestion_service, EmailIngestionError

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Process email files from a directory for clinical record ingestion'
    
    def add_arguments(self, parser):
        parser.add_argument(
            'directory',
            type=str,
            help='Directory containing email files to process'
        )
        parser.add_argument(
            '--clinic-id',
            type=str,
            required=True,
            help='ID of the clinic to process emails for'
        )
        parser.add_argument(
            '--user-id',
            type=str,
            help='ID of the user to attribute processing to (optional)'
        )
        parser.add_argument(
            '--file-pattern',
            type=str,
            default='*.eml',
            help='File pattern to match (default: *.eml)'
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be processed without actually processing'
        )
        parser.add_argument(
            '--continue-on-error',
            action='store_true',
            help='Continue processing other files if one fails'
        )
        parser.add_argument(
            '--verbose',
            action='store_true',
            help='Enable verbose output'
        )
    
    def handle(self, *args, **options):
        directory = options['directory']
        clinic_id = options['clinic_id']
        user_id = options.get('user_id')
        file_pattern = options['file_pattern']
        dry_run = options['dry_run']
        continue_on_error = options['continue_on_error']
        verbose = options['verbose']
        
        # Set up logging
        if verbose:
            logging.basicConfig(level=logging.DEBUG)
        
        # Validate directory
        if not os.path.exists(directory):
            raise CommandError(f"Directory does not exist: {directory}")
        
        if not os.path.isdir(directory):
            raise CommandError(f"Path is not a directory: {directory}")
        
        # Get clinic
        try:
            clinic = Clinic.objects.get(id=clinic_id)
        except Clinic.DoesNotExist:
            raise CommandError(f"Clinic not found: {clinic_id}")
        
        # Get user if specified
        processing_user = None
        if user_id:
            try:
                processing_user = CustomUser.objects.get(id=user_id)
                processing_user.current_tenant = clinic
            except CustomUser.DoesNotExist:
                raise CommandError(f"User not found: {user_id}")
        
        # Find email files
        email_files = self._find_email_files(directory, file_pattern)
        
        if not email_files:
            self.stdout.write(
                self.style.WARNING(f"No email files found in {directory} matching {file_pattern}")
            )
            return
        
        self.stdout.write(
            self.style.SUCCESS(f"Found {len(email_files)} email files to process")
        )
        
        if dry_run:
            self.stdout.write(self.style.WARNING("DRY RUN - No files will be processed"))
            for email_file in email_files:
                self.stdout.write(f"Would process: {email_file}")
            return
        
        # Process files
        processed_count = 0
        error_count = 0
        
        for email_file in email_files:
            try:
                self.stdout.write(f"Processing: {email_file}")
                
                result = email_ingestion_service.process_email_file(
                    email_file_path=email_file,
                    clinic=clinic,
                    processing_user=processing_user
                )
                
                if result['success']:
                    processed_count += 1
                    documents_created = len(result.get('documents_created', []))
                    patient_name = result.get('patient_match', {}).get('name', 'Unknown')
                    
                    self.stdout.write(
                        self.style.SUCCESS(
                            f"✓ Processed {email_file}: {documents_created} documents created for {patient_name}"
                        )
                    )
                    
                    if verbose:
                        for doc in result.get('documents_created', []):
                            self.stdout.write(f"  - {doc['filename']} ({doc['record_type']})")
                else:
                    error_count += 1
                    errors = '; '.join(result.get('errors', ['Unknown error']))
                    self.stdout.write(
                        self.style.ERROR(f"✗ Failed to process {email_file}: {errors}")
                    )
                    
                    if not continue_on_error:
                        raise CommandError(f"Processing failed for {email_file}")
                
            except EmailIngestionError as e:
                error_count += 1
                self.stdout.write(
                    self.style.ERROR(f"✗ Error processing {email_file}: {e}")
                )
                
                if not continue_on_error:
                    raise CommandError(f"Processing failed for {email_file}: {e}")
            
            except Exception as e:
                error_count += 1
                logger.exception(f"Unexpected error processing {email_file}")
                self.stdout.write(
                    self.style.ERROR(f"✗ Unexpected error processing {email_file}: {e}")
                )
                
                if not continue_on_error:
                    raise CommandError(f"Unexpected error processing {email_file}: {e}")
        
        # Summary
        self.stdout.write("\n" + "="*50)
        self.stdout.write("PROCESSING SUMMARY")
        self.stdout.write("="*50)
        self.stdout.write(f"Total files found: {len(email_files)}")
        self.stdout.write(f"Successfully processed: {processed_count}")
        self.stdout.write(f"Failed: {error_count}")
        
        if processed_count > 0:
            self.stdout.write(
                self.style.SUCCESS(f"✓ Successfully processed {processed_count} email files")
            )
        
        if error_count > 0:
            self.stdout.write(
                self.style.WARNING(f"⚠ {error_count} files failed to process")
            )
    
    def _find_email_files(self, directory, pattern):
        """Find email files in directory matching pattern"""
        import glob
        
        # Convert simple pattern to glob pattern
        if pattern == '*.eml':
            patterns = ['*.eml', '*.msg', '*.txt']
        else:
            patterns = [pattern]
        
        email_files = []
        for pattern in patterns:
            search_pattern = os.path.join(directory, pattern)
            email_files.extend(glob.glob(search_pattern))
        
        # Filter for actual email files
        valid_extensions = ['.eml', '.msg', '.txt', '.email']
        filtered_files = []
        
        for file_path in email_files:
            if any(file_path.lower().endswith(ext) for ext in valid_extensions):
                filtered_files.append(file_path)
        
        return sorted(filtered_files)