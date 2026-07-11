"""
Management command to manage SFTP monitors

This command allows starting, stopping, and managing SFTP monitors
for clinical record ingestion.
"""
import json
import logging
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from users.models import Clinic
from clinical_records.services.sftp_ingestion_service import sftp_ingestion_service, SFTPIngestionError

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Manage SFTP monitors for clinical record ingestion'
    
    def add_arguments(self, parser):
        subparsers = parser.add_subparsers(dest='action', help='Action to perform')
        
        # Start monitor
        start_parser = subparsers.add_parser('start', help='Start SFTP monitoring')
        start_parser.add_argument(
            '--clinic-id',
            type=str,
            required=True,
            help='ID of the clinic to monitor for'
        )
        start_parser.add_argument(
            '--monitor-directory',
            type=str,
            required=True,
            help='Directory to monitor for files'
        )
        start_parser.add_argument(
            '--connection-type',
            type=str,
            choices=['local', 'remote'],
            default='local',
            help='Connection type (local or remote)'
        )
        start_parser.add_argument(
            '--host',
            type=str,
            help='SFTP host (required for remote connections)'
        )
        start_parser.add_argument(
            '--username',
            type=str,
            help='SFTP username (required for remote connections)'
        )
        start_parser.add_argument(
            '--password',
            type=str,
            help='SFTP password (optional for remote connections)'
        )
        start_parser.add_argument(
            '--key-file',
            type=str,
            help='SSH key file path (optional for remote connections)'
        )
        start_parser.add_argument(
            '--port',
            type=int,
            default=22,
            help='SFTP port (default: 22)'
        )
        start_parser.add_argument(
            '--check-interval',
            type=int,
            default=60,
            help='Check interval in seconds (default: 60)'
        )
        start_parser.add_argument(
            '--move-processed',
            action='store_true',
            help='Move processed files to processed directory'
        )
        start_parser.add_argument(
            '--move-failed',
            action='store_true',
            help='Move failed files to failed directory'
        )
        start_parser.add_argument(
            '--processed-directory',
            type=str,
            default='processed',
            help='Directory for processed files (default: processed)'
        )
        start_parser.add_argument(
            '--failed-directory',
            type=str,
            default='failed',
            help='Directory for failed files (default: failed)'
        )
        
        # Stop monitor
        stop_parser = subparsers.add_parser('stop', help='Stop SFTP monitoring')
        stop_parser.add_argument(
            '--monitor-id',
            type=str,
            required=True,
            help='ID of the monitor to stop'
        )
        
        # List monitors
        list_parser = subparsers.add_parser('list', help='List active monitors')
        list_parser.add_argument(
            '--clinic-id',
            type=str,
            help='Filter by clinic ID (optional)'
        )
        
        # Status
        status_parser = subparsers.add_parser('status', help='Get monitor status')
        status_parser.add_argument(
            '--monitor-id',
            type=str,
            required=True,
            help='ID of the monitor to check'
        )
        
        # Process file
        process_parser = subparsers.add_parser('process-file', help='Process a single file')
        process_parser.add_argument(
            '--file-path',
            type=str,
            required=True,
            help='Path to file to process'
        )
        process_parser.add_argument(
            '--clinic-id',
            type=str,
            required=True,
            help='ID of the clinic to process for'
        )
        
        # Statistics
        stats_parser = subparsers.add_parser('stats', help='Get processing statistics')
        stats_parser.add_argument(
            '--clinic-id',
            type=str,
            required=True,
            help='ID of the clinic to get stats for'
        )
        stats_parser.add_argument(
            '--days',
            type=int,
            default=30,
            help='Number of days to look back (default: 30)'
        )
    
    def handle(self, *args, **options):
        action = options['action']
        
        if not action:
            self.print_help('manage.py', 'manage_sftp_monitors')
            return
        
        try:
            if action == 'start':
                self.handle_start(options)
            elif action == 'stop':
                self.handle_stop(options)
            elif action == 'list':
                self.handle_list(options)
            elif action == 'status':
                self.handle_status(options)
            elif action == 'process-file':
                self.handle_process_file(options)
            elif action == 'stats':
                self.handle_stats(options)
            else:
                raise CommandError(f"Unknown action: {action}")
                
        except Exception as e:
            raise CommandError(f"Command failed: {e}")
    
    def handle_start(self, options):
        """Handle start monitor command"""
        clinic_id = options['clinic_id']
        
        # Get clinic
        try:
            clinic = Clinic.objects.get(id=clinic_id)
        except Clinic.DoesNotExist:
            raise CommandError(f"Clinic not found: {clinic_id}")
        
        # Build configuration
        config = {
            'monitor_directory': options['monitor_directory'],
            'connection_type': options['connection_type'],
            'check_interval': options['check_interval'],
            'move_processed_files': options['move_processed'],
            'move_failed_files': options['move_failed'],
            'processed_directory': options['processed_directory'],
            'failed_directory': options['failed_directory']
        }
        
        # Add remote connection parameters if needed
        if options['connection_type'] == 'remote':
            if not options['host'] or not options['username']:
                raise CommandError("Host and username are required for remote connections")
            
            config.update({
                'host': options['host'],
                'username': options['username'],
                'port': options['port']
            })
            
            if options['password']:
                config['password'] = options['password']
            if options['key_file']:
                config['key_file'] = options['key_file']
        
        try:
            monitor_id = sftp_ingestion_service.start_monitoring(clinic, config)
            
            self.stdout.write(
                self.style.SUCCESS(f"✓ Started SFTP monitoring")
            )
            self.stdout.write(f"Monitor ID: {monitor_id}")
            self.stdout.write(f"Clinic: {clinic.name}")
            self.stdout.write(f"Directory: {config['monitor_directory']}")
            self.stdout.write(f"Connection Type: {config['connection_type']}")
            self.stdout.write(f"Check Interval: {config['check_interval']} seconds")
            
        except SFTPIngestionError as e:
            raise CommandError(f"Failed to start monitoring: {e}")
    
    def handle_stop(self, options):
        """Handle stop monitor command"""
        monitor_id = options['monitor_id']
        
        try:
            sftp_ingestion_service.stop_monitoring(monitor_id)
            
            self.stdout.write(
                self.style.SUCCESS(f"✓ Stopped SFTP monitoring for {monitor_id}")
            )
            
        except SFTPIngestionError as e:
            raise CommandError(f"Failed to stop monitoring: {e}")
    
    def handle_list(self, options):
        """Handle list monitors command"""
        clinic_id = options.get('clinic_id')
        
        monitors = sftp_ingestion_service.list_active_monitors()
        
        # Filter by clinic if specified
        if clinic_id:
            monitors = [m for m in monitors if m['clinic_id'] == clinic_id]
        
        if not monitors:
            self.stdout.write(
                self.style.WARNING("No active monitors found")
            )
            return
        
        self.stdout.write(f"Found {len(monitors)} active monitor(s):")
        self.stdout.write("")
        
        for monitor in monitors:
            self.stdout.write(f"Monitor ID: {monitor['monitor_id']}")
            self.stdout.write(f"  Clinic ID: {monitor['clinic_id']}")
            self.stdout.write(f"  Directory: {monitor['monitor_directory']}")
            self.stdout.write(f"  Connection: {monitor['connection_type']}")
            self.stdout.write(f"  Status: {monitor['status']}")
            if monitor['last_check']:
                self.stdout.write(f"  Last Check: {monitor['last_check']}")
            self.stdout.write("")
    
    def handle_status(self, options):
        """Handle status command"""
        monitor_id = options['monitor_id']
        
        status_info = sftp_ingestion_service.get_monitor_status(monitor_id)
        
        if status_info['status'] == 'not_found':
            self.stdout.write(
                self.style.ERROR(f"Monitor not found: {monitor_id}")
            )
            return
        
        self.stdout.write(f"Monitor Status: {monitor_id}")
        self.stdout.write(f"  Status: {status_info['status']}")
        
        if 'config' in status_info:
            config = status_info['config']
            self.stdout.write(f"  Directory: {config['monitor_directory']}")
            self.stdout.write(f"  Connection: {config['connection_type']}")
            self.stdout.write(f"  Check Interval: {config['check_interval']} seconds")
        
        if status_info.get('last_check'):
            self.stdout.write(f"  Last Check: {status_info['last_check']}")
    
    def handle_process_file(self, options):
        """Handle process file command"""
        file_path = options['file_path']
        clinic_id = options['clinic_id']
        
        # Get clinic
        try:
            clinic = Clinic.objects.get(id=clinic_id)
        except Clinic.DoesNotExist:
            raise CommandError(f"Clinic not found: {clinic_id}")
        
        self.stdout.write(f"Processing file: {file_path}")
        
        try:
            result = sftp_ingestion_service.process_single_file(
                file_path=file_path,
                clinic=clinic,
                processing_user=None
            )
            
            if result['success']:
                self.stdout.write(
                    self.style.SUCCESS("✓ File processed successfully")
                )
                
                if result['patient_match']:
                    patient = result['patient_match']
                    self.stdout.write(f"Patient: {patient['name']} ({patient['id']})")
                
                if result['document_created']:
                    doc = result['document_created']
                    self.stdout.write(f"Record Type: {doc['record_type']}")
                    self.stdout.write(f"Clinical Record ID: {doc['clinical_record_id']}")
                    self.stdout.write(f"Document ID: {doc['document_id']}")
            else:
                self.stdout.write(
                    self.style.ERROR("✗ File processing failed")
                )
                for error in result.get('errors', []):
                    self.stdout.write(f"  Error: {error}")
                
        except SFTPIngestionError as e:
            raise CommandError(f"Failed to process file: {e}")
    
    def handle_stats(self, options):
        """Handle statistics command"""
        clinic_id = options['clinic_id']
        days = options['days']
        
        # Get clinic
        try:
            clinic = Clinic.objects.get(id=clinic_id)
        except Clinic.DoesNotExist:
            raise CommandError(f"Clinic not found: {clinic_id}")
        
        stats = sftp_ingestion_service.get_processing_statistics(clinic, days)
        
        self.stdout.write(f"SFTP Processing Statistics ({days} days)")
        self.stdout.write("=" * 40)
        self.stdout.write(f"Files Processed: {stats['files_processed']}")
        self.stdout.write(f"Files Unmatched: {stats['files_unmatched']}")
        self.stdout.write(f"Files Unparseable: {stats['files_unparseable']}")
        self.stdout.write(f"Total Files: {stats['total_files']}")
        self.stdout.write(f"Success Rate: {stats['success_rate']:.1f}%")
        self.stdout.write(f"Documents Created: {stats['documents_created']}")
        
        if stats['document_types']:
            self.stdout.write("\nDocument Types:")
            for doc_type, count in stats['document_types'].items():
                self.stdout.write(f"  {doc_type}: {count}")
        
        self.stdout.write("")