"""
Django REST Framework permissions for clinical records.

This module provides custom permission classes that integrate with
the role-based access control system for API endpoints.
"""

import logging
from rest_framework import permissions
from rest_framework.request import Request
from rest_framework.views import APIView

from .minimal_access_control import access_control
from ..models import ClinicalRecord, ClinicalDocument
from ..services.simple_audit_service import audit_service

logger = logging.getLogger(__name__)


class ClinicalRecordPermission(permissions.BasePermission):
    """
    Permission class for clinical record operations.
    
    This permission class checks role-based access control for
    clinical record CRUD operations.
    """
    
    def has_permission(self, request: Request, view: APIView) -> bool:
        """
        Check if user has permission to access clinical records.
        
        Args:
            request: HTTP request
            view: API view being accessed
            
        Returns:
            True if permission granted
        """
        if not request.user or not request.user.is_authenticated:
            return False
        
        # Get clinic context
        clinic = getattr(request.user, 'clinic', None)
        if not clinic:
            return False
        
        # Check permissions based on HTTP method
        if request.method in permissions.SAFE_METHODS:
            # Read operations
            has_perm, reason = access_control.has_permission(
                request.user, 'can_view_all_patients', clinic=clinic
            )
        elif request.method == 'POST':
            # Create operations
            has_perm, reason = access_control.has_permission(
                request.user, 'can_edit_all_records', clinic=clinic
            )
        elif request.method in ['PUT', 'PATCH']:
            # Update operations
            has_perm, reason = access_control.has_permission(
                request.user, 'can_edit_all_records', clinic=clinic
            )
        elif request.method == 'DELETE':
            # Delete operations
            has_perm, reason = access_control.has_permission(
                request.user, 'can_delete_records', clinic=clinic
            )
        else:
            has_perm, reason = False, "Unknown HTTP method"
        
        if not has_perm:
            # Log unauthorized access attempt
            audit_service.log_unauthorized_access(
                user=request.user,
                resource_type='CLINICAL_RECORD',
                resource_id='',
                clinic=clinic,
                request=request,
                reason=reason
            )
        
        return has_perm
    
    def has_object_permission(self, request: Request, view: APIView, obj) -> bool:
        """
        Check if user has permission to access a specific clinical record.
        
        Args:
            request: HTTP request
            view: API view being accessed
            obj: Clinical record object
            
        Returns:
            True if permission granted
        """
        if not isinstance(obj, ClinicalRecord):
            return False
        
        # Check record-level access
        can_access, reason = access_control.can_access_record(request.user, obj)
        
        if not can_access:
            # Log unauthorized access attempt
            audit_service.log_unauthorized_access(
                user=request.user,
                resource_type='CLINICAL_RECORD',
                resource_id=str(obj.id),
                clinic=obj.clinic,
                request=request,
                reason=reason
            )
        
        return can_access


