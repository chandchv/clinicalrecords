"""
AWS Textract configuration settings for clinical records OCR processing.
"""

from django.conf import settings
import os


# AWS Textract Configuration
TEXTRACT_CONFIG = {
    # Enable/disable Textract service
    'TEXTRACT_ENABLED': getattr(settings, 'TEXTRACT_ENABLED', False),
    
    # AWS credentials and region
    'AWS_REGION': getattr(settings, 'AWS_REGION', 'us-east-1'),
    'AWS_ACCESS_KEY_ID': getattr(settings, 'AWS_ACCESS_KEY_ID', os.environ.get('AWS_ACCESS_KEY_ID')),
    'AWS_SECRET_ACCESS_KEY': getattr(settings, 'AWS_SECRET_ACCESS_KEY', os.environ.get('AWS_SECRET_ACCESS_KEY')),
    
    # Textract processing thresholds
    'TEXTRACT_CONFIDENCE_THRESHOLD': getattr(settings, 'TEXTRACT_CONFIDENCE_THRESHOLD', 0.7),
    'TEXTRACT_COST_OPTIMIZATION': getattr(settings, 'TEXTRACT_COST_OPTIMIZATION', True),
    
    # Document type specific settings
    'TEXTRACT_PRESCRIPTION_ENABLED': getattr(settings, 'TEXTRACT_PRESCRIPTION_ENABLED', True),
    'TEXTRACT_LAB_REPORT_ENABLED': getattr(settings, 'TEXTRACT_LAB_REPORT_ENABLED', True),
    'TEXTRACT_DISCHARGE_SUMMARY_ENABLED': getattr(settings, 'TEXTRACT_DISCHARGE_SUMMARY_ENABLED', True),
    
    # Processing limits
    'TEXTRACT_MAX_FILE_SIZE_MB': getattr(settings, 'TEXTRACT_MAX_FILE_SIZE_MB', 10),
    'TEXTRACT_SUPPORTED_FORMATS': getattr(settings, 'TEXTRACT_SUPPORTED_FORMATS', [
        'image/jpeg', 'image/png', 'image/tiff', 'application/pdf'
    ]),
    
    # Cost management
    'TEXTRACT_DAILY_COST_LIMIT': getattr(settings, 'TEXTRACT_DAILY_COST_LIMIT', 50.0),  # USD
    'TEXTRACT_MONTHLY_COST_LIMIT': getattr(settings, 'TEXTRACT_MONTHLY_COST_LIMIT', 500.0),  # USD
    
    # Retry and timeout settings
    'TEXTRACT_RETRY_ATTEMPTS': getattr(settings, 'TEXTRACT_RETRY_ATTEMPTS', 3),
    'TEXTRACT_TIMEOUT_SECONDS': getattr(settings, 'TEXTRACT_TIMEOUT_SECONDS', 30),
    
    # Fallback behavior
    'TEXTRACT_FALLBACK_TO_LOCAL': getattr(settings, 'TEXTRACT_FALLBACK_TO_LOCAL', True),
    'TEXTRACT_REQUIRE_CONSENT': getattr(settings, 'TEXTRACT_REQUIRE_CONSENT', True),
    
    # Logging and monitoring
    'TEXTRACT_LOG_REQUESTS': getattr(settings, 'TEXTRACT_LOG_REQUESTS', True),
    'TEXTRACT_TRACK_COSTS': getattr(settings, 'TEXTRACT_TRACK_COSTS', True),
}


def get_textract_config():
    """Get Textract configuration dictionary."""
    return TEXTRACT_CONFIG.copy()


def is_textract_enabled():
    """Check if Textract is enabled and properly configured."""
    config = get_textract_config()
    return (
        config['TEXTRACT_ENABLED'] and
        config['AWS_ACCESS_KEY_ID'] and
        config['AWS_SECRET_ACCESS_KEY'] and
        config['AWS_REGION']
    )


def should_use_textract_for_document_type(document_type: str) -> bool:
    """
    Check if Textract should be used for a specific document type.
    
    Args:
        document_type: Type of document (prescription, lab_report, etc.)
        
    Returns:
        bool: True if Textract should be used for this document type
    """
    if not is_textract_enabled():
        return False
    
    config = get_textract_config()
    
    type_mapping = {
        'prescription': config['TEXTRACT_PRESCRIPTION_ENABLED'],
        'lab_report': config['TEXTRACT_LAB_REPORT_ENABLED'],
        'discharge_summary': config['TEXTRACT_DISCHARGE_SUMMARY_ENABLED'],
        'referral': True,  # Always use for referrals (complex documents)
        'insurance': True,  # Always use for insurance forms
        'consent_form': True,  # Always use for consent forms
    }
    
    return type_mapping.get(document_type, False)


def is_file_supported_by_textract(content_type: str, file_size_bytes: int) -> bool:
    """
    Check if a file is supported by Textract.
    
    Args:
        content_type: MIME type of the file
        file_size_bytes: Size of the file in bytes
        
    Returns:
        bool: True if file is supported
    """
    config = get_textract_config()
    
    # Check file format
    if content_type not in config['TEXTRACT_SUPPORTED_FORMATS']:
        return False
    
    # Check file size
    max_size_bytes = config['TEXTRACT_MAX_FILE_SIZE_MB'] * 1024 * 1024
    if file_size_bytes > max_size_bytes:
        return False
    
    return True


def get_textract_pricing():
    """
    Get current Textract pricing information.
    
    Returns:
        dict: Pricing information
    """
    return {
        'detect_document_text': 0.0015,  # Per page
        'analyze_document_forms': 0.05,  # Per page
        'analyze_document_tables': 0.015,  # Per page
        'currency': 'USD',
        'unit': 'per_page',
        'last_updated': '2024-01-01'
    }


# Environment-specific configurations
DEVELOPMENT_CONFIG = {
    'TEXTRACT_ENABLED': False,  # Disabled by default in development
    'TEXTRACT_COST_OPTIMIZATION': True,
    'TEXTRACT_FALLBACK_TO_LOCAL': True,
    'TEXTRACT_LOG_REQUESTS': True,
}

PRODUCTION_CONFIG = {
    'TEXTRACT_ENABLED': True,
    'TEXTRACT_COST_OPTIMIZATION': True,
    'TEXTRACT_FALLBACK_TO_LOCAL': True,
    'TEXTRACT_LOG_REQUESTS': True,
    'TEXTRACT_TRACK_COSTS': True,
    'TEXTRACT_DAILY_COST_LIMIT': 100.0,
    'TEXTRACT_MONTHLY_COST_LIMIT': 1000.0,
}

TESTING_CONFIG = {
    'TEXTRACT_ENABLED': False,  # Use mock service for testing
    'TEXTRACT_FALLBACK_TO_LOCAL': True,
    'TEXTRACT_LOG_REQUESTS': False,
}


def get_environment_config():
    """Get configuration based on current environment."""
    env = getattr(settings, 'ENVIRONMENT', 'development').lower()
    
    if env == 'production':
        return PRODUCTION_CONFIG
    elif env == 'testing':
        return TESTING_CONFIG
    else:
        return DEVELOPMENT_CONFIG


def apply_environment_config():
    """Apply environment-specific configuration to global config."""
    env_config = get_environment_config()
    TEXTRACT_CONFIG.update(env_config)


# Apply environment configuration on import
apply_environment_config()