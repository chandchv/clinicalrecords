"""
AWS Lambda Functions for Clinical Records Document Processing

This module contains Lambda functions for serverless document processing,
providing auto-scaling and cost optimization for clinical document workflows.
"""

import json
import boto3
import os
import logging
from datetime import datetime, timezone
from typing import Dict, Any, Optional
import base64
import tempfile
import uuid

# Configure logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)

# AWS clients
s3_client = boto3.client('s3')
sqs_client = boto3.client('sqs')
textract_client = boto3.client('textract')
lambda_client = boto3.client('lambda')

# Environment variables
DOCUMENT_BUCKET = os.environ.get('DOCUMENT_BUCKET')
PROCESSING_QUEUE_URL = os.environ.get('PROCESSING_QUEUE_URL')
RESULTS_QUEUE_URL = os.environ.get('RESULTS_QUEUE_URL')
DATABASE_SECRET_ARN = os.environ.get('DATABASE_SECRET_ARN')
DJANGO_SETTINGS_MODULE = os.environ.get('DJANGO_SETTINGS_MODULE', 'RxBackend.settings')


def lambda_handler(event, context):
    """
    Main Lambda handler that routes requests to appropriate processing functions
    """
    try:
        # Determine the source of the event
        if 'Records' in event:
            # SQS message
            return handle_sqs_messages(event, context)
        elif 'source' in event and event['source'] == 'aws.s3':
            # S3 event
            return handle_s3_event(event, context)
        elif 'httpMethod' in event:
            # API Gateway event
            return handle_api_request(event, context)
        else:
            # Direct invocation
            return handle_direct_invocation(event, context)
            
    except Exception as e:
        logger.error(f"Lambda handler error: {str(e)}")
        return {
            'statusCode': 500,
            'body': json.dumps({
                'error': 'Internal server error',
                'message': str(e)
            })
        }


def handle_sqs_messages(event, context):
    """
    Process SQS messages for document processing tasks
    """
    results = []
    
    for record in event['Records']:
        try:
            # Parse SQS message
            message_body = json.loads(record['body'])
            
            # Process based on message type
            if message_body.get('task_type') == 'process_document':
                result = process_document_task(message_body)
            elif message_body.get('task_type') == 'ocr_processing':
                result = process_ocr_task(message_body)
            elif message_body.get('task_type') == 'dicom_processing':
                result = process_dicom_task(message_body)
            elif message_body.get('task_type') == 'batch_processing':
                result = process_batch_task(message_body)
            else:
                logger.warning(f"Unknown task type: {message_body.get('task_type')}")
                result = {'status': 'skipped', 'reason': 'unknown_task_type'}
            
            results.append(result)
            
        except Exception as e:
            logger.error(f"Error processing SQS record: {str(e)}")
            results.append({'status': 'error', 'error': str(e)})
    
    return {
        'statusCode': 200,
        'body': json.dumps({
            'processed': len(results),
            'results': results
        })
    }


def process_document_task(message: Dict[str, Any]) -> Dict[str, Any]:
    """
    Process a single document processing task
    """
    document_id = message.get('document_id')
    s3_key = message.get('s3_key')
    s3_bucket = message.get('s3_bucket', DOCUMENT_BUCKET)
    content_type = message.get('content_type')
    
    logger.info(f"Processing document {document_id} from s3://{s3_bucket}/{s3_key}")
    
    try:
        # Download document from S3
        with tempfile.NamedTemporaryFile() as temp_file:
            s3_client.download_fileobj(s3_bucket, s3_key, temp_file)
            temp_file.seek(0)
            
            # Process based on content type
            if content_type == 'application/pdf':
                result = process_pdf_document(temp_file.name, document_id)
            elif content_type.startswith('image/'):
                result = process_image_document(temp_file.name, document_id)
            elif content_type == 'application/dicom':
                result = process_dicom_document(temp_file.name, document_id)
            else:
                result = {'status': 'unsupported', 'content_type': content_type}
        
        # Send results back to Django via SQS
        send_processing_results(document_id, result)
        
        return {
            'status': 'completed',
            'document_id': document_id,
            'processing_result': result
        }
        
    except Exception as e:
        logger.error(f"Error processing document {document_id}: {str(e)}")
        
        # Send error notification
        send_processing_error(document_id, str(e))
        
        return {
            'status': 'error',
            'document_id': document_id,
            'error': str(e)
        }