class ClinicalDocumentPermission(permissions.BasePermission):
    """
    Permission class for clinical document operations.
    
    This permission class checks role-based access control for
    clinical document operations including upload, download, and modification.
    """
    
    def has_permission(self, request: Request, view: APIView) -> bool:
        """
        Check if user has permission to access clinical documents.
        
        Args:
            request: HTTP request
            view: API view being accessed
            
        Returns:
            True if permission granted
        """
        if not request.user or not request.user.is_authenticated:
            return False
        
        # Get clinic context
        clinic = getattr(request.user, 'clinic', None)
        if not clinic:
            return False
        
        # Check permissions based on HTTP method and view action
        action = getattr(view, 'action', None)
        
        if request.method in permissions.SAFE_METHODS or action in ['list', 'retrieve']:
            # Read operations
            has_perm, reason = access_control.has_permission(
                request.user, 'can_view_all_patients', clinic=clinic
            )
        elif request.method == 'POST' or action == 'create':
            # Upload operations
            has_perm, reason = access_control.has_permission(
                request.user, 'can_upload_documents', clinic=clinic
            )
        elif action == 'download':
            # Download operations
            has_perm, reason = access_control.has_permission(
                request.user, 'can_download_documents', clinic=clinic
            )
        elif request.method in ['PUT', 'PATCH'] or action == 'update':
            # Update operations
            has_perm, reason = access_control.has_permission(
                request.user, 'can_edit_all_records', clinic=clinic
            )
        elif request.method == 'DELETE' or action == 'destroy':
            # Delete operations
            has_perm, reason = access_control.has_permission(
                request.user, 'can_delete_records', clinic=clinic
            )
        else:
            has_perm, reason = True, "Default allow for unknown action"
        
        if not has_perm:
            # Log unauthorized access attempt
            audit_service.log_unauthorized_access(
                user=request.user,
                resource_type='CLINICAL_DOCUMENT',
                resource_id='',
                clinic=clinic,
                request=request,
                reason=reason
            )
        
        return has_perm
    
    def has_object_permission(self, request: Request, view: APIView, obj) -> bool:
        """
        Check if user has permission to access a specific clinical document.
        
        Args:
            request: HTTP request
            view: API view being accessed
            obj: Clinical document object
            
        Returns:
            True if permission granted
        """
        if not isinstance(obj, ClinicalDocument):
            return False
        
        # Determine action type
        action = getattr(view, 'action', None)
        
        if request.method in permissions.SAFE_METHODS or action in ['list', 'retrieve']:
            action_type = 'view'
        elif action == 'download':
            action_type = 'download'
        elif request.method in ['PUT', 'PATCH'] or action == 'update':
            action_type = 'edit'
        elif request.method == 'DELETE' or action == 'destroy':
            action_type = 'delete'
        else:
            action_type = 'view'
        
        # Check document-level access
        can_access, reason = access_control.can_access_document(
            request.user, obj, action_type
        )
        
        if not can_access:
            # Log unauthorized access attempt
            audit_service.log_unauthorized_access(
                user=request.user,
                resource_type='CLINICAL_DOCUMENT',
                resource_id=str(obj.id),
                clinic=obj.clinical_record.clinic,
                request=request,
                reason=reason
            )
        
        return can_access


class EmergencyAccessPermission(permissions.BasePermission):
    """
    Permission class for emergency access operations.
    
    This permission class allows emergency access to bypass normal
    access controls with proper justification and audit logging.
    """
    
    def has_permission(self, request: Request, view: APIView) -> bool:
        """
        Check if user can initiate emergency access.
        
        Args:
            request: HTTP request
            view: API view being accessed
            
        Returns:
            True if permission granted
        """
        if not request.user or not request.user.is_authenticated:
            return False
        
        # Check if user has emergency role
        clinic = getattr(request.user, 'clinic', None)
        if not clinic:
            return False
        
        roles = access_control.get_user_roles(request.user, clinic)
        has_emergency_role = any(role.is_emergency_role for role in roles)
        
        if not has_emergency_role:
            # Log unauthorized emergency access attempt
            audit_service.log_unauthorized_access(
                user=request.user,
                resource_type='EMERGENCY_ACCESS',
                resource_id='',
                clinic=clinic,
                request=request,
                reason="User does not have emergency access role"
            )
        
        return has_emergency_role
    
    def has_object_permission(self, request: Request, view: APIView, obj) -> bool:
        """
        Check if user can access emergency access record.
        
        Args:
            request: HTTP request
            view: API view being accessed
            obj: Emergency access object
            
        Returns:
            True if permission granted
        """
        # Users can only access their own emergency access records
        # or if they have permission management rights
        if obj.user == request.user:
            return True
        
        # Check if user can manage permissions
        clinic = getattr(request.user, 'clinic', None)
        if clinic:
            has_perm, _ = access_control.has_permission(
                request.user, 'can_manage_permissions', clinic=clinic
            )
            return has_perm
        
        return False


