"""
Management command for encryption operations.

This command provides utilities for managing file encryption,
key rotation, and encryption monitoring.
"""

import os
import json
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone
from django.db.models import Count, Q

from clinical_records.models import ClinicalDocument
from clinical_records.services.encryption_service import (
    EncryptionService, generate_master_key, rotate_tenant_keys
)
from users.models import Clinic


class Command(BaseCommand):
    help = 'Manage encryption for clinical records'

    def add_arguments(self, parser):
        parser.add_argument(
            '--action',
            type=str,
            choices=[
                'status', 'encrypt-clinic', 'encrypt-all', 'rotate-keys',
                'verify-integrity', 'generate-key', 'health-check'
            ],
            default='status',
            help='Action to perform'
        )
        
        parser.add_argument(
            '--clinic-id',
            type=int,
            help='Specific clinic ID to operate on'
        )
        
        parser.add_argument(
            '--force',
            action='store_true',
            help='Force operation even if files are already encrypted'
        )
        
        parser.add_argument(
            '--output-format',
            type=str,
            choices=['table', 'json'],
            default='table',
            help='Output format for results'
        )

    def handle(self, *args, **options):
        action = options['action']
        
        try:
            if action == 'status':
                self.show_encryption_status(options)
            elif action == 'encrypt-clinic':
                self.encrypt_clinic_files(options)
            elif action == 'encrypt-all':
                self.encrypt_all_files(options)
            elif action == 'rotate-keys':
                self.rotate_encryption_keys(options)
            elif action == 'verify-integrity':
                self.verify_encryption_integrity(options)
            elif action == 'generate-key':
                self.generate_master_key(options)
            elif action == 'health-check':
                self.perform_health_check(options)
                
        except Exception as e:
            raise CommandError(f"Error executing {action}: {str(e)}")

    def show_encryption_status(self, options):
        """Show encryption status across all clinics or specific clinic."""
        self.stdout.write(self.style.SUCCESS('Encryption Status Report'))
        self.stdout.write('=' * 50)
        
        try:
            encryption_service = EncryptionService()
            
            # Check master key configuration
            master_key_status = "✓ Configured" if encryption_service.master_key else "✗ Not configured"
            self.stdout.write(f"Master Key: {master_key_status}")
            
            # Get clinic filter
            clinics = Clinic.objects.all()
            if options['clinic_id']:
                clinics = clinics.filter(id=options['clinic_id'])
            
            results = []
            
            for clinic in clinics:
                stats = encryption_service.get_encryption_stats(clinic.id)
                
                if options['output_format'] == 'json':
                    results.append({
                        'clinic_id': clinic.id,
                        'clinic_name': clinic.name,
                        **stats
                    })
                else:
                    self.stdout.write(f"\nClinic: {clinic.name} (ID: {clinic.id})")
                    self.stdout.write(f"  Total Documents: {stats['total_documents']}")
                    self.stdout.write(f"  Encrypted: {stats['encrypted_documents']}")
                    self.stdout.write(f"  Unencrypted: {stats['unencrypted_documents']}")
                    
                    if stats['total_documents'] > 0:
                        percentage = stats['encryption_percentage']
                        color = self.style.SUCCESS if percentage == 100 else self.style.WARNING if percentage >= 50 else self.style.ERROR
                        self.stdout.write(f"  Encryption Rate: {color(f'{percentage}%')}")
            
            if options['output_format'] == 'json':
                self.stdout.write(json.dumps(results, indent=2))
                
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"Error getting encryption status: {str(e)}"))

    def encrypt_clinic_files(self, options):
        """Encrypt files for a specific clinic."""
        clinic_id = options.get('clinic_id')
        if not clinic_id:
            raise CommandError("--clinic-id is required for encrypt-clinic action")
        
        try:
            clinic = Clinic.objects.get(id=clinic_id)
        except Clinic.DoesNotExist:
            raise CommandError(f"Clinic with ID {clinic_id} not found")
        
        self.stdout.write(f"Encrypting files for clinic: {clinic.name}")
        
        try:
            encryption_service = EncryptionService()
            
            # Get documents to encrypt
            if options['force']:
                documents = ClinicalDocument.objects.filter(
                    clinical_record__clinic_id=clinic_id
                )
            else:
                documents = ClinicalDocument.objects.filter(
                    clinical_record__clinic_id=clinic_id,
                    is_encrypted=False
                )
            
            total_docs = documents.count()
            if total_docs == 0:
                self.stdout.write("No documents to encrypt.")
                return
            
            self.stdout.write(f"Found {total_docs} documents to encrypt...")
            
            processed = 0
            errors = 0
            
            for document in documents:
                try:
                    if document.file and document.file.path:
                        # Encrypt the file
                        metadata = encryption_service.encrypt_file(
                            document.file.path,
                            clinic_id
                        )
                        
                        # Update document record
                        document.is_encrypted = True
                        document.metadata.update({
                            'encryption': metadata
                        })
                        document.save(update_fields=['is_encrypted', 'metadata'])
                        
                        processed += 1
                        
                        if processed % 10 == 0:
                            self.stdout.write(f"Processed {processed}/{total_docs} documents...")
                            
                except Exception as e:
                    errors += 1
                    self.stdout.write(
                        self.style.ERROR(f"Error encrypting {document.original_filename}: {str(e)}")
                    )
            
            self.stdout.write(
                self.style.SUCCESS(f"Encryption completed: {processed} processed, {errors} errors")
            )
            
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"Error encrypting clinic files: {str(e)}"))

    def encrypt_all_files(self, options):
        """Encrypt files for all clinics."""
        self.stdout.write("Encrypting files for all clinics...")
        
        clinics = Clinic.objects.all()
        total_clinics = clinics.count()
        
        for i, clinic in enumerate(clinics, 1):
            self.stdout.write(f"\n[{i}/{total_clinics}] Processing clinic: {clinic.name}")
            
            # Set clinic_id for encrypt_clinic_files
            clinic_options = options.copy()
            clinic_options['clinic_id'] = clinic.id
            
            self.encrypt_clinic_files(clinic_options)

    def rotate_encryption_keys(self, options):
        """Rotate encryption keys for a clinic."""
        clinic_id = options.get('clinic_id')
        if not clinic_id:
            raise CommandError("--clinic-id is required for rotate-keys action")
        
        try:
            clinic = Clinic.objects.get(id=clinic_id)
        except Clinic.DoesNotExist:
            raise CommandError(f"Clinic with ID {clinic_id} not found")
        
        self.stdout.write(f"Rotating encryption keys for clinic: {clinic.name}")
        self.stdout.write("This will re-encrypt all files with new keys...")
        
        # Confirm operation
        confirm = input("Are you sure you want to proceed? (yes/no): ")
        if confirm.lower() != 'yes':
            self.stdout.write("Key rotation cancelled.")
            return
        
        try:
            results = rotate_tenant_keys(clinic_id)
            
            self.stdout.write(f"Key rotation completed:")
            self.stdout.write(f"  Processed: {results['processed']}")
            self.stdout.write(f"  Errors: {results['errors']}")
            
            if results['errors'] > 0:
                self.stdout.write("Error details:")
                for error in results['error_details']:
                    self.stdout.write(f"  - Document {error['document_id']}: {error['error']}")
                    
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"Error rotating keys: {str(e)}"))

    def verify_encryption_integrity(self, options):
        """Verify encryption integrity for clinic files."""
        clinic_id = options.get('clinic_id')
        
        if clinic_id:
            try:
                clinic = Clinic.objects.get(id=clinic_id)
                clinics = [clinic]
            except Clinic.DoesNotExist:
                raise CommandError(f"Clinic with ID {clinic_id} not found")
        else:
            clinics = Clinic.objects.all()
        
        self.stdout.write("Verifying encryption integrity...")
        
        encryption_service = EncryptionService()
        total_verified = 0
        total_failed = 0
        
        for clinic in clinics:
            self.stdout.write(f"\nVerifying clinic: {clinic.name}")
            
            # Get encrypted documents with file hashes
            documents = ClinicalDocument.objects.filter(
                clinical_record__clinic_id=clinic.id,
                is_encrypted=True
            ).exclude(file_hash='')
            
            clinic_verified = 0
            clinic_failed = 0
            
            for document in documents:
                try:
                    if document.file and document.file.path and document.file_hash:
                        is_valid = encryption_service.verify_file_integrity(
                            document.file.path,
                            clinic.id,
                            document.file_hash
                        )
                        
                        if is_valid:
                            clinic_verified += 1
                        else:
                            clinic_failed += 1
                            self.stdout.write(
                                self.style.ERROR(f"  ✗ {document.original_filename}: Integrity check failed")
                            )
                            
                except Exception as e:
                    clinic_failed += 1
                    self.stdout.write(
                        self.style.ERROR(f"  ✗ {document.original_filename}: {str(e)}")
                    )
            
            self.stdout.write(f"  Verified: {clinic_verified}, Failed: {clinic_failed}")
            total_verified += clinic_verified
            total_failed += clinic_failed
        
        self.stdout.write(f"\nTotal verified: {total_verified}, Total failed: {total_failed}")

    def generate_master_key(self, options):
        """Generate a new master encryption key."""
        self.stdout.write("Generating new master encryption key...")
        
        try:
            master_key = generate_master_key()
            
            self.stdout.write(self.style.SUCCESS("Master key generated successfully!"))
            self.stdout.write("\nAdd this to your settings:")
            self.stdout.write(f"CLINICAL_RECORDS_MASTER_KEY = '{master_key}'")
            self.stdout.write("\nIMPORTANT: Store this key securely and never commit it to version control!")
            
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"Error generating master key: {str(e)}"))

    def perform_health_check(self, options):
        """Perform encryption system health check."""
        self.stdout.write("Performing encryption system health check...")
        
        try:
            encryption_service = EncryptionService()
            
            # Check master key
            if encryption_service.master_key:
                self.stdout.write("✓ Master key configured")
            else:
                self.stdout.write("✗ Master key not configured")
                return
            
            # Test key derivation
            try:
                test_key, test_salt = encryption_service.derive_tenant_key(1)
                self.stdout.write("✓ Key derivation working")
            except Exception as e:
                self.stdout.write(f"✗ Key derivation failed: {str(e)}")
                return
            
            # Test encryption/decryption
            try:
                import tempfile
                test_data = b'test encryption data'
                
                with tempfile.NamedTemporaryFile(delete=False) as temp_file:
                    temp_file.write(test_data)
                    temp_path = temp_file.name
                
                try:
                    # Test encryption
                    metadata = encryption_service.encrypt_file(temp_path, 1)
                    
                    # Test decryption
                    decrypted_data = encryption_service.decrypt_file(temp_path, 1)
                    
                    if decrypted_data == test_data:
                        self.stdout.write("✓ Encryption/decryption working")
                    else:
                        self.stdout.write("✗ Encryption/decryption data mismatch")
                        
                finally:
                    # Clean up
                    try:
                        os.unlink(temp_path)
                    except:
                        pass
                        
            except Exception as e:
                self.stdout.write(f"✗ Encryption/decryption test failed: {str(e)}")
                return
            
            self.stdout.write(self.style.SUCCESS("All encryption system checks passed!"))
            
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"Health check failed: {str(e)}"))