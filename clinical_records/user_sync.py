"""
User Synchronization Service for Clinical Records Service
Syncs patient login details from RxBackend to Clinical Records
"""
import requests
import logging
from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.utils import timezone
from datetime import timedelta
import json

logger = logging.getLogger(__name__)
User = get_user_model()


class UserSyncService:
    """
    Service to synchronize users between RxBackend and Clinical Records Service
    """
    
    def __init__(self):
        self.rxbackend_url = settings.RXBACKEND_SERVICE_URL
        self.timeout = settings.RXBACKEND_API_TIMEOUT
        self.batch_size = getattr(settings, 'USER_SYNC_BATCH_SIZE', 100)
        self.sync_enabled = getattr(settings, 'USER_SYNC_ENABLED', True)
    
    def sync_all_users(self, admin_token=None):
        """
        Sync all users from RxBackend
        """
        if not self.sync_enabled:
            logger.info("User sync is disabled")
            return {'success': False, 'message': 'User sync is disabled'}
        
        logger.info("Starting full user synchronization from RxBackend")
        
        try:
            headers = self._get_headers(admin_token)
            synced_count = 0
            page = 1
            
            while True:
                # Fetch users page by page
                response = requests.get(
                    f"{self.rxbackend_url}/api/users/",
                    headers=headers,
                    params={
                        'page': page,
                        'page_size': self.batch_size
                    },
                    timeout=self.timeout
                )
                
                if response.status_code != 200:
                    logger.error(f"Failed to fetch users from RxBackend: {response.status_code}")
                    break
                
                data = response.json()
                users = data.get('results', [])
                
                if not users:
                    break
                
                # Sync users in this batch
                for user_data in users:
                    if self._sync_user(user_data):
                        synced_count += 1
                
                # Check if there are more pages
                if not data.get('next'):
                    break
                
                page += 1
            
            logger.info(f"Synchronized {synced_count} users from RxBackend")
            return {
                'success': True,
                'synced_count': synced_count,
                'message': f'Successfully synchronized {synced_count} users'
            }
            
        except requests.RequestException as e:
            logger.error(f"Network error during user sync: {e}")
            return {'success': False, 'message': f'Network error: {e}'}
        except Exception as e:
            logger.error(f"Error during user sync: {e}")
            return {'success': False, 'message': f'Sync error: {e}'}
    
    def sync_patient_users(self, admin_token=None):
        """
        Sync only patient users from RxBackend
        """
        if not self.sync_enabled:
            logger.info("User sync is disabled")
            return {'success': False, 'message': 'User sync is disabled'}
        
        logger.info("Starting patient user synchronization from RxBackend")
        
        try:
            headers = self._get_headers(admin_token)
            synced_count = 0
            page = 1
            
            while True:
                # Fetch patient users
                response = requests.get(
                    f"{self.rxbackend_url}/api/patients/",
                    headers=headers,
                    params={
                        'page': page,
                        'page_size': self.batch_size
                    },
                    timeout=self.timeout
                )
                
                if response.status_code != 200:
                    logger.error(f"Failed to fetch patients from RxBackend: {response.status_code}")
                    break
                
                data = response.json()
                patients = data.get('results', [])
                
                if not patients:
                    break
                
                # Sync patient users
                for patient_data in patients:
                    user_data = patient_data.get('user', {})
                    if user_data and self._sync_user(user_data, is_patient=True):
                        synced_count += 1
                
                # Check if there are more pages
                if not data.get('next'):
                    break
                
                page += 1
            
            logger.info(f"Synchronized {synced_count} patient users from RxBackend")
            return {
                'success': True,
                'synced_count': synced_count,
                'message': f'Successfully synchronized {synced_count} patient users'
            }
            
        except requests.RequestException as e:
            logger.error(f"Network error during patient sync: {e}")
            return {'success': False, 'message': f'Network error: {e}'}
        except Exception as e:
            logger.error(f"Error during patient sync: {e}")
            return {'success': False, 'message': f'Sync error: {e}'}
    
    def sync_single_user(self, user_id, admin_token=None):
        """
        Sync a single user from RxBackend
        """
        if not self.sync_enabled:
            logger.info("User sync is disabled")
            return {'success': False, 'message': 'User sync is disabled'}
        
        logger.info(f"Syncing user {user_id} from RxBackend")
        
        try:
            headers = self._get_headers(admin_token)
            
            response = requests.get(
                f"{self.rxbackend_url}/api/users/{user_id}/",
                headers=headers,
                timeout=self.timeout
            )
            
            if response.status_code == 200:
                user_data = response.json()
                if self._sync_user(user_data):
                    return {
                        'success': True,
                        'message': f'Successfully synchronized user {user_id}'
                    }
                else:
                    return {
                        'success': False,
                        'message': f'Failed to sync user {user_id}'
                    }
            else:
                logger.error(f"Failed to fetch user {user_id} from RxBackend: {response.status_code}")
                return {
                    'success': False,
                    'message': f'User {user_id} not found in RxBackend'
                }
                
        except requests.RequestException as e:
            logger.error(f"Network error syncing user {user_id}: {e}")
            return {'success': False, 'message': f'Network error: {e}'}
        except Exception as e:
            logger.error(f"Error syncing user {user_id}: {e}")
            return {'success': False, 'message': f'Sync error: {e}'}
    
    def _sync_user(self, user_data, is_patient=False):
        """
        Create or update a user based on RxBackend data
        """
        try:
            user_id = user_data.get('id')
            if not user_id:
                logger.warning("User data missing ID, skipping")
                return False
            
            username = f"rxbackend_{user_id}"
            email = user_data.get('email', f"user_{user_id}@rxbackend.local")
            
            # Get or create user
            user, created = User.objects.get_or_create(
                username=username,
                defaults={
                    'email': email,
                    'first_name': user_data.get('first_name', ''),
                    'last_name': user_data.get('last_name', ''),
                    'is_active': user_data.get('is_active', True),
                    'date_joined': timezone.now(),
                }
            )
            
            # Update existing user
            if not created:
                updated = False
                
                if user.email != email:
                    user.email = email
                    updated = True
                
                if user.first_name != user_data.get('first_name', ''):
                    user.first_name = user_data.get('first_name', '')
                    updated = True
                
                if user.last_name != user_data.get('last_name', ''):
                    user.last_name = user_data.get('last_name', '')
                    updated = True
                
                if user.is_active != user_data.get('is_active', True):
                    user.is_active = user_data.get('is_active', True)
                    updated = True
                
                if updated:
                    user.save()
                    logger.debug(f"Updated user: {username}")
            else:
                logger.debug(f"Created user: {username}")
            
            # Store additional user metadata
            self._store_user_metadata(user, user_data, is_patient)
            
            return True
            
        except Exception as e:
            logger.error(f"Error syncing user {user_data.get('id', 'unknown')}: {e}")
            return False
    
    def _store_user_metadata(self, user, user_data, is_patient=False):
        """
        Store additional user metadata from RxBackend
        """
        try:
            # Store metadata in user profile or custom fields
            # This could be extended to store tenant information, roles, etc.
            
            # For now, we'll store basic metadata as user attributes
            if hasattr(user, 'profile'):
                profile = user.profile
            else:
                # Create a simple profile storage mechanism
                # This would typically be a separate model
                pass
            
            # Store RxBackend user ID for reference
            if not hasattr(user, 'rxbackend_user_id'):
                user.rxbackend_user_id = user_data.get('id')
                user.save()
            
            # Store patient-specific information
            if is_patient:
                # Store patient-specific metadata
                pass
            
        except Exception as e:
            logger.error(f"Error storing user metadata for {user.username}: {e}")
    
    def _get_headers(self, admin_token=None):
        """
        Get headers for RxBackend API requests
        """
        headers = {
            'Content-Type': 'application/json',
            'Accept': 'application/json',
        }
        
        if admin_token:
            headers['Authorization'] = f'Bearer {admin_token}'
        
        return headers
    
    def get_sync_status(self):
        """
        Get synchronization status
        """
        try:
            total_users = User.objects.filter(username__startswith='rxbackend_').count()
            active_users = User.objects.filter(
                username__startswith='rxbackend_',
                is_active=True
            ).count()
            
            # Get last sync time (this would typically be stored in a sync log model)
            last_sync = timezone.now() - timedelta(hours=1)  # Placeholder
            
            return {
                'sync_enabled': self.sync_enabled,
                'total_synced_users': total_users,
                'active_synced_users': active_users,
                'last_sync': last_sync.isoformat(),
                'rxbackend_url': self.rxbackend_url,
            }
            
        except Exception as e:
            logger.error(f"Error getting sync status: {e}")
            return {
                'sync_enabled': self.sync_enabled,
                'error': str(e)
            }


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
    
    def handle(self, *args, **options):
        sync_service = UserSyncService()
        
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
                self.style.ERROR('Please specify --all, --patients, or --user-id')
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