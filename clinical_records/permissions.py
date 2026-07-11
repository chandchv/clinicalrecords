"""
Custom permissions for Clinical Records

This module contains custom permission classes to ensure proper tenant isolation
and access control for clinical records.
"""
from rest_framework import permissions
from django.core.exceptions import PermissionDenied


class TenantAwarePermission(permissions.BasePermission):
    """
    Permission class that ensures users can only access records from their current tenant.
    """
    
    def has_permission(self, request, view):
        """Check if user has permission to access the view"""
        if not request.user or not request.user.is_authenticated:
            return False
        
        # Check if user has a current tenant
        if hasattr(request.user, 'current_tenant') and request.user.current_tenant:
            return True
            
        # If user is a patient (has patient_id from token), allow access
        # Patients might not have a "current_tenant" context in the same way as staff
        if hasattr(request.user, 'patient_id') and request.user.patient_id:
            return True

        # Check session for patient_id (Session Auth support)
        if hasattr(request, 'session') and request.session.get('patient_id'):
            return True
            
        return False
    
    def has_object_permission(self, request, view, obj):
        """Check if user has permission to access the specific object"""
        if not request.user or not request.user.is_authenticated:
            return False
        
        obj_tenant_id = None
        
        # Get the tenant_id/clinic from the object
        if hasattr(obj, 'tenant_id'):
            obj_tenant_id = obj.tenant_id
        elif hasattr(obj, 'clinic'):
            if hasattr(obj.clinic, 'id'):
                obj_tenant_id = obj.clinic.id
            else:
                # obj.clinic might be the ID itself if not a foreign key object
                obj_tenant_id = obj.clinic
        elif hasattr(obj, 'clinical_record'):
            if hasattr(obj.clinical_record, 'tenant_id'):
                obj_tenant_id = obj.clinical_record.tenant_id
            elif hasattr(obj.clinical_record, 'clinic'):
                if hasattr(obj.clinical_record.clinic, 'id'):
                    obj_tenant_id = obj.clinical_record.clinic.id
                else:
                    obj_tenant_id = obj.clinical_record.clinic
        elif hasattr(obj, 'document') and hasattr(obj.document, 'clinical_record'):
            if hasattr(obj.document.clinical_record, 'tenant_id'):
                obj_tenant_id = obj.document.clinical_record.tenant_id
        
        # If we found a tenant_id, check it
        if obj_tenant_id is not None:
            # If user has current_tenant object
            if hasattr(request.user, 'current_tenant') and request.user.current_tenant:
                return str(obj_tenant_id) == str(request.user.current_tenant.id)
            # If user has tenant_id attribute directly (fallback)
            elif hasattr(request.user, 'tenant_id'):
                return str(obj_tenant_id) == str(request.user.tenant_id)
            
            # If user is a patient, maybe we relax tenant check if the record belongs to them?
            # But normally patients belong to a tenant.
            return False
            
        # Fallback to old logic if no tenant_id found (e.g. for objects with only 'clinic' property matching the exact object)
        if hasattr(obj, 'clinic'):
             return obj.clinic == request.user.current_tenant
             
        # If we can't determine the tenant, deny access
        return False


class ClinicalRecordPermission(TenantAwarePermission):
    """
    Permission class specifically for clinical records.
    """
    
    def has_object_permission(self, request, view, obj):
        """Check clinical record specific permissions"""
        # First check tenant isolation
        if not super().has_object_permission(request, view, obj):
            return False
        
        # Additional checks for confidential records
        if obj.is_confidential:
            # Only allow access if user has appropriate role or is the creator
            if obj.created_by == request.user:
                return True
            
            # TODO: Add role-based checks when role system is implemented
            # For now, allow access to all authenticated users in the same tenant
            return True
        
        # Check if consent is required
        if obj.requires_consent:
            # TODO: Implement consent checking logic
            # For now, allow access
            return True
        
        return True


class ClinicalRecordsPermission(TenantAwarePermission):
    """
    Permission class for clinical records (plural form used in some views).
    """
    
    def has_object_permission(self, request, view, obj):
        """Check clinical record specific permissions"""
        # First check tenant isolation
        if not super().has_object_permission(request, view, obj):
            return False
        
        # Additional checks for confidential records
        if hasattr(obj, 'is_confidential') and obj.is_confidential:
            # Only allow access if user has appropriate role or is the creator
            if hasattr(obj, 'created_by') and obj.created_by == request.user:
                return True
            
            # TODO: Add role-based checks when role system is implemented
            # For now, allow access to all authenticated users in the same tenant
            return True
        
        # Check if consent is required
        if hasattr(obj, 'requires_consent') and obj.requires_consent:
            # TODO: Implement consent checking logic
            # For now, allow access
            return True
        
        return True


class DocumentPermission(TenantAwarePermission):
    """
    Permission class for clinical documents.
    """
    
    def has_object_permission(self, request, view, obj):
        """Check document specific permissions"""
        # First check tenant isolation
        if not super().has_object_permission(request, view, obj):
            return False
        
        # Check if the associated clinical record allows access
        clinical_record = obj.clinical_record
        
        if clinical_record.is_confidential:
            # Only allow access if user has appropriate role or is the creator
            if clinical_record.created_by == request.user or obj.uploaded_by == request.user:
                return True
            
            # TODO: Add role-based checks when role system is implemented
            return True
        
        return True


class ReviewPermission(TenantAwarePermission):
    """
    Permission class for manual reviews.
    """
    
    def has_object_permission(self, request, view, obj):
        """Check review specific permissions"""
        # First check tenant isolation
        if not super().has_object_permission(request, view, obj):
            return False
        
        # Allow access if user is assigned to the review
        if obj.assigned_to == request.user:
            return True
        
        # Allow access if user created the review
        if obj.created_by == request.user:
            return True
        
        # TODO: Allow supervisors to access all reviews
        # For now, allow all authenticated users in the same tenant
        return True