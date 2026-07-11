"""
Simplified Access Control for Clinical Records Service

This module provides basic access control without external dependencies.
"""

import logging
from enum import Enum
from typing import Dict, Any, Optional, List
from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied
from django.db.models import Q

from ..models import ClinicalRecord, ClinicalDocument, Patient

User = get_user_model()
logger = logging.getLogger(__name__)


class AccessLevel(Enum):
    """Access levels for clinical records."""
    NONE = "none"
    READ = "read"
    WRITE = "write"
    ADMIN = "admin"


class ClinicalRole(Enum):
    """Clinical roles in the system."""
    PATIENT = "patient"
    DOCTOR = "doctor"
    NURSE = "nurse"
    ADMIN = "admin"


class SimpleAccessControl:
    """
    Simplified access control system for clinical records.
    """
    
    # Role-based permissions matrix
    ROLE_PERMISSIONS = {
        ClinicalRole.PATIENT: {
            'own_records': AccessLevel.READ,
            'own_documents': AccessLevel.READ,
            'share_own_records': AccessLevel.WRITE,
        },
        ClinicalRole.DOCTOR: {
            'patient_records': AccessLevel.READ,
            'patient_documents': AccessLevel.READ,
            'create_records': AccessLevel.WRITE,
            'upload_documents': AccessLevel.WRITE,
        },
        ClinicalRole.NURSE: {
            'assigned_patient_records': AccessLevel.READ,
            'create_records': AccessLevel.WRITE,
        },
        ClinicalRole.ADMIN: {
            'all_records': AccessLevel.ADMIN,
            'all_documents': AccessLevel.ADMIN,
            'system_management': AccessLevel.ADMIN,
        }
    }
    
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
            
            # Check role-based permissions
            user_role = self._get_user_role(user)
            if user_role in self.ROLE_PERMISSIONS:
                permissions = self.ROLE_PERMISSIONS[user_role]
                
                if action == 'read':
                    return any(perm in permissions for perm in ['own_records', 'patient_records', 'all_records'])
                elif action == 'write':
                    return any(perm in permissions for perm in ['create_records', 'all_records'])
            
            return False
            
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
            
            # Check role-based permissions
            user_role = self._get_user_role(user)
            if user_role in self.ROLE_PERMISSIONS:
                permissions = self.ROLE_PERMISSIONS[user_role]
                
                if action == 'read':
                    return any(perm in permissions for perm in ['own_records', 'patient_records', 'all_records'])
                elif action == 'write':
                    return any(perm in permissions for perm in ['create_records', 'all_records'])
            
            return False
            
        except Exception as e:
            self.logger.error(f"Error checking patient access: {e}")
            return False
    
    def _get_user_role(self, user: User) -> ClinicalRole:
        """
        Determine user's clinical role.
        
        Args:
            user: User to check
            
        Returns:
            Clinical role of the user
        """
        try:
            # Check if user has a role attribute
            if hasattr(user, 'role'):
                role_mapping = {
                    'patient': ClinicalRole.PATIENT,
                    'doctor': ClinicalRole.DOCTOR,
                    'nurse': ClinicalRole.NURSE,
                    'admin': ClinicalRole.ADMIN,
                }
                return role_mapping.get(user.role, ClinicalRole.PATIENT)
            
            # Check if user is staff/admin
            if user.is_superuser:
                return ClinicalRole.ADMIN
            elif user.is_staff:
                return ClinicalRole.DOCTOR
            
            # Default to patient role
            return ClinicalRole.PATIENT
            
        except Exception as e:
            self.logger.error(f"Error determining user role: {e}")
            return ClinicalRole.PATIENT
    
    def get_accessible_records(self, user: User, queryset=None) -> List[ClinicalRecord]:
        """
        Get records accessible to the user.
        
        Args:
            user: User requesting records
            queryset: Base queryset to filter
            
        Returns:
            List of accessible records
        """
        try:
            if queryset is None:
                queryset = ClinicalRecord.objects.all()
            
            # Admin users can see all records
            if user.is_superuser:
                return list(queryset)
            
            # Filter by tenant
            if hasattr(user, 'current_tenant') and user.current_tenant:
                queryset = queryset.filter(tenant_id=user.current_tenant)
            
            # Filter by patient access
            accessible_records = []
            for record in queryset:
                if self.check_record_access(user, record, 'read'):
                    accessible_records.append(record)
            
            return accessible_records
            
        except Exception as e:
            self.logger.error(f"Error getting accessible records: {e}")
            return []


# Global access control instance
access_control = SimpleAccessControl()
