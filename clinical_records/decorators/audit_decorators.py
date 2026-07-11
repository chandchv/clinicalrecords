"""
Audit logging decorators for clinical records.

This module provides decorators to easily add audit logging
to views, methods, and functions.
"""

import functools
import logging
from typing import Callable, Any, Dict, Optional
from django.http import HttpRequest
from django.contrib.auth import get_user_model

from ..services.simple_audit_service import audit_service
from ..models import ClinicalRecord, ClinicalDocument

User = get_user_model()
logger = logging.getLogger(__name__)


def audit_clinical_action(action: str, resource_type: str = None, 
                         sensitive_data: bool = False,
                         extract_resource_id: Callable = None):
    """
    Decorator to automatically audit clinical actions.
    
    Args:
        action: Action type from ClinicalAuditService.CLINICAL_ACTIONS
        resource_type: Resource type from ClinicalAuditService.CLINICAL_RESOURCE_TYPES
        sensitive_data: Whether sensitive data is being accessed
        extract_resource_id: Function to extract resource ID from args/kwargs
    
    Usage:
        @audit_clinical_action('CLINICAL_RECORD_VIEW', 'CLINICAL_RECORD', sensitive_data=True)
        def view_record(request, record_id):
            # View implementation
            pass
    """
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            # Extract request and user from arguments
            request = None
            user = None
            
            # Look for request in args
            for arg in args:
                if isinstance(arg, HttpRequest):
                    request = arg
                    user = getattr(request, 'user', None) if hasattr(request, 'user') else None
                    break
            
            # Extract resource ID
            resource_id = None
            if extract_resource_id:
                try:
                    resource_id = extract_resource_id(*args, **kwargs)
                except Exception as e:
                    logger.warning(f"Failed to extract resource ID: {str(e)}")
            else:
                # Try common patterns
                resource_id = kwargs.get('pk') or kwargs.get('id') or kwargs.get('record_id')
            
            # Get clinic context
            clinic = getattr(user, 'clinic', None) if user else None
            
            try:
                # Execute the function
                result = func(*args, **kwargs)
                
                # Log successful action
                audit_service.log_clinical_action(
                    action=action,
                    user=user,
                    resource_type=resource_type,
                    resource_id=str(resource_id) if resource_id else None,
                    clinic=clinic,
                    request=request,
                    sensitive_data=sensitive_data,
                    details={
                        'function_name': func.__name__,
                        'module': func.__module__,
                        'success': True
                    }
                )
                
                return result
                
            except Exception as e:
                # Log failed action
                audit_service.log_clinical_action(
                    action=f"{action}_FAILED",
                    user=user,
                    resource_type=resource_type,
                    resource_id=str(resource_id) if resource_id else None,
                    clinic=clinic,
                    request=request,
                    details={
                        'function_name': func.__name__,
                        'module': func.__module__,
                        'success': False,
                        'error': str(e),
                        'exception_type': type(e).__name__
                    }
                )
                
                # Re-raise the exception
                raise
        
        return wrapper
    return decorator


def audit_record_access(access_type: str = 'VIEW'):
    """
    Decorator specifically for clinical record access.
    
    Args:
        access_type: Type of access (VIEW, UPDATE, DELETE, etc.)
    
    Usage:
        @audit_record_access('VIEW')
        def get_record(request, record_id):
            record = ClinicalRecord.objects.get(id=record_id)
            return record
    """
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            request = None
            user = None
            record = None
            
            # Extract request from args
            for arg in args:
                if isinstance(arg, HttpRequest):
                    request = arg
                    user = getattr(request, 'user', None)
                    break
            
            try:
                # Execute the function
                result = func(*args, **kwargs)
                
                # Try to extract record from result or find it
                if isinstance(result, ClinicalRecord):
                    record = result
                elif hasattr(result, 'object') and isinstance(result.object, ClinicalRecord):
                    record = result.object
                else:
                    # Try to find record by ID
                    record_id = kwargs.get('pk') or kwargs.get('id') or kwargs.get('record_id')
                    if record_id:
                        try:
                            record = ClinicalRecord.objects.get(id=record_id)
                        except ClinicalRecord.DoesNotExist:
                            pass
                
                # Log the access
                if record and user and request:
                    audit_service.log_record_access(record, user, request, access_type)
                
                return result
                
            except Exception as e:
                # Log failed access attempt
                record_id = kwargs.get('pk') or kwargs.get('id') or kwargs.get('record_id')
                clinic = getattr(user, 'clinic', None) if user else None
                
                if user and request and clinic:
                    audit_service.log_clinical_action(
                        action=f'CLINICAL_RECORD_{access_type}_FAILED',
                        user=user,
                        resource_type='CLINICAL_RECORD',
                        resource_id=str(record_id) if record_id else None,
                        clinic=clinic,
                        request=request,
                        details={
                            'error': str(e),
                            'access_type': access_type,
                            'function_name': func.__name__
                        }
                    )
                
                raise
        
        return wrapper
    return decorator