def process_pdf_document(file_path: str, document_id: str) -> Dict[str, Any]:
    """
    Process PDF document using AWS Textract
    """
    try:
        # Read file content
        with open(file_path, 'rb') as file:
            file_content = file.read()
        
        # Use Textract for OCR
        response = textract_client.detect_document_text(
            Document={'Bytes': file_content}
        )
        
        # Extract text and confidence
        extracted_text = ""
        confidence_scores = []
        
        for block in response['Blocks']:
            if block['BlockType'] == 'LINE':
                extracted_text += block['Text'] + "\n"
                confidence_scores.append(block['Confidence'])
        
        average_confidence = sum(confidence_scores) / len(confidence_scores) if confidence_scores else 0
        
        # Parse structured data based on document type
        structured_data = parse_structured_data(extracted_text)
        
        return {
            'ocr_text': extracted_text,
            'confidence': average_confidence / 100,  # Convert to 0-1 scale
            'structured_data': structured_data,
            'processing_method': 'textract'
        }
        
    except Exception as e:
        logger.error(f"PDF processing error: {str(e)}")
        raise


def process_image_document(file_path: str, document_id: str) -> Dict[str, Any]:
    """
    Process image document using AWS Textract
    """
    try:
        # Read image content
        with open(file_path, 'rb') as file:
            file_content = file.read()
        
        # Use Textract for OCR
        response = textract_client.detect_document_text(
            Document={'Bytes': file_content}
        )
        
        # Extract text and confidence
        extracted_text = ""
        confidence_scores = []
        
        for block in response['Blocks']:
            if block['BlockType'] == 'LINE':
                extracted_text += block['Text'] + "\n"
                confidence_scores.append(block['Confidence'])
        
        average_confidence = sum(confidence_scores) / len(confidence_scores) if confidence_scores else 0
        
        # Parse structured data
        structured_data = parse_structured_data(extracted_text)
        
        return {
            'ocr_text': extracted_text,
            'confidence': average_confidence / 100,
            'structured_data': structured_data,
            'processing_method': 'textract'
        }
        
    except Exception as e:
        logger.error(f"Image processing error: {str(e)}")
        raise


def process_dicom_document(file_path: str, document_id: str) -> Dict[str, Any]:
    """
    Process DICOM document - extract metadata and generate previews
    """
    try:
        # Import pydicom (should be included in Lambda layer)
        import pydicom
        from PIL import Image
        import numpy as np
        
        # Read DICOM file
        ds = pydicom.dcmread(file_path)
        
        # Extract metadata
        metadata = {
            'study_instance_uid': str(ds.get('StudyInstanceUID', '')),
            'series_instance_uid': str(ds.get('SeriesInstanceUID', '')),
            'sop_instance_uid': str(ds.get('SOPInstanceUID', '')),
            'modality': str(ds.get('Modality', '')),
            'study_date': str(ds.get('StudyDate', '')),
            'study_time': str(ds.get('StudyTime', '')),
            'patient_name': str(ds.get('PatientName', '')),
            'patient_id': str(ds.get('PatientID', '')),
            'study_description': str(ds.get('StudyDescription', '')),
            'series_description': str(ds.get('SeriesDescription', '')),
            'body_part_examined': str(ds.get('BodyPartExamined', '')),
            'rows': int(ds.get('Rows', 0)),
            'columns': int(ds.get('Columns', 0))
        }
        
        # Generate preview image if pixel data exists
        preview_s3_key = None
        thumbnail_s3_key = None
        
        if hasattr(ds, 'pixel_array'):
            pixel_array = ds.pixel_array
            
            # Normalize pixel values
            pixel_array = ((pixel_array - pixel_array.min()) * 255.0 /
                          (pixel_array.max() - pixel_array.min())).astype(np.uint8)
            
            image = Image.fromarray(pixel_array)
            
            # Generate and upload preview
            preview_s3_key = upload_preview_image(image, document_id, 'preview')
            thumbnail_s3_key = upload_preview_image(image, document_id, 'thumbnail')
        
        return {
            'dicom_metadata': metadata,
            'preview_s3_key': preview_s3_key,
            'thumbnail_s3_key': thumbnail_s3_key,
            'processing_method': 'pydicom'
        }
        
    except Exception as e:
        logger.error(f"DICOM processing error: {str(e)}")
        raise


