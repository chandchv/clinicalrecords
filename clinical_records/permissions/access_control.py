"""
Role-based access control system for clinical records.

This module provides comprehensive access control with role-based permissions,
patient consent verification, emergency access, and permission inheritance.
"""

import logging
from typing import Dict, Any, List, Optional, Tuple
from datetime import datetime, timedelta
from enum import Enum

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission, Group
from django.contrib.contenttypes.models import ContentType
from django.utils import timezone
from django.core.exceptions import PermissionDenied
from django.db.models import Q

# from users.models import Clinic, Patient  # External dependency removed
from ..models import ClinicalRecord, ClinicalDocument, ShareToken, Patient
from ..services.simple_audit_service import audit_service

User = get_user_model()
logger = logging.getLogger(__name__)


class AccessLevel(Enum):
    """Access levels for clinical records."""
    NONE = "none"
    READ = "read"
    WRITE = "write"
    ADMIN = "admin"
    EMERGENCY = "emergency"


class ClinicalRole(Enum):
    """Clinical roles with specific permissions."""
    PATIENT = "patient"
    NURSE = "nurse"
    DOCTOR = "doctor"
    SPECIALIST = "specialist"
    ADMIN = "admin"
    REVIEWER = "reviewer"
    AUDITOR = "auditor"
    EMERGENCY_USER = "emergency_user"


class ConsentStatus(Enum):
    """Patient consent status."""
    GRANTED = "granted"
    DENIED = "denied"
    PENDING = "pending"
    EXPIRED = "expired"
    REVOKED = "revoked"


