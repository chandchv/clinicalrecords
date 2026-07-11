"""
Django management command to sync users from RxBackend
"""
from django.core.management.base import BaseCommand
from clinical_records.user_sync import UserSyncService


class Command(BaseCommand):
    """
    Django management command for user synchronization
    """
    help = 'Synchronize users from RxBackend to Clinical Records Service'
    
    def add_arguments(self, parser):
        parser.add_argument(
            '--all',
            action='store_true',
            help='Sync all users',
        )
        parser.add_argument(
            '--patients',
            action='store_true',
            help='Sync only patient users',
        )
        parser.add_argument(
            '--user-id',
            type=int,
            help='Sync specific user by ID',
        )
        parser.add_argument(
            '--token',
            type=str,
            help='Admin token for RxBackend API',
        )
        parser.add_argument(
            '--status',
            action='store_true',
            help='Show sync status',
        )
    
    def handle(self, *args, **options):
        sync_service = UserSyncService()
        
        if options['status']:
            status = sync_service.get_sync_status()
            self.stdout.write("User Sync Status:")
            self.stdout.write(f"  Sync Enabled: {status.get('sync_enabled', False)}")
            self.stdout.write(f"  Total Synced Users: {status.get('total_synced_users', 0)}")
            self.stdout.write(f"  Active Synced Users: {status.get('active_synced_users', 0)}")
            self.stdout.write(f"  RxBackend URL: {status.get('rxbackend_url', 'N/A')}")
            if 'error' in status:
                self.stdout.write(self.style.ERROR(f"  Error: {status['error']}"))
            return
        
        if options['user_id']:
            result = sync_service.sync_single_user(
                options['user_id'],
                options.get('token')
            )
        elif options['patients']:
            result = sync_service.sync_patient_users(options.get('token'))
        elif options['all']:
            result = sync_service.sync_all_users(options.get('token'))
        else:
            self.stdout.write(
                self.style.ERROR('Please specify --all, --patients, --user-id, or --status')
            )
            return
        
        if result['success']:
            self.stdout.write(
                self.style.SUCCESS(result['message'])
            )
        else:
            self.stdout.write(
                self.style.ERROR(result['message'])
            )