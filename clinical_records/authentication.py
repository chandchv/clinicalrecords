"""
JWT Authentication for Clinical Records Service
Integrates with RxBackend JWT tokens for SSO
"""
import jwt
import requests
from django.conf import settings
from django.contrib.auth.models import User
from django.contrib.auth import get_user_model
from rest_framework.authentication import BaseAuthentication
from rest_framework.exceptions import AuthenticationFailed
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework_simplejwt.exceptions import InvalidToken, TokenError
from rest_framework_simplejwt.tokens import UntypedToken
import logging

logger = logging.getLogger(__name__)
User = get_user_model()


class RxBackendJWTAuthentication(JWTAuthentication):
    """
    Custom JWT Authentication that validates tokens from RxBackend
    and creates/syncs users in Clinical Records Service
    """
    
    def authenticate(self, request):
        """
        Authenticate the request using JWT token from RxBackend
        """
        header = self.get_header(request)
        raw_token = None
        
        if header is not None:
            raw_token = self.get_raw_token(header)
        
        # Fallback to query parameter or session if Authorization header is missing
        if raw_token is None:
            raw_token = request.GET.get('token')
        if raw_token is None and hasattr(request, 'session'):
            raw_token = request.session.get('jwt_token')
            
        if raw_token is None:
            return None

        try:
            # Validate token using RxBackend's secret key
            validated_token = self.get_validated_token(raw_token)
            user = self.get_user(validated_token)
            
            # Store token claims in request for middleware access
            request.jwt_claims = validated_token.payload
            request.jwt_token = raw_token
            
            return (user, validated_token)
            
        except TokenError as e:
            logger.warning(f"JWT Token validation failed: {e}")
            raise AuthenticationFailed('Invalid token')
        except Exception as e:
            logger.error(f"JWT Authentication error: {e}")
            raise AuthenticationFailed('Authentication failed')

    def get_validated_token(self, raw_token):
        """
        Validate the JWT token using RxBackend's secret key
        """
        try:
            # Decode and validate token
            payload = jwt.decode(
                raw_token,
                settings.RXBACKEND_SECRET_KEY,
                algorithms=['HS256']
            )
            
            # Create a mock token object with the payload
            class MockToken:
                def __init__(self, payload):
                    self.payload = payload
            
            return MockToken(payload)
            
        except jwt.ExpiredSignatureError:
            raise TokenError('Token has expired')
        except jwt.InvalidTokenError as e:
            raise TokenError(f'Invalid token: {e}')

    def get_user(self, validated_token):
        """
        Get or create user based on JWT token claims
        """
        try:
            payload = validated_token.payload
            user_id = payload.get('user_id')
            username = payload.get('username')
            email = payload.get('email')
            first_name = payload.get('first_name', '')
            last_name = payload.get('last_name', '')
            
            if not user_id or not username:
                raise AuthenticationFailed('Invalid token payload')
            
            # Try to get existing user by RxBackend user ID
            try:
                user = User.objects.get(username=f"rxbackend_{user_id}")
            except User.DoesNotExist:
                # Create new user based on RxBackend data
                user = User.objects.create_user(
                    username=f"rxbackend_{user_id}",
                    email=email or f"user_{user_id}@rxbackend.local",
                    first_name=first_name,
                    last_name=last_name,
                    is_active=True
                )
                logger.info(f"Created new user from RxBackend: {user.username}")
            
            
            # Update user information if needed
            updated = False
            if user.email != email and email:
                user.email = email
                updated = True
            if user.first_name != first_name:
                user.first_name = first_name
                updated = True
            if user.last_name != last_name:
                user.last_name = last_name
                updated = True
            
            if updated:
                user.save()
                logger.info(f"Updated user information: {user.username}")
            
            # Parse tenant info
            current_tenant_id = payload.get('current_tenant_id')
            if current_tenant_id:
                class MockTenant:
                    def __init__(self, id, name):
                        self.id = id
                        self.name = name
                        self.address = ''
                        self.phone_number = ''
                    
                    def __eq__(self, other):
                        if hasattr(other, 'id'):
                            return self.id == other.id
                        return False
                
                user.current_tenant = MockTenant(
                    current_tenant_id, 
                    payload.get('current_tenant_name', 'Unknown Tenant')
                )
            else:
                user.current_tenant = None

            user.clinic = user.current_tenant

            # Attach patient_id and legacy_role to user for permission checks
            user.patient_id = payload.get('patient_id')
            user.legacy_role = payload.get('legacy_role')
            
            return user
            
        except Exception as e:
            logger.error(f"Error getting/creating user: {e}")
            raise AuthenticationFailed('User authentication failed')


