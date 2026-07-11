"""
Django settings configuration for S3 storage integration.
Provides settings that can be imported into main Django settings.
"""

import os
from clinical_records.config.s3_config import get_s3_config

# Get environment-specific S3 configuration
S3_CONFIG = get_s3_config()

# S3 Storage Settings for django-storages
AWS_ACCESS_KEY_ID = S3_CONFIG.ACCESS_KEY_ID
AWS_SECRET_ACCESS_KEY = S3_CONFIG.SECRET_ACCESS_KEY
AWS_STORAGE_BUCKET_NAME = S3_CONFIG.BUCKET_NAME
AWS_S3_REGION_NAME = S3_CONFIG.REGION_NAME
AWS_DEFAULT_ACL = S3_CONFIG.DEFAULT_ACL
AWS_S3_FILE_OVERWRITE = S3_CONFIG.FILE_OVERWRITE
AWS_S3_SIGNATURE_VERSION = S3_CONFIG.SIGNATURE_VERSION
AWS_S3_ADDRESSING_STYLE = S3_CONFIG.ADDRESSING_STYLE

# S3 Object Parameters
AWS_S3_OBJECT_PARAMETERS = {
    'ServerSideEncryption': S3_CONFIG.SERVER_SIDE_ENCRYPTION,
    'StorageClass': S3_CONFIG.DEFAULT_STORAGE_CLASS,
}

# Add KMS key if using KMS encryption
if S3_CONFIG.SERVER_SIDE_ENCRYPTION == 'aws:kms' and S3_CONFIG.KMS_KEY_ID:
    AWS_S3_OBJECT_PARAMETERS['SSEKMSKeyId'] = S3_CONFIG.KMS_KEY_ID

# Presigned URL Settings
AWS_QUERYSTRING_AUTH = True
AWS_QUERYSTRING_EXPIRE = S3_CONFIG.PRESIGNED_URL_EXPIRY

# CloudFront Settings (if configured)
if S3_CONFIG.CLOUDFRONT_DOMAIN:
    AWS_S3_CUSTOM_DOMAIN = S3_CONFIG.CLOUDFRONT_DOMAIN
    AWS_S3_URL_PROTOCOL = 'https'

# Security Settings
AWS_S3_SECURE_URLS = S3_CONFIG.REQUIRE_HTTPS
AWS_S3_USE_SSL = S3_CONFIG.REQUIRE_HTTPS

# Clinical Records Specific Settings
CLINICAL_RECORDS_S3_BUCKET = S3_CONFIG.BUCKET_NAME
CLINICAL_RECORDS_S3_ENCRYPTION = S3_CONFIG.SERVER_SIDE_ENCRYPTION
CLINICAL_RECORDS_S3_KMS_KEY_ID = S3_CONFIG.KMS_KEY_ID
CLINICAL_RECORDS_S3_TENANT_PREFIX = S3_CONFIG.TENANT_PREFIX
CLINICAL_RECORDS_PRESIGNED_URL_EXPIRY = S3_CONFIG.PRESIGNED_URL_EXPIRY

# CloudFront Settings
CLINICAL_RECORDS_CLOUDFRONT_DOMAIN = S3_CONFIG.CLOUDFRONT_DOMAIN
CLOUDFRONT_KEY_ID = S3_CONFIG.CLOUDFRONT_KEY_ID

# Load CloudFront private key if path is provided
if S3_CONFIG.CLOUDFRONT_PRIVATE_KEY_PATH and os.path.exists(S3_CONFIG.CLOUDFRONT_PRIVATE_KEY_PATH):
    with open(S3_CONFIG.CLOUDFRONT_PRIVATE_KEY_PATH, 'r') as f:
        CLOUDFRONT_PRIVATE_KEY = f.read()
else:
    CLOUDFRONT_PRIVATE_KEY = None

# Storage Backend Configuration
# Use S3 for clinical records, keep local storage for other media
DEFAULT_FILE_STORAGE = 'clinical_records.storage.s3_storage.ClinicalRecordsS3Storage'

# Alternative: Use S3 only for clinical records
CLINICAL_RECORDS_STORAGE = 'clinical_records.storage.s3_storage.ClinicalRecordsS3Storage'

# Multipart Upload Settings
AWS_S3_MULTIPART_THRESHOLD = S3_CONFIG.MULTIPART_THRESHOLD
AWS_S3_MULTIPART_CHUNKSIZE = S3_CONFIG.MULTIPART_CHUNKSIZE

# Transfer Configuration
AWS_S3_MAX_POOL_CONNECTIONS = 50
AWS_S3_RETRIES = {
    'max_attempts': 3,
    'mode': 'adaptive'
}

# Environment-specific overrides
ENVIRONMENT = os.environ.get('DJANGO_ENVIRONMENT', 'development').lower()

