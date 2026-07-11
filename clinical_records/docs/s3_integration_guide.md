# S3 Storage Backend Integration Guide

This guide covers the complete setup and usage of Amazon S3 storage backend for clinical records management in the RxDoctor platform.

## Overview

The S3 integration provides:
- Secure, scalable cloud storage for clinical documents
- Automatic encryption at rest and in transit
- Tenant-aware file organization
- Presigned URL generation for secure access
- CloudFront CDN integration for global content delivery
- Cost optimization through intelligent storage classes
- Comprehensive audit logging and monitoring

## Prerequisites

### AWS Account Setup
1. AWS account with appropriate permissions
2. S3 bucket creation permissions
3. IAM role/user with S3 access
4. Optional: CloudFront distribution permissions

### Required Dependencies
```bash
pip install django-storages boto3 botocore
```

## Configuration

### 1. Environment Variables
Set the following environment variables:

```bash
# AWS Credentials
AWS_ACCESS_KEY_ID=your_access_key
AWS_SECRET_ACCESS_KEY=your_secret_key

# S3 Configuration
CLINICAL_RECORDS_S3_BUCKET=rxdoctor-clinical-records-prod
AWS_S3_REGION_NAME=us-east-1

# Optional: KMS Encryption
CLINICAL_RECORDS_S3_KMS_KEY_ID=your_kms_key_id

# Optional: CloudFront
CLINICAL_RECORDS_CLOUDFRONT_DOMAIN=cdn.rxdoctor.com
CLOUDFRONT_KEY_ID=your_cloudfront_key_id
CLOUDFRONT_PRIVATE_KEY_PATH=/path/to/private_key.pem
```

### 2. Django Settings
Add to your Django settings:

```python
# Import S3 settings
from clinical_records.config.s3_settings import get_s3_django_settings

# Apply S3 settings
locals().update(get_s3_django_settings())

# Add to INSTALLED_APPS
INSTALLED_APPS = [
    # ... other apps
    'storages',
    'clinical_records',
]

# Storage configuration
DEFAULT_FILE_STORAGE = 'clinical_records.storage.s3_storage.ClinicalRecordsS3Storage'

# Or use S3 only for clinical records
CLINICAL_RECORDS_STORAGE = 'clinical_records.storage.s3_storage.ClinicalRecordsS3Storage'
```

## Setup Process

### 1. Initial S3 Setup
```bash
# Set up S3 bucket with all configurations
python manage.py setup_s3_storage setup

# Validate S3 setup
python manage.py setup_s3_storage validate

# Test S3 operations
python manage.py setup_s3_storage test
```

### 2. CloudFront Setup (Optional)
```bash
# Create CloudFront distribution
python manage.py setup_cloudfront create --wait

# Check distribution status
python manage.py setup_cloudfront status --distribution-id YOUR_DISTRIBUTION_ID
```

### 3. Data Migration
```bash
# Migrate existing files from local storage to S3
python manage.py migrate_to_s3 --batch-size 100

# Verify migration
python manage.py migrate_to_s3 --verify-only

# Migrate specific tenant
python manage.py migrate_to_s3 --tenant-id TENANT_UUID
```

## Usage

### 1. Basic File Operations

```python
from clinical_records.services.s3_service import ClinicalRecordsS3Service
from clinical_records.models import ClinicalRecord

# Initialize service
s3_service = ClinicalRecordsS3Service()

# Upload document
with open('document.pdf', 'rb') as file:
    result = s3_service.upload_clinical_document(
        clinical_record=clinical_record,
        file_obj=file,
        file_name='lab_report.pdf'
    )

# Generate download URL
download_url = s3_service.download_clinical_document(
    s3_key=result['s3_key'],
    expire_in=3600  # 1 hour
)

# Get document content
content = s3_service.get_document_content(result['s3_key'])

# Delete document
s3_service.delete_clinical_document(result['s3_key'])
```

### 2. Multipart Upload for Large Files

```python
# Create multipart upload
upload_info = s3_service.create_multipart_upload(
    clinical_record=clinical_record,
    file_name='large_imaging_study.dcm',
    file_size=500 * 1024 * 1024  # 500MB
)

# Upload parts
parts = []
with open('large_file.dcm', 'rb') as file:
    part_number = 1
    while True:
        chunk = file.read(upload_info['part_size'])
        if not chunk:
            break
        
        part_result = s3_service.upload_part(
            upload_info=upload_info,
            part_number=part_number,
            part_data=chunk
        )
        parts.append(part_result)
        part_number += 1

# Complete upload
s3_service.complete_multipart_upload(upload_info, parts)
```

### 3. Storage Usage Monitoring

```python
# Get tenant storage usage
usage_stats = s3_service.get_tenant_storage_usage(tenant_id)

print(f"Total documents: {usage_stats['total_documents']}")
print(f"Total size: {usage_stats['total_size_gb']:.2f} GB")
print(f"Record types: {usage_stats['record_types']}")
```

## File Organization

Files are organized in S3 with the following structure:

