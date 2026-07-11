# AWS Textract Integration Guide

This guide explains how to set up and use AWS Textract for enhanced OCR processing in the Clinical Records Management system.

## Overview

The AWS Textract integration provides enhanced OCR capabilities that significantly improve accuracy for clinical documents, especially prescriptions and lab reports. The system intelligently combines local Tesseract OCR with AWS Textract to optimize both accuracy and cost.

## Features

### Enhanced OCR Capabilities
- **Prescription OCR**: Specialized extraction of medication names, dosages, frequencies, and instructions
- **Lab Report Processing**: Table and form extraction for structured lab results
- **Form Recognition**: Automatic extraction of key-value pairs from medical forms
- **Table Extraction**: Structured data extraction from tabular lab reports
- **Handwriting Recognition**: Improved accuracy for handwritten prescriptions

### Intelligent Processing
- **Hybrid Processing**: Combines local OCR with Textract for optimal results
- **Cost Optimization**: Uses Textract only when needed based on confidence thresholds
- **Fallback Mechanism**: Graceful fallback to local OCR if Textract fails
- **Document Type Routing**: Different processing strategies for different document types

### Cost Management
- **Configurable Thresholds**: Set confidence levels for Textract usage
- **Cost Tracking**: Monitor and limit daily/monthly Textract costs
- **Smart Routing**: Avoid Textract for high-confidence simple documents

## Setup Instructions

### 1. AWS Account Setup

1. **Create AWS Account**: Sign up for an AWS account if you don't have one
2. **Enable Textract**: Ensure AWS Textract is available in your chosen region
3. **Create IAM User**: Create an IAM user with Textract permissions

#### Required IAM Permissions
```json
{
    "Version": "2012-10-17",
    "Statement": [
        {
            "Effect": "Allow",
            "Action": [
                "textract:DetectDocumentText",
                "textract:AnalyzeDocument"
            ],
            "Resource": "*"
        }
    ]
}
```

### 2. Django Configuration

Add the following settings to your Django `settings.py`:

```python
# AWS Textract Configuration
TEXTRACT_ENABLED = True
AWS_ACCESS_KEY_ID = 'your-aws-access-key-id'
AWS_SECRET_ACCESS_KEY = 'your-aws-secret-access-key'
AWS_REGION = 'us-east-1'

# Processing Configuration
TEXTRACT_CONFIDENCE_THRESHOLD = 0.7
TEXTRACT_COST_OPTIMIZATION = True
TEXTRACT_PRESCRIPTION_ENABLED = True
TEXTRACT_LAB_REPORT_ENABLED = True

# Cost Management
TEXTRACT_DAILY_COST_LIMIT = 50.0
TEXTRACT_MONTHLY_COST_LIMIT = 500.0
```

### 3. Environment Variables (Recommended)

For production, use environment variables:

```bash
export AWS_ACCESS_KEY_ID="your-access-key-id"
export AWS_SECRET_ACCESS_KEY="your-secret-access-key"
export AWS_REGION="us-east-1"
export TEXTRACT_ENABLED="true"
```

### 4. Install Dependencies

The required dependencies are already included in `requirements.txt`:
- `boto3` - AWS SDK for Python
- `botocore` - Low-level AWS service access

### 5. Test the Setup

Use the management command to test your configuration:

```bash
# Check configuration status
python manage.py setup_textract --status

# Test Textract connection
python manage.py setup_textract --test

# Test with a sample image
python manage.py setup_textract --test --test-image path/to/prescription.jpg
```

## Usage

### Automatic Processing

Once configured, Textract integration works automatically:

1. **Document Upload**: When a clinical document is uploaded
2. **Type Detection**: System determines document type (prescription, lab report, etc.)
3. **Processing Decision**: Decides whether to use local OCR, Textract, or both
4. **Enhanced Extraction**: Extracts structured data using appropriate method
5. **Result Combination**: Combines results for optimal accuracy

### Manual Processing

You can also trigger processing manually:

```python
from clinical_records.services.enhanced_ocr_service import enhanced_ocr_service

# Process a prescription
with open('prescription.jpg', 'rb') as f:
    image_data = f.read()

result = enhanced_ocr_service.process_prescription(image_data)
print(f"Confidence: {result['confidence']}")
print(f"Textract used: {result['textract_used']}")
print(f"Medications: {result['structured_data']['medications']}")
```

### API Integration

The enhanced OCR is automatically integrated into the document upload API:

```python
# Upload document via API
POST /api/clinical-records/documents/upload/
Content-Type: multipart/form-data

{
    "file": prescription_image.jpg,
    "record_type": "prescription",
    "patient_id": "patient-uuid"
}

# Response includes enhanced OCR results
{
    "document_id": "doc-uuid",
    "processing_status": "completed",
    "ocr_confidence": 0.92,
    "textract_used": true,
    "structured_data": {
        "medications": [...],
        "patient_info": {...}
    }
}
```

## Configuration Options

### Processing Thresholds

```python
# Confidence threshold for Textract fallback
TEXTRACT_CONFIDENCE_THRESHOLD = 0.7  # Use Textract if local OCR < 70%

# Document type specific settings
TEXTRACT_PRESCRIPTION_ENABLED = True      # Always use for prescriptions
TEXTRACT_LAB_REPORT_ENABLED = True        # Use for lab reports
TEXTRACT_DISCHARGE_SUMMARY_ENABLED = True # Use for discharge summaries
```

### Cost Management

