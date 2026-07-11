# AWS Lambda Integration Guide

## Overview

This guide covers the AWS Lambda serverless processing implementation for clinical document processing in the RxDoctor system. The Lambda integration provides auto-scaling, cost optimization, and high-performance document processing capabilities.

## Architecture

### Components

1. **Lambda Functions** - Serverless document processing
2. **SQS Queues** - Message queuing and job distribution
3. **Auto-scaling Service** - Intelligent concurrency management
4. **Cost Optimizer** - Cost analysis and optimization recommendations
5. **Deployment Manager** - Infrastructure deployment and management

### Data Flow

```
Django App → SQS Queue → Lambda Function → Processing → Results Queue → Django App
     ↓                                                                        ↑
Auto-scaler ←→ CloudWatch Metrics ←→ Cost Optimizer ←→ Recommendations
```

## Setup and Configuration

### Prerequisites

1. AWS Account with appropriate permissions
2. AWS CLI configured
3. Python 3.9+ runtime
4. Required Python packages (boto3, pydicom, PIL, etc.)

### Environment Variables

Add the following to your Django settings:

```python
# AWS Configuration
AWS_REGION = 'us-east-1'
AWS_ACCESS_KEY_ID = 'your-access-key'
AWS_SECRET_ACCESS_KEY = 'your-secret-key'

# Lambda Configuration
LAMBDA_DOCUMENT_PROCESSOR_NAME = 'clinical-document-processor'
LAMBDA_MAX_CONCURRENT_EXECUTIONS = 100
LAMBDA_MIN_CONCURRENCY = 0
LAMBDA_SCALE_UP_THRESHOLD = 10
LAMBDA_SCALE_DOWN_THRESHOLD = 2
LAMBDA_COST_OPTIMIZATION = True

# SQS Configuration
SQS_PROCESSING_QUEUE_URL = 'https://sqs.us-east-1.amazonaws.com/123456789012/clinical-processing-queue'
SQS_RESULTS_QUEUE_URL = 'https://sqs.us-east-1.amazonaws.com/123456789012/clinical-results-queue'
SQS_DEAD_LETTER_QUEUE_URL = 'https://sqs.us-east-1.amazonaws.com/123456789012/clinical-processing-dlq'
SQS_VISIBILITY_TIMEOUT = 300
```

### Deployment

#### Option 1: CloudFormation Deployment (Recommended)

```python
from clinical_records.lambda.deployment.lambda_deployment import LambdaDeploymentManager

# Initialize deployment manager
deployment_manager = LambdaDeploymentManager(aws_region='us-east-1')

# Perform full deployment
source_dir = 'clinical_records/lambda'
result = deployment_manager.full_deployment(source_dir, environment='production')

print(f"Deployment successful: {result['success']}")
print(f"Stack ID: {result['components']['cloudformation']['stack_id']}")
```

#### Option 2: Manual Deployment

1. **Create IAM Role**
```python
role_arn = deployment_manager.create_iam_role()
```

2. **Create SQS Queues**
```python
queue_urls = deployment_manager.create_sqs_queues()
```

3. **Deploy Lambda Function**
```python
package_path = deployment_manager.create_lambda_package(source_dir, 'package.zip')
function_arn = deployment_manager.deploy_lambda_function(package_path, role_arn, queue_urls)
```

## Usage

### Queuing Documents for Processing

```python
from clinical_records.services.lambda_sqs_service import LambdaSQSService

lambda_service = LambdaSQSService()

# Queue single document
success = lambda_service.queue_document_processing(
    document_id='uuid-here',
    priority='high'  # 'high', 'normal', 'low'
)

# Queue batch processing
document_ids = ['uuid1', 'uuid2', 'uuid3']
success = lambda_service.queue_batch_processing(document_ids, priority='normal')
```

### Processing Results

```python
# Process results from Lambda
result = lambda_service.process_results_queue()
print(f"Processed {result['processed_count']} messages")
print(f"Errors: {result['error_count']}")
```

### Auto-scaling

```python
from clinical_records.services.lambda_autoscaler import LambdaAutoScaler

autoscaler = LambdaAutoScaler()

# Run auto-scaling cycle
result = autoscaler.run_auto_scaling_cycle()
print(f"Action: {result['decision']['action']}")
print(f"Target concurrency: {result['decision']['target_concurrency']}")

# Get scaling recommendations
recommendations = autoscaler.get_scaling_recommendations(time_horizon_hours=24)
```

### Cost Optimization

```python
from clinical_records.services.lambda_cost_optimizer import LambdaCostOptimizer

optimizer = LambdaCostOptimizer()

# Analyze costs
cost_metrics = optimizer.analyze_cost_metrics(days=30)
print(f"Total cost: ${cost_metrics.total_cost:.4f}")
print(f"Cost per invocation: ${cost_metrics.cost_per_invocation:.6f}")

# Get optimization recommendations
recommendations = optimizer.generate_optimization_recommendations(cost_metrics)
for rec in recommendations:
    print(f"Recommendation: {rec.recommendation_type}")
    print(f"Potential savings: ${rec.estimated_savings_monthly:.2f}/month")

# Generate comprehensive report
report = optimizer.get_optimization_report(days=30)
```