class PatientConsentPermission(permissions.BasePermission):
    """
    Permission class for patient consent operations.
    
    This permission class manages access to patient consent records
    with appropriate privacy protections.
    """
    
    def has_permission(self, request: Request, view: APIView) -> bool:
        """
        Check if user can access patient consent records.
        
        Args:
            request: HTTP request
            view: API view being accessed
            
        Returns:
            True if permission granted
        """
        if not request.user or not request.user.is_authenticated:
            return False
        
        # Get clinic context
        clinic = getattr(request.user, 'clinic', None)
        if not clinic:
            return False
        
        # Check if user has permission to view patient records
        has_perm, reason = access_control.has_permission(
            request.user, 'can_view_all_patients', clinic=clinic
        )
        
        if not has_perm:
            # Log unauthorized access attempt
            audit_service.log_unauthorized_access(
                user=request.user,
                resource_type='PATIENT_CONSENT',
                resource_id='',
                clinic=clinic,
                request=request,
                reason=reason
            )
        
        return has_perm
    
    def has_object_permission(self, request: Request, view: APIView, obj) -> bool:
        """
        Check if user can access a specific patient consent record.
        
        Args:
            request: HTTP request
            view: API view being accessed
            obj: Patient consent object
            
        Returns:
            True if permission granted
        """
        # Check if user can access the patient's records
        can_access, reason = access_control.can_access_patient_records(
            request.user, obj.patient
        )
        
        if not can_access:
            # Log unauthorized access attempt
            audit_service.log_unauthorized_access(
                user=request.user,
                resource_type='PATIENT_CONSENT',
                resource_id=str(obj.id),
                clinic=obj.clinic,
                request=request,
                reason=reason
            )
        
        return can_access


class RoleManagementPermission(permissions.BasePermission):
    """
    Permission class for clinical role management operations.
    
    This permission class controls who can create, modify, and assign
    clinical roles within a clinic.
    """
    
    def has_permission(self, request: Request, view: APIView) -> bool:
        """
        Check if user can manage clinical roles.
        
        Args:
            request: HTTP request
            view: API view being accessed
            
        Returns:
            True if permission granted
        """
        if not request.user or not request.user.is_authenticated:
            return False
        
        # Get clinic context
        clinic = getattr(request.user, 'clinic', None)
        if not clinic:
            return False
        
        # Check if user has permission management rights
        has_perm, reason = access_control.has_permission(
            request.user, 'can_manage_permissions', clinic=clinic
        )
        
        if not has_perm:
            # Log unauthorized access attempt
            audit_service.log_unauthorized_access(
                user=request.user,
                resource_type='CLINICAL_ROLE',
                resource_id='',
                clinic=clinic,
                request=request,
                reason=reason
            )
        
        return has_perm
    
    def has_object_permission(self, request: Request, view: APIView, obj) -> bool:
        """
        Check if user can access a specific clinical role.
        
        Args:
            request: HTTP request
            view: API view being accessed
            obj: Clinical role object
            
        Returns:
            True if permission granted
        """
        # Users can only manage roles within their clinic
        if obj.clinic != getattr(request.user, 'clinic', None):
            return False
        
        # Check permission management rights
        has_perm, _ = access_control.has_permission(
            request.user, 'can_manage_permissions', clinic=obj.clinic
        )
        
        return has_perm


class SharePermission(permissions.BasePermission):
    """
    Permission class for record sharing operations.
    
    This permission class controls who can create and manage
    share tokens for clinical records.
    """
    
    def has_permission(self, request: Request, view: APIView) -> bool:
        """
        Check if user can create share tokens.
        
        Args:
            request: HTTP request
            view: API view being accessed
            
        Returns:
            True if permission granted
        """
        if not request.user or not request.user.is_authenticated:
            return False
        
        # Get clinic context
        clinic = getattr(request.user, 'clinic', None)
        if not clinic:
            return False
        
        # Check if user has sharing permissions
        has_perm, reason = access_control.has_permission(
            request.user, 'can_share_records', clinic=clinic
        )
        
        if not has_perm:
            # Log unauthorized access attempt
            audit_service.log_unauthorized_access(
                user=request.user,
                resource_type='SHARE_TOKEN',
                resource_id='',
                clinic=clinic,
                request=request,
                reason=reason
            )
        
        return has_perm
    
    def has_object_permission(self, request: Request, view: APIView, obj) -> bool:
        """
        Check if user can access a specific share token.
        
        Args:
            request: HTTP request
            view: API view being accessed
            obj: Share token object
            
        Returns:
            True if permission granted
        """
        # Check if user can access the underlying record
        can_access, reason = access_control.can_access_record(
            request.user, obj.clinical_record
        )
        
        if not can_access:
            # Log unauthorized access attempt
            audit_service.log_unauthorized_access(
                user=request.user,
                resource_type='SHARE_TOKEN',
                resource_id=str(obj.id),
                clinic=obj.clinical_record.clinic,
                request=request,
                reason=reason
            )
        
        return can_access


