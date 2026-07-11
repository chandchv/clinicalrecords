"""
Example Django settings configuration for AWS Textract integration.
Add these settings to your Django settings.py file.
"""

# AWS Textract Configuration
# =========================

# Enable/disable Textract service
TEXTRACT_ENABLED = True  # Set to False to disable Textract

# AWS Credentials and Region
# You can set these in settings.py or as environment variables
AWS_ACCESS_KEY_ID = 'your-aws-access-key-id'
AWS_SECRET_ACCESS_KEY = 'your-aws-secret-access-key'
AWS_REGION = 'us-east-1'  # Choose your preferred AWS region

# Alternative: Use environment variables (recommended for production)
# AWS_ACCESS_KEY_ID = os.environ.get('AWS_ACCESS_KEY_ID')
# AWS_SECRET_ACCESS_KEY = os.environ.get('AWS_SECRET_ACCESS_KEY')
# AWS_REGION = os.environ.get('AWS_REGION', 'us-east-1')

# Textract Processing Configuration
# ================================

# Confidence threshold for falling back to Textract
# If local OCR confidence is below this, use Textract
TEXTRACT_CONFIDENCE_THRESHOLD = 0.7

# Enable cost optimization
# When True, avoids Textract for high-confidence simple documents
TEXTRACT_COST_OPTIMIZATION = True

# Document type specific settings
TEXTRACT_PRESCRIPTION_ENABLED = True      # Always use Textract for prescriptions
TEXTRACT_LAB_REPORT_ENABLED = True        # Use Textract for lab reports
TEXTRACT_DISCHARGE_SUMMARY_ENABLED = True # Use Textract for discharge summaries

# File processing limits
TEXTRACT_MAX_FILE_SIZE_MB = 10  # Maximum file size for Textract processing
TEXTRACT_SUPPORTED_FORMATS = [
    'image/jpeg',
    'image/png', 
    'image/tiff',
    'application/pdf'
]

# Cost Management
# ==============

# Daily and monthly cost limits (in USD)
TEXTRACT_DAILY_COST_LIMIT = 50.0
TEXTRACT_MONTHLY_COST_LIMIT = 500.0

# Enable cost tracking
TEXTRACT_TRACK_COSTS = True

# Retry and Timeout Settings
# ==========================

TEXTRACT_RETRY_ATTEMPTS = 3
TEXTRACT_TIMEOUT_SECONDS = 30

# Fallback Behavior
# ================

# Fall back to local OCR if Textract fails
TEXTRACT_FALLBACK_TO_LOCAL = True

# Require patient consent before using cloud OCR
TEXTRACT_REQUIRE_CONSENT = True

# Logging and Monitoring
# =====================

# Log all Textract requests for monitoring
TEXTRACT_LOG_REQUESTS = True

# Environment-specific configurations
# ==================================

# Development environment
if DEBUG:
    TEXTRACT_ENABLED = False  # Disable in development to avoid costs
    TEXTRACT_FALLBACK_TO_LOCAL = True
    TEXTRACT_LOG_REQUESTS = True

# Production environment
else:
    TEXTRACT_ENABLED = True
    TEXTRACT_COST_OPTIMIZATION = True
    TEXTRACT_TRACK_COSTS = True
    TEXTRACT_DAILY_COST_LIMIT = 100.0
    TEXTRACT_MONTHLY_COST_LIMIT = 1000.0

# Clinical Records Processing Configuration
# ========================================

CLINICAL_RECORDS_PROCESSING = {
    # Maximum file size for processing (in bytes)
    'MAX_FILE_SIZE_MB': 100,
    
    # Supported file formats
    'SUPPORTED_FORMATS': [
        'application/pdf',
        'image/jpeg',
        'image/png',
        'image/tiff',
        'application/dicom',
        'text/plain',
        'text/csv'
    ],
    
    # Processing timeout (seconds)
    'PROCESSING_TIMEOUT': 300,
    
    # Retry configuration
    'max_attempts': 3,
    'RETRY_DELAYS': [60, 300, 900],  # Retry after 1min, 5min, 15min
    
    # Manual review threshold
    'MANUAL_REVIEW_THRESHOLD': 0.5,  # Flag for review if confidence < 50%
    
    # Background processing
    'ENABLE_BACKGROUND_PROCESSING': True,
    'BATCH_SIZE': 10,
    'QUEUE_PRIORITY': 'normal'
}

# Django-Q Configuration for Background Processing
# ===============================================

Q_CLUSTER = {
    'name': 'clinical_records',
    'workers': 4,
    'recycle': 500,
    'timeout': 300,
    'compress': True,
    'save_limit': 250,
    'queue_limit': 500,
    'cpu_affinity': 1,
    'label': 'Clinical Records Processing',
    'redis': {
        'host': '127.0.0.1',
        'port': 6379,
        'db': 0,
    }
}

# Logging Configuration
# ====================

LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'verbose': {
            'format': '{levelname} {asctime} {module} {process:d} {thread:d} {message}',
            'style': '{',
        },
    },
    'handlers': {
        'file': {
            'level': 'INFO',
            'class': 'logging.FileHandler',
            'filename': 'logs/clinical_records.log',
            'formatter': 'verbose',
        },
        'textract_file': {
            'level': 'INFO',
            'class': 'logging.FileHandler',
            'filename': 'logs/textract.log',
            'formatter': 'verbose',
        },
    },
    'loggers': {
        'clinical_records': {
            'handlers': ['file'],
            'level': 'INFO',
            'propagate': True,
        },
        'clinical_records.services.textract_service': {
            'handlers': ['textract_file'],
            'level': 'INFO',
            'propagate': False,
        },
        'clinical_records.services.enhanced_ocr_service': {
            'handlers': ['textract_file'],
            'level': 'INFO',
            'propagate': False,
        },
    },
}

# Security Settings
# ================

# Ensure AWS credentials are not logged
import logging
logging.getLogger('boto3').setLevel(logging.WARNING)
logging.getLogger('botocore').setLevel(logging.WARNING)
logging.getLogger('urllib3').setLevel(logging.WARNING)

# Example Environment Variables
# ============================
"""
Create a .env file or set these environment variables:

# AWS Configuration
AWS_ACCESS_KEY_ID=your-access-key-id
AWS_SECRET_ACCESS_KEY=your-secret-access-key
AWS_REGION=us-east-1

# Textract Configuration
TEXTRACT_ENABLED=true
TEXTRACT_CONFIDENCE_THRESHOLD=0.7
TEXTRACT_COST_OPTIMIZATION=true
TEXTRACT_PRESCRIPTION_ENABLED=true
TEXTRACT_DAILY_COST_LIMIT=50.0
TEXTRACT_MONTHLY_COST_LIMIT=500.0

# Django Configuration
DEBUG=false
SECRET_KEY=your-secret-key
DATABASE_URL=postgresql://user:pass@localhost/dbname
"""