## Management Commands

### Basic Operations

```bash
# Queue a document for processing
python manage.py manage_lambda_processing queue_document --document-id uuid-here --priority high

# Queue batch processing
python manage.py manage_lambda_processing queue_batch --document-ids uuid1 uuid2 uuid3

# Process results queue
python manage.py manage_lambda_processing process_results

# Get current metrics
python manage.py manage_lambda_processing get_metrics
```

### Auto-scaling Operations

```bash
# Run auto-scaling cycle
python manage.py manage_lambda_processing auto_scale --auto-scale-cycles 3

# Scale to specific concurrency
python manage.py manage_lambda_processing scale_to --concurrency 20

# Monitor in real-time
python manage.py manage_lambda_processing monitor --monitor-duration 600 --interval 30
```

### Maintenance Operations

```bash
# Reprocess failed documents
python manage.py manage_lambda_processing reprocess_failed --max-age-hours 24

# Purge dead letter queue
python manage.py manage_lambda_processing purge_dlq

# Test Lambda function
python manage.py manage_lambda_processing test_lambda

# View scaling history
python manage.py manage_lambda_processing scaling_history --limit 50

# Get scaling statistics
python manage.py manage_lambda_processing scaling_stats
```

## Lambda Function Details

### Supported Document Types

- **PDF Documents** - OCR processing with AWS Textract
- **Image Documents** - OCR processing (JPEG, PNG, TIFF)
- **DICOM Files** - Medical imaging metadata extraction and preview generation
- **Text Files** - Direct text processing

### Processing Pipeline

1. **Document Download** - Retrieve from S3
2. **Type Detection** - Determine processing method
3. **Processing** - OCR, DICOM, or text processing
4. **Structured Data Extraction** - Parse lab reports, prescriptions, etc.
5. **Results Upload** - Store processed data and previews
6. **Notification** - Send results back to Django

### Error Handling

- **Retry Logic** - Automatic retries with exponential backoff
- **Dead Letter Queue** - Failed messages for manual review
- **Error Notifications** - Real-time error reporting
- **Fallback Processing** - Alternative processing methods

## Monitoring and Alerting

### CloudWatch Metrics

The system monitors the following metrics:

- **Invocations** - Number of Lambda invocations
- **Duration** - Execution time per invocation
- **Errors** - Error count and rate
- **Throttles** - Throttling events
- **Concurrent Executions** - Current concurrency level

### Custom Metrics

- **Queue Depth** - Number of pending messages
- **Processing Rate** - Documents processed per minute
- **Cost per Document** - Processing cost analysis
- **Success Rate** - Processing success percentage

### Alerts

Configure CloudWatch alarms for:

- High error rates (>5%)
- Long queue depths (>100 messages)
- High costs (>$100/day)
- Processing delays (>10 minutes)

## Cost Optimization

### Automatic Optimizations

1. **Memory Optimization** - Adjust memory based on execution patterns
2. **Concurrency Management** - Scale based on queue depth
3. **Timeout Optimization** - Prevent runaway executions
4. **Usage Pattern Analysis** - Identify cost-saving opportunities

### Manual Optimizations

1. **Batch Processing** - Process multiple documents together
2. **Scheduled Processing** - Process during off-peak hours
3. **Tiered Processing** - Use different configurations for different document types
4. **Archive Old Data** - Remove unused processing results

### Cost Monitoring

```python
# Get cost breakdown
breakdown = optimizer.get_cost_breakdown(days=30)
print(f"Execution cost: ${breakdown['cost_breakdown']['execution_cost']['amount']:.4f}")
print(f"Request cost: ${breakdown['cost_breakdown']['request_cost']['amount']:.4f}")

# Forecast costs
forecast = optimizer.forecast_costs(days_ahead=30)
print(f"Forecasted cost: ${forecast['forecasted_total_cost']:.2f}")
```

## Security Considerations

### IAM Permissions

The Lambda function requires the following permissions:

```json
{
    "Version": "2012-10-17",
    "Statement": [
        {
            "Effect": "Allow",
            "Action": [
                "s3:GetObject",
                "s3:PutObject",
                "s3:DeleteObject"
            ],
            "Resource": "arn:aws:s3:::clinical-documents/*"
        },
        {
            "Effect": "Allow",
            "Action": [
                "sqs:ReceiveMessage",
                "sqs:DeleteMessage",
                "sqs:SendMessage"
            ],
            "Resource": "arn:aws:sqs:*:*:clinical-*"
        },
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

### Data Encryption

- **In Transit** - All data encrypted with TLS 1.3
- **At Rest** - S3 server-side encryption enabled
- **Processing** - Temporary files encrypted in Lambda
- **Results** - Encrypted storage of processing results

### Access Control

- **Tenant Isolation** - Strict separation of clinic data
- **Role-based Access** - Granular permissions per user role
- **Audit Logging** - Complete audit trail of all operations
- **IP Restrictions** - Optional IP-based access controls

## Troubleshooting

### Common Issues

#### High Processing Costs

1. Check memory allocation - may be over-provisioned
2. Review provisioned concurrency settings
3. Analyze processing patterns for optimization opportunities
4. Consider batch processing for high-volume scenarios

#### Processing Delays

1. Check queue depth and scaling settings
2. Verify Lambda function timeout settings
3. Monitor for throttling events
4. Review error rates and dead letter queue

#### Failed Processing

1. Check dead letter queue for failed messages
2. Review CloudWatch logs for error details
3. Verify S3 permissions and file accessibility
4. Test with sample documents

### Debugging Commands

```bash
# Check queue status
python manage.py manage_lambda_processing get_metrics

# Monitor processing in real-time
python manage.py manage_lambda_processing monitor --interval 10

# Test Lambda function
python manage.py manage_lambda_processing test_lambda

# Check scaling history
python manage.py manage_lambda_processing scaling_history
```

### Log Analysis

Lambda function logs are available in CloudWatch Logs:

- Log Group: `/aws/lambda/clinical-document-processor`
- Log Streams: One per Lambda execution
- Retention: 30 days (configurable)

## Performance Tuning

### Memory Optimization

- **Small Documents** (<1MB): 512MB memory
- **Medium Documents** (1-10MB): 1024MB memory
- **Large Documents** (>10MB): 2048MB+ memory
- **DICOM Files**: 1536MB+ memory

### Concurrency Settings

- **Low Volume** (<100 docs/day): 0-2 provisioned concurrency
- **Medium Volume** (100-1000 docs/day): 2-10 provisioned concurrency
- **High Volume** (>1000 docs/day): 10+ provisioned concurrency

### Timeout Configuration

- **OCR Processing**: 300 seconds (5 minutes)
- **DICOM Processing**: 180 seconds (3 minutes)
- **Text Processing**: 60 seconds (1 minute)
- **Batch Processing**: 900 seconds (15 minutes)

## Integration with Existing Systems

### Django Integration

The Lambda system integrates seamlessly with existing Django models:

```python
# Automatic processing trigger
def save(self, *args, **kwargs):
    super().save(*args, **kwargs)
    if self.processing_status == 'uploaded':
        lambda_service = LambdaSQSService()
        lambda_service.queue_document_processing(str(self.id))
```

### API Integration

REST API endpoints for Lambda management:

- `POST /api/documents/{id}/process/` - Queue document processing
- `GET /api/lambda/metrics/` - Get processing metrics
- `POST /api/lambda/scale/` - Manual scaling
- `GET /api/lambda/costs/` - Cost analysis

### Webhook Integration

Configure webhooks for processing events:

```python
# Webhook notification on completion
def notify_completion(document_id, result):
    webhook_service = WebhookService()
    webhook_service.send_notification(
        event='document_processed',
        data={'document_id': document_id, 'result': result}
    )
```

## Best Practices

### Development

1. **Test Locally** - Use LocalStack for local testing
2. **Gradual Rollout** - Deploy to staging before production
3. **Monitor Closely** - Watch metrics during initial deployment
4. **Version Control** - Tag Lambda function versions

### Production

1. **Set Alerts** - Configure CloudWatch alarms
2. **Regular Reviews** - Weekly cost and performance reviews
3. **Capacity Planning** - Monitor growth trends
4. **Backup Strategy** - Regular backups of configuration

### Cost Management

1. **Regular Optimization** - Monthly optimization reviews
2. **Usage Monitoring** - Track usage patterns
3. **Budget Alerts** - Set spending alerts
4. **Resource Cleanup** - Remove unused resources

## Support and Maintenance

### Regular Tasks

- **Weekly**: Review processing metrics and costs
- **Monthly**: Run optimization analysis and apply recommendations
- **Quarterly**: Review and update scaling parameters
- **Annually**: Comprehensive architecture review

### Monitoring Checklist

- [ ] Processing success rate >95%
- [ ] Average processing time <2 minutes
- [ ] Queue depth <50 messages
- [ ] Error rate <5%
- [ ] Cost per document <$0.01

### Escalation Procedures

1. **High Error Rate** - Check logs, restart if needed
2. **Processing Delays** - Scale up concurrency
3. **High Costs** - Review and apply optimizations
4. **System Outage** - Failover to Django-Q processing

For additional support, contact the development team or refer to the AWS Lambda documentation.