def audit_document_access(access_type: str = 'VIEW'):
    """
    Decorator specifically for clinical document access.
    
    Args:
        access_type: Type of access (VIEW, DOWNLOAD, UPDATE, etc.)
    
    Usage:
        @audit_document_access('DOWNLOAD')
        def download_document(request, document_id):
            document = ClinicalDocument.objects.get(id=document_id)
            return serve_document(document)
    """
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            request = None
            user = None
            document = None
            
            # Extract request from args
            for arg in args:
                if isinstance(arg, HttpRequest):
                    request = arg
                    user = getattr(request, 'user', None)
                    break
            
            try:
                # Execute the function
                result = func(*args, **kwargs)
                
                # Try to extract document from result or find it
                if isinstance(result, ClinicalDocument):
                    document = result
                elif hasattr(result, 'object') and isinstance(result.object, ClinicalDocument):
                    document = result.object
                else:
                    # Try to find document by ID
                    document_id = kwargs.get('pk') or kwargs.get('id') or kwargs.get('document_id')
                    if document_id:
                        try:
                            document = ClinicalDocument.objects.get(id=document_id)
                        except ClinicalDocument.DoesNotExist:
                            pass
                
                # Log the access
                if document and user and request:
                    audit_service.log_document_access(document, user, request, access_type)
                
                return result
                
            except Exception as e:
                # Log failed access attempt
                document_id = kwargs.get('pk') or kwargs.get('id') or kwargs.get('document_id')
                clinic = getattr(user, 'clinic', None) if user else None
                
                if user and request and clinic:
                    audit_service.log_clinical_action(
                        action=f'DOCUMENT_{access_type}_FAILED',
                        user=user,
                        resource_type='CLINICAL_DOCUMENT',
                        resource_id=str(document_id) if document_id else None,
                        clinic=clinic,
                        request=request,
                        details={
                            'error': str(e),
                            'access_type': access_type,
                            'function_name': func.__name__
                        }
                    )
                
                raise
        
        return wrapper
    return decorator


def audit_search_action(search_type: str = 'CLINICAL_SEARCH'):
    """
    Decorator for search actions.
    
    Args:
        search_type: Type of search being performed
    
    Usage:
        @audit_search_action('CLINICAL_SEARCH')
        def search_records(request):
            # Search implementation
            return results
    """
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            request = None
            user = None
            
            # Extract request from args
            for arg in args:
                if isinstance(arg, HttpRequest):
                    request = arg
                    user = getattr(request, 'user', None)
                    break
            
            try:
                # Execute the function
                result = func(*args, **kwargs)
                
                # Extract search parameters and results
                search_params = {}
                result_count = 0
                
                if request:
                    search_params = dict(request.GET)
                
                # Try to extract result count
                if hasattr(result, 'count'):
                    result_count = result.count()
                elif hasattr(result, '__len__'):
                    result_count = len(result)
                elif hasattr(result, 'data') and hasattr(result.data, '__len__'):
                    result_count = len(result.data)
                
                # Log the search
                if user and request:
                    clinic = getattr(user, 'clinic', None)
                    if clinic:
                        audit_service.log_search_action(
                            user=user,
                            search_params=search_params,
                            result_count=result_count,
                            clinic=clinic,
                            request=request
                        )
                
                return result
                
            except Exception as e:
                # Log failed search
                clinic = getattr(user, 'clinic', None) if user else None
                
                if user and request and clinic:
                    audit_service.log_clinical_action(
                        action=f'{search_type}_FAILED',
                        user=user,
                        resource_type='CLINICAL_RECORD',
                        clinic=clinic,
                        request=request,
                        details={
                            'error': str(e),
                            'search_type': search_type,
                            'function_name': func.__name__,
                            'search_params': dict(request.GET) if request else {}
                        }
                    )
                
                raise
        
        return wrapper
    return decorator