```
bucket-name/
├── tenants/
│   ├── {tenant_id}/
│   │   ├── lab_report/
│   │   │   ├── {patient_id}/
│   │   │   │   ├── lab_report_20240101.pdf
│   │   │   │   └── blood_test_20240115.pdf
│   │   ├── prescription/
│   │   │   ├── {patient_id}/
│   │   │   │   └── prescription_20240201.pdf
│   │   ├── imaging/
│   │   │   ├── {patient_id}/
│   │   │   │   ├── xray_20240301.dcm
│   │   │   │   └── ct_scan_20240315.dcm
│   │   └── other_types...
│   └── other_tenants...
└── cloudfront-logs/
    └── distribution_logs...
```

## Security Features

### 1. Encryption
- **At Rest**: AES-256 or AWS KMS encryption
- **In Transit**: TLS 1.3 for all communications
- **Client-side**: Optional additional encryption layer

### 2. Access Control
- **Bucket Policy**: Restricts access to authorized services
- **Presigned URLs**: Time-limited, secure access
- **CloudFront**: Signed URLs for CDN access
- **IAM Roles**: Principle of least privilege

### 3. Audit Logging
- **S3 Access Logs**: All bucket access logged
- **CloudTrail**: API call logging
- **Application Logs**: Custom audit trail
- **CloudWatch**: Monitoring and alerting

## Cost Optimization

### 1. Storage Classes
- **Standard-IA**: For infrequently accessed documents
- **Glacier**: For long-term archival
- **Deep Archive**: For compliance retention

### 2. Lifecycle Policies
```json
{
  "Rules": [
    {
      "ID": "ClinicalRecordsLifecycle",
      "Status": "Enabled",
      "Transitions": [
        {
          "Days": 30,
          "StorageClass": "STANDARD_IA"
        },
        {
          "Days": 90,
          "StorageClass": "GLACIER"
        },
        {
          "Days": 365,
          "StorageClass": "DEEP_ARCHIVE"
        }
      ]
    }
  ]
}
```

### 3. CloudFront Caching
- **Edge Locations**: Global content delivery
- **Cache Behaviors**: Optimized for document types
- **Compression**: Automatic file compression

## Monitoring and Alerting

### 1. CloudWatch Metrics
- Storage usage
- Request metrics
- Error rates
- Data transfer

### 2. Custom Alerts
```python
# Set up storage usage alerts
python manage.py setup_s3_storage metrics

# Monitor bucket health
python manage.py comprehensive_monitor --s3-health
```

### 3. Performance Monitoring
- Upload/download speeds
- Error rates
- Cache hit ratios
- Cost tracking

## Backup and Disaster Recovery

### 1. Cross-Region Replication
```bash
# Enable replication to backup region
aws s3api put-bucket-replication \
  --bucket rxdoctor-clinical-records-prod \
  --replication-configuration file://replication.json
```

### 2. Versioning
- Automatic file versioning
- Point-in-time recovery
- Accidental deletion protection

### 3. Backup Procedures
```bash
# Create backup snapshot
python manage.py backup_clinical_data --include-s3

# Restore from backup
python manage.py restore_clinical_data --from-s3-backup
```

## Troubleshooting

### Common Issues

#### 1. Access Denied Errors
```bash
# Check bucket policy
aws s3api get-bucket-policy --bucket your-bucket-name

# Verify IAM permissions
aws iam get-user-policy --user-name your-user --policy-name your-policy
```

#### 2. Upload Failures
```python
# Check file size limits
if file_size > 100 * 1024 * 1024:  # 100MB
    # Use multipart upload
    
# Verify content type
content_type = mimetypes.guess_type(filename)[0]
```

#### 3. Slow Performance
- Check region proximity
- Verify CloudFront configuration
- Monitor network connectivity
- Review cache settings

### Debugging Commands

```bash
# Validate S3 configuration
python manage.py setup_s3_storage validate

# Test S3 connectivity
python manage.py setup_s3_storage test

# Check bucket metrics
python manage.py setup_s3_storage metrics

# Sync database with S3
python manage.py migrate_to_s3 --verify-only
```

## Best Practices

### 1. Security
- Use IAM roles instead of access keys when possible
- Enable MFA for sensitive operations
- Regularly rotate access keys
- Monitor access patterns

### 2. Performance
- Use CloudFront for global distribution
- Implement proper caching strategies
- Use multipart upload for large files
- Monitor and optimize transfer speeds

### 3. Cost Management
- Implement lifecycle policies
- Monitor storage usage regularly
- Use appropriate storage classes
- Clean up incomplete multipart uploads

### 4. Reliability
- Enable versioning for critical data
- Set up cross-region replication
- Implement proper error handling
- Monitor system health

## Migration Checklist

- [ ] AWS account and permissions configured
- [ ] S3 bucket created and configured
- [ ] Django settings updated
- [ ] Dependencies installed
- [ ] S3 setup command executed
- [ ] CloudFront distribution created (optional)
- [ ] Data migration completed
- [ ] Migration verification passed
- [ ] Monitoring and alerting configured
- [ ] Backup procedures tested
- [ ] Documentation updated
- [ ] Team training completed

## Support and Maintenance

### Regular Tasks
- Monitor storage usage and costs
- Review access logs for security
- Update lifecycle policies as needed
- Test backup and restore procedures
- Update documentation

### Emergency Procedures
- Incident response plan
- Data recovery procedures
- Security breach protocols
- Performance issue resolution

For additional support, refer to:
- AWS S3 Documentation
- Django-storages Documentation
- Internal DevOps team
- AWS Support (if applicable)