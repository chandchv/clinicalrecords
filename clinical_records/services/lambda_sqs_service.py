"""
AWS Lambda and SQS Integration Service

This service manages the integration between Django and AWS Lambda functions
for serverless document processing, including SQS message handling and
auto-scaling coordination.
"""

import json
import boto3
import logging
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Any, Optional
from django.conf import settings
from django.core.cache import cache
from django.db import transaction
from botocore.exceptions import ClientError, BotoCoreError

from ..models import ClinicalDocument
from .audit_service import AuditService

logger = logging.getLogger(__name__)


class LambdaSQSService:
    """
    Service for managing Lambda function invocations and SQS message processing
    """
    
    def __init__(self):
        """Initialize AWS clients and configuration"""
        self.lambda_client = boto3.client(
            'lambda',
            region_name=getattr(settings, 'AWS_REGION', 'us-east-1'),
            aws_access_key_id=getattr(settings, 'AWS_ACCESS_KEY_ID', None),
            aws_secret_access_key=getattr(settings, 'AWS_SECRET_ACCESS_KEY', None)
        )
        
        self.sqs_client = boto3.client(
            'sqs',
            region_name=getattr(settings, 'AWS_REGION', 'us-east-1'),
            aws_access_key_id=getattr(settings, 'AWS_ACCESS_KEY_ID', None),
            aws_secret_access_key=getattr(settings, 'AWS_SECRET_ACCESS_KEY', None)
        )
        
        # Configuration
        self.lambda_function_name = getattr(settings, 'LAMBDA_DOCUMENT_PROCESSOR_NAME', 
                                          'clinical-document-processor')
        self.processing_queue_url = getattr(settings, 'SQS_PROCESSING_QUEUE_URL', '')
        self.results_queue_url = getattr(settings, 'SQS_RESULTS_QUEUE_URL', '')
        self.dead_letter_queue_url = getattr(settings, 'SQS_DEAD_LETTER_QUEUE_URL', '')
        
        # Auto-scaling configuration
        self.max_concurrent_executions = getattr(settings, 'LAMBDA_MAX_CONCURRENT_EXECUTIONS', 100)
        self.batch_size = getattr(settings, 'LAMBDA_BATCH_SIZE', 10)
        self.visibility_timeout = getattr(settings, 'SQS_VISIBILITY_TIMEOUT', 300)
        
        self.audit_service = AuditService()
    
    def queue_document_processing(self, document_id: str, priority: str = 'normal') -> bool:
        """
        Queue a document for Lambda processing
        
        Args:
            document_id: UUID of the clinical document
            priority: Processing priority ('high', 'normal', 'low')
            
        Returns:
            bool: True if successfully queued, False otherwise
        """
        try:
            document = ClinicalDocument.objects.get(id=document_id)
            
            # Prepare message
            message = {
                'task_type': 'process_document',
                'document_id': str(document.id),
                's3_key': document.s3_key,
                's3_bucket': document.s3_bucket,
                'content_type': document.content_type,
                'file_name': document.file_name,
                'file_size': document.file_size,
                'clinical_record_id': str(document.clinical_record.id),
                'patient_id': str(document.clinical_record.patient.id),
                'clinic_id': str(document.clinical_record.clinic.id),
                'priority': priority,
                'queued_at': datetime.now(timezone.utc).isoformat(),
                'retry_count': 0
            }
            
            # Set message attributes for priority handling
            message_attributes = {
                'Priority': {
                    'StringValue': priority,
                    'DataType': 'String'
                },
                'DocumentType': {
                    'StringValue': document.content_type,
                    'DataType': 'String'
                }
            }
            
            # Calculate delay for low priority items
            delay_seconds = 0
            if priority == 'low':
                delay_seconds = 60  # 1 minute delay for low priority
            
            # Send message to SQS
            response = self.sqs_client.send_message(
                QueueUrl=self.processing_queue_url,
                MessageBody=json.dumps(message),
                MessageAttributes=message_attributes,
                DelaySeconds=delay_seconds
            )
            
            # Update document status
            document.processing_status = 'queued'
            document.save(update_fields=['processing_status'])
            
            # Log the action
            self.audit_service.log_action(
                user=None,
                action='DOCUMENT_QUEUED_FOR_LAMBDA',
                resource_type='CLINICAL_DOCUMENT',
                resource_id=str(document.id),
                details=f"Document queued for Lambda processing with priority: {priority}",
                tenant=document.clinical_record.clinic
            )
            
            logger.info(f"Document {document_id} queued for Lambda processing")
            return True
            
        except ClinicalDocument.DoesNotExist:
            logger.error(f"Document {document_id} not found")
            return False
        except Exception as e:
            logger.error(f"Error queuing document {document_id}: {str(e)}")
            return False
    
    def queue_batch_processing(self, document_ids: List[str], priority: str = 'normal') -> bool:
        """
        Queue multiple documents for batch processing
        
        Args:
            document_ids: List of document UUIDs
            priority: Processing priority
            
        Returns:
            bool: True if successfully queued, False otherwise
        """
        try:
            documents = ClinicalDocument.objects.filter(id__in=document_ids)
            
            if not documents.exists():
                logger.error("No valid documents found for batch processing")
                return False
            
            # Prepare batch message
            s3_keys = {}
            content_types = {}
            
            for doc in documents:
                s3_keys[str(doc.id)] = doc.s3_key
                content_types[str(doc.id)] = doc.content_type
            
            message = {
                'task_type': 'batch_processing',
                'document_ids': [str(doc.id) for doc in documents],
                's3_keys': s3_keys,
                'content_types': content_types,
                's3_bucket': documents.first().s3_bucket,
                'priority': priority,
                'queued_at': datetime.now(timezone.utc).isoformat(),
                'batch_size': len(document_ids)
            }
            
            # Send batch message
            response = self.sqs_client.send_message(
                QueueUrl=self.processing_queue_url,
                MessageBody=json.dumps(message),
                MessageAttributes={
                    'Priority': {
                        'StringValue': priority,
                        'DataType': 'String'
                    },
                    'BatchSize': {
                        'StringValue': str(len(document_ids)),
                        'DataType': 'Number'
                    }
                }
            )
            
            # Update document statuses
            documents.update(processing_status='queued')
            
            logger.info(f"Batch of {len(document_ids)} documents queued for Lambda processing")
            return True
            
        except Exception as e:
            logger.error(f"Error queuing batch processing: {str(e)}")
            return False
    
    def process_results_queue(self) -> Dict[str, Any]:
        """
        Process messages from the results queue
        
        Returns:
            Dict containing processing statistics
        """
        processed_count = 0
        error_count = 0
        
        try:
            # Receive messages from results queue
            response = self.sqs_client.receive_message(
                QueueUrl=self.results_queue_url,
                MaxNumberOfMessages=10,
                WaitTimeSeconds=5,
                MessageAttributeNames=['All']
            )
            
            messages = response.get('Messages', [])
            
            for message in messages:
                try:
                    # Parse message
                    message_body = json.loads(message['Body'])
                    message_type = message_body.get('message_type')
                    
                    if message_type == 'processing_complete':
                        self._handle_processing_complete(message_body)
                        processed_count += 1
                    elif message_type == 'processing_error':
                        self._handle_processing_error(message_body)
                        error_count += 1
                    else:
                        logger.warning(f"Unknown message type: {message_type}")
                    
                    # Delete message from queue
                    self.sqs_client.delete_message(
                        QueueUrl=self.results_queue_url,
                        ReceiptHandle=message['ReceiptHandle']
                    )
                    
                except Exception as e:
                    logger.error(f"Error processing result message: {str(e)}")
                    error_count += 1
            
            return {
                'processed_count': processed_count,
                'error_count': error_count,
                'total_messages': len(messages)
            }
            
        except Exception as e:
            logger.error(f"Error processing results queue: {str(e)}")
            return {
                'processed_count': 0,
                'error_count': 1,
                'total_messages': 0,
                'error': str(e)
            }
    
    def _handle_processing_complete(self, message_body: Dict[str, Any]):
        """Handle successful processing completion"""
        document_id = message_body.get('document_id')
        result = message_body.get('result', {})
        
        try:
            with transaction.atomic():
                document = ClinicalDocument.objects.select_for_update().get(id=document_id)
                
                # Update document with processing results
                document.processing_status = 'completed'
                document.ocr_text = result.get('ocr_text', '')
                document.ocr_confidence = result.get('confidence', 0.0)
                document.structured_data = result.get('structured_data', {})
                
                # Update DICOM-specific fields
                if 'dicom_metadata' in result:
                    document.dicom_metadata = result['dicom_metadata']
                    document.preview_s3_key = result.get('preview_s3_key', '')
                    document.thumbnail_s3_key = result.get('thumbnail_s3_key', '')
                
                document.save()
                
                # Log completion
                self.audit_service.log_action(
                    user=None,
                    action='LAMBDA_PROCESSING_COMPLETED',
                    resource_type='CLINICAL_DOCUMENT',
                    resource_id=str(document.id),
                    details=f"Lambda processing completed with confidence: {result.get('confidence', 0.0)}",
                    tenant=document.clinical_record.clinic
                )
                
                logger.info(f"Document {document_id} processing completed successfully")
                
        except ClinicalDocument.DoesNotExist:
            logger.error(f"Document {document_id} not found for completion update")
        except Exception as e:
            logger.error(f"Error handling processing completion for {document_id}: {str(e)}")
    
    def _handle_processing_error(self, message_body: Dict[str, Any]):
        """Handle processing error"""
        document_id = message_body.get('document_id')
        error_message = message_body.get('error', 'Unknown error')
        
        try:
            with transaction.atomic():
                document = ClinicalDocument.objects.select_for_update().get(id=document_id)
                
                # Update document status
                document.processing_status = 'failed'
                document.save(update_fields=['processing_status'])
                
                # Log error
                self.audit_service.log_action(
                    user=None,
                    action='LAMBDA_PROCESSING_FAILED',
                    resource_type='CLINICAL_DOCUMENT',
                    resource_id=str(document.id),
                    details=f"Lambda processing failed: {error_message}",
                    tenant=document.clinical_record.clinic
                )
                
                logger.error(f"Document {document_id} processing failed: {error_message}")
                
        except ClinicalDocument.DoesNotExist:
            logger.error(f"Document {document_id} not found for error update")
        except Exception as e:
            logger.error(f"Error handling processing error for {document_id}: {str(e)}")
    
    def invoke_lambda_directly(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """
        Invoke Lambda function directly (synchronous)
        
        Args:
            payload: Lambda function payload
            
        Returns:
            Dict containing Lambda response
        """
        try:
            response = self.lambda_client.invoke(
                FunctionName=self.lambda_function_name,
                InvocationType='RequestResponse',
                Payload=json.dumps(payload)
            )
            
            # Parse response
            response_payload = json.loads(response['Payload'].read())
            
            return {
                'success': True,
                'status_code': response['StatusCode'],
                'payload': response_payload
            }
            
        except Exception as e:
            logger.error(f"Error invoking Lambda directly: {str(e)}")
            return {
                'success': False,
                'error': str(e)
            }
    
    def get_queue_metrics(self) -> Dict[str, Any]:
        """
        Get SQS queue metrics and statistics
        
        Returns:
            Dict containing queue metrics
        """
        try:
            metrics = {}
            
            # Get processing queue attributes
            processing_attrs = self.sqs_client.get_queue_attributes(
                QueueUrl=self.processing_queue_url,
                AttributeNames=['All']
            )
            
            metrics['processing_queue'] = {
                'approximate_number_of_messages': int(processing_attrs['Attributes'].get('ApproximateNumberOfMessages', 0)),
                'approximate_number_of_messages_not_visible': int(processing_attrs['Attributes'].get('ApproximateNumberOfMessagesNotVisible', 0)),
                'approximate_number_of_messages_delayed': int(processing_attrs['Attributes'].get('ApproximateNumberOfMessagesDelayed', 0))
            }
            
            # Get results queue attributes
            results_attrs = self.sqs_client.get_queue_attributes(
                QueueUrl=self.results_queue_url,
                AttributeNames=['All']
            )
            
            metrics['results_queue'] = {
                'approximate_number_of_messages': int(results_attrs['Attributes'].get('ApproximateNumberOfMessages', 0)),
                'approximate_number_of_messages_not_visible': int(results_attrs['Attributes'].get('ApproximateNumberOfMessagesNotVisible', 0))
            }
            
            # Get dead letter queue attributes if configured
            if self.dead_letter_queue_url:
                dlq_attrs = self.sqs_client.get_queue_attributes(
                    QueueUrl=self.dead_letter_queue_url,
                    AttributeNames=['All']
                )
                
                metrics['dead_letter_queue'] = {
                    'approximate_number_of_messages': int(dlq_attrs['Attributes'].get('ApproximateNumberOfMessages', 0))
                }
            
            return metrics
            
        except Exception as e:
            logger.error(f"Error getting queue metrics: {str(e)}")
            return {'error': str(e)}
    
    def get_lambda_metrics(self) -> Dict[str, Any]:
        """
        Get Lambda function metrics and statistics
        
        Returns:
            Dict containing Lambda metrics
        """
        try:
            # Get function configuration
            function_config = self.lambda_client.get_function(
                FunctionName=self.lambda_function_name
            )
            
            metrics = {
                'function_name': self.lambda_function_name,
                'runtime': function_config['Configuration']['Runtime'],
                'memory_size': function_config['Configuration']['MemorySize'],
                'timeout': function_config['Configuration']['Timeout'],
                'last_modified': function_config['Configuration']['LastModified'],
                'code_size': function_config['Configuration']['CodeSize'],
                'state': function_config['Configuration']['State']
            }
            
            # Get concurrency configuration
            try:
                concurrency = self.lambda_client.get_provisioned_concurrency_config(
                    FunctionName=self.lambda_function_name
                )
                metrics['provisioned_concurrency'] = concurrency['RequestedProvisionedConcurrencyUnits']
            except ClientError:
                # No provisioned concurrency configured
                metrics['provisioned_concurrency'] = 0
            
            return metrics
            
        except Exception as e:
            logger.error(f"Error getting Lambda metrics: {str(e)}")
            return {'error': str(e)}
    
    def scale_lambda_concurrency(self, target_concurrency: int) -> bool:
        """
        Scale Lambda function concurrency
        
        Args:
            target_concurrency: Target concurrency level
            
        Returns:
            bool: True if successful, False otherwise
        """
        try:
            if target_concurrency > self.max_concurrent_executions:
                target_concurrency = self.max_concurrent_executions
            
            if target_concurrency > 0:
                # Set provisioned concurrency
                self.lambda_client.put_provisioned_concurrency_config(
                    FunctionName=self.lambda_function_name,
                    ProvisionedConcurrencyUnits=target_concurrency
                )
            else:
                # Remove provisioned concurrency
                try:
                    self.lambda_client.delete_provisioned_concurrency_config(
                        FunctionName=self.lambda_function_name
                    )
                except ClientError:
                    pass  # Already deleted or doesn't exist
            
            logger.info(f"Lambda concurrency scaled to {target_concurrency}")
            return True
            
        except Exception as e:
            logger.error(f"Error scaling Lambda concurrency: {str(e)}")
            return False
    
    def auto_scale_based_on_queue_depth(self) -> Dict[str, Any]:
        """
        Automatically scale Lambda based on queue depth
        
        Returns:
            Dict containing scaling decision and metrics
        """
        try:
            metrics = self.get_queue_metrics()
            
            if 'error' in metrics:
                return {'error': 'Failed to get queue metrics'}
            
            # Calculate queue depth
            processing_queue_depth = metrics['processing_queue']['approximate_number_of_messages']
            
            # Determine target concurrency based on queue depth
            if processing_queue_depth > 100:
                target_concurrency = min(50, self.max_concurrent_executions)
            elif processing_queue_depth > 50:
                target_concurrency = min(25, self.max_concurrent_executions)
            elif processing_queue_depth > 20:
                target_concurrency = min(10, self.max_concurrent_executions)
            elif processing_queue_depth > 5:
                target_concurrency = min(5, self.max_concurrent_executions)
            else:
                target_concurrency = 0  # No provisioned concurrency needed
            
            # Apply scaling
            scaling_success = self.scale_lambda_concurrency(target_concurrency)
            
            return {
                'queue_depth': processing_queue_depth,
                'target_concurrency': target_concurrency,
                'scaling_applied': scaling_success,
                'timestamp': datetime.now(timezone.utc).isoformat()
            }
            
        except Exception as e:
            logger.error(f"Error in auto-scaling: {str(e)}")
            return {'error': str(e)}
    
    def purge_dead_letter_queue(self) -> bool:
        """
        Purge messages from dead letter queue
        
        Returns:
            bool: True if successful, False otherwise
        """
        try:
            if not self.dead_letter_queue_url:
                logger.warning("Dead letter queue URL not configured")
                return False
            
            self.sqs_client.purge_queue(QueueUrl=self.dead_letter_queue_url)
            logger.info("Dead letter queue purged successfully")
            return True
            
        except Exception as e:
            logger.error(f"Error purging dead letter queue: {str(e)}")
            return False
    
    def reprocess_failed_documents(self, max_age_hours: int = 24) -> int:
        """
        Requeue failed documents for processing
        
        Args:
            max_age_hours: Maximum age of failed documents to reprocess
            
        Returns:
            int: Number of documents requeued
        """
        try:
            cutoff_time = datetime.now(timezone.utc) - timedelta(hours=max_age_hours)
            
            failed_documents = ClinicalDocument.objects.filter(
                processing_status='failed',
                updated_at__gte=cutoff_time
            )
            
            requeued_count = 0
            
            for document in failed_documents:
                if self.queue_document_processing(str(document.id), priority='low'):
                    requeued_count += 1
            
            logger.info(f"Requeued {requeued_count} failed documents for processing")
            return requeued_count
            
        except Exception as e:
            logger.error(f"Error reprocessing failed documents: {str(e)}")
            return 0