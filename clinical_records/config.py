"""
Clinical Records Configuration
"""
from django.conf import settings

# DICOM Processing Configuration
DICOM_ENABLED = True
DICOM_THUMBNAIL_SIZE = (256, 256)
DICOM_ANONYMIZE_BY_DEFAULT = True

# FHIR Export Configuration
FHIR_ENABLED = True
FHIR_BASE_URL = getattr(settings, 'FHIR_BASE_URL', 'http://localhost:8000/fhir/')
FHIR_VERSION = 'R4'

# File Processing Configuration
MAX_FILE_SIZE = getattr(settings, 'CLINICAL_RECORDS_MAX_FILE_SIZE', 50 * 1024 * 1024)  # 50MB
ALLOWED_FILE_TYPES = [
    'application/pdf',
    'image/jpeg',
    'image/png', 
    'image/tiff',
    'application/dicom',
    'text/plain',
    'application/msword',
    'application/vnd.openxmlformats-officedocument.wordprocessingml.document'
]

# Storage Configuration
USE_S3_STORAGE = getattr(settings, 'CLINICAL_RECORDS_USE_S3', False)
S3_BUCKET_NAME = getattr(settings, 'CLINICAL_RECORDS_S3_BUCKET', None)
S3_REGION = getattr(settings, 'CLINICAL_RECORDS_S3_REGION', 'us-east-1')

# Security Configuration
ENCRYPT_FILES_AT_REST = getattr(settings, 'CLINICAL_RECORDS_ENCRYPT_FILES', True)
REQUIRE_PATIENT_CONSENT = getattr(settings, 'CLINICAL_RECORDS_REQUIRE_CONSENT', True)

# Processing Configuration
ENABLE_OCR_PROCESSING = True
ENABLE_STRUCTURED_EXTRACTION = True
OCR_CONFIDENCE_THRESHOLD = 0.7

# Background Processing
USE_BACKGROUND_PROCESSING = True
PROCESSING_QUEUE_NAME = 'clinical_records'