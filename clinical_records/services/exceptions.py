"""
Custom exceptions for Clinical Records Service
"""


class ClinicalRecordsServiceError(Exception):
    """Base exception for Clinical Records Service errors"""
    pass


class PatientSyncError(ClinicalRecordsServiceError):
    """Exception raised when patient synchronization fails"""
    pass


class DocumentProcessingError(ClinicalRecordsServiceError):
    """Exception raised when document processing fails"""
    pass


class AuthenticationError(ClinicalRecordsServiceError):
    """Exception raised when authentication fails"""
    pass


class ValidationError(ClinicalRecordsServiceError):
    """Exception raised when data validation fails"""
    pass
