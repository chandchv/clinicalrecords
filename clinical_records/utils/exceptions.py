"""
Clinical Records Custom Exceptions
"""


class ClinicalRecordsException(Exception):
    """Base exception for clinical records system"""
    pass


class DocumentProcessingError(ClinicalRecordsException):
    """Raised when document processing fails"""
    pass


class TenantIsolationError(ClinicalRecordsException):
    """Raised when tenant isolation is violated"""
    pass


class EncryptionError(ClinicalRecordsException):
    """Raised when encryption/decryption fails"""
    pass


class ConsentViolationError(ClinicalRecordsException):
    """Raised when patient consent requirements are not met"""
    pass