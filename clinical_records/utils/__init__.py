# Clinical Records Utilities Package

from .exceptions import (
    ClinicalRecordsException,
    DocumentProcessingError,
    TenantIsolationError,
    EncryptionError,
    ConsentViolationError
)

try:
    from .dicom_utils import DICOMProcessor
except ImportError:
    DICOMProcessor = None
from .fhir_utils import FHIRExportService
from .file_utils import FileTypeDetector, FileHasher, S3StorageService

__all__ = [
    'ClinicalRecordsException',
    'DocumentProcessingError', 
    'TenantIsolationError',
    'EncryptionError',
    'ConsentViolationError',
    'DICOMProcessor',
    'FHIRExportService',
    'FileTypeDetector',
    'FileHasher',
    'S3StorageService'
]