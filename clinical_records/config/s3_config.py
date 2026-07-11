"""
S3 configuration settings for clinical records storage.
Provides centralized configuration for S3 backend integration.
"""

import os
from django.conf import settings


class S3Config:
    """
    Centralized S3 configuration for clinical records.
    """
    
    # S3 Bucket Configuration
    BUCKET_NAME = getattr(settings, 'CLINICAL_RECORDS_S3_BUCKET', 'rxdoctor-clinical-records')
    REGION_NAME = getattr(settings, 'AWS_S3_REGION_NAME', 'us-east-1')
    
    # AWS Credentials (prefer environment variables or IAM roles)
    ACCESS_KEY_ID = getattr(settings, 'AWS_ACCESS_KEY_ID', os.environ.get('AWS_ACCESS_KEY_ID'))
    SECRET_ACCESS_KEY = getattr(settings, 'AWS_SECRET_ACCESS_KEY', os.environ.get('AWS_SECRET_ACCESS_KEY'))
    
    # S3 Storage Settings
    DEFAULT_ACL = 'private'
    FILE_OVERWRITE = False
    SIGNATURE_VERSION = 's3v4'
    ADDRESSING_STYLE = 'virtual'
    
    # Encryption Settings
    SERVER_SIDE_ENCRYPTION = getattr(settings, 'CLINICAL_RECORDS_S3_ENCRYPTION', 'AES256')
    KMS_KEY_ID = getattr(settings, 'CLINICAL_RECORDS_S3_KMS_KEY_ID', None)
    
    # Storage Classes for Cost Optimization
    DEFAULT_STORAGE_CLASS = 'STANDARD_IA'  # Infrequent Access for clinical records
    ARCHIVE_STORAGE_CLASS = 'GLACIER'
    DEEP_ARCHIVE_STORAGE_CLASS = 'DEEP_ARCHIVE'
    
    # Presigned URL Settings
    PRESIGNED_URL_EXPIRY = getattr(settings, 'CLINICAL_RECORDS_PRESIGNED_URL_EXPIRY', 3600)  # 1 hour
    
    # CloudFront CDN Settings
    CLOUDFRONT_DOMAIN = getattr(settings, 'CLINICAL_RECORDS_CLOUDFRONT_DOMAIN', None)
    CLOUDFRONT_KEY_ID = getattr(settings, 'CLOUDFRONT_KEY_ID', None)
    CLOUDFRONT_PRIVATE_KEY_PATH = getattr(settings, 'CLOUDFRONT_PRIVATE_KEY_PATH', None)
    
    # Tenant Organization
    TENANT_PREFIX = 'tenants'
    
    # Multipart Upload Settings
    MULTIPART_THRESHOLD = 100 * 1024 * 1024  # 100MB
    MULTIPART_CHUNKSIZE = 10 * 1024 * 1024   # 10MB chunks
    
    # Lifecycle Management
    TRANSITION_TO_IA_DAYS = 30
    TRANSITION_TO_GLACIER_DAYS = 90
    TRANSITION_TO_DEEP_ARCHIVE_DAYS = 365
    
    # Security Settings
    REQUIRE_HTTPS = True
    ENABLE_VERSIONING = True
    ENABLE_MFA_DELETE = False  # Requires MFA device
    
    # Backup and Replication
    CROSS_REGION_REPLICATION = getattr(settings, 'CLINICAL_RECORDS_S3_REPLICATION', False)
    BACKUP_BUCKET = getattr(settings, 'CLINICAL_RECORDS_S3_BACKUP_BUCKET', None)
    
    @classmethod
    def get_storage_settings(cls):
        """Get storage settings dictionary for django-storages"""
        return {
            'bucket_name': cls.BUCKET_NAME,
            'region_name': cls.REGION_NAME,
            'access_key': cls.ACCESS_KEY_ID,
            'secret_key': cls.SECRET_ACCESS_KEY,
            'default_acl': cls.DEFAULT_ACL,
            'file_overwrite': cls.FILE_OVERWRITE,
            'signature_version': cls.SIGNATURE_VERSION,
            'addressing_style': cls.ADDRESSING_STYLE,
            'object_parameters': {
                'ServerSideEncryption': cls.SERVER_SIDE_ENCRYPTION,
                'StorageClass': cls.DEFAULT_STORAGE_CLASS,
            },
            'querystring_auth': True,
            'querystring_expire': cls.PRESIGNED_URL_EXPIRY,
            'custom_domain': cls.CLOUDFRONT_DOMAIN,
            'url_protocol': 'https' if cls.REQUIRE_HTTPS else 'http',
        }
    
    @classmethod
    def get_bucket_policy(cls):
        """Get S3 bucket policy for clinical records"""
        return {
            "Version": "2012-10-17",
            "Statement": [
                {
                    "Sid": "DenyInsecureConnections",
                    "Effect": "Deny",
                    "Principal": "*",
                    "Action": "s3:*",
                    "Resource": [
                        f"arn:aws:s3:::{cls.BUCKET_NAME}",
                        f"arn:aws:s3:::{cls.BUCKET_NAME}/*"
                    ],
                    "Condition": {
                        "Bool": {
                            "aws:SecureTransport": "false"
                        }
                    }
                },
                {
                    "Sid": "RequireServerSideEncryption",
                    "Effect": "Deny",
                    "Principal": "*",
                    "Action": "s3:PutObject",
                    "Resource": f"arn:aws:s3:::{cls.BUCKET_NAME}/*",
                    "Condition": {
                        "StringNotEquals": {
                            "s3:x-amz-server-side-encryption": cls.SERVER_SIDE_ENCRYPTION
                        }
                    }
                },
                {
                    "Sid": "RestrictToTenantPaths",
                    "Effect": "Allow",
                    "Principal": {
                        "AWS": f"arn:aws:iam::*:role/RxDoctorClinicalRecordsRole"
                    },
                    "Action": [
                        "s3:GetObject",
                        "s3:PutObject",
                        "s3:DeleteObject"
                    ],
                    "Resource": f"arn:aws:s3:::{cls.BUCKET_NAME}/{cls.TENANT_PREFIX}/*"
                }
            ]
        }
    
    @classmethod
    def get_lifecycle_configuration(cls):
        """Get S3 lifecycle configuration for cost optimization"""
        return {
            'Rules': [
                {
                    'ID': 'ClinicalRecordsLifecycle',
                    'Status': 'Enabled',
                    'Filter': {'Prefix': f'{cls.TENANT_PREFIX}/'},
                    'Transitions': [
                        {
                            'Days': cls.TRANSITION_TO_IA_DAYS,
                            'StorageClass': 'STANDARD_IA'
                        },
                        {
                            'Days': cls.TRANSITION_TO_GLACIER_DAYS,
                            'StorageClass': 'GLACIER'
                        },
                        {
                            'Days': cls.TRANSITION_TO_DEEP_ARCHIVE_DAYS,
                            'StorageClass': 'DEEP_ARCHIVE'
                        }
                    ]
                },
                {
                    'ID': 'DeleteIncompleteMultipartUploads',
                    'Status': 'Enabled',
                    'Filter': {},
                    'AbortIncompleteMultipartUpload': {
                        'DaysAfterInitiation': 7
                    }
                },
                {
                    'ID': 'DeleteOldVersions',
                    'Status': 'Enabled',
                    'Filter': {},
                    'NoncurrentVersionTransitions': [
                        {
                            'NoncurrentDays': 30,
                            'StorageClass': 'STANDARD_IA'
                        },
                        {
                            'NoncurrentDays': 90,
                            'StorageClass': 'GLACIER'
                        }
                    ],
                    'NoncurrentVersionExpiration': {
                        'NoncurrentDays': 365
                    }
                }
            ]
        }
    
    @classmethod
    def get_cors_configuration(cls):
        """Get CORS configuration for web access"""
        return {
            'CORSRules': [
                {
                    'AllowedHeaders': ['*'],
                    'AllowedMethods': ['GET', 'PUT', 'POST', 'DELETE', 'HEAD'],
                    'AllowedOrigins': [
                        'https://*.rxdoctor.com',
                        'https://localhost:3000',  # Development
                        'http://localhost:3000'    # Development
                    ],
                    'ExposeHeaders': ['ETag', 'x-amz-version-id'],
                    'MaxAgeSeconds': 3000
                }
            ]
        }
    
    @classmethod
    def get_notification_configuration(cls):
        """Get S3 event notification configuration"""
        return {
            'CloudWatchConfigurations': [
                {
                    'Id': 'ClinicalRecordsCloudWatch',
                    'CloudWatchConfiguration': {
                        'LogGroupName': '/aws/s3/clinical-records',
                        'FilterRules': [
                            {
                                'Name': 'prefix',
                                'Value': f'{cls.TENANT_PREFIX}/'
                            }
                        ]
                    },
                    'Events': [
                        's3:ObjectCreated:*',
                        's3:ObjectRemoved:*'
                    ]
                }
            ]
        }
    
    @classmethod
    def validate_configuration(cls):
        """Validate S3 configuration"""
        errors = []
        
        if not cls.BUCKET_NAME:
            errors.append("S3 bucket name is required")
        
        if not cls.ACCESS_KEY_ID and not os.environ.get('AWS_ACCESS_KEY_ID'):
            errors.append("AWS access key ID is required")
        
        if not cls.SECRET_ACCESS_KEY and not os.environ.get('AWS_SECRET_ACCESS_KEY'):
            errors.append("AWS secret access key is required")
        
        if cls.SERVER_SIDE_ENCRYPTION == 'aws:kms' and not cls.KMS_KEY_ID:
            errors.append("KMS key ID is required when using KMS encryption")
        
        if cls.CLOUDFRONT_DOMAIN and not cls.CLOUDFRONT_KEY_ID:
            errors.append("CloudFront key ID is required when using CloudFront")
        
        return errors