class RxBackendUserSyncService:
    """
    Service to synchronize users between RxBackend and Clinical Records Service
    """
    
    def __init__(self):
        self.rxbackend_url = settings.RXBACKEND_SERVICE_URL
        self.timeout = settings.RXBACKEND_API_TIMEOUT
    
    def sync_user_from_rxbackend(self, user_id, token=None):
        """
        Sync a specific user from RxBackend
        """
        try:
            headers = {}
            if token:
                headers['Authorization'] = f'Bearer {token}'
            
            response = requests.get(
                f"{self.rxbackend_url}/api/users/{user_id}/",
                headers=headers,
                timeout=self.timeout
            )
            
            if response.status_code == 200:
                user_data = response.json()
                return self._create_or_update_user(user_data)
            else:
                logger.warning(f"Failed to fetch user {user_id} from RxBackend: {response.status_code}")
                return None
                
        except requests.RequestException as e:
            logger.error(f"Error syncing user {user_id} from RxBackend: {e}")
            return None
    
    def _create_or_update_user(self, user_data):
        """
        Create or update user based on RxBackend data
        """
        try:
            user_id = user_data.get('id')
            username = f"rxbackend_{user_id}"
            
            user, created = User.objects.get_or_create(
                username=username,
                defaults={
                    'email': user_data.get('email', f"user_{user_id}@rxbackend.local"),
                    'first_name': user_data.get('first_name', ''),
                    'last_name': user_data.get('last_name', ''),
                    'is_active': user_data.get('is_active', True),
                }
            )
            
            if not created:
                # Update existing user
                user.email = user_data.get('email', user.email)
                user.first_name = user_data.get('first_name', user.first_name)
                user.last_name = user_data.get('last_name', user.last_name)
                user.is_active = user_data.get('is_active', user.is_active)
                user.save()
            
            action = "Created" if created else "Updated"
            logger.info(f"{action} user: {user.username}")
            
            return user
            
        except Exception as e:
            logger.error(f"Error creating/updating user: {e}")
            return None
    
    def bulk_sync_users(self, token=None):
        """
        Bulk synchronize users from RxBackend
        """
        try:
            headers = {}
            if token:
                headers['Authorization'] = f'Bearer {token}'
            
            response = requests.get(
                f"{self.rxbackend_url}/api/users/",
                headers=headers,
                timeout=self.timeout,
                params={'page_size': settings.USER_SYNC_BATCH_SIZE}
            )
            
            if response.status_code == 200:
                data = response.json()
                users = data.get('results', [])
                
                synced_count = 0
                for user_data in users:
                    if self._create_or_update_user(user_data):
                        synced_count += 1
                
                logger.info(f"Bulk synced {synced_count} users from RxBackend")
                return synced_count
            else:
                logger.warning(f"Failed to bulk sync users from RxBackend: {response.status_code}")
                return 0
                
        except requests.RequestException as e:
            logger.error(f"Error bulk syncing users from RxBackend: {e}")
            return 0


def validate_rxbackend_token(token):
    """
    Utility function to validate RxBackend JWT token
    """
    try:
        payload = jwt.decode(
            token,
            settings.RXBACKEND_SECRET_KEY,
            algorithms=['HS256']
        )
        return payload
    except jwt.InvalidTokenError:
        return None