class ExportPermission(permissions.BasePermission):
    """
    Permission class for data export operations.
    
    This permission class controls who can export clinical data
    in various formats (FHIR, CSV, etc.).
    """
    
    def has_permission(self, request: Request, view: APIView) -> bool:
        """
        Check if user can export clinical data.
        
        Args:
            request: HTTP request
            view: API view being accessed
            
        Returns:
            True if permission granted
        """
        if not request.user or not request.user.is_authenticated:
            return False
        
        # Get clinic context
        clinic = getattr(request.user, 'clinic', None)
        if not clinic:
            return False
        
        # Check if user has export permissions
        has_perm, reason = access_control.has_permission(
            request.user, 'can_export_data', clinic=clinic
        )
        
        if not has_perm:
            # Log unauthorized access attempt
            audit_service.log_unauthorized_access(
                user=request.user,
                resource_type='DATA_EXPORT',
                resource_id='',
                clinic=clinic,
                request=request,
                reason=reason
            )
        
        return has_perm


class DocumentPermission(permissions.BasePermission):
    """
    Permission class for clinical documents.
    """
    
    def has_permission(self, request: Request, view: APIView) -> bool:
        """
        Check if user has permission to access clinical documents.
        
        Args:
            request: HTTP request
            view: API view being accessed
            
        Returns:
            True if permission granted
        """
        if not request.user or not request.user.is_authenticated:
            return False
        
        # Get clinic context
        clinic = getattr(request.user, 'clinic', None)
        if not clinic:
            return False
        
        # Check permissions based on HTTP method
        if request.method in permissions.SAFE_METHODS:
            # Read operations
            has_perm, reason = access_control.has_permission(
                request.user, 'can_view_all_patients', clinic=clinic
            )
        elif request.method == 'POST':
            # Create operations
            has_perm, reason = access_control.has_permission(
                request.user, 'can_edit_all_records', clinic=clinic
            )
        elif request.method in ['PUT', 'PATCH']:
            # Update operations
            has_perm, reason = access_control.has_permission(
                request.user, 'can_edit_all_records', clinic=clinic
            )
        elif request.method == 'DELETE':
            # Delete operations
            has_perm, reason = access_control.has_permission(
                request.user, 'can_delete_records', clinic=clinic
            )
        else:
            has_perm, reason = False, "Unknown HTTP method"
        
        if not has_perm:
            # Log unauthorized access attempt
            audit_service.log_unauthorized_access(
                user=request.user,
                resource_type='CLINICAL_DOCUMENT',
                resource_id='',
                clinic=clinic,
                request=request,
                reason=reason
            )
        
        return has_perm
    
    def has_object_permission(self, request: Request, view: APIView, obj) -> bool:
        """
        Check if user has permission to access a specific clinical document.
        
        Args:
            request: HTTP request
            view: API view being accessed
            obj: Clinical document object
            
        Returns:
            True if permission granted
        """
        if not isinstance(obj, ClinicalDocument):
            return False
        
        # Check document-level access
        can_access, reason = access_control.can_access_document(request.user, obj)
        
        if not can_access:
            # Log unauthorized access attempt
            audit_service.log_unauthorized_access(
                user=request.user,
                resource_type='CLINICAL_DOCUMENT',
                resource_id=str(obj.id),
                clinic=obj.clinical_record.clinic if hasattr(obj, 'clinical_record') else None,
                request=request,
                reason=reason
            )
        
        return can_access