def parse_structured_data(text: str) -> Dict[str, Any]:
    """
    Parse structured data from OCR text based on document patterns
    """
    import re
    
    structured_data = {
        'document_type': 'unknown',
        'extracted_fields': {}
    }
    
    # Lab report patterns
    lab_patterns = [
        r'(\w+(?:\s+\w+)*)\s*:\s*([0-9.]+)\s*([a-zA-Z/]+)?\s*\(([0-9.-]+)\s*-\s*([0-9.-]+)\)',
        r'(\w+(?:\s+\w+)*)\s+([0-9.]+)\s+([a-zA-Z/]+)\s+([0-9.-]+)\s*-\s*([0-9.-]+)'
    ]
    
    # Check if it's a lab report
    lab_matches = []
    for pattern in lab_patterns:
        matches = re.findall(pattern, text, re.IGNORECASE)
        lab_matches.extend(matches)
    
    if lab_matches:
        structured_data['document_type'] = 'lab_report'
        structured_data['extracted_fields']['tests'] = []
        
        for match in lab_matches:
            test_name, value, unit, ref_min, ref_max = match
            structured_data['extracted_fields']['tests'].append({
                'name': test_name.strip(),
                'value': float(value),
                'unit': unit.strip() if unit else '',
                'reference_range': f"{ref_min}-{ref_max}",
                'is_abnormal': not (float(ref_min) <= float(value) <= float(ref_max))
            })
    
    # Prescription patterns
    med_patterns = [
        r'(\w+(?:\s+\w+)*)\s+(\d+(?:\.\d+)?)\s*(mg|g|ml|tablets?)\s+([^\n]+)',
        r'Tab\.?\s+(\w+(?:\s+\w+)*)\s+(\d+(?:\.\d+)?)\s*(mg|g)\s+([^\n]+)'
    ]
    
    med_matches = []
    for pattern in med_patterns:
        matches = re.findall(pattern, text, re.IGNORECASE)
        med_matches.extend(matches)
    
    if med_matches:
        if structured_data['document_type'] == 'unknown':
            structured_data['document_type'] = 'prescription'
        structured_data['extracted_fields']['medications'] = []
        
        for match in med_matches:
            name, strength, unit, instructions = match
            structured_data['extracted_fields']['medications'].append({
                'name': name.strip(),
                'strength': f"{strength}{unit}",
                'instructions': instructions.strip()
            })
    
    return structured_data


def upload_preview_image(image, document_id: str, image_type: str) -> str:
    """
    Upload preview/thumbnail image to S3
    """
    try:
        from PIL import Image
        import io
        
        # Resize based on type
        if image_type == 'preview':
            image.thumbnail((1024, 1024), Image.Resampling.LANCZOS)
        else:  # thumbnail
            image.thumbnail((256, 256), Image.Resampling.LANCZOS)
        
        # Convert to JPEG
        img_buffer = io.BytesIO()
        image.save(img_buffer, format='JPEG', quality=85)
        img_buffer.seek(0)
        
        # Generate S3 key
        s3_key = f"clinical_documents/{document_id}/{image_type}.jpg"
        
        # Upload to S3
        s3_client.upload_fileobj(
            img_buffer,
            DOCUMENT_BUCKET,
            s3_key,
            ExtraArgs={'ContentType': 'image/jpeg'}
        )
        
        return s3_key
        
    except Exception as e:
        logger.error(f"Error uploading {image_type} image: {str(e)}")
        return None


def send_processing_results(document_id: str, result: Dict[str, Any]):
    """
    Send processing results back to Django via SQS
    """
    try:
        message = {
            'message_type': 'processing_complete',
            'document_id': document_id,
            'result': result,
            'timestamp': datetime.now(timezone.utc).isoformat()
        }
        
        sqs_client.send_message(
            QueueUrl=RESULTS_QUEUE_URL,
            MessageBody=json.dumps(message)
        )
        
        logger.info(f"Sent processing results for document {document_id}")
        
    except Exception as e:
        logger.error(f"Error sending processing results: {str(e)}")


def send_processing_error(document_id: str, error_message: str):
    """
    Send processing error notification
    """
    try:
        message = {
            'message_type': 'processing_error',
            'document_id': document_id,
            'error': error_message,
            'timestamp': datetime.now(timezone.utc).isoformat()
        }
        
        sqs_client.send_message(
            QueueUrl=RESULTS_QUEUE_URL,
            MessageBody=json.dumps(message)
        )
        
        logger.info(f"Sent processing error for document {document_id}")
        
    except Exception as e:
        logger.error(f"Error sending processing error: {str(e)}")


def process_ocr_task(message: Dict[str, Any]) -> Dict[str, Any]:
    """
    Dedicated OCR processing task
    """
    return process_document_task(message)


