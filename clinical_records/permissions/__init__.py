"""
Clinical Records Permissions Package

This package contains permission classes and access control logic for clinical records.
"""

from .rest_permissions import ClinicalRecordPermission, DocumentPermission, ClinicalRecordsPermission, CanViewRecords, CanShareRecords, TenantPermission, CanEditRecords
from .minimal_access_control import access_control

__all__ = [
    'ClinicalRecordPermission',
    'DocumentPermission',
    'ClinicalRecordsPermission',
    'CanViewRecords',
    'CanShareRecords',
    'TenantPermission',
    'CanEditRecords',
]