# Environment-specific configurations
class DevelopmentS3Config(S3Config):
    """Development environment S3 configuration"""
    BUCKET_NAME = 'rxdoctor-clinical-records-dev'
    DEFAULT_STORAGE_CLASS = 'STANDARD'  # No IA for dev
    PRESIGNED_URL_EXPIRY = 7200  # 2 hours for development


class StagingS3Config(S3Config):
    """Staging environment S3 configuration"""
    BUCKET_NAME = 'rxdoctor-clinical-records-staging'
    DEFAULT_STORAGE_CLASS = 'STANDARD_IA'
    PRESIGNED_URL_EXPIRY = 3600  # 1 hour


class ProductionS3Config(S3Config):
    """Production environment S3 configuration"""
    BUCKET_NAME = 'rxdoctor-clinical-records-prod'
    DEFAULT_STORAGE_CLASS = 'STANDARD_IA'
    PRESIGNED_URL_EXPIRY = 1800  # 30 minutes for security
    ENABLE_MFA_DELETE = True
    CROSS_REGION_REPLICATION = True


def get_s3_config():
    """Get S3 configuration based on environment"""
    environment = getattr(settings, 'ENVIRONMENT', 'development').lower()
    
    if environment == 'production':
        return ProductionS3Config
    elif environment == 'staging':
        return StagingS3Config
    else:
        return DevelopmentS3Config