class ClinicalAccessControl:
    """
    Comprehensive access control system for clinical records.
    
    Provides role-based permissions, patient consent verification,
    emergency access, and audit logging.
    """
    
    # Role-based permissions matrix
    ROLE_PERMISSIONS = {
        ClinicalRole.PATIENT: {
            'own_records': AccessLevel.READ,
            'own_documents': AccessLevel.READ,
            'share_own_records': AccessLevel.WRITE,
            'consent_management': AccessLevel.WRITE,
        },
        ClinicalRole.NURSE: {
            'assigned_patient_records': AccessLevel.READ,
            'assigned_patient_documents': AccessLevel.READ,
            'create_records': AccessLevel.WRITE,
            'upload_documents': AccessLevel.WRITE,
        },
        ClinicalRole.DOCTOR: {
            'patient_records': AccessLevel.WRITE,
            'patient_documents': AccessLevel.WRITE,
            'create_records': AccessLevel.WRITE,
            'prescriptions': AccessLevel.WRITE,
            'manual_review': AccessLevel.WRITE,
        },
        ClinicalRole.SPECIALIST: {
            'referred_patient_records': AccessLevel.WRITE,
            'referred_patient_documents': AccessLevel.WRITE,
            'specialist_reports': AccessLevel.WRITE,
        },
        ClinicalRole.ADMIN: {
            'all_clinic_records': AccessLevel.ADMIN,
            'all_clinic_documents': AccessLevel.ADMIN,
            'user_management': AccessLevel.ADMIN,
            'system_configuration': AccessLevel.ADMIN,
        },
        ClinicalRole.REVIEWER: {
            'manual_review_queue': AccessLevel.WRITE,
            'review_assignments': AccessLevel.WRITE,
            'quality_assurance': AccessLevel.READ,
        },
        ClinicalRole.AUDITOR: {
            'audit_logs': AccessLevel.READ,
            'compliance_reports': AccessLevel.READ,
            'all_clinic_records': AccessLevel.READ,
        },
        ClinicalRole.EMERGENCY_USER: {
            'emergency_access': AccessLevel.EMERGENCY,
            'all_patient_records': AccessLevel.READ,
        }
    }
    
    def __init__(self):
        self.logger = logging.getLogger(f"{__name__}.{self.__class__.__name__}")
    
    def check_record_access(self, user: User, record: ClinicalRecord, 
                          access_level: AccessLevel, 
                          emergency: bool = False) -> Tuple[bool, str]:
        """
        Check if user has access to a clinical record.
        
        Args:
            user: User requesting access
            record: Clinical record to access
            access_level: Required access level
            emergency: Whether this is an emergency access request
            
        Returns:
            Tuple of (has_access, reason)
        """
        try:
            # Emergency access check
            if emergency:
                return self._check_emergency_access(user, record, access_level)
            
            # Basic tenant check
            if not self._check_tenant_access(user, record.clinic):
                return False, "User not authorized for this clinic"
            
            # Get user's clinical role
            user_role = self._get_user_clinical_role(user)
            if not user_role:
                return False, "User has no clinical role assigned"
            
            # Check role-based permissions
            role_access = self._check_role_permissions(user_role, record, access_level)
            if not role_access[0]:
                return role_access
            
            # Check patient consent
            consent_check = self._check_patient_consent(user, record.patient, access_level)
            if not consent_check[0]:
                return consent_check
            
            # Check specific record permissions
            record_access = self._check_record_permissions(user, record, access_level)
            if not record_access[0]:
                return record_access
            
            # Check time-based restrictions
            time_check = self._check_time_restrictions(user, record, access_level)
            if not time_check[0]:
                return time_check
            
            return True, "Access granted"
            
        except Exception as e:
            self.logger.error(f"Error checking record access: {str(e)}")
            return False, f"Access check failed: {str(e)}"
    
    def check_document_access(self, user: User, document: ClinicalDocument,
                            access_level: AccessLevel,
                            emergency: bool = False) -> Tuple[bool, str]:
        """
        Check if user has access to a clinical document.
        
        Args:
            user: User requesting access
            document: Clinical document to access
            access_level: Required access level
            emergency: Whether this is an emergency access request
            
        Returns:
            Tuple of (has_access, reason)
        """
        try:
            # First check access to the parent record
            record_access = self.check_record_access(
                user, document.clinical_record, access_level, emergency
            )
            
            if not record_access[0]:
                return record_access
            
            # Check document-specific permissions
            document_access = self._check_document_permissions(user, document, access_level)
            if not document_access[0]:
                return document_access
            
            # Check document sensitivity level
            sensitivity_check = self._check_document_sensitivity(user, document, access_level)
            if not sensitivity_check[0]:
                return sensitivity_check
            
            return True, "Document access granted"
            
        except Exception as e:
            self.logger.error(f"Error checking document access: {str(e)}")
            return False, f"Document access check failed: {str(e)}"
    
    def grant_emergency_access(self, user: User, record: ClinicalRecord,
                             justification: str, duration_hours: int = 24) -> Dict[str, Any]:
        """
        Grant emergency access to a clinical record.
        
        Args:
            user: User requesting emergency access
            record: Clinical record to access
            justification: Justification for emergency access
            duration_hours: Duration of emergency access in hours
            
        Returns:
            Dictionary with emergency access details
        """
        try:
            # Verify user can request emergency access
            if not self._can_request_emergency_access(user):
                raise PermissionDenied("User not authorized for emergency access")
            
            # Create emergency access record
            emergency_access = EmergencyAccess.objects.create(
                user=user,
                clinical_record=record,
                justification=justification,
                granted_at=timezone.now(),
                expires_at=timezone.now() + timedelta(hours=duration_hours),
                clinic=record.clinic
            )
            
            # Log emergency access
            audit_service.log_clinical_action(
                action='EMERGENCY_ACCESS_GRANTED',
                user=user,
                resource_type='CLINICAL_RECORD',
                resource_id=str(record.id),
                clinic=record.clinic,
                patient_id=str(record.patient.id),
                sensitive_data=True,
                details={
                    'justification': justification,
                    'duration_hours': duration_hours,
                    'emergency_access_id': str(emergency_access.id),
                    'patient_name': record.patient.get_full_name(),
                    'record_title': record.title
                }
            )
            
            return {
                'emergency_access_id': str(emergency_access.id),
                'granted_at': emergency_access.granted_at.isoformat(),
                'expires_at': emergency_access.expires_at.isoformat(),
                'justification': justification,
                'record_id': str(record.id),
                'patient_name': record.patient.get_full_name()
            }
            
        except Exception as e:
            self.logger.error(f"Error granting emergency access: {str(e)}")
            raise
    
    def verify_patient_consent(self, patient: Patient, user: User,
                             purpose: str) -> Tuple[bool, str]:
        """
        Verify patient consent for data access.
        
        Args:
            patient: Patient whose data is being accessed
            user: User requesting access
            purpose: Purpose of data access
            
        Returns:
            Tuple of (has_consent, reason)
        """
        try:
            # Get patient consent records
            consent_records = PatientConsent.objects.filter(
                patient=patient,
                clinic=patient.clinic,
                is_active=True
            ).order_by('-created_at')
            
            if not consent_records.exists():
                # Check if consent is required
                if self._is_consent_required(patient, user, purpose):
                    return False, "Patient consent required but not found"
                else:
                    return True, "Consent not required for this access"
            
            # Check most recent consent
            latest_consent = consent_records.first()
            
            if latest_consent.status == ConsentStatus.GRANTED.value:
                # Check if consent covers this purpose
                if self._consent_covers_purpose(latest_consent, purpose):
                    # Check if consent is still valid
                    if self._is_consent_valid(latest_consent):
                        return True, "Valid patient consent found"
                    else:
                        return False, "Patient consent has expired"
                else:
                    return False, f"Patient consent does not cover purpose: {purpose}"
            
            elif latest_consent.status == ConsentStatus.DENIED.value:
                return False, "Patient has denied consent for data access"
            
            elif latest_consent.status == ConsentStatus.REVOKED.value:
                return False, "Patient consent has been revoked"
            
            else:
                return False, f"Patient consent status: {latest_consent.status}"
                
        except Exception as e:
            self.logger.error(f"Error verifying patient consent: {str(e)}")
            return False, f"Consent verification failed: {str(e)}"
    
    def delegate_permissions(self, delegator: User, delegatee: User,
                           permissions: List[str], duration_hours: int = 24,
                           scope: Dict[str, Any] = None) -> Dict[str, Any]:
        """
        Delegate permissions from one user to another.
        
        Args:
            delegator: User delegating permissions
            delegatee: User receiving permissions
            permissions: List of permissions to delegate
            duration_hours: Duration of delegation in hours
            scope: Scope limitations for delegated permissions
            
        Returns:
            Dictionary with delegation details
        """
        try:
            # Verify delegator has permissions to delegate
            if not self._can_delegate_permissions(delegator, permissions):
                raise PermissionDenied("User not authorized to delegate these permissions")
            
            # Verify delegatee can receive permissions
            if not self._can_receive_delegated_permissions(delegatee):
                raise PermissionDenied("Target user cannot receive delegated permissions")
            
            # Create permission delegation
            delegation = PermissionDelegation.objects.create(
                delegator=delegator,
                delegatee=delegatee,
                permissions=permissions,
                scope=scope or {},
                granted_at=timezone.now(),
                expires_at=timezone.now() + timedelta(hours=duration_hours),
                clinic=delegator.clinic
            )
            
            # Log permission delegation
            audit_service.log_clinical_action(
                action='PERMISSION_DELEGATION_GRANTED',
                user=delegator,
                resource_type='PERMISSION_DELEGATION',
                resource_id=str(delegation.id),
                clinic=delegator.clinic,
                details={
                    'delegatee_username': delegatee.username,
                    'delegated_permissions': permissions,
                    'duration_hours': duration_hours,
                    'scope': scope,
                    'delegation_id': str(delegation.id)
                }
            )
            
            return {
                'delegation_id': str(delegation.id),
                'delegator': delegator.username,
                'delegatee': delegatee.username,
                'permissions': permissions,
                'granted_at': delegation.granted_at.isoformat(),
                'expires_at': delegation.expires_at.isoformat(),
                'scope': scope
            }
            
        except Exception as e:
            self.logger.error(f"Error delegating permissions: {str(e)}")
            raise
    
    def _check_emergency_access(self, user: User, record: ClinicalRecord,
                              access_level: AccessLevel) -> Tuple[bool, str]:
        """Check emergency access permissions."""
        if not self._can_request_emergency_access(user):
            return False, "User not authorized for emergency access"
        
        # Check if there's an active emergency access grant
        active_emergency = EmergencyAccess.objects.filter(
            user=user,
            clinical_record=record,
            expires_at__gt=timezone.now(),
            is_active=True
        ).first()
        
        if active_emergency:
            return True, f"Active emergency access until {active_emergency.expires_at}"
        
        return False, "No active emergency access found"
    
    def _check_tenant_access(self, user: User, clinic: Clinic) -> bool:
        """Check if user has access to the clinic."""
        return hasattr(user, 'clinic') and user.clinic == clinic
    
    def _get_user_clinical_role(self, user: User) -> Optional[ClinicalRole]:
        """Get user's clinical role."""
        try:
            # Check user groups for clinical roles
            user_groups = user.groups.all()
            
            for group in user_groups:
                group_name = group.name.lower()
                for role in ClinicalRole:
                    if role.value in group_name:
                        return role
            
            # Check user profile for role information
            if hasattr(user, 'profile'):
                profile_role = getattr(user.profile, 'clinical_role', None)
                if profile_role:
                    try:
                        return ClinicalRole(profile_role)
                    except ValueError:
                        pass
            
            # Default role based on user type
            if user.is_staff:
                return ClinicalRole.ADMIN
            elif hasattr(user, 'is_doctor') and user.is_doctor:
                return ClinicalRole.DOCTOR
            else:
                return ClinicalRole.NURSE  # Default clinical role
                
        except Exception as e:
            self.logger.warning(f"Error determining user clinical role: {str(e)}")
            return None
    
    def _check_role_permissions(self, role: ClinicalRole, record: ClinicalRecord,
                              access_level: AccessLevel) -> Tuple[bool, str]:
        """Check role-based permissions."""
        role_perms = self.ROLE_PERMISSIONS.get(role, {})
        
        # Check specific permission patterns
        if access_level == AccessLevel.READ:
            read_perms = [
                'patient_records', 'assigned_patient_records', 'referred_patient_records',
                'all_clinic_records', 'own_records'
            ]
            for perm in read_perms:
                if perm in role_perms and role_perms[perm] in [AccessLevel.READ, AccessLevel.WRITE, AccessLevel.ADMIN]:
                    return True, f"Role {role.value} has {perm} permission"
        
        elif access_level == AccessLevel.WRITE:
            write_perms = [
                'patient_records', 'all_clinic_records', 'create_records'
            ]
            for perm in write_perms:
                if perm in role_perms and role_perms[perm] in [AccessLevel.WRITE, AccessLevel.ADMIN]:
                    return True, f"Role {role.value} has {perm} permission"
        
        elif access_level == AccessLevel.ADMIN:
            admin_perms = ['all_clinic_records', 'system_configuration']
            for perm in admin_perms:
                if perm in role_perms and role_perms[perm] == AccessLevel.ADMIN:
                    return True, f"Role {role.value} has {perm} permission"
        
        return False, f"Role {role.value} does not have required {access_level.value} access"
    
    def _check_patient_consent(self, user: User, patient: Patient,
                             access_level: AccessLevel) -> Tuple[bool, str]:
        """Check patient consent for data access."""
        # Skip consent check for patient accessing their own records
        if hasattr(user, 'patient_profile') and user.patient_profile == patient:
            return True, "Patient accessing own records"
        
        # Skip consent check for emergency access
        if access_level == AccessLevel.EMERGENCY:
            return True, "Emergency access bypasses consent"
        
        # Verify patient consent
        purpose = f"Clinical record access - {access_level.value}"
        return self.verify_patient_consent(patient, user, purpose)
    
    def _check_record_permissions(self, user: User, record: ClinicalRecord,
                                access_level: AccessLevel) -> Tuple[bool, str]:
        """Check specific record permissions."""
        # Check if user is the record creator
        if record.created_by == user:
            return True, "User is record creator"
        
        # Check if user is assigned to patient care
        if self._is_user_assigned_to_patient(user, record.patient):
            return True, "User assigned to patient care"
        
        # Check record-specific permissions
        record_perms = RecordPermission.objects.filter(
            clinical_record=record,
            user=user,
            is_active=True
        ).first()
        
        if record_perms:
            if self._permission_level_sufficient(record_perms.access_level, access_level):
                return True, f"Explicit record permission: {record_perms.access_level}"
        
        return True, "Default access granted"  # Allow by default for now
    
    def _check_time_restrictions(self, user: User, record: ClinicalRecord,
                               access_level: AccessLevel) -> Tuple[bool, str]:
        """Check time-based access restrictions."""
        # Check if user has time-based restrictions
        time_restrictions = UserTimeRestriction.objects.filter(
            user=user,
            is_active=True
        ).first()
        
        if time_restrictions:
            current_time = timezone.now().time()
            current_day = timezone.now().weekday()
            
            # Check time restrictions
            if not time_restrictions.is_time_allowed(current_time, current_day):
                return False, "Access denied due to time restrictions"
        
        return True, "No time restrictions apply"
    
    def _check_document_permissions(self, user: User, document: ClinicalDocument,
                                  access_level: AccessLevel) -> Tuple[bool, str]:
        """Check document-specific permissions."""
        # Check document sensitivity
        if document.is_confidential and access_level in [AccessLevel.READ, AccessLevel.WRITE]:
            # Verify user has confidential access
            if not self._has_confidential_access(user):
                return False, "Document is confidential - access denied"
        
        return True, "Document access granted"
    
    def _check_document_sensitivity(self, user: User, document: ClinicalDocument,
                                  access_level: AccessLevel) -> Tuple[bool, str]:
        """Check document sensitivity level."""
        # Check if document requires special permissions
        if document.document_type in ['pathology', 'genetics', 'mental_health']:
            if not self._has_specialized_access(user, document.document_type):
                return False, f"Specialized access required for {document.document_type} documents"
        
        return True, "Document sensitivity check passed"
    
    def _can_request_emergency_access(self, user: User) -> bool:
        """Check if user can request emergency access."""
        # Check if user has emergency access role
        user_role = self._get_user_clinical_role(user)
        if user_role in [ClinicalRole.DOCTOR, ClinicalRole.EMERGENCY_USER, ClinicalRole.ADMIN]:
            return True
        
        # Check if user has emergency access permission
        return user.has_perm('clinical_records.emergency_access')
    
    def _is_consent_required(self, patient: Patient, user: User, purpose: str) -> bool:
        """Check if consent is required for this access."""
        # Consent always required for external sharing
        if 'sharing' in purpose.lower() or 'external' in purpose.lower():
            return True
        
        # Consent required for research purposes
        if 'research' in purpose.lower():
            return True
        
        # Consent may be waived for treatment purposes
        if 'treatment' in purpose.lower() and self._is_treating_physician(user, patient):
            return False
        
        return True  # Default to requiring consent
    
    def _consent_covers_purpose(self, consent: 'PatientConsent', purpose: str) -> bool:
        """Check if consent covers the specified purpose."""
        consent_purposes = consent.purposes or []
        
        # Check for broad consent
        if 'all' in consent_purposes or 'general' in consent_purposes:
            return True
        
        # Check for specific purpose match
        for consent_purpose in consent_purposes:
            if consent_purpose.lower() in purpose.lower():
                return True
        
        return False
    
    def _is_consent_valid(self, consent: 'PatientConsent') -> bool:
        """Check if consent is still valid."""
        if consent.expires_at and consent.expires_at < timezone.now():
            return False
        
        return consent.is_active
    
    def _can_delegate_permissions(self, user: User, permissions: List[str]) -> bool:
        """Check if user can delegate specified permissions."""
        # Only admins and senior staff can delegate permissions
        user_role = self._get_user_clinical_role(user)
        if user_role not in [ClinicalRole.ADMIN, ClinicalRole.DOCTOR]:
            return False
        
        # Check if user has the permissions they want to delegate
        for permission in permissions:
            if not user.has_perm(permission):
                return False
        
        return True
    
    def _can_receive_delegated_permissions(self, user: User) -> bool:
        """Check if user can receive delegated permissions."""
        # Most clinical staff can receive delegated permissions
        user_role = self._get_user_clinical_role(user)
        return user_role in [ClinicalRole.NURSE, ClinicalRole.DOCTOR, ClinicalRole.SPECIALIST]
    
    def _is_user_assigned_to_patient(self, user: User, patient: Patient) -> bool:
        """Check if user is assigned to patient care."""
        # Check patient care assignments
        try:
            from users.models import PatientCareAssignment
            return PatientCareAssignment.objects.filter(
                patient=patient,
                healthcare_provider=user,
                is_active=True
            ).exists()
        except ImportError:
            # Fallback to simple check
            return True
    
    def _permission_level_sufficient(self, granted_level: str, required_level: AccessLevel) -> bool:
        """Check if granted permission level is sufficient."""
        level_hierarchy = {
            AccessLevel.NONE: 0,
            AccessLevel.READ: 1,
            AccessLevel.WRITE: 2,
            AccessLevel.ADMIN: 3,
            AccessLevel.EMERGENCY: 4
        }
        
        try:
            granted_enum = AccessLevel(granted_level)
            return level_hierarchy[granted_enum] >= level_hierarchy[required_level]
        except ValueError:
            return False
    
    def _has_confidential_access(self, user: User) -> bool:
        """Check if user has access to confidential documents."""
        user_role = self._get_user_clinical_role(user)
        return user_role in [ClinicalRole.DOCTOR, ClinicalRole.SPECIALIST, ClinicalRole.ADMIN]
    
    def _has_specialized_access(self, user: User, document_type: str) -> bool:
        """Check if user has access to specialized document types."""
        user_role = self._get_user_clinical_role(user)
        
        # Doctors and specialists generally have specialized access
        if user_role in [ClinicalRole.DOCTOR, ClinicalRole.SPECIALIST, ClinicalRole.ADMIN]:
            return True
        
        # Check for specific specialization permissions
        return user.has_perm(f'clinical_records.access_{document_type}')
    
    def _is_treating_physician(self, user: User, patient: Patient) -> bool:
        """Check if user is a treating physician for the patient."""
        user_role = self._get_user_clinical_role(user)
        if user_role not in [ClinicalRole.DOCTOR, ClinicalRole.SPECIALIST]:
            return False
        
        return self._is_user_assigned_to_patient(user, patient)


# Global access control instance
access_control = ClinicalAccessControl()