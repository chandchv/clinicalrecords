"""
Django management command to set up production file storage.
"""

import os
import stat
import shutil
from pathlib import Path
from django.core.management.base import BaseCommand, CommandError
from django.conf import settings
from django.contrib.auth import get_user_model

User = get_user_model()

class Command(BaseCommand):
    help = 'Set up production file storage with proper permissions and directory structure'
    
    def add_arguments(self, parser):
        parser.add_argument(
            '--media-root',
            type=str,
            default=getattr(settings, 'PRODUCTION_MEDIA_ROOT', '/var/www/rxdoctor/media'),
            help='Production media root directory'
        )
        parser.add_argument(
            '--owner',
            type=str,
            default='www-data',
            help='File owner (default: www-data)'
        )
        parser.add_argument(
            '--group',
            type=str,
            default='www-data',
            help='File group (default: www-data)'
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be done without making changes'
        )
        parser.add_argument(
            '--force',
            action='store_true',
            help='Force creation even if directories exist'
        )
    
    def handle(self, *args, **options):
        media_root = Path(options['media_root'])
        owner = options['owner']
        group = options['group']
        dry_run = options['dry_run']
        force = options['force']
        
        self.stdout.write(f"Setting up production storage at: {media_root}")
        
        if dry_run:
            self.stdout.write(self.style.WARNING("DRY RUN MODE - No changes will be made"))
        
        try:
            # Create directory structure
            self._create_directory_structure(media_root, dry_run, force)
            
            # Set permissions
            self._set_permissions(media_root, owner, group, dry_run)
            
            # Create security files
            self._create_security_files(media_root, dry_run)
            
            # Create log directories
            self._create_log_directories(dry_run)
            
            # Create backup directories
            self._create_backup_directories(dry_run)
            
            # Validate setup
            self._validate_setup(media_root)
            
            self.stdout.write(
                self.style.SUCCESS(
                    f"Production storage setup completed successfully at {media_root}"
                )
            )
            
        except Exception as e:
            raise CommandError(f"Error setting up production storage: {str(e)}")
    
    def _create_directory_structure(self, media_root, dry_run, force):
        """Create the required directory structure."""
        directories = [
            'clinical_records',
            'clinical_records/documents',
            'clinical_records/thumbnails',
            'clinical_records/previews',
            'clinical_records/temp',
            'clinical_records/backups',
            'clinical_records/encrypted',
            'clinic_logos',
            'doctor_profiles',
            'prescriptions',
            'lab_reports',
            'patient_documents',
            'uploads/temp'
        ]
        
        for directory in directories:
            dir_path = media_root / directory
            
            if dir_path.exists() and not force:
                self.stdout.write(f"Directory already exists: {dir_path}")
                continue
            
            if dry_run:
                self.stdout.write(f"Would create directory: {dir_path}")
            else:
                dir_path.mkdir(parents=True, exist_ok=True, mode=0o755)
                self.stdout.write(f"Created directory: {dir_path}")
    
    def _set_permissions(self, media_root, owner, group, dry_run):
        """Set proper file and directory permissions."""
        if dry_run:
            self.stdout.write(f"Would set ownership to {owner}:{group}")
            self.stdout.write("Would set directory permissions to 755")
            self.stdout.write("Would set file permissions to 644")
            return
        
        try:
            # Set ownership recursively
            for root, dirs, files in os.walk(media_root):
                # Set directory permissions
                os.chmod(root, 0o755)
                
                # Set file permissions
                for file in files:
                    file_path = os.path.join(root, file)
                    os.chmod(file_path, 0o644)
            
            # Try to set ownership (requires appropriate privileges)
            try:
                shutil.chown(media_root, owner, group)
                for root, dirs, files in os.walk(media_root):
                    shutil.chown(root, owner, group)
                    for file in files:
                        file_path = os.path.join(root, file)
                        shutil.chown(file_path, owner, group)
                
                self.stdout.write(f"Set ownership to {owner}:{group}")
            except PermissionError:
                self.stdout.write(
                    self.style.WARNING(
                        f"Could not set ownership to {owner}:{group} - insufficient privileges"
                    )
                )
            
            self.stdout.write("Set file and directory permissions")
            
        except Exception as e:
            self.stdout.write(
                self.style.ERROR(f"Error setting permissions: {str(e)}")
            )
    
    def _create_security_files(self, media_root, dry_run):
        """Create security files (.htaccess, etc.)."""
        # Apache .htaccess files
        htaccess_content = """# Secure file access
Options -Indexes
<Files "*.py">
    Require all denied
</Files>
<Files "*.pyc">
    Require all denied
</Files>
<Files "*.pyo">
    Require all denied
</Files>
<Files "*.db">
    Require all denied
</Files>
<Files "*.sqlite*">
    Require all denied
</Files>
"""
        
        # Nginx security file
        nginx_security_content = """# Nginx security configuration
location ~ \\.py$ {
    deny all;
}
location ~ \\.pyc$ {
    deny all;
}
location ~ \\.pyo$ {
    deny all;
}
location ~ \\.db$ {
    deny all;
}
location ~ \\.sqlite {
    deny all;
}
"""
        
        security_dirs = [
            'clinical_records',
            'clinical_records/documents',
            'clinical_records/thumbnails',
            'clinical_records/previews',
            'clinical_records/temp',
            'clinical_records/backups'
        ]
        
        for directory in security_dirs:
            dir_path = media_root / directory
            
            # Create .htaccess for Apache
            htaccess_path = dir_path / '.htaccess'
            if dry_run:
                self.stdout.write(f"Would create .htaccess: {htaccess_path}")
            else:
                with open(htaccess_path, 'w') as f:
                    f.write(htaccess_content)
                os.chmod(htaccess_path, 0o644)
                self.stdout.write(f"Created .htaccess: {htaccess_path}")
            
            # Create nginx security file
            nginx_path = dir_path / '.nginx-security'
            if dry_run:
                self.stdout.write(f"Would create nginx security file: {nginx_path}")
            else:
                with open(nginx_path, 'w') as f:
                    f.write(nginx_security_content)
                os.chmod(nginx_path, 0o644)
                self.stdout.write(f"Created nginx security file: {nginx_path}")
    
    def _create_log_directories(self, dry_run):
        """Create log directories."""
        log_dirs = [
            '/var/log/rxdoctor',
            '/var/log/rxdoctor/clinical_records',
            '/var/log/rxdoctor/file_access'
        ]
        
        for log_dir in log_dirs:
            log_path = Path(log_dir)
            
            if dry_run:
                self.stdout.write(f"Would create log directory: {log_path}")
            else:
                try:
                    log_path.mkdir(parents=True, exist_ok=True, mode=0o755)
                    self.stdout.write(f"Created log directory: {log_path}")
                except PermissionError:
                    self.stdout.write(
                        self.style.WARNING(
                            f"Could not create log directory {log_path} - insufficient privileges"
                        )
                    )
    
    def _create_backup_directories(self, dry_run):
        """Create backup directories."""
        backup_dirs = [
            '/var/backups/rxdoctor',
            '/var/backups/rxdoctor/media',
            '/var/backups/rxdoctor/database'
        ]
        
        for backup_dir in backup_dirs:
            backup_path = Path(backup_dir)
            
            if dry_run:
                self.stdout.write(f"Would create backup directory: {backup_path}")
            else:
                try:
                    backup_path.mkdir(parents=True, exist_ok=True, mode=0o750)
                    self.stdout.write(f"Created backup directory: {backup_path}")
                except PermissionError:
                    self.stdout.write(
                        self.style.WARNING(
                            f"Could not create backup directory {backup_path} - insufficient privileges"
                        )
                    )
    
    def _validate_setup(self, media_root):
        """Validate the setup."""
        self.stdout.write("Validating setup...")
        
        # Check if directories exist and are writable
        test_dirs = [
            'clinical_records/documents',
            'clinical_records/temp',
            'uploads/temp'
        ]
        
        for test_dir in test_dirs:
            dir_path = media_root / test_dir
            
            if not dir_path.exists():
                raise CommandError(f"Directory not created: {dir_path}")
            
            if not os.access(dir_path, os.W_OK):
                self.stdout.write(
                    self.style.WARNING(f"Directory not writable: {dir_path}")
                )
            else:
                self.stdout.write(f"✓ Directory writable: {dir_path}")
        
        # Test file creation
        test_file = media_root / 'clinical_records' / 'temp' / 'test_write.txt'
        try:
            with open(test_file, 'w') as f:
                f.write('test')
            test_file.unlink()
            self.stdout.write("✓ File write test passed")
        except Exception as e:
            self.stdout.write(
                self.style.WARNING(f"File write test failed: {str(e)}")
            )
        
        self.stdout.write("Setup validation completed")