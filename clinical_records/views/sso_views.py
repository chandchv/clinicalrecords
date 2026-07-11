"""
SSO Views for Clinical Records Service
Handles single sign-on from RxBackend
"""
import jwt
import logging
from django.shortcuts import redirect
from django.contrib.auth import login, get_user_model
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from django.conf import settings
from ..authentication import validate_rxbackend_token

logger = logging.getLogger(__name__)
User = get_user_model()


@csrf_exempt
@require_http_methods(["GET", "POST"])
def sso_login(request):
    """
    SSO login endpoint that accepts JWT token and creates session
    
    Usage: /sso/login/?token=JWT_TOKEN&next=/dashboard/
    """
    # Get token from query parameter or POST data
    token = request.GET.get('token') or request.POST.get('token')
    next_url = request.GET.get('next', '/dashboard/')
    
    if not token:
        return JsonResponse({
            'error': 'Token required',
            'message': 'Please provide a JWT token'
        }, status=400)
    
    try:
        # Validate token using RxBackend SECRET_KEY
        payload = validate_rxbackend_token(token)
        
        if not payload:
            return JsonResponse({
                'error': 'Invalid token',
                'message': 'Token validation failed'
            }, status=401)
        
        # Extract user information
        user_id = payload.get('user_id')
        username = payload.get('username')
        email = payload.get('email')
        first_name = payload.get('first_name', '')
        last_name = payload.get('last_name', '')
        
        if not user_id or not username:
            return JsonResponse({
                'error': 'Invalid token payload',
                'message': 'Token missing required user information'
            }, status=400)
        
        # Get or create user
        clinical_username = f"rxbackend_{user_id}"
        
        try:
            user = User.objects.get(username=clinical_username)
            # Update user info
            user.email = email or user.email
            user.first_name = first_name
            user.last_name = last_name
            user.save()
            logger.info(f"Updated existing user: {user.username}")
        except User.DoesNotExist:
            # Create new user
            user = User.objects.create_user(
                username=clinical_username,
                email=email or f"user_{user_id}@rxbackend.local",
                first_name=first_name,
                last_name=last_name,
                is_active=True
            )
            logger.info(f"Created new user via SSO: {user.username}")
        
        # Log the user in (creates session)
        login(request, user, backend='django.contrib.auth.backends.ModelBackend')
        
        # Store metadata in session for hybrid authentication (Session + JWT context)
        request.session['patient_id'] = payload.get('patient_id')
        request.session['jwt_token'] = token
        request.session['jwt_claims'] = payload
        request.session['current_tenant_id'] = payload.get('current_tenant_id') 
        
        # Redirect to requested page with token in params so frontend can extract it
        if '?' in next_url:
            redirect_url = f"{next_url}&token={token}"
        else:
            redirect_url = f"{next_url}?token={token}"
            
        logger.info(f"SSO login successful for user: {user.username}, redirecting to: {redirect_url}")
        
        # Redirect to requested page
        return redirect(redirect_url)
        
    except jwt.ExpiredSignatureError:
        return JsonResponse({
            'error': 'Token expired',
            'message': 'Please login again'
        }, status=401)
    except jwt.InvalidTokenError as e:
        return JsonResponse({
            'error': 'Invalid token',
            'message': str(e)
        }, status=401)
    except Exception as e:
        logger.error(f"SSO login error: {e}")
        return JsonResponse({
            'error': 'Authentication failed',
            'message': str(e)
        }, status=500)


@csrf_exempt
@require_http_methods(["GET"])
def sso_logout(request):
    """
    SSO logout endpoint
    """
    from django.contrib.auth import logout
    logout(request)
    return JsonResponse({'message': 'Logged out successfully'})


@csrf_exempt
@require_http_methods(["GET"])
def sso_status(request):
    """
    Check SSO authentication status
    """
    if request.user.is_authenticated:
        return JsonResponse({
            'authenticated': True,
            'username': request.user.username,
            'email': request.user.email,
        })
    else:
        return JsonResponse({
            'authenticated': False
        })


# Additional API endpoints for compatibility
def health_check(request):
    """Health check endpoint"""
    return JsonResponse({
        'status': 'healthy',
        'service': 'Clinical Records Service',
        'version': '1.0.0'
    })


def user_profile(request):
    """Get current user profile"""
    if not request.user.is_authenticated:
        return JsonResponse({'error': 'Authentication required'}, status=401)
    
    return JsonResponse({
        'id': request.user.id,
        'username': request.user.username,
        'email': request.user.email,
        'first_name': request.user.first_name,
        'last_name': request.user.last_name,
    })


def clinical_records_list(request):
    """List clinical records for the authenticated user"""
    if not request.user.is_authenticated:
        return JsonResponse({'error': 'Authentication required'}, status=401)
    
    return JsonResponse({
        'records': [],
        'count': 0,
        'message': 'Clinical records endpoint'
    })