class ClinicalRecordsPermission(permissions.BasePermission):
    """
    Permission class for clinical records (plural form used in some views).
    """
    
    def has_permission(self, request: Request, view: APIView) -> bool:
        """
        Check if user has permission to access clinical records.
        
        Args:
            request: HTTP request
            view: API view being accessed
            
        Returns:
            True if permission granted
        """
        if not request.user or not request.user.is_authenticated:
            return False
        
        # Get clinic context
        clinic = getattr(request.user, 'clinic', None)
        if not clinic:
            return False
        
        # Check permissions based on HTTP method
        if request.method in permissions.SAFE_METHODS:
            # Read operations
            has_perm, reason = access_control.has_permission(
                request.user, 'can_view_all_patients', clinic=clinic
            )
        elif request.method == 'POST':
            # Create operations
            has_perm, reason = access_control.has_permission(
                request.user, 'can_edit_all_records', clinic=clinic
            )
        elif request.method in ['PUT', 'PATCH']:
            # Update operations
            has_perm, reason = access_control.has_permission(
                request.user, 'can_edit_all_records', clinic=clinic
            )
        elif request.method == 'DELETE':
            # Delete operations
            has_perm, reason = access_control.has_permission(
                request.user, 'can_delete_records', clinic=clinic
            )
        else:
            has_perm, reason = False, "Unknown HTTP method"
        
        if not has_perm:
            # Log unauthorized access attempt
            audit_service.log_unauthorized_access(
                user=request.user,
                resource_type='CLINICAL_RECORDS',
                resource_id='',
                clinic=clinic,
                request=request,
                reason=reason
            )
        
        return has_perm
    
    def has_object_permission(self, request: Request, view: APIView, obj) -> bool:
        """
        Check if user has permission to access a specific clinical record.
        
        Args:
            request: HTTP request
            view: API view being accessed
            obj: Clinical record object
            
        Returns:
            True if permission granted
        """
        if not isinstance(obj, ClinicalRecord):
            return False
        
        # Check record-level access
        can_access, reason = access_control.can_access_record(request.user, obj)
        
        if not can_access:
            # Log unauthorized access attempt
            audit_service.log_unauthorized_access(
                user=request.user,
                resource_type='CLINICAL_RECORDS',
                resource_id=str(obj.id),
                clinic=obj.clinic,
                request=request,
                reason=reason
            )
        
        return can_access


class CanViewRecords(permissions.BasePermission):
    """
    Permission class for viewing clinical records.
    """
    
    def has_permission(self, request: Request, view: APIView) -> bool:
        """
        Check if user has permission to view clinical records.
        
        Args:
            request: HTTP request
            view: API view being accessed
            
        Returns:
            True if permission granted
        """
        if not request.user or not request.user.is_authenticated:
            return False
        
        # Get clinic context
        clinic = getattr(request.user, 'clinic', None)
        if not clinic:
            return False
        
        # Check if user has view permissions
        has_perm, reason = access_control.has_permission(
            request.user, 'can_view_all_patients', clinic=clinic
        )
        
        if not has_perm:
            # Log unauthorized access attempt
            audit_service.log_unauthorized_access(
                user=request.user,
                resource_type='VIEW_RECORDS',
                resource_id='',
                clinic=clinic,
                request=request,
                reason=reason
            )
        
        return has_perm
    
    def has_object_permission(self, request: Request, view: APIView, obj) -> bool:
        """
        Check if user has permission to view a specific clinical record.
        
        Args:
            request: HTTP request
            view: API view being accessed
            obj: Clinical record object
            
        Returns:
            True if permission granted
        """
        if not isinstance(obj, ClinicalRecord):
            return False
        
        # Check record-level access
        can_access, reason = access_control.can_access_record(request.user, obj)
        
        if not can_access:
            # Log unauthorized access attempt
            audit_service.log_unauthorized_access(
                user=request.user,
                resource_type='VIEW_RECORDS',
                resource_id=str(obj.id),
                clinic=obj.clinic,
                request=request,
                reason=reason
            )
        
        return can_access


