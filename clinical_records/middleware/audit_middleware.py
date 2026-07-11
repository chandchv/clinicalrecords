"""
Audit logging middleware for clinical records.

This middleware automatically captures and logs HTTP requests
related to clinical records for comprehensive audit trails.
"""

import json
import time
import logging
from typing import Dict, Any, Optional
from django.utils.deprecation import MiddlewareMixin
from django.http import HttpRequest, HttpResponse
from django.urls import resolve, Resolver404
from django.contrib.auth import get_user_model

from ..services.audit_service import audit_service

User = get_user_model()
logger = logging.getLogger(__name__)


class ClinicalAuditMiddleware(MiddlewareMixin):
    """
    Middleware to automatically audit clinical records operations.
    
    This middleware captures HTTP requests to clinical records endpoints
    and creates appropriate audit log entries.
    """
    
    # URL patterns that should be audited
    AUDITED_URL_PATTERNS = [
        'clinical_records:clinicalrecord',
        'clinical_records:clinicaldocument',
        'clinical_records:sharing',
        'clinical_records:manualreview',
        'clinical_records:fhir',
        'clinical_records:encryption',
        'clinical_records:webhooks',
        'clinical_records:emailingestion',
        'clinical_records:sftpingestion',
    ]
    
    # HTTP methods that should be audited
    AUDITED_METHODS = ['GET', 'POST', 'PUT', 'PATCH', 'DELETE']
    
    # Sensitive endpoints that require special logging
    SENSITIVE_ENDPOINTS = [
        'encrypted_file_serve',
        'download',
        'preview',
        'share_access',
        'fhir_export',
    ]
    
    def __init__(self, get_response):
        super().__init__(get_response)
        self.get_response = get_response
    
    def process_request(self, request: HttpRequest) -> Optional[HttpResponse]:
        """Process incoming request and prepare for audit logging."""
        # Store request start time for performance metrics
        request._audit_start_time = time.time()
        
        # Check if this request should be audited
        if self._should_audit_request(request):
            request._should_audit = True
            request._audit_context = self._extract_audit_context(request)
        else:
            request._should_audit = False
        
        return None
    
    def process_response(self, request: HttpRequest, response: HttpResponse) -> HttpResponse:
        """Process response and create audit log entry if needed."""
        if getattr(request, '_should_audit', False):
            try:
                self._create_audit_log(request, response)
            except Exception as e:
                # Don't let audit logging failures break the application
                logger.error(f"Audit logging failed: {str(e)}")
        
        return response
    
    def process_exception(self, request: HttpRequest, exception: Exception) -> Optional[HttpResponse]:
        """Process exceptions and log them for audit purposes."""
        if getattr(request, '_should_audit', False):
            try:
                self._log_exception(request, exception)
            except Exception as e:
                logger.error(f"Exception audit logging failed: {str(e)}")
        
        return None
    
    def _should_audit_request(self, request: HttpRequest) -> bool:
        """Determine if a request should be audited."""
        # Only audit specific HTTP methods
        if request.method not in self.AUDITED_METHODS:
            return False
        
        # Check if URL matches audited patterns
        try:
            resolved = resolve(request.path_info)
            url_name = resolved.url_name
            namespace = resolved.namespace
            
            # Check if this is a clinical records endpoint
            if namespace == 'clinical_records':
                return True
            
            # Check for specific URL patterns
            full_url_name = f"{namespace}:{url_name}" if namespace else url_name
            return any(pattern in full_url_name for pattern in self.AUDITED_URL_PATTERNS)
            
        except Resolver404:
            return False
    
    def _extract_audit_context(self, request: HttpRequest) -> Dict[str, Any]:
        """Extract audit context from request."""
        try:
            resolved = resolve(request.path_info)
            
            context = {
                'url_name': resolved.url_name,
                'namespace': resolved.namespace,
                'view_name': resolved.view_name,
                'method': request.method,
                'path': request.path_info,
                'query_params': dict(request.GET),
                'is_sensitive': any(endpoint in resolved.url_name 
                                  for endpoint in self.SENSITIVE_ENDPOINTS),
            }
            
            # Extract resource IDs from URL kwargs
            if resolved.kwargs:
                context['url_kwargs'] = resolved.kwargs
                
                # Common resource ID patterns
                if 'pk' in resolved.kwargs:
                    context['resource_id'] = resolved.kwargs['pk']
                elif 'id' in resolved.kwargs:
                    context['resource_id'] = resolved.kwargs['id']
            
            return context
            
        except Exception as e:
            logger.warning(f"Failed to extract audit context: {str(e)}")
            return {
                'method': request.method,
                'path': request.path_info,
                'error': str(e)
            }
    
    def _create_audit_log(self, request: HttpRequest, response: HttpResponse) -> None:
        """Create audit log entry for the request/response."""
        context = getattr(request, '_audit_context', {})
        start_time = getattr(request, '_audit_start_time', time.time())
        
        # Calculate request duration
        duration_ms = (time.time() - start_time) * 1000
        
        # Determine action type based on method and URL
        action = self._determine_action(context, response.status_code)
        
        # Determine resource type
        resource_type = self._determine_resource_type(context)
        
        # Extract resource ID
        resource_id = context.get('resource_id')
        
        # Get clinic context
        clinic = getattr(request.user, 'clinic', None) if hasattr(request, 'user') else None
        
        # Prepare audit details
        details = {
            'http_method': request.method,
            'status_code': response.status_code,
            'duration_ms': round(duration_ms, 2),
            'url_name': context.get('url_name'),
            'view_name': context.get('view_name'),
            'query_params': context.get('query_params', {}),
            'is_sensitive_endpoint': context.get('is_sensitive', False),
        }
        
        # Add request body for POST/PUT/PATCH (but sanitize sensitive data)
        if request.method in ['POST', 'PUT', 'PATCH']:
            try:
                if hasattr(request, 'body') and request.body:
                    # Only log non-file uploads and sanitize sensitive data
                    content_type = request.META.get('CONTENT_TYPE', '')
                    if 'multipart/form-data' not in content_type:
                        body_data = self._sanitize_request_body(request.body)
                        if body_data:
                            details['request_body'] = body_data
            except Exception:
                pass  # Don't fail audit logging due to body parsing issues
        
        # Add response size
        if hasattr(response, 'content'):
            details['response_size_bytes'] = len(response.content)
        
        # Log the action
        try:
            audit_service.log_clinical_action(
                action=action,
                user=request.user if hasattr(request, 'user') and request.user.is_authenticated else None,
                resource_type=resource_type,
                resource_id=resource_id,
                clinic=clinic,
                request=request,
                details=details,
                sensitive_data=context.get('is_sensitive', False)
            )
        except Exception as e:
            logger.error(f"Failed to create audit log: {str(e)}")
    
    def _log_exception(self, request: HttpRequest, exception: Exception) -> None:
        """Log exceptions for audit purposes."""
        context = getattr(request, '_audit_context', {})
        
        details = {
            'exception_type': type(exception).__name__,
            'exception_message': str(exception),
            'http_method': request.method,
            'url_name': context.get('url_name'),
            'view_name': context.get('view_name'),
        }
        
        # Get clinic context
        clinic = getattr(request.user, 'clinic', None) if hasattr(request, 'user') else None
        
        try:
            audit_service.log_clinical_action(
                action='SYSTEM_ERROR',
                user=request.user if hasattr(request, 'user') and request.user.is_authenticated else None,
                resource_type='SYSTEM',
                clinic=clinic,
                request=request,
                details=details
            )
        except Exception as e:
            logger.error(f"Failed to log exception audit: {str(e)}")
    
    def _determine_action(self, context: Dict[str, Any], status_code: int) -> str:
        """Determine audit action based on context and response."""
        method = context.get('method', 'UNKNOWN')
        url_name = context.get('url_name', '')
        
        # Handle specific endpoints
        if 'download' in url_name or 'serve' in url_name:
            return 'DOCUMENT_DOWNLOAD'
        elif 'preview' in url_name:
            return 'DOCUMENT_VIEW'
        elif 'share' in url_name and method == 'GET':
            return 'RECORD_SHARE_ACCESS'
        elif 'share' in url_name and method == 'POST':
            return 'RECORD_SHARE_CREATE'
        elif 'fhir' in url_name:
            return 'FHIR_EXPORT'
        elif 'encrypt' in url_name:
            return 'DOCUMENT_ENCRYPT'
        elif 'webhook' in url_name:
            return 'WEBHOOK_DELIVERY'
        
        # Handle generic CRUD operations
        if method == 'GET':
            return 'CLINICAL_RECORD_VIEW' if 'record' in url_name else 'DOCUMENT_VIEW'
        elif method == 'POST':
            return 'CLINICAL_RECORD_CREATE' if 'record' in url_name else 'DOCUMENT_UPLOAD'
        elif method in ['PUT', 'PATCH']:
            return 'CLINICAL_RECORD_UPDATE' if 'record' in url_name else 'DOCUMENT_UPDATE'
        elif method == 'DELETE':
            return 'CLINICAL_RECORD_DELETE' if 'record' in url_name else 'DOCUMENT_DELETE'
        
        return f'CLINICAL_ACTION_{method}'
    
    def _determine_resource_type(self, context: Dict[str, Any]) -> str:
        """Determine resource type based on context."""
        url_name = context.get('url_name', '').lower()
        view_name = context.get('view_name', '').lower()
        
        if 'document' in url_name or 'document' in view_name:
            return 'CLINICAL_DOCUMENT'
        elif 'record' in url_name or 'record' in view_name:
            return 'CLINICAL_RECORD'
        elif 'share' in url_name or 'share' in view_name:
            return 'SHARE_TOKEN'
        elif 'review' in url_name or 'review' in view_name:
            return 'MANUAL_REVIEW'
        elif 'webhook' in url_name or 'webhook' in view_name:
            return 'WEBHOOK_CONFIG'
        elif 'encrypt' in url_name or 'encrypt' in view_name:
            return 'ENCRYPTION_KEY'
        
        return 'CLINICAL_RECORD'  # Default
    
    def _sanitize_request_body(self, body: bytes) -> Optional[Dict[str, Any]]:
        """Sanitize request body for audit logging."""
        try:
            # Try to parse as JSON
            body_str = body.decode('utf-8')
            data = json.loads(body_str)
            
            # Sanitize sensitive fields
            sensitive_fields = [
                'password', 'token', 'secret', 'key', 'ssn', 
                'social_security', 'credit_card', 'bank_account'
            ]
            
            def sanitize_dict(d):
                if isinstance(d, dict):
                    return {
                        k: '***REDACTED***' if any(field in k.lower() for field in sensitive_fields)
                        else sanitize_dict(v) if isinstance(v, (dict, list)) else v
                        for k, v in d.items()
                    }
                elif isinstance(d, list):
                    return [sanitize_dict(item) for item in d]
                return d
            
            return sanitize_dict(data)
            
        except (UnicodeDecodeError, json.JSONDecodeError):
            # If not JSON or can't decode, just return metadata
            return {
                'body_size_bytes': len(body),
                'content_type': 'non-json'
            }
        except Exception:
            return None