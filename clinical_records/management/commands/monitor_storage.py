"""
Django management command to monitor file storage usage and health.
"""

import os
import time
import json
from pathlib import Path
from django.core.management.base import BaseCommand
from django.conf import settings
from django.core.mail import send_mail
from clinical_records.storage.secure_file_handler import FileStorageMonitor

class Command(BaseCommand):
    help = 'Monitor file storage usage and send alerts'
    
    def add_arguments(self, parser):
        parser.add_argument(
            '--check-disk-space',
            action='store_true',
            help='Check disk space usage'
        )
        parser.add_argument(
            '--cleanup-temp',
            action='store_true',
            help='Clean up temporary files'
        )
        parser.add_argument(
            '--temp-file-age',
            type=int,
            default=7,
            help='Age in days for temp file cleanup (default: 7)'
        )
        parser.add_argument(
            '--report',
            action='store_true',
            help='Generate storage usage report'
        )
        parser.add_argument(
            '--json-output',
            action='store_true',
            help='Output results in JSON format'
        )
        parser.add_argument(
            '--send-alerts',
            action='store_true',
            help='Send email alerts if thresholds are exceeded'
        )
    
    def handle(self, *args, **options):
        monitor = FileStorageMonitor()
        results = {}
        
        try:
            # Check disk space
            if options['check_disk_space'] or options['report']:
                disk_info = monitor.check_disk_space()
                if disk_info:
                    results['disk_space'] = disk_info
                    
                    if not options['json_output']:
                        self.stdout.write(
                            f"Disk Usage: {disk_info['usage_percent']:.1f}% "
                            f"({disk_info['used_space_gb']:.1f}GB / {disk_info['total_space_gb']:.1f}GB)"
                        )
            
            # Clean up temporary files
            if options['cleanup_temp']:
                cleaned_count = monitor.cleanup_temp_files(options['temp_file_age'])
                results['cleanup'] = {
                    'files_cleaned': cleaned_count,
                    'age_days': options['temp_file_age']
                }
                
                if not options['json_output']:
                    self.stdout.write(f"Cleaned up {cleaned_count} temporary files")
            
            # Generate detailed report
            if options['report']:
                report = self._generate_detailed_report()
                results['detailed_report'] = report
                
                if not options['json_output']:
                    self._print_detailed_report(report)
            
            # Output results
            if options['json_output']:
                self.stdout.write(json.dumps(results, indent=2))
            
            # Send alerts if requested and thresholds exceeded
            if options['send_alerts'] and 'disk_space' in results:
                self._check_and_send_alerts(results['disk_space'])
            
        except Exception as e:
            if options['json_output']:
                self.stdout.write(json.dumps({'error': str(e)}))
            else:
                self.stdout.write(self.style.ERROR(f"Error monitoring storage: {str(e)}"))
    
    def _generate_detailed_report(self):
        """Generate detailed storage usage report."""
        media_root = Path(settings.MEDIA_ROOT)
        report = {
            'timestamp': time.strftime('%Y-%m-%d %H:%M:%S'),
            'media_root': str(media_root),
            'directories': {}
        }
        
        # Analyze each subdirectory
        subdirs = [
            'clinical_records',
            'clinical_records/documents',
            'clinical_records/thumbnails',
            'clinical_records/previews',
            'clinical_records/temp',
            'clinical_records/backups',
            'clinic_logos',
            'doctor_profiles',
            'prescriptions',
            'lab_reports'
        ]
        
        for subdir in subdirs:
            dir_path = media_root / subdir
            if dir_path.exists():
                dir_info = self._analyze_directory(dir_path)
                report['directories'][subdir] = dir_info
        
        return report
    
    def _analyze_directory(self, dir_path):
        """Analyze a directory for size and file count."""
        total_size = 0
        file_count = 0
        file_types = {}
        
        try:
            for item in dir_path.rglob('*'):
                if item.is_file():
                    file_size = item.stat().st_size
                    total_size += file_size
                    file_count += 1
                    
                    # Track file types
                    suffix = item.suffix.lower()
                    if suffix in file_types:
                        file_types[suffix]['count'] += 1
                        file_types[suffix]['size'] += file_size
                    else:
                        file_types[suffix] = {'count': 1, 'size': file_size}
            
            return {
                'total_size_mb': total_size / (1024 * 1024),
                'file_count': file_count,
                'file_types': file_types,
                'readable': os.access(dir_path, os.R_OK),
                'writable': os.access(dir_path, os.W_OK)
            }
            
        except Exception as e:
            return {
                'error': str(e),
                'readable': False,
                'writable': False
            }
    
    def _print_detailed_report(self, report):
        """Print detailed report to stdout."""
        self.stdout.write(f"\n=== Storage Usage Report ===")
        self.stdout.write(f"Generated: {report['timestamp']}")
        self.stdout.write(f"Media Root: {report['media_root']}")
        self.stdout.write("")
        
        for dir_name, dir_info in report['directories'].items():
            if 'error' in dir_info:
                self.stdout.write(f"{dir_name}: ERROR - {dir_info['error']}")
                continue
            
            self.stdout.write(f"{dir_name}:")
            self.stdout.write(f"  Size: {dir_info['total_size_mb']:.1f} MB")
            self.stdout.write(f"  Files: {dir_info['file_count']}")
            self.stdout.write(f"  Readable: {dir_info['readable']}")
            self.stdout.write(f"  Writable: {dir_info['writable']}")
            
            if dir_info['file_types']:
                self.stdout.write("  File Types:")
                for ext, info in dir_info['file_types'].items():
                    ext_name = ext if ext else 'no extension'
                    self.stdout.write(f"    {ext_name}: {info['count']} files, {info['size'] / (1024*1024):.1f} MB")
            
            self.stdout.write("")
    
    def _check_and_send_alerts(self, disk_info):
        """Check disk usage and send alerts if necessary."""
        warning_threshold = getattr(settings, 'DISK_SPACE_WARNING_THRESHOLD', 80)
        critical_threshold = getattr(settings, 'DISK_SPACE_CRITICAL_THRESHOLD', 90)
        
        usage_percent = disk_info['usage_percent']
        
        if usage_percent >= critical_threshold:
            self._send_alert('CRITICAL', disk_info)
        elif usage_percent >= warning_threshold:
            self._send_alert('WARNING', disk_info)
    
    def _send_alert(self, level, disk_info):
        """Send storage alert email."""
        try:
            subject = f"RxDoctor Storage {level} Alert"
            message = f"""
Storage usage has reached {level.lower()} threshold.

Current usage: {disk_info['usage_percent']:.1f}%
Used space: {disk_info['used_space_gb']:.1f} GB
Total space: {disk_info['total_space_gb']:.1f} GB
Free space: {disk_info['free_space_gb']:.1f} GB

Please take action to free up storage space.

Server: {os.uname().nodename}
Media Root: {settings.MEDIA_ROOT}
Time: {time.strftime('%Y-%m-%d %H:%M:%S')}

Recommended actions:
1. Clean up temporary files
2. Archive old clinical records
3. Check for duplicate files
4. Consider expanding storage capacity
            """
            
            admin_email = getattr(settings, 'ADMIN_EMAIL', 'admin@rxdoctor.com')
            
            send_mail(
                subject,
                message,
                settings.DEFAULT_FROM_EMAIL,
                [admin_email],
                fail_silently=False
            )
            
            self.stdout.write(f"Storage {level} alert sent to {admin_email}")
            
        except Exception as e:
            self.stdout.write(
                self.style.ERROR(f"Error sending storage alert: {str(e)}")
            )