def process_dicom_task(message: Dict[str, Any]) -> Dict[str, Any]:
    """
    Dedicated DICOM processing task
    """
    return process_document_task(message)


def process_batch_task(message: Dict[str, Any]) -> Dict[str, Any]:
    """
    Process multiple documents in batch
    """
    document_ids = message.get('document_ids', [])
    results = []
    
    for doc_id in document_ids:
        try:
            # Create individual processing message
            individual_message = {
                'task_type': 'process_document',
                'document_id': doc_id,
                's3_key': message.get('s3_keys', {}).get(doc_id),
                's3_bucket': message.get('s3_bucket'),
                'content_type': message.get('content_types', {}).get(doc_id)
            }
            
            result = process_document_task(individual_message)
            results.append(result)
            
        except Exception as e:
            logger.error(f"Error in batch processing document {doc_id}: {str(e)}")
            results.append({
                'status': 'error',
                'document_id': doc_id,
                'error': str(e)
            })
    
    return {
        'status': 'batch_completed',
        'processed_count': len(results),
        'results': results
    }


def handle_s3_event(event, context):
    """
    Handle S3 events for automatic document processing
    """
    results = []
    
    for record in event['Records']:
        try:
            bucket = record['s3']['bucket']['name']
            key = record['s3']['object']['key']
            
            # Extract document ID from S3 key
            document_id = extract_document_id_from_key(key)
            
            if document_id:
                # Queue processing task
                message = {
                    'task_type': 'process_document',
                    'document_id': document_id,
                    's3_key': key,
                    's3_bucket': bucket,
                    'trigger': 's3_event'
                }
                
                sqs_client.send_message(
                    QueueUrl=PROCESSING_QUEUE_URL,
                    MessageBody=json.dumps(message)
                )
                
                results.append({'status': 'queued', 'document_id': document_id})
            else:
                results.append({'status': 'skipped', 'reason': 'no_document_id'})
                
        except Exception as e:
            logger.error(f"Error handling S3 event: {str(e)}")
            results.append({'status': 'error', 'error': str(e)})
    
    return {
        'statusCode': 200,
        'body': json.dumps({
            'processed': len(results),
            'results': results
        })
    }


def extract_document_id_from_key(s3_key: str) -> Optional[str]:
    """
    Extract document ID from S3 key path
    """
    import re
    
    # Pattern: clinical_documents/{document_id}/original.ext
    pattern = r'clinical_documents/([a-f0-9-]{36})/.*'
    match = re.match(pattern, s3_key)
    
    if match:
        return match.group(1)
    
    return None


def handle_api_request(event, context):
    """
    Handle API Gateway requests for Lambda management
    """
    try:
        http_method = event['httpMethod']
        path = event['path']
        
        if http_method == 'POST' and path == '/process':
            # Manual processing trigger
            body = json.loads(event['body'])
            document_id = body.get('document_id')
            
            if not document_id:
                return {
                    'statusCode': 400,
                    'body': json.dumps({'error': 'document_id required'})
                }
            
            # Queue processing task
            message = {
                'task_type': 'process_document',
                'document_id': document_id,
                's3_key': body.get('s3_key'),
                's3_bucket': body.get('s3_bucket', DOCUMENT_BUCKET),
                'content_type': body.get('content_type'),
                'trigger': 'api_request'
            }
            
            sqs_client.send_message(
                QueueUrl=PROCESSING_QUEUE_URL,
                MessageBody=json.dumps(message)
            )
            
            return {
                'statusCode': 200,
                'body': json.dumps({
                    'message': 'Processing queued',
                    'document_id': document_id
                })
            }
        
        elif http_method == 'GET' and path == '/health':
            # Health check
            return {
                'statusCode': 200,
                'body': json.dumps({
                    'status': 'healthy',
                    'timestamp': datetime.now(timezone.utc).isoformat()
                })
            }
        
        else:
            return {
                'statusCode': 404,
                'body': json.dumps({'error': 'Not found'})
            }
            
    except Exception as e:
        logger.error(f"API request error: {str(e)}")
        return {
            'statusCode': 500,
            'body': json.dumps({'error': str(e)})
        }


def handle_direct_invocation(event, context):
    """
    Handle direct Lambda invocation
    """
    task_type = event.get('task_type')
    
    if task_type == 'process_document':
        return process_document_task(event)
    elif task_type == 'batch_processing':
        return process_batch_task(event)
    else:
        return {
            'statusCode': 400,
            'body': json.dumps({'error': f'Unknown task type: {task_type}'})
        }