if ENVIRONMENT == 'production':
    # Production-specific S3 settings
    AWS_S3_OBJECT_PARAMETERS.update({
        'CacheControl': 'max-age=86400',  # 24 hours
    })
    AWS_QUERYSTRING_EXPIRE = 1800  # 30 minutes for security
    
elif ENVIRONMENT == 'staging':
    # Staging-specific S3 settings
    AWS_QUERYSTRING_EXPIRE = 3600  # 1 hour
    
else:
    # Development-specific S3 settings
    AWS_QUERYSTRING_EXPIRE = 7200  # 2 hours for convenience
    # Allow HTTP for development
    AWS_S3_SECURE_URLS = False
    AWS_S3_USE_SSL = False

# Logging configuration for S3 operations
LOGGING_S3_CONFIG = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        's3_formatter': {
            'format': '[{levelname}] {asctime} {name}: {message}',
            'style': '{',
        },
    },
    'handlers': {
        's3_file': {
            'level': 'INFO',
            'class': 'logging.FileHandler',
            'filename': 'logs/s3_operations.log',
            'formatter': 's3_formatter',
        },
        's3_console': {
            'level': 'DEBUG' if ENVIRONMENT == 'development' else 'INFO',
            'class': 'logging.StreamHandler',
            'formatter': 's3_formatter',
        },
    },
    'loggers': {
        'clinical_records.storage': {
            'handlers': ['s3_file', 's3_console'],
            'level': 'DEBUG' if ENVIRONMENT == 'development' else 'INFO',
            'propagate': False,
        },
        'clinical_records.services.s3_service': {
            'handlers': ['s3_file', 's3_console'],
            'level': 'DEBUG' if ENVIRONMENT == 'development' else 'INFO',
            'propagate': False,
        },
        'boto3': {
            'handlers': ['s3_file'],
            'level': 'WARNING',
            'propagate': False,
        },
        'botocore': {
            'handlers': ['s3_file'],
            'level': 'WARNING',
            'propagate': False,
        },
    },
}

# Health check settings for S3
S3_HEALTH_CHECK_SETTINGS = {
    'enabled': True,
    'timeout': 10,  # seconds
    'retry_attempts': 3,
    'check_interval': 300,  # 5 minutes
}

# Backup and disaster recovery settings
S3_BACKUP_SETTINGS = {
    'cross_region_replication': S3_CONFIG.CROSS_REGION_REPLICATION,
    'backup_bucket': S3_CONFIG.BACKUP_BUCKET,
    'versioning_enabled': S3_CONFIG.ENABLE_VERSIONING,
    'lifecycle_enabled': True,
}

# Monitoring and alerting settings
S3_MONITORING_SETTINGS = {
    'cloudwatch_enabled': True,
    'metrics_namespace': 'RxDoctor/ClinicalRecords',
    'alert_on_errors': True,
    'alert_email': os.environ.get('S3_ALERT_EMAIL'),
    'storage_usage_threshold_gb': 1000,  # Alert when storage exceeds 1TB
}

# Cost optimization settings
S3_COST_OPTIMIZATION = {
    'intelligent_tiering': True,
    'lifecycle_transitions': {
        'standard_ia_days': S3_CONFIG.TRANSITION_TO_IA_DAYS,
        'glacier_days': S3_CONFIG.TRANSITION_TO_GLACIER_DAYS,
        'deep_archive_days': S3_CONFIG.TRANSITION_TO_DEEP_ARCHIVE_DAYS,
    },
    'delete_incomplete_multipart_days': 7,
    'delete_old_versions_days': 365,
}

# Security and compliance settings
S3_SECURITY_SETTINGS = {
    'encryption_at_rest': True,
    'encryption_in_transit': True,
    'access_logging': True,
    'cloudtrail_logging': True,
    'bucket_notifications': True,
    'mfa_delete': S3_CONFIG.ENABLE_MFA_DELETE,
    'public_access_block': {
        'BlockPublicAcls': True,
        'IgnorePublicAcls': True,
        'BlockPublicPolicy': True,
        'RestrictPublicBuckets': True,
    },
}

# Integration settings
S3_INTEGRATION_SETTINGS = {
    'enable_cloudfront': bool(S3_CONFIG.CLOUDFRONT_DOMAIN),
    'enable_lambda_triggers': False,  # Can be enabled for advanced processing
    'enable_sns_notifications': False,  # Can be enabled for real-time alerts
    'enable_elasticsearch_indexing': False,  # Can be enabled for search
}

