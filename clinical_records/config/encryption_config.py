"""
Encryption configuration for clinical records.

This module contains configuration settings and utilities for
the encryption system.
"""

import os
from django.conf import settings


# Encryption algorithm settings
ENCRYPTION_ALGORITHM = 'AES-256-GCM'
KEY_DERIVATION_ALGORITHM = 'PBKDF2-SHA256'

# Key sizes (in bytes)
MASTER_KEY_SIZE = 32  # 256 bits
DERIVED_KEY_SIZE = 32  # 256 bits
SALT_SIZE = 16  # 128 bits
NONCE_SIZE = 12  # 96 bits for GCM
TAG_SIZE = 16  # 128 bits for authentication

# Key derivation settings
PBKDF2_ITERATIONS = 100000  # OWASP recommended minimum

# File encryption settings
MAX_FILE_SIZE_MB = 100  # Maximum file size for encryption (in MB)
TEMP_FILE_CLEANUP_HOURS = 1  # Hours after which temp files are cleaned up

# Auto-encryption settings
AUTO_ENCRYPT_NEW_FILES = getattr(settings, 'CLINICAL_RECORDS_AUTO_ENCRYPT', False)
AUTO_ENCRYPT_FILE_TYPES = [
    'pdf', 'image', 'dicom', 'text', 'office'
]

# Encryption monitoring settings
INTEGRITY_CHECK_INTERVAL_HOURS = 24  # How often to check file integrity
KEY_ROTATION_INTERVAL_DAYS = 90  # Recommended key rotation interval

# Storage settings
ENCRYPTED_STORAGE_BACKEND = 'clinical_records.storage.encrypted_storage.EncryptedFileSystemStorage'

# Performance settings
ENCRYPTION_BATCH_SIZE = 10  # Number of files to encrypt in one batch
ENCRYPTION_TIMEOUT_SECONDS = 300  # Timeout for encryption operations

# Security settings
REQUIRE_ENCRYPTION_FOR_SENSITIVE_TYPES = True
SENSITIVE_DOCUMENT_TYPES = ['lab_report', 'prescription', 'pathology', 'imaging']

# Compliance settings
ENCRYPTION_AUDIT_ENABLED = True
ENCRYPTION_COMPLIANCE_REPORTING = True

# Development settings
ALLOW_UNENCRYPTED_IN_DEBUG = getattr(settings, 'DEBUG', False)


def get_encryption_config():
    """
    Get complete encryption configuration.
    
    Returns:
        Dictionary with all encryption configuration settings
    """
    return {
        'algorithm': ENCRYPTION_ALGORITHM,
        'key_derivation': KEY_DERIVATION_ALGORITHM,
        'master_key_size': MASTER_KEY_SIZE,
        'derived_key_size': DERIVED_KEY_SIZE,
        'salt_size': SALT_SIZE,
        'nonce_size': NONCE_SIZE,
        'tag_size': TAG_SIZE,
        'pbkdf2_iterations': PBKDF2_ITERATIONS,
        'max_file_size_mb': MAX_FILE_SIZE_MB,
        'temp_file_cleanup_hours': TEMP_FILE_CLEANUP_HOURS,
        'auto_encrypt_new_files': AUTO_ENCRYPT_NEW_FILES,
        'auto_encrypt_file_types': AUTO_ENCRYPT_FILE_TYPES,
        'integrity_check_interval_hours': INTEGRITY_CHECK_INTERVAL_HOURS,
        'key_rotation_interval_days': KEY_ROTATION_INTERVAL_DAYS,
        'encrypted_storage_backend': ENCRYPTED_STORAGE_BACKEND,
        'encryption_batch_size': ENCRYPTION_BATCH_SIZE,
        'encryption_timeout_seconds': ENCRYPTION_TIMEOUT_SECONDS,
        'require_encryption_for_sensitive_types': REQUIRE_ENCRYPTION_FOR_SENSITIVE_TYPES,
        'sensitive_document_types': SENSITIVE_DOCUMENT_TYPES,
        'encryption_audit_enabled': ENCRYPTION_AUDIT_ENABLED,
        'encryption_compliance_reporting': ENCRYPTION_COMPLIANCE_REPORTING,
        'allow_unencrypted_in_debug': ALLOW_UNENCRYPTED_IN_DEBUG
    }


def is_encryption_required_for_document_type(document_type: str) -> bool:
    """
    Check if encryption is required for a specific document type.
    
    Args:
        document_type: Type of clinical document
        
    Returns:
        True if encryption is required
    """
    if REQUIRE_ENCRYPTION_FOR_SENSITIVE_TYPES:
        return document_type in SENSITIVE_DOCUMENT_TYPES
    
    return AUTO_ENCRYPT_NEW_FILES


def get_master_key_from_settings() -> str:
    """
    Get master key from Django settings.
    
    Returns:
        Base64-encoded master key
        
    Raises:
        ValueError: If master key is not configured properly
    """
    master_key = getattr(settings, 'CLINICAL_RECORDS_MASTER_KEY', None)
    
    if not master_key:
        if settings.DEBUG and ALLOW_UNENCRYPTED_IN_DEBUG:
            # Return development key for testing
            import base64
            dev_key = b'development_key_not_for_production_use_32_bytes'
            return base64.b64encode(dev_key).decode('utf-8')
        else:
            raise ValueError(
                "CLINICAL_RECORDS_MASTER_KEY must be set in settings. "
                "Use 'python manage.py manage_encryption --action generate-key' to generate one."
            )
    
    return master_key


def validate_encryption_settings():
    """
    Validate encryption configuration settings.
    
    Raises:
        ValueError: If configuration is invalid
    """
    # Check master key
    try:
        master_key = get_master_key_from_settings()
        import base64
        decoded_key = base64.b64decode(master_key)
        if len(decoded_key) != MASTER_KEY_SIZE:
            raise ValueError(f"Master key must be {MASTER_KEY_SIZE} bytes")
    except Exception as e:
        raise ValueError(f"Invalid master key configuration: {str(e)}")
    
    # Check file size limits
    if MAX_FILE_SIZE_MB <= 0:
        raise ValueError("MAX_FILE_SIZE_MB must be positive")
    
    # Check iteration count
    if PBKDF2_ITERATIONS < 10000:
        raise ValueError("PBKDF2_ITERATIONS should be at least 10,000 for security")
    
    # Check batch size
    if ENCRYPTION_BATCH_SIZE <= 0:
        raise ValueError("ENCRYPTION_BATCH_SIZE must be positive")
    
    return True


# Environment-specific settings
if hasattr(settings, 'CLINICAL_RECORDS_ENCRYPTION_CONFIG'):
    # Allow override from Django settings
    custom_config = settings.CLINICAL_RECORDS_ENCRYPTION_CONFIG
    
    # Update configuration with custom values
    for key, value in custom_config.items():
        if hasattr(globals(), key.upper()):
            globals()[key.upper()] = value


# Validate configuration on import
try:
    validate_encryption_settings()
except ValueError as e:
    if not settings.DEBUG:
        raise e
    # In debug mode, just log the warning
    import logging
    logger = logging.getLogger(__name__)
    logger.warning(f"Encryption configuration warning: {str(e)}")