def audit_export_action(export_type: str = 'CLINICAL_EXPORT'):
    """
    Decorator for export actions.
    
    Args:
        export_type: Type of export being performed
    
    Usage:
        @audit_export_action('FHIR_EXPORT')
        def export_fhir_data(request):
            # Export implementation
            return export_data
    """
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            request = None
            user = None
            
            # Extract request from args
            for arg in args:
                if isinstance(arg, HttpRequest):
                    request = arg
                    user = getattr(request, 'user', None)
                    break
            
            try:
                # Execute the function
                result = func(*args, **kwargs)
                
                # Extract export parameters and record count
                export_params = {}
                record_count = 0
                
                if request:
                    export_params = dict(request.GET)
                
                # Try to extract record count from result
                if hasattr(result, 'count'):
                    record_count = result.count()
                elif hasattr(result, '__len__'):
                    record_count = len(result)
                elif hasattr(result, 'data'):
                    if hasattr(result.data, '__len__'):
                        record_count = len(result.data)
                    elif isinstance(result.data, dict) and 'entry' in result.data:
                        record_count = len(result.data['entry'])
                
                # Log the export
                if user and request:
                    clinic = getattr(user, 'clinic', None)
                    if clinic:
                        audit_service.log_export_action(
                            user=user,
                            export_type=export_type.lower(),
                            export_params=export_params,
                            record_count=record_count,
                            clinic=clinic,
                            request=request
                        )
                
                return result
                
            except Exception as e:
                # Log failed export
                clinic = getattr(user, 'clinic', None) if user else None
                
                if user and request and clinic:
                    audit_service.log_clinical_action(
                        action=f'{export_type}_FAILED',
                        user=user,
                        resource_type='CLINICAL_RECORD',
                        clinic=clinic,
                        request=request,
                        details={
                            'error': str(e),
                            'export_type': export_type,
                            'function_name': func.__name__,
                            'export_params': dict(request.GET) if request else {}
                        }
                    )
                
                raise
        
        return wrapper
    return decorator


# Convenience decorators for common actions
audit_view = lambda: audit_clinical_action('CLINICAL_RECORD_VIEW', 'CLINICAL_RECORD', sensitive_data=True)
audit_create = lambda: audit_clinical_action('CLINICAL_RECORD_CREATE', 'CLINICAL_RECORD')
audit_update = lambda: audit_clinical_action('CLINICAL_RECORD_UPDATE', 'CLINICAL_RECORD', sensitive_data=True)
audit_delete = lambda: audit_clinical_action('CLINICAL_RECORD_DELETE', 'CLINICAL_RECORD', sensitive_data=True)

audit_document_view = lambda: audit_document_access('VIEW')
audit_document_download = lambda: audit_document_access('DOWNLOAD')
audit_document_upload = lambda: audit_clinical_action('DOCUMENT_UPLOAD', 'CLINICAL_DOCUMENT')

audit_search = lambda: audit_search_action('CLINICAL_SEARCH')
audit_fhir_export = lambda: audit_export_action('FHIR_EXPORT')


def audit_api_call(action: str = 'API_CALL', resource_type: str = None, 
                   sensitive_data: bool = False):
    """
    Decorator to audit API calls.
    
    Args:
        action: Action type for the API call
        resource_type: Resource type being accessed
        sensitive_data: Whether sensitive data is being accessed
    
    Usage:
        @audit_api_call('DOCUMENT_VIEW_API', 'CLINICAL_DOCUMENT', sensitive_data=True)
        def document_view_api(request, document_id):
            # API implementation
            pass
    """
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            # Extract request and user from arguments
            request = None
            user = None
            
            # Look for request in args
            for arg in args:
                if isinstance(arg, HttpRequest):
                    request = arg
                    user = getattr(request, 'user', None) if hasattr(request, 'user') else None
                    break
            
            # Extract resource ID from common patterns
            resource_id = kwargs.get('pk') or kwargs.get('id') or kwargs.get('document_id') or kwargs.get('record_id')
            
            # Get clinic context
            clinic = getattr(user, 'clinic', None) if user else None
            
            try:
                # Execute the function
                result = func(*args, **kwargs)
                
                # Log successful API call
                audit_service.log_clinical_action(
                    action=action,
                    user=user,
                    resource_type=resource_type,
                    resource_id=str(resource_id) if resource_id else None,
                    clinic=clinic,
                    request=request,
                    sensitive_data=sensitive_data,
                    details={
                        'function_name': func.__name__,
                        'module': func.__module__,
                        'api_call': True,
                        'success': True
                    }
                )
                
                return result
                
            except Exception as e:
                # Log failed API call
                audit_service.log_clinical_action(
                    action=f"{action}_FAILED",
                    user=user,
                    resource_type=resource_type,
                    resource_id=str(resource_id) if resource_id else None,
                    clinic=clinic,
                    request=request,
                    details={
                        'function_name': func.__name__,
                        'module': func.__module__,
                        'api_call': True,
                        'success': False,
                        'error': str(e)
                    }
                )
                
                raise
        
        return wrapper
    return decorator