def get_s3_django_settings():
    """
    Get complete S3 settings dictionary for Django settings.
    
    Returns:
        dict: S3 settings for Django
    """
    return {
        # AWS Credentials
        'AWS_ACCESS_KEY_ID': AWS_ACCESS_KEY_ID,
        'AWS_SECRET_ACCESS_KEY': AWS_SECRET_ACCESS_KEY,
        
        # S3 Configuration
        'AWS_STORAGE_BUCKET_NAME': AWS_STORAGE_BUCKET_NAME,
        'AWS_S3_REGION_NAME': AWS_S3_REGION_NAME,
        'AWS_DEFAULT_ACL': AWS_DEFAULT_ACL,
        'AWS_S3_FILE_OVERWRITE': AWS_S3_FILE_OVERWRITE,
        'AWS_S3_SIGNATURE_VERSION': AWS_S3_SIGNATURE_VERSION,
        'AWS_S3_ADDRESSING_STYLE': AWS_S3_ADDRESSING_STYLE,
        'AWS_S3_OBJECT_PARAMETERS': AWS_S3_OBJECT_PARAMETERS,
        
        # URL and Security
        'AWS_QUERYSTRING_AUTH': AWS_QUERYSTRING_AUTH,
        'AWS_QUERYSTRING_EXPIRE': AWS_QUERYSTRING_EXPIRE,
        'AWS_S3_SECURE_URLS': AWS_S3_SECURE_URLS,
        'AWS_S3_USE_SSL': AWS_S3_USE_SSL,
        
        # CloudFront
        'AWS_S3_CUSTOM_DOMAIN': globals().get('AWS_S3_CUSTOM_DOMAIN'),
        'AWS_S3_URL_PROTOCOL': globals().get('AWS_S3_URL_PROTOCOL', 'https'),
        
        # Multipart Upload
        'AWS_S3_MULTIPART_THRESHOLD': AWS_S3_MULTIPART_THRESHOLD,
        'AWS_S3_MULTIPART_CHUNKSIZE': AWS_S3_MULTIPART_CHUNKSIZE,
        
        # Clinical Records Specific
        'CLINICAL_RECORDS_S3_BUCKET': CLINICAL_RECORDS_S3_BUCKET,
        'CLINICAL_RECORDS_S3_ENCRYPTION': CLINICAL_RECORDS_S3_ENCRYPTION,
        'CLINICAL_RECORDS_S3_KMS_KEY_ID': CLINICAL_RECORDS_S3_KMS_KEY_ID,
        'CLINICAL_RECORDS_S3_TENANT_PREFIX': CLINICAL_RECORDS_S3_TENANT_PREFIX,
        'CLINICAL_RECORDS_PRESIGNED_URL_EXPIRY': CLINICAL_RECORDS_PRESIGNED_URL_EXPIRY,
        
        # CloudFront
        'CLINICAL_RECORDS_CLOUDFRONT_DOMAIN': CLINICAL_RECORDS_CLOUDFRONT_DOMAIN,
        'CLOUDFRONT_KEY_ID': CLOUDFRONT_KEY_ID,
        'CLOUDFRONT_PRIVATE_KEY': CLOUDFRONT_PRIVATE_KEY,
        
        # Storage Backend
        'DEFAULT_FILE_STORAGE': DEFAULT_FILE_STORAGE,
        'CLINICAL_RECORDS_STORAGE': CLINICAL_RECORDS_STORAGE,
    }

def validate_s3_settings():
    """
    Validate S3 settings configuration.
    
    Returns:
        list: List of validation errors
    """
    errors = []
    
    if not AWS_STORAGE_BUCKET_NAME:
        errors.append("AWS_STORAGE_BUCKET_NAME is required")
    
    if not AWS_ACCESS_KEY_ID and not os.environ.get('AWS_ACCESS_KEY_ID'):
        errors.append("AWS_ACCESS_KEY_ID is required")
    
    if not AWS_SECRET_ACCESS_KEY and not os.environ.get('AWS_SECRET_ACCESS_KEY'):
        errors.append("AWS_SECRET_ACCESS_KEY is required")
    
    if AWS_S3_OBJECT_PARAMETERS.get('ServerSideEncryption') == 'aws:kms':
        if not AWS_S3_OBJECT_PARAMETERS.get('SSEKMSKeyId'):
            errors.append("KMS Key ID is required when using KMS encryption")
    
    if CLINICAL_RECORDS_CLOUDFRONT_DOMAIN:
        if not CLOUDFRONT_KEY_ID:
            errors.append("CloudFront Key ID is required when using CloudFront")
        if not CLOUDFRONT_PRIVATE_KEY:
            errors.append("CloudFront private key is required when using CloudFront")
    
    return errors

# Validate settings on import
_validation_errors = validate_s3_settings()
if _validation_errors:
    import warnings
    warnings.warn(f"S3 settings validation errors: {', '.join(_validation_errors)}")