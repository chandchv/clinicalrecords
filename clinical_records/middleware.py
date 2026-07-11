"""
Middleware for Clinical Records Service
Handles JWT authentication and tenant context from RxBackend
"""
import jwt
import logging
from django.conf import settings
from django.contrib.auth import get_user_model
from django.http import JsonResponse
from django.utils.deprecation import MiddlewareMixin
from .authentication import validate_rxbackend_token

logger = logging.getLogger(__name__)
User = get_user_model()


class JWTAuthenticationMiddleware(MiddlewareMixin):
    """
    Middleware to handle JWT authentication from RxBackend
    """
    
    def process_request(self, request):
        """
        Process incoming request to extract and validate JWT token
        """
        # Skip authentication for certain paths
        skip_paths = [
            '/admin/',
            '/health/',
            '/static/',
            '/media/',
        ]
        
        if any(request.path.startswith(path) for path in skip_paths):
            return None
        
        # Extract JWT token from Authorization header, query parameters, or session
        token = None
        auth_header = request.META.get('HTTP_AUTHORIZATION')
        if auth_header and auth_header.startswith('Bearer '):
            token = auth_header.split(' ')[1]
        elif 'token' in request.GET:
            token = request.GET.get('token')
        elif hasattr(request, 'session') and 'jwt_token' in request.session:
            token = request.session['jwt_token']
            
        if not token:
            # No JWT token, let other authentication methods handle it
            return None
        
        try:
            # Validate token and extract claims
            payload = validate_rxbackend_token(token)
            if not payload:
                return JsonResponse({'error': 'Invalid token'}, status=401)
            
            # Store token claims in request for later use
            request.jwt_claims = payload
            request.jwt_token = token
            
            # Extract user information
            user_id = payload.get('user_id')
            username = payload.get('username')
            
            if user_id and username:
                # Try to get or create user
                try:
                    user = User.objects.get(username=f"rxbackend_{user_id}")
                except User.DoesNotExist:
                    # Create user based on JWT claims
                    user = User.objects.create_user(
                        username=f"rxbackend_{user_id}",
                        email=payload.get('email', f"user_{user_id}@rxbackend.local"),
                        first_name=payload.get('first_name', ''),
                        last_name=payload.get('last_name', ''),
                        is_active=True
                    )
                    logger.info(f"Created user from JWT: {user.username}")
                
                # Set user in request
                request.user = user
                request._cached_user = user
            
        except Exception as e:
            logger.error(f"JWT middleware error: {e}")
            return JsonResponse({'error': 'Authentication failed'}, status=401)
        
        return None


class TenantContextMiddleware(MiddlewareMixin):
    """
    Middleware to handle tenant context from RxBackend JWT tokens
    """
    
    def process_request(self, request):
        """
        Extract tenant context from JWT claims
        """
        # Initialize tenant context
        request.tenant_id = None
        request.tenant_name = None
        request.tenant_role = None
        request.accessible_tenants = []
        
        # Try to get claims from request (set by JWTAuthenticationMiddleware) or fallback to session
        claims = None
        if hasattr(request, 'jwt_claims'):
            claims = request.jwt_claims
        elif hasattr(request, 'session') and 'jwt_claims' in request.session:
            claims = request.session['jwt_claims']
            request.jwt_claims = claims
            if hasattr(request, 'session') and 'jwt_token' in request.session:
                request.jwt_token = request.session['jwt_token']
        
        # Extract tenant information from JWT claims if available
        if claims:
            # Current tenant information
            request.tenant_id = claims.get('current_tenant_id')
            request.tenant_name = claims.get('current_tenant_name')
            request.tenant_role = claims.get('tenant_role')
            
            # Accessible tenants
            request.accessible_tenants = claims.get('accessible_tenants', [])
            
            # Store additional tenant context
            request.tenant_context = {
                'current_tenant_id': request.tenant_id,
                'current_tenant_name': request.tenant_name,
                'tenant_role': request.tenant_role,
                'accessible_tenants': request.accessible_tenants,
                'is_primary_tenant': claims.get('is_primary_tenant', False),
            }
            
            # If request.user is authenticated, make sure they have current_tenant set
            if request.user and request.user.is_authenticated:
                if not hasattr(request.user, 'current_tenant') or not request.user.current_tenant:
                    if request.tenant_id:
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
                        
                        request.user.current_tenant = MockTenant(
                            request.tenant_id,
                            request.tenant_name or 'Unknown Tenant'
                        )
                        logger.info(f"Attached session tenant {request.tenant_id} to user {request.user.username}")
                
                # Expose clinic context to Django REST Framework permission classes
                if hasattr(request.user, 'current_tenant') and request.user.current_tenant:
                    request.user.clinic = request.user.current_tenant
            
            logger.debug(f"Tenant context set: {request.tenant_context}")
        
        return None
    
    def process_response(self, request, response):
        """
        Add tenant context to response headers for debugging
        """
        if hasattr(request, 'tenant_id') and request.tenant_id:
            response['X-Tenant-ID'] = str(request.tenant_id)
            response['X-Tenant-Name'] = request.tenant_name or 'Unknown'
        
        return response


class CORSMiddleware(MiddlewareMixin):
    """
    Custom CORS middleware for Clinical Records Service
    """
    
    def process_response(self, request, response):
        """
        Add CORS headers for RxBackend integration
        """
        # Allow requests from RxBackend
        origin = request.META.get('HTTP_ORIGIN')
        allowed_origins = [
            'http://localhost:8000',
            'http://127.0.0.1:8000',
        ]
        
        if origin in allowed_origins:
            response['Access-Control-Allow-Origin'] = origin
            response['Access-Control-Allow-Credentials'] = 'true'
            response['Access-Control-Allow-Methods'] = 'GET, POST, PUT, DELETE, OPTIONS'
            response['Access-Control-Allow-Headers'] = 'Authorization, Content-Type, X-Requested-With'
        
        return response


class SecurityMiddleware(MiddlewareMixin):
    """
    Security middleware for Clinical Records Service
    """
    
    def process_request(self, request):
        """
        Add security checks for API requests
        """
        # Rate limiting could be implemented here
        # IP whitelisting could be implemented here
        # Additional security checks could be implemented here
        
        return None
    
    def process_response(self, request, response):
        """
        Add security headers
        """
        response['X-Content-Type-Options'] = 'nosniff'
        response['X-Frame-Options'] = 'DENY'
        response['X-XSS-Protection'] = '1; mode=block'
        response['Referrer-Policy'] = 'strict-origin-when-cross-origin'
        
        return response


class LoggingMiddleware(MiddlewareMixin):
    """
    Logging middleware for Clinical Records Service
    """
    
    def process_request(self, request):
        """
        Log incoming requests
        """
        if settings.DEBUG:
            logger.info(f"Request: {request.method} {request.path}")
            if hasattr(request, 'user') and request.user.is_authenticated:
                logger.info(f"User: {request.user.username}")
            if hasattr(request, 'tenant_id') and request.tenant_id:
                logger.info(f"Tenant: {request.tenant_id}")
        
        return None
    
    def process_response(self, request, response):
        """
        Log response status
        """
        if settings.DEBUG:
            logger.info(f"Response: {response.status_code}")
        
        return response