class CanShareRecords(permissions.BasePermission):
    """
    Permission class for sharing clinical records.
    """
    
    def has_permission(self, request: Request, view: APIView) -> bool:
        """
        Check if user has permission to share clinical records.
        
        Args:
            request: HTTP request
            view: API view being accessed
            
        Returns:
            True if permission granted
        """
        if not request.user or not request.user.is_authenticated:
            return False
        
        # Get clinic context
        clinic = getattr(request.user, 'clinic', None)
        if not clinic:
            return False
        
        # Check if user has share permissions
        has_perm, reason = access_control.has_permission(
            request.user, 'can_share_records', clinic=clinic
        )
        
        if not has_perm:
            # Log unauthorized access attempt
            audit_service.log_unauthorized_access(
                user=request.user,
                resource_type='SHARE_RECORDS',
                resource_id='',
                clinic=clinic,
                request=request,
                reason=reason
            )
        
        return has_perm
    
    def has_object_permission(self, request: Request, view: APIView, obj) -> bool:
        """
        Check if user has permission to share a specific clinical record.
        
        Args:
            request: HTTP request
            view: API view being accessed
            obj: Clinical record object
            
        Returns:
            True if permission granted
        """
        if not isinstance(obj, ClinicalRecord):
            return False
        
        # Check record-level access
        can_access, reason = access_control.can_access_record(request.user, obj)
        
        if not can_access:
            # Log unauthorized access attempt
            audit_service.log_unauthorized_access(
                user=request.user,
                resource_type='SHARE_RECORDS',
                resource_id=str(obj.id),
                clinic=obj.clinic,
                request=request,
                reason=reason
            )
        
        return can_access


class TenantPermission(permissions.BasePermission):
    """
    Permission class for tenant-aware access control.
    """
    
    def has_permission(self, request: Request, view: APIView) -> bool:
        """
        Check if user has permission to access the view.
        
        Args:
            request: HTTP request
            view: API view being accessed
            
        Returns:
            True if permission granted
        """
        if not request.user or not request.user.is_authenticated:
            return False
        
        # Get clinic context
        clinic = getattr(request.user, 'clinic', None)
        if not clinic:
            return False
        
        # Basic tenant validation - user must have a clinic
        return True
    
    def has_object_permission(self, request: Request, view: APIView, obj) -> bool:
        """
        Check if user has permission to access a specific object.
        
        Args:
            request: HTTP request
            view: API view being accessed
            obj: Object being accessed
            
        Returns:
            True if permission granted
        """
        if not request.user or not request.user.is_authenticated:
            return False
        
        # Get clinic context
        clinic = getattr(request.user, 'clinic', None)
        if not clinic:
            return False
        
        # Check if object belongs to the same clinic
        if hasattr(obj, 'clinic'):
            return obj.clinic == clinic
        
        # If object doesn't have clinic attribute, allow access
        # (this is a fallback for objects that don't implement tenant isolation)
        return True


class CanEditRecords(permissions.BasePermission):
    """
    Permission class for editing clinical records.
    """
    
    def has_permission(self, request: Request, view: APIView) -> bool:
        """
        Check if user has permission to edit clinical records.
        
        Args:
            request: HTTP request
            view: API view being accessed
            
        Returns:
            True if permission granted
        """
        if not request.user or not request.user.is_authenticated:
            return False
        
        # Get clinic context
        clinic = getattr(request.user, 'clinic', None)
        if not clinic:
            return False
        
        # Check if user has edit permissions
        has_perm, reason = access_control.has_permission(
            request.user, 'can_edit_all_records', clinic=clinic
        )
        
        if not has_perm:
            # Log unauthorized access attempt
            audit_service.log_unauthorized_access(
                user=request.user,
                resource_type='EDIT_RECORDS',
                resource_id='',
                clinic=clinic,
                request=request,
                reason=reason
            )
        
        return has_perm
    
    def has_object_permission(self, request: Request, view: APIView, obj) -> bool:
        """
        Check if user has permission to edit a specific clinical record.
        
        Args:
            request: HTTP request
            view: API view being accessed
            obj: Clinical record object
            
        Returns:
            True if permission granted
        """
        if not isinstance(obj, ClinicalRecord):
            return False
        
        # Check record-level access
        can_access, reason = access_control.can_access_record(request.user, obj)
        
        if not can_access:
            # Log unauthorized access attempt
            audit_service.log_unauthorized_access(
                user=request.user,
                resource_type='EDIT_RECORDS',
                resource_id=str(obj.id),
                clinic=obj.clinic,
                request=request,
                reason=reason
            )
        
        return can_access