```python
# Cost limits (USD)
TEXTRACT_DAILY_COST_LIMIT = 50.0
TEXTRACT_MONTHLY_COST_LIMIT = 500.0

# Cost optimization
TEXTRACT_COST_OPTIMIZATION = True  # Avoid Textract for high-confidence simple docs
TEXTRACT_TRACK_COSTS = True        # Enable cost tracking
```

### File Processing

```python
# File size and format limits
TEXTRACT_MAX_FILE_SIZE_MB = 10
TEXTRACT_SUPPORTED_FORMATS = [
    'image/jpeg',
    'image/png',
    'image/tiff',
    'application/pdf'
]
```

## Processing Logic

### Decision Flow

1. **Document Type Check**: Determine if document type benefits from Textract
2. **Confidence Check**: If local OCR confidence < threshold, use Textract
3. **Cost Check**: Verify daily/monthly limits not exceeded
4. **Format Check**: Ensure file format is supported by Textract
5. **Processing**: Execute appropriate OCR method(s)
6. **Result Combination**: Merge results for best outcome

### Document Type Routing

| Document Type | Processing Strategy |
|---------------|-------------------|
| Prescription | Always use Textract (if enabled) |
| Lab Report | Use Textract for table extraction |
| Discharge Summary | Use Textract for form extraction |
| Progress Note | Local OCR unless low confidence |
| Vital Signs | Local OCR unless low confidence |
| Insurance Forms | Always use Textract |
| Referral Letters | Use Textract for complex layouts |

## Monitoring and Troubleshooting

### Logging

Enhanced OCR activities are logged to help with monitoring:

```python
# Configure logging in settings.py
LOGGING = {
    'loggers': {
        'clinical_records.services.textract_service': {
            'handlers': ['file'],
            'level': 'INFO',
        },
        'clinical_records.services.enhanced_ocr_service': {
            'handlers': ['file'],
            'level': 'INFO',
        },
    },
}
```

### Cost Monitoring

Track Textract usage and costs:

```python
from clinical_records.services.enhanced_ocr_service import enhanced_ocr_service

# Get processing statistics
stats = enhanced_ocr_service.get_processing_stats()
print(f"Textract enabled: {stats['textract_enabled']}")
print(f"Cost optimization: {stats['cost_optimization']}")
```

### Common Issues

#### 1. Textract Not Working
- Check AWS credentials are correct
- Verify IAM permissions include Textract access
- Ensure AWS region supports Textract
- Check network connectivity to AWS

#### 2. High Costs
- Review `TEXTRACT_CONFIDENCE_THRESHOLD` setting
- Enable `TEXTRACT_COST_OPTIMIZATION`
- Set appropriate daily/monthly limits
- Monitor document types being processed

#### 3. Low Accuracy
- Ensure image quality is good (300+ DPI recommended)
- Check file format is supported
- Verify document type is correctly identified
- Review confidence thresholds

## Performance Optimization

### Best Practices

1. **Image Quality**: Use high-resolution images (300+ DPI) for best results
2. **File Size**: Keep files under 10MB for optimal processing speed
3. **Document Types**: Correctly classify documents for appropriate processing
4. **Batch Processing**: Process multiple documents together when possible
5. **Caching**: Results are cached to avoid reprocessing

### Cost Optimization

1. **Threshold Tuning**: Adjust confidence thresholds based on your accuracy needs
2. **Document Filtering**: Only use Textract for documents that benefit from it
3. **Preprocessing**: Clean up images locally before sending to Textract
4. **Monitoring**: Regularly review costs and adjust settings

## Security Considerations

### Data Privacy

- **Encryption**: All data is encrypted in transit to AWS
- **Retention**: AWS Textract doesn't store your documents
- **Compliance**: Textract is HIPAA eligible when properly configured
- **Audit Trail**: All processing activities are logged

### Access Control

- **IAM Policies**: Use least-privilege IAM policies
- **Credentials**: Store AWS credentials securely (environment variables)
- **Network**: Consider VPC endpoints for additional security
- **Monitoring**: Monitor AWS CloudTrail for API access

## Pricing

### AWS Textract Pricing (as of 2024)

- **DetectDocumentText**: $0.0015 per page
- **AnalyzeDocument (Forms)**: $0.05 per page
- **AnalyzeDocument (Tables)**: $0.015 per page

### Cost Examples

| Document Type | Processing Method | Estimated Cost per Page |
|---------------|------------------|------------------------|
| Simple Text | Local OCR only | $0.00 |
| Prescription | Textract + Forms | $0.0515 |
| Lab Report | Textract + Tables | $0.0165 |
| Complex Form | Textract + Forms + Tables | $0.0665 |

## Support and Troubleshooting

### Management Commands

```bash
# Check configuration
python manage.py setup_textract --status

# Test connection
python manage.py setup_textract --test

# Configure interactively
python manage.py setup_textract --configure

# Test with image
python manage.py setup_textract --test --test-image sample.jpg
```

### Debug Mode

Enable debug logging for detailed troubleshooting:

```python
LOGGING = {
    'loggers': {
        'clinical_records.services.textract_service': {
            'level': 'DEBUG',
        },
    },
}
```

### Getting Help

1. Check the logs for error messages
2. Verify AWS credentials and permissions
3. Test with the management command
4. Review AWS Textract service status
5. Contact support with specific error messages

## Migration from Local OCR

If you're upgrading from local-only OCR:

1. **Backup**: Backup existing OCR results
2. **Configure**: Set up Textract configuration
3. **Test**: Test with sample documents
4. **Gradual Rollout**: Enable for specific document types first
5. **Monitor**: Watch costs and accuracy improvements
6. **Optimize**: Adjust thresholds based on results

The system maintains backward compatibility, so existing documents will continue to work while new documents benefit from enhanced OCR.