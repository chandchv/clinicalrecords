"""
Minimal Access Control for Clinical Records Service

This module provides basic access control without external dependencies.
"""

import logging
from typing import Dict, Any, Optional, List
from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied

from ..models import ClinicalRecord, ClinicalDocument, Patient

User = get_user_model()
logger = logging.getLogger(__name__)


class MinimalAccessControl:
    """
    Minimal access control system for clinical records.
    """
    
    def __init__(self):
        self.logger = logger
    
    def check_record_access(self, user: User, record: ClinicalRecord, action: str = 'read') -> bool:
        """
        Check if user has access to a specific clinical record.
        
        Args:
            user: User requesting access
            record: Clinical record to check
            action: Action being performed ('read', 'write', 'delete')
            
        Returns:
            True if access is granted, False otherwise
        """
        try:
            # Check if user is authenticated
            if not user.is_authenticated:
                return False
            
            # Admin users have full access
            if user.is_superuser:
                return True
            
            # Check tenant isolation
            if hasattr(user, 'current_tenant') and user.current_tenant:
                if record.tenant_id != user.current_tenant:
                    return False
            
            # Check if user is the patient
            if record.patient and hasattr(user, 'patient'):
                if user.patient and record.patient.rxbackend_patient_id == user.patient.id:
                    return True
            
            # For now, allow all authenticated users
            return True
            
        except Exception as e:
            self.logger.error(f"Error checking record access: {e}")
            return False
    
    def check_document_access(self, user: User, document: ClinicalDocument, action: str = 'read') -> bool:
        """
        Check if user has access to a specific clinical document.
        
        Args:
            user: User requesting access
            document: Clinical document to check
            action: Action being performed ('read', 'write', 'delete')
            
        Returns:
            True if access is granted, False otherwise
        """
        try:
            # Check if user is authenticated
            if not user.is_authenticated:
                return False
            
            # Admin users have full access
            if user.is_superuser:
                return True
            
            # Check tenant isolation
            if hasattr(user, 'current_tenant') and user.current_tenant:
                if document.tenant_id != user.current_tenant:
                    return False
            
            # Check access to the associated record
            if document.clinical_record:
                return self.check_record_access(user, document.clinical_record, action)
            
            return False
            
        except Exception as e:
            self.logger.error(f"Error checking document access: {e}")
            return False
    
    def check_patient_access(self, user: User, patient: Patient, action: str = 'read') -> bool:
        """
        Check if user has access to a specific patient's records.
        
        Args:
            user: User requesting access
            patient: Patient to check
            action: Action being performed ('read', 'write', 'delete')
            
        Returns:
            True if access is granted, False otherwise
        """
        try:
            # Check if user is authenticated
            if not user.is_authenticated:
                return False
            
            # Admin users have full access
            if user.is_superuser:
                return True
            
            # Check tenant isolation
            if hasattr(user, 'current_tenant') and user.current_tenant:
                if patient.tenant_id != user.current_tenant:
                    return False
            
            # Check if user is the patient
            if hasattr(user, 'patient'):
                if user.patient and patient.rxbackend_patient_id == user.patient.id:
                    return True
            
            # For now, allow all authenticated users
            return True
            
        except Exception as e:
            self.logger.error(f"Error checking patient access: {e}")
            return False

    def has_permission(self, user: User, permission: str, clinic: Optional[Any] = None):
        """
        Check if user has a specific permission in a clinic.
        """
        if not user or not user.is_authenticated:
            return False, "User is not authenticated"
            
        if user.is_superuser:
            return True, "Superuser access"
            
        # Tenant/Clinic validation:
        if clinic:
            clinic_id = getattr(clinic, 'id', clinic)
            user_tenant_id = None
            if hasattr(user, 'current_tenant') and user.current_tenant:
                user_tenant_id = getattr(user.current_tenant, 'id', user.current_tenant)
            elif hasattr(user, 'tenant_id'):
                user_tenant_id = user.tenant_id
                
            if user_tenant_id and str(clinic_id) != str(user_tenant_id):
                return False, f"User tenant context mismatch: user is {user_tenant_id}, clinic is {clinic_id}"
        
        # Allow access based on role
        legacy_role = getattr(user, 'legacy_role', None)
        
        if not legacy_role:
            if user.is_staff:
                legacy_role = 'STAFF'
            elif hasattr(user, 'patient_id') and user.patient_id:
                legacy_role = 'PATIENT'
        
        # For patients: allow viewing/editing own records
        if legacy_role == 'PATIENT':
            if permission in ['can_view_all_patients', 'can_edit_all_records', 'can_view_records', 'can_create_records', 'can_edit_records']:
                return True, "Patient own record access"
            return False, f"Patient role not authorized for: {permission}"
            
        # For doctors and staff: allow all operations
        if legacy_role in ['DOCTOR', 'STAFF', 'ADMIN', 'SUPERUSER']:
            return True, "Staff/Doctor access granted"
            
        return True, "Authenticated user default access"


# Global access control instance
access_control = MinimalAccessControl()
